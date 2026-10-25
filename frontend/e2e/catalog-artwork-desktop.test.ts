import assert from 'node:assert/strict';
import { after, before, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, requiredEnv, settle, layout } from './harness.ts';

let browser: Browser;
before(async () => { browser = await launch() });
after(async () => { await browser?.close() });

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
