export type UserRole = "STUDENT" | "ADMIN";
export type TaskStage = "BASELINE_PRACTICE" | "DEVELOPMENT" | "FINAL";
export type SubmissionKind = "DRAFT" | "EVALUATION" | "BASELINE_PRACTICE";
export type SubmissionStatus =
  | "UPLOADING"
  | "VALIDATING"
  | "QUARANTINED"
  | "QUEUED"
  | "RUNNING"
  | "SCORING"
  | "COMPLETED"
  | "FAILED"
  | "INVALIDATED";
export type EvaluationSplit = "SMOKE" | "PUBLIC" | "PRIVATE";

export interface Avatar {
  id: string;
  emoji: string;
  label: string;
}

export interface User {
  id: string;
  nickname: string;
  avatar_id: string;
  avatar_emoji: string;
  role: UserRole;
  student_number: string | null;
  real_name: string | null;
  password_reset_required: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
}

export interface TaskConfig {
  dataset_config: Record<string, unknown>;
  allowed_models: string[];
  artifact_policy: {
    allowed_paths?: string[];
    allowed_architectures?: string[];
    allowed_dtypes?: string[];
    [key: string]: unknown;
  };
  metric_config: Record<string, unknown>;
  split_config: Record<string, unknown>;
  scoring_strategy: string;
}

export interface Task {
  id: string;
  slug: string;
  title: string;
  description: string;
  stage: TaskStage;
  is_public: boolean;
  max_official_submissions: number;
  max_zip_bytes: number;
  timeout_seconds: number;
  evaluator_key: string;
  opens_at: string | null;
  dev_deadline: string | null;
  final_deadline: string | null;
  public_leaderboard_visible: boolean;
  private_leaderboard_visible: boolean;
}

export interface TaskDetail extends Task {
  config: TaskConfig;
}

export interface Score {
  split: EvaluationSplit;
  primary_metric: string;
  primary_score: number;
  metrics: Record<string, unknown>;
}

export interface Submission {
  id: string;
  task_id: string;
  kind: SubmissionKind;
  status: SubmissionStatus;
  model_name: string | null;
  safe_error_message: string | null;
  created_at: string;
}

export interface SubmissionFile {
  file_type: "notebook" | "model_zip" | string;
  original_filename: string;
  size_bytes: number;
  checksum_sha256: string;
}

export interface SubmissionDetail extends Submission {
  scores: Score[];
  files: SubmissionFile[];
}

export interface EvaluationJob {
  id: string;
  submission_id: string;
  split: EvaluationSplit;
  status: SubmissionStatus;
  attempts: number;
  max_attempts: number;
}

export interface EvaluationJobAdmin extends EvaluationJob {
  worker_id: string | null;
  error_kind: string | null;
  safe_error_message: string | null;
}

export interface SubmissionAdmin extends Submission {
  artifact_cleanup_status: "retained" | "pending" | "deleted";
  artifact_deleted_at: string | null;
  evaluator_version: string | null;
  dataset_version: string | null;
  user_id: string | null;
  participant_id: string | null;
  student_number: string | null;
  nickname: string;
  task_slug: string;
  task_title: string;
  artifact_digest: string | null;
  validation_report: Record<string, unknown>;
  malware_scan_status: string | null;
  internal_error_message: string | null;
}

export interface LeaderboardRow {
  rank: number;
  nickname: string;
  avatar_id: string;
  avatar_emoji: string;
  baseline_score: number | null;
  best_development_score: number | null;
  improvement: number | null;
  primary_metric: string;
  primary_score: number;
  metrics: Record<string, unknown>;
  model_name: string | null;
  submitted_at: string;
}

export interface RosterRow {
  student_number: string;
  real_name: string;
  section: string | null;
  participant_id: string | null;
  nickname: string | null;
}

export interface SubmissionCreateResponse {
  submission: Submission;
  evaluation_job: EvaluationJob | null;
}

export interface TaskUpdatePayload {
  title?: string;
  description?: string;
  stage?: TaskStage;
  is_public?: boolean;
  max_official_submissions?: number;
  config?: {
    allowed_models?: string[];
    artifact_policy?: {
      allowed_paths?: string[];
      allowed_architectures: string[];
      allowed_dtypes?: string[];
    };
  };
}

export interface ParticipantResult {
  participant_id: string;
  roster_entry_id: string;
  student_number: string;
  nickname: string;
  emoji: string;
  baseline_score: number | null;
  best_development_score: number | null;
  improvement: number | null;
  total_submission_count: number;
  successful_submission_count: number;
  failed_submission_count: number;
  quarantined_submission_count: number;
  last_submitted_at: string;
}
