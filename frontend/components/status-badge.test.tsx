import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./status-badge";

describe("StatusBadge", () => {
  it("shows a Korean label without exposing an internal error", () => {
    render(<StatusBadge status="QUARANTINED" />);
    expect(screen.getByText("관리자 검토 필요")).toBeTruthy();
    expect(screen.queryByText(/traceback/i)).toBeNull();
  });

  it("distinguishes a stored draft from a completed evaluation", () => {
    const { rerender } = render(<StatusBadge kind="DRAFT" status="COMPLETED" />);
    expect(screen.getByText("초안 저장 완료")).toBeTruthy();
    expect(screen.queryByText("평가 완료")).toBeNull();

    rerender(<StatusBadge kind="EVALUATION" status="COMPLETED" />);
    expect(screen.getByText("평가 완료")).toBeTruthy();
  });

  it("uses evaluation labels for queued and failed evaluation submissions", () => {
    const { rerender } = render(<StatusBadge kind="EVALUATION" status="QUEUED" />);
    expect(screen.getByText("평가 대기 중")).toBeTruthy();
    rerender(<StatusBadge kind="EVALUATION" status="FAILED" />);
    expect(screen.getByText("평가 실패")).toBeTruthy();
  });
});
