import { describe, expect, it } from "vitest";

import {
  hasEmptySubmissionPolicy,
  taskPolicyForm,
  taskUpdatePayload,
  validateTaskPolicyForm
} from "./task-policy-form";
import type { TaskDetail } from "./types";

function task(policy: TaskDetail["config"]["artifact_policy"]): TaskDetail {
  return {
    id: "task-id",
    slug: "test",
    title: "Development task",
    description: "description",
    stage: "DEVELOPMENT",
    is_public: true,
    max_official_submissions: 5,
    max_zip_bytes: 500_000_000,
    timeout_seconds: 900,
    evaluator_key: "mock",
    opens_at: null,
    dev_deadline: null,
    final_deadline: null,
    public_leaderboard_visible: true,
    private_leaderboard_visible: false,
    config: {
      dataset_config: {},
      allowed_models: ["course/bert-base"],
      artifact_policy: policy,
      metric_config: { primary: "mock_score" },
      split_config: {},
      scoring_strategy: "task_primary_score"
    }
  };
}

describe("task policy editor", () => {
  it("loads existing policy values into structured fields", () => {
    const form = taskPolicyForm(task({
      allowed_architectures: ["BertForSequenceClassification"],
      allowed_dtypes: ["F32"]
    }));
    expect(form.models).toBe("course/bert-base");
    expect(form.architectures).toBe("BertForSequenceClassification");
    expect(form.dtypes).toBe("F32");
    expect(form.evaluatorKey).toBe("mock_v1");
  });

  it("validates required and duplicate policy entries before saving", () => {
    const form = taskPolicyForm(task({ allowed_architectures: [] }));
    expect(validateTaskPolicyForm(form)).toContain("architecture");
    expect(validateTaskPolicyForm({
      ...form,
      architectures: "BertModel, BertModel"
    })).toContain("중복");
  });

  it("builds a typed partial update and displays the saved values", () => {
    const form = taskPolicyForm(task({ allowed_architectures: ["OldArchitecture"] }));
    const payload = taskUpdatePayload({
      ...form,
      models: "course/bert-v2",
      architectures: "BertForSequenceClassificationV2"
    });
    expect(payload.config?.allowed_models).toEqual(["course/bert-v2"]);
    expect(payload.evaluator_key).toBe("mock_v1");
    expect(payload.config?.artifact_policy?.allowed_architectures).toEqual([
      "BertForSequenceClassificationV2"
    ]);
  });

  it("flags an empty artifact policy", () => {
    expect(hasEmptySubmissionPolicy(task({}))).toBe(true);
    expect(hasEmptySubmissionPolicy(task({
      allowed_architectures: ["BertForSequenceClassification"]
    }))).toBe(false);
  });

  it("requires prepared local dataset configuration for Lab02 and rejects unknown keys", () => {
    const form = taskPolicyForm(task({ allowed_architectures: ["BertForSequenceClassification"] }));
    expect(validateTaskPolicyForm({ ...form, evaluatorKey: "lab02_sentiment_v1" })).toContain("준비 명령");
    expect(validateTaskPolicyForm({ ...form, evaluatorKey: "unknown" })).toContain("지원하지 않는");
  });

  it("serializes prepared Lab02 data and the 0–1 macro F1 metric without changing Mock", () => {
    const form = taskPolicyForm(task({ allowed_architectures: ["BertForSequenceClassification"] }));
    const data = { path: "/srv/data/reviews.jsonl", metadata_path: "/srv/data/metadata.json", version: "local-v1", sha256: "a".repeat(64), sample_count: 2 };
    const lab = { ...form, evaluatorKey: "lab02_sentiment_v1", models: "google-bert/bert-base-uncased", datasetConfig: JSON.stringify(data) };
    expect(validateTaskPolicyForm(lab)).toBeNull();
    expect(taskUpdatePayload(lab).config?.dataset_config).toEqual(data);
    expect(taskUpdatePayload(lab).config?.metric_config).toEqual({ primary: "macro_f1", scale: "0_1" });
    expect(taskUpdatePayload(form).config?.dataset_config).toBeUndefined();
  });
});
