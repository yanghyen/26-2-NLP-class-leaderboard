"use client";

import { Ban, Download, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";

import { useAuth } from "../../../../components/auth-provider";
import { StatusBadge } from "../../../../components/status-badge";
import { Button, EmptyState, ErrorState, LoadingState, PageHeader, inputClass } from "../../../../components/ui";
import { useApiData } from "../../../../hooks/use-api-data";
import { api, downloadAdminFile } from "../../../../lib/api";
import { formatDate } from "../../../../lib/format";

export default function AdminSubmissionsPage() {
  const { token } = useAuth();
  const loader = useCallback(() => api.adminSubmissions(token!), [token]);
  const { data, error, loading, refresh } = useApiData(loader);
  const [filter, setFilter] = useState("ALL");
  const [studentNumber, setStudentNumber] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  async function run(action: () => Promise<unknown>, question: string) {
    if (!window.confirm(question)) return;
    setActionError(null);
    try { await action(); await refresh(); }
    catch (caught) { setActionError(caught instanceof Error ? caught.message : "작업을 완료하지 못했습니다."); }
  }
  if (loading) return <LoadingState />;
  if (error || !data) return <ErrorState message={error ?? "제출을 불러오지 못했습니다."} retry={refresh} />;
  const rows = data.filter((row) => (filter === "ALL" || row.status === filter) && (!studentNumber.trim() || row.student_number === studentNumber.trim()));
  return <div className="space-y-6">
    <PageHeader title="전체 제출" description="검증 결과와 상태를 확인하고 필요한 관리자 조치를 수행합니다." />
    <div className="max-w-xs"><select aria-label="제출 상태 필터" className={inputClass} value={filter} onChange={(event) => setFilter(event.target.value)}><option value="ALL">모든 상태</option>{Array.from(new Set(data.map((row) => row.status))).map((value) => <option key={value}>{value}</option>)}</select></div>
    <input aria-label="학번별 제출 조회" placeholder="학번으로 전체 기록 필터" className={inputClass} value={studentNumber} onChange={(event) => setStudentNumber(event.target.value)} />
    {actionError && <p role="alert" className="text-sm text-red-700">{actionError}</p>}
    {rows.length ? <div className="overflow-x-auto border border-zinc-200 bg-white"><table><thead><tr><th>제출</th><th>학번</th><th>참가자</th><th>태스크</th><th>모델</th><th>상태</th><th>검사</th><th>시각</th><th>작업</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}>
      <td className="font-mono text-xs">{row.id}</td><td>{row.student_number ?? "이관 확인 필요"}</td><td>{row.nickname}</td><td>{row.task_title}<br /><span className="font-mono text-xs text-zinc-500">{row.task_slug}</span></td><td>{row.model_name || "-"}</td><td><StatusBadge status={row.status} kind={row.kind} /></td><td>{row.malware_scan_status || "-"}</td><td>{formatDate(row.created_at)}</td>
      <td><div className="flex min-w-max gap-1">{row.artifact_cleanup_status === "deleted" ? <span className="text-xs text-zinc-500">{row.kind !== "DRAFT" && row.status === "COMPLETED" ? "평가 완료 후 자동 삭제됨" : "파일 삭제됨"} · {formatDate(row.artifact_deleted_at)}</span> : (row.artifact_cleanup_status === "pending" || (row.status === "COMPLETED" && row.kind !== "DRAFT")) ? <span className="text-xs text-amber-700">파일 정리 대기 중 · 다운로드 및 재평가 불가</span> : row.status !== "QUARANTINED" && <><Button title="Notebook 다운로드" variant="ghost" onClick={() => void downloadAdminFile(token!, row.id, "notebook").catch((caught) => setActionError(caught.message))}><Download className="h-4 w-4" /><span className="sr-only">Notebook</span></Button><Button title="모델 ZIP 다운로드" variant="ghost" onClick={() => void downloadAdminFile(token!, row.id, "model_zip").catch((caught) => setActionError(caught.message))}><Download className="h-4 w-4" /><span className="sr-only">Model ZIP</span></Button></>}<Button title="무효화" variant="ghost" onClick={() => void run(() => api.invalidateSubmission(token!, row.id), "이 제출을 무효화할까요?")}><Ban className="h-4 w-4" /></Button><Button title={row.artifact_cleanup_status !== "deleted" && (row.artifact_cleanup_status === "pending" || (row.status === "COMPLETED" && row.kind !== "DRAFT")) ? "파일 정리 재시도" : "Artifact 삭제"} disabled={row.artifact_cleanup_status === "deleted"} variant="ghost" onClick={() => void run(() => api.deleteArtifact(token!, row.id), (row.artifact_cleanup_status === "pending" || (row.status === "COMPLETED" && row.kind !== "DRAFT")) ? "점수를 유지하고 파일 정리를 다시 시도할까요?" : "파일을 영구 삭제하고 제출을 무효화할까요?")}><Trash2 className="h-4 w-4 text-red-700" /></Button></div></td>
    </tr>)}</tbody></table></div> : <EmptyState title="제출이 없습니다" description="조건에 맞는 제출이 없습니다." />}
  </div>;
}
