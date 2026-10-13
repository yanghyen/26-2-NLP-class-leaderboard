"use client";

import { FileArchive, FileCode2, UploadCloud } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { readPreferences, savePreferences, rememberSubmission } from "../../../lib/local-submissions";
import { Button, ErrorState, Field, LoadingState, PageHeader, inputClass } from "../../../components/ui";
import { useApiData } from "../../../hooks/use-api-data";
import { api, uploadSubmission } from "../../../lib/api";
import { formatBytes, STAGE_LABELS } from "../../../lib/format";
import type { SubmissionKind } from "../../../lib/types";

export default function SubmitPage() {
  const [studentNumber, setStudentNumber] = useState("");
  const [nickname, setNickname] = useState("");
  const [emoji, setEmoji] = useState("🧠");
  const [kind, setKind] = useState<SubmissionKind>("EVALUATION");
  useEffect(() => { const saved = readPreferences(); setStudentNumber(saved.studentNumber); setNickname(saved.nickname); setEmoji(saved.emoji); }, []);
  const router = useRouter();
  const loader = useCallback(() => Promise.all([api.tasks(), api.avatars()]), []);
  const { data, error, loading, refresh } = useApiData(loader);
  const [taskSlug, setTaskSlug] = useState(() => typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("task") ?? "");
  const [modelName, setModelName] = useState("");
  const [baseModel, setBaseModel] = useState("");
  const [summary, setSummary] = useState("");
  const [notebook, setNotebook] = useState<File | null>(null);
  const [modelZip, setModelZip] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const selectedSlug = taskSlug || data?.[0][0]?.slug || "";
  const task = data?.[0].find((row) => row.slug === selectedSlug);

  async function submit(event: FormEvent, kind: SubmissionKind) {
    event.preventDefault();
    if (progress !== null) return;
    if (!task || !notebook || !modelZip) return setFormError("Notebook과 모델 ZIP을 모두 선택해 주세요.");
    if (!notebook.name.toLowerCase().endsWith(".ipynb")) return setFormError("Notebook은 .ipynb 파일만 제출할 수 있습니다.");
    if (!modelZip.name.toLowerCase().endsWith(".zip")) return setFormError("모델은 .zip 파일만 제출할 수 있습니다.");
    if (modelZip.size > task.max_zip_bytes) return setFormError(`모델 ZIP은 ${formatBytes(task.max_zip_bytes)} 이하여야 합니다.`);
    setFormError(null);
    setProgress(0);
    try {
      const result = await uploadSubmission(task.slug, { studentNumber, nickname, emoji, kind, modelName, baseModel, summary, notebook, modelZip }, setProgress);
      savePreferences({ studentNumber, nickname, emoji });
      rememberSubmission(result.submission.id);
      router.push(`/submissions/${result.submission.id}`);
    } catch (caught) {
      setFormError(caught instanceof Error ? caught.message : "제출하지 못했습니다.");
      setProgress(null);
    }
  }
  if (loading) return <LoadingState label="제출 환경을 확인하는 중" />;
  if (error || !data) return <ErrorState message={error ?? "제출 정보를 불러오지 못했습니다."} retry={refresh} />;
  return <div className="space-y-7"><PageHeader title="새 제출" description="Notebook은 서버에서 실행하지 않으며 평가 성공 후 자동 삭제됩니다. 모델은 안전 검사를 통과한 safetensors artifact만 평가됩니다." />
    <form className="space-y-7" onSubmit={(event) => void submit(event, kind)}>
      <section className="grid gap-5 border border-zinc-200 bg-white p-5 sm:grid-cols-2">
        <Field label="태스크"><select className={inputClass} value={selectedSlug} onChange={(e) => setTaskSlug(e.target.value)}>{data[0].map((row) => <option key={row.id} value={row.slug}>{row.title} · {STAGE_LABELS[row.stage]}</option>)}</select></Field>
        <Field label="학번"><input aria-label="학번" className={inputClass} value={studentNumber} onChange={(e) => setStudentNumber(e.target.value)} required maxLength={64} /></Field>
        <p className="text-sm sm:col-span-2">학번은 수강생 확인 및 제출 기록 연결에만 사용되며 공개 리더보드에는 표시되지 않습니다.</p>
        <Field label="닉네임"><input aria-label="닉네임" className={inputClass} value={nickname} onChange={(e) => setNickname(e.target.value)} required minLength={2} maxLength={16} /></Field>
        <Field label="이모지"><select aria-label="이모지" className={inputClass} value={emoji} onChange={(e) => setEmoji(e.target.value)}>{data[1].map((avatar) => <option key={avatar.id} value={avatar.emoji}>{avatar.emoji} {avatar.label}</option>)}</select></Field>
        <p className="text-sm sm:col-span-2">닉네임과 이모지는 첫 제출 때 고정됩니다. 이후 변경은 관리자에게 요청하세요. 자동 완성 정보는 인증에 사용되지 않습니다.</p>
        <Field label="제출 유형"><select aria-label="제출 유형" className={inputClass} value={kind} onChange={(e) => setKind(e.target.value as SubmissionKind)}><option value="BASELINE_PRACTICE">Baseline</option><option value="EVALUATION">Development</option><option value="DRAFT">초안 저장</option></select></Field>
        <Field label="모델 이름"><input className={inputClass} value={modelName} onChange={(e) => setModelName(e.target.value)} required maxLength={160} placeholder="예: koelectra-v2" /></Field>
        <Field label="Base model"><input className={inputClass} value={baseModel} onChange={(e) => setBaseModel(e.target.value)} maxLength={160} placeholder="태스크 허용 목록의 모델명" /></Field>
        <div className="sm:col-span-2"><Field label="실험 요약"><textarea className={`${inputClass} min-h-24 resize-y`} value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="변경 사항을 짧게 기록하세요." /></Field></div>
      </section>
      <section className="grid gap-4 sm:grid-cols-2">
        <FilePicker icon={FileCode2} label="Notebook" accept=".ipynb" file={notebook} setFile={setNotebook} hint="저장만 하며 실행하지 않습니다." />
        <FilePicker icon={FileArchive} label="모델 ZIP" accept=".zip" file={modelZip} setFile={setModelZip} hint={`최대 ${task ? formatBytes(task.max_zip_bytes) : "-"}, safetensors만 허용`} />
      </section>
      {formError && <div role="alert" className="border border-red-200 bg-red-50 p-4 text-sm text-red-900">{formError}</div>}
      {progress !== null && <div aria-label="업로드 진행률"><div className="mb-2 flex justify-between text-sm"><span>업로드 중</span><span>{progress}%</span></div><div className="h-2 overflow-hidden rounded bg-zinc-200"><div className="h-full bg-emerald-600 transition-all" style={{ width: `${progress}%` }} /></div></div>}
      <div className="flex flex-wrap justify-end gap-3 border-t border-zinc-200 pt-5">
        <Button type="submit" disabled={progress !== null}><UploadCloud className="h-4 w-4" />제출</Button>
      </div>
    </form>
  </div>;
}

function FilePicker({ icon: Icon, label, accept, file, setFile, hint }: { icon: typeof FileCode2; label: string; accept: string; file: File | null; setFile: (file: File | null) => void; hint: string }) {
  return <label className="block cursor-pointer border border-dashed border-zinc-300 bg-white p-6 text-center hover:border-emerald-500"><Icon className="mx-auto h-7 w-7 text-emerald-700" /><span className="mt-3 block text-sm font-semibold">{file?.name ?? label}</span><span className="mt-1 block text-xs text-zinc-500">{file ? formatBytes(file.size) : hint}</span><input className="sr-only" type="file" accept={accept} onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>;
}
