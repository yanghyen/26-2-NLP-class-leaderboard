"use client";
import Link from "next/link";
import { useCallback } from "react";
import { PageHeader, LoadingState, ErrorState } from "../../../components/ui";
import { StatusBadge } from "../../../components/status-badge";
import { useApiData } from "../../../hooks/use-api-data";
import { api } from "../../../lib/api";
import { LOCAL_NOTICE, submissionIds, readPreferences } from "../../../lib/local-submissions";
import { formatDate, formatScore } from "../../../lib/format";

export default function SubmissionsPage() {
  const loader = useCallback(async () => {
    const results = await Promise.allSettled(submissionIds().map((id) => api.submission(id)));
    return { preferences: readPreferences(), rows: results.flatMap((result) => result.status === "fulfilled" ? [result.value] : []), unavailable: results.filter((r) => r.status === "rejected").length };
  }, []);
  const { data, error, loading, refresh } = useApiData(loader);
  if (loading) return <LoadingState />;
  if (error || !data) return <ErrorState message={error ?? "조회 실패"} retry={refresh} />;
  return <div className="space-y-6"><PageHeader title="이 브라우저의 제출" description={LOCAL_NOTICE} /><p>{data.preferences.emoji} {data.preferences.nickname}</p>{data.unavailable > 0 && <p role="alert">일부 기록을 조회하지 못했습니다. <button onClick={() => void refresh()}>다시 조회</button></p>}<table><thead><tr><th>모델</th><th>유형</th><th>상태</th><th>점수</th><th>시각</th></tr></thead><tbody>{data.rows.map((row) => <tr key={row.id}><td><Link href={`/submissions/${row.id}`}>{row.model_name || "모델"}</Link></td><td>{row.kind}</td><td><StatusBadge status={row.status} kind={row.kind} /></td><td>{formatScore(row.scores[0]?.primary_score)}</td><td>{formatDate(row.created_at)}</td></tr>)}</tbody></table></div>;
}
