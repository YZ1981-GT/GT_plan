#!/usr/bin/env node
import { createServer } from 'node:http'
import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { dirname, relative, resolve, sep } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
const FRONTEND_ROOT = resolve(SCRIPT_DIR, '..')

function parseArgs(argv) {
  const options = { dir: 'dist' }
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--dir') options.dir = argv[++index]
    else if (argv[index] === '--help') options.help = true
    else throw new Error(`未知参数：${argv[index]}`)
  }
  return options
}

function ensure(condition, message) {
  if (!condition) throw new Error(message)
}

function safePath(root, file) {
  const path = resolve(root, file)
  const rel = relative(root, path)
  ensure(rel !== '..' && !rel.startsWith(`..${sep}`), `manifest 文件越界：${file}`)
  return path
}

function listen(server, port = 0) {
  return new Promise((resolveListen, reject) => {
    server.once('error', reject)
    server.listen(port, '127.0.0.1', () => {
      server.off('error', reject)
      resolveListen(server.address().port)
    })
  })
}

function closeServer(server) {
  if (!server?.listening) return Promise.resolve()
  return new Promise((resolveClose) => server.close(() => resolveClose()))
}

async function reservePort() {
  const server = createServer()
  const port = await listen(server)
  await closeServer(server)
  return port
}

async function fetchChecked(url, expectedStatus = 200, init = {}) {
  const response = await fetch(url, { ...init, signal: AbortSignal.timeout(10_000) })
  ensure(response.status === expectedStatus, `${url} 返回 ${response.status}，预期 ${expectedStatus}`)
  return response
}

async function validateArtifact(root) {
  const indexPath = resolve(root, 'index.html')
  const manifestPath = resolve(root, '.vite', 'manifest.json')
  ensure(existsSync(indexPath), `缺少 ${indexPath}`)
  ensure(existsSync(manifestPath), `缺少 ${manifestPath}`)
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'))
  const chunks = Object.values(manifest)
  ensure(chunks.some((chunk) => chunk?.isEntry), 'manifest 没有入口')

  for (const chunk of chunks) {
    for (const file of [chunk?.file, ...(chunk?.css ?? []), ...(chunk?.assets ?? [])].filter(Boolean)) {
      ensure(existsSync(safePath(root, file)), `manifest 指向的文件不存在：${file}`)
    }
  }
  const dynamicKeys = new Set(chunks.flatMap((chunk) => chunk?.dynamicImports ?? []))
  const dynamicChunk = [...dynamicKeys].map((key) => manifest[key]).find((chunk) => chunk?.file)
    ?? chunks.find((chunk) => chunk?.isDynamicEntry && chunk?.file)
  ensure(dynamicChunk, '构建产物没有动态 chunk，异步边界未生效')
  return { manifest, dynamicFile: dynamicChunk.file }
}

async function validateNginxContract() {
  const path = resolve(FRONTEND_ROOT, 'docker', 'nginx.conf')
  const source = await readFile(path, 'utf8')
  for (const token of [
    'try_files $uri $uri/ /index.html;',
    'max-age=31536000, immutable',
    'location = /index.html',
    'location = /sw.js',
    'location /api/',
    'location /wopi/',
    'proxy_buffering off;',
  ]) ensure(source.includes(token), `Nginx 配置缺少：${token}`)
}

export async function smokeBuiltArtifact(artifactDir) {
  const root = resolve(artifactDir)
  const { dynamicFile } = await validateArtifact(root)
  await validateNginxContract()

  const backend = createServer((request, response) => {
    if (request.url?.startsWith('/api/health')) {
      response.setHeader('content-type', 'application/json')
      response.end(JSON.stringify({ marker: 'built-smoke-health' }))
      return
    }
    if (request.url?.startsWith('/wopi/')) {
      response.setHeader('content-type', 'text/plain')
      response.end('built-smoke-wopi')
      return
    }
    response.statusCode = 404
    response.end('not found')
  })

  let previewServer
  const previousApi = process.env.VITE_API_BASE_URL
  const previousPort = process.env.VITE_DEV_PORT
  try {
    const backendPort = await listen(backend)
    const previewPort = await reservePort()
    process.env.VITE_API_BASE_URL = `http://127.0.0.1:${backendPort}`
    process.env.VITE_DEV_PORT = String(previewPort)
    const { preview } = await import('vite')
    previewServer = await preview({
      root: FRONTEND_ROOT,
      configFile: resolve(FRONTEND_ROOT, 'vite.config.ts'),
      mode: 'production',
      build: { outDir: root },
      preview: { host: '127.0.0.1', port: previewPort, strictPort: true },
      logLevel: 'silent',
    })

    const base = `http://127.0.0.1:${previewPort}`
    const htmlRequest = { headers: { accept: 'text/html' } }
    const home = await (await fetchChecked(`${base}/`, 200, htmlRequest)).text()
    const deep = await (await fetchChecked(`${base}/projects/smoke/deep-link`, 200, htmlRequest)).text()
    ensure(home === deep, 'SPA 深链没有回退到同一 index.html')
    const dynamicResponse = await fetchChecked(`${base}/${dynamicFile.replace(/^\//, '')}`)
    ensure(
      (dynamicResponse.headers.get('content-type') || '').includes('javascript'),
      '动态 chunk 的 Content-Type 不是 JavaScript',
    )
    const remoteChunk = Buffer.from(await dynamicResponse.arrayBuffer())
    const diskChunk = await readFile(safePath(root, dynamicFile))
    ensure(remoteChunk.equals(diskChunk), '动态 chunk 响应与同一构建产物的磁盘内容不一致')
    const health = await (await fetchChecked(`${base}/api/health`)).json()
    ensure(health?.marker === 'built-smoke-health', '/api/health 没有经过 preview 代理')
    const wopi = await (await fetchChecked(`${base}/wopi/smoke`)).text()
    ensure(wopi === 'built-smoke-wopi', '/wopi 没有经过 preview 代理')
  } finally {
    if (previewServer?.close) await previewServer.close()
    else if (previewServer?.httpServer) await closeServer(previewServer.httpServer)
    await closeServer(backend)
    if (previousApi === undefined) delete process.env.VITE_API_BASE_URL
    else process.env.VITE_API_BASE_URL = previousApi
    if (previousPort === undefined) delete process.env.VITE_DEV_PORT
    else process.env.VITE_DEV_PORT = previousPort
  }
}

export async function runSmokeCli(argv = process.argv.slice(2)) {
  const options = parseArgs(argv)
  if (options.help) {
    console.log('用法：node scripts/smoke-built-artifact.mjs [--dir dist]')
    return 0
  }
  await smokeBuiltArtifact(resolve(process.cwd(), options.dir))
  console.log('构建产物冒烟通过：主页、SPA 深链、动态块、API 与 WOPI 代理均可用。')
  return 0
}

const isMain = process.argv[1]
  && import.meta.url === pathToFileURL(resolve(process.argv[1])).href
if (isMain) {
  runSmokeCli().then((code) => {
    process.exitCode = code
  }).catch((error) => {
    console.error(`[ERROR] ${error instanceof Error ? error.message : String(error)}`)
    process.exitCode = 1
  })
}
