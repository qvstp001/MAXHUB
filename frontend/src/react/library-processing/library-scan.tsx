import { confirmModal } from '@peach/legacy/ui';
import { Button } from '@/components/base/buttons/button';
import { apiGet, apiSend, errorMessage } from '../../api';
import { useBackgroundJob } from '../background-job';
import { Note } from '../components/note';
import { queryClient } from '../query';
import { busyProps } from '../settings/busy-props';

const URL = '/api/library-scan';
const KEY = ['library-scan'] as const;
interface ScanState {
  status?: string; error?: string; hidden?: number; restored?: number; checked?: number;
  sources?: { online: boolean; unreadable: number }[];
}

export function LibraryScanButton({ receipt, onComplete }: { receipt?(message: string): void; onComplete?(): void }) {
  const scan = useBackgroundJob<ScanState>({
    queryKey: KEY,
    queryFn: ({ signal }) => apiGet<ScanState>(URL, signal),
    start: () => apiSend<ScanState>(URL, { confirmed: true }),
    onFinish: result => {
      // 终态也可能有已提交的来源：失败时同样重取馆藏与统计。
      void queryClient.invalidateQueries({ predicate: query => query.queryKey[0] !== KEY[0] });
      onComplete?.();
      if (result.status === 'complete') receipt?.(`已扫描媒体库，移出 ${result.hidden || 0} 部，恢复 ${result.restored || 0} 部`);
    },
  });
  const busy = scan.running || scan.start.isPending;
  const failure = scan.start.isError ? errorMessage(scan.start.error)
    : scan.query.isError ? errorMessage(scan.query.error)
    : scan.outcome?.status === 'failed' ? scan.outcome.error || '请重试扫描媒体库。' : '';
  const skipped = scan.outcome?.sources?.filter(source => !source.online || source.unreadable).length || 0;
  return (
    <div className="inline-flex max-w-full flex-wrap items-center gap-2" data-library-scan="">
      <Button size="small" variant="secondary" {...busyProps(busy)} onClick={() => {
        if (busy) return;
        void confirmModal({
          title: '扫描媒体库', confirmLabel: '扫描媒体库',
          body: '核对已登记的影片，将文件已不存在的影片移出媒体库；资料与观看记录保留。文件恢复后再次扫描可接回。',
          onConfirm: () => scan.start.mutateAsync(),
        });
      }}>{busy ? '正在扫描媒体库…' : '扫描媒体库'}</Button>
      {failure ? <Note tone="error" title="媒体库扫描未完成">{failure}</Note> : null}
      {skipped && !failure ? <Note tone="warning">{skipped} 个来源离线或部分目录不可读，相关影片已保留。</Note> : null}
    </div>
  );
}
