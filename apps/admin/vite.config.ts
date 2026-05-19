import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    vue(),
    {
      name: "dashbox-admin-dev-redirect",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url === "/") {
            res.statusCode = 302;
            res.setHeader("Location", "/admin/");
            res.end();
            return;
          }
          next();
        });
      }
    }
  ],
  base: "/admin/",
  root: fileURLToPath(new URL(".", import.meta.url)),
  server: {
    proxy: {
      "/admin/api": {
        target: "http://127.0.0.1:18990",
        changeOrigin: true,
        headers: {
          Origin: "http://127.0.0.1:18990"
        }
      },
      "/repo.zip": {
        target: "http://127.0.0.1:18990",
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: fileURLToPath(new URL("../../dashbox/assets/admin", import.meta.url)),
    emptyOutDir: true,
    sourcemap: false
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url))
    }
  }
});
