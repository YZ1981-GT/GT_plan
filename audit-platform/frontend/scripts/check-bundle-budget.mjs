#!/usr/bin/env node
/** Production bundle budget based on the emitted Vite manifest. */
import { createHash } from 'node:crypto'
import {
  existsSync,
  readFileSync,
  readdirSync,
  realpathSync,
  statSync,
  writeFileSync,
} from 'node:fs'
import { dirname, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const DEFAULT_BASELINE = resolve(ROOT, 'scripts/bundle-budget.baseline.json')
export const SCHEMA_VERSION = 2
export const GROWTH_RATIO = 1.05
export const LARGE_CHUNK_GZIP_BYTES = 500 * 1024
export const HEAVY_PATTERN = /(?:heavy-(?:univer|office|excel)|univer|vue-office|exceljs|xlsx|formula.?manager|onlyoffice|deliverable.?preview)/i

function cliOptions(argv) {
  const value = (flag, fallback) => {
    const index = argv.indexOf(flag)
    return index >= 0 && argv[index + 1] ? argv[index + 1] : fallback
  }
  // 产物目录优先认 `--dir`（全仓约定：smoke-built-artifact.mjs / update-bundle-budget.mjs /
  // package.json 的 bundle:check 与 smoke:built 都用 `--dir`），`--dist` 保留向后兼容。
  // 原先只认 `--dist` ⇒ `bundle:check` 传的 `--dir dist` 被静默忽略、落到环境变量兜底，
  // 设了 GT_FRONTEND_OUT_DIR（verified 构建会设）时会检查错目录。
  return {
    dist: resolve(
      ROOT,
      value('--dir', value('--dist', process.env.GT_FRONTEND_OUT_DIR || 'dist')),
    ),
    baseline: resolve(ROOT, value('--baseline', relative(ROOT, DEFAULT_BASELINE))),
    write: argv.includes('--write-baseline'),
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
  return { raw: body.length, gzip: gzipSync(body, { level: 9 }).length }
}

function readManifest(dist) {
  const path = resolve(dist, '.vite/manifest.json')
  if (!existsSync(path)) throw new Error(`缺少 Vite manifest：${path}`)
  const data = JSON.parse(readFileSync(path, 'utf8'))
  if (!data || typeof data !== 'object' || Object.keys(data).length === 0) {
    throw new Error('Vite manifest 为空')
  }
  return data
}

function validateManifestFiles(dist, manifest) {
  for (const [key, record] of Object.entries(manifest)) {
    if (!record?.file) throw new Error(`manifest 条目缺少 file：${key}`)
    for (const rel of [record.file, ...(record.css || []), ...(record.assets || [])]) {
      if (!existsSync(resolve(dist, rel))) throw new Error(`manifest 引用文件不存在：${rel}`)
    }
    for (const imported of [...(record.imports || []), ...(record.dynamicImports || [])]) {
      if (!manifest[imported]) throw new Error(`manifest 依赖条目不存在：${imported}`)
    }
  }
}

function staticEntryFiles(manifest) {
  const files = new Set()
  const records = new Set()
  const visit = (key) => {
    if (records.has(key)) return
    records.add(key)
    const record = manifest[key]
    if (!record) throw new Error(`manifest 静态依赖不存在：${key}`)
    files.add(record.file)
    for (const file of [...(record.css || []), ...(record.assets || [])]) files.add(file)
    for (const imported of record.imports || []) visit(imported)
  }
  const entries = Object.entries(manifest).filter(([, record]) => record.isEntry)
  if (entries.length !== 1) throw new Error(`预期一个前端入口，实际 ${entries.length} 个`)
  visit(entries[0][0])
  return { files, records }
}

function artifactMetrics(dist, largeLimit) {
  let raw = 0
  let gzip = 0
  let chunkCount = 0
  const large = []
  for (const path of walk(dist)) {
    const rel = relative(dist, path).split(sep).join('/')
    if (rel === '.vite/manifest.json' || rel === '.gt-build-verified.json') continue
    const size = sizeOf(path)
    raw += size.raw
    gzip += size.gzip
    if (!/\.(?:js|css)$/.test(rel)) continue
    chunkCount += 1
    if (!HEAVY_PATTERN.test(rel) && size.gzip > largeLimit) {
      large.push({ file: rel, rawBytes: size.raw, gzipBytes: size.gzip })
    }
  }
  large.sort((a, b) => b.gzipBytes - a.gzipBytes || a.file.localeCompare(b.file))
  return { rawBytes: raw, gzipBytes: gzip, chunkCount, largeChunks: large }
}

export function measure(dist, largeLimit = LARGE_CHUNK_GZIP_BYTES) {
  if (!existsSync(dist)) throw new Error(`构建目录不存在：${dist}`)
  const manifest = readManifest(dist)
  validateManifestFiles(dist, manifest)
  const entry = staticEntryFiles(manifest)
  let entryRaw = 0
  let entryGzip = 0
  for (const rel of [...entry.files].sort()) {
    const size = sizeOf(resolve(dist, rel))
    entryRaw += size.raw
    entryGzip += size.gzip
  }

  const heavyRecords = []
  for (const [key, record] of Object.entries(manifest)) {
    const identity = `${key} ${record.src || ''} ${record.name || ''} ${record.file || ''}`
    if (!HEAVY_PATTERN.test(identity)) continue
    if (entry.records.has(key) || entry.files.has(record.file)) {
      throw new Error(`重块进入入口静态闭包：${identity}`)
    }
    heavyRecords.push(record.file)
  }

  const all = artifactMetrics(dist, largeLimit)
  return {
    schemaVersion: SCHEMA_VERSION,
    limits: { growthRatio: GROWTH_RATIO, largeChunkGzipBytes: largeLimit },
    entry: { rawBytes: entryRaw, gzipBytes: entryGzip },
    total: { rawBytes: all.rawBytes, gzipBytes: all.gzipBytes },
    chunkCount: all.chunkCount,
    largeChunks: all.largeChunks,
    heavyAsyncFiles: [...new Set(heavyRecords)].sort(),
  }
}

export function stableBaseline(report) {
  return {
    schemaVersion: report.schemaVersion,
    limits: report.limits,
    entry: report.entry,
    total: report.total,
    chunkCount: report.chunkCount,
    largeChunks: report.largeChunks.map(({ rawBytes, gzipBytes }) => ({ rawBytes, gzipBytes })),
  }
}

export function compare(report, baseline) {
  if (baseline?.schemaVersion !== SCHEMA_VERSION) {
    return [`包体基线格式过期（schemaVersion=${baseline?.schemaVersion}，需要 ${SCHEMA_VERSION}）`]
  }
  const failures = []
  const ratio = baseline.limits?.growthRatio || GROWTH_RATIO
  const checkGrowth = (label, actual, expected) => {
    const ceiling = Math.ceil(expected * ratio)
    if (actual > ceiling) failures.push(`${label} ${actual} > ${ceiling}`)
  }
  checkGrowth('入口 raw', report.entry.rawBytes, baseline.entry.rawBytes)
  checkGrowth('入口 gzip', report.entry.gzipBytes, baseline.entry.gzipBytes)
  checkGrowth('总量 raw', report.total.rawBytes, baseline.total.rawBytes)
  checkGrowth('总量 gzip', report.total.gzipBytes, baseline.total.gzipBytes)

  const limit = baseline.limits?.largeChunkGzipBytes || LARGE_CHUNK_GZIP_BYTES
  const allowed = baseline.largeChunks || []
  report.largeChunks.forEach((chunk, index) => {
    if (index >= allowed.length) {
      failures.push(`新增普通大 chunk ${chunk.file} gzip ${chunk.gzipBytes} > ${limit}`)
      return
    }
    checkGrowth(`第 ${index + 1} 大的普通 chunk ${chunk.file} gzip`, chunk.gzipBytes, allowed[index].gzipBytes)
  })
  return failures
}

function digest(value) {
  return createHash('sha256').update(JSON.stringify(value)).digest('hex')
}

function main() {
  const opts = cliOptions(process.argv.slice(2))
  const report = measure(opts.dist)
  if (opts.write) {
    const baseline = stableBaseline(report)
    writeFileSync(opts.baseline, `${JSON.stringify(baseline)}\n`, 'utf8')
    console.log(`包体基线已写入：${opts.baseline} (${digest(baseline).slice(0, 12)})`)
    return
  }
  if (!existsSync(opts.baseline)) throw new Error(`包体基线不存在：${opts.baseline}`)
  const baseline = JSON.parse(readFileSync(opts.baseline, 'utf8'))
  const failures = compare(report, baseline)
  if (opts.json) console.log(JSON.stringify(report))
  else {
    console.log(`入口 gzip ${report.entry.gzipBytes} bytes；总 gzip ${report.total.gzipBytes} bytes；chunk ${report.chunkCount} 个`)
    console.log(`异步重块记录 ${report.heavyAsyncFiles.length} 个`)
  }
  if (failures.length) throw new Error(`包体预算超限（${failures.length} 项）：\n- ${failures.join('\n- ')}`)
  console.log('包体预算通过')
}

function invokedAsScript() {
  if (!process.argv[1]) return false
  try {
    const self = realpathSync(fileURLToPath(import.meta.url))
    const invoked = realpathSync(resolve(process.argv[1]))
    return process.platform === 'win32'
      ? self.toLowerCase() === invoked.toLowerCase()
      : self === invoked
  } catch {
    return false
  }
}

if (invokedAsScript()) {
  try {
    main()
  } catch (error) {
    console.error(error instanceof Error ? error.message : error)
    process.exitCode = 1
  }
}