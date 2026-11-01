#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const VERIFIED = resolve(ROOT, '.verified-dist')
const POINTER = resolve(VERIFIED, 'current.json')
const BASELINE = resolve(ROOT, 'scripts/bundle-budget.baseline.json')
const hash = (path) => createHash('sha256').update(readFileSync(path)).digest('hex')
function fail(message) { console.error(message); process.exit(1) }
if (!existsSync(POINTER) || !existsSync(BASELINE)) fail('没有已验证的稳定产物，请先运行 npm run build:verify')
const pointer = JSON.parse(readFileSync(POINTER, 'utf8'))
if (!/^[a-f0-9]{64}$/.test(pointer.artifactName || '')) fail('稳定产物指针格式无效')
const dist = resolve(VERIFIED, pointer.artifactName)
const manifest = resolve(dist, '.vite/manifest.json')
const markerPath = resolve(dist, '.gt-build-verified.json')
if (!existsSync(manifest) || !existsSync(markerPath)) fail('稳定产物不完整，请重新运行 npm run build:verify')
const marker = JSON.parse(readFileSync(markerPath, 'utf8'))
if (marker.manifestSha256 !== hash(manifest)
  || marker.budgetBaselineSha256 !== hash(BASELINE)
  || pointer.manifestSha256 !== marker.manifestSha256) fail('稳定产物验证摘要不一致，请重新运行 npm run build:verify')
const child = spawn(process.execPath, [
  resolve(ROOT, 'node_modules/vite/bin/vite.js'), 'preview', '--host', '0.0.0.0',
  '--port', process.env.VITE_DEV_PORT || '3030', '--strictPort', '--outDir', dist,
], { cwd: ROOT, env: process.env, stdio: 'inherit' })
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal))
child.on('exit', (code, signal) => signal ? process.kill(process.pid, signal) : process.exit(code ?? 1))
