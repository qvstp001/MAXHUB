/* 播放列表路由的首屏、刷新代次与详情背景；在线关注地址不打开任何页面。 */
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';

import type { ShellActions } from '../../../src/react/router/shell-actions';

const REACT_IMPORT_TIMEOUT_MS = 30_000;

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

beforeAll(async () => { await import('../../../src/react/router/router') }, REACT_IMPORT_TIMEOUT_MS);

async function load(path = '/') {
  vi.resetModules();
  window.history.replaceState(null, '', path);
  const [history, router, routes, shell] = await Promise.all([
    import('../../../src/history'), import('../../../src/react/router/router'),
    import('../../../src/react/router/managed-routes'), import('../../../src/shell'),
  ]);
  // 壳的内存状态是活绑定：整份模块留着读。
  return { ...history, ...router, ...routes, shell };
}
type Loaded = Awaited<ReturnType<typeof load>>;

const unmounts: Array<() => void> = [];
afterEach(async () => {
  for (const unmount of unmounts.splice(0)) await act(async () => { unmount() });
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** 壳交进来的能力，外加一份按先后记下的页面打开过程。 */
function shellActions() {
  const log: string[] = [];
  const actions: ShellActions = {
    openItem: vi.fn(), openEntity: vi.fn(), openTag: vi.fn(), openTasteSignal: vi.fn(), navigate: vi.fn(),
    openManage: vi.fn(), managePath: vi.fn(() => ''), openFollow: vi.fn(), receipt: vi.fn(), toast: vi.fn(),
    failure: vi.fn(), revealSource: vi.fn(async () => ''), reopenTutorial: vi.fn(async () => {}),
    requestConfigurationSection: vi.fn(), routeReview: vi.fn(),
    routeFollowManage: vi.fn(), saveFollowPreference: vi.fn(), srcBadge: () => '', routeIndex: vi.fn(),
    savePeopleLayout: vi.fn(), exitSelectMode: vi.fn(), personAvatar: vi.fn(() => ({ html: '', face: '' })),
    authorAvatar: vi.fn(() => ''), showIndexTags: vi.fn(), openFollowAuthor: vi.fn(), openFollowTag: vi.fn(),
    openPlaylist: vi.fn(), canFlip: () => true,
    surfaceChanged: vi.fn((kind: string, path: string) => { log.push(`surface ${kind} ${path}`) }),
    clearSearch: vi.fn(), openImmerse: vi.fn(), openOverlay: vi.fn(), closeStage: vi.fn(),
    grid: { helpers: {}, actions: {} } as ShellActions['grid'],
  };
  return { actions, log };
}

type Reply = { ok: boolean; status: number; json(): Promise<unknown> };
const reply = (body: unknown): Reply => ({ ok: true, status: 200, json: async () => body });

const playlists = {
  items: [{
    id: 1, name: '周末连看', source_kind: 'manual', source_seed_asset_id: null, current_asset_id: null,
    created_at: '2026-09-01 10:00:00', updated_at: '2026-09-01 10:00:00', item_count: 2,
    preview_asset_id: 11, preview_ids: [11, 12], faces: [],
  }],
};

/** 播放列表的本地响应，记下每一次请求。 */
function serve() {
  const fetched = vi.fn((input: string) => {
    const path = new URL(String(input), 'http://peach.test').pathname;
    if (path !== '/api/playlists') throw new Error(`未预期的请求：${path}`);
    const body = playlists;
    return Promise.resolve(reply(body));
  });
  vi.stubGlobal('fetch', fetched);
  return (path: string) => fetched.mock.calls.filter(([input]) => new URL(String(input), 'http://peach.test').pathname === path).length;
}

function statsSurface(skeleton = '') {
  const stats = document.createElement('section');
  stats.id = 'stats';
  stats.innerHTML = skeleton;
  document.body.append(stats);
  return stats;
}

async function until(ok: () => boolean, what: string): Promise<void> {
  for (let step = 0; step < 200; step += 1) {
    if (ok()) return;
    await act(async () => { await new Promise((resolve) => { setTimeout(resolve, 0) }) });
  }
  throw new Error(`一直没等到：${what}`);
}
async function settle() {
  for (let step = 0; step < 3; step += 1) {
    await act(async () => { await new Promise((resolve) => { setTimeout(resolve, 0) }) });
  }
}

/** 挂上路由根、接上页面包，再像壳那样开始路由：启动那一次把 `pageOpens` 写成 1。 */
async function boot(r: Loaded, actions: ShellActions) {
  const root = createRoot(document.createElement('div'));
  await act(async () => { root.render(<r.RouterRoot actions={actions} />) });
  unmounts.push(() => root.unmount());
  r.connectManagedRoutes(Promise.resolve(r.prefetchManagedRoute));
  await act(async () => { r.shell.writeShell({ pageOpens: 1 }) });
  await settle();
}

/** 壳认领写地址、再要求按地址重开（`openRoutedPage`）。 */
async function openRouted(r: Loaded, path: string) {
  await act(async () => {
    r.shellNavigate(path);
    r.shell.writeShell({ pageOpens: r.shell.pageOpens + 1 });
  });
  await settle();
}

async function pop(r: Loaded, path: string, state: unknown = null) {
  await act(async () => {
    window.history.replaceState(state, '', path);
    window.dispatchEvent(new PopStateEvent('popstate', { state }));
  });
  await settle();
}

const page = (stats: Element) => stats.querySelector(':scope > .peach-react > *');
const opens = (actions: ShellActions) => vi.mocked(actions.surfaceChanged).mock.calls.length;

it('播放列表元素：按地址整页打开；停在这一页要求重读时就地推新代次重取，壳要求重开时整页重开', async () => {
  const r = await load('/playlists');
  const stats = statsSurface('');
  const calls = serve();
  const { actions, log } = shellActions();
  await boot(r, actions);
  await until(() => page(stats) !== null, '整页画上');
  expect(log).toEqual(['surface playlists /playlists']);
  expect(stats.querySelector('[data-skeleton]'), '骨架取齐之后撤下').toBeNull();
  const painted = page(stats);
  await act(async () => { r.shell.writeShell({ playlistsRevision: r.shell.playlistsRevision + 1 }) });
  await until(() => calls('/api/playlists') === 2, '按新代次重取');
  expect(page(stats), '就地推，不重挂').toBe(painted);
  expect(r.managedEntry(stats)?.props).toEqual({ revision: 1 });
  expect(opens(actions)).toBe(1);
  await openRouted(r, '/playlists');
  await until(() => calls('/api/playlists') === 3 && page(stats) !== null && page(stats) !== painted, '整页重开');
  expect(opens(actions), '再点一次侧栏整页重开').toBe(2);
});

it('播放列表作为详情背景保持原节点，关闭本地详情时不重取', async () => {
  const r = await load('/playlists');
  const stats = statsSurface();
  const calls = serve();
  const { actions } = shellActions();
  await boot(r, actions);
  await until(() => page(stats) !== null, '播放列表画上');
  const painted = page(stats);
  await act(async () => {
    r.shellNavigate('/assets/11', { state: { backgroundLocation: { pathname: '/playlists', search: '' }, overlay: 'item' } });
  });
  await settle();
  expect(page(stats)).toBe(painted);
  await act(async () => { r.shellNavigate('/playlists') });
  await settle();
  expect(page(stats)).toBe(painted);
  expect(calls('/api/playlists')).toBe(1);
});

it.each(['/follow', '/posts/2'])('地址 %s 不打开关注页面、详情或发出请求', async path => {
  const r = await load(path);
  const stats = statsSurface();
  const calls = serve();
  const { actions, log } = shellActions();
  await boot(r, actions);
  await pop(r, path);
  expect(page(stats)).toBeNull();
  expect(log).toEqual([]);
  expect(actions.openOverlay).not.toHaveBeenCalled();
  expect(actions.openFollow).not.toHaveBeenCalled();
  expect(calls('/api/follow')).toBe(0);
  expect(calls('/api/follow/credentials')).toBe(0);
  expect(r.routeMetaOf(path)).toBeNull();
});
