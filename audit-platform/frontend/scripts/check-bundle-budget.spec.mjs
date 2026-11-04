// @vitest-environment node
import { afterEach, describe, expect, it } from 'vitest'
import { randomBytes } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const SCRIPT = resolve(ROOT, 'scripts/check-bundle-budget.mjs')
const LARGE_CHUNK_GZIP_BYTES = 500 * 1024
const roots = []

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })))
})

async function fixture({ eagerOffice = false, hash = 'aaaaaaaa', ordinaryLarge = false } = {}) {
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
  const files = [
    [`main-${hash}.js`, 'import "./shared.js"'],
    [`shared-${hash}.js`, 'export const shared = true'],
    [`heavy-office-${hash}.js`, 'export const office = true'],
    [`heavy-univer-${hash}.js`, 'export const univer = true'],
    [`heavy-excel-${hash}.js`, 'export const excel = true'],
  ]
  if (ordinaryLarge) {
    manifest['src/ordinary.ts'] = {
      file: `assets/ordinary-${hash}.js`, name: 'ordinary', isDynamicEntry: true,
    }
    // 随机字节保证 gzip 后仍超过普通 chunk 限额，避免重复文本压缩后产生假阳性。
    files.push([`ordinary-${hash}.js`, randomBytes(LARGE_CHUNK_GZIP_BYTES + 32 * 1024)])
  }

  await writeFile(resolve(root, 'index.html'), `<script type="module" src="/assets/main-${hash}.js"></script>`)
  await writeFile(resolve(root, '.vite', 'manifest.json'), JSON.stringify(manifest))
  await Promise.all(files.map(([name, body]) => writeFile(resolve(root, 'assets', name), body)))
  return root
}

function run(args, env = process.env) {
  return spawnSync(process.execPath, [SCRIPT, ...args], {
    cwd: ROOT,
    env,
    encoding: 'utf8',
  })
}

function output(result) {
  return `${result.stdout || ''}\n${result.stderr || ''}`
}

async function writeBaseline(dist) {
  // 基线不能写进待度量的 dist：否则第二次 measure 会把 baseline.json 本身计入总包体，
  // 造成「刚建基线就超预算」的假失败。
  const holder = await mkdtemp(resolve(tmpdir(), 'gt-bundle-baseline-'))
  roots.push(holder)
  const baseline = resolve(holder, 'baseline.json')
  const result = run(['--dir', dist, '--baseline', baseline, '--write-baseline'])
  expect(result.status).toBe(0)
  expect(output(result)).toContain('包体基线已写入')
  return baseline
}

describe('check-bundle-budget CLI', () => {
  it('动态重块不进入入口静态闭包时，按刚建立的稳定基线通过', async () => {
    const dist = await fixture()
    const baseline = await writeBaseline(dist)
    const result = run(['--dir', dist, '--baseline', baseline])
    expect(result.status).toBe(0)
    expect(output(result)).toContain('包体预算通过')
    expect(output(result)).toContain('异步重块记录 3 个')
  })

  it('重块进入入口静态闭包时 fail-closed', async () => {
    const dist = await fixture({ eagerOffice: true })
    const result = run(['--dir', dist, '--baseline', resolve(dist, 'missing.json')])
    expect(result.status).not.toBe(0)
    expect(output(result)).toContain('重块进入入口静态闭包')
  })

  it('缺少基线时 fail-closed，不生成零值假基线', async () => {
    const dist = await fixture()
    const result = run(['--dir', dist, '--baseline', resolve(dist, 'missing.json')])
    expect(result.status).not.toBe(0)
    expect(output(result)).toContain('包体基线不存在')
  })

  it('新增超过限额的普通 chunk 时按体积名次打红，不依赖 hash 文件名', async () => {
    const baseline = await writeBaseline(await fixture({ hash: 'aaaaaaaa' }))
    const changed = await fixture({ hash: 'bbbbbbbb', ordinaryLarge: true })
    const result = run(['--dir', changed, '--baseline', baseline])
    expect(result.status).not.toBe(0)
    expect(output(result)).toContain('新增普通大 chunk')
  })

  it('文件 hash 改变但产物相同时，稳定基线仍能通过', async () => {
    const baseline = await writeBaseline(await fixture({ hash: 'aaaaaaaa' }))
    const changed = await fixture({ hash: 'bbbbbbbb' })
    const result = run(['--dir', changed, '--baseline', baseline])
    expect(result.status).toBe(0)
    expect(output(result)).toContain('包体预算通过')
  })

  it('CLI 的 --dir 优先于 GT_FRONTEND_OUT_DIR，且保留 --dist 兼容', async () => {
    const dist = await fixture()
    const baseline = await writeBaseline(dist)
    const wrongEnvironmentDir = await mkdtemp(resolve(tmpdir(), 'gt-bundle-wrong-env-'))
    roots.push(wrongEnvironmentDir)
    const env = { ...process.env, GT_FRONTEND_OUT_DIR: wrongEnvironmentDir }

    const current = run(['--dir', dist, '--baseline', baseline], env)
    expect(current.status).toBe(0)
    expect(output(current)).toContain('包体预算通过')

    const legacy = run(['--dist', dist, '--baseline', baseline], env)
    expect(legacy.status).toBe(0)
    expect(output(legacy)).toContain('包体预算通过')
  })
})
