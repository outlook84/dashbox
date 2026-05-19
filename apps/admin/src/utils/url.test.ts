import { describe, expect, test } from "vitest";

import { safeWebUrl } from "./url";

describe("safeWebUrl", () => {
  test("normalizes trimmed http and https urls", () => {
    expect(safeWebUrl(" https://example.com/path?q=1 ")).toBe("https://example.com/path?q=1");
    expect(safeWebUrl("http://example.com")).toBe("http://example.com/");
  });

  test("rejects non-web, empty, and invalid values", () => {
    expect(safeWebUrl("javascript:alert(1)")).toBe("");
    expect(safeWebUrl("ftp://example.com/file")).toBe("");
    expect(safeWebUrl("not a url")).toBe("");
    expect(safeWebUrl("   ")).toBe("");
    expect(safeWebUrl(null)).toBe("");
  });
});
