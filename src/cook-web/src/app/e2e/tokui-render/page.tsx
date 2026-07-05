'use client';

import { useSearchParams } from 'next/navigation';
import { LearnerTokuiBlock } from '@/components/tokui';

export default function TokuiE2ERenderPage() {
  const searchParams = useSearchParams();
  const shifuBid = searchParams.get('shifu_bid') || '';
  const outlineBid = searchParams.get('outline_bid') || '';

  return (
    <main
      data-testid='tokui-e2e-render-page'
      className='min-h-screen bg-white px-6 py-6'
    >
      {shifuBid && outlineBid ? (
        <LearnerTokuiBlock
          shifuBid={shifuBid}
          outlineBid={outlineBid}
          style={{ margin: '0 auto', maxWidth: 1000 }}
        />
      ) : (
        <div className='text-sm text-slate-600'>Missing TokUI E2E params</div>
      )}
    </main>
  );
}
