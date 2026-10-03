/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// The shared .env lives in the repo root. Only VITE_* variables are read (never the API key).
const envDir = '..'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, envDir, 'VITE_')
  return {
    envDir,
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        '/api': { target: env.VITE_API_TARGET || 'http://localhost:8000', changeOrigin: true },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
    },
  }
})
