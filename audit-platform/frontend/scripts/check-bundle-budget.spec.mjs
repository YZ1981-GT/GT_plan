import { afterEach, describe, expect, it } from 'vitest'
import { spawnSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'
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

async function fixture({ eagerOffice = false, hash = 'aaaaaaaa', ordinaryLarge = false } = {}) {
  const root = await mkdtemp(resolve(tmpdir(), 'gt-bundle-budget-'))
  roots.push(root)
  await mkdir(resolve(root, 'assets'), { recursive: true })
  await mkdir(resolve(root, '.vite'), { recursive: true })
  if (ordinaryLarge) {
    // 随机字节保证 gzip 后仍超过普通 chunk 限额，避免重复文本压缩后产生假阴性。
    await writeFile(
      resolve(root, 'assets', `ordinary-${hash}.js`),
      randomBytes(ORDINARY_CHUNK_GZIP_LIMIT + 32 * 1024),
    )
  }
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
    ...(ordinaryLarge
      ? { 'src/ordinary.ts': { file: `assets/ordinary-${hash}.js`, name: 'ordinary', isDynamicEntry: true } }
      : {}),
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

  it('被测脚本不带 shebang：Windows CRLF 检出时 `#!…\\r` 会让本 spec 导入即语法错误', async () => {
    const source = await readFile(resolve(SCRIPT_DIR, 'check-bundle-budget.mjs'), 'utf8')
    expect(source.startsWith('#!')).toBe(false)
  })

  it('构建、预览和更新脚本统一读取 bundle-budget.json，不再引用匿名旧基线', async () => {
    for (const name of ['build-verified-dist.mjs', 'preview-verified-dist.mjs', 'update-bundle-budget.mjs']) {
      const source = await readFile(resolve(SCRIPT_DIR, name), 'utf8')
      expect(source).toContain('bundle-budget.json')
      expect(source).not.toContain('bundle-budget.baseline.json')
    }
  })
})

// CLI 层：真实子进程走一遍 main()（参数解析、读写策略文件、退出码）。用例源自并行会话按 CLI 写的
// 那一版（2026-11-05），判据改成单一策略文件实现的真实文案。
const SCRIPT = resolve(SCRIPT_DIR, 'check-bundle-budget.mjs')

function runCli(args, env = process.env) {
  const result = spawnSync(process.execPath, [SCRIPT, ...args], {
    cwd: resolve(SCRIPT_DIR, '..'),
    env,
    encoding: 'utf8',
  })
  return { status: result.status, output: `${result.stdout || ''}\n${result.stderr || ''}` }
}

async function writePolicy(dist) {
  // 策略文件不能写进待度量的 dist：否则第二次度量会把它自己算进总包体。
  const holder = await mkdtemp(resolve(tmpdir(), 'gt-bundle-policy-'))
  roots.push(holder)
  const file = resolve(holder, 'bundle-budget.json')
  const result = runCli(['--dir', dist, '--policy', file, '--update'])
  expect(result.status).toBe(0)
  expect(result.output).toContain('包体策略基线已写入')
  return file
}

describe('check-bundle-budget CLI', () => {
  it('动态重块不进入入口静态依赖时，按刚建立的策略基线通过', async () => {
    const dist = await fixture()
    const result = runCli(['--check', '--dir', dist, '--policy', await writePolicy(dist)])
    expect(result.status).toBe(0)
    expect(result.output).toContain('包体预算通过')
    expect(result.output).toContain('"heavy-excel":1,"heavy-office":1,"heavy-univer":1')
  })

  it('重块进入入口静态依赖时 fail-closed', async () => {
    const dist = await fixture({ eagerOffice: true })
    const result = runCli(['--check', '--dir', dist, '--policy', resolve(dist, 'missing.json')])
    expect(result.status).not.toBe(0)
    expect(result.output).toContain('入口递归依赖包含豁免重块 heavy-office')
  })

  it('缺少策略文件时 fail-closed，不生成零值假基线', async () => {
    const dist = await fixture()
    const missing = resolve(dist, 'missing.json')
    const result = runCli(['--check', '--dir', dist, '--policy', missing])
    expect(result.status).not.toBe(0)
    expect(result.output).toContain('基线尚未建立')
    await expect(readFile(missing, 'utf8')).rejects.toThrow()
  })

  it('新增超过限额的普通 chunk 按稳定名打红，hash 改变但内容相同仍通过', async () => {
    const policyFile = await writePolicy(await fixture({ hash: 'aaaaaaaa' }))
    const same = runCli(['--check', '--dir', await fixture({ hash: 'bbbbbbbb' }), '--policy', policyFile])
    expect(same.status).toBe(0)
    const grown = runCli([
      '--check', '--dir', await fixture({ hash: 'cccccccc', ordinaryLarge: true }), '--policy', policyFile,
    ])
    expect(grown.status).not.toBe(0)
    expect(grown.output).toContain('新增超过 500 KiB 的普通 chunk ordinary')
  })

  it('--dir 优先于 GT_FRONTEND_OUT_DIR，--dist 保留兼容，未知参数直接报错', async () => {
    const dist = await fixture()
    const policyFile = await writePolicy(dist)
    const wrong = await mkdtemp(resolve(tmpdir(), 'gt-bundle-wrong-env-'))
    roots.push(wrong)
    const env = { ...process.env, GT_FRONTEND_OUT_DIR: wrong }
    expect(runCli(['--check', '--dir', dist, '--policy', policyFile], env).status).toBe(0)
    expect(runCli(['--check', '--dist', dist, '--policy', policyFile], env).status).toBe(0)
    const unknown = runCli(['--check', '--dir', dist, '--policy', policyFile, '--bogus'])
    expect(unknown.status).not.toBe(0)
    expect(unknown.output).toContain('未知参数：--bogus')
  })
})
