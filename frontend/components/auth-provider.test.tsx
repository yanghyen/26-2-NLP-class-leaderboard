import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ replace: vi.fn(), login: vi.fn(), me: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: mocks.replace }) }));
vi.mock("../lib/api", () => ({
  AUTH_EXPIRED_EVENT: "nlp-auth-expired",
  api: { login: mocks.login, me: mocks.me }
}));

import { AuthProvider, useAuth } from "./auth-provider";

const admin = {
  id: "student-1", nickname: "NLPHero", avatar_id: "brain", avatar_emoji: "🧠",
  role: "ADMIN" as const, student_number: null, real_name: null,
  password_reset_required: false
};
const wrapper = ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>;

describe("AuthProvider", () => {
  beforeEach(() => {
    sessionStorage.clear();
    mocks.replace.mockReset();
    mocks.login.mockReset();
    mocks.me.mockReset();
  });

  it("stores a token only after the current user is verified", async () => {
    mocks.login.mockResolvedValue({ access_token: "safe-token", token_type: "bearer" });
    mocks.me.mockResolvedValue(admin);
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => { await result.current.login("RootTA", "password"); });
    expect(result.current.user?.nickname).toBe("NLPHero");
    expect(sessionStorage.getItem("nlp-admin-token")).toBe("safe-token");
  });

  it("does not retain a token when user verification fails", async () => {
    mocks.login.mockResolvedValue({ access_token: "rejected-token", token_type: "bearer" });
    mocks.me.mockRejectedValue(new Error("verification failed"));
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await expect(result.current.login("student", "password")).rejects.toThrow("verification failed");
    expect(sessionStorage.getItem("nlp-admin-token")).toBeNull();
  });

  it("clears the session and redirects on logout", async () => {
    sessionStorage.setItem("nlp-admin-token", "old-token");
    mocks.me.mockResolvedValue(admin);
    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => result.current.logout());
    expect(sessionStorage.getItem("nlp-admin-token")).toBeNull();
    expect(mocks.replace).toHaveBeenCalledWith("/login");
  });
});
