import { cp, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const root = dirname(require.resolve("pdfjs-dist/package.json"));
const destination = new URL("../public/pdfjs/", import.meta.url);
await mkdir(destination, { recursive: true });
for (const name of ["cmaps", "standard_fonts", "wasm"]) {
  await cp(join(root, name), new URL(name, destination), { recursive: true });
}
await cp(
  join(root, "build/pdf.worker.min.mjs"),
  new URL("pdf.worker.min.mjs", destination),
);
