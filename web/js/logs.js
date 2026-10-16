/* logs.js —— 日志窗口：任务日志（轮询/S状态机）+ 应用日志跟随 */
(function () {
  'use strict';

  var taskLines = [];     // 当前任务的日志行
  var appLines = [];      // 应用运行日志
  var mode = 'log';       // log | app
  var onlyErr = false;

  function consoleEl() { return UI.$('console'); }

  function lineClass(level) {
    if (level === 'error') return 'l-error';
    if (level === 'warn') return 'l-warn';
    if (level === 'ok') return 'l-ok';
    if (level === 'cmd') return 'l-cmd';
    return '';
  }

  function render() {
    var box = consoleEl();
    var src = mode === 'log' ? taskLines : appLines;
    var rows = src.filter(function (l) {
      if (!onlyErr) return true;
      return l.level === 'error' || l.level === 'warn';
    });
    if (!rows.length) {
      box.innerHTML = '<span style="color:#64748b">' +
        (mode === 'log' ? '（还没有任务日志，点「一键部署」或「启动服务」后这里会滚动输出）'
          : '（还没有应用日志，服务启动后会写入）') + '</span>';
      return;
    }
    box.innerHTML = rows.map(function (l) {
      var t = l.t ? ('[' + new Date(l.t * 1000).toTimeString().slice(0, 8) + '] ') : '';
      return '<div class="' + lineClass(l.level) + '">' + UI.esc(t + (l.text || '')) + '</div>';
    }).join('');
    if (UI.$('logAutoScroll') && UI.$('logAutoScroll').checked) {
      box.scrollTop = box.scrollHeight;
    }
  }

  function addTaskLines(lines) {
    if (!lines || !lines.length) return;
    lines.forEach(function (l) {
      taskLines.push({ t: l.t || Date.now() / 1000, level: l.level || 'info', text: l.text || '' });
    });
    if (taskLines.length > 4000) taskLines = taskLines.slice(-3000);
    if (mode === 'log') render();
  }

  function clearTask() { taskLines = []; if (mode === 'log') render(); }

  function setAppLines(lines) {
    appLines = (lines || []).slice(-1500);
    if (mode === 'app') render();
  }

  function setMode(next) {
    mode = next;
    if (mode === 'app') { return refreshAppLogs(); }
    render();
    return Promise.resolve();
  }

  function refreshAppLogs() {
    return API.logs(400, 'all').then(function (res) {
      setAppLines(res.data.lines || []);
      return res.data;
    }).catch(function (err) {
      setAppLines([{ level: 'error', text: '读取日志失败：' + err.message }]);
      throw err;
    });
  }

  function copyAll() {
    var src = mode === 'log' ? taskLines : appLines;
    var text = src.map(function (l) { return (l.text || ''); }).join('\n');
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { UI.toast('已复制 ' + src.length + ' 行日志'); });
    } else {
      UI.openDrawer('日志全文（手动复制）', text);
    }
  }

  function init() {
    UI.$('logFilter').addEventListener('change', function (ev) { setMode(ev.target.value); });
    UI.$('logOnlyErr').addEventListener('change', function (ev) { onlyErr = ev.target.checked; render(); });
    UI.$('logAutoScroll').addEventListener('change', function () { render(); });
    UI.$('btnLogCopy').addEventListener('click', copyAll);
    UI.$('btnLogRefresh').addEventListener('click', function () {
      if (mode === 'app') { refreshAppLogs().then(function () { UI.toast('日志已刷新'); }); }
      else { UI.toast('当前任务日志实时更新中'); }
    });
    UI.$('btnLogClear').addEventListener('click', function () {
      if (mode === 'app') {
        API.logsClear().then(function () { appLines = []; render(); UI.toast('应用日志已清空'); });
      } else { clearTask(); UI.toast('日志窗口已清空'); }
    });
    render();
  }

  /* ---------- 任务轮询：替代 SSE 的兜底实现，稳定且够用 ---------- */
  var polling = null;
  var lastJobId = null;

  function trackJob(jobId, onUpdate) {
    lastJobId = jobId;
    clearTask();
    if (polling) { clearInterval(polling); }
    var since = 0;
    var ticks = 0;
    polling = setInterval(function () {
      ticks++;
      API.job(jobId, since).then(function (res) {
        var job = res.data.job;
        since = job.rev || since;
        addTaskLines(job.lines);
        if (onUpdate) onUpdate(job);
        if (job.status !== 'running' && job.status !== 'pending') {
          clearInterval(polling);
          polling = null;
          if (onUpdate) onUpdate(job, true);
        }
      }).catch(function (err) {
        addTaskLines([{ level: 'error', text: '读取任务状态失败：' + err.message }]);
        clearInterval(polling);
        polling = null;
        if (onUpdate) onUpdate({ status: 'failed', level: 'error', message: err.message }, true);
      });
      if (ticks > 3600) { clearInterval(polling); polling = null; }
    }, 900);
    return polling;
  }

  function stopTracking() {
    if (polling) { clearInterval(polling); polling = null; }
  }

  function currentJobId() { return lastJobId; }

  window.LogView = {
    init: init, addTaskLines: addTaskLines, clearTask: clearTask,
    setMode: setMode, refreshAppLogs: refreshAppLogs,
    trackJob: trackJob, stopTracking: stopTracking, currentJobId: currentJobId,
    render: render
  };
})();
