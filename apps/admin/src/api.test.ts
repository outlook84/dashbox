import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError, login, logout, onUnauthorized, readConfig } from "./api";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status || 200,
    statusText: init.statusText,
    headers: { "Content-Type": "application/json", ...(init.headers || {}) }
  });
}

describe("api", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    onUnauthorized(() => undefined);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("sends json requests with same-origin credentials", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }));

    await expect(login("abc123")).resolves.toEqual({ ok: true });

    expect(fetchMock).toHaveBeenCalledWith("/admin/api/login", expect.objectContaining({
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_code: "abc123" })
    }));
  });

  test("calls the unauthorized handler for 401 responses", async () => {
    const fetchMock = vi.mocked(fetch);
    const handler = vi.fn();
    onUnauthorized(handler);
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "login required" }, { status: 401, statusText: "Unauthorized" }));

    await expect(logout()).rejects.toBeInstanceOf(ApiError);

    expect(handler).toHaveBeenCalledTimes(1);
  });

  test("uses detail or error fields when a request fails", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ error: "bad config" }, { status: 400, statusText: "Bad Request" }));

    await expect(readConfig()).rejects.toMatchObject({
      message: "bad config",
      status: 400,
      body: { error: "bad config" }
    });
  });
});
