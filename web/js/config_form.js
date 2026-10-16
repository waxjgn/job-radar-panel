/* config_form.js —— 由后端 Schema 动态渲染配置表单（含白名单增删、开关、可见性联动） */
(function () {
  'use strict';

  var SPECIAL_ENVS = ['all', 'sqlite', 'mysql', 'captcha', 'rate_limit', 'nginx_ssl'];
  var model = null;          // 后端返回的 ui 模型
  var values = {};           // 扁平配置值（点号键）
  var events = {};           // 事件回调

  function V(key) { return values[key]; }

  function context() {
    var sec = {
      captcha: !!values['security.captcha'],
      rate_limit: !!values['security.rate_limit']
    };
    return {
      env: values['target.env'] || 'local',
      source_mode: currentSourceMode(),
      database: values['database.engine'] || 'sqlite',
      security: sec,
      nginx: { ssl: !!values['nginx.ssl'] }
    };
  }

  function currentSourceMode() {
    var on = document.querySelector('input[name="source_mode"]:checked');
    return on ? on.value : (values['project.source_mode'] || 'upload');
  }

  // 与后端 config_schema._visible 保持同一套规则
  function visible(field) {
    var key = field.key;
    var envs = field.envs || ['all'];
    if (envs.indexOf('all') >= 0) return true;
    var ctx = context();

    if (key.indexOf('project.github') === 0 && ctx.source_mode !== 'github') return false;
    if (key === 'project.upload_zip' && ctx.source_mode !== 'upload') return false;
    if (key === 'project.template' && ctx.source_mode !== 'upload') return false;
    if ((key === 'project.auto_sync' || key === 'project.sync_interval_min') && ctx.source_mode !== 'github') return false;

    if (envs.indexOf('sqlite') >= 0 && ctx.database !== 'sqlite') return false;
    if (envs.indexOf('mysql') >= 0 && ctx.database !== 'mysql') return false;
    if (envs.indexOf('captcha') >= 0 && !ctx.security.captcha) return false;
    if (envs.indexOf('rate_limit') >= 0 && !ctx.security.rate_limit) return false;
    if (envs.indexOf('nginx_ssl') >= 0 && !ctx.nginx.ssl) return false;

    var concrete = envs.filter(function (e) { return SPECIAL_ENVS.indexOf(e) < 0; });
    if (concrete.length && concrete.indexOf(ctx.env) < 0) return false;
    return true;
  }

  // ---------- 单字段渲染 ----------
  function fieldHtml(f) {
    var id = 'f_' + f.key.replace(/[.]/g, '_');
    var v = values[f.key];
    var help = f.help ? '<p class="help">' + UI.esc(f.help) + '</p>' : '';
    var label = '<label for="' + id + '">' + UI.esc(f.label) +
      (f.help ? ' <span class="hint" data-tip="' + UI.esc(f.help) + '">?</span>' : '') + '</label>';

    if (f.type === 'switch') {
      return '<div class="field" data-key="' + UI.esc(f.key) + '">' +
        '<label class="switchline"><input type="checkbox" id="' + id + '" data-key="' + UI.esc(f.key) + '"' +
        (v ? ' checked' : '') + '><span>' + UI.esc(f.label) + '</span>' +
        (f.help ? ' <span class="hint" data-tip="' + UI.esc(f.help) + '">?</span>' : '') + '</label>' +
        help + '</div>';
    }
    if (f.type === 'select') {
      var opts = (f.options || []).map(function (o) {
        return '<option value="' + UI.esc(o[0]) + '"' + (String(v) === String(o[0]) ? ' selected' : '') + '>' +
          UI.esc(o[1]) + '</option>';
      }).join('');
      return '<div class="field" data-key="' + UI.esc(f.key) + '">' + label +
        '<select id="' + id + '" data-key="' + UI.esc(f.key) + '">' + opts + '</select>' + help + '</div>';
    }
    if (f.type === 'list') {
      return '<div class="field" data-key="' + UI.esc(f.key) + '">' + label +
        '<div class="inline"><input type="text" id="' + id + '_add" placeholder="' +
        UI.esc(f.list_placeholder || '输入后点添加') + '"><button type="button" class="ghost small" data-list-add="' +
        UI.esc(f.key) + '">添加</button></div>' +
        '<div class="chips" id="' + id + '_chips">' + chips(v || [], f.key) + '</div>' + help + '</div>';
    }
    if (f.type === 'textarea') {
      return '<div class="field" data-key="' + UI.esc(f.key) + '">' + label +
        '<textarea id="' + id + '" data-key="' + UI.esc(f.key) + '" spellcheck="false">' +
        UI.esc(v || '') + '</textarea>' + help + '</div>';
    }
    if (f.type === 'file') {
      return '<div class="field" data-key="' + UI.esc(f.key) + '">' + label +
        '<input type="file" accept=".zip" data-key="' + UI.esc(f.key) + '">' +
        '<p class="help">上传后请点「上传并解压」。</p></div>';
    }
    var inputType = f.type === 'number' ? 'number' : (f.type === 'password' ? 'password' : 'text');
    var extra = '';
    if (f.type === 'number') {
      if (f.min !== undefined) extra += ' min="' + f.min + '"';
      if (f.max !== undefined) extra += ' max="' + f.max + '"';
    }
    return '<div class="field" data-key="' + UI.esc(f.key) + '">' + label +
      '<input type="' + inputType + '" id="' + id + '" data-key="' + UI.esc(f.key) + '" value="' +
      UI.esc(v === undefined || v === null ? '' : v) + '"' + extra + '>' + help + '</div>';
  }

  function chips(list, key) {
    if (!list || !list.length) return '<span class="help">（空）</span>';
    return list.map(function (d) {
      return '<span class="chip">' + UI.esc(d) +
        '<button type="button" class="x" data-list-del="' + UI.esc(key) + '" data-value="' + UI.esc(d) + '">×</button></span>';
    }).join('');
  }

  // ---------- 整体渲染 ----------
  function render(uiModel, cfgFlat) {
    model = uiModel;
    values = {};
    (uiModel.groups || []).forEach(function (g) {
      (g.fields || []).forEach(function (f) { values[f.key] = f.default; });
    });
    Object.keys(cfgFlat || {}).forEach(function (k) { values[k] = cfgFlat[k]; });

    var host = UI.$('configGroups');
    host.innerHTML = (uiModel.groups || []).map(function (g) {
      if (g.key === 'advanced') return '';   // 高级模式单独一块展示
      var fields = (g.fields || []).filter(visible);
      if (!fields.length) return '';
      return '<div class="box" data-group="' + UI.esc(g.key) + '"><h3>' + UI.esc(g.title) + '</h3>' +
        '<p class="help">' + UI.esc(g.desc || '') + '</p>' +
        '<div class="grid two">' + fields.map(fieldHtml).join('') + '</div></div>';
    }).join('');
  }

  // 只重渲染可见性，尽量保留用户已输入的值
  function refreshVisibility() {
    collect();
    render(model, values);
    bind(host(), events);
  }

  function host() { return UI.$('configGroups'); }

  // ---------- 读取 ----------
  function collect() {
    UI.els('[data-key]', host()).forEach(function (input) {
      var key = input.getAttribute('data-key');
      if (input.type === 'checkbox') values[key] = input.checked;
      else if (input.type === 'number') values[key] = input.value === '' ? '' : Number(input.value);
      else if (input.type === 'file') { /* 文件单独处理 */ }
      else values[key] = input.value;
    });
    return values;
  }

  function get() { return collect(); }

  function setConfig(flat) {
    Object.keys(flat || {}).forEach(function (k) { values[k] = flat[k]; });
    if (model) { render(model, values); bind(host(), events); }
  }

  // ---------- 事件绑定 ----------
  function bind(root, handlers) {
    events = handlers || events;
    if (!root) return;

    root.addEventListener('change', function (ev) {
      var t = ev.target;
      var key = t.getAttribute && t.getAttribute('data-key');
      if (!key) return;
      if (t.type === 'checkbox') values[key] = t.checked;
      else if (t.type === 'number') values[key] = t.value === '' ? '' : Number(t.value);
      else values[key] = t.value;

      if (events.onChange) events.onChange(key, values[key], values);
      // 影响可见性的字段变化后重渲染
      if (['target.env', 'database.engine', 'security.captcha', 'security.rate_limit',
        'nginx.ssl'].indexOf(key) >= 0) {
        render(model, values);
        bind(host(), events);
        if (events.onChange) events.onChange(key, values[key], values);
      }
    });

    root.addEventListener('input', function (ev) {
      var key = ev.target.getAttribute && ev.target.getAttribute('data-key');
      if (!key) return;
      values[key] = ev.target.type === 'number'
        ? (ev.target.value === '' ? '' : Number(ev.target.value)) : ev.target.value;
    });

    root.addEventListener('click', function (ev) {
      var t = ev.target;
      var add = t.getAttribute && t.getAttribute('data-list-add');
      var del = t.getAttribute && t.getAttribute('data-list-del');
      if (add) {
        var inp = UI.$('f_' + add.replace(/[.]/g, '_') + '_add');
        var val = (inp.value || '').trim().toLowerCase().replace(/^https?:\/\//, '').split('/')[0];
        if (!val) return;
        var list = values[add] || [];
        if (list.indexOf(val) < 0) list.push(val);
        values[add] = list;
        inp.value = '';
        render(model, values); bind(host(), events);
        if (events.onChange) events.onChange(add, list, values);
      }
      if (del) {
        var list2 = (values[del] || []).filter(function (d) {
          return d !== t.getAttribute('data-value');
        });
        values[del] = list2;
        render(model, values); bind(host(), events);
        if (events.onChange) events.onChange(del, list2, values);
      }
    });

    root.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter') return;
      var id = ev.target.id || '';
      if (id.indexOf('_add') > 0) {
        ev.preventDefault();
        var key = id.replace(/^f_/, '').replace(/_add$/, '').replace(/_/g, '.');
        var btn = root.querySelector('[data-list-add="' + key + '"]');
        if (btn) btn.click();
      }
    });
  }

  function setValues(flat) { setConfig(flat); }

  function getSourceMode() { return currentSourceMode(); }

  function applySourceMode(mode) {
    values['project.source_mode'] = mode;
    if (model) { render(model, values); bind(host(), events); }
  }

  window.ConfigForm = {
    render: render, get: get, setConfig: setConfig, setValues: setValues,
    bind: bind, refreshVisibility: refreshVisibility,
    getSourceMode: getSourceMode, applySourceMode: applySourceMode,
    valuesOf: function () { return values; }
  };
})();
