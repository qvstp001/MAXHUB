/* 统计与配置页的路由生命周期：按导航代次打开，详情保留背景，离页停止提交。 */
import { useContext, useEffect, useRef, useSyncExternalStore } from 'react';
import { useLocation } from 'react-router';

import {
  isOverlayPath, managedEntry, openManagedRoute, peachHistory, releaseManagedRoute,
  configurationSection, updateManagedRoute,
} from '@peach/history';
import {
  configurationRequestedSection, pageOpens, runtimeConfigurable, subscribeShell, writeShell,
} from '@peach/shell';

import { managementSkeletonHtml, paintManagementPlaceholder } from '../../../management-placeholder';
import { ShellActionsContext, useOpenEpoch } from '../router';
import type { ManagedOpenProps, ManagedPath, ShellActions } from '../shell-actions';

interface Run { live: boolean; revision: number }
const readStarted = () => pageOpens > 0;
const useRoutingStarted = (): boolean => useSyncExternalStore(subscribeShell, readStarted);
const scrollTop = (): void => { window.scrollTo({ top: 0, behavior: 'smooth' }) };

function openProps(path: ManagedPath): object {
  if (path === '/stats') return { configurable: !!runtimeConfigurable } satisfies ManagedOpenProps['/stats'];
  if (path.startsWith('/settings/')) {
    const section = window.location.hash === '#peachProxy' ? '网络与访问'
      : new URLSearchParams(window.location.search).get('section') || configurationRequestedSection || configurationSection(path);
    return { section } satisfies ManagedOpenProps['/settings/library'];
  }
  return {};
}

async function openPage(path: ManagedPath, actions: ShellActions, run: Run): Promise<void> {
  const stats = document.getElementById('stats');
  if (!stats) return;
  actions.surfaceChanged('management', path);
  paintManagementPlaceholder(stats, managementSkeletonHtml(path, { followLayout: '', followSort: '', followDir: '' }));
  const opened = await openManagedRoute(path, openProps(path), { container: stats, isCurrent: () => run.live });
  if (opened) run.revision = managedEntry(stats)?.revision ?? 0;
  if (!run.live) return;
  if (path.startsWith('/settings/') && opened) writeShell({ configurationRequestedSection: '' });
  if (path === '/settings/library' && window.location.hash === '#peachProxy') {
    document.getElementById('peachProxy')?.scrollIntoView({ block: 'start' });
  } else scrollTop();
}

/** 详情的背景配置页在打开和关闭覆盖层期间保持挂载。 */
export function ManagedMatch({ path }: { path: ManagedPath }) {
  const epoch = useOpenEpoch();
  useLocation();
  const covered = isOverlayPath(peachHistory.navigation.location.pathname);
  const opening = useRef<number | null>(covered ? null : epoch);
  const wasCovered = useRef(covered);
  if (!covered && (!wasCovered.current || opening.current === null)) opening.current = epoch;
  wasCovered.current = covered;
  const group = path.startsWith('/settings/') ? '/settings/configuration' : path;
  return <ManagedPage key={`${group} ${opening.current ?? 'covered'}`} path={path} covered={opening.current === null} />;
}

function ManagedPage({ path, covered }: { path: ManagedPath; covered: boolean }) {
  const actions = useContext(ShellActionsContext);
  const started = useRoutingStarted();
  const run = useRef<Run | null>(null);
  useEffect(() => {
    if (path.startsWith('/settings/')) {
      updateManagedRoute(document.getElementById('stats'), { section: configurationSection(path) });
    }
  }, [path]);
  useEffect(() => {
    if (covered || !actions || !started || run.current) return;
    const current: Run = { live: true, revision: 0 };
    run.current = current;
    queueMicrotask(() => { if (current.live) void openPage(path, actions, current) });
  }, [started]);
  useEffect(() => () => {
    const current = run.current;
    if (!current) return;
    current.live = false;
    const stats = document.getElementById('stats');
    queueMicrotask(() => {
      if (stats && current.revision && !stats.hidden && managedEntry(stats)?.revision === current.revision) releaseManagedRoute(stats);
    });
  }, []);
  return null;
}
