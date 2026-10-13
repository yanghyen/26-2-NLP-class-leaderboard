"use client";

import { AlertTriangle, Pencil, Plus, Save, X } from "lucide-react";
import { FormEvent, useCallback, useState } from "react";

import { useAuth } from "../../../../components/auth-provider";
import { Button, ErrorState, Field, LoadingState, PageHeader, inputClass } from "../../../../components/ui";
import { useApiData } from "../../../../hooks/use-api-data";
import { api } from "../../../../lib/api";
import { formatBytes, STAGE_LABELS } from "../../../../lib/format";
import {
  hasEmptySubmissionPolicy,
  taskPolicyForm,
  taskUpdatePayload,
  validateTaskPolicyForm,
  type TaskPolicyForm
} from "../../../../lib/task-policy-form";
import type { TaskStage } from "../../../../lib/types";

const initialCreate = {
  slug: "", title: "", description: "", stage: "DEVELOPMENT" as TaskStage,
  models: "course/bert-base",
  architectures: "BertForSequenceClassification", public: true
};

export default function AdminTasksPage() {
  const { token } = useAuth();
  const loader = useCallback(() => api.adminTasks(token!), [token]);
  const { data, error, loading, refresh } = useApiData(loader, [loader]);
  const [open, setOpen] = useState(false);
  const [createForm, setCreateForm] = useState(initialCreate);
  const [editSlug, setEditSlug] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<TaskPolicyForm | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function create(event: FormEvent) {
    event.preventDefault();
    setActionError(null);
    setMessage(null);
    const models = createForm.models.split(",").map((value) => value.trim()).filter(Boolean);
    const architectures = createForm.architectures.split(",").map((value) => value.trim()).filter(Boolean);
    if (!models.length || !architectures.length) {
      setActionError("허용 base model과 architecture를 하나 이상 입력하세요.");
      return;
    }
    try {
      await api.createTask(token!, {
        slug: createForm.slug,
        title: createForm.title,
        description: createForm.description,
        stage: createForm.stage,
        is_public: createForm.public,
        evaluator_key: "mock",
        config: {
          allowed_models: models,
          artifact_policy: { allowed_architectures: architectures },
          metric_config: { primary: "mock_score" }
        }
      });
      setCreateForm(initialCreate);
      setOpen(false);
      setMessage("태스크를 생성했습니다.");
      await refresh();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "태스크를 만들지 못했습니다.");
    }
  }

  async function beginEdit(slug: string) {
    setActionError(null);
    setMessage(null);
    try {
      const task = await api.adminTask(token!, slug);
      setEditSlug(slug);
      setEditForm(taskPolicyForm(task));
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "태스크 설정을 불러오지 못했습니다.");
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!editSlug || !editForm) return;
    setActionError(null);
    setMessage(null);
    const validation = validateTaskPolicyForm(editForm);
    if (validation) {
      setActionError(validation);
      return;
    }
    try {
      await api.updateTask(token!, editSlug, taskUpdatePayload(editForm));
      const latest = await api.adminTask(token!, editSlug);
      setEditForm(taskPolicyForm(latest));
      setMessage("태스크 정책을 저장하고 DB 반영값을 다시 불러왔습니다.");
      await refresh();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "태스크 정책을 저장하지 못했습니다.");
    }
  }

  if (loading) return <LoadingState />;
  if (error || !data) return <ErrorState message={error ?? "태스크를 불러오지 못했습니다."} retry={refresh} />;
  return <div className="space-y-6">
    <PageHeader title="태스크 관리" description="평가 정책과 허용 모델을 지정하고 기존 설정을 수정합니다." action={<Button onClick={() => setOpen((value) => !value)}><Plus className="h-4 w-4" />태스크 생성</Button>} />
    {open && <form onSubmit={(event) => void create(event)} className="grid gap-4 border border-zinc-200 bg-white p-5 sm:grid-cols-2">
      <Field label="Slug"><input required pattern="[a-z0-9][a-z0-9-]{1,78}[a-z0-9]" className={inputClass} value={createForm.slug} onChange={(event) => setCreateForm({ ...createForm, slug: event.target.value })} /></Field>
      <Field label="제목"><input required className={inputClass} value={createForm.title} onChange={(event) => setCreateForm({ ...createForm, title: event.target.value })} /></Field>
      <Field label="Stage"><select className={inputClass} value={createForm.stage} onChange={(event) => setCreateForm({ ...createForm, stage: event.target.value as TaskStage })}>{Object.entries(STAGE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
      <Field label="허용 base models" hint="쉼표로 구분"><input className={inputClass} value={createForm.models} onChange={(event) => setCreateForm({ ...createForm, models: event.target.value })} /></Field>
      <Field label="허용 architectures" hint="쉼표로 구분"><input className={inputClass} value={createForm.architectures} onChange={(event) => setCreateForm({ ...createForm, architectures: event.target.value })} /></Field>
      <div className="sm:col-span-2"><Field label="설명"><textarea className={inputClass} value={createForm.description} onChange={(event) => setCreateForm({ ...createForm, description: event.target.value })} /></Field></div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={createForm.public} onChange={(event) => setCreateForm({ ...createForm, public: event.target.checked })} />학생에게 공개</label>
      <div className="flex justify-end"><Button type="submit">생성</Button></div>
    </form>}
    {editForm && editSlug && <form onSubmit={(event) => void save(event)} className="grid gap-4 border border-emerald-300 bg-white p-5 sm:grid-cols-2">
      <div className="flex items-center justify-between sm:col-span-2"><div><h2 className="font-bold">{editSlug} 정책 수정</h2><p className="mt-1 text-xs text-zinc-500">Slug는 기존 제출 참조를 보호하기 위해 수정할 수 없습니다.</p></div><Button type="button" variant="ghost" title="편집 닫기" onClick={() => { setEditSlug(null); setEditForm(null); }}><X className="h-4 w-4" /></Button></div>
      <Field label="제목"><input required className={inputClass} value={editForm.title} onChange={(event) => setEditForm({ ...editForm, title: event.target.value })} /></Field>
      <Field label="Stage"><select className={inputClass} value={editForm.stage} onChange={(event) => setEditForm({ ...editForm, stage: event.target.value as TaskStage })}>{Object.entries(STAGE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
      <label className="flex items-end gap-2 pb-3 text-sm"><input type="checkbox" checked={editForm.isPublic} onChange={(event) => setEditForm({ ...editForm, isPublic: event.target.checked })} />학생에게 공개</label>
      <Field label="허용 base models" hint="필수, 쉼표로 구분"><input className={inputClass} value={editForm.models} onChange={(event) => setEditForm({ ...editForm, models: event.target.value })} /></Field>
      <Field label="허용 architectures" hint="필수, 쉼표로 구분"><input className={inputClass} value={editForm.architectures} onChange={(event) => setEditForm({ ...editForm, architectures: event.target.value })} /></Field>
      <Field label="허용 경로" hint="비우면 서버 기본 allowlist 사용"><input className={inputClass} value={editForm.paths} onChange={(event) => setEditForm({ ...editForm, paths: event.target.value })} /></Field>
      <Field label="허용 dtype" hint="비우면 서버 기본 dtype 사용"><input className={inputClass} value={editForm.dtypes} onChange={(event) => setEditForm({ ...editForm, dtypes: event.target.value })} /></Field>
      <div className="sm:col-span-2"><Field label="설명"><textarea className={inputClass} value={editForm.description} onChange={(event) => setEditForm({ ...editForm, description: event.target.value })} /></Field></div>
      <div className="flex justify-end sm:col-span-2"><Button type="submit"><Save className="h-4 w-4" />정책 저장</Button></div>
    </form>}
    {actionError && <p role="alert" className="border border-red-200 bg-red-50 p-3 text-sm text-red-800">{actionError}</p>}
    {message && <p role="status" className="border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{message}</p>}
    <div className="overflow-x-auto border border-zinc-200 bg-white"><table><thead><tr><th>태스크</th><th>Stage</th><th>공개</th><th>제출 제한</th><th>ZIP 제한</th><th>정책</th><th>작업</th></tr></thead><tbody>{data.map((row) => {
      const emptyPolicy = hasEmptySubmissionPolicy(row);
      return <tr key={row.id}><td><strong>{row.title}</strong><br /><span className="font-mono text-xs text-zinc-500">{row.slug}</span></td><td>{STAGE_LABELS[row.stage]}</td><td>{row.is_public ? "공개" : "비공개"}</td><td>횟수 제한 없음</td><td>{formatBytes(row.max_zip_bytes)}</td><td>{emptyPolicy ? <span className="inline-flex items-center gap-1 text-sm font-semibold text-red-700"><AlertTriangle className="h-4 w-4" />정책 미설정</span> : <span className="text-sm text-emerald-700">설정됨</span>}{emptyPolicy && <p className="mt-1 max-w-xs text-xs text-red-700">정책이 없으면 모델 제출을 검증할 수 없습니다.</p>}</td><td><Button variant="secondary" onClick={() => void beginEdit(row.slug)}><Pencil className="h-4 w-4" />수정</Button></td></tr>;
    })}</tbody></table></div>
  </div>;
}
