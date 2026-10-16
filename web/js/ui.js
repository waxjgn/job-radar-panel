/* ui.js —— 通用交互：Toast、抽屉、步骤导航、状态着色、帮助气泡 */
(function () {
  'use strict';

  function $(id) { return document.getElementById(id); }
  function el(sel, root) { return (root || document).querySelector(sel); }
  function els(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  // ---------- Toast ----------
  function toast(message, level) {
    var box = $('toasts');
    if (!box) { return; }
    var t = document.createElement('div');
    t.className = 'toast ' + (level || 'ok');
    t.textContent = message;
    box.appendChild(t);
    setTimeout(function () {
      t.style.transition = 'opacity .3s';
      t.style.opacity = '0';
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 320);
    }, level === 'error' ? 7000 : 3600);
  }

  // ---------- 顶部告示条 ----------
  function alertBar(message, level) {
    var box = $('globalAlert');
    if (!box) return;
    if (!message) { box.className = 'alert hidden'; box.textContent = ''; return; }
    box.className = 'alert ' + (level || 'warn');
    box.textContent = message;
  }

  // ---------- 步骤导航 ----------
  var currentStep = '1';
  function goStep(step) {
    currentStep = String(step);
    els('.step').forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-step') === currentStep);
    });
    els('.panel').forEach(function (p) {
      p.classList.toggle('active', p.getAttribute('data-panel') === currentStep);
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function markStepDone(step, done) {
    var b = el('.step[data-step="' + step + '"]');
    if (b) b.classList.toggle('done', !!done);
  }

  function stepOf(key) { return String(key); }

  // ---------- 抽屉 ----------
  function openDrawer(title, content) {
    $('drawerTitle').textContent = title || '详情';
    $('drawerBody').textContent = content || '';
    $('drawer').classList.remove('hidden');
  }
  function closeDrawer() { $('drawer').classList.add('hidden'); }

  // ---------- 状态着色工具 ----------
  function levelClass(level) {
    if (level === 'ok' || level === 'done') return 'ok';
    if (level === 'warn' || level === 'warning') return 'warn';
    if (level === 'error' || level === 'failed') return 'error';
    return 'warn';
  }

  function detectCard(item) {
    var lv = levelClass(item.level);
    var html = '<div class="dcard ' + lv + '">' +
      '<div class="n"><span class="dot ' + lv + '"></span>' + esc(item.name) +
      (item.required ? ' <span class="req">必需</span>' : '') +
      ' <span class="badge ' + lv + '">' + (item.level === 'ok' ? '正常' : (item.level === 'warn' ? '警告' : '错误')) + '</span></div>';
    if (item.version) html += '<div class="v">' + esc(item.version) + '</div>';
    html += '<div class="v">' + esc(item.detail || '') + '</div>';
    if (item.path) html += '<div class="v">' + esc(item.path) + '</div>';
    if (item.fix && lv !== 'ok') html += '<div class="f">处理建议：' + esc(item.fix) + '</div>';
    html += '</div>';
    return html;
  }

  function esc(s) {
    return String(s === undefined || s === null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function bytes(n) {
    if (!n && n !== 0) return '-';
    if (n < 1024) return n + ' B';
    if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
    if (n < 1073741824) return (n / 1048576).toFixed(2) + ' MB';
    return (n / 1073741824).toFixed(2) + ' GB';
  }

  function timeText(ts) {
    if (!ts) return '-';
    var d = new Date(ts * (ts > 1e12 ? 1 : 1000));
    function p(n) { return (n < 10 ? '0' : '') + n; }
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' +
      p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
  }

  // ---------- 帮助气泡 ----------
  function initTips() {
    document.addEventListener('mouseover', function (ev) {
      var h = ev.target.closest ? ev.target.closest('.hint') : null;
      if (!h) return;
      var text = h.getAttribute('data-tip');
      if (!text) return;
      var box = document.createElement('div');
      box.className = 'tipbox';
      box.textContent = text;
      document.body.appendChild(box);
      var r = h.getBoundingClientRect();
      var top = r.bottom + window.scrollY + 6;
      var left = Math.min(r.left + window.scrollX, window.innerWidth - 340);
      box.style.top = top + 'px';
      box.style.left = Math.max(8, left) + 'px';
      h._tip = box;
    });
    document.addEventListener('mouseout', function (ev) {
      var h = ev.target.closest ? ev.target.closest('.hint') : null;
      if (h && h._tip) { h._tip.remove(); h._tip = null; }
    });
  }

  // ---------- 按钮忙碌态 ----------
  function busy(btn, on, textWhenBusy) {
    if (!btn) return;
    if (on) {
      btn._old = btn.textContent;
      btn.disabled = true;
      if (textWhenBusy) btn.textContent = textWhenBusy;
    } else {
      btn.disabled = false;
      if (btn._old) { btn.textContent = btn._old; btn._old = null; }
    }
  }

  window.UI = {
    $: $, el: el, els: els, esc: esc, toast: toast, alertBar: alertBar,
    goStep: goStep, markStepDone: markStepDone, stepOf: stepOf,
    openDrawer: openDrawer, closeDrawer: closeDrawer,
    levelClass: levelClass, detectCard: detectCard,
    bytes: bytes, timeText: timeText, initTips: initTips, busy: busy,
    currentStep: function () { return currentStep; }
  };
})();
