"use client";

import { Medal } from "lucide-react";
import { useCallback, useState } from "react";
import { EmptyState, ErrorState, LoadingState, PageHeader, inputClass } from "../../../components/ui";
import { useApiData } from "../../../hooks/use-api-data";
import { api } from "../../../lib/api";
import { formatDate, formatScore } from "../../../lib/format";

export default function LeaderboardPage() {
  const [slug, setSlug] = useState("");
  const tasksLoader = useCallback(() => api.tasks(), []);
  const tasksState = useApiData(tasksLoader);
  const selectedSlug = slug || tasksState.data?.[0]?.slug || "";
  const loader = useCallback(() => selectedSlug ? api.leaderboard(selectedSlug) : Promise.resolve([]), [selectedSlug]);
  const board = useApiData(loader);
  if (tasksState.loading) return <LoadingState />; if (tasksState.error || !tasksState.data) return <ErrorState message={tasksState.error ?? "태스크를 불러오지 못했습니다."} retry={tasksState.refresh} />;
  return <div className="space-y-6"><PageHeader title="Public Leaderboard" description="학생별 최고 Public score만 반영됩니다. 비공개 평가 결과와 개인정보는 표시하지 않습니다." />
    <div className="max-w-md"><select aria-label="태스크" className={inputClass} value={selectedSlug} onChange={(e) => setSlug(e.target.value)}>{tasksState.data.map((task) => <option value={task.slug} key={task.id}>{task.title}</option>)}</select></div>
    {board.loading ? <LoadingState label="순위를 계산하는 중" /> : board.error ? <ErrorState message={board.error} retry={board.refresh} /> : board.data?.length ? <div className="overflow-x-auto border border-zinc-200 bg-white"><table><thead><tr><th>순위</th><th>학생</th><th>모델</th><th>Metric</th><th>점수</th><th>Baseline</th><th>최고 Development</th><th>향상량</th><th>제출 시각</th></tr></thead><tbody>{board.data.map((row, index) => <tr key={`${row.rank}-${index}`}><td><span className="inline-flex items-center gap-2 font-bold">{row.rank <= 3 && <Medal className="h-4 w-4 text-amber-600" />}{row.rank}</span></td><td className="font-semibold">{row.avatar_emoji} {row.nickname}</td><td>{row.model_name || "-"}</td><td>{row.primary_metric}</td><td className="font-mono font-bold">{formatScore(row.primary_score)}</td><td>{formatScore(row.baseline_score)}</td><td>{formatScore(row.best_development_score)}</td><td>{formatScore(row.improvement)}</td><td>{formatDate(row.submitted_at)}</td></tr>)}</tbody></table></div> : <EmptyState title="아직 공개 점수가 없습니다" description="평가가 완료되면 학생별 최고 점수가 표시됩니다." />}
  </div>;
}
