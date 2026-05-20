import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { spiderFingerprint } from "./spider-fingerprint.mjs";

const adminDir = "dashbox/assets/admin";
const adminIndexPath = join(adminDir, "index.html");
const adminAssetPrefix = "/admin/assets/";

function checkAdminAssets() {
  if (!existsSync(adminIndexPath)) {
    throw new Error("No admin index found. Run `pnpm build:admin` first.");
  }

  const html = readFileSync(adminIndexPath, "utf8");
  const assetRefs = Array.from(html.matchAll(/(?:src|href)="([^"]+)"/g), (match) => match[1])
    .filter((ref) => ref.startsWith(adminAssetPrefix));

  if (assetRefs.length === 0) {
    throw new Error("Admin index does not reference any built assets.");
  }

  const missing = assetRefs
    .map((ref) => ref.slice(adminAssetPrefix.length))
    .filter((filename) => {
      const path = join(adminDir, "assets", filename);
      return !existsSync(path) || !statSync(path).isFile();
    });

  if (missing.length > 0) {
    throw new Error(`Admin index references missing assets: ${missing.join(", ")}`);
  }
}

const fingerprint = spiderFingerprint();
checkAdminAssets();
process.stdout.write(`spider ${fingerprint}\n`);
process.stdout.write("admin ok\n");
