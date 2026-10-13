import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ submissions: vi.fn(), download: vi.fn(), remove: vi.fn(), submission: vi.fn() }));
vi.mock("next/navigation", () => ({ useParams: () => ({ id: "submission" }) }));
vi.mock("./auth-provider", () => ({ useAuth: () => ({ token: "admin" }) }));
vi.mock("../lib/api", () => ({
  api: { adminSubmissions: mocks.submissions, deleteArtifact: mocks.remove, submission: mocks.submission },
  downloadAdminFile: mocks.download
}));

import AdminSubmissionsPage from "../app/(app)/admin/submissions/page";
import SubmissionDetailPage from "../app/(app)/submissions/[id]/page";

const record = {
  id: "submission", kind: "EVALUATION", status: "COMPLETED", model_name: "Tiny model",
  created_at: "2026-10-13T00:00:00Z", artifact_cleanup_status: "deleted",
  artifact_deleted_at: "2026-10-13T00:01:00Z", scores: [{ primary_score: .8 }]
};

describe("artifact retention UI", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.submissions.mockResolvedValue([record]);
    mocks.submission.mockResolvedValue(record);
  });

  it("keeps admin records and replaces downloads with a deletion notice", async () => {
    render(<AdminSubmissionsPage />);
    await screen.findByText(/평가 완료 후 자동 삭제됨/);
    expect(screen.getByText("Tiny model")).toBeTruthy();
    expect(screen.queryByTitle("Notebook 다운로드")).toBeNull();
    expect(screen.queryByTitle("모델 ZIP 다운로드")).toBeNull();
    expect((screen.getByTitle("Artifact 삭제") as HTMLButtonElement).disabled).toBe(true);
    expect(mocks.download).not.toHaveBeenCalled();
  });

  it("offers a cleanup retry while hiding pending downloads", async () => {
    mocks.submissions.mockResolvedValue([{ ...record, artifact_cleanup_status: "pending", artifact_deleted_at: null }]);
    mocks.remove.mockResolvedValue(undefined);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<AdminSubmissionsPage />);
    await screen.findByText(/파일 정리 대기 중/);
    expect(screen.queryByTitle("Notebook 다운로드")).toBeNull();
    fireEvent.click(screen.getByTitle("파일 정리 재시도"));
    expect(confirm).toHaveBeenCalledWith("점수를 유지하고 파일 정리를 다시 시도할까요?");
    expect(mocks.remove).toHaveBeenCalledWith("admin", "submission");
    confirm.mockRestore();
  });

  it("hides downloads for historical successes before the recovery sweep", async () => {
    mocks.submissions.mockResolvedValue([{ ...record, artifact_cleanup_status: "retained", artifact_deleted_at: null }]);
    render(<AdminSubmissionsPage />);
    await screen.findByText(/파일 정리 대기 중/);
    expect(screen.queryByTitle("Notebook 다운로드")).toBeNull();
    expect(screen.queryByTitle("모델 ZIP 다운로드")).toBeNull();
  });

  it("shows students their score and the exact file retention and LMS guidance", async () => {
    render(<SubmissionDetailPage />);
    await screen.findByText("Tiny model");
    expect(screen.getByText(/공개 점수: 0.8000/)).toBeTruthy();
    expect(screen.getByText(/제출 파일은 평가 완료 후 자동 삭제되며, 점수와 제출 기록만 보존됩니다./)).toBeTruthy();
    expect(screen.getByText(/공식 제출 파일은 반드시 본인이 보관하여 e-Class LMS에 제출하세요./)).toBeTruthy();
  });

  it("does not describe a stored draft as an evaluated auto-deleted submission", async () => {
    mocks.submission.mockResolvedValue({ ...record, kind: "DRAFT", scores: [] });
    render(<SubmissionDetailPage />);
    await screen.findByText("Tiny model");
    expect(screen.queryByText(/제출 파일은 평가 완료 후 자동 삭제/)).toBeNull();
    expect(screen.getByText("초안 저장 완료")).toBeTruthy();
  });
});
