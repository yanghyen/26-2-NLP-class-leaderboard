"use client";

import { ClipboardList, FileArchive, ListChecks, ShieldAlert, Users } from "lucide-react";
import { useCallback } from "react";

import { useAuth } from "../../../components/auth-provider";
import { ErrorState, LoadingState, PageHeader, Stat } from "../../../components/ui";
import { useApiData } from "../../../hooks/use-api-data";
import { api } from "../../../lib/api";
import { ACTIVE_STATUSES, submissionStatusLabel } from "../../../lib/format";

export default function AdminDashboardPage() {
  const { token } = useAuth();
  const loader = useCallback(async () => {
    const [roster, tasks, submissions, jobs, quarantine] = await Promise.all([
      api.roster(token!), api.adminTasks(token!), api.adminSubmissions(token!),
      api.jobs(token!), api.quarantine(token!)
    ]);
    return { roster, tasks, submissions, jobs, quarantine };
  }, [token]);
  const { data, error, loading, refresh } = useApiData(loader, [loader]);
  if (loading) return <LoadingState label="운영 현황을 집계하는 중" />;
  if (error || !data) return <ErrorState message={error ?? "운영 현황을 불러오지 못했습니다."} retry={refresh} />;
  return <div className="space-y-7">
    <PageHeader title="관리자 대시보드" description="수강생 등록, 제출 검증 및 평가 작업 상태를 한눈에 확인합니다." />
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <Stat label="Roster" value={data.roster.length} icon={Users} />
      <Stat label="태스크" value={data.tasks.length} icon={ClipboardList} />
      <Stat label="전체 제출" value={data.submissions.length} icon={FileArchive} />
      <Stat label="진행 Job" value={data.jobs.filter((job) => ACTIVE_STATUSES.has(job.status)).length} icon={ListChecks} />
      <Stat label="격리" value={data.quarantine.length} icon={ShieldAlert} />
    </div>
    <section><h2 className="mb-3 text-lg font-bold">최근 제출</h2><div className="overflow-x-auto border border-zinc-200 bg-white"><table><thead><tr><th>ID</th><th>모델</th><th>상태</th><th>시각</th></tr></thead><tbody>{data.submissions.slice(0, 8).map((row) => <tr key={row.id}><td className="font-mono text-xs">{row.id}</td><td>{row.model_name || "-"}</td><td>{submissionStatusLabel(row.kind, row.status)}</td><td>{new Date(row.created_at).toLocaleString("ko-KR")}</td></tr>)}</tbody></table></div></section>
  </div>;
}
