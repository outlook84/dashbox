import type { AdminSchema, AdminStatus, ApiOk, ConfigResponse, CookieStatus, NormalizeResponse, SessionState } from "./types";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

let unauthorizedHandler: (() => void) | undefined;

export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler;
}

async function requestJson<T>(path: string, init: RequestInit = {}, options: { skipUnauthorized?: boolean } = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers || {})
    }
  });
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (response.status === 401 && !options.skipUnauthorized) {
    unauthorizedHandler?.();
  }
  if (!response.ok) {
    const message = errorMessage(body) || response.statusText || `HTTP ${response.status}`;
    throw new ApiError(message, response.status, body);
  }
  return body as T;
}

function errorMessage(body: unknown): string {
  if (!body || typeof body !== "object") return "";
  const data = body as Record<string, unknown>;
  return String(data.error || data.detail || "");
}

export function session() {
  return requestJson<SessionState>("/admin/api/session", {}, { skipUnauthorized: true });
}

export function setup(setupCode: string, accessCode: string) {
  return requestJson<ApiOk>("/admin/api/setup", {
    method: "POST",
    body: JSON.stringify({ setup_code: setupCode, access_code: accessCode })
  }, { skipUnauthorized: true });
}

export function login(accessCode: string) {
  return requestJson<ApiOk>("/admin/api/login", {
    method: "POST",
    body: JSON.stringify({ access_code: accessCode })
  }, { skipUnauthorized: true });
}

export function logout() {
  return requestJson<ApiOk>("/admin/api/logout", { method: "POST" });
}

export function status() {
  return requestJson<AdminStatus>("/admin/api/status");
}

export function readConfig() {
  return requestJson<ConfigResponse>("/admin/api/config");
}

export function readSchema() {
  return requestJson<AdminSchema>("/admin/api/schema");
}

export function validateConfig(config: Record<string, unknown>) {
  return requestJson<ApiOk>("/admin/api/config/validate", {
    method: "POST",
    body: JSON.stringify({ config })
  });
}

export function normalizeConfig(config: Record<string, unknown>) {
  return requestJson<NormalizeResponse>("/admin/api/config/normalize", {
    method: "POST",
    body: JSON.stringify({ config })
  });
}

export function saveConfig(config: Record<string, unknown>) {
  return requestJson<ConfigResponse & ApiOk>("/admin/api/config", {
    method: "PUT",
    body: JSON.stringify({ config })
  });
}

export function cookieStatus() {
  return requestJson<CookieStatus>("/admin/api/cookies");
}

export function reloadCookies(load: boolean) {
  return requestJson<CookieStatus>(`/admin/api/cookies/reload?load=${load ? "true" : "false"}`, {
    method: "POST"
  });
}

export function hashSubscriptionAccessCode(accessCode: string) {
  return requestJson<{ ok: boolean; access_code_hash: string }>("/admin/api/subscription-access-code/hash", {
    method: "POST",
    body: JSON.stringify({ access_code: accessCode })
  });
}

export function updateAccessCode(currentAccessCode: string, newAccessCode: string) {
  return requestJson<ApiOk>("/admin/api/access-code", {
    method: "POST",
    body: JSON.stringify({
      current_access_code: currentAccessCode,
      new_access_code: newAccessCode
    })
  });
}
