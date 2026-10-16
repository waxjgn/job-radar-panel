/* main.js —— 面板主流程编排：加载配置、步骤流转、各按钮动作 */
(function () {
  'use strict';

  var state = {
    ui: null,
    flat: {},
    config: {},
    env: 'local',
    templates: [],
    serviceStatus: null,
    commands: [],
    source: {}
  };

  function cs() { return state; }

  /* ======================= 初始化 ======================= */
  function init() {
    UI.initTips();
    bindSteps();
    bindSourceMode();
    bindButtons();
    LogView.init();
    loadAll().then(function () {
      UI.alertBar('');
    }).catch(function (err) {
      UI.alertBar('加载面板数据失败：' + err.message, 'error');
    });
    setInterval(refreshStatusQuiet, 15000);
  }

  function bindSteps() {
    UI.els('.step').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var step = btn.getAttribute('data-step');
        UI.goStep(step);
        if (step === '4') { runDetect(false); }
        if (step === '5') { refreshStatus(); }
        if (step === '6') { loadBackups(); }
      });
    });
    UI.$('drawerClose').addEventListener('click', UI.closeDrawer);
    UI.$('btnRefreshAll').addEventListener('click', function () {
      loadAll().then(function () { UI.toast('已刷新配置与状态'); });
    });
  }

  function loadAll() {
    return API.config().then(function (res) {
      applyConfigResponse(res.data);
      return Promise.all([
        loadTemplates(),
        loadPresets(state.env),
        refreshStatusQuiet(),
        loadBackupPreview()
      ]);
    }).then(function () {
      if (UI.currentStep() === '4') { return runDetect(false); }
    });
  }

  function applyConfigResponse(data) {
    state.ui = data.ui;
    state.flat = data.flat || {};
    state.config = data.config || {};
    state.env = state.flat['target.env'] || 'local';
    state.source = data.source || {};

    // 顶栏环境行
    var p = data.platform || (data.preset && data.preset.platform) || {};
    UI.$('platformLine').textContent =
      '运行平台：' + (p.name || '未知') + '　|　部署环境：' + ((data.preset && data.preset.name) || state.env) +
      '　|　工作目录：' + (state.flat['_workdir'] || '面板 .workdir');

    // 环境下拉
    var sel = UI.$('envSelect');
    sel.innerHTML = (data.ui.envs || []).map(function (e) {
      return '<option value="' + UI.esc(e[0]) + '"' + (String(e[0]) === String(state.env) ? ' selected' : '') +
        '>' + UI.esc(e[1]) + '</option>';
    }).join('');

    // 项目源单选
    var mode = state.flat['project.source_mode'] || 'upload';
    var radio = document.querySelector('input[name="source_mode"][value="' + mode + '"]');
    if (radio) radio.checked = true;
    reflectSourceMode(mode);

    // GitHub 字段回填
    UI.$('ghUrl').value = state.flat['project.github_url'] || '';
    UI.$('ghBranch').value = state.flat['project.branch'] || 'main';
    UI.$('ghToken').value = state.flat['project.token'] || '';
    UI.$('ghSubdir').value = state.flat['project.subdir'] || '';
    UI.$('ghAutoSync').checked = !!state.flat['project.auto_sync'];
    UI.$('ghInterval').value = state.flat['project.sync_interval_min'] || 30;

    // 模板下拉
    UI.$('templateSelect').value = state.flat['project.template'] || '';

    // 配置表单
    ConfigForm.render(state.ui, state.flat);
    ConfigForm.bind(UI.$('configGroups'), { onChange: onConfigFieldChange });

    renderSourceState(state.source);
  }

  function bindSourceMode() {
    document.querySelectorAll('input[name="source_mode"]').forEach(function (r) {
      r.addEventListener('change', function () {
        var mode = r.value;
        state.flat['project.source_mode'] = mode;
        ConfigForm.applySourceMode(mode);
        reflectSourceMode(mode);
        saveConfigQuiet();
      });
    });
  }

  function reflectSourceMode(mode) {
    UI.els('.pick').forEach(function (p) {
      p.classList.toggle('on', p.getAttribute('data-mode') === mode);
    });
    UI.$('uploadBlock').classList.toggle('hidden', mode !== 'upload');
    UI.$('githubBlock').classList.toggle('hidden', mode !== 'github');
    UI.markStepDone(1, !!mode);
  }

  function onConfigFieldChange(key, value) {
    state.flat[key] = value;
    if (key === 'target.env') {
      state.env = value;
      loadPresets(value);
    }
    if (key === 'project.template') { /* 仅记录，套用需要点按钮 */ }
    saveConfigQuiet();
  }

  /* ======================= 预设 / 模板 ======================= */
  function loadPresets(env) {
    return API.presets(env).then(function (res) {
      var d = res.data;
      UI.$('envSummary').textContent = d.current.summary;
      UI.$('envDeps').innerHTML = (d.deps.required || []).map(function (x) {
        return '<li><b>' + UI.esc(x) + '</b>（必需）</li>';
      }).concat((d.deps.optional || []).map(function (x) {
        return '<li>' + UI.esc(x) + '（可选）</li>';
      })).join('') || '<li>无需额外依赖</li>';
      UI.$('envArtifacts').innerHTML = (d.artifacts || []).map(function (x) {
        return '<li>' + UI.esc(x) + '</li>';
      }).join('') || '<li>—</li>';
      var caps = d.capabilities || {};
      var labels = { nginx: 'Nginx 反代', mysql: 'MySQL', service: '常驻服务', auto_sync: '定时同步',
        systemd: 'systemd', static_only: '仅静态', needs_remote_account: '需平台账号' };
      UI.$('envCaps').innerHTML = Object.keys(labels).map(function (k) {
        var on = !!caps[k];
        return '<span class="cap ' + (on ? 'yes' : 'no') + '">' + labels[k] + '：' + (on ? '支持' : '不支持') + '</span>';
      }).join('');
      UI.$('envNotes').innerHTML = (d.current.notes || []).map(function (n) {
        return '<li>' + UI.esc(n) + '</li>';
      }).join('');
      UI.markStepDone(2, true);
      return d;
    });
  }

  function loadTemplates() {
    return API.templates().then(function (res) {
      state.templates = res.data.templates || [];
      var sel = UI.$('templateSelect');
      sel.innerHTML = '<option value="">（不套用模板）</option>' + state.templates.map(function (t) {
        return '<option value="' + UI.esc(t.id) + '">' + UI.esc(t.name) + '</option>';
      }).join('');
      if (state.flat['project.template']) { sel.value = state.flat['project.template']; }
    });
  }

  /* ======================= 项目源 ======================= */
  function renderSourceState(src) {
    var box = UI.$('sourceState');
    if (!src || !src.exists) {
      box.innerHTML = '<b>当前工作目录还没有代码。</b>请上传 zip、从 GitHub 拉取，或直接套用内置模板。';
      return;
    }
    box.innerHTML = '<b>工作目录已有代码：</b>' + src.files + ' 个文件；入口 app.py：' +
      (src.has_app ? '有' : '无') + '；requirements.txt：' + (src.has_requirements ? '有' : '无') +
      '<br>顶层内容：' + UI.esc((src.entries || []).join('、'));
  }

  function bindButtons() {
    // --- 一键部署与运维 ---
    UI.$('btnDeploy').addEventListener('click', function () { runJobAction('deploy'); });
    UI.$('btnStart').addEventListener('click', function () { runJobAction('start'); });
    UI.$('btnStop').addEventListener('click', function () { runJobAction('stop'); });
    UI.$('btnRestart').addEventListener('click', function () { runJobAction('restart'); });
    UI.$('btnStatus').addEventListener('click', function () { refreshStatus(true); });
    UI.$('btnDbInit').addEventListener('click', function () { runJobAction('db'); });
    UI.$('btnBackupNow').addEventListener('click', function () { runJobAction('backup'); });
    UI.$('btnCancelJob').addEventListener('click', cancelJob);

    // --- 检测 / 依赖 ---
    UI.$('btnDetect').addEventListener('click', function () { runDetect(true); });
    UI.$('btnInstallDeps').addEventListener('click', installDeps);

    // --- 上传 / 模板 ---
    UI.$('btnUpload').addEventListener('click', uploadZip);
    UI.$('btnTemplateApply').addEventListener('click', applyTemplate);
    UI.$('btnTemplateInfo').addEventListener('click', showTemplateInfo);

    // --- GitHub ---
    UI.$('btnGhTest').addEventListener('click', ghTest);
    UI.$('btnGhPull').addEventListener('click', ghPull);
    UI.$('btnSyncToggle').addEventListener('click', ghSyncStatus);

    // --- 配置 ---
    UI.$('btnSaveConfig').addEventListener('click', function () { saveConfig(true); });
    UI.$('btnValidate').addEventListener('click', validateConfig);

    // --- Nginx ---
    UI.$('btnNginxReload').addEventListener('click', loadNginx);
    UI.$('btnNginxDownload').addEventListener('click', function () { window.open('/api/gen/nginx?download=1', '_blank'); });

    // --- 备份 / 导出 ---
    UI.$('btnBackup').addEventListener('click', doBackup);
    UI.$('btnBackupList').addEventListener('click', loadBackups);
    UI.$('btnExportDeploy').addEventListener('click', function () { doExport('deploy'); });
    UI.$('btnExportNginx').addEventListener('click', function () { doExport('nginx'); });
    UI.$('btnExportCode').addEventListener('click', function () { doExport('code'); });
    UI.$('btnArtifacts').addEventListener('click', showArtifacts);

    // --- 高级模式 ---
    UI.$('advancedToggle').addEventListener('change', function (ev) {
      var on = ev.target.checked;
      var panel = UI.el('.panel.advanced');
      panel.classList.toggle('hidden', !on);
      if (on) {
        UI.goStep('adv');
        loadCommands();
      } else if (UI.currentStep() === 'adv') {
        UI.goStep('1');
      }
    });
    UI.$('btnSaveCommands').addEventListener('click', saveCommands);
    UI.$('btnReloadCommands').addEventListener('click', function () { loadCommands(); });
  }

  /* ======================= 任务执行 ======================= */
  var ACTION_CALLS = {
    deploy: function () { return API.deploy(); },
    start: function () { return API.service('start'); },
    stop: function () { return API.service('stop'); },
    restart: function () { return API.service('restart'); },
    db: function () { return API.dbInit(); },
    backup: function () { return API.backup(UI.$('backupNote').value); }
  };

  var running = false;

  function runJobAction(kind) {
    if (running) { UI.toast('已有任务在运行，请等它结束或点取消', 'warn'); return; }
    var call = ACTION_CALLS[kind];
    if (!call) return;
    running = true;
    LogView.clearTask();
    UI.goStep('5');
    UI.$('jobTitle').textContent = '当前任务：提交中…';
    call().then(function (res) {
      var job = res.data.job;
      UI.toast(res.message || '任务已提交', job.level === 'error' ? 'error' : 'ok');
      trackJob(job.id);
    }).catch(function (err) {
      running = false;
      UI.$('jobTitle').textContent = '当前任务：提交失败';
      UI.toast(err.message, 'error');
      LogView.addTaskLines([{ level: 'error', text: err.message }]);
    });
  }

  function trackJob(jobId) {
    LogView.trackJob(jobId, function (job, final) {
      UI.$('jobBar').style.width = (job.progress ? job.progress.value : 0) + '%';
      UI.$('jobPercent').textContent = (job.progress ? job.progress.value : 0) + '%';
      UI.$('jobTitle').textContent = '当前任务：' + (job.title || '') +
        (job.progress && job.progress.text ? '（' + job.progress.text + '）' : '');
      if (!final) return;
      running = false;
      var lv = UI.levelClass(job.level || (job.status === 'done' ? 'ok' : 'error'));
      UI.toast((job.message || job.status), lv);
      if (job.status === 'done') {
        UI.markStepDone('5', true);
        if (job.kind === 'backup') { loadBackups(); }
        if (job.kind === 'db') { loadDbOverview(); }
      }
      refreshStatusQuiet();
      if (UI.$('logFilter').value === 'app') { LogView.refreshAppLogs(); }
    });
  }

  function cancelJob() {
    var id = LogView.currentJobId();
    if (!id) { UI.toast('当前没有正在跟踪的任务', 'warn'); return; }
    API.cancelJob(id).then(function (res) {
      UI.toast(res.message, 'warn');
    }).catch(function (err) { UI.toast(err.message, 'error'); });
  }

  /* ======================= 环境检测 ======================= */
  function runDetect(verbose) {
    UI.$('detectMsg').textContent = '检测中…';
    return API.detect().then(function (res) {
      var d = res.data;
      UI.$('detectGrid').innerHTML = (d.items || []).map(UI.detectCard).join('');
      var msg = '总体状态：' + (d.overall === 'ok' ? '全部正常' : (d.overall === 'warn' ? '有警告' : '存在错误'));
      UI.$('detectMsg').textContent = msg + '（' + (d.items || []).length + ' 项）';
      UI.$('detectMsg').className = 'validmsg ' + UI.levelClass(d.overall);
      UI.markStepDone(4, d.overall === 'ok');
      if (verbose) {
        UI.toast(msg, UI.levelClass(d.overall));
        var bad = (d.items || []).filter(function (i) { return i.level === 'error'; });
        if (bad.length) {
          UI.alertBar('有 ' + bad.length + ' 项必需依赖缺失：' +
            bad.map(function (i) { return i.name; }).join('、') + '。可点「安装依赖」自动处理。', 'error');
        } else { UI.alertBar(''); }
      }
      return d;
    }).catch(function (err) {
      UI.$('detectMsg').textContent = '检测失败：' + err.message;
      UI.$('detectMsg').className = 'validmsg error';
      throw err;
    });
  }

  function installDeps() {
    var btn = UI.$('btnInstallDeps');
    UI.busy(btn, true, '安装中…');
    API.installDeps(true).then(function (res) {
      UI.toast(res.message, 'ok');
      LogView.clearTask();
      trackJob(res.data.job.id);
    }).catch(function (err) {
      UI.toast(err.message, 'error');
    }).then(function () { UI.busy(btn, false); });
  }

  /* ======================= 上传 / 模板 / GitHub ======================= */
  function uploadZip() {
    var f = UI.$('zipFile').files[0];
    if (!f) { UI.toast('请先选择一个 .zip 压缩包', 'warn'); return; }
    if (!/\.zip$/i.test(f.name)) { UI.toast('只支持 .zip 文件', 'error'); return; }
    var fd = new FormData();
    fd.append('file', f);
    var tpl = UI.$('templateSelect').value;
    if (tpl) fd.append('template', tpl);
    if (UI.$('ghSubdir').value.trim()) fd.append('subdir', UI.$('ghSubdir').value.trim());
    var btn = UI.$('btnUpload');
    UI.busy(btn, true, '上传中…');
    API.upload(fd).then(function (res) {
      UI.toast(res.message, 'ok');
      LogView.clearTask();
      trackJob(res.data.job.id);
      setTimeout(function () { API.config().then(function (r) { renderSourceState(r.data.source); }); }, 1500);
    }).catch(function (err) {
      UI.toast(err.message, 'error');
    }).then(function () { UI.busy(btn, false); });
  }

  function applyTemplate() {
    var tpl = UI.$('templateSelect').value;
    if (!tpl) { UI.toast('请先在下拉里选中一个内置模板', 'warn'); return; }
    state.flat['project.template'] = tpl;
    state.flat['project.source_mode'] = 'upload';
    var radio = document.querySelector('input[name="source_mode"][value="upload"]');
    if (radio) radio.checked = true;
    reflectSourceMode('upload');
    saveConfig(true).then(function () {
      UI.toast('已选择模板「' + tpl + '」，点「一键部署」会自动展开并生成数据库表、接口与页面', 'ok');
      showTemplateInfo();
    });
  }

  function showTemplateInfo() {
    var tpl = UI.$('templateSelect').value || '打工避雷平台';
    API.templateInspector(tpl).then(function (res) {
      var m = res.data.manifest || {};
      var text = [];
      text.push('模板：' + (m.name || tpl) + '  版本：' + (m.version || '-'));
      text.push(m.desc || '');
      text.push('');
      text.push('数据库表（' + (m.tables || []).length + '）：');
      (m.tables || []).forEach(function (t) { text.push('  - ' + t.name + '：' + (t.desc || '')); });
      text.push('');
      text.push('接口（' + (m.routes || []).length + '）：');
      (m.routes || []).forEach(function (r) { text.push('  ' + r.method + ' ' + r.path + ' — ' + (r.desc || '')); });
      text.push('');
      text.push('页面：');
      (m.pages || []).forEach(function (p) { text.push('  - ' + p.path + '：' + (p.desc || '')); });
      text.push('');
      text.push('视频白名单默认值：' + ((m.safety && m.safety.video_allowlist) || []).join(', '));
      UI.openDrawer('内置模板内容：' + (m.name || tpl), text.join('\n'));
    }).catch(function (err) { UI.toast(err.message, 'error'); });
  }

  function ghTest() {
    var btn = UI.$('btnGhTest');
    UI.busy(btn, true, '测试中…');
    API.ghTest({ url: UI.$('ghUrl').value, branch: UI.$('ghBranch').value, token: UI.$('ghToken').value })
      .then(function (res) {
        UI.toast(res.message, UI.levelClass(res.level));
        if (res.data && res.data.branches && res.data.branches.length) {
          UI.openDrawer('仓库分支列表', res.data.branches.join('\n') +
            '\n\n默认分支：' + (res.data.default_branch || '-') +
            '\n私有仓库：' + (res.data.private ? '是' : '否') +
            '\n当前填的分支是否存在：' + (res.data.branch_exists ? '是' : '否'));
        }
      })
      .catch(function (err) { UI.toast(err.message, 'error'); })
      .then(function () { UI.busy(btn, false); });
  }

  function ghPull() {
    state.flat['project.github_url'] = UI.$('ghUrl').value;
    state.flat['project.branch'] = UI.$('ghBranch').value || 'main';
    state.flat['project.subdir'] = UI.$('ghSubdir').value;
    state.flat['project.auto_sync'] = UI.$('ghAutoSync').checked;
    state.flat['project.sync_interval_min'] = Number(UI.$('ghInterval').value || 30);
    var token = UI.$('ghToken').value;
    saveConfig(false).then(function () {
      var btn = UI.$('btnGhPull');
      UI.busy(btn, true, '拉取中…');
      API.ghPull({
        url: state.flat['project.github_url'], branch: state.flat['project.branch'],
        subdir: state.flat['project.subdir'], token: token
      }).then(function (res) {
        UI.toast(res.message, 'ok');
        LogView.clearTask();
        trackJob(res.data.job.id);
        setTimeout(function () { API.config().then(function (r) { renderSourceState(r.data.source); }); }, 2000);
      }).catch(function (err) { UI.toast(err.message, 'error'); })
        .then(function () { UI.busy(btn, false); });
    });
  }

  function ghSyncStatus() {
    API.ghSync().then(function (res) {
      var s = res.data;
      UI.openDrawer('定时同步状态', '运行中：' + (s.running ? '是' : '否') +
        '\n上次执行：' + UI.timeText(s.last_run) +
        '\n下次执行：' + UI.timeText(s.next_run) +
        '\n上次结果：' + JSON.stringify(s.last_result || {}, null, 2));
    }).catch(function (err) { UI.toast(err.message, 'error'); });
  }

  /* ======================= 配置保存 ======================= */
  function collectAll() {
    var cfg = ConfigForm.get();
    // GitHub / 文件类字段不在渲染表单里，单独合并
    cfg['project.source_mode'] = ConfigForm.getSourceMode();
    cfg['project.github_url'] = UI.$('ghUrl').value;
    cfg['project.branch'] = UI.$('ghBranch').value || 'main';
    cfg['project.token'] = UI.$('ghToken').value || state.flat['project.token'] || '';
    cfg['project.subdir'] = UI.$('ghSubdir').value;
    cfg['project.auto_sync'] = UI.$('ghAutoSync').checked;
    cfg['project.sync_interval_min'] = Number(UI.$('ghInterval').value || 30);
    cfg['project.template'] = UI.$('templateSelect').value;
    cfg['target.env'] = UI.$('envSelect').value;
    cfg['project.upload_zip'] = '';
    return cfg;
  }

  function saveConfig(verbose) {
    var cfg = collectAll();
    var btn = UI.$('btnSaveConfig');
    if (verbose) UI.busy(btn, true, '保存中…');
    return API.saveConfig(cfg).then(function (res) {
      state.flat = res.data.config ? flatten(res.data.config) : cfg;
      if (res.data.warnings && res.data.warnings.length) {
        UI.$('configMsg').textContent = '已保存，但有 ' + res.data.warnings.length + ' 条提示：' + res.data.warnings.join('；');
        UI.$('configMsg').className = 'validmsg warn';
      } else {
        UI.$('configMsg').textContent = '配置已保存';
        UI.$('configMsg').className = 'validmsg ok';
      }
      UI.markStepDone(3, true);
      if (verbose) UI.toast(res.message || '配置已保存', res.data.warnings && res.data.warnings.length ? 'warn' : 'ok');
      return res.data;
    }).catch(function (err) {
      UI.$('configMsg').textContent = err.message;
      UI.$('configMsg').className = 'validmsg error';
      if (err.payload && err.payload.data && err.payload.data.errors) {
        UI.alertBar('配置有误：' + err.payload.data.errors.join('；'), 'error');
      }
      if (verbose) UI.toast(err.message, 'error');
      throw err;
    }).then(function (v) { UI.busy(btn, false); return v; },
      function (e) { UI.busy(btn, false); throw e; });
  }

  function saveConfigQuiet() {
    clearTimeout(saveConfigQuiet._t);
    saveConfigQuiet._t = setTimeout(function () {
      saveConfig(false).then(function () { loadNginxQuiet(); }).catch(function () { /* 静默失败，等用户手动保存 */ });
    }, 700);
  }

  function flatten(nested) {
    var out = {};
    Object.keys(nested || {}).forEach(function (k) {
      var v = nested[k];
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        Object.keys(v).forEach(function (kk) { out[k + '.' + kk] = v[kk]; });
      } else { out[k] = v; }
    });
    return out;
  }

  function validateConfig() {
    var cfg = collectAll();
    API.validateConfig(cfg).then(function (res) {
      var d = res.data;
      if (d.valid) {
        UI.$('configMsg').textContent = '校验通过' + (d.warnings.length ? '（' + d.warnings.join('；') + '）' : '');
        UI.$('configMsg').className = 'validmsg ' + (d.warnings.length ? 'warn' : 'ok');
        UI.toast('校验通过', d.warnings.length ? 'warn' : 'ok');
      } else {
        UI.$('configMsg').textContent = '校验失败：' + d.errors.join('；');
        UI.$('configMsg').className = 'validmsg error';
        UI.toast('校验失败，请按提示修改', 'error');
      }
    }).catch(function (err) { UI.toast(err.message, 'error'); });
  }

  /* ======================= Nginx ======================= */
  function loadNginx() {
    return API.nginx().then(function (res) {
      UI.$('nginxPreviewBox').classList.remove('hidden');
      UI.$('nginxPreview').value = res.data.content;
      UI.toast('已生成 nginx.conf 预览', 'ok');
      return res.data;
    }).catch(function (err) { UI.toast(err.message, 'error'); });
  }

  function loadNginxQuiet() {
    API.nginx().then(function (res) {
      UI.$('nginxPreview').value = res.data.content;
    }).catch(function () { /* 忽略 */ });
  }

  /* ======================= 状态 / 数据库 ======================= */
  function refreshStatus(verbose) {
    return API.serviceStatus().then(function (res) {
      var s = res.data;
      state.serviceStatus = s;
      UI.$('serviceStatus').innerHTML =
        '<div class="sbadge ' + UI.levelClass(s.level) + '"><b>服务状态：' + UI.esc(s.message) + '</b>' +
        '<span>模式：' + UI.esc(s.mode) + '　PID：' + (s.pid || '—') +
        '　端口：' + s.port + '（' + (s.listening ? '监听中' : '未监听') + '）</span>' +
        '<span>启动时间：' + UI.timeText(s.started_at) + '　日志：' + UI.esc(s.log_file) + '</span></div>';
      var dot = UI.el('#quickStatus .dot');
      dot.className = 'dot ' + UI.levelClass(s.level);
      UI.$('quickStatusText').textContent = s.running ? '运行中' : (s.static_only ? '静态环境' : '未运行');
      UI.markStepDone('5', !!s.running);
      if (verbose) UI.toast(s.message, UI.levelClass(s.level));
      return s;
    }).catch(function (err) {
      if (verbose) UI.toast('读取状态失败：' + err.message, 'error');
    });
  }

  function refreshStatusQuiet() { return refreshStatus(false); }

  function loadDbOverview() {
    return API.dbOverview().then(function (res) {
      var d = res.data;
      if (d.engine !== 'sqlite') {
        UI.$('dbOverview').innerHTML = '当前使用 MySQL。导入方式：<code>' + UI.esc(d.hint || '') + '</code>';
        return;
      }
      if (!d.exists) { UI.$('dbOverview').textContent = '还没有数据库文件，点「初始化数据库」生成。'; return; }
      UI.$('dbOverview').innerHTML = '文件：<code>' + UI.esc(d.path) + '</code><br>' +
        (d.tables || []).map(function (t) {
          return '<span class="cap yes">' + UI.esc(t.name) + '：' + t.rows + ' 行</span>';
        }).join(' ') || '（没有表）';
    }).catch(function () { /* 忽略 */ });
  }

  /* ======================= 备份 / 导出 ======================= */
  function doBackup() { runJobAction('backup'); }

  function loadBackups() {
    return API.backupList().then(function (res) {
      var list = res.data.backups || [];
      UI.$('backupList').innerHTML = list.length ? list.map(function (b) {
        return '<li><span class="nm">' + UI.esc(b.name) + '</span>' +
          '<span class="sz">' + UI.bytes(b.size) + ' · ' + UI.timeText(b.created_at) + '</span>' +
          '<a href="/api/download?kind=backup&name=' + encodeURIComponent(b.name) + '">下载</a></li>';
      }).join('') : '<li class="help">还没有备份</li>';
    });
  }

  function loadBackupPreview() {
    return API.export().then(function (res) {
      var d = res.data;
      UI.$('exportList').innerHTML = (d.kinds || []).map(function (k) {
        return '<li><span class="nm"><b>' + UI.esc(k.name) + '</b>：' + UI.esc(k.desc) + '</span></li>';
      }).join('');
    }).catch(function () { /* 忽略 */ });
  }

  function doExport(kind) {
    API.export(kind).then(function (res) {
      var d = res.data;
      UI.toast(d.message, 'ok');
      var html = '<li><span class="nm">' + UI.esc(d.name) + '</span><span class="sz">' + UI.bytes(d.size) +
        '</span><a href="/api/download?kind=export&name=' + encodeURIComponent(d.name) + '">下载</a></li>';
      UI.$('exportList').insertAdjacentHTML('afterbegin', html);
    }).catch(function (err) { UI.toast(err.message, 'error'); });
  }

  function showArtifacts() {
    API.artifacts().then(function (res) {
      var d = res.data;
      var text = (d.files || []).map(function (f) {
        return '===== ' + f.name + ' (' + UI.bytes(f.size) + ') =====\n' + f.preview +
          (f.truncated ? '\n…（预览截断，可点导出下载完整文件）' : '');
      }).join('\n\n');
      UI.openDrawer('将要生成的 ' + d.count + ' 个文件（预览）', text);
    }).catch(function (err) { UI.toast(err.message, 'error'); });
  }

  /* ======================= 高级模式 ======================= */
  function loadCommands() {
    return API.commands().then(function (res) {
      state.commands = res.data.commands || [];
      UI.$('commandList').innerHTML = state.commands.map(function (c) {
        return '<div class="cmd" data-id="' + UI.esc(c.id) + '">' +
          '<div class="hd">' + UI.esc(c.title) + ' <span class="req">id=' + UI.esc(c.id) + '</span></div>' +
          '<p class="help">' + UI.esc(c.desc || '') + (c.cwd ? '　工作目录：' + UI.esc(c.cwd) : '') + '</p>' +
          '<code>' + UI.esc(c.cmd) + '</code>' +
          '<input class="need" placeholder="覆盖命令（留空使用上面的默认命令）" value="' + UI.esc(c.override || '') + '">' +
          '</div>';
      }).join('');
      UI.$('cmdMsg').textContent = '共 ' + state.commands.length + ' 条命令（这里就是面板真正执行的命令）';
      UI.$('cmdMsg').className = 'validmsg';
      return state.commands;
    }).catch(function (err) { UI.toast(err.message, 'error'); });
  }

  function saveCommands() {
    var overrides = {};
    UI.els('.cmd').forEach(function (box) {
      var id = box.getAttribute('data-id');
      var input = UI.el('input.need', box);
      if (input && input.value.trim()) overrides[id] = input.value.trim();
    });
    API.saveCommands(overrides).then(function (res) {
      UI.toast('命令覆盖已保存（' + Object.keys(overrides).length + ' 条）', 'ok');
      UI.$('cmdMsg').textContent = '已保存 ' + Object.keys(overrides).length + ' 条覆盖';
      UI.$('cmdMsg').className = 'validmsg ok';
      loadCommands();
      return res;
    }).catch(function (err) { UI.toast(err.message, 'error'); });
  }

  /* ======================= 启动 ======================= */
  document.addEventListener('DOMContentLoaded', init);
  window.Panel = { state: cs, saveConfig: saveConfig, loadAll: loadAll };
})();
