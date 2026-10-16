/* 打工避雷平台 · 后台审核页 */
(function () {
  'use strict';
  var token = window.ADMIN_TOKEN || '';
  var q = token ? ('?token=' + encodeURIComponent(token)) : '';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function load() {
    fetch('/api/admin/queue' + q).then(function (r) { return r.json(); }).then(function (j) {
      if (!j.ok) {
        document.getElementById('queue').textContent = j.message || '无权访问';
        document.getElementById('rejected').textContent = '—';
        document.getElementById('logs').textContent = '—';
        return;
      }
      render(j.data);
    }).catch(function (e) {
      document.getElementById('queue').textContent = '加载失败：' + e;
    });
  }

  function render(data) {
    var qEl = document.getElementById('queue');
    if (!data.pending.length) { qEl.textContent = '暂无待审核记录'; }
    else {
      qEl.innerHTML = data.pending.map(function (r) {
        return '<div class="item" data-id="' + r.id + '">' +
          '<div><b>' + esc(r.company_name) + '</b> · ' + esc(r.category) + '</div>' +
          '<div>' + esc(r.title) + '</div>' +
          '<div style="color:#6b7280;font-size:13px;white-space:pre-wrap">' + esc(r.content) + '</div>' +
          (r.video_url ? '<div style="font-size:13px">视频：' + esc(r.video_url) + '</div>' : '') +
          '<div style="color:#6b7280;font-size:12px">' + esc(r.created_at) + ' · ' + esc(r.city || '') + ' ' + esc(r.job || '') + '</div>' +
          '<div class="act">' +
          '<button class="approve" data-act="approve">通过</button>' +
          '<button class="reject" data-act="reject">驳回</button>' +
          '</div></div>';
      }).join('');
    }
    document.getElementById('rejected').innerHTML = data.rejected.length
      ? data.rejected.map(function (r) { return '<div class="item">#' + r.id + ' ' + esc(r.title) + '</div>'; }).join('')
      : '暂无';
    document.getElementById('logs').innerHTML = data.logs.length
      ? data.logs.map(function (l) {
        return '<div class="item">#' + l.report_id + ' · ' + esc(l.action) + ' · ' + esc(l.detail || '') +
          ' <span style="color:#6b7280">' + esc(l.created_at) + '</span></div>';
      }).join('')
      : '暂无';
  }

  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest ? ev.target.closest('button[data-act]') : null;
    if (!btn) return;
    var item = btn.closest('.item');
    var id = item && item.getAttribute('data-id');
    if (!id) return;
    fetch('/api/admin/review' + q, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: Number(id), action: btn.getAttribute('data-act') })
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.ok) { load(); } else { alert(j.message || '操作失败'); }
    });
  });

  load();
})();
