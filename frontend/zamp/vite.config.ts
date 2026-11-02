import { createReadStream, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// In production nginx serves the test invoices; this serves them in dev.
const SAMPLES_DIR = resolve(__dirname, '../../backend/tests/fixtures/iitm')

function devSamples(): Plugin {
  return {
    name: 'dev-samples',
    configureServer(server) {
      server.middlewares.use('/samples', (req, res, next) => {
        const file = resolve(SAMPLES_DIR, decodeURIComponent((req.url ?? '').split('?')[0]).slice(1))
        if (!file.startsWith(SAMPLES_DIR) || !file.endsWith('.pdf') || !existsSync(file)) return next()
        res.setHeader('Content-Type', 'application/pdf')
        createReadStream(file).pipe(res)
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), devSamples()],
  server: {
    proxy: {
      '/api': process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
      '/health': process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
    },
  },
})
