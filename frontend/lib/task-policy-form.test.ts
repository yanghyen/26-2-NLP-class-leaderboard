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

  it("rejects unavailable and unknown evaluator selections before saving", () => {
    const form = taskPolicyForm(task({ allowed_architectures: ["BertForSequenceClassification"] }));
    expect(validateTaskPolicyForm({ ...form, evaluatorKey: "lab02_sentiment_v1" })).toContain("mock_v1뿐");
    expect(validateTaskPolicyForm({ ...form, evaluatorKey: "unknown" })).toContain("mock_v1뿐");
  });
});
