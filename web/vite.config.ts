import process from "node:process";
import { URL, fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import { setupVitePlugins } from "./build/plugins";
import { createViteProxy, getBuildTime } from "./build/config";
import monacoEditorPlugin from "vite-plugin-monaco-editor-esm";
import path from "node:path";
import fs from "fs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig((configEnv) => {
  const viteEnv = loadEnv(
    configEnv.mode,
    process.cwd(),
  ) as unknown as Env.ImportMeta;

  const buildTime = getBuildTime();
  const prefix = `monaco-editor/esm/vs`;

  const enableProxy = configEnv.command === "serve" && !configEnv.isPreview;

  return {
    base: viteEnv.VITE_BASE_URL,
    resolve: {
      alias: {
        "~": fileURLToPath(new URL("./", import.meta.url)),
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    css: {
      preprocessorOptions: {
        scss: {
          api: "modern-compiler",
          additionalData: `@use "@/styles/scss/global.scss" as *;`,
        },
      },
    },
    plugins: [
      ...setupVitePlugins(viteEnv, buildTime),
      monacoEditorPlugin({
        languageWorkers: ["editorWorkerService", "json"],
      }),
      {
        name: "vite-plugin-dynamic-config",
        configureServer(server) {
          server.middlewares.use((req, res, next) => {
            if (req.url === "/config.js") {
              const config = {
                VITE_SERVICE_BASE_URL: viteEnv.VITE_SERVICE_BASE_URL,
              };
              res.setHeader("Content-Type", "application/javascript");
              res.end(`window.APP_CONFIG = ${JSON.stringify(config)}`);
              return;
            }
            next();
          });
        },
      },
      {
        name: "monaco-vscode-resources",
        configureServer(server) {
          server.middlewares.use((req, res, next) => {
            if (
              req.url &&
              req.url.startsWith("/node_modules/.vite/deps/resources/")
            ) {
              const resourcePath = req.url.replace(
                "/node_modules/.vite/deps/resources/",
                "",
              );
              const possibleBases = [
                path.resolve(__dirname, "node_modules/vscode/resources"),
                path.resolve(
                  __dirname,
                  "node_modules/@codingame/monaco-vscode-python-default-extension/resources",
                ),
                path.resolve(
                  __dirname,
                  "node_modules/@codingame/monaco-vscode-theme-defaults-default-extension/resources",
                ),
              ];
              for (const base of possibleBases) {
                const filePath = path.join(base, resourcePath);
                if (fs.existsSync(filePath)) {
                  res.setHeader("Content-Type", "application/json");
                  fs.createReadStream(filePath).pipe(res);
                  return;
                }
              }
            }
            next();
          });
        },
      }
    ],
    define: {
      BUILD_TIME: JSON.stringify(buildTime),
    },
    server: {
      host: "0.0.0.0",
      port: 9527,
      proxy: createViteProxy(viteEnv, enableProxy),
      allowedHosts: ["*"],
    },
    preview: {
      port: 9725,
    },
    build: {
      reportCompressedSize: false,
      sourcemap: viteEnv.VITE_SOURCE_MAP === "Y",
      commonjsOptions: {
        ignoreTryCatch: false,
      },
      rollupOptions: {
        output: {
          manualChunks: {
            editorWorker: [`${prefix}/editor/editor.worker`],
          },
        },
      },
    },
    optimizeDeps: {
      force: true,
    },
  };
});
