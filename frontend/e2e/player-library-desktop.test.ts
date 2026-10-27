import assert from 'node:assert/strict';
import { after, before, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { join } from 'node:path';
import { launch, layout, requiredEnv, settle, visit, VIEWPORTS } from './harness.ts';
import { ITEM, openItemPage } from './item-fixture.ts';

const desktop = VIEWPORTS.find(viewport => !viewport.mobile)!;
const retired = /^\/api\/(?:follow(?:\/|$)|feeds(?:\/|$)|jav(?:\/|$)|taste(?:\/|$)|review(?:\/|$)|tasks$|scraping(?:\/|$)|performer-scrape(?:\/|$)|downloads(?:\/|$))/;
let browser: Browser;
before(async () => { browser = await launch() });
after(async () => { await browser?.close() });

it('桌面媒体库保留目录与播放器，启动和详情仅请求本地馆藏', { timeout: 60_000 }, async () => {
  const opened = await openItemPage(browser, '/', desktop, { ready: '#grid [data-media-card]' });
  try {
    const { page } = opened;
    const removedRequests: string[] = [];
    page.on('request', request => { const path = new URL(request.url()).pathname; if (retired.test(path)) removedRequests.push(path) });
    await page.reload({ waitUntil: 'load' });
    await page.locator('#grid [data-media-card]').first().waitFor();
    await settle(page);
    assert.equal(await page.locator('[data-nav="follow"], [data-nav="jav"], [data-nav="review"]').count(), 0);
    assert.equal(await page.locator('a[href^="/subscriptions"]').count(), 0);
    await page.locator(`#grid [data-media-card][data-id="${ITEM.plain}"] [data-media-title]`).first().click();
    await page.locator('#stage[open] [data-item-side]').waitFor();
    await settle(page);
    assert.equal(await page.locator('#likeBtn').getAttribute('aria-label'), '收藏');
    assert.equal(await page.locator('#stageLater').getAttribute('aria-label'), '稍后看');
    assert.equal(await page.locator('#addPlaylist').getAttribute('aria-label'), '加入播放列表');
    assert.equal(await page.locator('#betterVersion, #preferenceToggle').count(), 0);
    const measured = await layout(page);
    assert.ok(measured.scrollWidth <= measured.viewportWidth + 1, JSON.stringify(measured));
    assert.deepEqual(removedRequests, []);
    assert.deepEqual(opened.problems.filter(problem => !problem.includes('VIDEOJS')), []);
  } finally { await opened.close() }
});

it('桌面设置保留海报横幅、排序和播放选项', { timeout: 60_000 }, async () => {
  const opened = await openItemPage(browser, '/', desktop, { ready: '#grid [data-media-card]' });
  try {
    const { page } = opened;
    await page.locator('#settingsBtn').click();
    await page.locator('#settingsPanel:not([hidden])').waitFor();
    await page.getByRole('tab', { name: '浏览与播放', exact: true }).click();
    await page.locator('#defaultSortSetting').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#settingsPanel').getByText('海报尺寸', { exact: true }).isVisible(), true);
    assert.equal(await page.locator('#settingsPanel').getByText('横幅尺寸', { exact: true }).isVisible(), true);
    assert.equal(await page.locator('#detailAutoplaySetting:visible').count(), 1);
    assert.equal(await page.getByText('JAV 与新作', { exact: true }).count(), 0);
    const measured = await layout(page);
    assert.ok(measured.scrollWidth <= measured.viewportWidth + 1, JSON.stringify(measured));
    assert.deepEqual(opened.problems, []);
  } finally { await opened.close() }
});

it('桌面实际解码合成视频与海报，并加载本地字幕', { timeout: 60_000 }, async () => {
  const id = requiredEnv('PEACH_E2E_ITEM');
  const opened = await visit(browser, `/assets/${id}`, desktop);
  try {
    const { page } = opened;
    await page.waitForFunction(() => {
      const video = document.querySelector<HTMLVideoElement>('#stage video');
      return video && video.readyState >= 2;
    }, undefined, { timeout: 15_000 });
    const media = await (await page.request.get(new URL('/api/items?limit=100&loc=', page.url()).toString())).json();
    const poster = media.items.find((item: { has_local_poster?: boolean }) => item.has_local_poster);
    assert.ok(poster, '演示库应提供至少一张本地海报');
    const picture = await page.evaluate(async (id) => {
      const image = new Image();
      image.src = `/poster?id=${id}`;
      await image.decode();
      return { width: image.naturalWidth, height: image.naturalHeight };
    }, String(poster.id));
    assert.ok(picture.width > 0 && picture.height > 0, JSON.stringify(picture));
    await page.locator('#stage video').evaluate(async (video: HTMLVideoElement) => { video.muted = true; await video.play() });
    await page.waitForFunction(() => document.querySelector<HTMLVideoElement>('#stage video')!.currentTime > .25);
    const decoded = await page.locator('#stage video').evaluate((video: HTMLVideoElement) => {
      video.pause(); video.currentTime = .25;
      return { width: video.videoWidth, height: video.videoHeight, error: video.error?.code ?? null };
    });
    assert.ok(decoded.width > 0 && decoded.height > 0, JSON.stringify(decoded));
    assert.equal(decoded.error, null);
    await page.locator('#stage input[type="file"][aria-label="加载字幕文件"]').setInputFiles({
      name: '本地.chs.srt', mimeType: 'text/plain',
      buffer: Buffer.from('1\n00:00:00,000 --> 00:00:02,000\n本地字幕回归\n'),
    });
    await page.locator('#stage .vjs-peach-caption-line').filter({ hasText: '本地字幕回归' }).waitFor({ timeout: 10_000 });
    await page.screenshot({ path: join(process.cwd(), '../build/player-library-desktop.png') });
    assert.deepEqual(opened.problems, []);
  } finally { await opened.close() }
});
