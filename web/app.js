'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const icons = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  people: '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v3"/>',
  heart: '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',
  tag: '<path d="M20 13 13 20a2 2 0 0 1-3 0L2 12V2h10l8 8a2 2 0 0 1 0 3Z"/><circle cx="7" cy="7" r="1"/>',
  settings: '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="18" r="2"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  scan: '<path d="M20 7V3l-3 3a8 8 0 1 0 3 10M20 3h-4"/>',
  play: '<path d="m8 4 13 8-13 8Z"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  film: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M7 3v18M17 3v18M3 8h4m-4 8h4M17 8h4m-4 8h4"/>',
  exit: '<path d="M9 4H4v16h5m5-13 5 5-5 5M9 12h10"/>',
};
function icon(name) { return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.film}</svg>`; }
function esc(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
const state = {movies: [], settings: {}, scan: {}, view: 'library', search: '', facet: '', facetValue: '', filter: '', sort: 'added', page: 1, layout: localStorage.getItem('layout') || 'poster', random: new Map()};
let dialogMovie = null, requestVersion = 0, pollTimer;
async function api(path, body) {
  const response = await fetch(path, {credentials: 'same-origin', ...(body !== undefined ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {})});
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/login') { clearTimeout(pollTimer); $('#detail').close(); login(); }
    throw new Error(result.error || '请求失败');
  }
  return result;
}
function toast(message) { $('#toast').textContent = message; $('#toast').classList.add('visible'); clearTimeout(toast.timer); toast.timer = setTimeout(() => $('#toast').classList.remove('visible'), 4000); }
function bindActions(root = document) {
  root.querySelectorAll('[data-action]').forEach(el => el.onclick = async event => {
    try { await actions[el.dataset.action]?.(el, event); } catch (error) { toast(error.message); }
  });
}
function nav(view, label, glyph, extra = '') { return `<a href="#${view}" class="nav-link ${state.view === view ? 'active' : ''}">${icon(glyph)}<span>${label}</span>${extra}</a>`; }
function shell() {
  $('#app').innerHTML = `<aside class="sidebar"><a class="brand" href="#library"><span class="brand-mark">Q</span><span>QMaxHub<small>私人影库</small></span></a>
    <div class="nav-caption">你的收藏，井然有序</div><nav aria-label="主导航">${nav('library','全部影片','grid',`<b>${state.movies.length}</b>`)}${nav('actors','演员','people')}${nav('tags','标签与系列','tag')}${nav('favorites','我的收藏','heart')}</nav>
    <div class="sidebar-bottom"><div class="source-state"><i></i><span>本地元数据<small>VIDEO · STRM · NFO</small></span></div>${nav('settings','设置与扫描','settings')}<button class="nav-link" data-action="logout">${icon('exit')}<span>退出登录</span></button><div class="version">QMAXHUB <span>v${esc(state.settings.version)}</span></div></div></aside>
    <div class="workspace"><header class="topbar"><span class="breadcrumb">我的媒体库 <span>/</span> <strong id="crumb"></strong></span><div class="top-actions"><span class="local-badge"><i></i> PRIVATE LIBRARY</span><button class="button subtle" data-action="scan">${icon('scan')}<span id="scan-button-text">扫描媒体库</span></button></div></header><main id="content"></main><footer>QMaxHub <span>你的影片，你的收藏。</span><span class="footer-right">本地管理 · 外部播放</span></footer></div>`;
  bindActions(); render();
}
function login() {
  $('#app').innerHTML = `<main class="login-page"><form id="login-form" class="login-card"><span class="brand-mark large">Q</span><span class="eyebrow">YOUR PERSONAL COLLECTION</span><h1>欢迎回到你的影库。</h1><p>让每一份收藏，都有自己的位置。</p><label>管理员密码<input name="password" type="password" minlength="10" autocomplete="current-password" required autofocus placeholder="输入部署时设置的密码"></label><button class="button primary" type="submit">打开媒体库 ${icon('arrow')}</button><p id="login-error" class="error" role="alert"></p><small>QMaxHub · 本地元数据 / 网盘直连 / 外部播放</small></form></main>`;
  $('#login-form').onsubmit = async event => {
    event.preventDefault(); const button = $('button', event.target); button.disabled = true;
    try { await api('/api/login', {password: new FormData(event.target).get('password')}); await load(); }
    catch (error) { $('#login-error').textContent = error.message; } finally { button.disabled = false; }
  };
}
async function load() {
  const [movies, settings, scan] = await Promise.all([api('/api/movies'), api('/api/settings'), api('/api/scan')]);
  state.movies = movies.items; state.settings = settings; state.scan = scan;
  shell(); route(); poll();
}
function route() {
  const value = location.hash.slice(1) || 'library';
  const [view, facet, ...rest] = value.split('/');
  state.view = ['library', 'actors', 'tags', 'favorites', 'settings'].includes(view) ? view : 'library';
  state.facet = facet || ''; state.facetValue = decodeURIComponent(rest.join('/')); state.page = 1;
  document.querySelectorAll('.nav-link').forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + state.view));
  $('#detail').close(); render();
}
function heading(kicker, title, description, trailing = '') { return `<section class="page-heading"><div><div class="eyebrow">${kicker}</div><h1>${title}</h1><p>${description}</p></div>${trailing}</section>`; }
function render() {
  if (!$('#content')) return;
  $('#crumb').textContent = ({library: '全部影片', actors: '演员', tags: '标签与系列', favorites: '我的收藏', settings: '设置与扫描'})[state.view];
  if (state.view === 'settings') renderSettings();
  else if (state.view === 'actors' && !state.facet) renderActors();
  else if (state.view === 'tags' && !state.facet) renderTags();
  else renderLibrary();
  bindActions($('#content')); updateScan();
}
function filtered() {
  const q = state.search.toLocaleLowerCase().trim();
  return state.movies.filter(m => {
    if (state.view === 'favorites' && !m.favorite) return false;
    if (state.facet === 'actor' && !m.actors.some(a => a.name === state.facetValue)) return false;
    if (state.facet === 'tag' && !m.tags.includes(state.facetValue)) return false;
    if (['studio','series'].includes(state.facet) && m[state.facet] !== state.facetValue) return false;
    if (state.filter === 'unwatched' && m.watched || state.filter === 'watched' && !m.watched || state.filter === 'missing' && m.available) return false;
    if (q && ![m.code,m.title,m.studio,m.series,...m.tags,...m.actors.map(a => a.name)].join(' ').toLocaleLowerCase().includes(q)) return false;
    return true;
  }).sort((a, b) => state.sort === 'title' ? a.code.localeCompare(b.code, undefined, {numeric:true}) : state.sort === 'date' ? (b.date || b.year).localeCompare(a.date || a.year) : state.sort === 'score' ? b.score - a.score : state.sort === 'random' ? random(a.id) - random(b.id) : b.added - a.added);
}
function random(id) { if (!state.random.has(id)) state.random.set(id, Math.random()); return state.random.get(id); }
function renderLibrary() {
  const facet = state.facetValue;
  $('#content').innerHTML = heading('THE COLLECTION', esc(facet || (state.view === 'favorites' ? '值得珍藏。' : '每一部，都是收藏。')), facet ? '从这份收藏出发，发现更多关联影片。' : '浏览、发现，让喜欢的影片触手可及。', `<div class="collection-stats"><strong>${state.movies.length.toLocaleString()}</strong><span>部影片入库</span><div>${new Set(state.movies.flatMap(m => m.actors.map(a => a.name))).size} 位演员 <span>·</span> ${state.movies.filter(m => m.favorite).length} 部收藏</div></div>`) +
    `<section class="library-controls"><div class="tab-row"><div class="tabs"><button class="tab ${!state.filter?'selected':''}" data-action="filter" data-value="">全部影片</button><button class="tab ${state.filter==='unwatched'?'selected':''}" data-action="filter" data-value="unwatched">尚未观看</button><button class="tab ${state.filter==='watched'?'selected':''}" data-action="filter" data-value="watched">已经看过</button><button class="tab ${state.filter==='missing'?'selected':''}" data-action="filter" data-value="missing">资源缺失</button></div><div class="layout-toggle" aria-label="封面比例"><button class="${state.layout==='poster'?'selected':''}" data-action="layout" data-value="poster" title="竖版海报">▥</button><button class="${state.layout==='cover'?'selected':''}" data-action="layout" data-value="cover" title="横版封面">▤</button></div></div>
    <div class="tools"><label class="search">${icon('search')}<input id="search" type="search" placeholder="搜索番号、片名、演员或标签…" value="${esc(state.search)}" aria-label="搜索影片"><kbd>/</kbd></label><label class="sort-label">排序<select id="sort"><option value="added">最近添加</option><option value="date">发行日期</option><option value="title">番号顺序</option><option value="score">元数据评分</option><option value="random">随机发现</option></select></label></div>${facet ? `<a href="#${state.view}" class="clear-filter">${icon('close')} 清除筛选：${esc(facet)}</a>` : ''}</section>
    <div id="results"></div>`;
  $('#sort').value = state.sort;
  $('#sort').onchange = e => { state.sort = e.target.value; state.page = 1; renderResults(); };
  $('#search').oninput = e => { state.search = e.target.value; state.page = 1; renderResults(); };
  renderResults();
}
function renderResults() {
  const movies = filtered(), pageCount = Math.ceil(movies.length / 60), visible = movies.slice((state.page - 1) * 60, state.page * 60);
  $('#results').innerHTML = `<div class="results-label"><span>${movies.length} 部影片${state.search ? ` · 搜索“${esc(state.search)}”` : ''}</span><span>本地视频 · STRM</span></div>` + (visible.length ?
    `<div class="movie-grid ${state.layout}">${visible.map(card).join('')}</div>${pageCount > 1 ? `<div class="pagination"><button class="button" data-action="page" data-value="-1" ${state.page===1?'disabled':''}>上一页</button><span>${state.page} / ${pageCount}</span><button class="button" data-action="page" data-value="1" ${state.page===pageCount?'disabled':''}>下一页</button></div>` : ''}` :
    `<section class="empty-state"><div class="empty-icon">${icon('film')}</div><span class="eyebrow">${state.movies.length ? 'A LITTLE MORE DISCOVERY' : 'YOUR COLLECTION STARTS HERE'}</span><h2>${state.movies.length ? '暂时没有匹配的影片' : '为你的收藏，留一个位置。'}</h2><p>${state.movies.length ? '试试其他关键词，或切换上方的筛选条件。' : '在设置中添加视频、STRM、NFO 和图片所在目录，<br>扫描后，影片会在这里有序呈现。'}</p><button class="button primary" data-action="${state.movies.length ? 'reset' : 'go-settings'}">${state.movies.length ? '清除搜索和筛选' : '配置我的媒体库'} ${icon('arrow')}</button><div class="empty-steps"><span>01 <b>添加目录</b></span><span>02 <b>扫描元数据</b></span><span>03 <b>外部播放器打开</b></span></div></section>`);
  bindActions($('#results'));
  $('#results').querySelectorAll('img').forEach(img => img.onerror = () => { img.hidden = true; });
}
function card(m) {
  return `<article class="movie-card"><div class="poster-wrap"><button class="poster-open" data-action="detail" data-id="${m.id}" aria-label="查看 ${esc(m.code || m.title)}"><span class="poster-placeholder"><span>${icon('film')}</span><b>${esc(m.code || 'NFO')}</b><small>LOCAL COLLECTION</small></span>${m[state.layout] ? `<img src="${esc(m[state.layout])}" alt="${esc(m.title)}" loading="lazy">` : ''}<span class="poster-play">${icon('play')} 查看影片</span></button><span class="format-badge">${m.resources.length>1?m.resources.length+' 个版本':esc(m.resources[0]?.format || 'VIDEO')}</span><button class="favorite-button ${m.favorite?'is-favorite':''}" data-action="favorite" data-id="${m.id}" aria-label="${m.favorite?'取消收藏':'收藏'} ${esc(m.code)}" aria-pressed="${m.favorite}">${icon('heart')}</button>${m.watched?`<span class="watched-badge">${icon('check')}</span>`:''}${!m.available?'<span class="missing-badge">资源不可用</span>':''}</div><div class="card-meta"><button class="code-button" data-action="detail" data-id="${m.id}">${esc(m.code || '未识别番号')}</button>${m.score?`<span class="score">★ ${Number(m.score).toFixed(1)}</span>`:''}</div><button class="movie-title" data-action="detail" data-id="${m.id}" title="${esc(m.title)}">${esc(m.title)}</button><div class="card-subtitle">${esc(m.actors.slice(0,2).map(a=>a.name).join(' / ') || m.studio || '暂无演员资料')}<span>${esc((m.date || m.year || '').slice(0,4))}</span></div></article>`;
}
function facetLink(type, name, content, cls = 'chip') { return `<a class="${cls}" href="#${type === 'actor'?'actors':'tags'}/${type}/${encodeURIComponent(name)}">${content || esc(name)}</a>`; }
function renderActors() {
  const actors = new Map();
  for (const m of state.movies) for (const a of m.actors) { const entry = actors.get(a.name) || {...a, count:0}; entry.count++; entry.thumb ||= a.thumb; actors.set(a.name, entry); }
  $('#content').innerHTML = heading('PEOPLE IN YOUR COLLECTION', '从演员开始，发现。', `${actors.size} 位演员，串起你的影片收藏。`) + `<div class="actor-grid">${[...actors.values()].sort((a,b)=>b.count-a.count).map(a=>facetLink('actor',a.name,`<span class="avatar">${a.thumb?`<img src="${esc(a.thumb)}" alt="" loading="lazy">`:esc(a.name.slice(0,1))}</span><strong>${esc(a.name)}</strong><small>${a.count} 部影片 ${icon('arrow')}</small>`, 'actor-card')).join('') || '<p class="muted">扫描包含演员资料的 NFO 后，会在这里显示演员。</p>'}</div>`;
}
function renderTags() {
  $('#content').innerHTML = heading('EXPLORE YOUR LIBRARY', '按喜好，慢慢发现。', '通过标签、系列与制作商，找到下一部想看的影片。') + ['tag','series','studio'].map(type=>{
    const counts = new Map();
    for (const m of state.movies) for (const value of type==='tag'?m.tags:[m[type]]) if(value) counts.set(value, (counts.get(value)||0)+1);
    return `<section class="facet-section"><h2>${({tag:'内容标签',series:'影片系列',studio:'制作商'})[type]}<span>${counts.size}</span></h2><div class="facet-grid">${[...counts].sort((a,b)=>b[1]-a[1]).map(([name,count])=>facetLink(type,name,`<span>${esc(name)}</span><b>${count}</b>`, 'facet-tile')).join('') || '<p class="muted">暂无元数据</p>'}</div></section>`;
  }).join('');
}
async function openDetail(id) {
  const m = state.movies.find(m => m.id === id); if (!m) return;
  dialogMovie = id;
  $('#detail').innerHTML = `<div class="detail-backdrop">${m.cover?`<img src="${esc(m.cover)}" alt="">`:''}<div></div><button class="round-button detail-close" data-action="close" aria-label="关闭详情">${icon('close')}</button></div><div class="detail-body"><div class="detail-heading"><div><span class="eyebrow">${esc(m.code || 'LOCAL COLLECTION')}</span><h2>${esc(m.title)}</h2><div class="detail-specs">${[m.date||m.year,m.runtime?m.runtime+' 分钟':'',m.score?'★ '+m.score:'',m.resources.length+' 个资源'].filter(Boolean).map(v=>`<span>${esc(v)}</span>`).join('')}</div></div><button class="round-button ${m.favorite?'is-favorite':''}" data-action="favorite" data-id="${m.id}" aria-label="切换收藏" aria-pressed="${m.favorite}">${icon('heart')}</button></div><p class="plot">${esc(m.plot || '这部影片还没有简介。你可以在原 NFO 中补充资料，再重新扫描。')}</p><div class="detail-info">${m.studio?`<span>制作商 ${facetLink('studio',m.studio)}</span>`:''}${m.series?`<span>系列 ${facetLink('series',m.series)}</span>`:''}${m.director?`<span>导演 <strong>${esc(m.director)}</strong></span>`:''}</div><div class="chips">${m.tags.map(t=>facetLink('tag',t)).join('')}</div><div class="detail-actions"><button class="button primary" data-action="prepare" data-id="${m.id}" ${!m.available?'disabled':''}>${icon('play')} 选择播放器</button><button class="button" data-action="watched" data-id="${m.id}">${icon('check')} ${m.watched?'已看过 · 取消标记':'标记为已看'}</button><label class="personal-rating">我的评分 <select id="rating" aria-label="个人评分">${[0,1,2,3,4,5].map(n=>`<option value="${n}" ${m.rating===n?'selected':''}>${n?'★'.repeat(n):'未评分'}</option>`).join('')}</select></label></div><div id="play-panel" class="play-panel" hidden></div><section class="detail-section"><h3>播放资源 <span>${m.resources.length}</span></h3>${m.resources.map((r,i)=>`<label class="resource-row"><input name="resource" type="radio" value="${r.id}" ${!r.available?'disabled':''} ${r.available&&!m.resources.slice(0,i).some(v=>v.available)?'checked':''}><span>${esc(r.name)}<small>${esc(r.root)}</small></span><span class="resource-status ${r.available?'':'unavailable'}">${r.available?'可用':'缺失'}</span></label>`).join('')}<small class="muted">外部播放器无法向网页回传进度；观看状态请手动标记。</small></section>${m.actors.length?`<section class="detail-section"><h3>出演演员</h3><div class="actor-chips">${m.actors.map(a=>facetLink('actor',a.name,`<span class="mini-avatar">${a.thumb?`<img src="${esc(a.thumb)}" alt="" loading="lazy">`:esc(a.name.slice(0,1))}</span>${esc(a.name)}`, 'actor-chip')).join('')}</div></section>`:''}${m.samples.length?`<section class="detail-section"><h3>剧照 <span>${m.samples.length}</span></h3><div class="samples">${m.samples.map((s,i)=>`<a href="${esc(s)}" target="_blank" rel="noopener"><img src="${esc(s)}" loading="lazy" alt="剧照 ${i+1}"></a>`).join('')}</div></section>`:''}</div>`;
  $('#rating').onchange = async e => { try { await updateState(id, {rating:Number(e.target.value)}); toast('评分已保存'); } catch(error) { toast(error.message); } };
  bindActions($('#detail')); if (!$('#detail').open) $('#detail').showModal();
}
async function updateState(id, values) {
  const updated = await api(`/api/movies/${id}/state`, values);
  state.movies = state.movies.map(m=>m.id===id?updated:m); return updated;
}
function renderSettings() {
  const s = state.settings;
  $('#content').innerHTML = heading('MAKE IT YOURS', '让影库，按你的方式运行。', '管理媒体来源、扫描任务与播放连接。') + `<div class="settings-grid"><form id="settings-form" class="settings-card"><h2>${icon('play')} 播放连接</h2><p class="muted">本地视频由 QMaxHub 提供原文件播放；STRM 按下方方式连接。请填写播放器设备能访问的服务地址。</p><label>播放方式<select name="playback_mode"><option value="proxy" ${s.playback_mode==='proxy'?'selected':''}>302 反代入口</option><option value="direct" ${s.playback_mode==='direct'?'selected':''}>直连（本地视频 / STRM 302 跳转）</option></select></label><label>QMaxHub 访问地址<input name="public_url" type="url" value="${esc(s.public_url)}" required placeholder="http://192.168.1.10:8096"></label><label>反代播放入口<input name="proxy_url" type="url" value="${esc(s.proxy_url)}" placeholder="https://proxy.example:10443/media"><small>填写客户端可访问的完整地址，端口和路径前缀按实际部署配置。</small></label><label>自动扫描间隔（秒）<input name="scan_interval" type="number" min="0" max="604800" value="${s.scan_interval}" required><small>默认 1800 秒；设为 0 关闭定时扫描。启动时始终扫描一次。</small></label><details><summary>STRM 地址替换（可选）</summary><p class="muted">STRM 内使用 127.0.0.1 或容器内部地址时，可替换成播放器可访问的地址。只替换完整地址前缀，保留路径、参数与签名。</p><label>原地址前缀<input name="rewrite_from" type="url" value="${esc(s.rewrite_from)}" placeholder="http://internal-service:8080"></label><label>替换为<input name="rewrite_to" type="url" value="${esc(s.rewrite_to)}" placeholder="https://stream.example"></label></details><button class="button primary" type="submit">保存设置 ${icon('check')}</button></form>
    <div><section class="settings-card"><h2>${icon('film')} 媒体来源</h2><p class="muted">添加运行 QMaxHub 的电脑上可读取的文件夹。只读取来源文件，设置会保留到下次启动。</p><form id="roots-form"><label>来源目录（每行一个）<textarea name="roots" rows="5" spellcheck="false" placeholder="F:/Media&#10;D:/Movies">${esc(s.roots.join('\n'))}</textarea><small>填写完整路径，例如 F:/Media。支持多个目录；删去一行即可移除该来源，收藏记录仍保留。容器部署时填写容器内的挂载路径。</small></label><p id="roots-error" class="error" role="alert"></p><button class="button primary" type="submit">${icon('check')} 保存来源并扫描</button></form><p class="muted">支持 MP4、MKV、AVI、MOV、WMV、FLV、WebM、M4V、TS、M2TS、MTS、MPG、MPEG、VOB、3GP、OGV 和 STRM。可读取同名 NFO、movie.nfo 及本地图片；无 NFO 时显示文件名。</p><button class="button" data-action="scan">${icon('scan')} 立即扫描</button><div id="scan-status"></div></section>
    <section class="settings-card"><h2>反代工具对接</h2><p class="muted">可接入支持 Emby 兼容接口的播放反代工具。若 STRM 本身已是其他工具提供的播放地址，也可使用 STRM 地址直连。</p><ol class="connect-steps"><li>将反代工具的上游设置为 QMaxHub 的可达地址，例如 <code>${esc(s.public_url)}</code>。</li><li>按工具要求填写下面的 API Key，用于读取媒体源和播放信息。</li><li>把工具对外提供的播放地址填入左侧「反代播放入口」。主机、端口和路径前缀均由你的部署决定。</li></ol><div class="key-row"><input id="api-key" type="password" readonly value="${esc(s.api_key)}" aria-label="媒体服务 API Key"><button type="button" class="button" data-action="copy-key">复制</button></div><small class="muted">API Key 供兼容的反代工具读取播放信息，请妥善保存。使用详情页的播放器按钮即可播放。</small></section></div></div>`;
  $('#content').insertAdjacentHTML('beforeend', `<button class="button" data-action="logout">${icon('exit')} 退出登录</button>`);
  $('#roots-form').onsubmit = async event => {
    event.preventDefault();
    const button = $('button[type=submit]', event.target), errorLabel = $('#roots-error');
    button.disabled = true; errorLabel.textContent = '';
    try {
      const roots = new FormData(event.target).get('roots').split(/\r?\n/).map(r=>r.trim()).filter(Boolean);
      state.settings = await api('/api/settings', {roots});
      $('textarea', event.target).value = state.settings.roots.join('\n');
      state.scan = await api('/api/scan', {});
      state.movies = (await api('/api/movies')).items;
      updateScan(); poll(); toast('媒体来源已保存，已开始扫描');
    } catch(error) { errorLabel.textContent = error.message; toast(error.message); }
    finally { button.disabled = state.scan.running; }
  };
  $('#settings-form').onsubmit = async event => {
    event.preventDefault(); const button = $('button[type=submit]',event.target); button.disabled = true;
    try { const values = Object.fromEntries(new FormData(event.target)); values.scan_interval = Number(values.scan_interval); state.settings = await api('/api/settings', values); toast('设置已保存'); }
    catch(error) { toast(error.message); } finally { button.disabled = false; }
  };
}
function updateScan() {
  const scan = state.scan, text = $('#scan-button-text');
  const total = $('.nav-link[href="#library"] b');
  if (total) total.textContent = state.movies.length;
  const rootsInput = $('#roots-form textarea');
  if (rootsInput) rootsInput.disabled = scan.running;
  if (text) text.textContent = scan.running ? `扫描中 · ${scan.processed}` : '扫描媒体库';
  document.querySelectorAll('[data-action="scan"], #roots-form button[type=submit]').forEach(b => b.disabled = scan.running);
  const area = $('#scan-status');
  if (area) area.innerHTML = `<p class="scan-summary">${scan.running ? '正在扫描' : scan.finished ? '最近完成扫描' : '等待首次扫描'} · ${scan.processed} 个媒体文件${scan.finished?' · '+new Date(scan.finished*1000).toLocaleString('zh-CN'):''}</p>${scan.errors.length?`<details class="scan-errors"><summary>${scan.errors.length} 项异常（最多显示 200 项）</summary>${scan.errors.map(e=>`<p><code>${esc(e.path)}</code><br>${esc(e.message)}</p>`).join('')}</details>`:''}`;
}
async function poll() {
  clearTimeout(pollTimer);
  try {
    const previous = state.scan; state.scan = await api('/api/scan'); updateScan();
    if (!state.scan.running && (previous.running || state.scan.finished !== previous.finished)) { const data = await api('/api/movies'); state.movies = data.items; render(); toast(`扫描完成 · ${state.scan.processed} 个媒体文件${state.scan.errors.length?'，有异常，请在设置中查看':''}`); }
    pollTimer = setTimeout(poll, state.scan.running ? 1500 : 10000);
  } catch(error) { if($('#content')) { toast(error.message); pollTimer = setTimeout(poll,10000); } }
}
async function copy(value) {
  if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(value);
  else { const el = document.createElement('textarea'); el.value = value; document.body.append(el); el.select(); const ok = document.execCommand('copy'); el.remove(); if(!ok) throw new Error('浏览器不支持自动复制，请长按播放链接手动复制'); }
  toast('已复制');
}
const actions = {
  logout: async () => { await api('/api/logout',{}); clearTimeout(pollTimer); login(); },
  scan: async () => {
    state.scan = await api('/api/scan',{});
    if (!state.scan.running) { state.movies = (await api('/api/movies')).items; if (state.view !== 'settings') render(); }
    updateScan(); poll();
  },
  filter: el => { state.filter=el.dataset.value; state.page=1; render(); },
  layout: el => { state.layout=el.dataset.value; localStorage.setItem('layout',state.layout); render(); },
  page: el => { state.page+=Number(el.dataset.value); renderResults(); window.scrollTo({top:0,behavior:'smooth'}); },
  reset: () => { state.search=''; state.filter=''; state.facet=''; state.facetValue=''; location.hash=state.view; render(); },
  'go-settings': () => { location.hash='settings'; },
  detail: el => openDetail(el.dataset.id),
  close: () => $('#detail').close(),
  favorite: async el => {
    const m=state.movies.find(m=>m.id===el.dataset.id); await updateState(m.id,{favorite:!m.favorite});
    const open=$('#detail').open; render(); if(open) await openDetail(m.id);
  },
  watched: async el => { const m=state.movies.find(m=>m.id===el.dataset.id); await updateState(m.id,{watched:!m.watched}); render(); await openDetail(m.id); },
  'copy-key': () => copy(state.settings.api_key),
  prepare: async el => {
    const version=++requestVersion, id=el.dataset.id, resource=$('input[name=resource]:checked', $('#detail'))?.value;
    if(!resource) throw new Error('请选择可用的播放资源');
    el.disabled=true;
    try {
      const links=await api(`/api/movies/${id}/play`,{resource_id:resource});
      if(version!==requestVersion || dialogMovie!==id || !$('#detail').open) return;
      const panel=$('#play-panel'); panel.hidden=false;
      panel.innerHTML=`<strong>选择此设备上的播放器</strong><div class="player-links"><a class="button primary" href="${esc(links.potplayer)}">PotPlayer <small>Windows</small></a><a class="button primary" href="${esc(links.mpv)}">mpv <small>Android</small></a><button class="button" id="copy-play">复制播放链接</button><button class="button" id="playlist">下载 M3U</button></div><p>点击后由浏览器请求打开播放器。PotPlayer 需要注册 potplayer:// 协议，Android 需要安装 mpv。链接有效期 12 小时。</p><p>地址：<code>${esc(new URL(links.url).origin)}</code> · ${links.kind==='local'?'本地视频原文件播放':state.settings.playback_mode==='proxy'?'通过 302 反代入口':'直接跳转 STRM'}</p>`;
      $('#copy-play').onclick=()=>copy(links.url).catch(e=>toast(e.message));
      $('#playlist').onclick=()=>{ const blob=new Blob(['#EXTM3U\n'+links.url+'\n'],{type:'audio/x-mpegurl'}), url=URL.createObjectURL(blob), a=document.createElement('a'); a.href=url; a.download='qmaxhub.m3u'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000); };
      panel.scrollIntoView({behavior:'smooth',block:'nearest'});
    } finally { el.disabled=false; }
  },
};
window.addEventListener('hashchange',route);
$('#detail').addEventListener('close',()=>{requestVersion++; dialogMovie=null;});
$('#detail').addEventListener('click',event=>{if(event.target===$('#detail')) $('#detail').close();});
document.addEventListener('keydown',event=>{if(event.key==='/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) && !$('#detail').open && $('#search')) {event.preventDefault();$('#search').focus();}});
(async()=>{ try { const session=await api('/api/session'); if(session.authenticated) await load(); else login(); } catch(error) { login(); toast(error.message); } })();
