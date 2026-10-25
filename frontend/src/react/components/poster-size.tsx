/* 海报宽度复用全站单值拉条，键盘与拖动共用边界。 */
import { useLayoutEffect, useRef } from 'react';
import { dialSliderHtml, wireDialSlider } from '@peach/legacy/ui';

export function PosterSize({ value, onChange }: { value: number; onChange(value: number): void }) {
  const root = useRef<HTMLDivElement>(null);
  const slider = useRef<ReturnType<typeof wireDialSlider> | null>(null);
  const handler = useRef(onChange);
  handler.current = onChange;
  useLayoutEffect(() => {
    const node = root.current!;
    node.innerHTML = dialSliderHtml({ value, min: 140, max: 260, step: 10, label: '海报尺寸', suffix: 'px' });
    slider.current = wireDialSlider(node, { suffix: 'px', onInput: next => handler.current(next) });
    return () => { slider.current = null; node.replaceChildren() };
  }, []);
  useLayoutEffect(() => { slider.current?.set(value) }, [value]);
  return <span data-poster-size-control=""><span>海报尺寸</span><div ref={root} /></span>;
}
