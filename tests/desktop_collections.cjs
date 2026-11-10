// Run against tests/desktop_fixture.py; uses only fictional media.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_BROWSER_CHANNEL||undefined});
  const base=process.env.MAXHUB_TEST_URL||'http://127.0.0.1:18099';
  let page;
  try {
    for(const viewport of [{width:1440,height:1000},{width:1100,height:800}]) {
      page=await browser.newPage({viewport,reducedMotion:'reduce'});
      const errors=[],created=[];
      page.on('pageerror',e=>errors.push(e.message));
      page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
      const count=total=>page.waitForFunction(total=>document.querySelector('#results .results-label>span')?.textContent.startsWith(total+' 部影片')&&document.querySelectorAll('.movie-card').length===Math.min(total,60),total);
      const closeSaved=()=>page.getByRole('button',{name:'关闭收藏窗口',exact:true}).click();
      const listName='周末 <精选> '+viewport.width;
      try {
        for(const name of ['演员甲','演员乙']){
          const reset=await page.request.post(base+'/api/favorites/actors',{data:{name,favorite:false}});
          assert.equal(reset.status(),200,await reset.text());
        }
        await page.goto(base+'/#actors?actor='+encodeURIComponent('演员甲'));
        const favorite=page.getByRole('button',{name:'收藏演员',exact:true});await favorite.click();
        await page.waitForFunction(()=>document.querySelector('.actor-favorite')?.getAttribute('aria-pressed')==='true');
        await page.reload();await page.getByRole('button',{name:'已收藏演员',exact:true}).waitFor();
        assert.equal(await page.locator('.sidebar a[href="#folders"]').count(),0);
        assert.deepEqual(await page.locator('.sidebar nav .nav-link span').allTextContents(),['媒体库','演员','厂商与标签','收藏']);
        await page.locator('.sidebar a[href="#favorites"]').click();
        await page.locator('.saved-actor').filter({hasText:'演员甲'}).waitFor();
        await page.getByRole('button',{name:'添加演员',exact:true}).click();
        await page.getByRole('searchbox',{name:'搜索要收藏的演员'}).fill('演员乙');
        await page.locator('.saved-picker-row').filter({hasText:'演员乙'}).click();
        await page.locator('#collection-dialog[open]').waitFor({state:'hidden'});
        await page.locator('.saved-actor').filter({hasText:'演员乙'}).waitFor();
        assert.equal(await page.locator('.saved-actor button').count(),0);
        await page.screenshot({path:'artifacts/desktop-collection-actors-'+viewport.width+'.png',fullPage:true});
        await page.locator('[data-saved-new-list]').click();
        await page.getByRole('textbox',{name:'清单名称',exact:true}).fill(listName);
        await page.getByRole('button',{name:'创建清单',exact:true}).click();
        const card=page.locator('.saved-list-card').filter({hasText:listName});await card.waitFor();
        const href=await card.locator('a').getAttribute('href'),listId=new URLSearchParams(href.split('?')[1]).get('list');created.push(listId);
        await page.locator('a.nav-link[href="#library"]').click();await count(80);
        await page.locator('#search').fill('DESK-000');await count(1);
        await page.getByRole('button',{name:'查看 DESK-000',exact:true}).click();
        await page.getByRole('button',{name:'加入清单',exact:true}).click();
        let row=page.locator('.saved-picker-row').filter({hasText:listName});await row.click();
        await page.waitForFunction(name=>[...document.querySelectorAll('.saved-picker-row')].find(b=>b.textContent.includes(name))?.getAttribute('aria-checked')==='true',listName);
        await page.keyboard.press('ArrowRight');assert.equal(await page.locator('.detail-eyebrow').innerText(),'DESK-000');
        await closeSaved();assert.equal(await page.locator('#detail[open]').count(),1);
        await page.getByRole('button',{name:'关闭详情',exact:true}).click();
        await page.locator('.sidebar a[href="#favorites"]').click();
        await page.locator('.saved-list-card').filter({hasText:listName}).locator('a').click();await count(1);
        assert.equal(new URLSearchParams(page.url().split('?')[1]).get('list'),listId);
        await page.reload();await count(1);await page.locator('.saved-list-header h1').filter({hasText:listName}).waitFor();
        await page.locator('#search').fill('no-such-movie');await count(0);
        await page.getByRole('button',{name:'清除搜索和筛选',exact:true}).click();await count(1);
        assert.match(page.url(),new RegExp('list='+listId));
        await page.getByRole('button',{name:'改名',exact:true}).click();
        await page.getByRole('textbox',{name:'清单名称',exact:true}).fill(listName+' 已改名');
        await page.getByRole('button',{name:'保存名称',exact:true}).click();
        await page.locator('.saved-list-header h1').filter({hasText:'已改名'}).waitFor();
        await page.getByRole('button',{name:'查看 DESK-000',exact:true}).click();
        await page.getByRole('button',{name:'加入清单',exact:true}).click();
        row=page.locator('.saved-picker-row').filter({hasText:listName});assert.equal(await row.getAttribute('aria-checked'),'true');
        await row.click();await count(0);
        await page.waitForFunction(()=>document.querySelector('.saved-picker-row')?.getAttribute('aria-checked')==='false');
        await row.click();await count(1);
        await page.getByRole('textbox',{name:'新清单名称',exact:true}).fill('新建并加入 '+viewport.width);
        await page.getByRole('button',{name:'创建并加入',exact:true}).click();
        const inlineRow=page.locator('.saved-picker-row').filter({hasText:'新建并加入 '+viewport.width});await inlineRow.waitFor();
        assert.equal(await inlineRow.getAttribute('aria-checked'),'true');
        const lists=await (await page.request.get(base+'/api/lists')).json();
        created.push(lists.items.find(l=>l.name==='新建并加入 '+viewport.width).id);
        assert(await page.locator('#collection-dialog').evaluate(d=>d.scrollWidth<=d.clientWidth+1));
        await closeSaved();await page.getByRole('button',{name:'关闭详情',exact:true}).click();
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
        await page.screenshot({path:'artifacts/desktop-collections-'+viewport.width+'.png',fullPage:true});
        await page.getByRole('button',{name:'删除清单',exact:true}).click();
        await page.locator('#collection-dialog').getByRole('button',{name:'删除清单',exact:true}).click();
        await page.waitForURL('**/#favorites');
        await page.locator('.saved-actor').filter({hasText:'演员甲'}).locator('a').click();
        await page.getByRole('button',{name:'已收藏演员',exact:true}).click();
        await page.getByRole('button',{name:'收藏演员',exact:true}).waitFor();
        await page.locator('.sidebar a[href="#favorites"]').click();
        await page.locator('.saved-actor').filter({hasText:'演员甲'}).waitFor({state:'hidden'});
        assert.deepEqual(errors,[]);
        console.log('PASS '+viewport.width+' px: actor favorites, sidebar, create/rename/delete lists, membership, inline creation, reload and scoped search');
      } finally {
        for(const id of created)await page.request.post(base+'/api/lists/'+id,{data:{delete:true}}).catch(()=>{});
        for(const name of ['演员甲','演员乙'])await page.request.post(base+'/api/favorites/actors',{data:{name,favorite:false}}).catch(()=>{});
      }
      await page.close();page=null;
    }
  }catch(error){if(page)await page.screenshot({path:'artifacts/desktop-collections-failure.png',fullPage:true}).catch(()=>{});throw error;}
  finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
