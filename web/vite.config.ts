/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// The shared .env lives in the repo root. Only VITE_* variables are read (never the API key).
const envDir = '..'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, envDir, 'VITE_') // also reads VITE_* from the shell
  // VITE_BASE serves the dashboard under a path prefix, e.g. /proxy/absolute/5173/ behind Jupyter's proxy
  // on Vertex AI Workbench. The API is then at <base>api and is proxied to the backend's /api.
  const base = env.VITE_BASE || '/'
  return {
    envDir,
    base,
    plugins: [react(), tailwindcss()],
    server: {
      // Behind a proxy the Host header is the proxy's, which Vite would otherwise reject.
      allowedHosts: base === '/' ? undefined : true,
      proxy: {
        [`${base}api`]: {
          target: env.VITE_API_TARGET || 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(base, '/'),
        },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
    },
  }
})
