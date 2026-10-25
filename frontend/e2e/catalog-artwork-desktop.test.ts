import assert from 'node:assert/strict';
import { after, before, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, requiredEnv, settle, layout } from './harness.ts';

let browser: Browser;
before(async () => { browser = await launch() });
after(async () => { await browser?.close() });

it('桌面海报铺满卡框，版式图标表示方向，扫描后重读馆藏', async () => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  try {
    const page = await context.newPage();
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => localStorage.setItem('peach.settings.v1', JSON.stringify({
      detailAutoplay: false, homeLayout: 'big', posterWidth: 180, mix: false,
    })));
    let scanned = false, starts = 0;
    await page.route('**/api/library-scan', route => {
      if (route.request().method() === 'POST') {
        starts++;
        assert.deepEqual(route.request().postDataJSON(), { confirmed: true });
        scanned = true;
        return route.fulfill({ json: { status: 'running', job_id: 'scan-test' } });
      }
      return route.fulfill({ json: scanned
        ? { status: 'complete', job_id: 'scan-test', checked: 3, hidden: 2, restored: 0, sources: [] }
        : { status: 'idle' } });
    });
    await page.route('**/api/items?*', route => route.fulfill({ json: {
      items: Array.from({ length: scanned ? 1 : 3 }, (_, i) => ({
        id: 92000 + i, name: `示例影片 ${i}`, title: `示例影片 ${i}`, code: `PCH-${i + 1}`, is_jav: true,
        has_cover: i !== 1, has_local_poster: true, has_thumb: true, medium: 'video', location: 'local',
        ...(i === 2 ? { poster_box: { x0: 833, y0: 0, x1: 1500, y1: 1000, px: [1500, 1000], method: 'manual' } } : {}),
        duration: 120, width: 1920, height: 1080, performers: [], tags: [],
      })), total: scanned ? 1 : 3, has_more: false,
    } }));
    for (const endpoint of ['cover', 'poster']) await page.route(`**/${endpoint}?*`, route => route.fulfill({
      contentType: 'image/svg+xml', body: route.request().url().includes('PCH-3')
        ? '<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="1000"><rect width="1500" height="1000" fill="red"/><rect x="833" width="667" height="1000" fill="tan"/></svg>'
        : '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="1000"><rect width="600" height="1000" fill="tan"/></svg>',
    }));
    await page.goto(requiredEnv('PEACH_E2E_ORIGIN') + '/', { waitUntil: 'load' });
    assert.equal(await page.locator('[data-nav="performers"]').getAttribute('aria-label'), '女优');
    for (const [name, glyph] of [['海报', 'rectangle-vertical'], ['横幅', 'rectangle-horizontal']]) {
      const segment = page.locator('[data-glass-segment]', { has: page.getByRole('radio', { name, exact: true }) });
      assert.equal(await segment.locator('use').getAttribute('href'), `#i-${glyph}`);
    }
    const images = page.locator('#grid [data-media-card] [data-media-art] img');
    await images.first().waitFor();
    assert.equal(await images.count(), 3);
    for (const img of await images.all()) {
      await img.evaluate((node: HTMLImageElement) => node.decode());
      if (!(await img.getAttribute('class'))?.includes('panel'))
        assert.equal(await img.evaluate(node => getComputedStyle(node).objectFit), 'cover');
      const picture = img.locator('xpath=../..');
      const pixels = await page.evaluate(async encoded => {
        const image = new Image(); image.src = `data:image/png;base64,${encoded}`; await image.decode();
        const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
        const ctx = canvas.getContext('2d')!; ctx.drawImage(image, 0, 0);
        return [4, image.width - 5].map(x => Array.from(ctx.getImageData(x, Math.floor(image.height / 2), 1, 1).data));
      }, (await picture.screenshot()).toString('base64'));
      for (const pixel of pixels) assert.ok(pixel[0]! > 150 && pixel[1]! > 100, JSON.stringify(pixels));
    }
    const button = page.getByRole('button', { name: '扫描媒体库', exact: true });
    await page.screenshot({ path: '../build/library-scan-desktop.png' });
    await button.click();
    await page.getByRole('dialog').getByRole('button', { name: '取消', exact: true }).click();
    assert.equal(starts, 0);
    await button.click();
    await page.getByRole('dialog').getByRole('button', { name: '扫描媒体库', exact: true }).click();
    await page.locator('#grid [data-media-card][data-id="92001"]').waitFor({ state: 'detached' });
    assert.equal(starts, 1);
    assert.equal(await page.locator('#grid [data-media-card]').count(), 1);
    await settle(page);
    const geometry = await layout(page);
    assert.ok(geometry.scrollWidth <= geometry.viewportWidth + 1, JSON.stringify(geometry));
    assert.deepEqual(errors, []);
  } finally { await context.close() }
});

it('桌面女优作品默认按番号升序，显式排序支持刷新与历史导航', async () => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  try {
    const page = await context.newPage();
    const origin = requiredEnv('PEACH_E2E_ORIGIN');
    const shell = await (await page.request.get(origin + '/')).text();
    await page.route(url => url.pathname === '/performers/93000', route => route.fulfill({
      contentType: 'text/html', body: shell,
    }));
    const name = '示例女优';
    await page.route(/\/api\/entity\?/, route => route.fulfill({ json: {
      id: 93000, kind: 'performer', canonical_name: name, asset_count: 2, aliases: [],
      display_aliases: [], user_aliases: [], tags: [], related_performers: [], links: [],
      metadata: {}, has_image: false, has_avatar: false, entry_links: [], feed: null,
    } }));
    await page.route(url => url.pathname === '/api/photos', route => route.fulfill({
      json: { total: 0, sample_total: 0, sets: [], items: [], has_more: false },
    }));
    await page.route(url => url.pathname === '/api/items', route => route.fulfill({ json: {
      items: [1, 2].map(i => ({ id: 93000 + i, name: `示例 ${i}`, code: `PCH-${i}`, is_jav: true,
        medium: 'video', location: 'local', duration: 120, performers: [], tags: [] })),
      total: 2, has_more: false,
    } }));
    await page.addInitScript(() => localStorage.setItem('peach.settings.v1', JSON.stringify({
      detailAutoplay: false, defaultSort: 'rating', defaultSortDirection: 'desc',
    })));
    const requests: URL[] = [];
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.pathname === '/api/items' && url.searchParams.has('performer')) requests.push(url);
    });
    const address = origin + '/performers/93000';
    await page.goto(address, { waitUntil: 'load' });
    const code = page.locator('#index [data-entity-sort="code"]');
    await code.waitFor();
    await settle(page);
    assert.ok(requests.length > 0);
    assert.equal(requests[0]!.searchParams.get('sort'), 'code');
    assert.equal(requests[0]!.searchParams.get('dir'), 'asc');
    assert.equal(await code.getAttribute('aria-pressed'), 'true');
    await page.locator('#index [data-entity-sort="rating"]').click();
    await page.waitForURL('**/*sort=rating*');
    await page.reload({ waitUntil: 'load' });
    await page.locator('#index [data-entity-sort="rating"][aria-pressed="true"]').waitFor();
    await page.goto(address, { waitUntil: 'load' });
    await code.waitFor();
    await settle(page);
    assert.equal(await code.getAttribute('aria-pressed'), 'true');
    assert.equal(requests.at(-1)!.searchParams.get('sort'), 'code');
    await page.goBack();
    await page.locator('#index [data-entity-sort="rating"][aria-pressed="true"]').waitFor();
  } finally { await context.close() }
});

it('桌面首页横幅、海报尺寸和排序可以切换并保存', async () => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  try {
    const page = await context.newPage();
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const requests: URL[] = [];
    await page.addInitScript(() => {
      if (!localStorage.getItem('peach.settings.v1')) localStorage.setItem('peach.settings.v1', JSON.stringify({
        detailAutoplay: false, homeLayout: 'small', posterWidth: 180,
      }));
    });
    await page.route('**/api/items?*', route => {
      requests.push(new URL(route.request().url()));
      return route.fulfill({ json: { items: Array.from({ length: 20 }, (_, i) => ({
        id: 91000 + i, name: `示例影片 ${i}`, title: `示例影片 ${i}`, code: `PCH-${i + 1}`, is_jav: true,
        has_backdrop: true, has_cover: true, has_thumb: true, medium: 'video', location: 'local',
        duration: 120, width: 1920, height: 1080, performers: [], tags: [],
      })), total: 20, has_more: false } });
    });
    for (const endpoint of ['backdrop', 'cover', 'poster']) await page.route(`**/${endpoint}?*`, route => route.fulfill({
      contentType: 'image/svg+xml', body: `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="539"><rect width="800" height="539" fill="${endpoint === 'backdrop' ? 'navy' : 'tan'}"/></svg>`,
    }));
    await page.goto(requiredEnv('PEACH_E2E_ORIGIN') + '/', { waitUntil: 'load' });
    const picture = page.locator('#grid [data-media-card] [data-media-pic]').first();
    await picture.locator('img[data-backdrop-image]').waitFor();
    await picture.locator('img').evaluate((node: HTMLImageElement) => node.decode());
    assert.equal(await picture.locator('img').evaluate(node => getComputedStyle(node).objectFit), 'cover');
    const pixels = await page.evaluate(async encoded => {
      const img = new Image();
      img.src = `data:image/png;base64,${encoded}`;
      await img.decode();
      const canvas = document.createElement('canvas');
      canvas.width = img.width; canvas.height = img.height;
      const ctx = canvas.getContext('2d')!;
      ctx.drawImage(img, 0, 0);
      return [4, img.width - 5].map(x => Array.from(ctx.getImageData(x, Math.floor(img.height / 2), 1, 1).data));
    }, (await picture.screenshot()).toString('base64'));
    for (const pixel of pixels) assert.ok(pixel[2]! > 80, JSON.stringify(pixels));
    const ratio = await picture.evaluate(node => node.clientWidth / node.clientHeight);
    assert.ok(Math.abs(ratio - 16 / 9) < .02, String(ratio));
    const bannerSlider = page.getByRole('slider', { name: '横幅尺寸', exact: true });
    await bannerSlider.focus();
    for (const [key, expected] of [['End', 480], ['Home', 220], ['ArrowRight', 230]] as const) {
      await bannerSlider.press(key);
      await page.waitForFunction(value => document.querySelector('[data-card-size-control] [role=slider]')?.getAttribute('aria-valuenow') === String(value), expected);
      const box = await picture.boundingBox();
      assert.ok(box && Math.abs(box.width - expected) < 1, JSON.stringify(box));
      assert.ok(box && Math.abs(box.width / box.height - 16 / 9) < .02, JSON.stringify(box));
    }
    await page.locator('[data-glass-segment]', { has: page.getByRole('radio', { name: '海报', exact: true }) }).click();
    await picture.locator('img[data-jav-image]').waitFor();
    const slider = page.getByRole('slider', { name: '海报尺寸', exact: true });
    await slider.focus();
    await slider.press('End');
    await page.waitForFunction(() => document.querySelector('[data-card-size-control] [role=slider]')?.getAttribute('aria-valuenow') === '260');
    const size = await picture.boundingBox();
    assert.ok(size && size.width <= 260.5 && size.width > 250, JSON.stringify(size));
    await slider.press('Home');
    await page.waitForFunction(() => document.querySelector('[data-card-size-control] [role=slider]')?.getAttribute('aria-valuenow') === '140');
    await page.reload({ waitUntil: 'load' });
    await page.getByRole('slider', { name: '海报尺寸', exact: true }).waitFor();
    assert.equal(await page.getByRole('slider', { name: '海报尺寸', exact: true }).getAttribute('aria-valuenow'), '140');
    for (const key of ['code', 'name']) {
      const response = page.waitForResponse(response => {
        const url = new URL(response.url());
        return url.pathname === '/api/items' && url.searchParams.get('sort') === key;
      });
      await page.locator(`[data-entity-sort="${key}"]`).click();
      const url = new URL((await response).url());
      assert.equal(url.searchParams.get('dir'), 'asc');
    }
    await page.locator('[data-glass-segment]', { has: page.getByRole('radio', { name: '横幅', exact: true }) }).click();
    await picture.locator('img[data-backdrop-image]').waitFor();
    assert.equal(await bannerSlider.getAttribute('aria-valuenow'), '230');
    await page.reload({ waitUntil: 'load' });
    await bannerSlider.waitFor();
    assert.equal(await bannerSlider.getAttribute('aria-valuenow'), '230');
    const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('peach.settings.v1')!));
    assert.equal(saved.bannerWidth, 230);
    assert.equal(saved.posterWidth, 140);
    await settle(page);
    const geometry = await layout(page);
    assert.ok(geometry.scrollWidth <= geometry.viewportWidth + 1, JSON.stringify(geometry));
    assert.deepEqual(errors, []);
    assert.ok(requests.length > 0);
  } finally { await context.close() }
});
