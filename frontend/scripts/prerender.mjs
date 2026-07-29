// Prerenders the static marketing routes to plain HTML after `vite build`.
//
// The app is a client-side-rendered SPA (see src/App.jsx): dist/index.html
// ships as an empty <div id="root">, and React fills it in after the
// browser runs main.jsx. Any fetch that doesn't execute JS - most LLM
// crawlers (GPTBot, ClaudeBot, PerplexityBot, ...) and some search bots -
// only ever sees that empty shell plus the <head> meta/JSON-LD tags.
//
// This script launches a real (headless) browser against the built dist/
// output, lets each static route fully render, and writes the resulting
// HTML back to disk at a path matching the route (e.g. dist/faq/index.html).
// Render's static file server serves an existing file at a path before
// falling back to the SPA rewrite in render.yaml, so these prerendered
// files are served as-is to any client - JS or not - while the live app
// still works identically for real browsers landing on "/" and
// navigating client-side from there.
//
// Routes intentionally excluded: /ranking and /show/:slug depend on
// in-memory search results that only exist after a user submits the ICP
// form - there is no valid content to prerender for a cold load of those
// paths (see the STATIC_SCREEN_PATHS comment in App.jsx).

import { chromium } from 'playwright'
import { createServer } from 'node:http'
import { readFile, writeFile, mkdir, stat } from 'node:fs/promises'
import { join, extname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const DIST_DIR = join(__dirname, '..', 'dist')
const PORT = 4174

const ROUTES = ['/', '/privacy', '/terms', '/pricing', '/faq']

const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.ico': 'image/x-icon', '.jpg': 'image/jpeg',
  '.woff': 'font/woff', '.woff2': 'font/woff2',
}

function startStaticServer() {
  return new Promise((resolve) => {
    const server = createServer(async (req, res) => {
      const cleanPath = req.url.split('?')[0]
      let filePath = join(DIST_DIR, cleanPath)
      try {
        const s = await stat(filePath)
        if (s.isDirectory()) filePath = join(filePath, 'index.html')
      } catch {
        filePath = join(DIST_DIR, 'index.html') // SPA fallback, mirrors render.yaml
      }
      try {
        const body = await readFile(filePath)
        res.writeHead(200, { 'Content-Type': MIME[extname(filePath)] || 'application/octet-stream' })
        res.end(body)
      } catch {
        res.writeHead(404)
        res.end('Not found')
      }
    })
    server.listen(PORT, () => resolve(server))
  })
}

async function main() {
  const server = await startStaticServer()
  const browser = await chromium.launch()
  const page = await browser.newPage()

  for (const route of ROUTES) {
    await page.goto(`http://localhost:${PORT}${route}`, { waitUntil: 'networkidle' })
    // Wait for React to have actually painted content into #root.
    await page.waitForFunction(() => document.getElementById('root')?.childElementCount > 0)
    const html = await page.content()

    const outPath = route === '/'
      ? join(DIST_DIR, 'index.html')
      : join(DIST_DIR, route.slice(1), 'index.html')
    await mkdir(join(outPath, '..'), { recursive: true })
    await writeFile(outPath, html)
    console.log(`prerendered ${route} -> ${outPath.replace(DIST_DIR, 'dist')}`)
  }

  await browser.close()
  server.close()
}

main().catch((err) => {
  console.error('Prerender failed:', err)
  process.exit(1)
})
