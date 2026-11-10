'use strict';
globalThis.CollectionManager=class CollectionManager {
  constructor(options) {
    this.options=options;this.dialog=document.querySelector('#collection-dialog');
    this.dialogVersion=0;this.pageVersion=0;
    this.dialog.addEventListener('close',()=>{this.dialogVersion++;this.dialogController?.abort();clearTimeout(this.timer);});
    this.dialog.onclick=event=>{if(event.target===this.dialog)this.dialog.close();};
  }
  listHref(id){return MaxhubBrowse.href({...MaxhubBrowse.defaults(),list:id});}
  changed(){this.options.changed();}
  disposePage(){this.pageVersion++;this.pageController?.abort();}
  async renderPage(target, search='', pages={actors:1,lists:1}) {
    this.disposePage();const version=this.pageVersion,{api,esc,icon}=this.options;
    this.pageController=new AbortController();target.innerHTML='<p class="muted" role="status">正在读取收藏…</p>';
    try {
      const [actors,lists]=await Promise.all([
        api('/api/favorites/actors?'+new URLSearchParams({page:pages.actors,limit:24,search}),undefined,this.pageController.signal),
        api('/api/lists?'+new URLSearchParams({page:pages.lists,limit:24,search}),undefined,this.pageController.signal)]);
      if(version!==this.pageVersion||!target.isConnected)return;
      const pager=(data,kind)=>data.total>data.limit?`<div class="pagination"><button class="button" data-saved-page="${kind}" data-step="-1" ${data.page===1?'disabled':''}>上一页</button><span>${data.page} / ${Math.ceil(data.total/data.limit)}</span><button class="button" data-saved-page="${kind}" data-step="1" ${data.page*data.limit>=data.total?'disabled':''}>下一页</button></div>`:'';
      target.innerHTML=`<section class="saved-section"><div class="saved-section-heading"><h2>收藏的演员 <small>${actors.total}</small></h2><button class="button" data-saved-add-actor>添加演员</button></div><div class="actor-grid">${actors.items.map(a=>`<article class="saved-actor"><a class="actor-card" href="${esc(MaxhubBrowse.profile('actor',a.name))}"><span class="avatar">${a.thumb?`<img src="${esc(a.thumb)}" alt="" loading="lazy">`:esc([...a.name][0])}</span><strong>${esc(a.name)}</strong><small>${a.count} 部影片</small></a></article>`).join('')}</div>${!actors.total?'<p class="saved-empty">'+(search?'没有匹配的收藏演员。':'收藏常看的演员，在这里集中查看和管理。')+'</p>':''}${pager(actors,'actors')}</section><section class="saved-section"><div class="saved-section-heading"><h2>自定义清单 <small>${lists.total}</small></h2><button class="button" data-saved-new-list>新建清单</button></div><div class="saved-list-grid">${lists.items.map(l=>`<article class="saved-list-card"><a href="${esc(this.listHref(l.id))}">${icon('list')}<strong>${esc(l.name)}</strong><small>${l.count} 部影片</small></a><div><button data-saved-edit-list="${l.id}">改名</button><button data-saved-delete-list="${l.id}">删除</button></div></article>`).join('')}</div>${!lists.total?'<p class="saved-empty">'+(search?'没有匹配的清单。':'新建清单，在影片详情中加入想整理的影片。')+'</p>':''}${pager(lists,'lists')}</section>`;
      target.querySelector('[data-saved-add-actor]').onclick=()=>this.chooseActor();
      target.querySelector('[data-saved-new-list]').onclick=()=>this.editList();
      for(const l of lists.items){target.querySelector(`[data-saved-edit-list="${l.id}"]`).onclick=()=>this.editList(l);target.querySelector(`[data-saved-delete-list="${l.id}"]`).onclick=()=>this.deleteList(l);}
      target.querySelectorAll('[data-saved-page]').forEach(b=>b.onclick=()=>this.renderPage(target,search,{actors:actors.page,lists:lists.page,[b.dataset.savedPage]:(b.dataset.savedPage==='actors'?actors.page:lists.page)+Number(b.dataset.step)}));
      this.options.restoreScroll();
    } catch(error){if(error.name!=='AbortError'&&version===this.pageVersion&&target.isConnected){target.innerHTML=`<p class="error" role="alert">${esc(error.message)}</p><button class="button">重试</button>`;target.querySelector('button').onclick=()=>this.renderPage(target,search,pages);}}
  }
  openDialog(title, body) {
    this.dialogController?.abort();clearTimeout(this.timer);this.dialogVersion++;
    const {esc,icon}=this.options;
    this.dialog.innerHTML=`<header class="saved-dialog-heading"><h2>${esc(title)}</h2><button class="icon-button" aria-label="关闭收藏窗口">${icon('close')}</button></header><div class="saved-dialog-body">${body}<p class="error saved-dialog-error" role="alert" hidden></p></div>`;
    this.dialog.querySelector('header button').onclick=()=>this.dialog.close();
    if(!this.dialog.open)this.dialog.showModal();
    return this.dialogVersion;
  }
  showError(error,version){if(version===this.dialogVersion&&this.dialog.open){const box=this.dialog.querySelector('.saved-dialog-error');box.hidden=false;box.textContent=error.message;}}
  editList(list=null) {
    const {api,esc}=this.options,version=this.openDialog(list?'清单改名':'新建清单',`<form id="saved-list-form"><label>清单名称<input name="name" aria-label="清单名称" maxlength="80" value="${esc(list?.name||'')}" required autocomplete="off"></label><button class="button primary" type="submit">${list?'保存名称':'创建清单'}</button></form>`);
    const form=this.dialog.querySelector('form');form.querySelector('input').focus();
    form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('button');button.disabled=true;try{await api('/api/lists'+(list?'/'+list.id:''),{name:form.elements.name.value});if(version===this.dialogVersion)this.dialog.close();await this.changed();}catch(e){this.showError(e,version);}finally{button.disabled=false;}};
  }
  deleteList(list) {
    const {api,esc}=this.options,version=this.openDialog('删除清单',`<p>删除「${esc(list.name)}」？影片和来源文件会保留。</p><button class="button" data-saved-cancel>取消</button> <button class="button primary" data-saved-confirm>删除清单</button>`);
    this.dialog.querySelector('[data-saved-cancel]').onclick=()=>this.dialog.close();
    const button=this.dialog.querySelector('[data-saved-confirm]');button.onclick=async()=>{button.disabled=true;try{await api('/api/lists/'+list.id,{delete:true});if(version===this.dialogVersion)this.dialog.close();this.options.deleted(list.id);await this.changed();}catch(e){this.showError(e,version);button.disabled=false;}};
  }
  chooseActor(){this.picker('actor');}
  chooseMovieLists(movie){this.picker('movie',movie);}
  picker(kind,movie=null) {
    const {esc}=this.options;
    this.pickerState={kind,movie,page:1,search:''};
    this.openDialog(kind==='actor'?'添加收藏演员':'加入清单',`${movie?`<p class="muted">${esc(movie.code||movie.title)}</p>`:''}<label class="search"><input type="search" aria-label="${kind==='actor'?'搜索要收藏的演员':'搜索清单'}" placeholder="${kind==='actor'?'搜索演员':'搜索清单'}"></label><div class="saved-picker-results" aria-live="polite"></div>${kind==='movie'?'<form class="saved-inline-create"><label class="sr-only" for="saved-inline-name">新清单名称</label><input id="saved-inline-name" name="name" maxlength="80" placeholder="新清单名称" required><button class="button" type="submit">创建并加入</button></form>':''}`);
    const input=this.dialog.querySelector('input[type=search]');
    input.oninput=()=>{this.dialogController?.abort();this.dialogVersion++;this.dialog.querySelector('.saved-picker-results').innerHTML='<p class="muted">正在读取…</p>';clearTimeout(this.timer);this.timer=setTimeout(()=>{this.pickerState.search=input.value;this.pickerState.page=1;this.loadPicker();},220);};
    if(kind==='movie')this.dialog.querySelector('form').onsubmit=async event=>{
      event.preventDefault();const form=event.target,button=form.querySelector('button'),version=this.dialogVersion;button.disabled=true;
      try{const list=await this.options.api('/api/lists',{name:form.elements.name.value});await this.options.api('/api/lists/'+list.id+'/movies',{movie_id:movie.id,included:true});form.reset();if(version===this.dialogVersion){this.pickerState.search='';this.pickerState.page=1;input.value='';this.loadPicker();}await this.changed();}catch(e){this.showError(e,version);}finally{button.disabled=false;}
    };
    this.loadPicker();input.focus();
  }
  async loadPicker() {
    this.dialogController?.abort();this.dialogController=new AbortController();const version=++this.dialogVersion;
    const p=this.pickerState,{api,esc}=this.options,target=this.dialog.querySelector('.saved-picker-results');
    target.innerHTML='<p class="muted">正在读取…</p>';this.dialog.querySelector('.saved-dialog-error').hidden=true;
    try {
      const query=new URLSearchParams({page:p.page,limit:20,search:p.search});
      if(p.kind==='actor')query.set('kind','actor');else query.set('movie_id',p.movie.id);
      const data=await api((p.kind==='actor'?'/api/facets?':'/api/lists?')+query,undefined,this.dialogController.signal);
      if(version!==this.dialogVersion||!target.isConnected)return;
      p.page=data.page;
      target.innerHTML=data.items.map((item,i)=>`<button class="saved-picker-row" data-index="${i}" ${p.kind==='movie'?`role="checkbox" aria-checked="${item.included}"`:''}><span>${esc(item.name)}</span><small>${p.kind==='movie'?(item.included?'已加入 · 点击移除':'加入清单'):item.count+' 部影片 · 收藏'}</small></button>`).join('')||'<p class="saved-empty">'+(p.kind==='actor'?'没有匹配的演员。':'暂无匹配清单，可在下方创建。')+'</p>';
      if(data.total>data.limit)target.insertAdjacentHTML('beforeend',`<div class="pagination"><button class="button" data-step="-1" ${data.page===1?'disabled':''}>上一页</button><span>${data.page} / ${Math.ceil(data.total/data.limit)}</span><button class="button" data-step="1" ${data.page*data.limit>=data.total?'disabled':''}>下一页</button></div>`);
      target.querySelectorAll('[data-step]').forEach(b=>b.onclick=()=>{p.page+=Number(b.dataset.step);this.loadPicker();});
      target.querySelectorAll('[data-index]').forEach(b=>b.onclick=async()=>{
        b.disabled=true;const item=data.items[Number(b.dataset.index)];
        try {
          if(p.kind==='actor'){await api('/api/favorites/actors',{name:item.name,favorite:true});if(version===this.dialogVersion)this.dialog.close();}
          else{const included=!item.included;await api('/api/lists/'+item.id+'/movies',{movie_id:p.movie.id,included});item.included=included;if(version===this.dialogVersion){b.setAttribute('aria-checked',included);b.querySelector('small').textContent=included?'已加入 · 点击移除':'加入清单';}}
          await this.changed();
        }catch(e){this.showError(e,version);}finally{b.disabled=false;}
      });
    } catch(error){if(error.name!=='AbortError'&&version===this.dialogVersion){this.showError(error,version);target.innerHTML='<button class="button">重试</button>';target.querySelector('button').onclick=()=>this.loadPicker();}}
  }
};
