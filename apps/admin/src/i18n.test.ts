import { describe, expect, test } from "vitest";
import { resolvePreferredLocale } from "./i18n";

describe("resolvePreferredLocale", () => {
  test("uses the first supported browser language", () => {
    expect(resolvePreferredLocale(["zh-CN", "en-US"])).toBe("zh-CN");
    expect(resolvePreferredLocale(["en-US", "zh-CN"])).toBe("en-US");
  });

  test("matches language families and skips unsupported languages", () => {
    expect(resolvePreferredLocale(["fr-FR", "zh-Hant", "en-US"])).toBe("zh-CN");
    expect(resolvePreferredLocale(["fr-FR", "de-DE"])).toBe("");
  });
});
