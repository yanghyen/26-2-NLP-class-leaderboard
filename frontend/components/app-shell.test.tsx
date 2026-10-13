import { render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/admin",
  useRouter: () => ({ replace: mocks.replace })
}));
vi.mock("./auth-provider", () => ({
  useAuth: () => ({
    user: { role: "STUDENT", nickname: "NLPHero", avatar_emoji: "🧠" },
    token: "token", loading: false, logout: vi.fn(), login: vi.fn()
  })
}));

import { ProtectedShell } from "./app-shell";

describe("ProtectedShell", () => {
  it("redirects a student away from administrator routes", async () => {
    render(<ProtectedShell><p>secret admin content</p></ProtectedShell>);
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/login"));
    expect(document.body.textContent).not.toContain("secret admin content");
  });
});
