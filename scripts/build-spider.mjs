import { build } from "esbuild";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { readdirSync, unlinkSync, writeFileSync } from "node:fs";

const repoRoot = resolve(fileURLToPath(new URL("..", import.meta.url)));
const assetDir = resolve(repoRoot, "dashbox/assets");
const hashedNamePattern = /^dashbox\.[0-9a-f]{12}\.js$/;

// dashbox/assets/dashbox.<hash>.js is a generated distribution artifact. Keep
// apps/tvbox/src/index.ts as the source of truth and build these during release.
const result = await build({
  entryPoints: [resolve(repoRoot, "apps/tvbox/src/index.ts")],
  bundle: true,
  format: "esm",
  target: "es2020",
  outfile: resolve(assetDir, "dashbox.js"),
  write: false,
});

const js = result.outputFiles[0].contents;
const fingerprint = createHash("sha256").update(js).digest("hex").slice(0, 12);
const hashedName = `dashbox.${fingerprint}.js`;

for (const entry of readdirSync(assetDir)) {
  if ((hashedNamePattern.test(entry) && entry !== hashedName) || entry === "dashbox.js") {
    unlinkSync(resolve(assetDir, entry));
  }
}

writeFileSync(resolve(assetDir, hashedName), js);
process.stdout.write(`${fingerprint}\n`);
