import { describe, expect, it } from "vitest";

import { ACTIVE_STATUSES, ERROR_MESSAGES, formatBytes, formatScore, isCompletedEvaluation, statusTone } from "./format";

describe("submission presentation rules", () => {
  it("polls only non-terminal evaluation states", () => {
    expect(ACTIVE_STATUSES.has("RUNNING")).toBe(true);
    expect(ACTIVE_STATUSES.has("COMPLETED")).toBe(false);
    expect(ACTIVE_STATUSES.has("FAILED")).toBe(false);
  });

  it("maps statuses and values to stable student-facing text", () => {
    expect(statusTone("QUARANTINED")).toBe("danger");
    expect(statusTone("COMPLETED")).toBe("success");
    expect(formatScore(0.812345)).toBe("0.8123");
    expect(formatBytes(2 * 1024 * 1024)).toBe("2.0 MB");
    expect(ERROR_MESSAGES.UNSUPPORTED_FILE).not.toContain("traceback");
  });

  it("counts only successful evaluation submissions as evaluation completions", () => {
    expect(isCompletedEvaluation("DRAFT", "COMPLETED")).toBe(false);
    expect(isCompletedEvaluation("EVALUATION", "COMPLETED")).toBe(true);
    expect(isCompletedEvaluation("EVALUATION", "FAILED")).toBe(false);
    expect(isCompletedEvaluation("EVALUATION", "QUARANTINED")).toBe(false);
    expect(isCompletedEvaluation("EVALUATION", "INVALIDATED")).toBe(false);
  });
});
