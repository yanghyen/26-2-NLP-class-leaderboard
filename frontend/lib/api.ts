import { ERROR_MESSAGES } from "./format";
import type {
  Avatar,
  EvaluationJobAdmin,
  LeaderboardRow,
  RosterRow,
  SubmissionAdmin,
  SubmissionCreateResponse,
  SubmissionDetail,
  SubmissionKind,
  Task,
  TaskDetail,
  TaskUpdatePayload,
  TokenResponse,
  User
} from "./types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
export const AUTH_EXPIRED_EVENT = "nlp-auth-expired";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string | null,
    message: string
  ) {
    super(message);
  }
}

function safeErrorMessage(status: number, detail: unknown): { code: string | null; message: string } {
  if (detail && typeof detail === "object" && "code" in detail) {
    const code = String((detail as { code: unknown }).code);
    return { code, message: ERROR_MESSAGES[code] ?? "요청을 처리하지 못했습니다." };
  }
  if (typeof detail === "string" && status < 500) return { code: null, message: detail };
  if (status === 401) return { code: null, message: "로그인이 만료되었습니다." };
  if (status === 403) return { code: null, message: "이 작업을 수행할 권한이 없습니다." };
  if (status === 404) return { code: null, message: "요청한 정보를 찾을 수 없습니다." };
  return { code: null, message: "서버와 통신하지 못했습니다. 잠시 후 다시 시도해 주세요." };
}

async function parseError(response: Response): Promise<ApiError> {
  let detail: unknown = null;
  try {
    const body = (await response.json()) as { detail?: unknown };
    detail = body.detail;
  } catch {
    detail = null;
  }
  const safe = safeErrorMessage(response.status, detail);
  return new ApiError(response.status, safe.code, safe.message);
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null
): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, null, "API 서버에 연결할 수 없습니다.");
  }
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
    throw await parseError(response);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  login: (loginId: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ student_number_or_nickname: loginId, password })
    }),
  me: (token: string) => request<User>("/auth/me", {}, token),
  avatars: () => request<Avatar[]>("/avatars"),
  tasks: () => request<Task[]>("/tasks"),
  adminTasks: (token: string) => request<TaskDetail[]>("/tasks/admin", {}, token),
  adminTask: (token: string, slug: string) =>
    request<TaskDetail>(`/tasks/admin/${encodeURIComponent(slug)}`, {}, token),
  task: (slug: string) => request<TaskDetail>(`/tasks/${encodeURIComponent(slug)}`),
  createTask: (token: string, payload: unknown) =>
    request<Task>("/tasks", { method: "POST", body: JSON.stringify(payload) }, token),
  updateTask: (token: string, slug: string, payload: TaskUpdatePayload) =>
    request<TaskDetail>(`/tasks/${encodeURIComponent(slug)}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }, token),
  submission: (id: string) => request<SubmissionDetail>(`/submissions/${id}`),
  leaderboard: (slug: string) =>
    request<LeaderboardRow[]>(`/tasks/${encodeURIComponent(slug)}/leaderboard`),
  roster: (token: string) => request<RosterRow[]>("/admin/roster", {}, token),
  adminSubmissions: (token: string) =>
    request<SubmissionAdmin[]>("/admin/submissions", {}, token),
  jobs: (token: string) => request<EvaluationJobAdmin[]>("/admin/jobs", {}, token),
  quarantine: (token: string) => request<SubmissionAdmin[]>("/admin/quarantine", {}, token),
  retryJob: (token: string, id: string) =>
    request<EvaluationJobAdmin>(`/admin/jobs/${id}/retry`, { method: "POST" }, token),
  invalidateSubmission: (token: string, id: string) =>
    request<SubmissionAdmin>(`/admin/submissions/${id}/invalidate`, { method: "POST" }, token),
  deleteArtifact: (token: string, id: string) =>
    request<void>(`/admin/submissions/${id}/artifact`, { method: "DELETE" }, token),
  uploadRoster: (token: string, file: File) => {
    const form = new FormData();
    form.set("file", file);
    return request<{ imported: number }>("/admin/roster/upload", { method: "POST", body: form }, token);
  }
};

export function uploadSubmission(
  taskSlug: string,
  values: {
    studentNumber: string;
    nickname: string;
    emoji: string;
    kind: SubmissionKind;
    modelName: string;
    baseModel: string;
    summary: string;
    notebook: File;
    modelZip: File;
  },
  onProgress: (progress: number) => void
): Promise<SubmissionCreateResponse> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.set("student_number", values.studentNumber);
    form.set("nickname", values.nickname);
    form.set("emoji", values.emoji);
    form.set("submission_type", values.kind);
    form.set("model_name", values.modelName);
    form.set("base_model", values.baseModel);
    form.set("metadata_json", JSON.stringify({ summary: values.summary }));
    form.set("notebook", values.notebook);
    form.set("artifact", values.modelZip);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/submissions/${encodeURIComponent(taskSlug)}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () => reject(new ApiError(0, null, "업로드 중 네트워크 연결이 끊어졌습니다."));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as SubmissionCreateResponse);
        return;
      }
      if (xhr.status === 401) window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
      const detail = body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : null;
      const safe = safeErrorMessage(xhr.status, detail);
      reject(new ApiError(xhr.status, safe.code, safe.message));
    };
    xhr.send(form);
  });
}

export async function downloadAdminFile(
  token: string,
  submissionId: string,
  fileType: "notebook" | "model_zip"
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/admin/submissions/${submissionId}/download/${fileType}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  if (!response.ok) throw await parseError(response);
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") ?? "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  const filename = encoded ? decodeURIComponent(encoded) : plain ?? `${fileType}.bin`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function downloadResultsCsv(token: string, slug: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/admin/tasks/${encodeURIComponent(slug)}/results.csv`, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) throw await parseError(response);
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = "practice-results.csv"; anchor.click();
  URL.revokeObjectURL(url);
}
