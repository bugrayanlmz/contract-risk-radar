import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "../backend/openapi.json",
  output: { path: "src/api/generated", postProcess: ["prettier"] },
  plugins: [
    "@hey-api/typescript",
    "@hey-api/sdk",
    { name: "@hey-api/client-fetch", throwOnError: true },
  ],
});
