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

it('桌面空名册与统计页显示本地入库提示', { timeout: 60_000 }, async () => {
  const opened = await visit(browser, '/performers', desktop, async page => {
    await page.route(url => url.pathname === '/api/index', route =>
      route.fulfill({ json: { items: [], has_more: false } }));
    await page.route(url => url.pathname === '/api/stats', async route => {
      const response = await route.fetch();
      await route.fulfill({ json: { ...await response.json(), by_loc: [], by_library: [], top_tags: [], tag_sources: [] } });
    });
  });
  try {
    const { page } = opened;
    for (const path of ['/performers', '/stats']) {
      await page.goto(new URL(path, page.url()).toString(), { waitUntil: 'load' });
      await page.getByRole('heading', { name: path === '/stats' ? '还没有视频' : '还没有艺人', exact: true }).waitFor();
      await settle(page);
      assert.equal(await page.locator('a[href^="/subscriptions"], a[href="/data-cleanup"]').count(), 0);
      assert.ok(await page.getByText(path === '/stats' ? '导入本地媒体后，这里会显示馆藏统计。' : '添加内容并读取本地资料后，这里会显示对应信息。', { exact: true }).isVisible());
    }
    assert.deepEqual(opened.problems, []);
  } finally { await opened.close() }
});

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
      const video = document.querySelector<HTMLVideoElement>('#stage video.vjs-tech');
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
    await page.locator('#stage video.vjs-tech').evaluate(async (video: HTMLVideoElement) => { video.muted = true; await video.play() });
    await page.waitForFunction(() => document.querySelector<HTMLVideoElement>('#stage video.vjs-tech')!.currentTime > .25);
    const decoded = await page.locator('#stage video.vjs-tech').evaluate((video: HTMLVideoElement) => {
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

it('桌面浏览本地人物、播放列表与媒体库导入设置', { timeout: 60_000 }, async () => {
  const removedRequests: string[] = [];
  const opened = await visit(browser, '/performers', desktop, async page => {
    page.on('request', request => { const path = new URL(request.url()).pathname; if (retired.test(path)) removedRequests.push(path) });
    // 演示库没有人物实体；给名册与资料一份本地形状，页面的路由和渲染照常运行。
    await page.route(url => url.pathname === '/api/index' && url.searchParams.get('kind') === 'performers', route =>
      route.fulfill({ json: { items: [{ k: '本地艺人', entity_id: 90001, n: 0, rep: null,
        has_image: false, has_avatar: false }], has_more: false } }));
    await page.route(url => url.pathname === '/api/entity', route => route.fulfill({ json: {
      id: 90001, kind: 'performer', canonical_name: '本地艺人', asset_count: 0,
      aliases: [], user_aliases: [], tags: [], related_performers: [], links: [],
      has_image: false, has_avatar: false,
    } }));
  });
  try {
    const { page } = opened;
    await page.locator('#index [data-index-cell]').first().waitFor();
    await settle(page);
    await page.locator('#index [data-index-cell]').first().click();
    await page.locator('#index [data-entity-card]').waitFor();
    await settle(page);
    assert.equal(await page.locator('[data-media-view="online"], [data-performer-scrape], [data-entry-marks]').count(), 0);
    await page.goto(new URL('/playlists', page.url()).toString(), { waitUntil: 'load' });
    await page.locator('#stats').getByRole('heading', { name: '播放列表', exact: true }).waitFor();
    await settle(page);
    await page.goto(new URL('/settings/library', page.url()).toString(), { waitUntil: 'load' });
    await page.getByRole('button', { name: '导入本地媒体', exact: true }).waitFor();
    await settle(page);
    const sections = await page.locator('.ui-configpage > [role="tablist"] > [role="tab"]').allTextContents();
    assert.ok(sections.includes('媒体库与入库'));
    assert.equal(sections.some(section => /订阅|下载/.test(section)), false);
    assert.deepEqual(removedRequests, []);
    assert.deepEqual(opened.problems, []);
  } finally { await opened.close() }
});
