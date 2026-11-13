/**
 * 正式构建包体预算：按 Vite manifest 的稳定 chunk 身份比较，不按带 hash 文件名或体积名次比较。
 * 单一策略真源：scripts/bundle-budget.json。
 *
 * 不写 shebang：本模块会被 vitest 直接导入，Windows 按 CRLF 检出时首行 `#!…\r` 让导入报
 * 「Invalid or unexpected token」。一律用 `node scripts/check-bundle-budget.mjs` 调用。
 */
import { createHash } from 'node:crypto'
import {
  existsSync,
  readFileSync,
  readdirSync,
  realpathSync,
  statSync,
  writeFileSync,
} from 'node:fs'
import { basename, dirname, extname, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
export const DEFAULT_POLICY_FILE = resolve(ROOT, 'scripts/bundle-budget.json')
export const SCHEMA_VERSION = 2
export const MAX_GROWTH_RATIO = 0.05
export const ORDINARY_CHUNK_GZIP_LIMIT = 500 * 1024
export const EXEMPT_CHUNK_NAMES = ['heavy-univer', 'heavy-office', 'heavy-excel']

function parseCli(argv) {
  const value = (...flags) => {
    for (const flag of flags) {
      const index = argv.indexOf(flag)
      if (index >= 0 && argv[index + 1]) return argv[index + 1]
    }
    return undefined
  }
  const known = new Set([
    '--check', '--update', '--write-baseline', '--json',
    '--dir', '--dist', '--policy', '--baseline',
  ])
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index]
    if (!known.has(item)) throw new Error(`未知参数：${item}`)
    if (['--dir', '--dist', '--policy', '--baseline'].includes(item)) index += 1
  }
  // 产物目录优先认 `--dir`（全仓约定：smoke-built-artifact.mjs / package.json 的 bundle:check
  // 与 smoke:built 都用它），`--dist` 保留兼容；显式参数一律优先于 GT_FRONTEND_OUT_DIR，
  // 否则 verified 构建设了该变量时会检查错目录。
  return {
    dist: resolve(ROOT, value('--dir', '--dist') || process.env.GT_FRONTEND_OUT_DIR || 'dist'),
    policy: resolve(ROOT, value('--policy', '--baseline') || relative(ROOT, DEFAULT_POLICY_FILE)),
    update: argv.includes('--update') || argv.includes('--write-baseline'),
    json: argv.includes('--json'),
  }
}

function walk(dir) {
  const files = []
  for (const name of readdirSync(dir).sort()) {
    const path = resolve(dir, name)
    if (statSync(path).isDirectory()) files.push(...walk(path))
    else files.push(path)
  }
  return files
}

function sizeOf(path) {
  const body = readFileSync(path)
  return { rawBytes: body.length, gzipBytes: gzipSync(body, { level: 9 }).length }
}

function readManifest(dist) {
  const path = resolve(dist, '.vite/manifest.json')
  if (!existsSync(path)) throw new Error(`缺少 Vite manifest：${path}`)
  const manifest = JSON.parse(readFileSync(path, 'utf8'))
  if (!manifest || typeof manifest !== 'object' || Object.keys(manifest).length === 0) {
    throw new Error('Vite manifest 为空')
  }
  return manifest
}

function validateManifest(dist, manifest) {
  for (const [key, record] of Object.entries(manifest)) {
    if (!record?.file) throw new Error(`manifest 条目缺少 file：${key}`)
    for (const file of [record.file, ...(record.css || []), ...(record.assets || [])]) {
      if (!existsSync(resolve(dist, file))) throw new Error(`manifest 引用文件不存在：${file}`)
    }
    for (const imported of [...(record.imports || []), ...(record.dynamicImports || [])]) {
      if (!manifest[imported]) throw new Error(`manifest 依赖条目不存在：${imported}`)
    }
  }
}

function stableStem(value) {
  return basename(String(value || ''), extname(String(value || '')))
}

function baseChunkId(key, record) {
  return String(record.name || stableStem(record.src || key) || stableStem(record.file))
}

function chunkRecords(manifest) {
  const raw = Object.entries(manifest).map(([key, record]) => ({
    key,
    record,
    baseId: baseChunkId(key, record),
  }))
  const counts = new Map()
  for (const item of raw) counts.set(item.baseId, (counts.get(item.baseId) || 0) + 1)
  return raw.map((item) => ({
    ...item,
    id: counts.get(item.baseId) === 1 ? item.baseId : `${item.baseId}:${item.key}`,
  }))
}

function entryClosure(manifest) {
  const keys = new Set()
  const files = new Set(['index.html'])
  const visit = (key) => {
    if (keys.has(key)) return
    const record = manifest[key]
    if (!record) throw new Error(`manifest 静态依赖不存在：${key}`)
    keys.add(key)
    files.add(record.file)
    for (const file of [...(record.css || []), ...(record.assets || [])]) files.add(file)
    for (const imported of record.imports || []) visit(imported)
  }
  for (const [key, record] of Object.entries(manifest)) {
    if (record.isEntry) visit(key)
  }
  if (!keys.size) throw new Error('manifest 没有入口')
  return { keys, files }
}

function sumFiles(dist, files) {
  let rawBytes = 0
  let gzipBytes = 0
  let fileCount = 0
  for (const file of [...files].sort()) {
    const path = resolve(dist, file)
    if (!existsSync(path)) throw new Error(`构建文件不存在：${file}`)
    const size = sizeOf(path)
    rawBytes += size.rawBytes
    gzipBytes += size.gzipBytes
    fileCount += 1
  }
  return { rawBytes, gzipBytes, fileCount }
}

function totalMetrics(dist) {
  const files = walk(dist).filter((path) => {
    const rel = relative(dist, path).split(sep).join('/')
    return rel !== '.vite/manifest.json' && rel !== '.gt-build-verified.json'
  })
  return sumFiles(dist, files.map((path) => relative(dist, path)))
}

function policyExemptNames(policy) {
  const configured = policy?.policy?.exemptChunkNames
  return new Set(Array.isArray(configured) ? configured : EXEMPT_CHUNK_NAMES)
}

export async function analyzeBundle(dist, policy = null) {
  const root = resolve(dist)
  if (!existsSync(root)) throw new Error(`构建目录不存在：${root}`)
  const manifest = readManifest(root)
  validateManifest(root, manifest)
  const entries = entryClosure(manifest)
  const records = chunkRecords(manifest)
  const exempt = policyExemptNames(policy)
  const structuralIssues = []
  const chunks = records.map(({ key, record, id, baseId }) => {
    const size = sizeOf(resolve(root, record.file))
    const exemptName = exempt.has(baseId) ? baseId : null
    if (exemptName && entries.keys.has(key)) {
      structuralIssues.push(`入口递归依赖包含豁免重块 ${exemptName}：${key}`)
    }
    return { id, label: baseId, file: record.file, exemptName, ...size }
  }).sort((a, b) => a.id.localeCompare(b.id))

  const limit = Number(policy?.policy?.ordinaryChunkGzipLimitBytes) || ORDINARY_CHUNK_GZIP_LIMIT
  const ordinary = chunks.filter((chunk) => !chunk.exemptName)
  const ordinaryLargeChunks = ordinary
    .filter((chunk) => chunk.gzipBytes > limit)
    .map(({ id, rawBytes, gzipBytes }) => ({ id, rawBytes, gzipBytes }))
    .sort((a, b) => a.id.localeCompare(b.id))
  const exemptChunkCount = Object.fromEntries(
    [...exempt].sort().map((name) => [name, chunks.filter((chunk) => chunk.exemptName === name).length]),
  )

  return {
    schemaVersion: SCHEMA_VERSION,
    entryIds: ['index.html'],
    entry: sumFiles(root, entries.files),
    total: totalMetrics(root),
    ordinaryChunkCount: ordinary.length,
    ordinaryLargeChunks,
    exemptChunkCount,
    chunks,
    structuralIssues,
  }
}

function growthFailure(failures, label, actual, expected, maxGrowthRatio) {
  const ceiling = Math.ceil(Number(expected) * (1 + maxGrowthRatio))
  if (Number(actual) > ceiling) failures.push(`${label} ${actual} > ${ceiling}`)
}

export function checkBudget(report, policy) {
  const failures = [...(report.structuralIssues || [])]
  if (policy?.schemaVersion !== SCHEMA_VERSION) {
    failures.push(`包体策略格式过期（schemaVersion=${policy?.schemaVersion}，需要 ${SCHEMA_VERSION}）`)
    return failures
  }
  const baseline = policy.baseline
  if (!baseline) {
    failures.push('基线尚未建立；请先生成真实 production build，再显式执行 npm run bundle:update')
    return failures
  }
  const maxGrowthRatio = Number(policy.policy?.maxGrowthRatio ?? MAX_GROWTH_RATIO)
  if (JSON.stringify(report.entryIds) !== JSON.stringify(baseline.entryIds)) {
    failures.push(`入口身份变化：${JSON.stringify(report.entryIds)} != ${JSON.stringify(baseline.entryIds)}`)
  }
  for (const metric of ['rawBytes', 'gzipBytes']) {
    growthFailure(failures, `入口 ${metric}`, report.entry?.[metric], baseline.entry?.[metric], maxGrowthRatio)
    growthFailure(failures, `总量 ${metric}`, report.total?.[metric], baseline.total?.[metric], maxGrowthRatio)
  }

  const baselineLarge = new Map(
    (baseline.ordinaryLargeChunks || []).map((chunk) => [chunk.id || chunk.label, chunk]),
  )
  for (const chunk of report.ordinaryLargeChunks || []) {
    const id = chunk.id || chunk.label
    const previous = baselineLarge.get(id)
    if (!previous) {
      failures.push(`新增超过 500 KiB 的普通 chunk ${id}：gzip ${chunk.gzipBytes}`)
      continue
    }
    growthFailure(failures, `普通 chunk ${id} gzip`, chunk.gzipBytes, previous.gzipBytes, maxGrowthRatio)
  }

  if (baseline.exemptChunkCount) {
    for (const name of policy.policy?.exemptChunkNames || EXEMPT_CHUNK_NAMES) {
      const current = Number(report.exemptChunkCount?.[name] || 0)
      const previous = Number(baseline.exemptChunkCount?.[name] || 0)
      if (current !== previous) failures.push(`豁免重块 ${name} 数量变化：${current} != ${previous}`)
    }
  }
  return failures
}

export function baselineFromReport(report) {
  return {
    entryIds: report.entryIds,
    entry: report.entry,
    total: report.total,
    ordinaryChunkCount: report.ordinaryChunkCount,
    ordinaryLargeChunks: report.ordinaryLargeChunks,
    exemptChunkCount: report.exemptChunkCount,
  }
}

function defaultPolicy() {
  return {
    schemaVersion: SCHEMA_VERSION,
    policy: {
      maxGrowthRatio: MAX_GROWTH_RATIO,
      ordinaryChunkGzipLimitBytes: ORDINARY_CHUNK_GZIP_LIMIT,
      exemptChunkNames: EXEMPT_CHUNK_NAMES,
    },
    baseline: null,
  }
}

function digest(value) {
  return createHash('sha256').update(JSON.stringify(value)).digest('hex')
}

async function main() {
  const opts = parseCli(process.argv.slice(2))
  const saved = existsSync(opts.policy)
    ? JSON.parse(readFileSync(opts.policy, 'utf8'))
    : defaultPolicy()
  const policy = {
    ...defaultPolicy(),
    ...saved,
    policy: { ...defaultPolicy().policy, ...(saved.policy || {}) },
  }
  const report = await analyzeBundle(opts.dist, policy)
  if (opts.update) {
    const updated = { ...policy, schemaVersion: SCHEMA_VERSION, baseline: baselineFromReport(report) }
    writeFileSync(opts.policy, `${JSON.stringify(updated, null, 2)}\n`, 'utf8')
    console.log(`包体策略基线已写入：${opts.policy} (${digest(updated.baseline).slice(0, 12)})`)
    return
  }
  const failures = checkBudget(report, policy)
  if (opts.json) console.log(JSON.stringify(report))
  else {
    console.log(`入口 gzip ${report.entry.gzipBytes} bytes；总 gzip ${report.total.gzipBytes} bytes；普通 chunk ${report.ordinaryChunkCount} 个`)
    console.log(`豁免重块：${JSON.stringify(report.exemptChunkCount)}`)
  }
  if (failures.length) throw new Error(`包体预算超限（${failures.length} 项）：\n- ${failures.join('\n- ')}`)
  console.log('包体预算通过')
}

function invokedAsScript() {
  if (!process.argv[1]) return false
  try {
    const self = realpathSync(fileURLToPath(import.meta.url))
    const invoked = realpathSync(resolve(process.argv[1]))
    return process.platform === 'win32' ? self.toLowerCase() === invoked.toLowerCase() : self === invoked
  } catch {
    return false
  }
}

if (invokedAsScript()) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error)
    process.exitCode = 1
  })
}
