#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const VITE = resolve(ROOT, 'node_modules/vite/bin/vite.js')
const BUDGET = resolve(ROOT, 'scripts/check-bundle-budget.mjs')
const SMOKE = resolve(ROOT, 'scripts/smoke-built-dist.mjs')
const BASELINE = resolve(ROOT, 'scripts/bundle-budget.baseline.json')
const CANDIDATE = resolve(ROOT, `.dist-verify-${process.pid}`)
const VERIFIED_ROOT = resolve(ROOT, '.verified-dist')
const POINTER = resolve(VERIFIED_ROOT, 'current.json')

function run(script, args = [], env = process.env) {
  const result = spawnSync(process.execPath, [script, ...args], { cwd: ROOT, env, stdio: 'inherit' })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error(`${script} 退出码 ${result.status}`)
}
function sha256(path) { return createHash('sha256').update(readFileSync(path)).digest('hex') }
function removeTree(path) { rmSync(path, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 }) }
function artifactValid(target, marker) {
  const manifest = resolve(target, '.vite/manifest.json')
  const markerPath = resolve(target, '.gt-build-verified.json')
  if (!existsSync(manifest) || !existsSync(markerPath)) return false
  try {
    const saved = JSON.parse(readFileSync(markerPath, 'utf8'))
    return saved.manifestSha256 === marker.manifestSha256
      && saved.budgetBaselineSha256 === marker.budgetBaselineSha256
      && sha256(manifest) === marker.manifestSha256
  } catch { return false }
}
function publish(marker) {
  mkdirSync(VERIFIED_ROOT, { recursive: true })
  const target = resolve(VERIFIED_ROOT, marker.manifestSha256)
  if (!artifactValid(target, marker)) {
    removeTree(target)
    cpSync(CANDIDATE, target, { recursive: true, errorOnExist: true })
    if (!artifactValid(target, marker)) throw new Error('版本化前端产物复制后摘要不一致')
  }
  writeFileSync(POINTER, `${JSON.stringify({ schemaVersion: 1, artifactName: marker.manifestSha256, ...marker }, null, 2)}\n`, 'utf8')
  return target
}
function main() {
  removeTree(CANDIDATE)
  console.log(`构建候选产物：${CANDIDATE}`)
  run(VITE, ['build', '--mode', 'production'], {
    ...process.env, GT_FRONTEND_OUT_DIR: CANDIDATE, NODE_OPTIONS: '--max-old-space-size=16384',
  })
  run(BUDGET, ['--check', '--dist', CANDIDATE])
  run(SMOKE, ['--dist', CANDIDATE])
  const marker = {
    manifestSha256: sha256(resolve(CANDIDATE, '.vite/manifest.json')),
    budgetBaselineSha256: sha256(BASELINE),
  }
  writeFileSync(resolve(CANDIDATE, '.gt-build-verified.json'), `${JSON.stringify({ schemaVersion: 1, ...marker }, null, 2)}\n`, 'utf8')
  console.log(`验证产物已发布：${publish(marker)}`)
}
try { main() } catch (error) {
  console.error(error instanceof Error ? error.message : error)
  process.exitCode = 1
} finally { removeTree(CANDIDATE) }
