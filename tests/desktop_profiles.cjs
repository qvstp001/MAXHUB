// 本地虚构媒体服务 tests/desktop_fixture.py；只验证桌面视口。
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_BROWSER_CHANNEL||undefined});
  let page;
  try {
    page=await browser.newPage({viewport:{width:1440,height:1000},colorScheme:'light',reducedMotion:'reduce'});
    const base=process.env.MAXHUB_TEST_URL||'http://127.0.0.1:18099',errors=[],requests=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
    page.on('request',r=>requests.push(r.url()));
    const count=total=>page.waitForFunction(total=>document.querySelector('#results .results-label>span')?.textContent.startsWith(total+' 部影片')&&document.querySelectorAll('.movie-card').length===Math.min(total,60),total);
    const profile=async(name,total)=>{await page.locator('.entity-name h1').filter({hasText:name}).waitFor();await count(total);};
    const detail=async(code)=>{await page.waitForFunction(code=>document.querySelector('#detail[open] .detail-eyebrow')?.textContent===code,code);};
    const open=async(code)=>{await page.getByRole('button',{name:'查看 '+code,exact:true}).click();await detail(code);};
    await page.goto(base+'/#actors');await page.locator('.actor-card').filter({hasText:'演员甲'}).click();
    await profile('演员甲',40);
    assert.match(page.url(),/^.*#actors\?actor=/);
    assert.deepEqual(await page.locator('.entity-stats dd').allTextContents(),['40','40','41','2020 至 2024']);
    assert(await page.locator('.entity-portrait img').evaluate(image=>image.complete&&image.naturalWidth>0));
    await page.locator('.entity-refine[data-kind="studio"][data-value="厂商甲"]').click();await profile('演员甲',20);
    assert.equal(await page.locator('.entity-refine[data-kind="studio"][data-value="厂商甲"]').getAttribute('aria-pressed'),'true');
    await page.locator('.entity-refine[data-kind="tag"][data-value="收藏"]').click();await profile('演员甲',7);
    const actorAddress=page.url();await page.reload();await profile('演员甲',7);assert.equal(page.url(),actorAddress);
    await page.locator('[data-action="remove-filter"][data-kind="actor"]').click();await count(13);
    assert.equal(await page.locator('.entity-card').count(),0);
    await page.goBack();await profile('演员甲',7);
    console.log('PASS actor profile: local portrait, deduplicated stats, combinations and browser history');

    await page.locator('a.nav-link[href="#fields"]').click();await page.locator('.facet-tile').filter({hasText:'厂商甲'}).click();
    await profile('厂商甲',40);
    assert.deepEqual(await page.locator('.entity-stats dd').allTextContents(),['40','40','41','2020 至 2024']);
    assert.equal(await page.locator('.entity-portrait.company img').count(),0);
    await page.locator('.entity-refine[data-kind="actor"][data-value="演员甲"]').click();await profile('厂商甲',20);
    await page.locator('.entity-refine[data-kind="actor"][data-value="演员甲"]').click();await profile('厂商甲',40);
    await page.locator('#search').fill('DESK-000');await profile('厂商甲',1);
    await open('DESK-000');
    assert.match(await page.locator('.detail-original-title').innerText(),/Desktop fixture 000/);
    assert.match(await page.locator('.detail-facts').innerText(),/120 分钟/);
    assert.equal(await page.locator('#detail-resource option').count(),2);
    assert.match(await page.locator('.detail-cast').innerText(),/出演/);
    assert.equal(requests.filter(url=>url.includes('size=preview')).length,0);
    await page.locator('.detail-gallery summary').click();await page.locator('.gallery-thumb').first().waitFor();
    assert.equal(await page.locator('.gallery-thumb').count(),2);
    await page.getByRole('button',{name:'查看剧照 1',exact:true}).click();await page.locator('#lightbox[open]').waitFor();
    await page.keyboard.press('ArrowRight');assert.match(await page.locator('.photo-toolbar').innerText(),/剧照 2 \/ 2/);
    await page.keyboard.press('ArrowLeft');assert.match(await page.locator('.photo-toolbar').innerText(),/剧照 1 \/ 2/);
    await page.keyboard.press('Escape');await page.locator('#lightbox[open]').waitFor({state:'hidden'});await detail('DESK-000');

    const initial=await page.locator('#detail-resource').inputValue();
    await page.getByRole('button',{name:'选择播放器',exact:true}).click();await page.locator('.player-links').waitFor();
    const signed=await page.locator('#detail-player-open').getAttribute('href');
    assert.match(decodeURIComponent(signed),new RegExp('MediaSourceId='+initial));
    await page.locator('#detail-player').selectOption('link');
    assert.equal(await page.locator('#detail-player-open').isVisible(),false);
    assert.equal(await page.evaluate(()=>localStorage.getItem('maxhub.player')),'link');
    const second=await page.locator('#detail-resource option').nth(1).getAttribute('value');
    await page.locator('#detail-resource').selectOption(second);assert.equal(await page.locator('#play-panel').isVisible(),false);
    await page.getByRole('button',{name:'选择播放器',exact:true}).click();await page.locator('.player-links').waitFor();
    await page.locator('#detail-player').selectOption('potplayer');
    assert.match(decodeURIComponent(await page.locator('#detail-player-open').getAttribute('href')),new RegExp('MediaSourceId='+second));
    await page.getByRole('button',{name:'关闭详情',exact:true}).click();await open('DESK-000');
    assert.equal(await page.locator('#detail-resource').inputValue(),second);
    await page.getByRole('button',{name:'选择播放器',exact:true}).click();await page.locator('.player-links').waitFor();
    assert.equal(await page.locator('#detail-player').inputValue(),'potplayer');
    await page.getByRole('button',{name:'关闭详情',exact:true}).click();

    // 资源切换时使旧的异步播放请求失效。
    let delayed=false;
    await page.route('**/api/movies/*/play',async route=>{
      if(!delayed){delayed=true;await new Promise(resolve=>setTimeout(resolve,250));}
      await route.continue().catch(()=>{});
    });
    await open('DESK-000');await page.getByRole('button',{name:'选择播放器',exact:true}).click();
    await page.locator('#detail-resource').selectOption(initial);
    await page.waitForTimeout(400);assert.equal(await page.locator('#play-panel').isVisible(),false);
    await page.unroute('**/api/movies/*/play');
    await page.getByRole('button',{name:'选择播放器',exact:true}).click();await page.locator('.player-links').waitFor();
    assert.match(decodeURIComponent(await page.locator('#detail-player-open').getAttribute('href')),new RegExp('MediaSourceId='+initial));
    await page.locator('.detail-cast .actor-chip').click();await profile('演员甲',40);
    assert.equal(await page.locator('#detail[open]').count(),0);
    await page.goBack();await profile('厂商甲',1);
    console.log('PASS studio profile and detail: facts, roles, lazy gallery, keyboard photos, resource selection, player preference and stale-request cancellation');

    await page.locator('a.nav-link[href="#library"]').click();await count(80);
    await page.locator('#sort').selectOption('title');await count(80);await open('DESK-000');
    assert.equal(await page.getByRole('button',{name:'上一部影片',exact:true}).isEnabled(),false);
    await page.keyboard.press('ArrowRight');await detail('DESK-001');
    await page.keyboard.press('ArrowLeft');await detail('DESK-000');
    await page.locator('.detail-resource-location a').click();await count(40);
    assert.match(page.url(),/#folders/);assert.match(page.url(),/folder=/);
    await page.goBack();await count(80);

    for(const viewport of [{width:1440,height:1000},{width:1100,height:800}]) {
      await page.setViewportSize(viewport);await page.goto(base+'/#actors?actor='+encodeURIComponent('演员甲'));await profile('演员甲',40);
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      await page.locator('.poster-open').first().click();await page.locator('.detail-heading').waitFor();
      assert(await page.locator('#detail').evaluate(d=>d.scrollWidth<=d.clientWidth+1));
      assert(await page.locator('.detail-shell').evaluate(d=>d.getBoundingClientRect().right<=innerWidth));
      await page.getByRole('button',{name:'关闭详情',exact:true}).click();
    }
    assert.equal(await page.evaluate(()=>Object.values(localStorage).some(value=>value.includes('api_key=')||value.includes('MediaSourceId='))),false);
    assert.deepEqual(errors,[]);
    console.log('PASS desktop detail queue, folder navigation, direct profile URLs and 1440/1100 px layouts');
  } catch(error){if(page){console.error('Desktop profile state:',page.url());await page.screenshot({path:'artifacts/desktop-profiles-failure.png',fullPage:true}).catch(()=>{});}throw error;}
  finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
