/* 打工避雷平台 · 静态演示站：纯前端检索，数据来自 ./data/companies.json */
(function () {
  'use strict';

  var ANIME_STOPS = ['#0b1026', '#1b2a6b', '#2b5fd9', '#37c9e6', '#8be9c0', '#ffe066', '#ff9f45', '#ff4d6d', '#c026d3'];
  var ANIME_LABELS = ['无记录', '极稀', '很稀', '较稀', '一般', '较多', '密集', '很密', '最密'];
  var ANIME_BORDER = '#7de3ff';
  var ANIME_NEON = '#ff5ec8';

  var D = null;
  var state = {
    q: '', cat: '', city: '', province: '', sort: 'risk', view: 'map', boardFilter: 'all'
  };
  var randomTimer = null;
  var randomPool = [];
  var voteStore = {};
  var VOTE_KEY = 'job-radar-metoo-v1';

  function $(id) { return document.getElementById(id); }
  function $$(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function hl(text, kw) {
    var safe = esc(text);
    if (!kw) return safe;
    var k = esc(kw).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    try { return safe.replace(new RegExp(k, 'gi'), function (m) { return '<mark>' + m + '</mark>'; }); }
    catch (e) { return safe; }
  }
  function riskLevel(lv) { return lv >= 3 ? 3 : (lv === 2 ? 2 : 1); }
  function riskBadge(lv) {
    var label = (D.risk_labels && D.risk_labels[String(lv)]) || '';
    return '<span class="badge r' + riskLevel(lv) + '">风险 ' + lv + '/3 · ' + esc(label) + '</span>';
  }
  function appealLabel(st) {
    return (D.appeal_status_labels && D.appeal_status_labels[st]) || '未申诉';
  }
  function fmtNum(n) { return String(n == null ? 0 : n); }

  function allReports() {
    var out = [];
    D.companies.forEach(function (c) {
      (c.reports || []).forEach(function (r) { out.push({ c: c, r: r }); });
    });
    return out;
  }
  function metooOfCompany(c) {
    var sum = 0;
    (c.reports || []).forEach(function (r) { sum += (r.metoo || 0); });
    return Math.max(c.metoo || 0, sum ? Math.round(sum * 0.6) : 0) || (c.metoo || 0);
  }
  function provinceStats() {
    var map = {};
    D.companies.forEach(function (c) {
      var p = c.province || (D.regions[c.city] && D.regions[c.city].province) || c.city;
      if (!map[p]) map[p] = { province: p, adcode: c.adcode, companies: 0, reports: 0, metoo: 0, cities: {} };
      map[p].companies += 1;
      map[p].reports += (c.reports || []).length;
      map[p].metoo += metooOfCompany(c);
      map[p].cities[c.city] = (map[p].cities[c.city] || 0) + (c.reports || []).length;
      map[p].adcode = c.adcode || map[p].adcode;
    });
    Object.keys(map).forEach(function (k) {
      var s = map[k];
      s.density = s.reports / Math.max(1, s.companies);   // 每家公司平均被举报数 = "密"
      s.cities = Object.keys(s.cities).map(function (city) { return { city: city, n: s.cities[city] }; })
        .sort(function (a, b) { return b.n - a.n; });
    });
    return map;
  }
  function heatColor(score) {
    if (!score || score <= 0) return ANIME_STOPS[0];
    var i = Math.min(ANIME_STOPS.length - 1, Math.max(0, Math.round(score * (ANIME_STOPS.length - 1))));
    return ANIME_STOPS[i];
  }
  function heatTextColor(score) {
    return score >= 0.45 ? '#0b1026' : '#dceaff';
  }

  function countUp(el, target, dur) {
    if (!el) return;
    var from = 0, start = null;
    dur = dur || 900;
    function step(ts) {
      if (!start) start = ts;
      var t = Math.min(1, (ts - start) / dur);
      var eased = 1 - Math.pow(1 - t, 3);
      el.textContent = fmtNum(Math.round(from + (target - from) * eased));
      if (t < 1) requestAnimationFrame(step);
      else { el.textContent = fmtNum(target); el.classList.add('flash'); }
    }
    requestAnimationFrame(step);
  }
  function renderStats() {
    var reports = allReports();
    var prov = provinceStats();
    var severe = D.companies.filter(function (c) { return c.risk_level === 3; }).length;
    var metoo = D.companies.reduce(function (a, c) { return a + metooOfCompany(c); }, 0);
    var appeal = D.companies.filter(function (c) { return c.appeal && c.appeal.status !== 'none'; }).length;
    $('stats').innerHTML =
      '<div class="stat"><b data-n="' + D.companies.length + '">0</b><span>收录主体</span></div>' +
      '<div class="stat"><b data-n="' + reports.length + '">0</b><span>避雷记录</span></div>' +
      '<div class="stat"><b data-n="' + severe + '">0</b><span>高风险主体</span></div>' +
      '<div class="stat"><b data-n="' + Object.keys(prov).length + '">0</b><span>覆盖省份</span></div>' +
      '<div class="stat"><b data-n="' + metoo + '">0</b><span>同问次数</span></div>' +
      '<div class="stat"><b data-n="' + appeal + '">0</b><span>申诉记录</span></div>';
    $$('#stats b').forEach(function (el, i) { setTimeout(function () { countUp(el, Number(el.getAttribute('data-n'))); }, i * 120); });
  }

  function strength(c) { return (c.reports || []).length * 2 + metooOfCompany(c) / 20; }
  function strengthOfSet(list) {
    var max = 1;
    list.forEach(function (c) { max = Math.max(max, strength(c)); });
    return max;
  }
  function renderList(elId, list, ranked) {
    var el = $(elId);
    if (!el) return;
    var max = strengthOfSet(list.length ? list : D.companies);
    el.innerHTML = list.map(function (c, i) {
      var w = Math.max(6, Math.round(strength(c) / max * 100));
      var lv = riskLevel(c.risk_level);
      return '<li class="enter r' + lv + '" data-cid="' + c.id + '" title="' + esc(c.name) + '">' +
        '<span class="bar" style="width:' + w + '%"></span>' +
        '<span class="row">' +
        (ranked ? '<span class="rk">' + (i + 1) + '</span>' : '<span class="rk">' + (i + 1) + '</span>') +
        '<span class="nm">' + esc(c.name) + '</span>' +
        '<span class="num">' + metooOfCompany(c) + '</span>' +
        '</span>' +
        '<span class="sub">' + esc(c.city) + ' · ' + (c.reports || []).length + ' 条记录 · 风险 ' + c.risk_level + '/3' +
        (c.appeal && c.appeal.status !== 'none' ? ' · ' + esc(appealLabel(c.appeal.status)) : '') + '</span>' +
        '<span class="sub cc">' + esc(c.credit_code || '未填写统一社会信用代码') + '</span>' +
        '</li>';
    }).join('');
  }

  function shuffle(a) {
    var arr = a.slice();
    for (var i = arr.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = arr[i]; arr[i] = arr[j]; arr[j] = t;
    }
    return arr;
  }
  function pickRandom(n) {

    var pool = D.companies.slice();
    var picked = [];
    while (picked.length < Math.min(n, pool.length)) {
      var weighted = [];
      pool.forEach(function (c) { weighted.push(c); if (strength(c) > 6) weighted.push(c); });
      var c = weighted[Math.floor(Math.random() * weighted.length)];
      picked.push(c);
      pool = pool.filter(function (x) { return x.id !== c.id; });
    }
    return picked;
  }
  function refreshRandom(animate) {
    var list = pickRandom(6);
    randomPool = list;
    renderList('random-list', list, false);
    renderList('random-list-m', list, false);
    var hint = $('randomHint');
    if (hint) hint.textContent = '每 10 秒自动轮换 · 本次 ' + new Date().toTimeString().slice(0, 8) + ' 更新';
    if (animate) {
      $$('#random-list li, #random-list-m li').forEach(function (li, i) {
        li.style.animationDelay = (i * 40) + 'ms';
      });
    }
  }

  function boardCandidates() {
    var list = D.companies.slice();
    if (state.boardFilter === 'appeal') list = list.filter(function (c) { return c.appeal && c.appeal.status !== 'none'; });
    if (state.boardFilter === 'high') list = list.filter(function (c) { return c.risk_level >= 3; });
    if (state.boardFilter === 'nocode') list = list.filter(function (c) { return !c.credit_code; });
    if (state.boardFilter === 'province' && state.province) {
      list = list.filter(function (c) { return (c.province || '') === state.province; });
    }
    if (state.boardFilter === 'city' && state.city) list = list.filter(function (c) { return c.city === state.city; });
    var key = state.sort;
    list.sort(function (a, b) {
      if (key === 'metoo') return metooOfCompany(b) - metooOfCompany(a);
      if (key === 'reports') return (b.reports || []).length - (a.reports || []).length;
      if (key === 'recent') {
        var da = (a.reports[0] || {}).date || '', db = (b.reports[0] || {}).date || '';
        return String(db).localeCompare(String(da));
      }
      return (b.risk_level - a.risk_level) || (metooOfCompany(b) - metooOfCompany(a));
    });
    return list;
  }
  function renderBoard() {
    var list = boardCandidates();
    renderList('board-list', list, true);
    renderList('board-list-m', list, true);
  }
  function renderBoardFilters() {
    var chips = [
      { k: 'all', t: '全部' },
      { k: 'high', t: '高风险' },
      { k: 'appeal', t: '有申诉' },
      { k: 'nocode', t: '缺信用代码' }
    ];
    if (state.city) chips.push({ k: 'city', t: '仅 ' + state.city });
    if (state.province) chips.push({ k: 'province', t: '仅 ' + state.province });
    $('boardFilters').innerHTML = chips.map(function (c) {
      return '<button type="button" class="fchip' + (state.boardFilter === c.k ? ' on' : '') +
        '" data-bf="' + c.k + '">' + esc(c.t) + '</button>';
    }).join('');
  }

  function loadVotes() {
    try { voteStore = JSON.parse(localStorage.getItem(VOTE_KEY) || '{}') || {}; }
    catch (e) { voteStore = {}; }
  }
  function saveVotes() {
    try { localStorage.setItem(VOTE_KEY, JSON.stringify(voteStore)); } catch (e) { /* 隐私模式忽略 */ }
  }
  function voteOf(key) { return voteStore[key] || 0; }
  function voteMarkup(key, count, small) {
    var my = voteOf(key);
    return '<span class="vote" data-vote="' + esc(key) + '" data-base="' + count + '">' +
      (small ? '' : '<span class="metoo-label">我有相同问题</span>') +
      '<button type="button" class="arrow up' + (my === 1 ? ' on' : '') + '" data-dir="1" title="我有相同问题">▲</button>' +
      '<span class="cnt">' + (count + (my === 1 ? 1 : 0)) + '</span>' +
      '<button type="button" class="arrow down' + (my === -1 ? ' on' : '') + '" data-dir="-1" title="取消/不认同">▼</button>' +
      '</span>';
  }
  function handleVote(btn) {
    var box = btn.closest('.vote');
    if (!box) return;
    var key = box.getAttribute('data-vote');
    var base = Number(box.getAttribute('data-base')) || 0;
    var dir = Number(btn.getAttribute('data-dir'));
    var cur = voteOf(key);
    var next = (cur === dir) ? 0 : dir;      // 再点一次取消
    if (next === 0) delete voteStore[key]; else voteStore[key] = next;
    saveVotes();
    var cntEl = box.querySelector('.cnt');
    var value = base + (next === 1 ? 1 : 0);
    var prev = Number(cntEl.textContent) || 0;
    cntEl.textContent = value;
    cntEl.classList.remove('bump');
    void cntEl.offsetWidth;
    cntEl.classList.add('bump');
    box.querySelectorAll('.arrow').forEach(function (a) {
      a.classList.toggle('on', Number(a.getAttribute('data-dir')) === next);
    });

    $$('.vote[data-vote="' + key + '"]').forEach(function (other) {
      if (other === box) return;
      other.querySelector('.cnt').textContent = value;
      other.querySelectorAll('.arrow').forEach(function (a) {
        a.classList.toggle('on', Number(a.getAttribute('data-dir')) === next);
      });
    });
    if (next === 1) setTimeout(refreshRandomSilently, 400);
    return { value: value, prev: prev };
  }
  function refreshRandomSilently() {
    if (!randomPool.length) return;
    renderList('random-list', randomPool.slice(), false);
    renderList('random-list-m', randomPool.slice(), false);
  }

  function matches(c, r) {
    if (state.cat && r.category !== state.cat) return false;
    if (state.city && c.city !== state.city) return false;
    if (state.province && (c.province || '') !== state.province) return false;
    if (!state.q) return true;
    var q = state.q.toLowerCase();
    var hay = [c.name, c.credit_code || '', c.industry, c.city, c.province || '', c.scale,
      (c.tags || []).join(' '), r.title, r.content, r.job, r.category,
      (r.evidence || []).join(' ')].join(' ').toLowerCase();
    return hay.indexOf(q) >= 0;
  }
  function renderResults() {
    var rows = [];
    D.companies.forEach(function (c) {
      (c.reports || []).forEach(function (r) { if (matches(c, r)) rows.push({ c: c, r: r }); });
    });
    if (state.sort === 'recent') {
      rows.sort(function (a, b) { return String(b.r.date).localeCompare(String(a.r.date)); });
    } else if (state.sort === 'metoo') {
      rows.sort(function (a, b) { return (b.r.metoo || 0) - (a.r.metoo || 0); });
    } else {
      rows.sort(function (a, b) { return (b.c.risk_level - a.c.risk_level) || (b.r.metoo || 0) - (a.r.metoo || 0); });
    }
    $('resultCount').textContent = rows.length + ' 条记录';
    writeUrl();
    if (!rows.length) {
      $('results').innerHTML = '<div class="empty">没有匹配的记录。<br>换个关键词（公司名 / 统一社会信用代码 / 城市 / 岗位），或点「清空」看全部 ' +
        allReports().length + ' 条。</div>';
      return;
    }
    var shownCompany = {};
    $('results').innerHTML = rows.map(function (x) {
      var c = x.c, r = x.r;
      var hasAppeal = c.appeal && c.appeal.status !== 'none';
      var more = '';
      if (!shownCompany[c.id]) {
        shownCompany[c.id] = 1;
        if ((c.reports || []).length > 1) {
          more = '<div class="res-more">该公司共 ' + c.reports.length + ' 条记录，点开看全部 →</div>';
        }
      } else {
        more = '<div class="res-more">（同一公司的其他记录）</div>';
      }
      return '<article class="res risk' + riskLevel(c.risk_level) + (hasAppeal ? ' has-appeal' : '') + '" data-cid="' + c.id + '">' +
        '<div class="res-head">' +
        '<h3>' + hl(c.name, state.q) + '</h3>' +
        '<span class="badge cat">' + esc(r.category) + '</span>' +
        riskBadge(c.risk_level) +
        '<span class="badge">' + esc(c.city) + '</span>' +
        (c.credit_code
          ? '<span class="badge cc">' + esc(c.credit_code) + '</span>'
          : '<span class="badge" style="color:#b91c1c;border-color:#fecaca;background:#fff1f2">未填统一社会信用代码</span>') +
        voteMarkup('r' + r.id, r.metoo || 0) +
        '</div>' +
        '<p class="res-title">' + hl(r.title, state.q) + '</p>' +
        '<p class="res-body">' + hl(r.content, state.q) + '</p>' +
        '<p class="res-meta">' + esc(c.industry) + ' · ' + esc(c.scale) + ' · 岗位：' + esc(r.job) +
        ' · ' + esc(r.date) + (c.tags && c.tags.length ? ' · 标签：' + esc(c.tags.join('、')) : '') + '</p>' +
        (hasAppeal
          ? '<div class="appeal-strip"><span class="st ' + esc(c.appeal.status) + '">' + esc(appealLabel(c.appeal.status)) +
            '</span>该主体已提出申诉：' + esc(c.appeal.latest || '申诉理由处理中') + '</div>'
          : '') +
        more +
        '</article>';
    }).join('');
  }

  function readUrl() {
    var p = new URLSearchParams(location.search);
    state.q = p.get('q') || '';
    state.cat = p.get('cat') || '';
    state.city = p.get('city') || '';
    state.province = p.get('province') || '';
    state.sort = p.get('sort') || 'risk';
    state.view = p.get('view') || 'map';
  }
  function writeUrl() {
    var p = new URLSearchParams();
    if (state.q) p.set('q', state.q);
    if (state.cat) p.set('cat', state.cat);
    if (state.city) p.set('city', state.city);
    if (state.province) p.set('province', state.province);
    if (state.sort && state.sort !== 'risk') p.set('sort', state.sort);
    if (state.view && state.view !== 'map') p.set('view', state.view);
    var qs = p.toString();
    try { history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '')); } catch (e) { /* file:// 忽略 */ }
  }

  var chart = null, mapReady = false;

  function loadScript(urls, cb) {
    var i = 0;
    function next() {
      if (i >= urls.length) { cb(new Error('全部 CDN 均不可用')); return; }
      var s = document.createElement('script');
      s.src = urls[i++];
      s.onload = function () { cb(null); };
      s.onerror = function () { next(); };
      document.head.appendChild(s);
    }
    next();
  }
  function fetchJson(urls, cb) {
    var i = 0;
    function next() {
      if (i >= urls.length) { cb(new Error('GeoJSON 全部 CDN 均不可用')); return; }
      fetch(urls[i++], { cache: 'force-cache' })
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function (j) { cb(null, j); })
        .catch(function () { next(); });
    }
    next();
  }

  function provData() {
    var prov = provinceStats();
    var keys = Object.keys(prov);
    // 排名驱动归一化：颜色表示相对密度，各档颜色都会出现
    var ranked = keys.slice().sort(function (a, b) {
      return (prov[a].reports - prov[b].reports) || (prov[a].companies - prov[b].companies);
    });
    var scoreOf = {};
    ranked.forEach(function (k, i) { scoreOf[k] = ranked.length > 1 ? i / (ranked.length - 1) : 1; });
    return keys.map(function (k) {
      var s = prov[k];
      return {
        name: k, value: s.reports, density: s.density, companies: s.companies,
        metoo: s.metoo, score: scoreOf[k], adcode: s.adcode,
        cities: s.cities, color: heatColor(scoreOf[k])
      };
    }).sort(function (a, b) { return b.value - a.value; });
  }

  /* 二次元配色：霓虹描边 + 冷色梯度，越密越暖 */
  var ANIME_STOPS = ['#0b1026', '#1b2a6b', '#2b5fd9', '#37c9e6', '#8be9c0', '#ffe066', '#ff9f45', '#ff4d6d', '#c026d3'];
  var ANIME_LABELS = ['无记录', '极稀', '很稀', '较稀', '一般', '较多', '密集', '很密', '最密'];
  var ANIME_BORDER = '#7de3ff';
  var ANIME_NEON = '#ff5ec8';

  function initMap() {
    var tech = D.tech && D.tech.map_library ? D.tech.map_library : {};
    var scripts = tech.script || ['https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js'];
    var geos = tech.geojson || ['https://cdn.jsdelivr.net/gh/apache/echarts@4.9.0/map/json/china.json'];
    if ($('mapAttribution')) {
      $('mapAttribution').textContent = '地图：' + (tech.name || 'Apache ECharts') + '；边界数据：Apache ECharts 官方仓库 map/json/china.json（Apache-2.0）。' +
        (tech.note ? ' ' + tech.note : '');
    }
    renderLegend();
    if (!window.echarts) {
      loadScript(scripts, function (err) {
        if (err || !window.echarts) { fallbackGrid('地图库加载失败'); return; }
        loadGeo();
      });
    } else { loadGeo(); }

    function loadGeo() {
      fetchJson(geos, function (err, geo) {
        if (err || !geo) { fallbackGrid('边界数据加载失败'); return; }
        try {
          echarts.registerMap('china', geo);
          drawChart();
          mapReady = true;
          $('map-fallback').classList.add('hidden');
          $('map-chart').classList.remove('hidden');
        } catch (e) { fallbackGrid('地图初始化失败：' + e.message); }
      });
    }
  }

  function renderLegend() {
    var el = $('map-legend');
    if (!el) return;
    el.innerHTML = ANIME_STOPS.map(function (c, i) {
      return '<span class="swatch" style="background:' + c + ';box-shadow:0 0 6px ' + c + '"></span>' +
        '<span>' + ANIME_LABELS[i] + '</span>';
    }).join('') + '<span style="margin-left:8px">（按“每家公司平均被举报数”着色）</span>';
  }

  function drawChart() {
    var dom = $('map-chart');
    if (!dom || !window.echarts) return;
    chart = echarts.init(dom, null, { renderer: 'canvas' });
    var data = provData();
    var opt = {
      backgroundColor: 'transparent',
      textStyle: { fontFamily: '"Yu Gothic", "Noto Sans SC", "Microsoft YaHei", sans-serif' },
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(10,14,34,.9)', borderColor: ANIME_BORDER, borderWidth: 1,
        padding: [9, 12], extraCssText: 'border-radius:10px;box-shadow:0 0 16px rgba(125,227,255,.45);backdrop-filter:blur(4px)',
        textStyle: { color: '#e8f6ff', fontSize: 12 },
        formatter: function (p) {
          if (!p.data || !p.data.raw) return '<b>' + p.name + '</b><br><span style="color:#96a8d9">暂无记录</span>';
          var d = p.data;
          var cities = (d.cities || []).slice(0, 4).map(function (x) { return x.city + '(' + x.n + ')'; }).join('、');
          return '<b style="color:' + ANIME_BORDER + '">' + p.name + '</b><br>' +
            '记录数：' + d.value + '<br>' +
            '主体数：' + d.companies + '<br>' +
            '每主体平均：' + d.density.toFixed(2) + '<br>' +
            '同问：' + d.metoo +
            (cities ? '<br><span style="color:#96a8d9">主要城市：' + cities + '</span>' : '');
        }
      },
      series: [{
        type: 'map', map: 'china', roam: true, zoom: 1.16,
        scaleLimit: { min: 0.8, max: 8 },
        selectedMode: false,
        label: {
          show: true, color: '#cfe8ff', fontSize: 9,
          fontFamily: '"Yu Gothic", "Noto Sans SC", sans-serif',
          textShadowColor: 'rgba(10,14,34,.95)', textShadowBlur: 3,
          formatter: function (p) { return p.name.replace(/省|市|自治区|回族|维吾尔|壮族|特别行政区/g, ''); }
        },
        itemStyle: {
          borderColor: ANIME_BORDER, borderWidth: 0.6, borderType: 'solid',
          areaColor: '#0b1026',
          shadowColor: 'rgba(125,227,255,.55)', shadowBlur: 8, shadowOffsetY: 1
        },
        emphasis: {
          label: { show: true, color: '#ffffff', fontSize: 11, fontWeight: 'bold', textShadowColor: ANIME_NEON, textShadowBlur: 8 },
          itemStyle: {
            areaColor: ANIME_NEON, borderColor: '#ffffff', borderWidth: 1.2,
            shadowColor: ANIME_NEON, shadowBlur: 18
          }
        },
        select: {
          label: { color: '#ffffff', fontWeight: 'bold' },
          itemStyle: { areaColor: '#ff9f45', borderColor: ANIME_NEON, borderWidth: 1.2, shadowColor: ANIME_NEON, shadowBlur: 16 }
        },
        data: data.map(function (d) {
          var c = heatColor(d.score);
          return {
            name: d.name, value: d.score, raw: d, density: d.density, companies: d.companies,
            metoo: d.metoo, cities: d.cities,
            itemStyle: {
              areaColor: c,
              borderColor: ANIME_BORDER,
              borderWidth: 0.6,
              shadowColor: c === ANIME_STOPS[0] ? 'rgba(125,227,255,.35)' : c,
              shadowBlur: d.score > 0.55 ? 14 : 8
            },
            emphasis: {
              itemStyle: {
                areaColor: ANIME_NEON, borderColor: '#ffffff', borderWidth: 1.2,
                shadowColor: ANIME_NEON, shadowBlur: 20
              }
            }
          };
        })
      }],
      animationDuration: 1100,
      animationEasing: 'cubicOut',
      animationDurationUpdate: 500
    };
    chart.setOption(opt, true);

    chart.on('click', function (p) {
      if (!p.name || !p.data || !p.data.raw) return;
      state.province = (state.province === p.name) ? '' : p.name;
      state.boardFilter = state.province ? 'province' : 'all';
      renderBoardFilters(); renderBoard(); renderResults();
      if ($('mapTip')) $('mapTip').textContent = state.province ? ('已筛选：' + state.province + '（再点一次取消）') : '点击省份筛选，点空白处取消';
    });
  }

  function fallbackGrid(reason) {
    var fb = $('map-fallback');
    if (!fb) return;
    fb.classList.remove('hidden');
    var chartDom = $('map-chart');
    if (chartDom) chartDom.classList.add('hidden');
    if ($('mapTip')) $('mapTip').textContent = '已切换为热力网格（' + reason + '）';
    var data = provData();
    var maxRep = 1;
    data.forEach(function (d) { maxRep = Math.max(maxRep, d.value); });
    $('heat-grid').innerHTML = data.map(function (d) {
      var score = d.value / maxRep;
      return '<div class="heatcell" data-province="' + esc(d.name) + '" style="background:' + heatColor(score) +
        ';color:' + heatTextColor(score) + '">' +
        '<b>' + esc(d.name) + '</b>' +
        '<span>' + d.value + ' 条 · ' + d.companies + ' 主体</span>' +
        '</div>';
    }).join('') || '<p class="muted">暂无省级数据</p>';
  }

  function openCompany(cid) {
    var c = D.companies.filter(function (x) { return x.id === Number(cid); })[0];
    if (!c) return;
    var hasAppeal = c.appeal && c.appeal.status !== 'none';
    var html =
      '<h2>' + esc(c.name) + ' ' + riskBadge(c.risk_level) + '</h2>' +
      '<p class="msub">' + esc(c.city) + ' · ' + esc(c.province || '') + ' · ' + esc(c.industry) + ' · ' + esc(c.scale) +
      ' · 共 ' + (c.reports || []).length + ' 条避雷记录</p>' +
      '<p class="msub">统一社会信用代码：' +
      (c.credit_code
        ? '<span class="badge cc">' + esc(c.credit_code) + '</span>' + (c.credit_code_verified ? ' <span class="badge r1">已核验</span>' : ' <span class="badge">待核验</span>')
        : '<span class="badge r3">未填写（建议提交时补齐，避免同名误伤）</span>') +
      '</p>' +
      (hasAppeal
        ? '<div class="appeal-strip"><span class="st ' + esc(c.appeal.status) + '">' + esc(appealLabel(c.appeal.status)) +
          '</span><b>主体申诉：</b>' + esc(c.appeal.latest || '申诉理由处理中') +
          (c.appeal.count ? '（累计 ' + c.appeal.count + ' 次申诉）' : '') + '</div>'
        : '') +
      '<p class="msub">' + esc(c.summary || '') + '</p>' +
      voteMarkup('c' + c.id, metooOfCompany(c)) +
      (c.reports || []).map(function (r) {
        return '<div class="mreport">' +
          '<div class="mt">' + esc(r.title) + ' <span class="badge cat">' + esc(r.category) + '</span>' +
          '<span class="badge">' + esc(r.job) + '</span><span class="badge">' + esc(r.date) + '</span>' +
          voteMarkup('r' + r.id, r.metoo || 0, true) +
          '</div>' +
          '<div class="mc">' + esc(r.content) + '</div>' +
          '<div class="mm">城市：' + esc(r.city) +
          (r.evidence && r.evidence.length ? ' · 证据类型：' + esc(r.evidence.join('、')) : '') + '</div>' +
          (r.video ? '<div class="mm">视频证据：<a href="' + esc(r.video) + '" target="_blank" rel="noopener nofollow">' + esc(r.video) + '</a></div>' : '') +
          '</div>';
      }).join('') +
      '<p class="msub" style="margin-top:14px">内容为示例数据，仅用于演示平台形态；统一社会信用代码为按规则生成的示例值。</p>';
    $('modalBody').innerHTML = html;
    $('modal').classList.remove('hidden');
  }

  var CODE_RE = /^[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}$/;
  function checkCredit(input, hint) {
    var v = (input.value || '').trim().toUpperCase();
    input.value = v;
    if (!v) { input.classList.remove('good', 'bad'); if (hint) { hint.textContent = '格式：18 位数字与大写字母'; hint.className = 'field-hint'; } return false; }
    var ok = CODE_RE.test(v);
    input.classList.toggle('good', ok);
    input.classList.toggle('bad', !ok);
    if (hint) {
      hint.textContent = ok ? '格式正确（' + v.length + ' 位）' : ('格式可能有误（当前 ' + v.length + ' 位，应为 18 位，不含 I O S V Z）');
      hint.className = 'field-hint ' + (ok ? 'validmsg ok' : 'validmsg error');
    }
    return ok;
  }
  function creditChecksum(code) {
    var chars = '0123456789ABCDEFGHJKLMNPQRTUWXY';
    var w = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28];
    if (!CODE_RE.test(code)) return false;
    var sum = 0;
    for (var i = 0; i < 17; i++) sum += chars.indexOf(code[i]) * w[i];
    var c = 31 - (sum % 31);
    if (c === 31) c = 0;
    return chars[c] === code[17];
  }
  function bindForms() {
    var ci = $('creditInput');
    if (ci) ci.addEventListener('input', function () { checkCredit(ci, $('creditHint')); });

    if ($('demoFill')) $('demoFill').addEventListener('click', function () {
      var f = $('submitForm');
      f.company.value = '示例新科技有限公司';
      f.credit_code.value = '91330106MA2CD1E47X';
      f.city.value = '杭州';
      f.job.value = '测试工程师';
      f.category.value = '拖欠工资';
      f.date.value = '2026-10-01';
      f.title.value = '试用期工资只发一半';
      f.content.value = '入职时说试用期按 80% 发放，实际只发了一半，问 HR 说余下部分转正后补，转正两个月还没补。';
      f.evidence.value = '劳动合同, 工资流水';
      checkCredit(f.credit_code, $('creditHint'));
    });

    if ($('submitBtn')) $('submitBtn').addEventListener('click', function () {
      var f = $('submitForm');
      var msg = $('submitMsg');
      var data = {};
      new FormData(f).forEach(function (v, k) { data[k] = v; });
      var code = (data.credit_code || '').toUpperCase();

      if (!data.company || !data.title) {
        msg.textContent = '公司名称与标题必填';
        msg.className = 'validmsg error';
        return;
      }
      if (!CODE_RE.test(code)) {
        msg.textContent = '统一社会信用代码必须是 18 位（不含 I O S V Z）';
        msg.className = 'validmsg error';
        checkCredit(f.credit_code, $('creditHint'));
        return;
      }
      if ((data.content || '').trim().length < 10) {
        msg.textContent = '经过至少 10 个字，便于他人核实';
        msg.className = 'validmsg error';
        return;
      }
      if (data.video && !/^https?:\/\/[^\s]+$/i.test(data.video.trim())) {
        msg.textContent = '视频链接需以 http(s):// 开头';
        msg.className = 'validmsg error';
        return;
      }
      if (data.video && !/(bilibili\.com|douyin\.com|kuaishou\.com|channels\.weixin\.qq\.com)/i.test(data.video)) {
        msg.textContent = '视频链接只接受 B站 / 抖音 / 快手 / 视频号';
        msg.className = 'validmsg error';
        return;
      }

      var tip = creditChecksum(code) ? '' : '（信用代码校验位与真实算法不一致，请核对是否抄错）';
      msg.textContent = '上传成功，已直接发布，本站不设人工审核' + tip;
      msg.className = tip ? 'validmsg warn' : 'validmsg ok';
      addLocalReport(data);
    });

    if ($('appealBtn')) $('appealBtn').addEventListener('click', function () {
      var f = $('appealForm');
      var msg = $('appealMsg');
      var data = {};
      new FormData(f).forEach(function (v, k) { data[k] = v; });
      if (!data.company || !data.reason) { msg.textContent = '主体名称与申诉理由必填'; msg.className = 'validmsg error'; return; }
      if (!CODE_RE.test((data.credit_code || '').toUpperCase())) {
        msg.textContent = '请填写 18 位统一社会信用代码，用于确认申诉主体身份';
        msg.className = 'validmsg error';
        return;
      }
      if ((data.reason || '').trim().length < 10) {
        msg.textContent = '申诉理由至少 10 个字，并注明可核验的凭证类型';
        msg.className = 'validmsg error';
        return;
      }
      var target = D.companies.filter(function (c) {
        return (c.credit_code || '').toUpperCase() === data.credit_code.toUpperCase() ||
          c.name === data.company;
      })[0];
      if (target) {
        target.appeal = target.appeal || { status: 'none', count: 0, latest: '' };
        target.appeal.status = 'pending';
        target.appeal.count = (target.appeal.count || 0) + 1;
        target.appeal.latest = data.reason.slice(0, 120);
        msg.textContent = '申诉已提交：平台审核后会在「' + target.name + '」详情页公示结论（上传内容免审，申诉需要审核）';
        msg.className = 'validmsg ok';
        renderResults(); renderBoard(); renderStats();
      } else {
        msg.textContent = '未匹配到该主体（演示站仅含示例数据），正式部署后会进入申诉审核队列';
        msg.className = 'validmsg warn';
      }
      f.reset();
      loadAppealCaptcha();
    });
  }
  function loadAppealCaptcha() {
    var el = $('appealCaptcha');
    if (!el) return;
    el.textContent = '静态演示站不校验验证码';
  }
  function addLocalReport(d) {

    try {
      var key = 'job-radar-local-submits';
      var arr = JSON.parse(localStorage.getItem(key) || '[]');
      arr.push({ t: Date.now(), company: d.company, credit_code: d.credit_code, title: d.title });
      localStorage.setItem(key, JSON.stringify(arr.slice(-20)));
    } catch (e) { /* 隐私模式忽略 */ }
  }

  function renderChips() {
    var used = {};
    allReports().forEach(function (x) { used[x.r.category] = 1; });
    var cats = (D.categories || []).filter(function (c) { return used[c]; });
    $('catChips').innerHTML = '<button type="button" class="chip' + (state.cat ? '' : ' on') + '" data-cat="">全部</button>' +
      cats.map(function (c) {
        return '<button type="button" class="chip' + (state.cat === c ? ' on' : '') + '" data-cat="' + esc(c) + '">' + esc(c) + '</button>';
      }).join('');
  }
  function renderCities() {
    var cities = {}, provinces = {};
    D.companies.forEach(function (c) {
      cities[c.city] = (cities[c.city] || 0) + 1;
      var p = c.province || '';
      if (p) provinces[p] = 1;
    });
    $('citySel').innerHTML = '<option value="">全部城市（' + D.companies.length + '）</option>' +
      Object.keys(cities).sort().map(function (c) {
        return '<option value="' + esc(c) + '"' + (state.city === c ? ' selected' : '') + '>' + esc(c) + '（' + cities[c] + '）</option>';
      }).join('');
    if ($('cityList')) {
      $('cityList').innerHTML = Object.keys(cities).sort().map(function (c) { return '<option value="' + esc(c) + '">'; }).join('');
    }
    if ($('catSelect')) {
      $('catSelect').innerHTML = (D.categories || []).map(function (c) { return '<option>' + esc(c) + '</option>'; }).join('');
    }
  }
  function renderGuides() {
    $('guides-list').innerHTML = (D.guides || []).map(function (g) {
      return '<div class="guide"><h3>' + esc(g.title) + '</h3><ol>' +
        (g.steps || []).map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('') +
        '</ol>' + (g.note ? '<p class="note">' + esc(g.note) + '</p>' : '') + '</div>';
    }).join('');
    if ($('techNote') && D.tech && D.tech.map_library) {
      $('techNote').textContent = '地图实现：' + D.tech.map_library.name + '。' + (D.tech.map_library.note || '');
    }
  }
  function syncControls() {
    $('q').value = state.q || '';
    $('citySel').value = state.city || '';
    $('viewSel').value = state.view || 'list';
    $$('#boardSort').forEach(function (s) { s.value = state.sort || 'risk'; });
    var bm = $('boardSort-m'); if (bm) bm.value = state.sort || 'risk';
    renderChips();
    applyView();
  }
  function applyView() {
    var isMap = state.view === 'map';
    $('map').classList.toggle('hidden', !isMap);
    if (isMap && mapReady) {
      setTimeout(function () { if (chart) chart.resize(); }, 60);
    }
  }

  function bind() {
    var t = null;
    $('q').addEventListener('input', function (e) {
      clearTimeout(t);
      var v = e.target.value.trim();
      t = setTimeout(function () { state.q = v; renderResults(); }, 120);
    });
    $('clearBtn').addEventListener('click', function () {
      state.q = ''; state.cat = ''; state.city = ''; state.province = ''; state.boardFilter = 'all';
      $('q').value = ''; $('citySel').value = '';
      renderChips(); renderBoardFilters(); renderBoard(); renderResults();
      if ($('mapTip')) $('mapTip').textContent = '点击省份筛选，点空白处取消';
    });
    $('catChips').addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('.chip') : null;
      if (!b) return;
      state.cat = b.getAttribute('data-cat') || '';
      renderChips(); renderResults();
    });
    $('citySel').addEventListener('change', function (e) {
      state.city = e.target.value;
      state.boardFilter = state.city ? 'city' : 'all';
      renderBoardFilters(); renderBoard(); renderResults();
    });
    $('viewSel').addEventListener('change', function (e) {
      state.view = e.target.value;
      applyView(); writeUrl();
    });
    $('boardSort').addEventListener('change', function (e) {
      state.sort = e.target.value;
      var m = $('boardSort-m'); if (m) m.value = state.sort;
      renderBoard(); renderResults();
      $$('#boardSort').forEach(function (s) { s.value = state.sort; });
    });
    var bm = $('boardSort-m');
    if (bm) bm.addEventListener('change', function (e) {
      state.sort = e.target.value;
      $$('#boardSort').forEach(function (s) { s.value = state.sort; });
      renderBoard(); renderResults();
    });
    $('boardFilters').addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('.fchip') : null;
      if (!b) return;
      state.boardFilter = b.getAttribute('data-bf');
      renderBoardFilters(); renderBoard();
    });
    document.addEventListener('click', function (e) {
      var rb = e.target.closest ? e.target.closest('[data-reshuffle]') : null;
      if (rb) { refreshRandom(true); return; }
      var arrow = e.target.closest ? e.target.closest('.vote .arrow') : null;
      if (arrow) { e.stopPropagation(); handleVote(arrow); return; }
      var cell = e.target.closest ? e.target.closest('.heatcell') : null;
      if (cell) {
        var p = cell.getAttribute('data-province');
        state.province = (state.province === p) ? '' : p;
        state.boardFilter = state.province ? 'province' : 'all';
        renderBoardFilters(); renderBoard(); renderResults();
        return;
      }
      var card = e.target.closest ? e.target.closest('[data-cid]') : null;
      if (card && !e.target.closest('.vote')) { openCompany(card.getAttribute('data-cid')); return; }
    });
    $('modalClose').addEventListener('click', function () { $('modal').classList.add('hidden'); });
    $('modal').addEventListener('click', function (e) { if (e.target === $('modal')) $('modal').classList.add('hidden'); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') $('modal').classList.add('hidden');
      if (e.key === '/' && document.activeElement !== $('q')) { e.preventDefault(); $('q').focus(); }
    });
    window.addEventListener('resize', function () { if (chart) chart.resize(); });
    window.addEventListener('load', function () {
      setTimeout(function () { if (chart) chart.resize(); }, 120);
    });
    if ($('mapZoomIn')) $('mapZoomIn').addEventListener('click', function () { zoomMap(1.25); });
    if ($('mapZoomOut')) $('mapZoomOut').addEventListener('click', function () { zoomMap(0.8); });
    if ($('mapReset')) $('mapReset').addEventListener('click', function () {
      if (chart) { chart.dispatchAction({ type: 'restore' }); chart.setOption({ series: [{ zoom: 1.16, center: undefined }] }); }
      state.province = ''; state.boardFilter = 'all';
      renderBoardFilters(); renderBoard(); renderResults();
    });
  }
  var mapZoom = 1.16;
  function zoomMap(k) {
    if (!chart) return;
    mapZoom = Math.max(0.8, Math.min(8, mapZoom * k));
    chart.setOption({ series: [{ zoom: mapZoom }] });
  }

  /* ---------------- 右下角音符：播放 / 静音 + 长按拖动 ---------------- */
  var audio = { ctx: null, bus: null, timer: null, step: 0, playing: false };
  var NOTE_Hz = {
    C4: 261.63, D4: 293.66, E4: 329.63, G4: 392.00, A4: 440.00,
    C5: 523.25, D5: 587.33, E5: 659.25, G5: 783.99, A5: 880.00
  };
  var LEAD = ['E4', 'G4', 'A4', 'C5', 'A4', 'G4', 'E4', 'D4',
              'E4', 'G4', 'C5', 'E5', 'D5', 'C5', 'A4', 'G4'];
  var BASS = ['C4', 'C4', 'A4', 'A4', 'E4', 'E4', 'G4', 'G4',
              'C4', 'C4', 'A4', 'A4', 'D4', 'D4', 'G4', 'G4'];

  function ensureAudio() {
    if (audio.ctx) {
      if (audio.ctx.state === 'suspended') { audio.ctx.resume(); }
      return audio.ctx;
    }
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    audio.ctx = new AC();
    audio.bus = audio.ctx.createGain();
    audio.bus.gain.value = 0.16;
    audio.bus.connect(audio.ctx.destination);
    return audio.ctx;
  }

  function beep(freq, at, dur, type, peak) {
    var osc = audio.ctx.createOscillator();
    var env = audio.ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    env.gain.setValueAtTime(0.0001, at);
    env.gain.exponentialRampToValueAtTime(peak, at + 0.02);
    env.gain.exponentialRampToValueAtTime(0.0001, at + dur);
    osc.connect(env);
    env.connect(audio.bus);
    osc.start(at);
    osc.stop(at + dur + 0.03);
  }

  function scheduleStep(step, at) {
    var lead = NOTE_Hz[LEAD[step % LEAD.length]];
    var bass = NOTE_Hz[BASS[step % BASS.length]];
    beep(lead, at, 0.17, 'square', 0.22);
    if (step % 2 === 0) { beep(bass / 2, at, 0.3, 'triangle', 0.3); }
    if (step % 4 === 2) { beep(lead * 2, at + 0.09, 0.07, 'sine', 0.09); }
  }

  function tick() {
    if (!audio.playing || !audio.ctx) return;
    scheduleStep(audio.step, audio.ctx.currentTime + 0.08);
    audio.step++;
    audio.timer = setTimeout(tick, 230);
  }

  function musicStart() {
    if (!ensureAudio()) return false;
    audio.playing = true;
    if (!audio.timer) tick();
    syncMusicBtn();
    return true;
  }

  function musicStop() {
    audio.playing = false;
    clearTimeout(audio.timer);
    audio.timer = null;
    syncMusicBtn();
  }

  function musicToggle() {
    if (audio.playing) {
      musicStop();
      try { localStorage.setItem('job-radar-music', 'off'); } catch (e) {}
    } else if (musicStart()) {
      try { localStorage.setItem('job-radar-music', 'on'); } catch (e) {}
    }
    return audio.playing;
  }

  function syncMusicBtn() {
    var btn = $('musicBtn');
    if (!btn) return;
    var icon = $('musicIcon');
    btn.classList.toggle('playing', audio.playing);
    btn.classList.toggle('muted', !audio.playing);
    btn.setAttribute('aria-pressed', audio.playing ? 'true' : 'false');
    if (icon) icon.textContent = audio.playing ? '♫' : '♪̸';
    btn.title = audio.playing ? '正在播放：点击静音（长按可拖动）' : '已静音：点击播放（长按可拖动）';
  }

  function musicPos() {
    try { return JSON.parse(localStorage.getItem('job-radar-music-pos') || 'null'); } catch (e) { return null; }
  }
  function musicSavePos(x, y) {
    try { localStorage.setItem('job-radar-music-pos', JSON.stringify({ x: x, y: y })); } catch (e) {}
  }
  function musicApplyPos(x, y) {
    var btn = $('musicBtn');
    if (!btn) return null;
    var w = btn.offsetWidth || 54, h = btn.offsetHeight || 54;
    var cx = Math.min(Math.max(6, x), Math.max(6, window.innerWidth - w - 6));
    var cy = Math.min(Math.max(6, y), Math.max(6, window.innerHeight - h - 6));
    btn.style.left = cx + 'px';
    btn.style.top = cy + 'px';
    btn.style.right = 'auto';
    btn.style.bottom = 'auto';
    return { x: cx, y: cy };
  }

  function bindMusic() {
    var btn = $('musicBtn');
    if (!btn) return;
    var pos = musicPos();
    if (pos) musicApplyPos(pos.x, pos.y);
    syncMusicBtn();

    var pressStart = 0, dragging = false, moved = false;
    var startX = 0, startY = 0, boxL = 0, boxT = 0;

    btn.addEventListener('pointerdown', function (e) {
      pressStart = Date.now();
      dragging = false;
      moved = false;
      startX = e.clientX;
      startY = e.clientY;
      var r = btn.getBoundingClientRect();
      boxL = r.left;
      boxT = r.top;
      try { btn.setPointerCapture(e.pointerId); } catch (err) {}
      e.preventDefault();
    });

    btn.addEventListener('pointermove', function (e) {
      if (!pressStart) return;
      var dx = e.clientX - startX, dy = e.clientY - startY;
      if (!dragging && (Math.abs(dx) > 4 || Math.abs(dy) > 4) && Date.now() - pressStart > 260) {
        dragging = true;
        btn.classList.add('dragging');
      }
      if (dragging) {
        moved = true;
        musicApplyPos(boxL + dx, boxT + dy);
      }
    });

    function end() {
      if (dragging) {
        var r = btn.getBoundingClientRect();
        musicSavePos(r.left, r.top);
      } else if (pressStart && !moved) {
        musicToggle();
      }
      dragging = false;
      pressStart = 0;
      btn.classList.remove('dragging');
    }
    btn.addEventListener('pointerup', end);
    btn.addEventListener('pointercancel', end);
    btn.addEventListener('click', function (e) { e.preventDefault(); });

    var saved = null;
    try { saved = localStorage.getItem('job-radar-music'); } catch (e) {}
    if (saved === 'on') {
      syncMusicBtn();
      window.addEventListener('pointerdown', function () { if (!audio.playing) musicStart(); }, { once: true });
    }

    window.addEventListener('resize', function () {
      var r = btn.getBoundingClientRect();
      var got = musicApplyPos(r.left, r.top);
      if (got) musicSavePos(got.x, got.y);
    });
  }

  readUrl();
  loadVotes();
  bindMusic();
  fetch('./data/companies.json', { cache: 'no-cache' })
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function (json) {
      D = json;
      document.title = json.site.name + ' · 入职前查一查';
      $('heroTagline').textContent = json.site.tagline;
      $('navTagline').textContent = json.site.tagline;
      $('heroNotice').textContent = '提示：' + json.site.notice;
      $('footNotice').textContent = json.site.notice;
      $('updated').textContent = '数据更新：' + json.site.updated;
      renderStats();
      renderCities();
      syncControls();
      renderBoardFilters();
      renderBoard();
      renderResults();
      renderGuides();
      bindForms();
      bind();
      refreshRandom(true);
      clearInterval(randomTimer);
      randomTimer = setInterval(function () { refreshRandom(true); }, 10000);
      initMap();

      setTimeout(function () { if (!mapReady && !window.echarts) fallbackGrid('加载超时'); }, 6000);
    })
    .catch(function (err) {
      $('results').innerHTML = '<div class="empty">数据加载失败：' + esc(err.message) +
        '<br>如果是在本地直接双击打开 index.html，浏览器会因 file:// 限制拒绝读取 JSON。' +
        '<br>请用本地服务器打开，例如 <code>python -m http.server 8080</code>，访问 http://127.0.0.1:8080/docs/</div>';
    });
})();
