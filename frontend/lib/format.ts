import type { SubmissionKind, SubmissionStatus, TaskStage } from "./types";

export const ACTIVE_STATUSES = new Set<SubmissionStatus>([
  "UPLOADING",
  "VALIDATING",
  "QUEUED",
  "RUNNING",
  "SCORING"
]);

export const STATUS_LABELS: Record<SubmissionStatus, string> = {
  UPLOADING: "업로드 중",
  VALIDATING: "파일 검사 중",
  QUARANTINED: "관리자 검토 필요",
  QUEUED: "평가 대기 중",
  RUNNING: "모델 평가 중",
  SCORING: "점수 계산 중",
  COMPLETED: "평가 완료",
  FAILED: "평가 실패",
  INVALIDATED: "무효 처리"
};

const DRAFT_STATUS_LABELS: Partial<Record<SubmissionStatus, string>> = {
  UPLOADING: "초안 업로드 중",
  VALIDATING: "초안 검사 중",
  COMPLETED: "초안 저장 완료",
  FAILED: "초안 저장 실패",
  QUARANTINED: "초안 관리자 검토 필요",
  INVALIDATED: "이전 초안"
};

export function submissionStatusLabel(
  kind: SubmissionKind | undefined,
  status: SubmissionStatus
): string {
  if (kind === "DRAFT") return DRAFT_STATUS_LABELS[status] ?? STATUS_LABELS[status];
  return STATUS_LABELS[status];
}

export function isCompletedEvaluation(kind: SubmissionKind, status: SubmissionStatus): boolean {
  return kind === "EVALUATION" && status === "COMPLETED";
}

export const STAGE_LABELS: Record<TaskStage, string> = {
  BASELINE_PRACTICE: "Baseline Practice",
  DEVELOPMENT: "개발 제출",
  FINAL: "최종 제출"
};

export function formatDate(value: string | null | undefined): string {
  if (!value) return "미정";
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

export function formatScore(value: number | null | undefined): string {
  return value === null || value === undefined ? "-" : value.toFixed(4);
}

export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 ** 2).toFixed(1)} MB`;
}

export function statusTone(status: SubmissionStatus): "success" | "danger" | "neutral" | "progress" {
  if (status === "COMPLETED") return "success";
  if (status === "FAILED" || status === "QUARANTINED") return "danger";
  if (status === "INVALIDATED") return "neutral";
  return "progress";
}

export const ERROR_MESSAGES: Record<string, string> = {
  EVALUATOR_NOT_AVAILABLE: "아직 사용할 수 없는 evaluator입니다.",
  UNKNOWN_EVALUATOR: "알 수 없는 evaluator 설정입니다.",
  EVALUATOR_CONFIG_INVALID: "evaluator 설정이 올바르지 않습니다.",
  LAB02_MANIFEST_INVALID: "Lab02 manifest 또는 파일 구성이 올바르지 않습니다.",
  LAB02_CONFIG_INVALID: "Lab02 모델 config가 평가 규격과 일치하지 않습니다.",
  INVALID_NOTEBOOK: "Notebook 형식을 확인해 주세요.",
  INVALID_ARCHIVE: "모델 ZIP 형식이 올바르지 않습니다.",
  UNSUPPORTED_FILE: "ZIP에 허용되지 않은 파일이 포함되어 있습니다.",
  INVALID_MODEL_FORMAT: "모델 artifact 구조를 확인해 주세요.",
  MODEL_TOO_LARGE: "제출 파일이 허용 크기를 초과했습니다.",
  MISSING_MODEL_FILE: "필수 모델 파일이 없습니다.",
  UNSUPPORTED_ARCHITECTURE: "이 태스크에서 허용하지 않는 모델 구조입니다.",
  SUBMISSION_LIMIT_EXCEEDED: "공식 제출 가능 횟수를 모두 사용했습니다.",
  ACTIVE_SUBMISSION_EXISTS: "이미 평가 중인 제출이 있습니다.",
  MALWARE_DETECTED: "제출 파일이 검토 대상으로 분류되었습니다. 관리자에게 문의해 주세요.",
  VALIDATION_FAILED: "제출 파일 검증에 실패했습니다.",
  EVALUATION_FAILED: "평가에 실패했습니다. 잠시 후 상태를 다시 확인해 주세요.",
  EVALUATION_TIMEOUT: "평가 제한 시간을 초과했습니다.",
  TASK_POLICY_NOT_CONFIGURED: "태스크의 제출 정책이 설정되지 않았습니다. 관리자에게 문의하세요."
};
