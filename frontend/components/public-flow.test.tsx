import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ push: vi.fn(), upload: vi.fn(), submission: vi.fn(), pathname: "/submit" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push, replace: vi.fn() }), usePathname: () => mocks.pathname }));
vi.mock("./auth-provider", () => ({ useAuth: () => ({ user: null, token: null, loading: false }) }));
vi.mock("../lib/api", () => ({ api: {
  tasks: async () => [{ id: "task", slug: "sentiment", title: "Sentiment", stage: "DEVELOPMENT", max_zip_bytes: 1000000 }],
  avatars: async () => [{ id: "brain", emoji: "🧠", label: "Brain" }],
  submission: mocks.submission
}, uploadSubmission: mocks.upload }));
import SubmitPage from "../app/(app)/submit/page";
import SubmissionsPage from "../app/(app)/submissions/page";
import { ProtectedShell } from "./app-shell";
import { savePreferences, rememberSubmission } from "../lib/local-submissions";

describe("public student flow", () => {
  beforeEach(() => { localStorage.clear(); mocks.upload.mockReset(); mocks.submission.mockReset(); mocks.push.mockReset(); });
  it("allows anonymous routes and includes LMS guidance with no student auth links", () => {
    render(<ProtectedShell><p>공개 제출</p></ProtectedShell>);
    expect(screen.getByText("공개 제출")).toBeTruthy();
    expect(screen.getByText(/공식 최종 제출은 e-Class LMS/)).toBeTruthy();
    expect(document.querySelector('a[href="/register"]')).toBeNull();
    expect(document.querySelector('a[href="/login"]')).toBeNull();
  });
  it("autocompletes identifiers, explains privacy, and disables duplicate upload clicks", async () => {
    savePreferences({ studentNumber: "synthetic", nickname: "Hero", emoji: "🧠" });
    let finish: (value: unknown) => void = () => {};
    mocks.upload.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const { container } = render(<SubmitPage />);
    await screen.findByText("학번은 수강생 확인 및 제출 기록 연결에만 사용되며 공개 리더보드에는 표시되지 않습니다.");
    expect((screen.getByLabelText("학번") as HTMLInputElement).value).toBe("synthetic");
    expect(screen.getByLabelText("닉네임")).toBeTruthy();
    expect(screen.getByLabelText("이모지")).toBeTruthy();
    const inputs = container.querySelectorAll('input[type="file"]');
    fireEvent.change(inputs[0], { target: { files: [new File(["{}"], "test.ipynb")] } });
    fireEvent.change(inputs[1], { target: { files: [new File(["zip"], "model.zip")] } });
    fireEvent.change(container.querySelector('input[placeholder="예: koelectra-v2"]')!, { target: { value: "model" } });
    const button = screen.getByRole("button", { name: "제출" });
    fireEvent.click(button); fireEvent.click(button);
    await waitFor(() => expect(mocks.upload).toHaveBeenCalledTimes(1));
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(mocks.upload.mock.calls[0][0]).toBe("sentiment");
    await act(async () => { finish({ submission: { id: "11111111-1111-1111-1111-111111111111" } }); });
    expect(mocks.push).toHaveBeenCalledWith("/submissions/11111111-1111-1111-1111-111111111111");
  });
  it("loads only browser UUIDs and never displays saved student numbers", async () => {
    savePreferences({ studentNumber: "private-student-number", nickname: "Hero", emoji: "🧠" });
    const id = "11111111-1111-1111-1111-111111111111"; rememberSubmission(id);
    mocks.submission.mockResolvedValue({ id, model_name: "Tiny model", kind: "EVALUATION", status: "COMPLETED", created_at: "2026-10-12T00:00:00Z", scores: [{ primary_score: .8 }] });
    render(<SubmissionsPage />);
    await screen.findByText("Tiny model");
    expect(mocks.submission).toHaveBeenCalledWith(id);
    expect(document.body.textContent).not.toContain("private-student-number");
    expect(screen.getByText(/다른 기기를 사용하면 과거 기록이 자동으로 나타나지/)).toBeTruthy();
    expect(document.body.textContent).not.toContain("최종 제출로 선택");
  });
});
