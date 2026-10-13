import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, request } from "./api";

afterEach(() => vi.restoreAllMocks());

describe("API error boundary", () => {
  it("maps validation codes to stable messages", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { code: "UNSUPPORTED_FILE", message: "server path /private/tmp/x" } }),
      { status: 400, headers: { "content-type": "application/json" } }
    )));
    await expect(request("/submission")).rejects.toMatchObject({
      code: "UNSUPPORTED_FILE",
      message: "ZIP에 허용되지 않은 파일이 포함되어 있습니다."
    });
  });

  it("does not expose server details from a 500 response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Traceback: database password" }),
      { status: 500, headers: { "content-type": "application/json" } }
    )));
    try {
      await request("/broken");
      throw new Error("expected rejection");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as Error).message).not.toContain("Traceback");
      expect((error as Error).message).toContain("서버와 통신");
    }
  });

  it("sends task policy edits as an authenticated PATCH", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ slug: "test" }), {
      status: 200,
      headers: { "content-type": "application/json" }
    }));
    vi.stubGlobal("fetch", fetchMock);

    await api.updateTask("admin-token", "test", {
      config: {
        allowed_models: ["course/bert-base"],
        artifact_policy: { allowed_architectures: ["BertForSequenceClassification"] }
      }
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/tasks/test"),
      expect.objectContaining({ method: "PATCH" })
    );
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(options.headers).get("Authorization")).toBe("Bearer admin-token");
  });

  it("maps forbidden task edits to the shared permission message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "관리자 권한이 필요합니다." }),
      { status: 403, headers: { "content-type": "application/json" } }
    )));
    await expect(api.updateTask("student-token", "test", { title: "No" })).rejects.toMatchObject({
      status: 403,
      message: "관리자 권한이 필요합니다."
    });
  });
});

describe("practice API privacy and admin CSV", () => {
  it("queries public UUID status without an Authorization header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "QUEUED" })));
    vi.stubGlobal("fetch", fetchMock);
    await api.submission("11111111-1111-1111-1111-111111111111");
    expect(new Headers((fetchMock.mock.calls[0][1] as RequestInit).headers).has("Authorization")).toBe(false);
  });
  it("downloads CSV through the admin Bearer endpoint", async () => {
    const { downloadResultsCsv } = await import("./api");
    const fetchMock = vi.fn().mockResolvedValue(new Response("student_number,nickname\n", { headers: { "content-type": "text/csv" } }));
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(URL, "createObjectURL", { value: vi.fn().mockReturnValue("blob:test"), configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    await downloadResultsCsv("admin-token", "sentiment");
    expect(fetchMock.mock.calls[0][0]).toContain("/admin/tasks/sentiment/results.csv");
    expect(new Headers((fetchMock.mock.calls[0][1] as RequestInit).headers).get("Authorization")).toBe("Bearer admin-token");
    expect(click).toHaveBeenCalledOnce();
  });
});
