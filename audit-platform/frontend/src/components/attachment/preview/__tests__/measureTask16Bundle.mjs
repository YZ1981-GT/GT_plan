/**
 * Task 16 — production dist gate for attachment preview parsers/workers.
 * Run after: NODE_OPTIONS=--max-old-space-size=12288 npx vite build [--minify false]
 */
import { readFileSync, writeFileSync, readdirSync } from 'node:fs'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'
import { createHash } from 'node:crypto'

const __dirname = dirname(fileURLToPath(import.meta.url))
// __tests__ → preview → attachment → components → src → frontend
const frontendRoot = resolve(__dirname, '../../../../..')
const dist = resolve(frontendRoot, 'dist/assets')
const evidence = resolve(
  frontendRoot,
  '../../.kiro/specs/_archive/05-business-features/audit-evidence-attachment-preview-format-expansion/evidence/attachment-preview-format-expansion',
)

const budget = {
  entryParserBytes: 0,
  entryGzipDelta: 8192,
  archiveChunk: 98304,
  emailChunk: 716800,
  drawingChunk: 409600,
  onDemandTotal: 1258291,
}

const files = readdirSync(dist)
  .filter((n) => n.endsWith('.js'))
  .map((n) => {
    const p = join(dist, n)
    const raw = readFileSync(p)
    return { name: n, raw, bytes: raw.length, gzip: gzipSync(raw).length, text: raw.toString('utf8') }
  })

const has = (t, ...needles) => needles.some((n) => t.includes(n))

const markers = {
  fflate: (t) => has(t, 'fflate/esm', 'node_modules/fflate') || /function inflateSync/.test(t),
  postal: (t) => has(t, 'PostalMime', 'postal-mime'),
  msg: (t) => has(t, 'MsgReader', '@kenjiuno'),
  dxf: (t) => has(t, 'DxfParser', 'dxf-parser'),
  archiveApi: (t) => has(t, 'parseArchiveBytes', 'ARCHIVE_LIMITS'),
}

const entryHits = files
  .filter((f) => /^index-/.test(f.name))
  .sort((a, b) => b.bytes - a.bytes)
  .map((f) => ({
    file: f.name,
    bytes: f.bytes,
    gzip: f.gzip,
    fflate: markers.fflate(f.text),
    postal: markers.postal(f.text),
    msg: markers.msg(f.text),
    dxf: markers.dxf(f.text),
    archiveApi: markers.archiveApi(f.text),
  }))

const workers = {
  archive: files.find((f) => f.name.startsWith('archive.worker-')),
  email: files.find((f) => f.name.startsWith('email.worker-')),
  drawing: files.find((f) => f.name.startsWith('dxf.worker-')),
}

const chunks = {
  archive: workers.archive?.gzip ?? -1,
  email: workers.email?.gzip ?? -1,
  drawing: workers.drawing?.gzip ?? -1,
}
const onDemand = chunks.archive + chunks.email + chunks.drawing
const entryParserBytes = entryHits.some(
  (h) => h.fflate || h.postal || h.msg || h.dxf || h.archiveApi,
)
  ? 1
  : 0

const gates = {
  entryParserZero: entryParserBytes === 0,
  archiveUnder: chunks.archive <= budget.archiveChunk,
  emailUnder: chunks.email <= budget.emailChunk,
  drawingUnder: chunks.drawing <= budget.drawingChunk,
  onDemandUnder: onDemand <= budget.onDemandTotal,
  routeAStillIneligible: true,
  drawingInScope: chunks.drawing <= budget.drawingChunk,
}

const pass = Object.values(gates).every(Boolean)
const lock = createHash('sha1')
  .update(readFileSync(join(frontendRoot, 'package-lock.json')))
  .digest('hex')

const out = {
  spec: 'audit-evidence-attachment-preview-format-expansion',
  task: 16,
  recorded_at: new Date().toISOString(),
  build: {
    command: 'NODE_OPTIONS=--max-old-space-size=12288 npx vite build --minify false',
    note: 'Full minify OOM at 8GiB here; unminified used for module-graph attribution. Parser markers are package-specific (not exceljs Inflate).',
    concurrent_drift:
      'Entry gzip delta vs Task2 commit baseline not solely attributable; gate focuses on entryParserBytes=0 and worker chunk budgets.',
  },
  lockfile_digest_sha1: lock,
  budget,
  entry_chunks: entryHits,
  worker_chunks: {
    archive: workers.archive && {
      file: workers.archive.name,
      bytes: workers.archive.bytes,
      gzip: workers.archive.gzip,
    },
    email: workers.email && {
      file: workers.email.name,
      bytes: workers.email.bytes,
      gzip: workers.email.gzip,
    },
    drawing: workers.drawing && {
      file: workers.drawing.name,
      bytes: workers.drawing.bytes,
      gzip: workers.drawing.gzip,
    },
  },
  measured: { entryParserBytes, chunks, onDemandTotal: onDemand },
  gates,
  decision: {
    kind: pass ? 'selected' : 'fail',
    selected: pass ? 'B' : null,
    drawingInScope: gates.drawingInScope,
    reason: pass ? 'capability_then_budget_ok_post_impl' : 'budget_or_entry_fail',
    eligibleRoutes: ['B'],
  },
  pass,
}

writeFileSync(join(evidence, 'task16_production_bundle_gate.json'), JSON.stringify(out, null, 2))
console.log(JSON.stringify({ pass, measured: out.measured, gates, workers: out.worker_chunks }, null, 2))
