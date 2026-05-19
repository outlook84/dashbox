import { afterEach, describe, expect, test } from "vitest";

import spider from "./index";

type ReqCall = {
  url: string;
  options?: Record<string, unknown>;
};

type ReqResponse = {
  code?: number | string;
  content?: string;
};

declare global {
  var req: ((url: string, options?: Record<string, unknown>) => ReqResponse) | undefined;
  var local: {
    get?: (rule: string, key: string) => string | undefined;
    set?: (rule: string, key: string, value: string) => void;
    delete?: (rule: string, key: string) => void;
  } | undefined;
}

function parse(value: string): Record<string, unknown> {
  return JSON.parse(value) as Record<string, unknown>;
}

function setupReq(handler: (url: string, options?: Record<string, unknown>) => ReqResponse): ReqCall[] {
  const calls: ReqCall[] = [];
  globalThis.req = (url, options) => {
    calls.push({ url, options });
    return handler(url, options);
  };
  return calls;
}

const serverLabels = {
  refreshDirectory: "刷新此列表",
  refreshRejected: "稍后重试",
  currentDirectory: "当前目录",
  playCurrentDirectory: "点击播放$$$当前目录",
  play: "播放",
  episode: "第{index}集",
  items: "{count}项",
  authTitle: "访问码",
  authEmpty: "未输入",
  authPrompt: "请输入访问码",
  authBackspace: "退格",
  authSubmit: "确认",
  authClear: "清空",
  authSuccessRestart: "认证成功，请重启应用",
  authFailed: "访问码错误",
};

function init(ext: Record<string, unknown> = {}) {
  spider.init({
    gateway: `http://127.0.0.1:18990/tvbox/${Math.random().toString(36).slice(2)}`,
    assetBase: "http://127.0.0.1:18990",
    skey: `test_${Math.random().toString(36).slice(2)}`,
    labels: serverLabels,
    ...ext,
  });
}

afterEach(() => {
  globalThis.req = undefined;
  globalThis.local = undefined;
});

describe("tvbox spider runtime", () => {
  test("uses scoped gateway paths for backend requests", () => {
    const calls = setupReq((url) => {
      if (url.endsWith("/auth")) return { content: JSON.stringify({ ok: true, access_token: "token", expires_at: 123 }) };
      if (url.includes("/home")) return { content: JSON.stringify({ class: [] }) };
      if (url.includes("/category")) return { content: JSON.stringify({ list: [] }) };
      if (url.includes("/detail")) return { content: JSON.stringify({ list: [] }) };
      if (url.includes("/search")) return { content: JSON.stringify({ list: [] }) };
      if (url.includes("/play")) return { content: JSON.stringify({ url: "https://cdn.example/video.mp4" }) };
      return { content: "{}" };
    });
    init({ gateway: "http://127.0.0.1:18990/tvbox/main" });

    spider.home(true);
    spider.category("source", "1", true, {});
    spider.detail("video");
    spider.search("keyword");
    spider.play("dashbox", "video", []);

    expect(calls.map((call) => call.url)).toEqual([
      "http://127.0.0.1:18990/tvbox/main/auth",
      "http://127.0.0.1:18990/tvbox/main/home",
      "http://127.0.0.1:18990/tvbox/main/category?tid=source&extend=%7B%7D",
      "http://127.0.0.1:18990/tvbox/main/detail?id=video",
      "http://127.0.0.1:18990/tvbox/main/search?key=keyword",
      "http://127.0.0.1:18990/tvbox/main/play?id=video",
    ]);
    expect(calls.every((call) => !call.url.includes("/api/tvbox/"))).toBe(true);
  });

  test("gets an anonymous token before protocol requests", () => {
    const calls = setupReq((url) => {
      if (url.endsWith("/auth")) return { content: JSON.stringify({ ok: true, access_token: "anon-token", expires_at: 123 }) };
      if (url.includes("/play")) return { content: JSON.stringify({ url: "https://cdn.example/video.mp4" }) };
      return { content: "{}" };
    });
    init({ gateway: "http://127.0.0.1:18990/tvbox/main" });

    spider.play("dashbox", "video", []);

    expect(calls[0].url).toBe("http://127.0.0.1:18990/tvbox/main/auth");
    expect(calls[0].options?.body).toBe(JSON.stringify({ code: "" }));
    expect(calls[1].options?.headers).toEqual({ "X-Access-Token": "anon-token" });
  });

  test("uses stored access code before anonymous auth", () => {
    const calls = setupReq((url) => {
      if (url.endsWith("/auth")) return { content: JSON.stringify({ ok: true, access_token: "stored-token", expires_at: 123 }) };
      if (url.includes("/play")) return { content: JSON.stringify({ url: "https://cdn.example/video.mp4" }) };
      return { content: "{}" };
    });
    globalThis.local = {
      get() {
        return "1234";
      },
    };
    init({ gateway: "http://127.0.0.1:18990/tvbox/main", skey: "test_storage_scope" });

    spider.play("dashbox", "video", []);

    expect(calls[0].url).toBe("http://127.0.0.1:18990/tvbox/main/auth");
    expect(calls[0].options?.body).toBe(JSON.stringify({ code: "1234" }));
    expect(calls[1].options?.headers).toEqual({ "X-Access-Token": "stored-token" });
  });

  test("uses explicit asset base for refresh and auth icons", () => {
    setupReq(() => ({ content: JSON.stringify({ error: "unauthorized" }) }));
    init({ gateway: "http://127.0.0.1:18990/tvbox/main", assetBase: "http://assets.example/base/" });

    const home = parse(spider.home(true));
    const list = home.list as Array<Record<string, unknown>>;

    expect(list[0].vod_pic).toBe("http://assets.example/base/assets/icons/refresh.png");
  });

  test("renders auth UI with configured labels and style", () => {
    setupReq(() => ({ content: JSON.stringify({ error: "unauthorized" }) }));
    init({
      vodStyle: "landscape",
      labels: {
        authTitle: "Code",
        authEmpty: "empty",
        authPrompt: "enter code",
        authBackspace: "back",
        authSubmit: "go",
        authClear: "clear",
      },
    });

    const home = parse(spider.home(true));
    const classes = home.class as Array<Record<string, unknown>>;
    const list = home.list as Array<Record<string, unknown>>;

    expect(classes[0]).toMatchObject({ type_id: "__dashbox_auth__", type_name: "Code", type_flag: "2" });
    expect(classes[0].style).toEqual({ type: "rect", ratio: 1.78 });
    expect(home.filters).toEqual({});
    expect(list[0]).toMatchObject({ vod_name: "Code：empty", vod_remarks: "enter code", type_flag: "2" });
    expect(list.map((item) => item.vod_name)).toEqual(expect.arrayContaining(["back", "go", "clear"]));
  });

  test("does not keep built-in localized copy when labels are missing", () => {
    setupReq(() => ({ content: JSON.stringify({ error: "unauthorized" }) }));
    init({ labels: {} });

    const home = parse(spider.home(true));
    const classes = home.class as Array<Record<string, unknown>>;
    const list = home.list as Array<Record<string, unknown>>;

    expect(classes[0].type_name).toBe("");
    expect(list[0].vod_name).toBe("");
    expect(list.some((item) => item.vod_name === "访问码")).toBe(false);
  });

  test("auth submit reads current input and returns success page", () => {
    const calls = setupReq((url) => {
      if (url.endsWith("/auth")) {
        return { content: JSON.stringify({ ok: true, access_token: "token", expires_at: 123 }) };
      }
      return { content: JSON.stringify({ error: "unexpected" }) };
    });
    globalThis.local = {
      get(rule, key) {
        expect(arguments.length).toBe(2);
        expect(rule).toBe("dashbox_tvbox");
        expect(key).toContain("access_code:");
        return "";
      },
      set(rule, key, value) {
        expect(arguments.length).toBe(3);
        expect(rule).toBe("dashbox_tvbox");
        expect(key).toContain("access_code:");
        expect(value).toBe("1234");
      },
      delete(rule, key) {
        expect(arguments.length).toBe(2);
        expect(rule).toBe("dashbox_tvbox");
        expect(key).toContain("access_code:");
      },
    };
    init({ gateway: "http://127.0.0.1:18990/tvbox/main", skey: "test_storage_scope" });

    const category = parse(spider.category("__dashbox_auth__/submit/1234", "1", true, {}));
    const list = category.list as Array<Record<string, unknown>>;

    expect(calls[0].url).toBe("http://127.0.0.1:18990/tvbox/main/auth");
    expect(calls[0].options?.body).toBe(JSON.stringify({ code: "1234" }));
    expect(list).toHaveLength(1);
    expect(list[0].vod_name).toBe("认证成功，请重启应用");
  });

  test("auth actions keep slash-delimited current input", () => {
    setupReq(() => ({ content: JSON.stringify({ error: "unauthorized" }) }));
    init();

    const category = parse(spider.category("__dashbox_auth__/digit/5/12/34", "1", true, {}));
    const list = category.list as Array<Record<string, unknown>>;

    expect(list[0].vod_id).toBe("__dashbox_auth__/noop/12345");
    expect(list[0].vod_name).toBe("访问码：*****");
  });

  test("home preserves classes and shows auth UI when the first category is unauthorized", () => {
    setupReq((url) => {
      if (url.includes("/home")) {
        return { content: JSON.stringify({ class: [{ type_id: "main", type_name: "Main" }] }) };
      }
      if (url.includes("/category") && url.includes("tid=main")) {
        return { content: JSON.stringify({ error: "unauthorized" }) };
      }
      return { content: "{}" };
    });
    init();

    const home = parse(spider.home(true));
    const classes = home.class as Array<Record<string, unknown>>;
    const list = home.list as Array<Record<string, unknown>>;

    expect(classes[0].type_id).toBe("main");
    expect(list[0].vod_name).toBe("访问码：未输入");
  });

  test("home returns an empty object when unauthorized response has no JSON body", () => {
    setupReq(() => ({ code: 401, content: "" }));
    init();

    expect(parse(spider.home(true))).toEqual({});
  });

  test("storage scope keeps the gateway path when no explicit key is configured", () => {
    setupReq((url) => {
      if (url.endsWith("/auth")) {
        return { content: JSON.stringify({ ok: true, access_token: "token", expires_at: 123 }) };
      }
      return { content: "{}" };
    });
    const keys: string[] = [];
    globalThis.local = {
      set(_rule, key) {
        keys.push(key);
      },
    };
    init({ gateway: "http://127.0.0.1:18990/tvbox/main", skey: "" });

    spider.category("__dashbox_auth__/submit/1234", "1", true, {});

    expect(keys[0]).toContain("tvbox_main");
    expect(keys[0]).not.toBe("access_code:http_127.0.0.1_18990");
  });

  test("refresh vod inherits category style fields", () => {
    setupReq(() => ({
      content: JSON.stringify({
        dashbox_category_name: "Styled",
        dashbox_refreshable: true,
        style: { type: "rect", ratio: 1.78 },
        ratio: 1.78,
        land: 1,
        list: [],
        limit: 0,
        total: 0,
      }),
    }));
    init();

    const category = parse(spider.category("styled", "1", true, {}));
    const list = category.list as Array<Record<string, unknown>>;

    expect(list[0]).toMatchObject({
      vod_id: "__refresh__/styled",
      vod_remarks: "Styled",
      style: { type: "rect", ratio: 1.78 },
      ratio: 1.78,
      land: 1,
    });
  });

  test("refresh vod is omitted when backend marks category not refreshable", () => {
    setupReq(() => ({
      content: JSON.stringify({
        dashbox_category_name: "Config",
        dashbox_refreshable: false,
        list: [{ vod_id: "child", vod_name: "Child" }],
      }),
    }));
    init();

    const category = parse(spider.category("config", "1", true, {}));
    const list = category.list as Array<Record<string, unknown>>;

    expect(list.map((item) => item.vod_id)).toEqual(["child"]);
  });

  test("refresh vod requests backend refresh", () => {
    const calls = setupReq((url) => {
      if (url.endsWith("/auth")) return { content: JSON.stringify({ ok: true, access_token: "token", expires_at: 123 }) };
      if (url.includes("/category")) return { content: JSON.stringify({ list: [] }) };
      return { content: "{}" };
    });
    init({ gateway: "http://127.0.0.1:18990/tvbox/main" });

    spider.category("__refresh__/styled", "1", true, {});

    expect(calls.map((call) => call.url)).toContain(
      "http://127.0.0.1:18990/tvbox/main/category?tid=styled&extend=%7B%7D&refresh=1",
    );
  });

  test("refresh vod remark shows configured retry message when backend rejects refresh", () => {
    setupReq((url) => {
      if (url.endsWith("/auth")) return { content: JSON.stringify({ ok: true, access_token: "token", expires_at: 123 }) };
      if (url.includes("/category")) {
        return {
          content: JSON.stringify({
            dashbox_category_name: "Styled",
            dashbox_refreshable: true,
            dashbox_refresh: { requested: true, refreshed: false, rejected: true },
            list: [],
          }),
        };
      }
      return { content: "{}" };
    });
    init({
      gateway: "http://127.0.0.1:18990/tvbox/main",
      labels: { refreshRejected: "Try again later" },
    });

    const category = parse(spider.category("__refresh__/styled", "1", true, {}));
    const list = category.list as Array<Record<string, unknown>>;

    expect(list[0].vod_remarks).toBe("Try again later");
  });

  test("category requests are not cached in the spider", () => {
    const calls = setupReq((url) => {
      if (url.endsWith("/auth")) return { content: JSON.stringify({ ok: true, access_token: "token", expires_at: 123 }) };
      if (url.includes("/category")) return { content: JSON.stringify({ list: [] }) };
      return { content: "{}" };
    });
    init({ gateway: "http://127.0.0.1:18990/tvbox/main" });

    spider.category("source", "1", true, {});
    spider.category("source", "1", true, {});

    expect(calls.filter((call) => call.url.includes("/category")).map((call) => call.url)).toEqual([
      "http://127.0.0.1:18990/tvbox/main/category?tid=source&extend=%7B%7D",
      "http://127.0.0.1:18990/tvbox/main/category?tid=source&extend=%7B%7D",
    ]);
  });

  test("playlist metadata detail is resolved by backend detail", () => {
    const calls = setupReq((url) => {
      if (url.endsWith("/auth")) return { content: JSON.stringify({ ok: true, access_token: "token", expires_at: 123 }) };
      if (url.includes("/category")) {
        return {
          content: JSON.stringify({
            list: [
              {
                vod_id: "playlist-item-id",
                vod_name: "Twitch Item Title",
                vod_pic: "https://example.com/thumb.jpg",
                dashbox_client_detail: "playlist",
                dashbox_playlist_item: "1",
                dashbox_playlist_name: "Twitch Item Title",
                dashbox_playlist_url: "https://www.twitch.tv/videos/362696059?dashbox_index=2",
                dashbox_use_playlist_metadata: "1",
              },
            ],
          }),
        };
      }
      if (url.includes("/detail")) {
        return {
          content: JSON.stringify({
            list: [
              {
                vod_id: "playlist-item-id",
                vod_name: "Backend Twitch Item Title",
                vod_pic: "https://example.com/backend-thumb.jpg",
                vod_play_url: "Backend Twitch Item Title$https://www.twitch.tv/videos/362696059?dashbox_index=2",
              },
            ],
          }),
        };
      }
      return { content: "{}" };
    });
    init({ gateway: "http://127.0.0.1:18990/tvbox/main" });

    spider.category("twitch", "1", true, {});
    const detail = parse(spider.detail("playlist-item-id"));
    const list = detail.list as Array<Record<string, unknown>>;

    expect(list[0].vod_name).toBe("Backend Twitch Item Title");
    expect(list[0].vod_pic).toBe("https://example.com/backend-thumb.jpg");
    expect(String(list[0].vod_play_url)).toContain("https://www.twitch.tv/videos/362696059?dashbox_index=2");
    expect(calls.filter((call) => call.url.includes("/detail")).map((call) => call.url)).toEqual([
      "http://127.0.0.1:18990/tvbox/main/detail?id=playlist-item-id",
    ]);
  });
});
