/* api.js —— 与 Flask 后端通信的统一封装
   后端统一返回 {ok, data, message, level}；这里把它拆成 Promise 结果。 */
(function () {
  'use strict';

  function qs(params) {
    if (!params) return '';
    var parts = [];
    Object.keys(params).forEach(function (k) {
      var v = params[k];
      if (v === undefined || v === null || v === '') return;
      parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
    });
    return parts.length ? ('?' + parts.join('&')) : '';
  }

  function handle(res) {
    return res.text().then(function (text) {
      var json = null;
      try { json = text ? JSON.parse(text) : null; } catch (e) { json = null; }
      if (!res.ok && (!json || typeof json.ok === 'undefined')) {
        throw new Error('HTTP ' + res.status + (text ? (': ' + text.slice(0, 300)) : ''));
      }
      if (!json) throw new Error('响应不是合法 JSON：' + text.slice(0, 200));
      if (!json.ok) {
        var err = new Error(json.message || ('请求失败 HTTP ' + res.status));
        err.payload = json;
        err.status = res.status;
        throw err;
      }
      return json;
    });
  }

  function request(method, url, payload, isForm) {
    var opts = { method: method, headers: {} };
    if (payload !== undefined && payload !== null) {
      if (isForm) {
        opts.body = payload;                       // FormData，浏览器自己设 Content-Type
      } else {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(payload);
      }
    }
    return fetch(url, opts).then(handle);
  }

  window.API = {
    get: function (url, params) { return request('GET', url + qs(params)); },
    put: function (url, payload) { return request('PUT', url, payload || {}); },
    post: function (url, payload) { return request('POST', url, payload || {}); },
    del: function (url) { return request('DELETE', url); },
    upload: function (url, formData) { return request('POST', url, formData, true); },
    qs: qs,

    // ---- 具体接口 ----
    config: function () { return request('GET', '/api/config'); },
    saveConfig: function (config) { return request('PUT', '/api/config', { config: config }); },
    validateConfig: function (config) { return request('POST', '/api/config/validate', { config: config }); },
    presets: function (env) { return request('GET', '/api/presets' + qs({ env: env })); },
    templates: function () { return request('GET', '/api/templates'); },
    templateInspector: function (id) { return request('GET', '/api/template/' + encodeURIComponent(id) + '/inspector'); },
    detect: function () { return request('GET', '/api/detect'); },
    installDeps: function (force) { return request('POST', '/api/detect/install', { force: !!force }); },
    upload: function (formData) { return window.API.upload('/api/upload', formData); },
    ghTest: function (payload) { return request('POST', '/api/github/test', payload); },
    ghPull: function (payload) { return request('POST', '/api/github/pull', payload); },
    ghSync: function (action) { return request('POST', '/api/github/sync', action ? { action: action } : {}); },
    commands: function () { return request('GET', '/api/commands'); },
    saveCommands: function (overrides) { return request('POST', '/api/commands/preview', { overrides: overrides }); },
    nginx: function () { return request('GET', '/api/gen/nginx'); },
    artifacts: function () { return request('GET', '/api/gen/artifacts'); },
    writeArtifacts: function () { return request('POST', '/api/gen/artifacts', { write: true }); },
    dbInit: function () { return request('POST', '/api/db/init'); },
    dbOverview: function () { return request('GET', '/api/db/overview'); },
    deploy: function () { return request('POST', '/api/deploy'); },
    service: function (action) { return request('POST', '/api/service/' + action); },
    serviceStatus: function () { return request('GET', '/api/service/status'); },
    logs: function (lines, level) { return request('GET', '/api/logs' + qs({ lines: lines || 300, level: level || 'all' })); },
    logsClear: function () { return request('POST', '/api/logs/clear'); },
    jobs: function () { return request('GET', '/api/jobs'); },
    job: function (id, since) { return request('GET', '/api/jobs/' + id + qs({ since: since })); },
    cancelJob: function (id) { return request('DELETE', '/api/jobs/' + id); },
    backup: function (note) { return request('POST', '/api/backup', { note: note || '' }); },
    backupList: function () { return request('GET', '/api/backup'); },
    export: function (kind) { return request('POST', '/api/export', { kind: kind }); },
    info: function () { return request('GET', '/api/info'); }
  };
})();
