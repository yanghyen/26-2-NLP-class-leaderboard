export const LOCAL_NOTICE = "현재 브라우저에서 생성한 제출만 표시합니다. 브라우저 데이터를 삭제하거나 다른 기기를 사용하면 과거 기록이 자동으로 나타나지 않습니다. 공식 제출 기록이나 본인 인증 수단이 아닙니다.";
export interface Preferences { studentNumber: string; nickname: string; emoji: string }
export function readPreferences(): Preferences {
  try {
    const value = JSON.parse(localStorage.getItem("nlp-autocomplete") ?? "{}");
    return { studentNumber: typeof value.studentNumber === "string" ? value.studentNumber : "", nickname: typeof value.nickname === "string" ? value.nickname : "", emoji: typeof value.emoji === "string" ? value.emoji : "🧠" };
  } catch { return { studentNumber: "", nickname: "", emoji: "🧠" }; }
}
export function savePreferences(value: Preferences) { try { localStorage.setItem("nlp-autocomplete", JSON.stringify(value)); } catch { /* Storage may be disabled. */ } }
export function submissionIds(): string[] {
  try { const ids: unknown = JSON.parse(localStorage.getItem("nlp-submission-ids") ?? "[]"); return Array.isArray(ids) ? ids.filter((id) => typeof id === "string" && /^[0-9a-f-]{36}$/.test(id)) : []; } catch { return []; }
}
export function rememberSubmission(id: string) { try { localStorage.setItem("nlp-submission-ids", JSON.stringify([...new Set([id, ...submissionIds()])])); } catch { /* Storage may be disabled. */ } }
