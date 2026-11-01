#!/usr/bin/env node
import { spawn, spawnSync } from 'node:child_process'
import { createServer } from 'node:http'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { once } from 'node:events'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const VITE = resolve(ROOT, 'node_modules/vite/bin/vite.js')
const MARKER = 'gt-built-dist-smoke'
const option = (flag, fallback) => {
  const i = process.argv.indexOf(flag)
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback
}
async function listen(server) {
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  return server.address().port
}
async function get(url, timeout = 5000) {
  const response = await fetch(url, { signal: AbortSignal.timeout(timeout) })
  if (!response.ok) throw new Error(`${url} 返回 ${response.status}`)
  return response
}
async function stop(child) {
  if (child.exitCode != null) return
  child.kill('SIGTERM')
  await Promise.race([once(child, 'exit'), new Promise((r) => setTimeout(r, 1500))])
  if (child.exitCode == null && process.platform === 'win32') spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
  else if (child.exitCode == null) child.kill('SIGKILL')
}
function dynamicAsset(dist) {
  const manifest = JSON.parse(readFileSync(resolve(dist, '.vite/manifest.json'), 'utf8'))
  const item = Object.values(manifest).find((r) => r.isDynamicEntry && r.file)
  if (!item) throw new Error('manifest 没有动态入口')
  return item.file
}
async function main() {
  const dist = resolve(ROOT, option('--dist', 'dist'))
  if (!existsSync(resolve(dist, 'index.html'))) throw new Error(`缺少构建入口：${dist}`)
  const backend = createServer((req, res) => {
    res.setHeader('Content-Type', req.url?.includes('events') ? 'text/event-stream' : 'application/json')
    res.end(req.url?.includes('events') ? `data: ${MARKER}\n\n` : JSON.stringify({ marker: MARKER }))
  })
  const backendPort = await listen(backend)
  const probe = createServer(); const frontendPort = await listen(probe)
  await new Promise((r) => probe.close(r))
  const output = []
  const child = spawn(process.execPath, [VITE, 'preview', '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort', '--outDir', dist], {
    cwd: ROOT,
    env: { ...process.env, VITE_API_BASE_URL: `http://127.0.0.1:${backendPort}`, VITE_DEV_PORT: String(frontendPort) },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  child.stdout.on('data', (c) => output.push(String(c))); child.stderr.on('data', (c) => output.push(String(c)))
  const base = `http://127.0.0.1:${frontendPort}`
  try {
    const deadline = Date.now() + 30000
    while (Date.now() < deadline) { try { await get(base, 1000); break } catch { await new Promise((r) => setTimeout(r, 150)) } }
    const home = await (await get(`${base}/`)).text()
    const deep = await (await get(`${base}/projects/smoke/deep-link`)).text()
    if (![home, deep].every((x) => x.includes('<div id="app"></div>'))) throw new Error('主页或 SPA 深链未返回入口 HTML')
    const asset = dynamicAsset(dist)
    const assetResponse = await get(`${base}/${asset}`)
    if (!String(assetResponse.headers.get('content-type')).includes('javascript')) throw new Error('动态 chunk MIME 错误')
    for (const path of ['/api/health', '/wopi/smoke', '/api/events/smoke']) {
      const text = await (await get(`${base}${path}`)).text()
      if (!text.includes(MARKER)) throw new Error(`${path} 没有到达代理上游`)
    }
    console.log(`built-dist smoke 通过：主页、深链、${asset}、API、WOPI、SSE`)
  } finally { await stop(child); await new Promise((r) => backend.close(r)) }
}
main().catch((error) => { console.error(error instanceof Error ? error.message : error); process.exitCode = 1 })
