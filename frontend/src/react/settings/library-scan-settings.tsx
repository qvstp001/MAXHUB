import { Button } from '@/components/base/buttons/button';
import { apiGet, apiSend } from '../../api';
import { useBackgroundJob } from '../background-job';
import { LibraryScanButton } from '../library-processing/library-scan';
import { LIBRARY_PROCESSING_URL, LIBRARY_PROCESSING_KEY, type LibraryProcessingData } from '../library-processing/library-processing';
import { queryClient } from '../query';
import { busyProps } from './busy-props';
import { ErrorText, Help, Section, Stack } from './section';

export function LibraryScanSettings({ receipt }: { receipt(message: string): void }) {
  const job = useBackgroundJob<LibraryProcessingData>({
    queryKey: LIBRARY_PROCESSING_KEY,
    queryFn: ({ signal }) => apiGet(LIBRARY_PROCESSING_URL, signal),
    start: () => apiSend(LIBRARY_PROCESSING_URL, { stage: 'all' }),
    onFinish: result => {
      void queryClient.invalidateQueries({ queryKey: ['catalog-grid'] });
      void queryClient.invalidateQueries({ queryKey: ['index'] });
      if (result.status === 'complete') receipt('已导入本地媒体');
    },
  });
  const busy = job.running || job.start.isPending;
  return <Section title="媒体库扫描">
    <Stack>
      <Help>读取媒体目录、NFO 和本地图片，将影片加入媒体库。</Help>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" {...busyProps(busy)} onClick={() => { if (!busy) job.start.mutate() }}>
          {busy ? '正在导入媒体…' : '导入本地媒体'}
        </Button>
        <LibraryScanButton receipt={receipt} />
      </div>
      {job.running ? <Help role="status">{job.query.data?.current_action || '正在扫描媒体目录…'}</Help> : null}
      {job.start.isError || job.query.isError || job.outcome?.status === 'failed'
        ? <ErrorText>{job.outcome?.error || '媒体扫描未完成，请重试。'}</ErrorText> : null}
    </Stack>
  </Section>;
}
