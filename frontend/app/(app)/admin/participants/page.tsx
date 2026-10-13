"use client";
import { useCallback, useState } from "react";
import { useAuth } from "../../../../components/auth-provider";
import { PageHeader, Button, LoadingState, ErrorState, inputClass } from "../../../../components/ui";
import { useApiData } from "../../../../hooks/use-api-data";
import { api, request, downloadResultsCsv } from "../../../../lib/api";
import { formatScore, formatDate } from "../../../../lib/format";
import type { ParticipantResult } from "../../../../lib/types";
export default function ParticipantsPage() {
  const { token } = useAuth();
  const [slug, setSlug] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const tasksLoader = useCallback(() => api.adminTasks(token!), [token]);
  const tasks = useApiData(tasksLoader);
  const selectedSlug = slug || tasks.data?.[0]?.slug || "";
  const loader = useCallback(() => selectedSlug ? request<ParticipantResult[]>(`/admin/tasks/${encodeURIComponent(selectedSlug)}/participants`, {}, token) : Promise.resolve([]), [selectedSlug, token]);
  const results = useApiData(loader);
  async function run(action: () => Promise<unknown>) {
    setActionError(null);
    try { await action(); await results.refresh(); } catch (caught) { setActionError(caught instanceof Error ? caught.message : "관리자 작업 실패"); }
  }
  function edit(row: ParticipantResult) {
    const nickname = window.prompt("닉네임", row.nickname);
    if (nickname === null) return;
    const emoji = window.prompt("이모지 (활성 이모지 목록에서 선택)", row.emoji);
    if (emoji === null) return;
    void run(() => request(`/admin/participants/${row.participant_id}`, { method: "PATCH", body: JSON.stringify({ nickname, emoji }) }, token));
  }
  function reset(row: ParticipantResult) {
    const id = window.prompt("동일 참가자의 성공한 Baseline 내부 ID (전체 제출 화면에서 확인)");
    if (!id || !window.confirm("기준 Baseline을 변경하면 향상량이 바뀝니다. 변경할까요?")) return;
    void run(() => request(`/admin/participants/${row.participant_id}/tasks/${encodeURIComponent(selectedSlug)}/baseline`, { method: "PUT", body: JSON.stringify({ submission_id: id }) }, token));
  }
  if (tasks.loading) return <LoadingState />;
  if (tasks.error) return <ErrorState message={tasks.error} retry={tasks.refresh} />;
  return <div className="space-y-6"><PageHeader title="참가자 결과" description="학번으로 LMS 명단과 대조하세요. 연결 정보는 확인용이며 변경·삭제하지 않습니다. 이관되지 않은 기록은 전체 제출 화면에 표시됩니다." /><select aria-label="태스크" className={inputClass} value={selectedSlug} onChange={(e) => setSlug(e.target.value)}>{tasks.data?.map((task) => <option key={task.id} value={task.slug}>{task.title}</option>)}</select><Button disabled={!selectedSlug} onClick={() => void run(() => downloadResultsCsv(token!, selectedSlug))}>관리자 CSV 다운로드</Button>{actionError && <p role="alert">{actionError}</p>}{results.error && <ErrorState message={results.error} retry={results.refresh} />}<div className="overflow-x-auto"><table><thead><tr><th>학번</th><th>닉네임</th><th>태스크</th><th>Baseline</th><th>최고 Development</th><th>향상량</th><th>전체</th><th>성공</th><th>실패</th><th>격리</th><th>마지막 제출</th><th>연결 정보</th><th>작업</th></tr></thead><tbody>{results.data?.map((row) => <tr key={row.participant_id}><td>{row.student_number}</td><td>{row.emoji} {row.nickname}</td><td>{selectedSlug}</td><td>{formatScore(row.baseline_score)}</td><td>{formatScore(row.best_development_score)}</td><td>{formatScore(row.improvement)}</td><td>{row.total_submission_count}</td><td>{row.successful_submission_count}</td><td>{row.failed_submission_count}</td><td>{row.quarantined_submission_count}</td><td>{formatDate(row.last_submitted_at)}</td><td className="text-xs">Participant: {row.participant_id}<br />Roster: {row.roster_entry_id}</td><td><Button onClick={() => edit(row)}>표시 정보 수정</Button><Button onClick={() => reset(row)}>Baseline 재설정</Button></td></tr>)}</tbody></table></div></div>;
}
