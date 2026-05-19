type Json = Record<string, unknown>;

declare const req:
  | undefined
  | ((url: string, options?: Record<string, unknown>) => { content?: string; code?: number | string });
declare const http:
  | undefined
  | ((url: string, options?: Record<string, unknown>) => { content?: string; code?: number | string });
declare const local:
  | undefined
  | {
      get?: (rule: string, key: string) => string | undefined;
      set?: (rule: string, key: string, value: string) => void;
      delete?: (rule: string, key: string) => void;
    };

let gateway = "";
let assetBase = "";
let order = "source";
const refreshID = "__refresh__";
const authID = "__dashbox_auth__";
const accessCodeStorageRule = "dashbox_tvbox";
let accessToken = "";
let storageScope = "";
let defaultVodStyle = "list";
const labelKeys = [
  "refreshDirectory",
  "refreshRejected",
  "currentDirectory",
  "playCurrentDirectory",
  "play",
  "episode",
  "items",
  "authTitle",
  "authEmpty",
  "authPrompt",
  "authBackspace",
  "authSubmit",
  "authClear",
  "authSuccessRestart",
  "authFailed",
];
let labels: Record<string, string> = emptyLabels();

function emptyLabels(): Record<string, string> {
  const out: Record<string, string> = {};
  for (const key of labelKeys) out[key] = "";
  return out;
}

function normalizeBaseURL(value: string): string {
  return String(value || "").replace(/\/+$/, "");
}

function parseJSON(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function resolveStringInput(value: string | Json, keys: string[], allowRawString: boolean): string {
  let current: unknown = value;
  for (let i = 0; i < 3; i += 1) {
    if (typeof current === "string") {
      const parsed = parseJSON(current);
      if (parsed === current) return allowRawString ? current : "";
      current = parsed;
      continue;
    }
    if (current && typeof current === "object") {
      const obj = current as Json;
      for (const key of keys) {
        const direct = obj[key];
        if (typeof direct === "string") return direct;
      }
      if (obj.ext !== undefined) {
        current = obj.ext;
        continue;
      }
    }
    break;
  }
  return "";
}

function resolveGatewayInput(value: string | Json): string {
  return resolveStringInput(value, ["gateway", "url"], true);
}

function resolveAssetBaseInput(value: string | Json): string {
  return resolveStringInput(value, ["assetBase", "asset_base", "base"], false);
}

function resolveStorageScopeInput(value: string | Json): string {
  return resolveStringInput(value, ["skey", "storageKey", "storage_key"], false);
}

function resolveLabelsInput(value: string | Json): Record<string, string> {
  let current: unknown = value;
  for (let i = 0; i < 3; i += 1) {
    if (typeof current === "string") {
      const parsed = parseJSON(current);
      if (parsed === current) return {};
      current = parsed;
      continue;
    }
    if (current && typeof current === "object") {
      const obj = current as Json;
      if (obj.labels && typeof obj.labels === "object") {
        const out: Record<string, string> = {};
        const rawLabels = obj.labels as Json;
        for (const key of labelKeys) {
          const value = rawLabels[key];
          if (typeof value === "string" && value) out[key] = value;
        }
        return out;
      }
      if (obj.ext !== undefined) {
        current = obj.ext;
        continue;
      }
    }
    break;
  }
  return {};
}

function resolveVodStyleInput(value: string | Json): string {
  return normalizeVodStyle(resolveStringInput(value, ["vodStyle", "vod_style"], false));
}

function normalizeVodStyle(value: string): string {
  return value === "landscape" || value === "portrait" ? value : "list";
}

function vodStyleFields(value: string): Json {
  const style = normalizeVodStyle(value);
  if (style === "landscape") return { style: { type: "rect", ratio: 1.78 }, ratio: 1.78, land: 1 };
  if (style === "portrait") return { style: { type: "rect", ratio: 0.56 }, ratio: 0.56 };
  return { style: { type: "list", ratio: 1.0 }, ratio: 1.0 };
}

function typeFlagForVodStyle(value: string): string {
  return normalizeVodStyle(value) === "list" ? "1" : "2";
}

function defaultVodStyleFields(): Json {
  return vodStyleFields(defaultVodStyle);
}

function label(key: string): string {
  return labels[key] || "";
}

function queryString(params: Record<string, string> = {}): string {
  const parts: string[] = [];
  for (const key of Object.keys(params)) {
    const value = params[key];
    if (value === "") continue;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
  }
  return parts.join("&");
}

function request(path: string, params: Record<string, string> = {}): string {
  return requestWithAuth(path, params, true);
}

function responseContent(response: { content?: string; code?: number | string } | undefined): string {
  if (!response || response.content === undefined) throw new Error("gateway request failed");
  return String(response.content);
}

function requestWithAuth(path: string, params: Record<string, string> = {}, allowRetry: boolean): string {
  if (!accessToken) authenticateInitial();
  if (!gateway) throw new Error("dashbox gateway is not initialized");
  const query = queryString(params);
  const url = `${gateway}${path}${query ? `?${query}` : ""}`;
  const httpReq = typeof req === "function" ? req : typeof http === "function" ? http : null;
  if (!httpReq) throw new Error("TVBox req helper is not available");
  const headers: Record<string, string> = {};
  if (accessToken) headers["X-Access-Token"] = accessToken;
  const response = httpReq(url, { method: "get", timeout: 60000, async: false, headers });
  const content = responseContent(response);
  if (!isUnauthorizedResult(content)) return content;
  accessToken = "";
  if (allowRetry && authenticateWithStoredCode()) return requestWithAuth(path, params, false);
  if (allowRetry && authenticateAnonymous()) return requestWithAuth(path, params, false);
  return authDirectoryResult();
}

function postAuth(code = ""): Json {
  if (!gateway) return {};
  const httpReq = typeof req === "function" ? req : typeof http === "function" ? http : null;
  if (!httpReq) return {};
  const response = httpReq(`${gateway}/auth`, {
    method: "post",
    timeout: 60000,
    async: false,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  const content = responseContent(response);
  return parseResult(content);
}

function authenticateAnonymous(): boolean {
  const result = postAuth();
  const token = stringValue(result.access_token);
  if (result.ok === true && token) {
    accessToken = token;
    return true;
  }
  accessToken = "";
  return false;
}

function authenticateInitial(): boolean {
  return authenticateWithStoredCode() || authenticateAnonymous();
}

function authenticateWithStoredCode(): boolean {
  const code = storedAccessCode();
  if (!code) return false;
  return authenticateWithCode(code, false);
}

function authenticateWithCode(code: string, persist: boolean): boolean {
  const result = postAuth(code);
  const token = stringValue(result.access_token);
  if (result.ok === true && token) {
    accessToken = token;
    if (persist) storeAccessCode(code);
    return true;
  }
  accessToken = "";
  clearStoredAccessCode();
  return false;
}

function isUnauthorizedResult(raw: string): boolean {
  const result = parseResult(raw);
  return result.error === "unauthorized";
}

function parseResult(raw: string): Json {
  try {
    return JSON.parse(raw) as Json;
  } catch {
    return {};
  }
}

function storageKey(kind: "access_code"): string {
  return `${kind}:${storageScope || normalizeStorageScope(gateway)}`;
}

function normalizeStorageScope(value: string): string {
  const match = String(value || "").match(/^([a-zA-Z][a-zA-Z0-9+.-]*:)?\/\/([^/]+)(\/[^?#]*)?/);
  const protocol = (match && match[1] ? match[1].replace(/:$/, "") : "").toLowerCase();
  const host = match && match[2] ? match[2] : "";
  const path = match && match[3] ? match[3] : "";
  const scoped = protocol && host && path
    ? `${protocol}_${host}_${path}`
    : value;
  return scoped.replace(/[^A-Za-z0-9._-]+/g, "_");
}

function storedAccessCode(): string {
  try {
    if (typeof local === "undefined" || !local || typeof local.get !== "function") return "";
    const key = storageKey("access_code");
    return String(local.get(accessCodeStorageRule, key) || "");
  } catch {
    return "";
  }
}

function storeAccessCode(code: string): void {
  try {
    if (typeof local === "undefined" || !local || typeof local.set !== "function") return;
    const key = storageKey("access_code");
    local.set(accessCodeStorageRule, key, code);
  } catch {
    return;
  }
}

function clearStoredAccessCode(): void {
  try {
    if (typeof local === "undefined" || !local || typeof local.delete !== "function") return;
    const key = storageKey("access_code");
    local.delete(accessCodeStorageRule, key);
  } catch {
    return;
  }
}

function authDirectoryResult(input = "", message = ""): string {
  const list: Json[] = [];
  const masked = input ? "*".repeat(input.length) : label("authEmpty");
  const title = label("authTitle");
  list.push(authVod(`${authID}/noop/${input}`, title ? `${title}：${masked}` : masked, "folder", message || label("authPrompt")));
  for (let digit = 1; digit <= 9; digit += 1) list.push(authVod(`${authID}/digit/${digit}/${input}`, String(digit), "folder"));
  list.push(authVod(`${authID}/backspace/${input}`, label("authBackspace"), "folder"));
  list.push(authVod(`${authID}/digit/0/${input}`, "0", "folder"));
  list.push(authVod(`${authID}/submit/${input}`, label("authSubmit"), "folder"));
  list.push(authVod(`${authID}/clear/${input}`, label("authClear"), "folder"));
  return JSON.stringify({
    class: [{
      type_id: authID,
      type_name: label("authTitle"),
      type_flag: typeFlagForVodStyle(defaultVodStyle),
      ...defaultVodStyleFields(),
    }],
    filters: {},
    list,
    ...defaultVodStyleFields(),
    page: 1,
    pagecount: 1,
    limit: list.length,
    total: list.length,
  });
}

function authVod(id: string, name: string, tag: string, remarks = ""): Json {
  return {
    vod_id: id,
    vod_name: name,
    vod_pic: refreshIconURL(),
    vod_remarks: remarks,
    vod_tag: tag,
    type_flag: typeFlagForVodStyle(defaultVodStyle),
    ...defaultVodStyleFields(),
  };
}

function authSuccessResult(): string {
  const list = [authVod(`${authID}/noop/`, label("authSuccessRestart"), "folder")];
  return JSON.stringify({
    list,
    page: 1,
    pagecount: 1,
    limit: list.length,
    total: list.length,
  });
}

function authCategory(tid: string): string {
  const parts = tid.split("/");
  const action = parts[1] || "";
  const digit = parts[2] || "";
  const inputStart = action === "digit" ? 3 : 2;
  const input = parts.slice(inputStart).join("/").replace(/[^0-9]/g, "").slice(0, 12);
  if (action === "digit") {
    return authDirectoryResult((input + digit.replace(/[^0-9]/g, "").slice(0, 1)).slice(0, 12));
  }
  if (action === "backspace") return authDirectoryResult(input.slice(0, -1));
  if (action === "noop") return authDirectoryResult(input);
  if (action === "clear") {
    accessToken = "";
    clearStoredAccessCode();
    return authDirectoryResult("");
  }
  if (action === "submit") {
    if (input.length >= 4 && authenticateWithCode(input, true)) {
      return authSuccessResult();
    }
    return authDirectoryResult("", label("authFailed"));
  }
  return authDirectoryResult(input);
}

function normalizeResult(raw: string): string {
  return JSON.stringify(parseResult(raw));
}

function refreshIconURL(): string {
  const root = assetBase || gatewayRootFallback();
  return root ? `${root}/assets/icons/refresh.png` : "/assets/icons/refresh.png";
}

function gatewayRootFallback(): string {
  for (const prefix of ["/tvbox/", "/s/"]) {
    const index = gateway.lastIndexOf(prefix);
    if (index >= 0) return gateway.slice(0, index);
  }
  return "";
}

function resolveOrder(extend: unknown): string {
  let current = extend;
  for (let i = 0; i < 3; i += 1) {
    if (typeof current === "string") {
      const parsed = parseJSON(current);
      if (parsed === current) return current === "reverse" ? "reverse" : "source";
      current = parsed;
      continue;
    }
    if (current && typeof current === "object") {
      const value = (current as Json).order;
      return value === "reverse" ? "reverse" : "source";
    }
    break;
  }
  return "source";
}

function orderedResult(raw: string, selectedOrder: string): string {
  const result = parseResult(raw);
  if (Array.isArray(result.list)) result.list = orderedItems(result.list, selectedOrder);
  return JSON.stringify(result);
}

function orderedItems<T>(items: T[], selectedOrder: string): T[] {
  if (selectedOrder !== "reverse") return items;
  const indexedItems = items.filter(hasOrderedIndex).reverse();
  if (!indexedItems.length) return items;
  let index = 0;
  return items.map((item) => hasOrderedIndex(item) ? indexedItems[index++] : item);
}

function hasOrderedIndex(item: unknown): boolean {
  if (!item || typeof item !== "object") return false;
  const vod = item as Json;
  return vod.dashbox_index !== undefined
    || stringValue(vod.dashbox_playlist_url).includes("dashbox_index=")
    || stringValue(vod.vod_play_url).includes("dashbox_index=");
}

function fetchCategoryRaw(tid: string, extend?: unknown, refresh = false): string {
  const params: Record<string, string> = {
    tid,
    extend: typeof extend === "string" ? extend : JSON.stringify(extend || {}),
  };
  if (refresh) params.refresh = "1";
  return request("/category", params);
}

function refreshDirectoryVod(tid: string, result: Json): Json {
  const refresh = result.dashbox_refresh && typeof result.dashbox_refresh === "object"
    ? result.dashbox_refresh as Json
    : {};
  const rejected = refresh.rejected === true;
  const vod: Json = {
    vod_id: `${refreshID}/${tid}`,
    vod_name: label("refreshDirectory"),
    vod_pic: refreshIconURL(),
    vod_remarks: rejected ? label("refreshRejected") : stringValue(result.dashbox_category_name) || label("currentDirectory"),
    vod_tag: "folder",
    type_flag: "1",
  };
  copyStyleFields(result, vod);
  return vod;
}

function copyStyleFields(source: Json, target: Json): void {
  const style = source.style;
  if (style && typeof style === "object") target.style = style;
  if (typeof source.ratio === "number") target.ratio = source.ratio;
  if (typeof source.land === "number") target.land = source.land;
  if (typeof source.circle === "number") target.circle = source.circle;
}

function withRefreshDirectoryVod(raw: string, tid: string): string {
  const result = parseResult(raw);
  if (result.dashbox_refreshable !== true) return JSON.stringify(result);
  const list = Array.isArray(result.list) ? result.list : [];
  result.list = [refreshDirectoryVod(tid, result), ...list];
  if (typeof result.limit === "number") result.limit += 1;
  if (typeof result.total === "number") result.total += 1;
  return JSON.stringify(result);
}

function categoryResponse(tid: string, extend?: unknown): string {
  order = resolveOrder(extend);
  const raw = fetchCategoryRaw(tid, extend);
  return withRefreshDirectoryVod(orderedResult(raw, order), tid);
}

function homeResponse(): string {
  const raw = request("/home");
  if (isUnauthorizedResult(raw)) return authDirectoryResult();
  const home = parseResult(raw);
  const classes = Array.isArray(home.class) ? home.class as Array<{ type_id?: string }> : [];
  const first = classes.length ? stringValue(classes[0].type_id) : "";
  if (first === authID) return JSON.stringify(home);
  if (first) {
    const categoryRaw = fetchCategoryRaw(first);
    if (isUnauthorizedResult(categoryRaw)) return authDirectoryResult();
    const category = parseResult(categoryRaw);
    if (Array.isArray(category.list)) home.list = category.list;
  }
  return JSON.stringify(home);
}

function refreshCategory(tid: string, extend?: unknown): string {
  const target = tid.slice(`${refreshID}/`.length);
  if (!target) return normalizeResult(JSON.stringify({ list: [] }));
  order = resolveOrder(extend);
  const raw = fetchCategoryRaw(target, extend, true);
  return withRefreshDirectoryVod(orderedResult(raw, order), target);
}

function orderedDetailResult(raw: string, selectedOrder: string): string {
  const result = parseResult(raw);
  if (selectedOrder !== "reverse" || !Array.isArray(result.list)) return JSON.stringify(result);
  result.list = result.list.map((item) => {
    if (!item || typeof item !== "object") return item;
    const vod = item as Json;
    if (typeof vod.vod_play_url !== "string" || !vod.vod_play_url.includes("dashbox_index=")) return vod;
    return {
      ...vod,
      vod_play_url: vod.vod_play_url
        .split("$$$")
        .map((source) => source.split("#").filter(Boolean).reverse().join("#"))
        .join("$$$"),
    };
  });
  return JSON.stringify(result);
}

function detailResponse(id: string | string[]): string {
  const value = Array.isArray(id) ? id[0] : id;
  return orderedDetailResult(request("/detail", { id: value }), order);
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

const spider = {
  init(ext: string | Json) {
    const nextGateway = normalizeBaseURL(resolveGatewayInput(ext));
    assetBase = normalizeBaseURL(resolveAssetBaseInput(ext));
    labels = { ...emptyLabels(), ...resolveLabelsInput(ext) };
    defaultVodStyle = resolveVodStyleInput(ext);
    gateway = nextGateway;
    storageScope = normalizeStorageScope(resolveStorageScopeInput(ext) || gateway);
    accessToken = "";
  },

  home(_filter?: boolean) {
    return homeResponse();
  },

  homeContent(_filter?: boolean) {
    return homeResponse();
  },

  homeVod() {
    const home = parseResult(homeResponse());
    return JSON.stringify({ list: Array.isArray(home.list) ? home.list : [] });
  },

  category(tid: string, _pg?: string, _filter?: boolean, extend?: unknown) {
    if (tid.startsWith(authID)) return authCategory(tid);
    if (tid.startsWith(`${refreshID}/`)) return refreshCategory(tid, extend);
    return categoryResponse(tid, extend);
  },

  categoryContent(tid: string, pg?: string, filter?: boolean, extend?: unknown) {
    return this.category(tid, pg, filter, extend);
  },

  detail(id: string | string[]) {
    return detailResponse(id);
  },

  detailContent(ids: string[]) {
    return detailResponse(ids);
  },

  search(key: string, _quick?: boolean, _pg?: string) {
    return normalizeResult(request("/search", { key }));
  },

  searchContent(key: string, quick?: boolean) {
    return this.search(key, quick, "1");
  },

  play(_flag: string, id: string, _vipFlags?: string[]) {
    return normalizeResult(request("/play", { id }));
  },

  playerContent(flag: string, id: string, vipFlags?: string[]) {
    return this.play(flag, id, vipFlags);
  },

  proxy() {
    return "";
  },

  destroy() {},
};

export default spider;

export function __jsEvalReturn() {
  return spider;
}
