'use strict';
// 地址与请求使用同一组浏览条件，供桌面页面和历史导航复用。
(() => {
  const defaults = () => ({view:'library',search:'',sort:'added',page:1,filter:'',actor:'',studio:'',series:'',tags:[],root:'',folder:'',recursive:true});
  const uniqueTags = values => [...new Set(values.filter(v=>typeof v==='string'&&v))].slice(0,20);
  function normalize(value) {
    const result={...defaults(),...value};
    result.tags=uniqueTags(Array.isArray(result.tags)?result.tags:[]);
    result.page=Number.isSafeInteger(Number(result.page))?Math.max(1,Math.min(1000000,Number(result.page))):1;
    if(!['added','date','title','score'].includes(result.sort))result.sort='added';
    if(!['','missing','watched','unwatched'].includes(result.filter))result.filter='';
    if(!['library','folders','actors','fields','settings'].includes(result.view))result.view='library';
    if(!result.root){result.folder='';result.recursive=true;}
    return result;
  }
  function parse(hash) {
    const raw=String(hash||'').replace(/^#/,''), split=raw.indexOf('?');
    const address=split<0?raw:raw.slice(0,split), params=new URLSearchParams(split<0?'':raw.slice(split+1));
    const [view,kind,...parts]=address.split('/');
    const value={...defaults(),view:view==='tags'?'fields':view||'library'};
    let legacy='';try{legacy=decodeURIComponent(parts.join('/'));}catch{}
    if(['actor','studio','series','tag'].includes(kind)) {
      value.view=kind==='actor'?'actors':kind==='studio'?'fields':'library';if(kind==='tag')value.tags=[legacy];else value[kind]=legacy;
    } else if(kind==='search'){value.search=legacy;value.view='library';}
    else if(view==='folders'&&kind==='folder') {
      try{const folder=JSON.parse(legacy);value.root=String(folder.root||'');value.folder=String(folder.path||'');}catch{}
    }
    for(const key of ['actor','studio','series','root','folder','sort','page'])if(params.has(key))value[key]=params.get(key);
    if(params.has('tag'))value.tags=params.getAll('tag');
    if(params.has('q'))value.search=params.get('q');
    if(params.has('status'))value.filter=params.get('status');
    value.recursive=params.get('recursive')!=='0';
    return normalize(value);
  }
  function href(value) {
    const s=normalize(value), q=new URLSearchParams();
    for(const [key,v] of [['actor',s.actor],['studio',s.studio],['series',s.series]])if(v)q.set(key,v);
    for(const tag of s.tags)q.append('tag',tag);
    if(s.root){q.set('root',s.root);if(s.folder)q.set('folder',s.folder);if(!s.recursive)q.set('recursive','0');}
    if(s.search)q.set('q',s.search);
    if(s.filter)q.set('status',s.filter);
    if(s.sort!=='added')q.set('sort',s.sort);
    if(s.page!==1)q.set('page',s.page);
    const query=q.toString();return '#'+s.view+(query?'?'+query:'');
  }
  function entity(value){return value.view==='actors'&&value.actor?{kind:'actor',name:value.actor}:value.view==='fields'&&value.studio?{kind:'studio',name:value.studio}:null;}
  function profile(kind,name){return href({...defaults(),view:kind==='actor'?'actors':'fields',[kind]:name});}
  const api={defaults,normalize,parse,href,entity,profile};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else globalThis.MaxhubBrowse=api;
})();
