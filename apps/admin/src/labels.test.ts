import { describe, expect, test, vi } from "vitest";

vi.mock("./i18n", () => ({
  t: (key: string) => `translated:${key}`
}));

import { displayLabel } from "./labels";

describe("displayLabel", () => {
  test("returns translated labels for known values", () => {
    expect(displayLabel("authMode", "anonymous")).toBe("translated:labels.authMode.anonymous");
    expect(displayLabel("subscriptionType", "tvbox")).toBe("translated:labels.subscriptionType.tvbox");
    expect(displayLabel("searchProvider", "bilibili")).toBe("translated:labels.searchProvider.bilibili");
  });

  test("falls back to the original string for unknown values", () => {
    expect(displayLabel("authMode", "custom-auth")).toBe("custom-auth");
    expect(displayLabel("vodStyle", "")).toBe("");
    expect(displayLabel("cookiesMode", null)).toBe("");
  });
});
