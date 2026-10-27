/* 路由树一面一层错误边界：某一面渲染抛错只空出那一面并撤掉它的登记，别的面与 `<Routes>` 照旧；
 * 错误经根的 `onCaughtError` 交给 `reportError`，每次一条；壳下次打开能重开。
 *
 * 统计页的页面模块整个换掉，抛不抛、首屏取数成不成由 `pages` 当场决定：用例中途改它，就是
 * 「下一次打开换成好页面」。 */
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { useLocation } from 'react-router';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';

import type { CatalogFilterProps } from '../../src/react/catalog-filter/catalog-filter';
import type { ShellActions } from '../../src/react/router/shell-actions';
import type { SearchApi, SearchProps } from '../../src/react/search/search';

// 首次导入会编译路由表带进来的整棵页面子树，编译等待使用独立的有限窗口；之后每条用例重新装载只重跑模块。
const REACT_IMPORT_TIMEOUT_MS = 30_000;

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

beforeAll(async () => { await import('../../src/react/router/router') }, REACT_IMPORT_TIMEOUT_MS);

const pages = vi.hoisted(() => ({
  statsBroken: false, statsPrefetchFails: false,
}));

vi.mock('../../src/react/stats/stats-page', () => ({
  StatsPage: () => {
    if (pages.statsBroken) throw new Error('统计页画不出来');
    return <p data-stats-good>统计</p>;
  },
}));
vi.mock(import('../../src/react/stats/stats'), async (importOriginal) => ({
  ...(await importOriginal()),
  prefetchStats: async () => { if (pages.statsPrefetchFails) throw new Error('取数失败') },
}));

/** 装载时停在沉浸地址上：页面组 `path="*"` 只在不归路由树画的地址上画出 `children`。 */
async function load() {
  vi.resetModules();
  window.history.replaceState(null, '', '/nowhere');
  const [history, router, routes] = await Promise.all([
    import('../../src/history'), import('../../src/react/router/router'), import('../../src/react/router/managed-routes'),
  ]);
  return { ...history, ...router, ...routes };
}
type Loaded = Awaited<ReturnType<typeof load>>;

const unmounts: Array<() => void> = [];
afterEach(async () => {
  for (const unmount of unmounts.splice(0)) await act(async () => { unmount() });
  document.body.innerHTML = '';
  Object.assign(pages, { statsBroken: false, statsPrefetchFails: false });
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function shellActions(): ShellActions {
  return {
    openItem: vi.fn(), openEntity: vi.fn(), openTag: vi.fn(), openTasteSignal: vi.fn(), navigate: vi.fn(),
    openManage: vi.fn(), managePath: vi.fn(() => ''), openFollow: vi.fn(), receipt: vi.fn(), toast: vi.fn(),
    failure: vi.fn(), revealSource: vi.fn(async () => ''), reopenTutorial: vi.fn(async () => {}),
    requestConfigurationSection: vi.fn(), routeReview: vi.fn(),
    routeFollowManage: vi.fn(), saveFollowPreference: vi.fn(), srcBadge: () => '', routeIndex: vi.fn(),
    savePeopleLayout: vi.fn(), exitSelectMode: vi.fn(), personAvatar: vi.fn(() => ({ html: '', face: '' })),
    authorAvatar: vi.fn(() => ''), showIndexTags: vi.fn(), openFollowAuthor: vi.fn(), openFollowTag: vi.fn(),
    openPlaylist: vi.fn(), canFlip: vi.fn(() => true),
    surfaceChanged: vi.fn(), clearSearch: vi.fn(), openImmerse: vi.fn(), openOverlay: vi.fn(), closeStage: vi.fn(), grid: {} as ShellActions['grid'],
  };
}

/** 壳启动时的顺序：先画路由树，再接上取数。根的选项与 `configureRouter` 是同一份；返回根所在的容器，
 *  `children` 的标记节点画在那里面。 */
/* 页面组认不出的地址那一格：记着它看到的地址，后退前进之后还跟着变就说明 `<Routes>` 还活着。 */
function Marker() {
  return <i data-marker data-path={useLocation().pathname} />;
}

async function mount(r: Loaded): Promise<HTMLElement> {
  const el = document.createElement('div');
  const root = createRoot(el, r.ROUTER_ROOT_OPTIONS);
  await act(async () => { root.render(<r.RouterRoot actions={shellActions()}><Marker /></r.RouterRoot>) });
  unmounts.push(() => root.unmount());
  await act(async () => { r.connectManagedRoutes(Promise.resolve(r.prefetchManagedRoute)) });
  return el;
}

/** 壳铺好骨架的容器。 */
function container(id: string): HTMLElement {
  const el = document.createElement('div');
  el.id = id;
  el.innerHTML = '<div class="geist-skeleton" data-skeleton="cards">正在读取</div>';
  document.body.append(el);
  return el;
}

/** 收下每一次上报；`console.error` 只静音，不数条数。取数一律回空闲、空列表。 */
function watchReports() {
  const reported = vi.fn();
  vi.stubGlobal('reportError', reported);
  vi.spyOn(console, 'error').mockImplementation(() => {});
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ status: 'idle', items: [] }) })));
  return reported;
}

function filterProps(): CatalogFilterProps {
  return {
    tiers: { key: 'k', performers: [], studios: [] }, empty: true, tags: [], tagFirst: 0,
    views: [{ k: '', label: '全部', href: '/' }], state: '', count: { total: 0, shown: 0 }, trash: false,
    sorts: [], layout: null, refreshing: false, offscreen: false, combo: [], comboHidden: true, comboHost: null,
    actions: {
      openEntity: vi.fn(), setView: vi.fn(), toggleTag: vi.fn(), clearFilter: vi.fn(), clearAll: vi.fn(),
      setSort: vi.fn(), reshuffle: vi.fn(async () => {}), setLayout: vi.fn(), moreTops: vi.fn(async () => []),
    },
    helpers: { wireDrag: vi.fn(), wireScroller: vi.fn() },
  };
}

function searchProps(exposed: { api: SearchApi | null }): SearchProps {
  const input = document.createElement('input');
  document.body.append(input);
  return {
    input, historyLimit: 10,
    actions: { search: vi.fn(), openItem: vi.fn(), openEntity: vi.fn() },
    helpers: {
      pool: async () => [], coverHtml: () => '',
      present: (el) => { el.hidden = false }, dismiss: (el) => { el.hidden = true },
      wireScroller: () => {}, typed: () => {}, composing: () => {}, clearField: (el) => { el.value = '' },
    },
    expose: (api) => { exposed.api = api },
  };
}

const always = () => true;

async function openFilter(r: Loaded): Promise<HTMLElement> {
  const el = container('catalogFilter');
  await act(async () => {
    expect(await r.openManagedRoute('catalog-filter', filterProps(), { container: el, isCurrent: always })).toBe(true);
  });
  return el;
}

it('页面内组件渲染抛错：只空那一面、撤掉登记、上报一次，另一面与整棵树照旧', async () => {
  const reported = watchReports();
  pages.statsBroken = true;
  const r = await load();
  const tree = await mount(r);
  const filter = await openFilter(r);
  const stats = container('stats');
  await act(async () => {
    expect(await r.openManagedRoute('/stats', {}, { container: stats, isCurrent: always }),
      '首帧抛错时打开照样回 true').toBe(true);
  });

  expect(r.managedTaken(stats), '壳下次打开能重开').toBe(false);
  expect(stats.childNodes.length, '坏的那一面连宿主一起撤掉').toBe(0);
  expect(r.managedEntry(stats)).toBeNull();
  expect(r.managedEntries().map((entry) => entry.path)).toEqual(['catalog-filter']);
  expect(filter.querySelector(':scope > .peach-react [data-catalog-placeholder="performer"]'), '筛选条照画').not.toBeNull();
  expect(tree.querySelector('[data-marker]'), '整棵树没卸').not.toBeNull();
  expect(reported).toHaveBeenCalledTimes(1);
  expect(reported).toHaveBeenCalledWith(expect.objectContaining({ message: '统计页画不出来' }));
});

it('抛错之后推补丁是空操作；壳每重开一次再报一次，换成好页面就画上', async () => {
  const reported = watchReports();
  pages.statsBroken = true;
  const r = await load();
  await mount(r);
  const stats = container('stats');
  const open = () => r.openManagedRoute('/stats', {}, { container: stats, isCurrent: always });
  await act(async () => { await open() });
  expect(reported).toHaveBeenCalledTimes(1);

  await act(async () => { r.updateManagedRoute(stats, { configurable: true }) });
  expect(reported, '没画上的容器推补丁不重画').toHaveBeenCalledTimes(1);
  await act(async () => { await open() });
  expect(reported, '确定性抛错每重开一次报一次').toHaveBeenCalledTimes(2);

  pages.statsBroken = false;
  await act(async () => { expect(await open()).toBe(true) });
  expect(stats.querySelector(':scope > .peach-react [data-stats-good]')).not.toBeNull();
  expect(r.managedTaken(stats)).toBe(true);
  expect(reported).toHaveBeenCalledTimes(2);
});

it('首屏取数失败不是渲染错误：照画、不上报', async () => {
  const reported = watchReports();
  pages.statsPrefetchFails = true;
  const r = await load();
  await mount(r);
  const stats = container('stats');
  await act(async () => {
    expect(await r.openManagedRoute('/stats', {}, { container: stats, isCurrent: always })).toBe(true);
  });
  expect(stats.querySelector(':scope > .peach-react [data-stats-good]')).not.toBeNull();
  expect(r.managedTaken(stats)).toBe(true);
  expect(reported).not.toHaveBeenCalled();
});

it('一页抛错：筛选与搜索照画，后退前进照旧跟着走', async () => {
  const reported = watchReports();
  pages.statsBroken = true;
  const r = await load();
  const tree = await mount(r);
  const filter = await openFilter(r);
  const menu = container('searchMenu');
  const exposed: { api: SearchApi | null } = { api: null };
  await act(async () => {
    await r.openManagedRoute('search', searchProps(exposed), { container: menu, isCurrent: always });
  });
  const stats = container('stats');
  await act(async () => { await r.openManagedRoute('/stats', {}, { container: stats, isCurrent: always }) });

  expect(stats.childNodes.length).toBe(0);
  expect(r.managedTaken(stats)).toBe(false);
  expect(reported).toHaveBeenCalledTimes(1);
  expect(r.managedEntries().map((entry) => entry.path).sort())
    .toEqual(['catalog-filter', 'search']);
  expect(filter.querySelector('[data-catalog-placeholder="performer"]')).not.toBeNull();
  expect(menu.querySelector(':scope > .peach-react')).not.toBeNull();
  expect(exposed.api).not.toBeNull();
  expect(tree.querySelector('[data-marker]')).not.toBeNull();

  await act(async () => {
    window.history.replaceState(window.history.state, '', '/elsewhere');
    window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  });
  expect(tree.querySelector('[data-marker]')?.getAttribute('data-path'), '路由根还跟着历史走').toBe('/elsewhere');
});
