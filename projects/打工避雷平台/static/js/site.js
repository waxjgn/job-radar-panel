/* 打工避雷平台 · 首页交互：验证码 + 提交举报 */
(function () {
  'use strict';

  var form = document.getElementById('reportForm');
  var msg = document.getElementById('reportMsg');
  var qEl = document.getElementById('captchaQ');
  var refreshBtn = document.getElementById('refreshCaptcha');

  function setMsg(text, kind) {
    if (!msg) return;
    msg.textContent = text || '';
    msg.className = 'msg' + (kind ? ' ' + kind : '');
  }

  function loadCaptcha() {
    fetch('/api/captcha').then(function (r) { return r.json(); }).then(function (j) {
      if (j && j.ok) {
        qEl.textContent = j.data.enabled ? j.data.question : '已关闭人机验证';
      } else {
        qEl.textContent = '验证码加载失败';
      }
    }).catch(function () { qEl.textContent = '验证码加载失败'; });
  }

  if (refreshBtn) refreshBtn.addEventListener('click', loadCaptcha);
  loadCaptcha();

  if (form) {
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      setMsg('提交中…', '');
      var data = {};
      new FormData(form).forEach(function (v, k) { data[k] = v; });
      fetch('/api/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      }).then(function (r) { return r.json().then(function (j) { return { status: r.status, body: j }; }); })
        .then(function (res) {
          var body = res.body || {};
          if (body.ok) {
            setMsg(body.message || '提交成功', body.level === 'warn' ? 'warn' : 'ok');
            form.reset();
            loadCaptcha();
          } else {
            var checks = (body.checks || []).map(function (c) { return c.step + '：' + c.detail; }).join('；');
            setMsg((body.message || '提交失败') + (checks ? '（' + checks + '）' : ''), 'bad');
            loadCaptcha();
          }
        })
        .catch(function (err) { setMsg('网络错误：' + err, 'bad'); });
    });
  }
})();
