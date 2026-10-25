import { useMutation } from '@tanstack/react-query';
import { confirmModal } from '@peach/legacy/ui';
import { Button } from '@/components/base/buttons/button';
import { apiGet, apiSend, errorMessage } from '../../api';
import { useBackgroundJob } from '../background-job';
import { Note } from '../components/note';
import { TaskProgress } from '../components/task-progress';
import { queryClient } from '../query';
import { busyProps } from '../settings/busy-props';

const URL = '/api/performer-scrape';
const KEY = ['performer-scrape'] as const;
interface ScrapeState {
  status?: string; job_id?: string; checked?: number; total?: number; profiles?: number;
  avatars?: number; failed?: number; message?: string; error?: string;
  stopped?: boolean; stop_requested?: boolean;
  retry_ids?: number[]; entity_ids?: number[]; completed_ids?: number[];
  results?: { entity_id: number; name: string; message: string; retryable: boolean }[];
}
type Request = { confirmed: true; entity_ids: number[] } | { confirmed: true; all: true }
  | { confirmed: true; action: 'retry'; job_id?: string };

export function PerformerScrapeControls({ entityId, name, receipt, onComplete }: {
  entityId?: number; name?: string; receipt?(message: string): void; onComplete?(): void;
}) {
  const single = entityId !== undefined;
  const title = single ? '刮削女优资料' : '批量补全女优资料';
  const scrape = useBackgroundJob<ScrapeState, Request>({
    queryKey: KEY,
    queryFn: ({ signal }) => apiGet<ScrapeState>(URL, signal),
    start: request => apiSend<ScrapeState>(URL, request),
    onFinish: result => {
      void queryClient.invalidateQueries({ predicate: query => query.queryKey[0] !== KEY[0] });
      onComplete?.();
      receipt?.(result.error || `${result.stopped ? '已停止' : '已完成'}：补全 ${result.profiles || 0} 份档案、${result.avatars || 0} 张头像`);
    },
  });
  const stop = useMutation({
    mutationFn: () => apiSend<ScrapeState>(URL, { action: 'stop', job_id: scrape.job?.job_id }),
    onSuccess: state => { queryClient.setQueryData(KEY, state) },
  });
  const busy = scrape.running || scrape.start.isPending;
  const state = scrape.outcome || scrape.job;
  const result = state?.status === 'complete' || state?.status === 'failed' ? state : null;
  const failure = scrape.start.isError ? errorMessage(scrape.start.error)
    : stop.isError ? errorMessage(stop.error)
    : scrape.query.isError ? errorMessage(scrape.query.error) : state?.error;
  const retryable = !!state && (!!state.retry_ids?.length || (state.checked || 0) < (state.total || 0));
  const confirm = (retry = false) => {
    if (busy) return;
    void confirmModal({
      title: retry ? '重试未完成的女优' : title,
      confirmLabel: retry ? '重试' : title,
      body: `${retry ? '仅处理未完成和未取得完整结果的女优' : single ? `为${name || '这位女优'}采集头像和个人档案` : '为媒体库全部女优补全头像和个人档案'}。保留已有档案字段与手动选择的头像，影片资料与观看记录保持不变。`,
      onConfirm: () => scrape.start.mutateAsync(retry
        ? { confirmed: true, action: 'retry', job_id: state?.job_id }
        : single ? { confirmed: true, entity_ids: [entityId] } : { confirmed: true, all: true }),
    });
  };
  return <div className="flex max-w-full flex-col gap-2" data-performer-scrape="">
    <div className="flex flex-wrap items-center gap-2">
      <Button size="small" variant="secondary" {...busyProps(busy)} onClick={() => confirm()}>{busy ? '正在刮削女优资料…' : title}</Button>
      {scrape.running ? <Button size="small" variant="secondary" {...busyProps(stop.isPending || !!state?.stop_requested)}
        onClick={() => { if (!stop.isPending && !state?.stop_requested) stop.mutate() }}>
        {state?.stop_requested ? '等待当前女优处理结束…' : '停止刮削'}</Button> : null}
      {!busy && retryable ? <Button size="small" variant="secondary" onClick={() => confirm(true)}>重试未完成的女优</Button> : null}
    </div>
    {scrape.running ? <TaskProgress label={`${state?.message || '刮削女优资料'} · ${state?.checked || 0}/${state?.total || 0}`}
      value={state?.checked} total={state?.total} /> : null}
    {failure ? <Note tone="error" title="女优资料采集未完成">{failure}</Note> : null}
    {result ? <Note tone={retryable ? 'warning' : 'success'}>
      {result.stopped ? '已停止。' : '处理结束。'}补全 {result.profiles || 0} 份档案、{result.avatars || 0} 张头像。
      {retryable ? '部分资料未取得，可重试未完成的女优。' : ''}
    </Note> : null}
    {result?.results?.length ? <details className="text-caption-1-regular text-text-secondary">
      <summary>查看采集结果</summary>
      <ul>{result.results.map(person => <li key={person.entity_id}>{person.name || '已移除的女优'}：{person.message}</li>)}</ul>
    </details> : null}
  </div>;
}
