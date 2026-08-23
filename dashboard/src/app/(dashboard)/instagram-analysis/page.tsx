"use client";

import { Suspense } from 'react';
import InstagramAnalyticsDashboard from '@/components/instagram/InstagramAnalyticsDashboard';

export default function InstagramAnalysisPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-96 text-slate-400 text-sm">
          Loading Instagram dashboard...
        </div>
      }
    >
      <InstagramAnalyticsDashboard />
    </Suspense>
  );
}
