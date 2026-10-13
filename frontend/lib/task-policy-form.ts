import type { TaskDetail, TaskStage, TaskUpdatePayload } from "./types";

export interface TaskPolicyForm {
  title: string;
  description: string;
  stage: TaskStage;
  isPublic: boolean;
  evaluatorKey: string;
  models: string;
  architectures: string;
  paths: string;
  dtypes: string;
}

export function csvValues(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function taskPolicyForm(task: TaskDetail): TaskPolicyForm {
  return {
    title: task.title,
    description: task.description,
    stage: task.stage,
    isPublic: task.is_public,
    evaluatorKey: task.evaluator_key === "mock" ? "mock_v1" : task.evaluator_key,
    models: task.config.allowed_models.join(", "),
    architectures: (task.config.artifact_policy.allowed_architectures ?? []).join(", "),
    paths: (task.config.artifact_policy.allowed_paths ?? []).join(", "),
    dtypes: (task.config.artifact_policy.allowed_dtypes ?? []).join(", ")
  };
}

function hasDuplicates(values: string[]): boolean {
  return new Set(values).size !== values.length;
}

export function validateTaskPolicyForm(form: TaskPolicyForm): string | null {
  const models = csvValues(form.models);
  const architectures = csvValues(form.architectures);
  if (!form.title.trim()) return "태스크 제목을 입력하세요.";
  if (form.evaluatorKey !== "mock_v1") return "현재 사용할 수 있는 evaluator는 mock_v1뿐입니다.";
  if (!models.length) return "허용 base model을 하나 이상 입력하세요.";
  if (!architectures.length) return "허용 architecture를 하나 이상 입력하세요.";
  if ([models, architectures, csvValues(form.paths), csvValues(form.dtypes)].some(hasDuplicates)) {
    return "정책 목록에서 중복 값을 제거하세요.";
  }
  return null;
}

export function taskUpdatePayload(form: TaskPolicyForm): TaskUpdatePayload {
  const paths = csvValues(form.paths);
  const dtypes = csvValues(form.dtypes);
  return {
    title: form.title.trim(),
    description: form.description,
    stage: form.stage,
    is_public: form.isPublic,
    evaluator_key: form.evaluatorKey,
    config: {
      allowed_models: csvValues(form.models),
      artifact_policy: {
        allowed_architectures: csvValues(form.architectures),
        ...(paths.length ? { allowed_paths: paths } : {}),
        ...(dtypes.length ? { allowed_dtypes: dtypes } : {})
      }
    }
  };
}

export function hasEmptySubmissionPolicy(task: TaskDetail): boolean {
  return !task.config.allowed_models.length
    || !(task.config.artifact_policy.allowed_architectures?.length);
}
