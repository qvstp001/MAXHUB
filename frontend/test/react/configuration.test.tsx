import { notifyManager, QueryClientProvider } from '@tanstack/react-query';
import { act } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { CONFIGURATION_URL } from '../../src/configuration-endpoints';
import type { ConfigurationData } from '../../src/react/bundle';
import { queryClient } from '../../src/react/query';
import { CONFIGURATION_KEY, prefetchConfiguration } from '../../src/react/settings/configuration';
import { ConfigurationPage } from '../../src/react/settings/configuration-page';
import { buttonNamed, click, mount, section, settle, type } from './render';

afterEach(() => queryClient.clear());
notifyManager.setScheduler(notify => notify());
const data = (over: Partial<ConfigurationData> = {}): ConfigurationData => ({
  editable: true, notice: '', revision: 'rev-1', media_dirs: ['D:\\Media'], library_count: 1,
  port: 9123, facts: [], ...over,
});
const full = () => data({ startup: {
  available: true, enabled: false, silent: true, desktop: false, desktop_message: '', message: '',
}, peach_proxy: { mode: 'environment', proxy_saved: false, needs_selection: false },
});
const names = ['媒体库与入库', '网络与访问', '应用与维护'];
function serve(config: ConfigurationData) {
  const fetcher = vi.fn(async (url: string) => ({ ok: true, status: 200, json: async () => {
    if (url === CONFIGURATION_URL) return config;
    return { mode: 'off', status: 'idle' };
  } }));
  vi.stubGlobal('fetch', fetcher);
  return fetcher;
}
async function open(config = full(), selected?: string) {
  serve(config);
  await prefetchConfiguration(new AbortController().signal);
  return mount(<QueryClientProvider client={queryClient}>
    <ConfigurationPage receipt={vi.fn()} reopenTutorial={vi.fn()} section={selected} />
  </QueryClientProvider>);
}
const tabs = (host: ParentNode) => [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
const chosen = (host: ParentNode) => tabs(host).find(tab => tab.getAttribute('aria-selected') === 'true')!;
const press = (target: Element, key: string) => act(async () => {
  target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
});

it('Peach 配置按用途分类，媒体库与入库默认打开，各分类关联独立面板', async () => {
  const host = await open();
  expect(tabs(host).map(tab => tab.textContent)).toEqual(names);
  expect(chosen(host).textContent).toBe(names[0]);
  for (const tab of tabs(host)) {
    const panel = host.querySelector(`#${tab.getAttribute('aria-controls')}`)!;
    expect(panel.getAttribute('role')).toBe('tabpanel');
    expect(panel.getAttribute('aria-labelledby')).toBe(tab.id);
  }
  expect(host.querySelector('#configPort')?.closest('[role="tabpanel"]')?.getAttribute('aria-labelledby'))
    .toBe(tabs(host)[1]!.id);
  expect(host.textContent).not.toContain('来源与订阅');
  expect(host.textContent).not.toContain('下载渠道');
});
it('方向键首尾循环，Home 与 End 选择两端并同步焦点', async () => {
  const host = await open();
  chosen(host).focus();
  await press(chosen(host), 'ArrowUp');
  expect(chosen(host).textContent).toBe('应用与维护');
  expect(document.activeElement).toBe(chosen(host));
  await press(chosen(host), 'ArrowDown');
  expect(chosen(host).textContent).toBe('媒体库与入库');
  await press(chosen(host), 'End');
  expect(chosen(host).textContent).toBe('应用与维护');
  await press(chosen(host), 'Home');
  expect(chosen(host).textContent).toBe('媒体库与入库');
  expect(tabs(host).map(tab => tab.tabIndex)).toEqual([0, -1, -1]);
});
it('网络分区深链打开，切换分类保留未保存端口', async () => {
  const host = await open(full(), '网络与访问');
  expect(chosen(host).textContent).toBe('网络与访问');
  await type(host.querySelector<HTMLInputElement>('#configPort'), '9124');
  await click(tabs(host)[0]);
  await click(tabs(host)[1]);
  expect(host.querySelector<HTMLInputElement>('#configPort')?.value).toBe('9124');
  await act(async () => { queryClient.setQueryData(CONFIGURATION_KEY, { ...full(), revision: 'rev-2' }) });
  expect(chosen(host).textContent).toBe('网络与访问');
});
it('配置页只请求媒体库与基础设置', async () => {
  const fetcher = serve(full());
  const host = await mount(<QueryClientProvider client={queryClient}>
    <ConfigurationPage receipt={vi.fn()} reopenTutorial={vi.fn()} />
  </QueryClientProvider>);
  await settle();
  expect(host.querySelector('[role="tablist"]')).not.toBeNull();
  expect(fetcher.mock.calls.map(([url]) => url).some(url => /follow|scraping|downloads|indexers|jav-browser/.test(url))).toBe(false);
});
it('未知分区回到媒体库，只读配置省略网络表单', async () => {
  const host = await open(data({ editable: false }), '不存在');
  expect(tabs(host).map(tab => tab.textContent)).toEqual(['媒体库与入库', '应用与维护']);
  expect(chosen(host).textContent).toBe('媒体库与入库');
});
it('配置读取失败显示服务端原因', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({ message: '数据库正在迁移' }) })));
  const host = await mount(<QueryClientProvider client={queryClient}>
    <ConfigurationPage receipt={vi.fn()} reopenTutorial={vi.fn()} />
  </QueryClientProvider>);
  await settle();
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('数据库正在迁移');
  expect(host.querySelector('[role="tablist"]')).toBeNull();
});
it('挂载状态只跟随已保存路径，修改文件夹时撤下读数', async () => {
  const host = await open(data({ windows: true, media_sources: [{ location: '115', path: 'B:/', root: 'B:/', online: false }] }));
  const row = host.querySelector('[data-folder-row]')!;
  expect(row.querySelector('[data-mount="offline"]')?.textContent).toBe('离线');
  await type(row.querySelector<HTMLInputElement>('input[aria-label^="媒体目录 "]'), 'B:/Movies');
  expect(row.querySelector('[data-mount]')).toBeNull();
});
it('非 Windows 文件夹只展示媒体目录，提交时保留已有路径对应关系', async () => {
  const host = await open(data({ windows: false,
    media_sources: [{ location: 'local', path: '/old', root: 'R:\\media', library: '电影', cost: 'free' }] }));
  const row = host.querySelector('[data-folder-row]')!;
  expect(row.querySelector('details')).toBeNull();
  expect(row.querySelector('input[placeholder="自动配置"]')).toBeNull();
  await type(row.querySelector<HTMLInputElement>('input[aria-label^="媒体目录 "]'), '/new');
  await click(buttonNamed('保存配置', row.closest('form')!));
});
it('只读媒体配置可刷新挂载状态，更新共用配置快照', async () => {
  const offline = { location: '115', path: 'B:/', root: 'B:/', online: false };
  const host = await open(data({ editable: false, notice: '只在本机可改', media_sources: [offline] }));
  serve(data({ editable: false, notice: '只在本机可改', media_sources: [{ ...offline, online: true }], revision: 'rev-2' }));
  await click(buttonNamed('刷新挂载状态', host));
  await settle();
  expect(section(host, '挂载状态')?.textContent).toContain('在线');
  expect(queryClient.getQueryData<ConfigurationData>(CONFIGURATION_KEY)?.revision).toBe('rev-2');
});
