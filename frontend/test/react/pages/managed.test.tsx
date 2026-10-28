/* 统计与配置页的路由生命周期：首屏等待、历史代次、详情背景与离页停止提交。 */
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';

import type { ShellActions } from '../../../src/react/router/shell-actions';

const REACT_IMPORT_TIMEOUT_MS = 30_000;

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

beforeAll(async () => { await import('../../../src/react/router/router') }, REACT_IMPORT_TIMEOUT_MS);
vi.mock('../../../src/react/stats/stats-page', () => ({ StatsPage: () => <p data-stats-page>馆藏统计</p> }));

async function load(path = '/') {
  vi.resetModules();
  window.history.replaceState(null, '', path);
  const [history, router, routes, shell, placeholder] = await Promise.all([
    import('../../../src/history'), import('../../../src/react/router/router'),
    import('../../../src/react/router/managed-routes'), import('../../../src/shell'),
    import('../../../src/management-placeholder'),
  ]);
  // 壳的内存状态是活绑定：整份模块留着读，展开出来的只是装载那一刻的值。
  return { ...history, ...router, ...routes, ...placeholder, shell };
}
type Loaded = Awaited<ReturnType<typeof load>>;

const unmounts: Array<() => void> = [];
afterEach(async () => {
  for (const unmount of unmounts.splice(0)) await act(async () => { unmount() });
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function shellActions(): ShellActions {
  return {
    openItem: vi.fn(), openEntity: vi.fn(), openTag: vi.fn(), openTasteSignal: vi.fn(), navigate: vi.fn(),
    openManage: vi.fn(), managePath: vi.fn(() => ''), openFollow: vi.fn(),
    receipt: vi.fn(), toast: vi.fn(), failure: vi.fn(), revealSource: vi.fn(async () => ''),
    reopenTutorial: vi.fn(async () => {}), requestConfigurationSection: vi.fn(),
    routeReview: vi.fn(), routeFollowManage: vi.fn(), saveFollowPreference: vi.fn(), srcBadge: () => '',
    routeIndex: vi.fn(), savePeopleLayout: vi.fn(), exitSelectMode: vi.fn(),
    personAvatar: vi.fn(() => ({ html: '', face: '' })), authorAvatar: vi.fn(() => ''), showIndexTags: vi.fn(),
    openFollowAuthor: vi.fn(), openFollowTag: vi.fn(), openPlaylist: vi.fn(), canFlip: () => true,
    surfaceChanged: vi.fn(), clearSearch: vi.fn(), openImmerse: vi.fn(), openOverlay: vi.fn(), closeStage: vi.fn(), grid: {} as ShellActions['grid'],
  };
}

/** 挂上路由树、接上页面包，再像壳那样开始路由：`pageOpens` 写成 1。 */
async function boot(r: Loaded, actions = shellActions()) {
  const root = createRoot(document.createElement('div'));
  await act(async () => { root.render(<r.RouterRoot actions={actions} />) });
  unmounts.push(() => root.unmount());
  r.connectManagedRoutes(Promise.resolve(r.prefetchManagedRoute));
  await act(async () => { r.shell.writeShell({ pageOpens: 1 }) });
  return { actions };
}

/** 管理区正文的容器，铺着壳冷启动时那一张骨架。 */
function surface(r: Loaded, path: string) {
  const stats = document.createElement('section');
  stats.id = 'stats';
  stats.innerHTML = r.managementSkeletonHtml(path, { followLayout: 'default', followSort: '', followDir: '' });
  document.body.append(stats);
  return { stats, skeleton: stats.firstElementChild! };
}

const statsData = {};
const configuration = {
  editable: true, notice: '', revision: 'rev-1', media_dirs: ['D:\\Media'], port: 9123, facts: [],
  startup: { available: true, enabled: false, silent: true, message: '', desktop: false, desktop_message: '' },
  peach_proxy: { mode: 'environment', proxy_saved: false, needs_selection: false },
};
type Reply = { ok: boolean; status: number; json(): Promise<unknown> };
const reply = (body: unknown): Reply => ({ ok: true, status: 200, json: async () => body });

/** 按路径回的取数替身：`deferred` 里的路径等手动兑现，表里没有的一直不回（中止时拒绝）。 */
function serve(bodies: Record<string, unknown>, deferred: string[] = []) {
  const pending: Array<() => void> = [];
  const signals = new Map<string, AbortSignal>();
  const fetched = vi.fn((input: string, init?: RequestInit) => {
    const path = input.split('?')[0]!;
    if (init?.signal) signals.set(path, init.signal);
    return new Promise<Reply>((resolve, reject) => {
      init?.signal?.addEventListener('abort', () => { reject(new DOMException('已中止', 'AbortError')) });
      if (!Object.hasOwn(bodies, path)) return;
      if (deferred.includes(path)) pending.push(() => resolve(reply(bodies[path])));
      else resolve(reply(bodies[path]));
    });
  });
  vi.stubGlobal('fetch', fetched);
  const calls = (path: string) => fetched.mock.calls.filter(([input]) => input.split('?')[0] === path).length;
  return { fetched, calls, signal: (path: string) => signals.get(path), resolve: () => { for (const settle of pending.splice(0)) settle() } };
}

async function until(ok: () => boolean, what: string): Promise<void> {
  for (let step = 0; step < 200; step += 1) {
    if (ok()) return;
    await act(async () => { await new Promise((resolve) => { setTimeout(resolve, 0) }) });
  }
  throw new Error(`一直没等到：${what}`);
}
const settle = () => act(async () => { await new Promise((resolve) => { setTimeout(resolve, 0) }) });

/** 页面画出来的那一块（宿主里的第一个元素）：重挂之后就换成另一个。 */
const painted = (stats: Element) => stats.querySelector(':scope > .peach-react > *');

it('挂上就打开：先报换页，骨架与冷启动那张同键不重画，首屏取齐才换成整页', async () => {
  const r = await load('/stats');
  const { stats, skeleton } = surface(r, '/stats');
  const order: string[] = [];
  const actions = shellActions();
  vi.mocked(actions.surfaceChanged).mockImplementation((kind, path) => { order.push(`${kind} ${path}`) });
  const api = serve({ '/api/stats': statsData }, ['/api/stats']);
  api.fetched.mockImplementationOnce(((original) => (input: string, init?: RequestInit) => {
    order.push(`fetch ${input.split('?')[0]}`);
    return original(input, init);
  })(api.fetched.getMockImplementation()!));
  await boot(r, actions);
  await until(() => api.calls('/api/stats') > 0, '首屏取数发出去');
  expect(order).toEqual(['management /stats', 'fetch /api/stats']);
  expect(stats.firstElementChild, '同一张骨架原样留着').toBe(skeleton);
  api.resolve();
  await until(() => painted(stats) !== null, '整页画上');
  expect(stats.firstElementChild).not.toBe(skeleton);
  expect(stats.textContent).toContain('馆藏统计');
});

it('没人认领的写地址一次就是打开一次：认领的写地址不重开，同一路径不认领再写就重取、重挂', async () => {
  const r = await load('/stats');
  const { stats } = surface(r, '/stats');
  const api = serve({ '/api/stats': statsData });
  await boot(r);
  await until(() => painted(stats) !== null, '第一次画上');
  const page = painted(stats);
  const revision = r.managedEntry(stats)?.revision;
  await act(async () => { r.shellNavigate('/stats?from=menu', { replace: true }) });
  await settle();
  expect([api.calls('/api/stats'), painted(stats)]).toEqual([1, page]);
  const length = window.history.length;
  await act(async () => { r.peachHistory.push('/stats') });
  await until(() => painted(stats) !== null && painted(stats) !== page, '重挂之后再画上');
  expect(api.calls('/api/stats')).toBe(2);
  expect(r.managedEntry(stats)?.revision).not.toBe(revision);
  expect(window.history.length - length).toBe(1);
});

it('详情压在上面时页面不拆也不重开，关掉详情回到这一页照旧', async () => {
  const r = await load('/stats');
  const { stats } = surface(r, '/stats');
  const api = serve({ '/api/stats': statsData });
  await boot(r);
  await until(() => painted(stats) !== null, '画上');
  const page = painted(stats);
  const overlay = { backgroundLocation: { pathname: '/stats', search: '' }, overlay: 'item' };
  await act(async () => { r.shellNavigate('/assets/7', { state: overlay }) });
  await settle();
  expect(painted(stats), '舞台下面那一页留着').toBe(page);
  await act(async () => { r.shellNavigate('/stats') });
  await settle();
  expect([painted(stats), api.calls('/api/stats')]).toEqual([page, 1]);
});

it('后退落到压在这一页上的详情才挂上（中间去过别的页）时不开；关掉详情回来按地址打开一次', async () => {
  const r = await load('/stats');
  const { stats } = surface(r, '/stats');
  const api = serve({ '/api/stats': statsData });
  await boot(r);
  await until(() => painted(stats) !== null, '画上');
  const overlay = { backgroundLocation: { pathname: '/stats', search: '' }, overlay: 'item' };
  await act(async () => { r.shellNavigate('/assets/7', { state: overlay }) });
  await settle();
  await act(async () => { r.shellNavigate('/'); stats.replaceChildren() });
  await settle();
  await act(async () => {
    window.history.replaceState({ usr: overlay, key: 'x', idx: 1 }, '', '/assets/7');
    window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  });
  await settle();
  expect([painted(stats), api.calls('/api/stats')], '被详情压着挂上不开').toEqual([null, 1]);
  await act(async () => { r.shellNavigate('/stats') });
  await until(() => painted(stats) !== null, '关掉详情后画上');
  expect(api.calls('/api/stats')).toBe(2);
});

it('走开时还露在 `#stats` 上就收起，收起排在提交之后、不报同步提交的告警；壳藏起了它就留着', async () => {
  const errors = vi.spyOn(console, 'error');
  const r = await load('/stats');
  const { stats } = surface(r, '/stats');
  serve({ '/api/stats': statsData });
  await boot(r);
  await until(() => painted(stats) !== null, '画上');
  await act(async () => { r.shellNavigate('/') });
  await settle();
  expect([stats.querySelector('.peach-react'), r.managedEntry(stats)]).toEqual([null, null]);
  expect(errors).not.toHaveBeenCalled();

  await act(async () => { r.peachHistory.push('/stats') });
  await until(() => painted(stats) !== null, '再开一次画上');
  const page = painted(stats);
  // 资料页压过来：壳在同一个任务里藏起 `#stats`，页面藏着照常活，等下一次认领表面才收。
  await act(async () => { r.shellNavigate('/performers/someone'); stats.hidden = true });
  await settle();
  expect(painted(stats)).toBe(page);
  expect(errors).not.toHaveBeenCalled();
});

it('统计首屏取数期间离开：响应回来也不占用下一页的容器', async () => {
  const r = await load('/stats');
  const { stats } = surface(r, '/stats');
  const api = serve({ '/api/stats': statsData }, ['/api/stats']);
  await boot(r);
  await until(() => api.calls('/api/stats') > 0, '统计请求发出');
  await act(async () => { r.shellNavigate('/'); stats.innerHTML = '<p data-next-page>下一页</p>' });
  api.resolve();
  await settle();
  expect(stats.querySelector('[data-next-page]')).not.toBeNull();
  expect(stats.querySelector('[data-stats-page]')).toBeNull();
  expect(r.managedEntry(stats)).toBeNull();
});

it('配置页打开时交出指定分区；画上才清除一次性请求', async () => {
  const r = await load('/settings/library');
  r.shell.writeShell({ configurationRequestedSection: '网络与访问' });
  const { stats } = surface(r, '/settings/library');
  const api = serve({ '/api/configuration': configuration, '/api/library-processing': { status: 'idle' } }, ['/api/configuration']);
  await boot(r);
  await until(() => api.calls('/api/configuration') > 0, '配置请求发出');
  expect(r.shell.configurationRequestedSection).toBe('网络与访问');
  api.resolve();
  await until(() => painted(stats) !== null, '配置画上');
  expect(r.shell.configurationRequestedSection).toBe('');
  expect(stats.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toBe('网络与访问');
});

it('在线管理与资源同步地址不认领本地管理容器，也不改写地址', async () => {
  const r = await load('/subscriptions');
  const { stats } = surface(r, '/subscriptions');
  const api = serve({});
  const { actions } = await boot(r);
  const length = window.history.length;
  for (const path of ['/subscriptions', '/follow', '/taste', '/tasks', '/resource-sync', '/data-cleanup']) {
    await act(async () => { r.shellNavigate(path, { replace: true }) });
    await settle();
    expect(location.pathname).toBe(path);
    expect(r.managedEntry(stats)).toBeNull();
  }
  expect(api.fetched).not.toHaveBeenCalled();
  expect(actions.surfaceChanged).not.toHaveBeenCalled();
  expect(window.history.length).toBe(length);
});

it('配置页入库锚点保持本地配置地址，不增加历史条目', async () => {
  const r = await load('/settings/library#libraryProcessing');
  const { stats } = surface(r, '/settings/library');
  serve({ '/api/configuration': configuration, '/api/library-processing': { status: 'idle' } });
  const length = window.history.length;
  const { actions } = await boot(r);
  await until(() => painted(stats) !== null, '媒体库配置画上');
  expect([location.pathname, location.hash, window.history.length - length]).toEqual(['/settings/library', '#libraryProcessing', 0]);
  expect(vi.mocked(actions.surfaceChanged).mock.calls.map(([, path]) => path)).toEqual(['/settings/library']);
  expect(stats.hidden).toBe(false);
});

it('网络配置页的标题、管理区身份与换一批由路由元数据登记', async () => {
  const r = await load();
  expect(r.routeMetaOf('/settings/network')).toEqual({ section: 'configuration', title: '网络与访问', refresh: 'reopen' });
  expect(r.routeMetaOf('/settings/diagnostics')).toBeNull();
});
