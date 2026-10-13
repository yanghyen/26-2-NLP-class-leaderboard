import type { TaskDetail, TaskStage, TaskUpdatePayload } from "./types";

export interface TaskPolicyForm {
  title: string;
  description: string;
  stage: TaskStage;
  isPublic: boolean;
  evaluatorKey: string;
  datasetConfig: string;
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
    datasetConfig: JSON.stringify(task.config.dataset_config ?? {}, null, 2),
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
  if (!["mock_v1", "lab02_sentiment_v1"].includes(form.evaluatorKey)) return "지원하지 않는 evaluator입니다.";
  if (form.evaluatorKey === "lab02_sentiment_v1") {
    try {
      const data = JSON.parse(form.datasetConfig);
      if (!data || typeof data !== "object" || Array.isArray(data) || !data.path || !data.metadata_path || !data.version || !data.sha256 || !data.sample_count) {
        return "준비 명령이 반환한 Lab02 dataset 설정을 입력하세요.";
      }
    } catch { return "Lab02 dataset 설정은 JSON object여야 합니다."; }
  }
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
      ...(form.evaluatorKey === "lab02_sentiment_v1" ? {
        dataset_config: JSON.parse(form.datasetConfig), metric_config: { primary: "macro_f1", scale: "0_1" }
      } : {}),
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
