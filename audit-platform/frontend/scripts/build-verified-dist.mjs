#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { cp, mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const VITE = resolve(ROOT, 'node_modules/vite/bin/vite.js')
const BUDGET = resolve(ROOT, 'scripts/check-bundle-budget.mjs')
const SMOKE = resolve(ROOT, 'scripts/smoke-built-artifact.mjs')
const BUDGET_POLICY = resolve(ROOT, 'scripts/bundle-budget.json')
const CANDIDATE = resolve(ROOT, `.dist-verify-${process.pid}`)
const VERIFIED_ROOT = resolve(ROOT, '.verified-dist')
const CURRENT_FILE = resolve(VERIFIED_ROOT, 'current.json')

function run(script, args = [], env = process.env) {
  const result = spawnSync(process.execPath, [script, ...args], {
    cwd: ROOT,
    env,
    stdio: 'inherit',
  })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error(`${script} 退出码 ${result.status}`)
}

async function sha256(path) {
  return createHash('sha256').update(await readFile(path)).digest('hex')
}

async function artifactValid(target, digest) {
  const manifest = resolve(target, '.vite/manifest.json')
  const markerPath = resolve(target, '.gt-build-verified.json')
  if (!existsSync(manifest) || !existsSync(markerPath)) return false
  try {
    const marker = JSON.parse(await readFile(markerPath, 'utf8'))
    return marker.manifestSha256 === digest.manifestSha256
      && marker.budgetBaselineSha256 === digest.budgetBaselineSha256
      && await sha256(manifest) === digest.manifestSha256
  } catch {
    return false
  }
}

async function selectSnapshot(artifactId, fullDigest) {
  await mkdir(VERIFIED_ROOT, { recursive: true })
  const target = resolve(VERIFIED_ROOT, artifactId)
  if (!await artifactValid(target, fullDigest)) {
    await rm(target, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 })
    await cp(CANDIDATE, target, { recursive: true, errorOnExist: true })
    if (!await artifactValid(target, fullDigest)) throw new Error('版本化前端产物复制后摘要不一致')
  }

  const pointer = { schemaVersion: 1, artifactName: artifactId, ...fullDigest }
  if (existsSync(CURRENT_FILE)) {
    try {
      const current = JSON.parse(await readFile(CURRENT_FILE, 'utf8'))
      if (JSON.stringify(current) === JSON.stringify(pointer)) {
        console.log('当前快照指针未改变')
        return target
      }
    } catch { /* 损坏指针由本次原子替换修复 */ }
  }
  // current.json 是 stable preview 的唯一切换点：临时文件写全再 rename，读取者只会看到旧的或新的
  // 完整指针；rename 失败时删掉临时文件，不在 .verified-dist 里留半截产物。
  const temporary = `${CURRENT_FILE}.${process.pid}.tmp`
  try {
    await writeFile(temporary, `${JSON.stringify(pointer, null, 2)}\n`, 'utf8')
    await rename(temporary, CURRENT_FILE)
  } finally {
    await rm(temporary, { force: true })
  }
  return target
}

async function main() {
  await rm(CANDIDATE, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 })
  console.log(`构建候选产物：${CANDIDATE}`)
  run(VITE, ['build', '--mode', 'production'], {
    ...process.env,
    GT_FRONTEND_OUT_DIR: CANDIDATE,
    NODE_OPTIONS: '--max-old-space-size=16384',
  })
  run(BUDGET, ['--check', '--dir', CANDIDATE])
  run(SMOKE, ['--dir', CANDIDATE])

  const fullDigest = {
    manifestSha256: await sha256(resolve(CANDIDATE, '.vite/manifest.json')),
    budgetBaselineSha256: await sha256(BUDGET_POLICY),
  }
  await writeFile(
    resolve(CANDIDATE, '.gt-build-verified.json'),
    `${JSON.stringify({ schemaVersion: 1, ...fullDigest }, null, 2)}\n`,
    'utf8',
  )
  const artifactId = fullDigest.manifestSha256
  console.log(`验证产物已发布：${await selectSnapshot(artifactId, fullDigest)}`)
}

try {
  await main()
} catch (error) {
  console.error(error instanceof Error ? error.message : error)
  process.exitCode = 1
} finally {
  await rm(CANDIDATE, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 })
}
