/* 打工避雷平台 · 静态演示站逻辑
   数据：./data/companies.json（纯前端检索，无需后端）
   功能：搜索(含统一社会信用代码) / 同问上下箭头 / 随机榜+排行榜(左侧垂直条) /
         中国地图热力(开源 ECharts + 官方 GeoJSON，失败自动降级网格) / 动态数显 / 申诉 */
(function () {
  'use strict';

  var D = null;                 // 全量数据
  var state = {
    q: '', cat: '', city: '', province: '', sort: 'risk', view: 'map', boardFilter: 'all'
  };
  var randomTimer = null;
  var randomPool = [];
  var voteStore = {};           // 本地"同问"记录
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

  /* ---------------- 统计与派生 ---------------- */
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
    if (!score || score <= 0) return '#ffffff';
    var stops = ['#dbeafe', '#93c5fd', '#fde68a', '#fb923c', '#ef4444', '#b91c1c', '#7f1d1d'];
    var i = Math.min(stops.length - 1, Math.max(0, Math.round((score - 0.001) * (stops.length - 1))));
    return stops[i];
  }
  function heatTextColor(score) { return score >= 0.55 ? '#fff' : '#3f2b30'; }

  /* ---------------- 动态数显 ---------------- */
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

  /* ---------------- 榜单（随机榜为主 + 可筛选排行榜） ---------------- */
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
    // 随机榜：权重与"记录密度"相关，但不完全按排名，保证轮换可见
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

  /* ---------------- 同问（上下箭头） ---------------- */
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
    void cntEl.offsetWidth;                  // 触发重排以重放动画
    cntEl.classList.add('bump');
    box.querySelectorAll('.arrow').forEach(function (a) {
      a.classList.toggle('on', Number(a.getAttribute('data-dir')) === next);
    });
    // 同步其他位置同一 key 的计数
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

  /* ---------------- 搜索 ---------------- */
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

  /* ---------------- URL 同步 ---------------- */
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

  /* ---------------- 地图（ECharts + 官方 GeoJSON，失败降级） ---------------- */
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
    var maxRep = 0;
    Object.keys(prov).forEach(function (k) { maxRep = Math.max(maxRep, prov[k].reports); });
    return Object.keys(prov).map(function (k) {
      var s = prov[k];
      var score = maxRep ? (s.reports / maxRep) : 0;    // 越密（记录越多）越红
      return {
        name: k, value: s.reports, density: s.density, companies: s.companies,
        metoo: s.metoo, score: score, adcode: s.adcode,
        cities: s.cities, color: heatColor(score)
      };
    }).sort(function (a, b) { return b.value - a.value; });
  }

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
    var stops = ['#ffffff', '#dbeafe', '#93c5fd', '#fde68a', '#fb923c', '#ef4444', '#7f1d1d'];
    var labels = ['无记录', '很少', '较少', '一般', '较多', '密集', '最密'];
    el.innerHTML = stops.map(function (c, i) {
      return '<span class="swatch" style="background:' + c + '"></span><span>' + labels[i] + '</span>';
    }).join('') + '<span style="margin-left:8px">（按“每家公司平均被举报数”着色）</span>';
  }

  function drawChart() {
    var dom = $('map-chart');
    if (!dom || !window.echarts) return;
    chart = echarts.init(dom, null, { renderer: 'canvas' });
    var data = provData();
    var opt = {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(28,16,19,.92)', borderColor: '#7f1d1d', borderWidth: 0,
        textStyle: { color: '#fee2e2', fontSize: 12 },
        formatter: function (p) {
          if (!p.data) return '<b>' + p.name + '</b><br>暂无记录';
          var d = p.data;
          var cities = (d.cities || []).slice(0, 4).map(function (x) { return x.city + '(' + x.n + ')'; }).join('、');
          return '<b>' + p.name + '</b><br>' +
            '记录数：' + d.value + '<br>' +
            '主体数：' + d.companies + '<br>' +
            '每主体平均：' + d.density.toFixed(2) + '<br>' +
            '同问：' + d.metoo +
            (cities ? '<br>主要城市：' + cities : '');
        }
      },
      visualMap: {
        type: 'continuous', min: 0, max: 1, left: 12, bottom: 18, calculable: true,
        orient: 'horizontal', itemWidth: 12, itemHeight: 110,
        text: ['密（红）', '稀（蓝）'], textStyle: { color: '#8a6b70', fontSize: 11 },
        inRange: { color: ['#ffffff', '#dbeafe', '#93c5fd', '#fde68a', '#fb923c', '#ef4444', '#7f1d1d'] }
      },
      series: [{
        type: 'map', map: 'china', roam: true, zoom: 1.16,
        scaleLimit: { min: 0.8, max: 8 },
        selectedMode: false,
        label: {
          show: true, color: '#3f2b30', fontSize: 9,
          formatter: function (p) { return p.name.replace(/省|市|自治区|回族|维吾尔|壮族|特别行政区/g, ''); }
        },
        itemStyle: { borderColor: '#e8c9cb', borderWidth: .6, areaColor: '#ffffff' },
        emphasis: {
          label: { show: true, color: '#fff', fontWeight: 'bold' },
          itemStyle: { areaColor: '#b91c1c', borderColor: '#fff', borderWidth: 1 }
        },
        select: { label: { color: '#fff' }, itemStyle: { areaColor: '#58120f' } },
        data: data.map(function (d) {
          return { name: d.name, value: d.score, raw: d, density: d.density, companies: d.companies, metoo: d.metoo, cities: d.cities };
        })
      }],
      animationDuration: 900,
      animationEasing: 'cubicOut'
    };
    chart.setOption(opt);

    chart.on('click', function (p) {
      if (!p.name || !p.data) return;
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

  /* ---------------- 弹层（含申诉公示） ---------------- */
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

  /* ---------------- 表单：信用代码校验 / 提交 / 申诉 ---------------- */
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
      // 校验位：示例数据不一定满足真实算法，因此只提示不拦截
      if (creditChecksum(code)) {
        msg.textContent = '提交成功（演示）：信用代码校验位正确';
        msg.className = 'validmsg ok';
      } else {
        msg.textContent = '已提交（演示）：信用代码校验位与真实算法不一致，请核对是否抄错';
        msg.className = 'validmsg warn';
      }
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
      var target = D.companies.filter(function (c) {
        return (c.credit_code || '').toUpperCase() === data.credit_code.toUpperCase() ||
          c.name === data.company;
      })[0];
      if (target) {
        target.appeal = target.appeal || { status: 'none', count: 0, latest: '' };
        target.appeal.status = 'pending';
        target.appeal.count = (target.appeal.count || 0) + 1;
        target.appeal.latest = data.reason.slice(0, 120);
        msg.textContent = '申诉已提交（演示）：已在「' + target.name + '」的详情页顶部与列表中标红公示';
        msg.className = 'validmsg ok';
        renderResults(); renderBoard(); renderStats();
      } else {
        msg.textContent = '未匹配到该主体（演示站仅含示例数据），正式部署后会进入申诉审核队列';
        msg.className = 'validmsg warn';
      }
      f.reset();
    });
  }
  function addLocalReport(d) {
    // 演示用：只存本地，不落库
    try {
      var key = 'job-radar-local-submits';
      var arr = JSON.parse(localStorage.getItem(key) || '[]');
      arr.push({ t: Date.now(), company: d.company, credit_code: d.credit_code, title: d.title });
      localStorage.setItem(key, JSON.stringify(arr.slice(-20)));
    } catch (e) { /* 隐私模式忽略 */ }
  }

  /* ---------------- 渲染杂项 ---------------- */
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
    } else if (isMap && !mapReady && !$('map-fallback').classList.contains('hidden')) {
      /* 已降级，保持网格 */
    }
  }

  /* ---------------- 事件 ---------------- */
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

  /* ---------------- 启动 ---------------- */
  readUrl();
  loadVotes();
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
      // 若 3 秒内地图库还没就绪，先给出网格兜底，避免空白
      setTimeout(function () { if (!mapReady && !window.echarts) fallbackGrid('加载超时'); }, 6000);
    })
    .catch(function (err) {
      $('results').innerHTML = '<div class="empty">数据加载失败：' + esc(err.message) +
        '<br>如果是在本地直接双击打开 index.html，浏览器会因 file:// 限制拒绝读取 JSON。' +
        '<br>请用本地服务器打开，例如 <code>python -m http.server 8080</code>，访问 http://127.0.0.1:8080/docs/</div>';
    });
})();
