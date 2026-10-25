/* 合成横幅的待播图、全图浏览和正片切换。 */
import assert from 'node:assert/strict';
import { before, after, describe, it } from 'node:test';
import { join } from 'node:path';
import type { Browser } from 'playwright-core';
import { launch, requiredEnv, visit, VIEWPORTS } from './harness.ts';

describe('影片详情横幅', () => {
  let browser: Browser;
  before(async () => { browser = await launch() });
  after(async () => { await browser?.close() });
  for (const viewport of VIEWPORTS) {
    it(`${viewport.name}：横幅完整展示并可切换正片`, { timeout: 60_000 }, async () => {
      const id = requiredEnv('PEACH_E2E_ITEM');
      const opened = await visit(browser, `/assets/${id}`, viewport, async page => {
        await page.route('**/api/item?**', async route => {
          const response = await route.fetch();
          await route.fulfill({ json: { ...await response.json(), has_backdrop: true, is_jav: false } });
        });
        await page.route('**/backdrop?**', route => route.fulfill({ contentType: 'image/svg+xml',
          body: '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540"><rect width="960" height="540" fill="#182738"/><text x="60" y="280" fill="white" font-size="60">Landscape artwork</text></svg>' }));
      });
      try {
        const { page, problems } = opened;
        const video = page.locator('#stage video.vjs-tech');
        await video.waitFor({ state: 'attached' });
        assert.equal(await video.getAttribute('poster'), `/backdrop?id=${id}`);
        await page.locator('[data-jav-preview-toggle]').click();
        const picture = page.locator('[data-catalog-picture]');
        await picture.waitFor();
        await page.waitForFunction(() => document.querySelector<HTMLImageElement>('[data-catalog-picture]')?.naturalWidth === 960);
        const geometry = await picture.evaluate(node => {
          const box = node.getBoundingClientRect();
          return { fit: getComputedStyle(node).objectFit, left: box.left, right: box.right, width: innerWidth,
            overflow: document.documentElement.scrollWidth > innerWidth };
        });
        assert.equal(geometry.fit, 'contain');
        assert.ok(geometry.left >= 0 && geometry.right <= geometry.width + 1, JSON.stringify(geometry));
        assert.equal(geometry.overflow, false);
        await page.screenshot({ path: join(process.cwd(), `../build/item-backdrop-${viewport.name}.png`) });
        await page.locator('[data-follow-image-item="-2"]').click();
        assert.equal(await picture.count(), 0);
        assert.equal(await page.locator('[data-follow-image-item="-2"]').getAttribute('aria-current'), 'true');
        assert.deepEqual(problems, []);
      } finally { await opened.close() }
    });
  }
});
