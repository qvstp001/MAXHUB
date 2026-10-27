import { describe, expect, it } from 'vitest';
import { getManageMenuSections, NAV_CATALOG, SIDEBAR_ITEMS } from '../../src/application/navigation-items';
import { DEFAULT_SIDEBAR_ORDER, normalizeSidebarOrder } from '../../src/sidebar';

describe('应用导航词表', () => {
  it('媒体库导航包含播放列表与人物，可选入口按偏好显示', () => {
    const keys = SIDEBAR_ITEMS.map(([key]) => key);
    expect(keys).toContain('performers');
    expect(keys).toContain('playlists');
    expect(normalizeSidebarOrder([])).toEqual(DEFAULT_SIDEBAR_ORDER);
    expect(DEFAULT_SIDEBAR_ORDER).not.toContain('immerse');
    expect(NAV_CATALOG.map(([key]) => key)).toContain('immerse');
  });

  it('每个导航身份只有一项，在线发现与采集不进入导航', () => {
    const keys = NAV_CATALOG.map(([key]) => key);
    expect(new Set(keys).size).toBe(keys.length);
    expect(keys).not.toContain('follow');
    expect(keys).not.toContain('follow-manage');
    expect(keys).not.toContain('review');
  });

  it('配置入口只在本机可改时出现在管理菜单，其余入口顺序不动', () => {
    const enabled = getManageMenuSections(true), locked = getManageMenuSections(false);
    expect(enabled.some(([key]) => key === 'configuration')).toBe(true);
    expect(locked.some(([key]) => key === 'configuration')).toBe(false);
    expect(enabled.filter(([key]) => key !== 'configuration')).toEqual(locked);
  });
});
