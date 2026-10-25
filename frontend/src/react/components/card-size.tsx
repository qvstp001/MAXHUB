/* 视频图片宽度复用全站单值拉条，键盘与拖动共用边界。 */
import { useLayoutEffect, useRef } from 'react';
import { dialSliderHtml, wireDialSlider } from '@peach/legacy/ui';
import { CARD_SIZE_SPECS } from '../../appearance/card-size';

export function CardSize({ mode, value, onChange }: { mode: 'big' | 'small'; value: number; onChange(value: number): void }) {
  const root = useRef<HTMLDivElement>(null);
  const slider = useRef<ReturnType<typeof wireDialSlider> | null>(null);
  const handler = useRef(onChange);
  handler.current = onChange;
  useLayoutEffect(() => {
    const node = root.current!;
    node.innerHTML = dialSliderHtml({ value, ...CARD_SIZE_SPECS[mode], suffix: 'px' });
    slider.current = wireDialSlider(node, { suffix: 'px', onInput: next => handler.current(next) });
    return () => { slider.current = null; node.replaceChildren() };
  }, [mode]);
  useLayoutEffect(() => { slider.current?.set(value) }, [value]);
  return <span data-card-size-control=""><span>{CARD_SIZE_SPECS[mode].label}</span><div ref={root} /></span>;
}
