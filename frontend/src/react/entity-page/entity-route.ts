import { entityPath } from '@peach/legacy/core';
import { defaultSortDir, sortFromAddress } from '../../sort-preferences';
import { ENTITY_FILTER_KEYS, type EntityFilters, type EntityMedia } from './entity-page';

export const emptyEntityFilters = (kind = ''): Record<string, string> => Object.fromEntries(
  ENTITY_FILTER_KEYS.map(key => [key, key === 'sort' ? (kind === 'performer' ? 'code' : 'new')
    : key === 'dir' ? (kind === 'performer' ? 'asc' : 'desc') : '']));

/** 女优作品默认按番号升序，显式地址保留指定的列与方向。 */
export function parseEntityFilters(search: string, preference: { sort: string; dir: string }, kind = ''): EntityFilters {
  const params = new URLSearchParams(search), filters = emptyEntityFilters(kind);
  for (const key of ENTITY_FILTER_KEYS) if (key !== 'sort' && key !== 'dir') filters[key] = params.get(key) || '';
  const defaults = kind === 'performer' ? { sort: 'code', dir: 'asc' } : preference;
  return { ...filters, ...sortFromAddress(params.get('sort'), params.get('dir'), defaults.sort, defaults.dir, filters.sort) };
}

export function entityFilterSearch(filters: EntityFilters, kind = ''): string {
  const params = new URLSearchParams();
  for (const key of ENTITY_FILTER_KEYS) if (filters[key] && !(key === 'sort' && filters[key] === emptyEntityFilters(kind).sort)
    && !(key === 'dir' && filters[key] === defaultSortDir(filters.sort || ''))) params.set(key, filters[key]);
  return params.toString();
}

export function parseMediaView(search: string): EntityMedia {
  const params = new URLSearchParams(search), set = params.get('set') || '', media = params.get('media');
  return { media: media === 'photos' || media === 'online' ? media : 'videos',
    set: media === 'photos' && /^\d+$/.test(set) ? Number(set) : 0 };
}

export function entityViewSearch(filters: EntityFilters, media?: EntityMedia, kind = ''): string {
  const params = new URLSearchParams(entityFilterSearch(filters, kind));
  if (media?.media === 'photos') {
    params.set('media', 'photos');
    if (media.set) params.set('set', String(media.set));
  } else if (media?.media === 'online') params.set('media', 'online');
  return params.toString();
}

export function entityViewPath(kind: string, name: string, filters: EntityFilters, media?: EntityMedia): string {
  const search = entityViewSearch(filters, media, kind);
  return entityPath(kind, name) + (search ? `?${search}` : '');
}

/** 认领打开同一位时消费一次空筛选；深链与 POP 始终读地址。 */
export function createEntityEntryState() {
  let freshPath = '';
  return {
    fresh(kind: string, name: string): string { freshPath = entityPath(kind, name); return freshPath },
    read(kind: string, name: string, search: string, preference: { sort: string; dir: string }) {
      const fresh = freshPath === entityPath(kind, name) && !search;
      freshPath = '';
      const filters = fresh ? emptyEntityFilters(kind) : { ...parseEntityFilters(search, preference, kind) };
      if (kind === 'creator') filters.creator = '';
      return { filters, media: fresh ? { media: 'videos' as const, set: 0 } : parseMediaView(search) };
    },
  };
}
