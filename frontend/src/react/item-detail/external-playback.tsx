import { useState } from 'react';
import { Button } from '@/components/base/buttons/button';
import { Input } from '@/components/base/input/input';
import { apiSend } from '../../api';
import { SelectField } from '../settings-panel/legacy-controls';
import { ErrorText, Help, Stack } from '../settings/section';
import { busyProps, useAction } from '../settings/use-action';

const KEY = 'peach.external-player.v1';
const MODE_KEY = 'peach.external-strm-mode.v1';
const PLAYERS = [['m3u', 'M3U 播放列表'], ['potplayer', 'PotPlayer（Windows）'], ['mpv-android', 'mpv（Android）'],
  ['vlc-ios', 'VLC（iPhone / iPad）'], ['iina', 'IINA（Mac）']] as const;
const MODES = [['direct', '302 直连'], ['proxy', 'Peach 代理']] as const;
type Mode = typeof MODES[number][0];

export function playerLink(player: string, url: string, playlist: string): string {
  if (player === 'potplayer') return `potplayer://${url}`;
  if (player === 'mpv-android') {
    const parsed = new URL(url);
    return `intent://${parsed.host}${parsed.pathname}${parsed.search}#Intent;scheme=${parsed.protocol.slice(0, -1)};type=video/any;package=is.xyz.mpv;end;`;
  }
  if (player === 'vlc-ios') return `vlc-x-callback://x-callback-url/stream?url=${encodeURIComponent(url)}`;
  if (player === 'iina') return `iina://weblink?url=${encodeURIComponent(url)}`;
  return playlist;
}

export function ExternalPlayback({ id, isStrm = false }: { id: number; isStrm?: boolean }) {
  const [player, setPlayer] = useState(() => {
    try { return PLAYERS.find(([key]) => key === localStorage.getItem(KEY))?.[0] || 'm3u' } catch { return 'm3u' }
  });
  const [strmMode, setStrmMode] = useState<Mode>(() => {
    try { return localStorage.getItem(MODE_KEY) === 'proxy' ? 'proxy' : 'direct' } catch { return 'direct' }
  });
  const mode = isStrm ? strmMode : 'proxy';
  const [links, setLinks] = useState<{ id: number; mode: Mode; url: string; playlist: string } | null>(null);
  const current = links?.id === id && links.mode === mode ? links : null;
  const action = useAction();
  return <details key={id}>
    <summary>外部播放器 / VR</summary>
    <Stack>
      {isStrm ? <>
        <SelectField id={`external-mode-${id}`} label="STRM 播放方式" options={MODES} value={mode}
          epoch={0} onPick={(value) => {
            const selected = value === 'proxy' ? 'proxy' : 'direct';
            setStrmMode(selected);
            setLinks(null);
            action.setError('');
            try { localStorage.setItem(MODE_KEY, selected) } catch { /* 浏览器未允许保存偏好。 */ }
          }} />
        <Help>{mode === 'direct' ? '播放器直接访问 STRM 地址；该地址需要能从播放器所在设备访问。'
          : '视频通过 Peach 传输；适用于播放器无法直接访问 STRM 地址的情况。'}</Help>
      </> : null}
      <SelectField id={`external-player-${id}`} label="此设备的外部播放器" options={PLAYERS} value={player}
        epoch={0} onPick={(value) => {
          const selected = PLAYERS.find(([key]) => key === value)?.[0] || 'm3u';
          setPlayer(selected);
          try { localStorage.setItem(KEY, selected) } catch { /* 浏览器未允许保存偏好。 */ }
        }} />
      <Button variant="secondary" {...busyProps(action.busy === 'prepare')}
        onClick={() => void action.run('prepare', (signal) => apiSend<{ url: string; playlist: string }>(
          `/api/external-playback?id=${id}${isStrm ? `&mode=${mode}` : ''}`, {}, 'POST', signal), (result) => setLinks({
            id, mode,
            url: new URL(result.url, location.origin).href, playlist: new URL(result.playlist, location.origin).href,
          }))}>生成播放链接</Button>
      {action.error ? <ErrorText>{action.error}</ErrorText> : null}
      {current ? <>
        <a href={playerLink(player, current.url, current.playlist)} rel="noreferrer">
          {player === 'm3u' ? '下载 M3U 播放列表' : `打开 ${PLAYERS.find(([key]) => key === player)?.[1]}`}
        </a>
        <Input label="网络播放地址" value={current.url} isReadOnly />
        <Help>链接有效期为 6 小时。VR 播放器可使用网络播放地址；另一台设备需要能访问当前 Peach 地址。</Help>
      </> : null}
      {player === 'potplayer' ? <Help>需要安装 PotPlayer 并注册 potplayer:// 协议；也可选择 M3U 播放列表。</Help> : null}
      {player === 'mpv-android' ? <Help>需要安装包名为 is.xyz.mpv 的 mpv，并使用支持 Android Intent 的浏览器。</Help> : null}
    </Stack>
  </details>;
}
