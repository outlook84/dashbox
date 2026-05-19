import { createHash } from "node:crypto";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const assetDir = "dashbox/assets";
export const fingerprintPath = "dashbox/assets/spider-fingerprint.txt";
export const hashedNamePattern = /^dashbox\.[0-9a-f]{12}\.js$/;

export function spiderPath() {
  const candidates = readdirSync(assetDir).filter((entry) => hashedNamePattern.test(entry)).sort();
  if (candidates.length === 0) {
    throw new Error("No hashed spider asset found. Run `pnpm build:spider` first.");
  }
  return resolve(assetDir, candidates[candidates.length - 1]);
}

export function spiderFingerprint(path = spiderPath()) {
  const js = readFileSync(path);
  return createHash("sha256").update(js).digest("hex").slice(0, 12);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  const fingerprint = spiderFingerprint();
  if (process.argv.includes("--write")) {
    writeFileSync(fingerprintPath, `${fingerprint}\n`);
  }
  process.stdout.write(`${fingerprint}\n`);
}
