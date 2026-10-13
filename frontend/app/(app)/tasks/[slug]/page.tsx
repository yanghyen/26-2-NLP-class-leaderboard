"use client";

import Link from "next/link";
import { CheckCircle2, LockKeyhole } from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback } from "react";

import { EmptyState, ErrorState, LoadingState, PageHeader } from "../../../../components/ui";
import { useApiData } from "../../../../hooks/use-api-data";
import { api } from "../../../../lib/api";
import { formatBytes, formatDate, STAGE_LABELS } from "../../../../lib/format";

export default function TaskDetailPage() {
  const slug = String(useParams().slug);
  const loader = useCallback(async () => Promise.all([api.task(slug), api.leaderboard(slug)]), [slug]);
  const { data, error, loading, refresh } = useApiData(loader);
  if (loading) return <LoadingState />;
  if (error || !data) return <ErrorState message={error ?? "태스크를 불러오지 못했습니다."} retry={refresh} />;
  const [task, leaderboard] = data;
  const architectures = task.config.artifact_policy.allowed_architectures ?? [];
  return <div className="space-y-8"><PageHeader title={task.title} description={task.description || "태스크 설명이 아직 등록되지 않았습니다."} action={<Link href={`/submit?task=${task.slug}`} className="rounded-md bg-zinc-950 px-4 py-2 text-sm font-semibold text-white">이 태스크 제출</Link>} /><section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><Info label="Stage" value={STAGE_LABELS[task.stage]} /><Info label="개발 마감" value={formatDate(task.dev_deadline)} /><Info label="제출 제한" value="횟수 제한 없음" /><Info label="ZIP 제한" value={formatBytes(task.max_zip_bytes)} /></section><div className="grid gap-8 lg:grid-cols-[1fr_0.9fr]"><section className="space-y-6"><Block title="평가 설정"><p>Primary metric: <strong>{String(task.config.metric_config?.primary ?? "미정")}</strong></p><p>평가기는 서버가 제공하는 공통 evaluator만 사용합니다.</p></Block><Block title="허용 모델"><TagList values={task.config.allowed_models} empty="허용 base model이 아직 등록되지 않았습니다." /></Block><Block title="허용 architecture"><TagList values={architectures} empty="허용 architecture가 아직 등록되지 않았습니다." /></Block><Block title="제출 규칙"><ul className="space-y-2 text-sm text-zinc-700"><li className="flex gap-2"><CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-700" />Notebook과 모델 ZIP을 함께 제출합니다.</li><li className="flex gap-2"><LockKeyhole className="h-4 w-4 shrink-0 text-emerald-700" />Notebook은 저장만 하며 서버에서 실행하지 않습니다.</li><li className="flex gap-2"><LockKeyhole className="h-4 w-4 shrink-0 text-emerald-700" />실행 코드, pickle checkpoint, custom model code는 허용하지 않습니다.</li></ul></Block></section><section><h2 className="mb-3 text-lg font-bold">Public Leaderboard</h2>{leaderboard.length ? <div className="overflow-x-auto border border-zinc-200 bg-white"><table><thead><tr><th>순위</th><th>학생</th><th>점수</th></tr></thead><tbody>{leaderboard.slice(0, 10).map((row, index) => <tr key={`${row.rank}-${index}`}><td>{row.rank}</td><td>{row.avatar_emoji} {row.nickname}</td><td className="font-mono font-semibold">{row.primary_score.toFixed(4)}</td></tr>)}</tbody></table></div> : <EmptyState title="아직 점수가 없습니다" description="평가 완료 후 공개 순위가 표시됩니다." />}</section></div></div>;
}

function Info({ label, value }: { label: string; value: string }) { return <div className="border border-zinc-200 bg-white p-4"><p className="text-xs font-semibold text-zinc-500">{label}</p><p className="mt-2 text-sm font-bold text-zinc-950">{value}</p></div>; }
function Block({ title, children }: { title: string; children: React.ReactNode }) { return <section><h2 className="text-lg font-bold">{title}</h2><div className="mt-3 space-y-2 border-l-2 border-emerald-600 pl-4 text-sm leading-6 text-zinc-700">{children}</div></section>; }
function TagList({ values, empty }: { values: string[]; empty: string }) { return values.length ? <div className="flex flex-wrap gap-2">{values.map((value) => <span key={value} className="rounded border border-zinc-200 bg-zinc-50 px-2 py-1 text-xs">{value}</span>)}</div> : <p>{empty}</p>; }
