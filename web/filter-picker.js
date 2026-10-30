'use strict';
globalThis.FilterPicker=class FilterPicker {
  constructor(options){this.options=options;this.instances=[];}
  dispose(){for(const item of this.instances){item.controller?.abort();clearTimeout(item.timer);}this.instances=[];}
  mount(target,state) {
    this.dispose();
    const {icon}=this.options;
    target.innerHTML=[['actor','演员','people'],['studio','厂商','film'],['tag','影片标签','tag']].map(([kind,label,glyph])=>`<details class="filter-picker" data-picker="${kind}"><summary class="filter-chip">${icon(glyph)}${label}${kind==='tag'&&state.tags.length?`<b>${state.tags.length}</b>`:state[kind]?'<b>1</b>':''}</summary><div class="filter-popover" role="group" aria-label="${label}筛选"></div></details>`).join('');
    target.querySelectorAll('details').forEach(details=>{
      const item={details,kind:details.dataset.picker,page:1,search:'',version:0};this.instances.push(item);
      details.ontoggle=()=>{
        if(!details.open){item.controller?.abort();clearTimeout(item.timer);return;}
        this.instances.forEach(other=>{if(other!==item)other.details.open=false;});
        item.draft=new Set(item.kind==='tag'?state.tags:[state[item.kind]].filter(Boolean));item.page=1;item.search='';
        const panel=details.querySelector('.filter-popover');
        panel.innerHTML=`<p class="picker-hint">${item.kind==='tag'?'同时满足所选标签':'选择一项，可与其它条件组合'}</p><label class="search"><input type="search" placeholder="搜索${({actor:'演员',studio:'厂商',tag:'标签'})[item.kind]}" aria-label="搜索筛选选项"></label><div class="picker-selected"></div><div class="picker-options" aria-live="polite"></div><div class="picker-footer"><button class="button" data-picker-clear>清空选择</button><button class="button primary" data-picker-apply>应用筛选</button></div>`;
        const input=panel.querySelector('input');
        const search=()=>{item.version++;item.controller?.abort();clearTimeout(item.timer);item.timer=setTimeout(()=>{item.search=input.value;item.page=1;this.load(item);},220);};
        input.oninput=e=>{if(!e.isComposing)search();};input.oncompositionend=search;
        panel.onclick=event=>{
          const choice=event.target.closest('[data-picker-value]');
          if(choice){
            const value=choice.dataset.pickerValue;
            if(item.draft.has(value))item.draft.delete(value);
            else if(item.kind==='tag'){if(item.draft.size>=20){this.options.toast('最多选择 20 个标签');return;}item.draft.add(value);}
            else{item.draft.clear();item.draft.add(value);}
            this.paintSelection(item);return;
          }
          if(event.target.closest('[data-picker-clear]')){item.draft.clear();this.paintSelection(item);}
          if(event.target.closest('[data-picker-apply]')){details.open=false;this.options.apply(item.kind==='tag'?{tags:[...item.draft]}:{[item.kind]:[...item.draft][0]||''});}
          const page=event.target.closest('[data-picker-page]');if(page&&!page.disabled){item.page+=Number(page.dataset.pickerPage);this.load(item);}
          if(event.target.closest('[data-picker-retry]'))this.load(item);
        };
        this.paintSelection(item);this.load(item);input.focus();
      };
    });
  }
  paintSelection(item) {
    const {esc,icon}=this.options, panel=item.details.querySelector('.filter-popover');
    panel.querySelector('.picker-selected').innerHTML=[...item.draft].map(value=>`<button class="chip" data-picker-value="${esc(value)}">${esc(value)} ${icon('close')}</button>`).join('');
    panel.querySelectorAll('.picker-option').forEach(button=>button.setAttribute('aria-pressed',item.draft.has(button.dataset.pickerValue)));
    panel.querySelector('[data-picker-apply]').textContent=`应用筛选${item.draft.size?'（'+item.draft.size+'）':''}`;
  }
  async load(item) {
    const version=++item.version,{esc,icon}=this.options, target=item.details.querySelector('.picker-options');
    item.controller?.abort();item.controller=new AbortController();target.innerHTML='<p class="muted" role="status">正在读取…</p>';
    try {
      const data=await this.options.api('/api/facets?'+new URLSearchParams({kind:item.kind,search:item.search,page:item.page,limit:60}),undefined,item.controller.signal);
      if(version!==item.version||!item.details.isConnected||!item.details.open)return;
      item.page=data.page;const pages=Math.max(1,Math.ceil(data.total/data.limit));
      target.innerHTML=`<div class="picker-readout">全库 ${data.total} 项</div><div class="picker-list">${data.items.map(option=>`<button class="picker-option" data-picker-value="${esc(option.name)}" aria-pressed="${item.draft.has(option.name)}"><span class="picker-mark">${icon('check')}</span><span>${esc(option.name)}</span><small>${option.count}</small></button>`).join('')||'<p class="muted">没有匹配的选项</p>'}</div>${pages>1?`<div class="picker-pagination"><button data-picker-page="-1" ${data.page<=1?'disabled':''}>上一页</button><span>${data.page} / ${pages}</span><button data-picker-page="1" ${data.page>=pages?'disabled':''}>下一页</button></div>`:''}`;
    } catch(error){if(error.name!=='AbortError'&&version===item.version&&item.details.isConnected)target.innerHTML=`<p class="error">${esc(error.message)}</p><button class="button" data-picker-retry>重试</button>`;}
  }
};
