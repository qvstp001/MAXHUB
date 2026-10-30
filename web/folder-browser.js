'use strict';
// 目录分支仅在展开时读取，缓存只在本次页面会话中保留。
globalThis.FolderBrowser=class FolderBrowser {
  constructor(options) {
    this.options=options;this.cache=new Map();this.expanded=new Set();this.search='';this.epoch=0;this.mountVersion=0;
  }
  key(root='',path='',search=''){return JSON.stringify([root,path,search]);}
  invalidate(){this.epoch++;this.cache.clear();}
  detach(){clearTimeout(this.timer);this.mountVersion++;this.target=null;this.header=null;}
  clearSearch(){this.search='';clearTimeout(this.timer);const input=this.target?.querySelector('input');if(input)input.value='';queueMicrotask(()=>this.renderTree());}
  async load(root='',path='',page=1,search='') {
    const key=this.key(root,path,search), epoch=this.epoch;
    let entry=this.cache.get(key);
    if(entry?.loading)return entry.promise;
    if(entry&&entry.page>=page&&!entry.error)return entry;
    if(!entry){entry={root,path,search,items:[],page:0,total:0};this.cache.set(key,entry);}
    entry.loading=true;entry.error='';
    const params=new URLSearchParams({root,path,page,limit:100});if(search)params.set('search',search);
    entry.promise=(async()=>{
      try {
        const data=await this.options.api('/api/folders?'+params);
        if(epoch!==this.epoch)return entry;
        const rows=page===1?data.items:[...entry.items,...data.items];
        entry.items=[...new Map(rows.map(n=>[this.key(n.root,n.path),n])).values()];
        Object.assign(entry,{page:data.page,total:data.total,ancestors:data.ancestors,selected:data.selected});
      } catch(error){if(epoch===this.epoch)entry.error=error.message;}
      finally{entry.loading=false;if(epoch===this.epoch)this.renderTree();}
      return entry;
    })();
    return entry.promise;
  }
  mount(target,header,selection) {
    clearTimeout(this.timer);
    const {esc,icon}=this.options, version=++this.mountVersion;
    this.target=target;this.header=header;this.selection=selection;
    target.innerHTML=`<div class="folder-tree-title">${icon('folder')}<strong>文件夹</strong></div><label class="search folder-search">${icon('search')}<input id="folder-search" type="search" aria-label="查找文件夹" placeholder="查找文件夹" value="${esc(this.search)}"></label><div class="folder-tree-content"></div><p class="folder-tree-note">目录数量按全库统计</p>`;
    const input=target.querySelector('input');
    const search=()=>{clearTimeout(this.timer);this.timer=setTimeout(()=>{this.search=input.value.trim();this.renderTree();this.load('','',1,this.search);},220);};
    input.oninput=e=>{if(!e.isComposing)search();};input.oncompositionend=search;
    target.onclick=event=>this.click(event);
    header.innerHTML='<p class="muted">正在读取目录…</p>';
    this.renderTree();this.load();if(this.search)this.load('','',1,this.search);
    this.load(selection.root,selection.path).then(entry=>{
      if(version!==this.mountVersion||!header.isConnected)return;
      if(entry.error){header.innerHTML=`<p class="error" role="alert">${esc(entry.error)}</p><button class="button" data-folder-retry>重试</button>`;header.querySelector('button').onclick=()=>this.mount(target,header,selection);return;}
      for(const node of entry.ancestors||[])if(node.has_children){this.expanded.add(this.key(node.root,node.path));this.load(node.root,node.path);}
      this.renderHeader(entry);this.renderTree();
    });
  }
  click(event) {
    const link=event.target.closest('a[data-folder-link]');
    if(link&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey){this.clearSearch();return;}
    const button=event.target.closest('button[data-folder-branch],button[data-folder-page],button[data-folder-retry]');
    if(!button)return;
    const key=button.dataset.folderBranch||button.dataset.folderPage||button.dataset.folderRetry;
    const [root,path,search]=JSON.parse(key);
    if(button.hasAttribute('data-folder-branch')) {
      if(this.expanded.has(key))this.expanded.delete(key);else{this.expanded.add(key);this.load(root,path);}
      this.renderTree();
    } else {
      const entry=this.cache.get(key);this.load(root,path,button.hasAttribute('data-folder-page')?(entry?.page||0)+1:Math.max(1,(entry?.page||0)+1),search);
    }
  }
  renderTree() {
    if(!this.target?.isConnected)return;
    const body=this.target.querySelector('.folder-tree-content');if(!body)return;
    const {esc,href}=this.options;
    if(this.search) {
      const entry=this.cache.get(this.key('','',this.search));
      body.innerHTML=`<div class="folder-search-results">${entry?.items.map(node=>`<a data-folder-link href="${esc(href(node.root,node.path))}" class="folder-search-result"><strong>${esc(node.name)}</strong><span>${esc(node.root)}${node.path?'/'+esc(node.path):''}</span></a>`).join('')||''}${this.status(entry,this.key('','',this.search),true)}</div>`;
    } else {
      const entry=this.cache.get(this.key());
      body.innerHTML=`<nav aria-label="目录树"><a class="folder-all ${!this.selection?.root?'selected':''}" data-folder-link href="${esc(href('',''))}">全部来源</a><ul class="folder-tree-list">${entry?.items.map(n=>this.node(n)).join('')||''}${this.status(entry,this.key())}</ul></nav>`;
    }
  }
  node(node) {
    const {esc,icon,href}=this.options, key=this.key(node.root,node.path), open=this.expanded.has(key), entry=this.cache.get(key);
    const selected=this.selection.root===node.root&&this.selection.path===node.path;
    return `<li><div class="folder-tree-row ${selected?'selected':''}">${node.has_children?`<button class="tree-expand ${open?'expanded':''}" data-folder-branch="${esc(key)}" aria-label="${open?'收起':'展开'} ${esc(node.name)}" aria-expanded="${open}">${icon('chevron')}</button>`:'<span class="tree-spacer"></span>'}<a data-folder-link href="${esc(href(node.root,node.path))}" ${selected?'aria-current="page"':''} title="${esc(node.root+(node.path?'/'+node.path:''))}">${icon('folder')}<span>${esc(node.name)}</span><small>${node.count}</small></a></div>${open?`<ul class="folder-tree-list">${entry?.items.map(n=>this.node(n)).join('')||''}${this.status(entry,key)}</ul>`:''}</li>`;
  }
  status(entry,key,search=false) {
    const {esc}=this.options;let content='';
    if(!entry||entry.loading)content='<span class="muted" role="status">正在读取…</span>';
    else if(entry.error)content=`<span class="error">${esc(entry.error)}</span><button data-folder-retry="${esc(key)}" class="tree-more">重试</button>`;
    else if(entry.items.length<entry.total)content=`<button data-folder-page="${esc(key)}" class="tree-more">加载更多目录（${entry.items.length} / ${entry.total}）</button>`;
    else if(!entry.items.length)content=`<span class="muted">${search?'没有匹配的文件夹':'暂无子目录'}</span>`;
    return content?`<${search?'div':'li'} class="folder-tree-status">${content}</${search?'div':'li'}>`:'';
  }
  renderHeader(entry) {
    if(!this.header?.isConnected)return;
    const {esc,href}=this.options, selected=entry.selected, recursive=this.selection.recursive;
    this.header.innerHTML=`<nav class="folder-breadcrumbs" aria-label="文件夹路径"><a data-folder-link href="${esc(href('',''))}">全部来源</a>${(entry.ancestors||[]).map((node,i,rows)=>`<span aria-hidden="true">/</span>${i===rows.length-1?`<span aria-current="page" title="${esc(node.name)}">${esc(node.name)}</span>`:`<a data-folder-link href="${esc(href(node.root,node.path))}" title="${esc(node.name)}">${esc(node.name)}</a>`}`).join('')}</nav>${this.selection.root&&!selected?'<p class="muted">该目录不在媒体索引中。</p>':''}${selected?`<div class="folder-scope-row"><label><input id="folder-recursive" type="checkbox" ${recursive?'checked':''}>包含子文件夹</label><span>目录范围内 ${recursive?selected.count:selected.direct_count} 部影片</span></div>`:'<p class="muted">选择左侧目录，可继续叠加演员、厂商和标签条件。</p>'}`;
    const checkbox=this.header.querySelector('input');if(checkbox)checkbox.onchange=()=>this.options.onRecursive(checkbox.checked);
    this.header.onclick=event=>{if(event.target.closest('a[data-folder-link]'))this.clearSearch();};
  }
};
