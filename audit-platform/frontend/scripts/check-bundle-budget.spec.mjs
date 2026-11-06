import { afterEach, describe, expect, it } from 'vitest'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  analyzeBundle,
  checkBudget,
  EXEMPT_CHUNK_NAMES,
  MAX_GROWTH_RATIO,
  ORDINARY_CHUNK_GZIP_LIMIT,
  SCHEMA_VERSION,
} from './check-bundle-budget.mjs'

const roots = []
const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })))
})

function policy(baseline = null) {
  return {
    schemaVersion: SCHEMA_VERSION,
    policy: {
      maxGrowthRatio: MAX_GROWTH_RATIO,
      ordinaryChunkGzipLimitBytes: ORDINARY_CHUNK_GZIP_LIMIT,
      exemptChunkNames: EXEMPT_CHUNK_NAMES,
    },
    baseline,
  }
}

async function fixture({ eagerOffice = false, hash = 'aaaaaaaa' } = {}) {
  const root = await mkdtemp(resolve(tmpdir(), 'gt-bundle-budget-'))
  roots.push(root)
  await mkdir(resolve(root, 'assets'), { recursive: true })
  await mkdir(resolve(root, '.vite'), { recursive: true })
  const manifest = {
    'src/main.ts': {
      file: `assets/main-${hash}.js`, isEntry: true, src: 'src/main.ts',
      imports: ['_shared.js', ...(eagerOffice ? ['src/office.ts'] : [])],
      dynamicImports: eagerOffice ? [] : ['src/office.ts'],
    },
    '_shared.js': { file: `assets/shared-${hash}.js`, name: 'shared' },
    'src/office.ts': { file: `assets/heavy-office-${hash}.js`, name: 'heavy-office', isDynamicEntry: true },
    'src/univer.ts': { file: `assets/heavy-univer-${hash}.js`, name: 'heavy-univer', isDynamicEntry: true },
    'src/excel.ts': { file: `assets/heavy-excel-${hash}.js`, name: 'heavy-excel', isDynamicEntry: true },
  }
  await writeFile(resolve(root, 'index.html'), `<script type="module" src="/assets/main-${hash}.js"></script>`)
  await writeFile(resolve(root, '.vite', 'manifest.json'), JSON.stringify(manifest))
  await Promise.all([
    writeFile(resolve(root, 'assets', `main-${hash}.js`), 'import "./shared.js"'),
    writeFile(resolve(root, 'assets', `shared-${hash}.js`), 'export const shared = true'),
    writeFile(resolve(root, 'assets', `heavy-office-${hash}.js`), 'export const office = true'),
    writeFile(resolve(root, 'assets', `heavy-univer-${hash}.js`), 'export const univer = true'),
    writeFile(resolve(root, 'assets', `heavy-excel-${hash}.js`), 'export const excel = true'),
  ])
  return root
}

describe('check-bundle-budget', () => {
  it('入口递归不包含动态重块，正常预算通过', async () => {
    const report = await analyzeBundle(await fixture())
    expect(report.structuralIssues).toEqual([])
    const baseline = {
      entryIds: report.entryIds,
      ordinaryLargeChunks: [],
      entry: report.entry,
      total: report.total,
    }
    expect(checkBudget(report, policy(baseline))).toEqual([])
  })

  it('重块进入入口递归依赖时 fail-closed', async () => {
    const report = await analyzeBundle(await fixture({ eagerOffice: true }))
    expect(report.structuralIssues).toContainEqual(expect.stringContaining('入口递归依赖包含豁免重块 heavy-office'))
  })

  it('缺少真实基线时 fail-closed，不生成零值假基线', async () => {
    const report = await analyzeBundle(await fixture())
    expect(checkBudget(report, policy())).toContainEqual(expect.stringContaining('基线尚未建立'))
  })

  it('新增超过 500 KiB 的普通 chunk 时按稳定身份打红，不依赖 hash 文件名', async () => {
    const report = await analyzeBundle(await fixture())
    report.ordinaryLargeChunks = [{ label: 'new-[hash].js', rawBytes: 700_000, gzipBytes: 600_000 }]
    const baseline = { entryIds: report.entryIds, entry: report.entry, total: report.total, ordinaryLargeChunks: [] }
    expect(checkBudget(report, policy(baseline))).toContainEqual(expect.stringContaining('新增超过 500 KiB'))
  })

  it('文件 hash 改变不改变 schema 与稳定 chunk 身份，gzip 只允许文件名编码造成的微小波动', async () => {
    const first = await analyzeBundle(await fixture({ hash: 'aaaaaaaa' }))
    const second = await analyzeBundle(await fixture({ hash: 'bbbbbbbb' }))
    expect(second.schemaVersion).toBe(first.schemaVersion)
    expect(second.entry.rawBytes).toBe(first.entry.rawBytes)
    expect(second.total.rawBytes).toBe(first.total.rawBytes)
    expect(second.chunks.map((chunk) => chunk.label)).toEqual(first.chunks.map((chunk) => chunk.label))
    expect(Math.abs(second.entry.gzipBytes - first.entry.gzipBytes)).toBeLessThanOrEqual(8)
    expect(Math.abs(second.total.gzipBytes - first.total.gzipBytes)).toBeLessThanOrEqual(8)
  })

  it('普通大 chunk 按 id 与自身基线比较，不再按 gzip 名次错配', async () => {
    const report = await analyzeBundle(await fixture())
    report.ordinaryLargeChunks = [
      { id: 'WorkpaperEditor', rawBytes: 700_000, gzipBytes: 550_000 },
      { id: 'SecondEditor', rawBytes: 650_000, gzipBytes: 530_000 },
    ]
    const baseline = {
      entryIds: report.entryIds,
      entry: report.entry,
      total: report.total,
      ordinaryLargeChunks: [
        // 故意反向排列；按名次比较会把两者配错，按 id 应保持通过。
        { id: 'SecondEditor', rawBytes: 650_000, gzipBytes: 530_000 },
        { id: 'WorkpaperEditor', rawBytes: 700_000, gzipBytes: 550_000 },
      ],
    }
    expect(checkBudget(report, policy(baseline))).toEqual([])
  })

  it('构建、预览和更新脚本统一读取 bundle-budget.json，不再引用匿名旧基线', async () => {
    for (const name of ['build-verified-dist.mjs', 'preview-verified-dist.mjs', 'update-bundle-budget.mjs']) {
      const source = await readFile(resolve(SCRIPT_DIR, name), 'utf8')
      expect(source).toContain('bundle-budget.json')
      expect(source).not.toContain('bundle-budget.baseline.json')
    }
  })
})
