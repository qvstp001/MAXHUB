'use strict';
globalThis.MovieDetail=class MovieDetail {
  constructor(options) {
    this.options=options;this.dialog=document.querySelector('#detail');this.photo=document.querySelector('#lightbox');
    this.version=0;this.playVersion=0;this.resources=new Map();this.queue=[];this.player='potplayer';
    try{const choice=localStorage.getItem('maxhub.player');if(['potplayer','mpv','link'].includes(choice))this.player=choice;}catch{}
    this.dialog.onclick=event=>{
      if(event.target===this.dialog){this.close();return;}
      const button=event.target.closest('[data-detail-action]');if(button)this.action(button);
    };
    this.dialog.addEventListener('close',()=>this.cancel());
    this.photo.onclick=event=>{
      if(event.target===this.photo){this.photo.close();return;}
      const button=event.target.closest('[data-photo-action]');if(!button)return;
      const action=button.dataset.photoAction;if(action==='close')this.photo.close();else this.showPhoto(this.photoIndex+(action==='next'?1:-1));
    };
    this.photo.addEventListener('close',()=>{this.photo.innerHTML='';});
    document.addEventListener('keydown',event=>{
      if(event.altKey||event.ctrlKey||event.metaKey||event.isComposing||/INPUT|TEXTAREA|SELECT/.test(event.target.tagName))return;
      if(this.photo.open&&['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();this.showPhoto(this.photoIndex+(event.key==='ArrowRight'?1:-1));}
      else if(this.dialog.open&&['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();this.move(event.key==='ArrowRight'?1:-1);}
    });
  }
  cancel(){this.version++;this.playVersion++;this.controller?.abort();this.playController?.abort();this.data=null;this.links=null;if(this.photo.open)this.photo.close();}
  close(){this.cancel();this.dialog.close();}
  toolbar() {
    const {esc,icon}=this.options,index=this.queue.indexOf(this.id);
    return `<header class="detail-toolbar"><span class="detail-toolbar-label">${esc(this.data?.code||'影片详情')}</span><div class="detail-page-controls"><button class="icon-button" data-detail-action="previous" aria-label="上一部影片" ${index<=0?'disabled':''}>${icon('left')}</button><span>${index>=0?'本页 '+(index+1)+' / '+this.queue.length:''}</span><button class="icon-button" data-detail-action="next" aria-label="下一部影片" ${index<0||index>=this.queue.length-1?'disabled':''}>${icon('arrow')}</button></div><button class="icon-button" data-detail-action="close" aria-label="关闭详情">${icon('close')}</button></header>`;
  }
  async open(id,queue) {
    this.controller?.abort();this.playController?.abort();if(this.photo.open)this.photo.close();
    const version=++this.version;this.playVersion++;this.id=id;this.data=null;this.links=null;
    if(queue)this.queue=[...new Set(queue)];if(!this.queue.includes(id))this.queue=[id];
    this.dialog.innerHTML=this.toolbar()+'<div class="detail-status" role="status">正在读取本地资料…</div>';
    if(!this.dialog.open)this.dialog.showModal();
    this.controller=new AbortController();
    try {
      const data=await this.options.api('/api/movies/'+encodeURIComponent(id),undefined,this.controller.signal);
      if(version!==this.version||!this.dialog.open)return;
      this.data=data;this.render();
    } catch(error){if(error.name!=='AbortError'&&version===this.version&&this.dialog.open)this.dialog.innerHTML=this.toolbar()+`<div class="detail-status"><p class="error" role="alert">${this.options.esc(error.message)}</p><button class="button" data-detail-action="retry">重试</button></div>`;}
  }
  move(step){const index=this.queue.indexOf(this.id),next=this.queue[index+step];if(next)this.open(next);}
  link(kind,name,content,cls='chip') {
    const {esc,profileHref,filterHref}=this.options;
    return `<a class="${cls}" href="${esc(['actor','studio'].includes(kind)?profileHref(kind,name):filterHref(kind,name))}">${content||esc(name)}</a>`;
  }
  render() {
    const m=this.data,{esc,icon}=this.options;
    this.art=m.cover?'cover':'poster';this.galleryShown=0;
    const remembered=this.resources.get(m.id);
    this.selected=m.resources.find(r=>r.id===remembered&&r.available)||m.resources.find(r=>r.available)||m.resources[0]||null;
    this.dialog.innerHTML=this.toolbar()+`<div class="detail-shell"><section class="detail-media" aria-label="本地图片"><div class="detail-art-controls"><div class="layout-toggle"><button data-detail-action="art" data-art="cover" ${!m.cover?'disabled':''} class="${this.art==='cover'?'selected':''}">横幅</button><button data-detail-action="art" data-art="poster" ${!m.poster?'disabled':''} class="${this.art==='poster'?'selected':''}">海报</button></div><a id="detail-original" class="text-link" target="_blank" rel="noopener" ${m[this.art]?`href="${esc(m[this.art])}"`: 'hidden'}>查看原图 ${icon('external')}</a></div><a class="detail-art-main" data-art="${this.art}" ${m[this.art]?`href="${esc(m[this.art])}" target="_blank" rel="noopener"`:''} aria-label="查看影片原图"><span class="detail-art-placeholder">${icon('film')}<span>暂无本地封面</span></span>${m[this.art]?`<img id="detail-image" src="${esc(m[this.art])}" alt="${esc(m.title)}" decoding="async">`:''}</a>
      ${m.samples.length?`<details class="detail-gallery"><summary>本地剧照 <span>${m.samples.length}</span></summary><div class="detail-thumbnails"></div><button class="button gallery-more" data-detail-action="more-photos" hidden>加载更多剧照</button></details>`:''}</section>
      <section class="detail-summary"><div class="detail-heading"><div><span class="detail-eyebrow">${esc(m.code||'本地影片')}</span><h2 id="detail-title">${esc(m.title)}</h2>${m.original_title&&m.original_title!==m.title?`<p class="detail-original-title">${esc(m.original_title)}</p>`:''}</div></div>
      <dl class="detail-facts">${[[m.date||m.year,'发行日期'],[m.runtime?m.runtime+' 分钟':'','时长'],[m.score?Number(m.score).toFixed(1):'','NFO 评分']].map(([value,label])=>`<div><dt>${label}</dt><dd>${esc(value||'未记录')}</dd></div>`).join('')}</dl>
      <div class="detail-relations">${m.studio?`<div><span>厂商</span>${this.link('studio',m.studio)}</div>`:''}${m.series?`<div><span>系列</span>${this.link('series',m.series)}</div>`:''}${m.director?`<div><span>导演</span><strong>${esc(m.director)}</strong></div>`:''}</div>
      <section class="detail-playback" aria-label="资源与播放"><label>播放资源 <span>${m.resources.length} 个</span><select id="detail-resource" aria-label="选择播放资源" ${!m.available?'disabled':''}>${m.resources.map(r=>`<option value="${r.id}" ${this.selected?.id===r.id?'selected':''} ${!r.available?'disabled':''}>${esc(r.name)}${!r.available?' · 不可用':''}</option>`).join('')}</select></label><div class="detail-resource-location"></div><button class="button primary detail-prepare" data-detail-action="prepare" ${!this.selected?.available?'disabled':''}>${icon('play')} 选择播放器</button><p class="detail-play-error error" role="alert" hidden></p><div id="play-panel" class="play-panel" hidden></div></section>
      ${m.actors.length?`<section class="detail-cast"><h3>出演演员 <span>${m.actors.length}</span></h3><div class="actor-chips">${m.actors.map(a=>this.link('actor',a.name,`<span class="mini-avatar">${a.thumb?`<img src="${esc(a.thumb)}?size=avatar" alt="" loading="lazy" decoding="async">`:esc([...a.name][0])}</span><span>${esc(a.name)}${a.role?`<small>${esc(a.role)}</small>`:''}</span>`,'actor-chip')).join('')}</div></section>`:''}
      ${m.tags.length?`<section class="detail-tags"><h3>影片标签</h3><div class="chips">${m.tags.map(t=>this.link('tag',t)).join('')}</div></section>`:''}
      ${m.plot?`<details class="detail-plot" open><summary>简介</summary><p>${esc(m.plot)}</p></details>`:''}</section></div>`;
    this.dialog.setAttribute('aria-label',m.title);
    this.dialog.querySelector('#detail-resource').onchange=event=>this.selectResource(event.target.value);
    this.paintResource();this.imageFallbacks(this.dialog);
    const gallery=this.dialog.querySelector('.detail-gallery');if(gallery)gallery.ontoggle=()=>{if(gallery.open&&!this.galleryShown)this.morePhotos();};
    this.dialog.querySelector('[aria-label="关闭详情"]').focus({preventScroll:true});
  }
  selectResource(id) {
    const resource=this.data.resources.find(r=>r.id===id&&r.available);if(!resource)return;
    this.selected=resource;this.resources.set(this.id,id);if(this.resources.size>100)this.resources.delete(this.resources.keys().next().value);
    this.playVersion++;this.playController?.abort();this.links=null;
    this.dialog.querySelector('#play-panel').hidden=true;this.dialog.querySelector('#play-panel').innerHTML='';
    this.dialog.querySelector('.detail-play-error').hidden=true;this.dialog.querySelector('.detail-prepare').disabled=false;this.paintResource();
  }
  paintResource() {
    const r=this.selected,{esc,icon,folderHref}=this.options,target=this.dialog.querySelector('.detail-resource-location');
    target.innerHTML=r?`<span>${esc(r.root)}${r.folder?'/'+esc(r.folder):''}</span>${r.folder!==null?`<a class="text-link" href="${esc(folderHref(r))}">${icon('folder')} 在目录中查看</a>`:''}`:'<span>暂无资源</span>';
  }
  async prepare() {
    const resource=this.selected;if(!resource?.available)return;
    const version=++this.playVersion,id=this.id,button=this.dialog.querySelector('.detail-prepare'),errorBox=this.dialog.querySelector('.detail-play-error');
    button.disabled=true;errorBox.hidden=true;this.playController?.abort();this.playController=new AbortController();
    try {
      const links=await this.options.api(`/api/movies/${encodeURIComponent(id)}/play`,{resource_id:resource.id},this.playController.signal);
      if(version!==this.playVersion||id!==this.id||resource.id!==this.selected?.id||!this.dialog.open)return;
      this.links=links;this.expires=Date.now()+links.expires_in*1000;this.paintPlayer();
    } catch(error){if(error.name!=='AbortError'&&version===this.playVersion&&this.dialog.open){errorBox.textContent=error.message;errorBox.hidden=false;}}
    finally{if(version===this.playVersion&&this.dialog.open)button.disabled=false;}
  }
  paintPlayer() {
    const panel=this.dialog.querySelector('#play-panel'),{esc}=this.options;panel.hidden=false;
    panel.innerHTML=`<label>此设备的播放器<select id="detail-player" aria-label="此设备的播放器"><option value="potplayer">PotPlayer · Windows</option><option value="mpv">mpv · Android</option><option value="link">复制链接 / M3U</option></select></label><div class="player-links"><a class="button primary" id="detail-player-open"></a><button class="button" data-detail-action="copy">复制播放链接</button><button class="button" data-detail-action="m3u">下载 M3U</button></div><p>地址：<code>${esc(new URL(this.links.url).origin)}</code> · 链接有效期 ${Math.round(this.links.expires_in/3600)} 小时</p><p>播放器选择保存在此设备，每次播放会生成新的链接。</p>`;
    const select=panel.querySelector('select');select.value=this.player;
    select.onchange=()=>{this.player=select.value;try{localStorage.setItem('maxhub.player',this.player);}catch{}this.paintPlayerLink();};
    this.paintPlayerLink();
  }
  paintPlayerLink() {
    const link=this.dialog.querySelector('#detail-player-open');link.hidden=this.player==='link';
    link.href=this.player==='mpv'?this.links.mpv:this.links.potplayer;link.textContent=this.player==='mpv'?'用 mpv 打开':'用 PotPlayer 打开';
    link.onclick=event=>{if(!this.validLinks())event.preventDefault();};
  }
  validLinks(){if(this.links&&Date.now()<this.expires)return true;this.options.toast('播放链接已过期，请重新生成');return false;}
  action(button) {
    const action=button.dataset.detailAction;
    if(action==='close')this.close();else if(action==='retry')this.open(this.id);
    else if(action==='next'||action==='previous')this.move(action==='next'?1:-1);
    else if(action==='prepare')this.prepare();
    else if(action==='art')this.showArt(button.dataset.art);
    else if(action==='more-photos')this.morePhotos();
    else if(action==='photo')this.showPhoto(Number(button.dataset.index));
    else if(action==='copy'&&this.validLinks())this.options.copy(this.links.url).catch(e=>this.options.toast(e.message));
    else if(action==='m3u'&&this.validLinks()){
      const url=URL.createObjectURL(new Blob(['#EXTM3U\n'+this.links.url+'\n'],{type:'audio/x-mpegurl'})),anchor=document.createElement('a');anchor.href=url;anchor.download=(this.data.code||'maxhub')+'.m3u';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
  }
  showArt(kind) {
    if(!this.data?.[kind])return;this.art=kind;
    const image=this.dialog.querySelector('#detail-image'),frame=this.dialog.querySelector('.detail-art-main');frame.dataset.art=kind;frame.href=this.data[kind];
    if(image){image.hidden=false;image.src=this.data[kind];}this.dialog.querySelector('#detail-original').href=this.data[kind];
    this.dialog.querySelectorAll('[data-detail-action="art"]').forEach(b=>b.classList.toggle('selected',b.dataset.art===kind));
  }
  morePhotos() {
    const {esc}=this.options,end=Math.min(this.galleryShown+12,this.data.samples.length),target=this.dialog.querySelector('.detail-thumbnails');
    target.insertAdjacentHTML('beforeend',this.data.samples.slice(this.galleryShown,end).map((src,i)=>`<button class="gallery-thumb" data-detail-action="photo" data-index="${this.galleryShown+i}" aria-label="查看剧照 ${this.galleryShown+i+1}"><img src="${esc(src)}?size=preview" alt="剧照 ${this.galleryShown+i+1}" loading="lazy" decoding="async"></button>`).join(''));
    this.galleryShown=end;this.dialog.querySelector('.gallery-more').hidden=end>=this.data.samples.length;this.imageFallbacks(target);
  }
  showPhoto(index) {
    if(!this.data||!Number.isInteger(index)||index<0||index>=this.data.samples.length)return;
    const {esc,icon}=this.options;this.photoIndex=index;
    this.photo.innerHTML=`<div class="photo-toolbar"><span>剧照 ${index+1} / ${this.data.samples.length}</span><a href="${esc(this.data.samples[index])}" target="_blank" rel="noopener">查看原图</a><button class="icon-button" data-photo-action="close" aria-label="关闭图片">${icon('close')}</button></div><div class="photo-stage"><button class="icon-button" data-photo-action="previous" aria-label="上一张图片" ${index===0?'disabled':''}>${icon('left')}</button><div class="photo-image"><span hidden>图片不可用</span><img src="${esc(this.data.samples[index])}" alt="剧照 ${index+1}" decoding="async"></div><button class="icon-button" data-photo-action="next" aria-label="下一张图片" ${index===this.data.samples.length-1?'disabled':''}>${icon('arrow')}</button></div>`;
    this.imageFallbacks(this.photo);if(!this.photo.open)this.photo.showModal();
  }
  imageFallbacks(root){root.querySelectorAll('img').forEach(image=>{image.onerror=()=>{image.hidden=true;const message=image.closest('.photo-image')?.querySelector('span');if(message)message.hidden=false;};});}
};
