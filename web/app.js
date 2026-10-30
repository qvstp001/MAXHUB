'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const icons = {
  left: '<path d="M19 12H5m6-6-6 6 6 6"/>',
  external: '<path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
  studio: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9 7h1m4 0h1M9 11h1m4 0h1m-5 5h4v5"/>',

  chevron: '<path d="m9 5 7 7-7 7"/>',
  panel: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
  moon: '<path d="M20.8 13.2A9 9 0 0 1 10.8 3.2 9 9 0 1 0 20.8 13.2Z"/>',
  density: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',

  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  folder: '<path d="M3 7V4h6l3 3h9v13H3Z"/>',
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
const state = {...MaxhubBrowse.defaults(),movies:[],stats:{total:0,actors:0},settings:{},scan:{errors:[]},layout:localStorage.getItem('maxhub.layout')||'cover',density:localStorage.getItem('maxhub.density')||'normal',sidebarOpen:innerWidth>760&&localStorage.getItem('maxhub.sidebar')!=='closed',field:'studio',facetPage:1,facetSearch:''};
let entityPending=false,entityController,pollTimer,browseVersion=0,queryVersion=0,searchTimer,movieController,currentAddress='',pendingScroll=null,scrollTimer;
const positions=new Map();
const folderBrowser=new FolderBrowser({api,esc,icon,href:(root,path)=>folderLink(root,path),onRecursive:recursive=>changeBrowse({recursive})});
const filterPicker=new FilterPicker({api,esc,icon,toast,apply:changes=>changeBrowse(changes)});
const movieDetail=new MovieDetail({api,esc,icon,toast,copy,profileHref:MaxhubBrowse.profile,filterHref:(kind,name)=>filterHref(kind,name),folderHref:r=>MaxhubBrowse.href({...MaxhubBrowse.defaults(),view:'folders',root:r.root,folder:r.folder})});
const controlsObserver=new ResizeObserver(entries=>{for(const entry of entries)document.documentElement.style.setProperty('--folder-tree-top',(entry.borderBoxSize?.[0]?.blockSize||entry.target.offsetHeight)+88+'px');});
async function api(path, body, signal) {
  const response = await fetch(path, {signal, credentials: 'same-origin', ...(body !== undefined ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {})});
  const result = await response.json();
  if (!response.ok) {
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
function nav(view, label, glyph, extra = '') { return `<a href="#${view}" title="${label}" class="nav-link ${state.view === view ? 'active' : ''}">${icon(glyph)}<span>${label}</span>${extra}</a>`; }
function shell() {
  $('#app').classList.toggle('nav-open',state.sidebarOpen);
  document.body.dataset.density=state.density;
  $('#app').innerHTML=`<button class="nav-scrim" data-action="nav-toggle" aria-label="关闭导航"></button><aside class="sidebar" aria-label="媒体库导航">
    <div class="sidebar-head"><a class="brand" href="#library" title="MAXHUB"><span class="brand-mark">${icon('film')}</span><span class="brand-name">MAXHUB</span></a><button class="icon-button" data-action="nav-toggle" aria-label="展开或收起导航" aria-expanded="${state.sidebarOpen}">${icon('panel')}</button></div>
    <nav aria-label="主导航">${nav('library','媒体库','grid',`<b id="library-count">${state.stats.total}</b>`)}${nav('actors','演员','people')}${nav('folders','文件夹','folder')}${nav('fields','厂商与标签','tag')}</nav>
    <div class="sidebar-note"><span>本地馆藏</span><p>STRM 与已刮削资料</p><a href="#folders">${icon('folder')} 浏览媒体来源</a></div>
    <div class="sidebar-bottom">${nav('settings','设置','settings')}<div class="sidebar-foot"><span>MAXHUB <small>${esc(state.settings.version)} · <a href="https://github.com/qvstp001/MAXHUB" target="_blank" rel="noopener">源码</a></small></span><button class="icon-button theme-button" data-action="theme" aria-label="切换明暗主题"><span class="theme-sun">${icon('sun')}</span><span class="theme-moon">${icon('moon')}</span></button></div></div></aside>
    <div class="workspace"><header class="topbar"><button class="icon-button mobile-menu" data-action="nav-toggle" aria-label="打开导航" aria-expanded="${state.sidebarOpen}">${icon('panel')}</button><strong id="crumb"></strong><label class="search global-search">${icon('search')}<input id="search" type="search" placeholder="搜索馆藏" aria-label="搜索影片" autocomplete="off"><kbd>/</kbd></label><div class="top-actions"><button class="icon-button" data-action="scan" title="扫描媒体库" aria-label="扫描媒体库">${icon('scan')}</button><button class="icon-button density-button" data-action="density" aria-label="切换卡片密度" title="切换卡片密度">${icon('density')}</button><a class="icon-button" href="#settings" aria-label="打开设置" title="设置">${icon('settings')}</a><button class="icon-button theme-button" data-action="theme" aria-label="切换明暗主题"><span class="theme-sun">${icon('sun')}</span><span class="theme-moon">${icon('moon')}</span></button></div></header><main id="content"></main></div>`;
  const search=()=>{
    queryVersion++;movieController?.abort();clearTimeout(searchTimer);
    searchTimer=setTimeout(()=>changeBrowse({search:$('#search').value,view:isBrowseView()?state.view:'library'}),220);
  };
  $('#search').oninput=e=>{if(!e.isComposing)search();};$('#search').oncompositionend=search;
  bindActions();
}
async function load() {
  state.settings = await api('/api/settings');
  shell(); route(); poll(); refreshStats();
}
async function refreshStats() {
  try {
    state.stats = await api('/api/stats');
    const count=$('#library-count'); if(count) count.textContent=state.stats.total;
    const stats=$('#collection-stats'); if(stats) stats.innerHTML=statsMarkup();
  } catch(error) { if($('#content')) toast(error.message); }
}
function rememberScroll() {
  if(!currentAddress||pendingScroll!==null)return;
  positions.set(currentAddress,scrollY);if(positions.size>40)positions.delete(positions.keys().next().value);
  history.replaceState({scrollY},'',location.href);
}
function navigate(hash) {
  const address=MaxhubBrowse.href(MaxhubBrowse.parse(hash));
  if(address===currentAddress){if($('#results'))renderResults();return;}
  rememberScroll();history.pushState({scrollY:positions.get(address)||0},'',address);route();
}
function isBrowseView(){return ['library','folders'].includes(state.view)||!!MaxhubBrowse.entity(state);}
function changeBrowse(changes) {
  const next={...state,view:isBrowseView()?state.view:'library',search:$('#search').value,page:1,...changes};
  if(MaxhubBrowse.entity(state)&&['actors','fields'].includes(next.view)&&!MaxhubBrowse.entity(next))next.view='library';
  navigate(MaxhubBrowse.href(next));
}
function restoreScroll() {
  if(pendingScroll===null||entityPending||$('#results')?.getAttribute('aria-busy')==='true')return;
  const address=currentAddress,y=pendingScroll;
  requestAnimationFrame(()=>{if(address!==currentAddress)return;window.scrollTo(0,y);pendingScroll=null;});
}
function route() {
  const parsed=MaxhubBrowse.parse(location.hash),address=MaxhubBrowse.href(parsed);
  if(address===currentAddress)return;
  movieController?.abort();clearTimeout(searchTimer);queryVersion++;browseVersion++;
  if(location.hash!==address)history.replaceState(history.state,'',address);
  currentAddress=address;pendingScroll=positions.get(address)??history.state?.scrollY??0;
  Object.assign(state,parsed,{facetPage:1,facetSearch:''});
  if($('#search').value!==state.search)$('#search').value=state.search;
  document.querySelectorAll('.nav-link').forEach(a=>a.classList.toggle('active',a.getAttribute('href')==='#'+state.view));
  if(innerWidth<=760){state.sidebarOpen=false;$('#app').classList.remove('nav-open');}
  movieDetail.close();render();
}
function heading(kicker,title,description,trailing='') { return `<section class="page-heading"><div><h1>${title}</h1><p>${description}</p></div>${trailing}</section>`; }
function render() {
  if(!$('#content')) return;
  browseVersion++;movieController?.abort();queryVersion++;filterPicker.dispose();folderBrowser.detach();controlsObserver.disconnect();entityController?.abort();entityPending=false;
  $('#crumb').textContent=({library:'媒体库',actors:'演员',folders:'文件夹',fields:'厂商与标签',settings:'设置'})[state.view];
  if(state.view==='settings') renderSettings();
  else if(['actors','fields'].includes(state.view)&&!MaxhubBrowse.entity(state))renderFacets();
  else renderLibrary();
  bindActions($('#content'));updateScan();if(state.view==='settings')restoreScroll();
}
function statsMarkup(){return `${state.total==null?'…':state.total.toLocaleString()} 部影片 <span>· 全库 ${state.stats.total.toLocaleString()} 部</span>`;}
function folderSelection(){return {root:state.root,path:state.folder,recursive:state.recursive};}
function folderLink(root,path){return MaxhubBrowse.href({...state,view:'folders',root,folder:path,page:1});}
function comboMarkup() {
  const filters=[];
  for(const [kind,label] of [['actor','演员'],['studio','厂商'],['series','系列']])if(state[kind])filters.push([kind,state[kind],label+'：'+state[kind]]);
  for(const tag of state.tags)filters.push(['tag',tag,'标签：'+tag]);
  if(state.root)filters.push(['folder','','目录：'+(state.folder||state.root)]);
  if(state.search)filters.push(['search','','搜索：'+state.search]);
  if(state.filter)filters.push(['filter','',({missing:'资源缺失',watched:'已经看过',unwatched:'尚未观看'})[state.filter]]);
  return filters.length?`<div class="combo-row" aria-label="生效的筛选条件"><span class="combo-label">同时满足</span>${filters.map(([kind,value,label])=>`<span class="combo-chip"><span>${esc(label)}</span><button data-action="remove-filter" data-kind="${kind}" data-value="${esc(value)}" aria-label="移除${esc(label)}">${icon('close')}</button></span>`).join('')}<button class="combo-clear" data-action="reset">全部清除</button></div>`:'';
}
function renderLibrary() {
  const folders=state.view==='folders';
  state.total=null;
  $('#content').innerHTML=`${MaxhubBrowse.entity(state)?'<div id="entity-header" class="entity-header"></div>':'<div id="highlights"></div>'}${comboMarkup()}<section class="library-controls"><div class="filter-row"><div class="tabs"><button class="tab ${!state.filter?'selected':''}" data-action="filter" data-value="">全部影片</button><button class="tab ${state.filter==='missing'?'selected':''}" data-action="filter" data-value="missing">资源缺失</button></div><div id="filter-pickers"></div><a href="${esc(MaxhubBrowse.href({...state,view:folders?'library':'folders',page:1}))}" class="filter-chip ${folders?'is-selected':''}" aria-label="${folders?'关闭':'打开'}目录树">${icon('folder')} 文件夹</a></div>
    <div class="control-row"><span id="collection-stats">${statsMarkup()}</span><div class="control-options"><div class="layout-toggle" aria-label="封面比例"><button class="${state.layout==='cover'?'selected':''}" data-action="layout" data-value="cover" aria-pressed="${state.layout==='cover'}">横幅</button><button class="${state.layout==='poster'?'selected':''}" data-action="layout" data-value="poster" aria-pressed="${state.layout==='poster'}">海报</button></div><label class="sort-label"><span class="sr-only">排序</span><select id="sort" aria-label="影片排序"><option value="added">最近添加</option><option value="date">发行日期</option><option value="title">番号顺序</option><option value="score">元数据评分</option></select></label></div></div></section>
    ${folders?'<div class="folder-browse"><aside id="folder-tree" class="folder-tree-panel"></aside><section class="folder-results"><div id="folder-header" class="folder-header"></div><div id="results" aria-live="polite"></div></section></div>':'<div id="results" aria-live="polite"></div>'}`;
  $('#sort').value=state.sort;$('#sort').onchange=e=>changeBrowse({sort:e.target.value});
  filterPicker.mount($('#filter-pickers'),state);controlsObserver.observe($('.library-controls'));
  if(MaxhubBrowse.entity(state))renderEntity();
  renderResults();if(folders)folderBrowser.mount($('#folder-tree'),$('#folder-header'),folderSelection());else if(!MaxhubBrowse.entity(state))renderHighlights();
}
async function renderHighlights() {
  const version=browseVersion, target=$('#highlights');
  try {
    const [actors,studios]=await Promise.all([api('/api/facets?kind=actor&limit=10'),api('/api/facets?kind=studio&limit=6')]);
    if(version!==browseVersion || !target?.isConnected)return;
    if(!actors.total&&!studios.total)return;
    target.innerHTML=`<section class="catalog-tiers" aria-label="快速浏览"><div class="performer-row">${actors.items.map(a=>facetLink('actor',a.name,`<span class="performer-avatar">${a.thumb?`<img src="${esc(a.thumb)}" alt="" loading="lazy" decoding="async">`:esc(a.name.slice(0,1))}</span><span>${esc(a.name)}</span>`,'performer')).join('')}<a class="performer performer-all" href="#actors"><span class="performer-avatar">${icon('arrow')}</span><span>全部演员</span></a></div>${studios.total?`<div class="studio-row">${studios.items.map(a=>facetLink('studio',a.name,`<span class="studio-mark">${esc(a.name.slice(0,1))}</span><span>${esc(a.name)}</span>`,'studio-shortcut')).join('')}</div>`:''}</section>`;
  } catch(error){if(version===browseVersion)target.innerHTML='<p class="muted">快捷分类暂不可用</p>';}
}
async function renderResults() {
  const version=++queryVersion, viewVersion=browseVersion, target=$('#results'); if(!target) return;
  movieController?.abort(); movieController=new AbortController();
  target.setAttribute('aria-busy','true');
  target.innerHTML='<p class="muted">正在读取影片…</p>';
  const selected=folderSelection(), params=new URLSearchParams({page:state.page,limit:60,search:state.search,sort:state.sort,status:state.filter});
  for(const kind of ['actor','studio','series'])if(state[kind])params.set(kind,state[kind]);
  for(const tag of state.tags)params.append('tag',tag);
  if(selected.root){params.set('root',selected.root);params.set('folder',selected.path);params.set('recursive',selected.recursive?'1':'0');}
  try {
    const data=await api('/api/movies?'+params,undefined,movieController.signal);
    if(version!==queryVersion || viewVersion!==browseVersion) return;
    state.movies=data.items;state.total=data.total;state.page=data.page;$('#collection-stats').innerHTML=statsMarkup();
    const address=MaxhubBrowse.href(state);if(address!==currentAddress){currentAddress=address;history.replaceState(history.state,'',address);}
    const pageCount=Math.ceil(data.total/data.limit);
    target.innerHTML=`<div class="results-label"><span>${data.total.toLocaleString()} 部影片${state.search?` · 搜索“${esc(state.search)}”`:''}</span><span>本地元数据 · STRM</span></div>`+(data.items.length?
      `<div class="movie-grid ${state.layout}">${data.items.map(card).join('')}</div>${pagination(state.page,pageCount,'page')}`:
      `<section class="empty-state"><div class="empty-icon">${icon('film')}</div><h2>${state.stats.total?'暂时没有匹配的影片':'为你的收藏，留一个位置。'}</h2><p>${state.stats.total?'试试其他关键词，或切换筛选条件。':'挂载存放 STRM、NFO 和图片的目录，扫描后即可浏览。'}</p><button class="button primary" data-action="${state.stats.total?'reset':'go-settings'}">${state.stats.total?'清除搜索和筛选':'配置我的媒体库'} ${icon('arrow')}</button></section>`);
    bindActions(target);restoreScroll();target.querySelectorAll('img').forEach(img=>img.onerror=()=>{img.hidden=true;});
  } catch(error) {
    if(error.name==='AbortError' || version!==queryVersion || viewVersion!==browseVersion) return;
    target.innerHTML='<p class="error" role="alert">'+esc(error.message)+'</p><button class="button" data-action="retry">重试</button>';bindActions(target);
  } finally {if(version===queryVersion){target.removeAttribute('aria-busy');restoreScroll();}}
}
function pagination(page,pages,action) {
  return pages>1?`<div class="pagination"><button class="button" data-action="${action}" data-value="-1" ${page<=1?'disabled':''}>上一页</button><span>${page} / ${pages}</span><button class="button" data-action="${action}" data-value="1" ${page>=pages?'disabled':''}>下一页</button></div>`:'';
}
function card(m) {
  const actor=m.actors[0], names=m.actors.slice(0,2).map(a=>facetLink('actor',a.name,esc(a.name),'byline-person')).join(' / ');
  return `<article class="movie-card"><div class="poster-wrap"><button class="poster-open" data-action="detail" data-id="${m.id}" aria-label="查看 ${esc(m.code||m.title)}"><span class="poster-placeholder">${icon('film')}<b>${esc(m.code||'暂无封面')}</b></span>${m[state.layout]?`<img src="${esc(m[state.layout])}" alt="${esc(m.title)}" loading="lazy" decoding="async">`:''}<span class="poster-play">${icon('play')}</span></button><span class="format-badge">${m.resource_count>1?m.resource_count+' 个版本':'STRM'}</span>${m.score?`<span class="score-badge">★ ${Number(m.score).toFixed(1)}</span>`:''}${!m.available?'<span class="missing-badge">资源不可用</span>':''}</div>
    <button class="movie-title" data-action="detail" data-id="${m.id}" title="${esc(m.title)}">${m.code?`<span class="card-code">${esc(m.code)}</span> `:''}${esc(m.title)}</button><div class="card-byline"><span class="byline-avatar">${actor?esc(actor.name.slice(0,1)):icon('film')}</span><div><span class="byline-name">${actor?names:esc(m.studio||'本地媒体')}</span><div class="card-subtitle">${esc([m.studio,(m.date||m.year||'').slice(0,4)].filter(Boolean).join(' · '))}</div></div></div></article>`;
}
function filterHref(type,name) {
  const changes=type==='tag'?{tags:[...new Set([...state.tags,name])]}:{[type]:name};
  return MaxhubBrowse.href({...state,view:isBrowseView()?state.view:'library',page:1,...changes});
}
function facetLink(type,name,content,cls='chip') {
  const href=['actor','studio'].includes(type)?MaxhubBrowse.profile(type,name):filterHref(type,name);
  return `<a class="${cls}" href="${esc(href)}">${content||esc(name)}</a>`;
}
async function renderEntity() {
  const entity=MaxhubBrowse.entity(state),version=browseVersion,target=$('#entity-header');
  entityPending=true;entityController=new AbortController();
  target.innerHTML='<div class="entity-loading" role="status">正在读取本地资料…</div>';
  try {
    const data=await api('/api/entities?'+new URLSearchParams(entity),undefined,entityController.signal);
    if(version!==browseVersion||!target.isConnected)return;
    const actor=entity.kind==='actor',years=data.first_year?(data.first_year===data.last_year?data.first_year:data.first_year+' 至 '+data.last_year):'未记录';
    const refinements=(kind,items,title)=>items.length?`<div class="entity-refinements"><h3>${title}</h3><div class="entity-related">${items.map(item=>{
      const selected=kind==='tag'?state.tags.includes(item.name):state[kind]===item.name;
      return `<button class="chip entity-refine" data-action="entity-filter" data-kind="${kind}" data-value="${esc(item.name)}" aria-pressed="${selected}">${item.thumb?`<img src="${esc(item.thumb)}" alt="" loading="lazy" decoding="async">`:''}<span>${esc(item.name)}</span><small>${item.count}</small></button>`;
    }).join('')}</div></div>`:'';
    target.innerHTML=`<nav class="entity-breadcrumbs" aria-label="资料页路径"><a href="#${actor?'actors':'fields'}">${actor?'全部演员':'厂商与标签'}</a><span>/</span><span aria-current="page">${esc(data.name)}</span></nav><section class="entity-card" aria-label="${actor?'演员':'厂商'}资料"><div class="entity-identity"><span class="entity-portrait ${actor?'':'company'}"><span>${actor?esc([...data.name][0]):icon('studio')}</span>${data.thumb?`<img src="${esc(data.thumb)}" alt="${esc(data.name)}" decoding="async">`:''}</span><div class="entity-name"><span class="entity-kind">${actor?'演员':'厂商'} · 本地 NFO</span><h1>${esc(data.name)}</h1><p>本地馆藏统计</p></div><dl class="entity-stats"><div><dt>影片</dt><dd>${data.movie_count}</dd></div><div><dt>可播放影片</dt><dd>${data.available_count}</dd></div><div><dt>播放资源</dt><dd>${data.resource_count}</dd></div><div class="entity-years"><dt>发行年份</dt><dd>${esc(years)}</dd></div></dl></div>${data.missing_count?`<div class="entity-missing"><button data-action="entity-missing">${data.missing_count} 部影片资源不可用 ${icon('arrow')}</button></div>`:''}<div class="entity-associations">${actor?refinements('studio',data.related.studios,'按厂商筛选'):refinements('actor',data.related.actors,'按演员筛选')}${refinements('tag',data.related.tags,'常见标签')}</div></section>`;
    bindActions(target);target.querySelectorAll('img').forEach(img=>img.onerror=()=>{img.hidden=true;});
  } catch(error){if(error.name!=='AbortError'&&version===browseVersion&&target.isConnected){target.innerHTML=`<div class="entity-error"><p class="error" role="alert">${esc(error.message)}</p><button class="button" data-action="entity-retry">重试</button><a class="button" href="#${entity.kind==='actor'?'actors':'fields'}">返回索引</a></div>`;bindActions(target);}}
  finally{if(version===browseVersion){entityPending=false;restoreScroll();}}
}
function renderFacets() {
  const actors=state.view==='actors';
  $('#content').innerHTML=heading(actors?'PEOPLE IN YOUR COLLECTION':'EXPLORE YOUR LIBRARY',actors?'演员':'厂商与标签',actors?'从本地 NFO 中读取演员，按作品数量浏览。':'选择厂商或影片标签，查看对应影片。')+
    `<div class="tools"><label class="search">${icon('search')}<input id="facet-search" type="search" placeholder="${actors?'搜索演员':'搜索字段值'}" value="${esc(state.facetSearch)}" aria-label="搜索分类"></label>${actors?'':`<label class="sort-label">字段<select id="field-kind"><option value="studio">厂商</option><option value="tag">影片标签</option></select></label>`}</div><div id="facet-results" aria-live="polite"></div>`;
  if(!actors) {$('#field-kind').value=state.field;$('#field-kind').onchange=e=>{state.field=e.target.value;state.facetPage=1;fetchFacets();};}
  $('#facet-search').oninput=e=>{state.facetSearch=e.target.value;state.facetPage=1;queryVersion++;clearTimeout(searchTimer);searchTimer=setTimeout(fetchFacets,220);};
  fetchFacets();
}
async function fetchFacets() {
  const version=++queryVersion, viewVersion=browseVersion, target=$('#facet-results'), kind=state.view==='actors'?'actor':state.field;
  if(!target) return;
  target.innerHTML='<p class="muted">正在读取分类…</p>';
  try {
    const data=await api('/api/facets?'+new URLSearchParams({kind,page:state.facetPage,limit:100,search:state.facetSearch}));
    if(version!==queryVersion || viewVersion!==browseVersion) return;
    state.facetPage=data.page;
    target.innerHTML=`<div class="results-label"><span>${data.total.toLocaleString()} 项</span></div><div class="${kind==='actor'?'actor-grid':'facet-grid'}">`+data.items.map(a=>kind==='actor'?
      facetLink('actor',a.name,`<span class="avatar">${a.thumb?`<img src="${esc(a.thumb)}" alt="" loading="lazy" decoding="async">`:esc(a.name.slice(0,1))}</span><strong>${esc(a.name)}</strong><small>${a.count} 部影片 ${icon('arrow')}</small>`,'actor-card'):
      facetLink(kind,a.name,`<span>${esc(a.name)}</span><b>${a.count}</b>`,'facet-tile')).join('')+'</div>'+(!data.items.length?'<p class="muted">暂无匹配的分类。</p>':'')+pagination(data.page,Math.ceil(data.total/data.limit),'facet-page');
    bindActions(target);restoreScroll();
  } catch(error) {if(version===queryVersion && viewVersion===browseVersion) {target.innerHTML='<p class="error">'+esc(error.message)+'</p>';}}
}
function openDetail(id){return movieDetail.open(id,state.movies.map(m=>m.id));}
function renderSettings() {
  const s = state.settings;
  $('#content').innerHTML = heading('MAKE IT YOURS', '设置', '管理媒体来源、扫描任务与播放连接。') + `<div class="settings-grid"><form id="settings-form" class="settings-card"><h2>${icon('play')} 播放连接</h2><p class="muted">播放器安装在打开网页的设备上。请使用该设备可访问的局域网或公网地址。</p><label>播放方式<select name="playback_mode"><option value="proxy" ${s.playback_mode==='proxy'?'selected':''}>302 反代入口</option><option value="direct" ${s.playback_mode==='direct'?'selected':''}>STRM 地址直连（302 跳转）</option></select></label><label>MAXHUB 访问地址<input name="public_url" type="url" value="${esc(s.public_url)}" required placeholder="http://192.168.1.10:8096"></label><label>反代播放入口<input name="proxy_url" type="url" value="${esc(s.proxy_url)}" placeholder="https://proxy.example:10443/media"><small>填写客户端可访问的完整地址，端口和路径前缀按实际部署配置。</small></label><label>自动扫描间隔（秒）<input name="scan_interval" type="number" min="0" max="604800" value="${s.scan_interval}" required><small>默认 1800 秒；设为 0 关闭定时扫描。启动时始终扫描一次。</small></label><details><summary>STRM 地址替换（可选）</summary><p class="muted">STRM 内使用 127.0.0.1 或容器内部地址时，可替换成播放器可访问的地址。只替换完整地址前缀，保留路径、参数与签名。</p><label>原地址前缀<input name="rewrite_from" type="url" value="${esc(s.rewrite_from)}" placeholder="http://internal-service:8080"></label><label>替换为<input name="rewrite_to" type="url" value="${esc(s.rewrite_to)}" placeholder="https://stream.example"></label></details><button class="button primary" type="submit">保存设置 ${icon('check')}</button></form>
    <div><section class="settings-card"><h2>${icon('film')} 媒体来源</h2><p class="muted">从部署配置读取。请在 Docker 中将 STRM 和元数据目录挂载为只读。</p>${s.roots.map(r=>`<div class="root-row"><span>${icon('film')}<code>${esc(r)}</code></span><b>只读来源</b></div>`).join('')}<p class="muted">支持同名 NFO、movie.nfo、poster、fanart、.actors 和 extrafanart 等常见目录布局。</p><button class="button" data-action="scan">${icon('scan')} 增量扫描</button> <button class="button" data-action="rescan">重读全部资料</button><div id="scan-status"></div></section>
    <section class="settings-card"><h2>LitePan 对接</h2><p class="muted">在 LitePan 的「增强工具 → Emby 反代」中配置本服务。STRM 需由当前 LitePan 生成，包含可识别的播放地址。</p><ol class="connect-steps"><li>将 LitePan 的 Emby 地址设置为 MAXHUB 的可达地址，例如 <code>${esc(s.public_url)}</code>。</li><li>填写下方 API Key 并测试连接。LitePan 与本服务在同一 Docker 网络时，可用容器名连接上游。</li><li>启用反代，把 LitePan 显示的反代入口填入左侧「反代播放入口」。此地址需能从播放设备访问。</li></ol><div class="key-row"><input id="api-key" type="password" readonly value="${esc(s.api_key)}" aria-label="媒体服务 API Key"><button type="button" class="button" data-action="copy-key">复制</button></div><small class="muted">API Key 供兼容的反代工具读取播放信息，请妥善保存。使用详情页的播放器按钮即可播放。</small></section></div></div>`;
  $('#settings-form').onsubmit = async event => {
    event.preventDefault(); const button = $('button[type=submit]',event.target); button.disabled = true;
    try { const values = Object.fromEntries(new FormData(event.target)); values.scan_interval = Number(values.scan_interval); state.settings = await api('/api/settings', values); toast('设置已保存'); }
    catch(error) { toast(error.message); } finally { button.disabled = false; }
  };
}
function updateScan() {
  const scan = state.scan, text = $('#scan-button-text');
  if (text) text.textContent = scan.running ? `扫描中 · ${scan.processed}` : '扫描媒体库';
  document.querySelectorAll('[data-action="scan"],[data-action="rescan"]').forEach(b => b.disabled = scan.running);
  const area = $('#scan-status');
  if (area) area.innerHTML = `<p class="scan-summary">${scan.running ? '正在扫描' : scan.finished ? '最近完成扫描' : '等待首次扫描'} · ${scan.processed || 0} 个 STRM · 更新 ${scan.updated || 0} / 未变化 ${scan.unchanged || 0}${scan.finished?' · '+new Date(scan.finished*1000).toLocaleString('zh-CN'):''}</p>${scan.errors.length?`<details class="scan-errors"><summary>${scan.errors.length} 项异常（最多显示 200 项）</summary>${scan.errors.map(e=>`<p><code>${esc(e.path)}</code><br>${esc(e.message)}</p>`).join('')}</details>`:''}`;
}
async function poll() {
  clearTimeout(pollTimer);
  try {
    const previous = state.scan; state.scan = await api('/api/scan'); updateScan();
    if (!state.scan.running && (previous.running || state.scan.finished!==previous.finished)) { folderBrowser.invalidate();await refreshStats();render(); if(previous.running) toast(`扫描完成 · ${state.scan.processed} 个 STRM${state.scan.errors.length?'，有异常，请在设置中查看':''}`); }
    pollTimer = setTimeout(poll, state.scan.running ? 1500 : 10000);
  } catch(error) { if($('#content')) { toast(error.message); pollTimer = setTimeout(poll,10000); } }
}
async function copy(value) {
  if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(value);
  else { const el = document.createElement('textarea'); el.value = value; document.body.append(el); el.select(); const ok = document.execCommand('copy'); el.remove(); if(!ok) throw new Error('浏览器不支持自动复制，请长按播放链接手动复制'); }
  toast('已复制');
}
const actions = {
  'nav-toggle': ()=>{state.sidebarOpen=!state.sidebarOpen;$('#app').classList.toggle('nav-open',state.sidebarOpen);if(innerWidth>760)localStorage.setItem('maxhub.sidebar',state.sidebarOpen?'open':'closed');document.querySelectorAll('[data-action="nav-toggle"]').forEach(el=>el.setAttribute('aria-expanded',state.sidebarOpen));},
  theme: ()=>window.setLibraryTheme(document.documentElement.dataset.theme==='dark'?'light':'dark'),
  density: ()=>{state.density=state.density==='dense'?'normal':'dense';document.body.dataset.density=state.density;localStorage.setItem('maxhub.density',state.density);},

  scan: async () => { state.scan = await api('/api/scan',{}); updateScan(); poll(); },
  rescan: async () => { state.scan = await api('/api/scan',{full:true}); updateScan(); poll(); },
  filter:el=>changeBrowse({filter:el.dataset.value}),
  layout: el => { state.layout=el.dataset.value; localStorage.setItem('maxhub.layout',state.layout); render(); },
  retry: () => renderResults(),
  'facet-page': el=>{state.facetPage+=Number(el.dataset.value);fetchFacets();window.scrollTo({top:0,behavior:'smooth'});},
  page:el=>changeBrowse({page:state.page+Number(el.dataset.value)}),
  reset:()=>changeBrowse({...MaxhubBrowse.defaults(),view:state.view==='folders'?'folders':'library'}),
  'remove-filter':el=>{const kind=el.dataset.kind;changeBrowse(kind==='tag'?{tags:state.tags.filter(t=>t!==el.dataset.value)}:kind==='folder'?{root:'',folder:'',recursive:true}:{[kind]:''});},
  'go-settings':()=>navigate('#settings'),
  detail: el => openDetail(el.dataset.id),
  close:()=>movieDetail.close(),
  'entity-retry':()=>renderEntity(),
  'entity-missing':()=>changeBrowse({filter:state.filter==='missing'?'':'missing'}),
  'entity-filter':el=>{const kind=el.dataset.kind,value=el.dataset.value;if(kind==='tag'&&!state.tags.includes(value)&&state.tags.length>=20){toast('最多同时选择 20 个标签');return;}changeBrowse(kind==='tag'?{tags:state.tags.includes(value)?state.tags.filter(t=>t!==value):[...state.tags,value]}:{[kind]:state[kind]===value?'':value});},
  'copy-key': () => copy(state.settings.api_key),

};
history.scrollRestoration='manual';
window.addEventListener('hashchange',route);window.addEventListener('popstate',route);
window.addEventListener('scroll',()=>{clearTimeout(scrollTimer);scrollTimer=setTimeout(rememberScroll,120);},{passive:true});
document.addEventListener('click',event=>{
  const link=event.target.closest('a[href^="#"]');
  if(!link||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||link.target==='_blank')return;
  event.preventDefault();navigate(link.getAttribute('href'));
});
document.addEventListener('pointerdown',event=>{document.querySelectorAll('.filter-picker[open]').forEach(p=>{if(!p.contains(event.target))p.open=false;});});
document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.filter-picker[open]').forEach(p=>p.open=false);});
document.addEventListener('keydown',event=>{if(event.key==='/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) && !$('#detail').open && $('#search')) {event.preventDefault();$('#search').focus();}});
load().catch(error=>{ $('#app').innerHTML='<main class="loading"><p>'+esc(error.message)+'</p><button class="button" id="retry-open">重新打开</button></main>'; $('#retry-open').onclick=()=>location.reload(); });
