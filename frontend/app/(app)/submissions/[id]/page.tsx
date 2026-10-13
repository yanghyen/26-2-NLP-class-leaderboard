"use client";
import { useCallback } from "react";
import { useParams } from "next/navigation";
import { PageHeader, LoadingState, ErrorState, Button } from "../../../../components/ui";
import { SubmissionRetentionNotice } from "../../../../components/submission-retention-notice";
import { StatusBadge } from "../../../../components/status-badge";
import { usePolling } from "../../../../hooks/use-polling";
import { api } from "../../../../lib/api";
import { ACTIVE_STATUSES, formatDate, formatScore } from "../../../../lib/format";
import type { SubmissionDetail } from "../../../../lib/types";
const shouldPoll = (value: SubmissionDetail) => ACTIVE_STATUSES.has(value.status);
export default function SubmissionDetailPage() {
  const id = String(useParams().id);
  const loader = useCallback(() => api.submission(id), [id]);
  const { data, error, loading, refresh } = usePolling(loader, shouldPoll, 4000);
  if (loading && !data) return <LoadingState />;
  if (error && !data) return <ErrorState message={error} retry={refresh} />;
  if (!data) return null;
  return <div className="space-y-6"><PageHeader title={data.model_name || "제출 결과"} description={`제출 시각 ${formatDate(data.created_at)}`} /><p>제출 유형: {data.kind}</p>{data.kind !== "DRAFT" && <SubmissionRetentionNotice />}<StatusBadge status={data.status} kind={data.kind} /><p>평가 상태: {data.kind === "DRAFT" ? "평가 대상 아님" : data.status}</p><p>공개 점수: {formatScore(data.scores[0]?.primary_score)}</p>{data.safe_error_message && <p role="alert">{data.safe_error_message}</p>}<Button onClick={() => void refresh()}>새로고침</Button></div>;
}
