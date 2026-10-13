import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ tasks: vi.fn(), task: vi.fn(), create: vi.fn(), update: vi.fn() }));
vi.mock("./auth-provider", () => ({ useAuth: () => ({ token: "admin" }) }));
vi.mock("../lib/api", () => ({ api: {
  adminTasks: mocks.tasks, adminTask: mocks.task, createTask: mocks.create, updateTask: mocks.update
} }));

import AdminTasksPage from "../app/(app)/admin/tasks/page";

const task = {
  id: "task", slug: "existing", title: "Existing task", description: "", stage: "DEVELOPMENT",
  is_public: true, max_zip_bytes: 500000000, evaluator_key: "mock",
  config: { allowed_models: ["course/bert-base"], artifact_policy: { allowed_architectures: ["BertForSequenceClassification"] } }
};

describe("admin evaluator selection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.tasks.mockResolvedValue([task]);
    mocks.task.mockResolvedValue(task);
    mocks.create.mockResolvedValue(undefined);
    mocks.update.mockResolvedValue(undefined);
  });

  it("creates a task with an explicit mock_v1 selection and offers Lab02 with required local data preparation", async () => {
    render(<AdminTasksPage />);
    await screen.findByText("Existing task");
    fireEvent.click(screen.getByRole("button", { name: "태스크 생성" }));
    const select = screen.getByLabelText("Evaluator") as HTMLSelectElement;
    expect(select.value).toBe("mock_v1");
    expect((screen.getByRole("option", { name: /lab02_sentiment_v1/ }) as HTMLOptionElement).disabled).toBe(false);
    fireEvent.change(screen.getByLabelText("Slug"), { target: { value: "lab02-name" } });
    fireEvent.change(screen.getByLabelText("제목"), { target: { value: "Lab02 Sentiment" } });
    fireEvent.click(screen.getByRole("button", { name: "생성" }));
    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith("admin", expect.objectContaining({ evaluator_key: "mock_v1" })));
  });

  it("edits a historical mock task using the canonical evaluator key", async () => {
    render(<AdminTasksPage />);
    await screen.findByText("Existing task");
    fireEvent.click(screen.getByRole("button", { name: "수정" }));
    await screen.findByLabelText("Evaluator");
    expect((screen.getByLabelText("Evaluator") as HTMLSelectElement).value).toBe("mock_v1");
    fireEvent.click(screen.getByRole("button", { name: "정책 저장" }));
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith("admin", "existing", expect.objectContaining({ evaluator_key: "mock_v1" })));
  });
});
