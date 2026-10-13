import { beforeEach, describe, expect, it } from "vitest";
import { readPreferences, savePreferences, rememberSubmission, submissionIds } from "./local-submissions";
describe("local submission convenience", () => {
  beforeEach(() => { localStorage.clear(); sessionStorage.clear(); });
  it("stores autocomplete without issuing an authentication token", () => {
    savePreferences({ studentNumber: "synthetic", nickname: "Hero", emoji: "🧠" });
    expect(readPreferences()).toEqual({ studentNumber: "synthetic", nickname: "Hero", emoji: "🧠" });
    expect(sessionStorage.length).toBe(0);
    expect(localStorage.getItem("nlp-admin-token")).toBeNull();
  });
  it("retains only browser submission UUIDs and deduplicates clicks", () => {
    const id = "11111111-1111-1111-1111-111111111111";
    rememberSubmission(id); rememberSubmission(id);
    expect(submissionIds()).toEqual([id]);
    localStorage.clear();
    expect(submissionIds()).toEqual([]);
  });
  it("recovers safely from malformed storage", () => {
    localStorage.setItem("nlp-autocomplete", "bad");
    localStorage.setItem("nlp-submission-ids", '{"token":"bad"}');
    expect(readPreferences().studentNumber).toBe("");
    expect(submissionIds()).toEqual([]);
  });
});
