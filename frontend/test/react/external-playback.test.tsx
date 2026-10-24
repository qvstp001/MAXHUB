import { afterEach, expect, it, vi } from 'vitest';
import { ExternalPlayback, playerLink } from '../../src/react/item-detail/external-playback';
import { click, mount, mountRoot, pending, settle } from './render';

afterEach(() => {
  localStorage.removeItem('peach.external-player.v1');
  localStorage.removeItem('peach.external-strm-mode.v1');
});

it('外部播放器只在用户请求后签发链接，并保留网络地址供 VR 播放器使用', async () => {
  const fetcher = vi.fn(async () => ({ ok: true, json: async () => ({
    url: '/external-stream/1?ticket=short', playlist: '/external-playlist/1.m3u?ticket=short',
  }) }));
  vi.stubGlobal('fetch', fetcher);
  const host = await mount(<ExternalPlayback id={1} />);
  expect(fetcher).not.toHaveBeenCalled();
  await click(Array.from(host.querySelectorAll('button')).find(button => button.textContent === '生成播放链接')!);
  await settle();
  expect(fetcher.mock.calls).toHaveLength(1);
  expect(host.querySelector('a')?.getAttribute('href')).toContain('/external-playlist/1.m3u?ticket=short');
  expect(host.querySelector('input')?.value).toContain('/external-stream/1?ticket=short');
});

it('专属协议只编码服务端播放地址', () => {
  const url = 'https://peach.example/external-stream/1?ticket=a.b';
  expect(playerLink('vlc-ios', url, '/list')).toBe(`vlc-x-callback://x-callback-url/stream?url=${encodeURIComponent(url)}`);
  expect(playerLink('iina', url, '/list')).toBe(`iina://weblink?url=${encodeURIComponent(url)}`);
  expect(playerLink('unknown', url, '/list')).toBe('/list');
});

it('PotPlayer 与 Android mpv 使用签名网络入口并保留地址参数', () => {
  for (const scheme of ['http', 'https']) {
    const url = `${scheme}://peach.example:18098/external-stream/1?ticket=a.b&origin=https%3A%2F%2Fpeach.example&mode=direct`;
    expect(playerLink('potplayer', url, '/list')).toBe(`potplayer://${url}`);
    expect(playerLink('mpv-android', url, '/list')).toBe(
      `intent://peach.example:18098/external-stream/1?ticket=a.b&origin=https%3A%2F%2Fpeach.example&mode=direct#Intent;scheme=${scheme};type=video/any;package=is.xyz.mpv;end;`,
    );
  }
});

it('STRM 外部播放按需签发直连入口', async () => {
  localStorage.removeItem('peach.external-strm-mode.v1');
  const fetcher = vi.fn<(...args: [string, RequestInit?]) => Promise<unknown>>(async () => ({ ok: true, json: async () => ({
    url: '/external-stream/1?ticket=short&mode=direct', playlist: '/external-playlist/1.m3u?ticket=short&mode=direct',
  }) }));
  vi.stubGlobal('fetch', fetcher);
  const host = await mount(<ExternalPlayback id={1} isStrm />);
  expect(fetcher).not.toHaveBeenCalled();
  await click(Array.from(host.querySelectorAll('button')).find(button => button.textContent === '生成播放链接')!);
  await settle();
  expect(String(fetcher.mock.calls[0]?.[0])).toContain('/api/external-playback?id=1&mode=direct');
  expect(host.querySelector('input')?.value).toContain('&mode=direct');
});

it('切换作品期间到达的播放链接不显示在另一作品中', async () => {
  const response = pending<{ ok: boolean; json(): Promise<unknown> }>();
  vi.stubGlobal('fetch', vi.fn(() => response.answer));
  const view = await mountRoot(<ExternalPlayback id={1} isStrm />);
  await click(Array.from(view.host.querySelectorAll('button')).find(button => button.textContent === '生成播放链接')!);
  await view.rerender(<ExternalPlayback id={2} isStrm />);
  await response.release({ ok: true, json: async () => ({ url: '/external-stream/1', playlist: '/list/1' }) });
  await settle();
  expect(view.host.querySelector('a')).toBeNull();
});

it('STRM 的代理偏好会保留，普通视频使用原文件播放入口', async () => {
  localStorage.setItem('peach.external-strm-mode.v1', 'proxy');
  const fetcher = vi.fn<(...args: [string, RequestInit?]) => Promise<unknown>>(async () => ({ ok: true, json: async () => ({
    url: '/external-stream/1?ticket=short', playlist: '/external-playlist/1.m3u?ticket=short',
  }) }));
  vi.stubGlobal('fetch', fetcher);
  const view = await mountRoot(<ExternalPlayback id={1} isStrm />);
  const generate = () => Array.from(view.host.querySelectorAll('button')).find(button => button.textContent === '生成播放链接')!;
  await click(generate());
  await settle();
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/external-playback?id=1&mode=proxy');
  await view.rerender(<ExternalPlayback id={2} />);
  await click(generate());
  await settle();
  expect(fetcher.mock.calls[1]?.[0]).toBe('/api/external-playback?id=2');
  expect(view.host.querySelector('#external-mode-2')).toBeNull();
});
