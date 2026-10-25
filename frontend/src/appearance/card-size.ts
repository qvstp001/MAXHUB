/* 视频图片的尺寸范围由拉条、数值设置和网格共同使用。 */
export const CARD_SIZE_SPECS = {
  big: { key: 'posterWidth', label: '海报尺寸', min: 140, max: 260, step: 10, fallback: 180 },
  small: { key: 'bannerWidth', label: '横幅尺寸', min: 220, max: 480, step: 10, fallback: 320 },
} as const;

export function imageWidth(mode: 'big' | 'small', settings: { posterWidth?: unknown; bannerWidth?: unknown }): number {
  const spec = CARD_SIZE_SPECS[mode];
  const value = Number(settings[spec.key]);
  return Number.isFinite(value) ? Math.min(spec.max, Math.max(spec.min, value)) : spec.fallback;
}
