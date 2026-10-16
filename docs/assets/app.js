/* 打工避雷平台 · 静态演示站逻辑
   数据来源：./data/companies.json（纯前端检索，无需后端） */
(function () {
  'use strict';

  var DATA = null;
  var state = { q: '', cat: '', city: '', sort: 'risk' };

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  /* 关键词高亮：先转义再包 mark，避免 XSS */
  function hl(text, kw) {
    var safe = esc(text);
    if (!kw) return safe;
    var k = esc(kw).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    try { return safe.replace(new RegExp(k, 'gi'), function (m) { return '<mark>' + m + '</mark>'; }); }
    catch (e) { return safe; }
  }
  function riskClass(lv) { return 'risk' + (lv === 3 ? '3' : lv === 2 ? '2' : '1'); }
  function riskBadge(lv) {
    var label = (DATA.risk_labels && DATA.risk_labels[String(lv)]) || '';
    return '<span class="badge r' + lv + '">风险 ' + lv + '/3 · ' + esc(label) + '</span>';
  }

  /* ---------- 派生统计 ---------- */
  function allReports() {
    var out = [];
    DATA.companies.forEach(function (c) {
      (c.reports || []).forEach(function (r) { out.push({ c: c, r: r }); });
    });
    return out;
  }

  function matches(company, r) {
    if (state.cat && r.category !== state.cat) return false;
    if (state.city && company.city !== state.city) return false;
    if (!state.q) return true;
    var q = state.q.toLowerCase();
    var hay = [company.name, company.industry, company.city, company.scale,
      (company.tags || []).join(' '), r.title, r.content, r.job, r.category]
      .join(' ').toLowerCase();
    return hay.indexOf(q) >= 0;
  }

  /* ---------- URL 同步：搜索状态可分享（?q=押金&city=深圳&cat=虚假招聘&sort=risk） ---------- */
  function readUrl() {
    var p = new URLSearchParams(location.search);
    state.q = p.get('q') || '';
    state.cat = p.get('cat') || '';
    state.city = p.get('city') || '';
    state.sort = p.get('sort') || 'risk';
  }
  function writeUrl() {
    var p = new URLSearchParams();
    if (state.q) p.set('q', state.q);
    if (state.cat) p.set('cat', state.cat);
    if (state.city) p.set('city', state.city);
    if (state.sort && state.sort !== 'risk') p.set('sort', state.sort);
    var qs = p.toString();
    var url = location.pathname + (qs ? '?' + qs : '') + location.hash;
    try { history.replaceState(null, '', url); } catch (e) { /* file:// 下可能失败，忽略 */ }
  }

  /* ---------- 渲染 ---------- */
  function renderStats() {
    var reports = allReports();
    var cities = {};
    DATA.companies.forEach(function (c) { cities[c.city] = 1; });
    var severe = DATA.companies.filter(function (c) { return c.risk_level === 3; }).length;
    $('stats').innerHTML =
      '<div class="stat"><b>' + DATA.companies.length + '</b><span>收录公司</span></div>' +
      '<div class="stat"><b>' + reports.length + '</b><span>避雷记录</span></div>' +
      '<div class="stat"><b>' + severe + '</b><span>高风险公司</span></div>' +
      '<div class="stat"><b>' + Object.keys(cities).length + '</b><span>覆盖城市</span></div>';
  }

  function renderChips() {
    var used = {};
    allReports().forEach(function (x) { used[x.r.category] = 1; });
    var cats = (DATA.categories || []).filter(function (c) { return used[c]; });
    var html = '<button type="button" class="chip' + (state.cat ? '' : ' on') + '" data-cat="">全部</button>';
    cats.forEach(function (c) {
      html += '<button type="button" class="chip' + (state.cat === c ? ' on' : '') +
        '" data-cat="' + esc(c) + '">' + esc(c) + '</button>';
    });
    $('catChips').innerHTML = html;
  }

  function renderCities() {
    var cities = {};
    DATA.companies.forEach(function (c) { cities[c.city] = (cities[c.city] || 0) + 1; });
    var names = Object.keys(cities).sort();
    var sel = $('citySel');
    sel.innerHTML = '<option value="">全部（' + DATA.companies.length + '）</option>' +
      names.map(function (c) {
        return '<option value="' + esc(c) + '"' + (state.city === c ? ' selected' : '') + '>' +
          esc(c) + '（' + cities[c] + '）</option>';
      }).join('');
  }

  /* 把 URL 里带来的筛选条件回填到控件上 */
  function syncControls() {
    $('q').value = state.q || '';
    $('citySel').value = state.city || '';
    $('sortSel').value = state.sort || 'risk';
    renderChips();
  }

  function renderResults() {
    var rows = [];
    DATA.companies.forEach(function (c) {
      (c.reports || []).forEach(function (r) { if (matches(c, r)) rows.push({ c: c, r: r }); });
    });
    if (state.sort === 'risk') {
      rows.sort(function (a, b) { return (b.c.risk_level - a.c.risk_level) || (b.r.id - a.r.id); });
    } else if (state.sort === 'recent') {
      rows.sort(function (a, b) { return String(b.r.date).localeCompare(String(a.r.date)); });
    } else {
      rows.sort(function (a, b) { return (b.c.reports.length - a.c.reports.length) || (b.c.risk_level - a.c.risk_level); });
    }

    $('resultCount').textContent = rows.length + ' 条记录';
    writeUrl();
    if (!rows.length) {
      $('results').innerHTML = '<div class="empty">没有匹配的记录。<br>换个关键词，或清空筛选看看全部 ' +
        allReports().length + ' 条。</div>';
      return;
    }
    var seen = {};
    $('results').innerHTML = rows.map(function (x) {
      var c = x.c, r = x.r;
      var more = '';
      if (!seen[c.id]) {
        seen[c.id] = 1;
        if (c.reports.length > 1) more = '<div class="res-more">该公司共 ' + c.reports.length + ' 条记录，点开看全部 →</div>';
      } else {
        more = '<div class="res-more">（同一公司的其他记录）</div>';
      }
      return '<article class="res ' + riskClass(c.risk_level) + '" data-cid="' + c.id + '">' +
        '<div class="res-head">' +
        '<h3>' + hl(c.name, state.q) + '</h3>' +
        '<span class="badge cat">' + hs(r.category) + '</span>' +
        riskBadge(c.risk_level) +
        '<span class="badge">' + hs(c.city) + '</span>' +
        '</div>' +
        '<p class="res-title">' + hl(r.title, state.q) + '</p>' +
        '<p class="res-body">' + hl(r.content, state.q) + '</p>' +
        '<p class="res-meta">' + hs(c.industry) + ' · ' + hs(c.scale) + ' · 岗位：' + hs(r.job) +
        ' · ' + hs(r.date) + (c.tags && c.tags.length ? ' · 标签：' + hs(c.tags.join('、')) : '') + '</p>' +
        more +
        '</article>';
    }).join('');

    function hs(s) { return esc(s); }
  }

  function renderBoard() {
    var list = DATA.companies.slice().sort(function (a, b) {
      return (b.risk_level - a.risk_level) || (b.reports.length - a.reports.length) || a.name.localeCompare(b.name);
    });
    $('board-list').innerHTML = list.map(function (c) {
      return '<div class="bcard ' + riskClass(c.risk_level) + '" data-cid="' + c.id + '">' +
        '<div class="bn">' + esc(c.name) + '</div>' +
        '<div class="bm">' + esc(c.city) + ' · ' + esc(c.industry) + ' · ' + c.reports.length + ' 条记录</div>' +
        '<div class="bt">' + riskBadge(c.risk_level) +
        (c.tags || []).map(function (t) { return '<span class="badge">' + esc(t) + '</span>'; }).join('') +
        '</div></div>';
    }).join('');
  }

  function renderGuides() {
    $('guides-list').innerHTML = (DATA.guides || []).map(function (g) {
      return '<div class="guide"><h3>' + esc(g.title) + '</h3><ol>' +
        (g.steps || []).map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('') +
        '</ol>' + (g.note ? '<p class="note">' + esc(g.note) + '</p>' : '') + '</div>';
    }).join('');
  }

  /* ---------- 详情弹层 ---------- */
  function openCompany(cid) {
    var c = DATA.companies.filter(function (x) { return x.id === Number(cid); })[0];
    if (!c) return;
    var html = '<h2>' + esc(c.name) + ' ' + riskBadge(c.risk_level) + '</h2>' +
      '<p class="msub">' + esc(c.city) + ' · ' + esc(c.industry) + ' · ' + esc(c.scale) +
      ' · 共 ' + c.reports.length + ' 条避雷记录</p>' +
      '<p class="msub">' + esc(c.summary || '') + '</p>' +
      (c.reports || []).map(function (r) {
        return '<div class="mreport">' +
          '<div class="mt">' + esc(r.title) + ' <span class="badge cat">' + esc(r.category) + '</span></div>' +
          '<div class="mc">' + esc(r.content) + '</div>' +
          '<div class="mm">岗位：' + esc(r.job) + ' · 城市：' + esc(r.city) + ' · ' + esc(r.date) + '</div>' +
          (r.video ? '<div class="mm">视频证据：<a href="' + esc(r.video) + '" target="_blank" rel="noopener nofollow">' + esc(r.video) + '</a></div>' : '') +
          '</div>';
      }).join('') +
      '<p class="msub" style="margin-top:14px">内容为示例数据，仅用于演示平台形态。</p>';
    $('modalBody').innerHTML = html;
    $('modal').classList.remove('hidden');
  }

  /* ---------- 事件 ---------- */
  function bind() {
    var timer = null;
    $('q').addEventListener('input', function (e) {
      clearTimeout(timer);
      var v = e.target.value.trim();
      timer = setTimeout(function () { state.q = v; renderResults(); }, 120);
    });
    $('clearBtn').addEventListener('click', function () {
      state = { q: '', cat: '', city: '', sort: $('sortSel').value };
      $('q').value = ''; $('citySel').value = '';
      renderChips(); renderResults();
    });
    $('catChips').addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('.chip') : null;
      if (!b) return;
      state.cat = b.getAttribute('data-cat') || '';
      renderChips(); renderResults();
    });
    $('citySel').addEventListener('change', function (e) { state.city = e.target.value; renderResults(); });
    $('sortSel').addEventListener('change', function (e) { state.sort = e.target.value; renderResults(); });
    document.addEventListener('click', function (e) {
      var card = e.target.closest ? e.target.closest('[data-cid]') : null;
      if (card) { openCompany(card.getAttribute('data-cid')); return; }
    });
    $('modalClose').addEventListener('click', function () { $('modal').classList.add('hidden'); });
    $('modal').addEventListener('click', function (e) {
      if (e.target === $('modal')) $('modal').classList.add('hidden');
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') $('modal').classList.add('hidden');
      if (e.key === '/' && document.activeElement !== $('q')) { e.preventDefault(); $('q').focus(); }
    });
  }

  /* ---------- 启动 ---------- */
  readUrl();
  fetch('./data/companies.json', { cache: 'no-cache' })
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function (json) {
      DATA = json;
      document.title = json.site.name + ' · 入职前查一查';
      $('heroTagline').textContent = json.site.tagline;
      $('navTagline').textContent = json.site.tagline;
      $('heroNotice').textContent = '提示：' + json.site.notice;
      $('footNotice').textContent = json.site.notice;
      $('updated').textContent = '数据更新：' + json.site.updated;
      renderStats(); renderCities(); syncControls();
      renderResults(); renderBoard(); renderGuides();
      bind();
    })
    .catch(function (err) {
      $('results').innerHTML = '<div class="empty">数据加载失败：' + esc(err.message) +
        '<br>如果你是在本地直接双击打开 index.html，浏览器会因 file:// 限制拒绝读取 JSON。' +
        '<br>请用本地服务器打开，例如：<code>python -m http.server 8080</code>，然后访问 http://127.0.0.1:8080/docs/</div>';
    });
})();
