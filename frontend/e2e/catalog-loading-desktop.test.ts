import assert from 'node:assert/strict';
import { after, before, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, requiredEnv } from './harness.ts';

let browser: Browser;
before(async () => { browser = await launch() });
after(async () => { await browser?.close() });

it('桌面影片卡片独立于人物结构名单加载，延迟回调遵守导航代际', async () => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  let release = () => {};
  const gate = new Promise<void>(resolve => { release = resolve });
  try {
    const page = await context.newPage();
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => localStorage.setItem('peach.settings.v1', JSON.stringify({ detailAutoplay: false, mix: false })));
    let shapeRequested = false, itemRequested = false;
    await page.route('**/api/entity/shapes', async route => {
      shapeRequested = true;
      await gate;
      await route.fulfill({ json: { ok: true, home: { feed: false }, entities: [] } });
    });
    await page.route(url => url.pathname === '/api/items', route => {
      itemRequested = true;
      return route.fulfill({ json: { total: 1, has_more: false, items: [{
        id: 97001, name: '示例影片', code: 'PCH-001', is_jav: true, medium: 'video',
        location: 'local', duration: 120, performers: [], tags: [], has_thumb: false,
      }] } });
    });
    await page.goto(requiredEnv('PEACH_E2E_ORIGIN') + '/', { waitUntil: 'domcontentloaded' });
    await page.locator('#grid [data-media-card][data-id="97001"]').waitFor({ timeout: 8000 });
    assert.ok(shapeRequested && itemRequested);
    await page.locator('[data-nav="performers"]').click();
    await page.locator('[data-index-page="performers"]').waitFor();
    release();
    await page.waitForTimeout(200);
    assert.equal(new URL(page.url()).pathname, '/performers');
    assert.ok(await page.locator('[data-index-page="performers"]').isVisible());
    assert.equal(await page.locator('#grid [data-id="97001"]').count(), 0);
    assert.deepEqual(errors, []);
  } finally { release(); await context.close() }
});
