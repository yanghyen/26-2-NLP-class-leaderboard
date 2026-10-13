"use client";

import Link from "next/link";
import { ArrowRight, CalendarClock, Gauge } from "lucide-react";
import { useCallback } from "react";

import { EmptyState, ErrorState, LoadingState, PageHeader } from "../../../components/ui";
import { useApiData } from "../../../hooks/use-api-data";
import { api } from "../../../lib/api";
import { formatDate, STAGE_LABELS } from "../../../lib/format";

export default function TasksPage() {
  const loader = useCallback(() => api.tasks(), []);
  const { data, error, loading, refresh } = useApiData(loader);
  if (loading) return <LoadingState />;
  if (error || !data) return <ErrorState message={error ?? "태스크를 불러오지 못했습니다."} retry={refresh} />;
  return <div className="space-y-6"><PageHeader title="Tasks" description="공개된 태스크의 단계, 제출 제한, 마감 정보를 확인하세요." />{data.length ? <div className="grid gap-4 md:grid-cols-2">{data.map((task) => <Link key={task.id} href={`/tasks/${task.slug}`} className="group border border-zinc-200 bg-white p-5 hover:border-emerald-500"><div className="flex items-start justify-between gap-4"><div><span className="text-xs font-bold text-emerald-700">{STAGE_LABELS[task.stage]}</span><h2 className="mt-1 text-lg font-bold text-zinc-950">{task.title}</h2></div><ArrowRight className="h-5 w-5 text-zinc-400 group-hover:text-emerald-700" /></div><p className="mt-3 line-clamp-2 text-sm leading-6 text-zinc-600">{task.description || "상세 설명이 아직 등록되지 않았습니다."}</p><div className="mt-5 flex flex-wrap gap-4 border-t border-zinc-100 pt-4 text-xs text-zinc-600"><span className="flex items-center gap-1.5"><CalendarClock className="h-4 w-4" />{formatDate(task.dev_deadline || task.final_deadline)}</span><span className="flex items-center gap-1.5"><Gauge className="h-4 w-4" />제출 횟수 제한 없음</span></div></Link>)}</div> : <EmptyState title="공개된 태스크가 없습니다" description="담당자가 태스크를 공개한 뒤 다시 확인해 주세요." />}</div>;
}
