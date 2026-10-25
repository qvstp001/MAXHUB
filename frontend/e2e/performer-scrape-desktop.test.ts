import assert from 'node:assert/strict';
import { after, before, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, requiredEnv, settle, layout } from './harness.ts';

let browser: Browser;
before(async () => { browser = await launch() });
after(async () => { await browser?.close() });

it('桌面单人刮削确认、进度、局部失败重试和资料刷新', async () => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  try {
    const page = await context.newPage();
    const origin = requiredEnv('PEACH_E2E_ORIGIN');
    const shell = await (await page.request.get(origin + '/')).text();
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    let requestCount = 0, reads = 0, phase = 0;
    const requests: unknown[] = [];
    await page.route(url => url.pathname === '/performers/93000', route => route.fulfill({ contentType: 'text/html', body: shell }));
    await page.route(/\/api\/entity\?/, route => {
      reads++;
      return route.fulfill({ json: {
        id: 93000, kind: 'performer', canonical_name: '示例女优', asset_count: 2, aliases: [],
        display_aliases: [], user_aliases: [], tags: [], related_performers: [], links: [], metadata: {},
        has_image: false, has_avatar: false, entry_links: [], feed: null,
        profile: phase ? { height: 160 } : null,
      } });
    });
    await page.route(url => url.pathname === '/api/photos', route => route.fulfill({ json: { total: 0, sets: [], items: [], has_more: false } }));
    await page.route(url => url.pathname === '/api/items', route => route.fulfill({ json: { items: [], total: 0, has_more: false } }));
    await page.route('**/api/performer-scrape', route => {
      const id = `scrape-${phase}`;
      if (route.request().method() === 'POST') {
        requestCount++;
        requests.push(route.request().postDataJSON());
        phase++;
        return route.fulfill({ json: { status: 'running', job_id: `scrape-${phase}`, checked: 0, total: 1 } });
      }
      return route.fulfill({ json: !phase ? { status: 'idle' } : {
        status: 'complete', job_id: id, checked: 1, total: 1, profiles: 1, avatars: phase === 2 ? 1 : 0,
        retry_ids: phase === 1 ? [93000] : [], entity_ids: [93000], completed_ids: [93000],
        results: [{ entity_id: 93000, name: '示例女优', message: phase === 1 ? '头像未取得' : '头像已取得', retryable: phase === 1 }],
      } });
    });
    await page.goto(origin + '/performers/93000', { waitUntil: 'load' });
    const button = page.getByRole('button', { name: '刮削女优资料', exact: true });
    await button.click();
    await page.getByRole('dialog').getByRole('button', { name: '取消', exact: true }).click();
    assert.equal(requestCount, 0);
    await button.click();
    const dialog = page.getByRole('dialog');
    assert.match(await dialog.innerText(), /影片资料与观看记录保持不变/);
    await dialog.getByRole('button', { name: '刮削女优资料', exact: true }).click();
    const retry = page.getByRole('button', { name: '重试未完成的女优', exact: true });
    await retry.waitFor();
    await page.locator('[data-entity-facts]').getByText('T160', { exact: true }).waitFor();
    assert.ok(reads >= 2, `资料读取 ${reads} 次`);
    assert.deepEqual(requests[0], { confirmed: true, entity_ids: [93000] });
    await retry.click();
    await page.getByRole('dialog').getByRole('button', { name: '重试', exact: true }).click();
    await retry.waitFor({ state: 'detached' });
    await page.locator('[data-performer-scrape]').getByText('处理结束。补全 1 份档案、1 张头像。').waitFor();
    assert.deepEqual(requests[1], { confirmed: true, action: 'retry', job_id: 'scrape-1' });
    await settle(page);
    const geometry = await layout(page);
    assert.ok(geometry.scrollWidth <= geometry.viewportWidth + 1, JSON.stringify(geometry));
    assert.deepEqual(errors, []);
    await page.screenshot({ path: '../build/performer-scrape-desktop.png' });
  } finally { await context.close() }
});

it('桌面女优列表提供全部补全并支持停止', async () => {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  try {
    const page = await context.newPage();
    const requests: unknown[] = [];
    let started = false;
    await page.route('**/api/performer-scrape', route => {
      if (route.request().method() === 'POST') {
        const body = route.request().postDataJSON();
        requests.push(body);
        started = true;
        return route.fulfill({ json: { status: body.action === 'stop' ? 'complete' : 'running', job_id: 'batch', total: 2, checked: body.action === 'stop' ? 1 : 0, stopped: body.action === 'stop' } });
      }
      return route.fulfill({ json: started ? { status: 'running', job_id: 'batch', total: 2, checked: 0 } : { status: 'idle' } });
    });
    await page.goto(requiredEnv('PEACH_E2E_ORIGIN') + '/performers', { waitUntil: 'load' });
    await page.getByRole('button', { name: '批量补全女优资料', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: '批量补全女优资料', exact: true }).click();
    await page.getByRole('button', { name: '停止刮削', exact: true }).click();
    await page.locator('[data-performer-scrape]').getByText(/已停止。/).waitFor();
    assert.deepEqual(requests, [{ confirmed: true, all: true }, { action: 'stop', job_id: 'batch' }]);
  } finally { await context.close() }
});
