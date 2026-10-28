/**
 * 后端产出的站内底稿跳转路由必须能命中前端路由（spec acnr-foundation-defect-closure T16 / RV7.5-01）。
 *
 * 浏览器实测：acnr_targets 结果的 chip 打开 `/workpapers/{wp_id}?sheet=…`，前端没有这条路由 ⇒ 兜底 404。
 * 本契约用真实路由表（`@/router` 导出的 `routes`）建 memory history router，把后端产出的全部路由形态逐个 resolve：
 * - 目录 `backend/data/acnr/global_catalog.json` 里不重复的 `jump_route_template`（`sheet=` 值归一）；
 * - 后端源码路由位置上的形态：`backend/tests/acnr/fixtures/frontend_route_shapes.json`（后端
 *   `test_frontend_route_shapes_fixture.py` 用 AST 守它不过期：resolver 缺省、目录模板生成、acnr_targets、AI 提及、
 *   证据治理、联动契约等）。
 * 占位符一律换成样例 UUID。断言命中非空且不是兜底 `NotFound`。
 *
 * `/projects/{…}/workpapers/{…}`（联动契约三处，不带 `/edit`）同样落到 404，不归本 spec：如实登记在
 * `KNOWN_UNROUTABLE`（只许删），并断言它们确实仍然落到 404（修好后这里会红，提醒删条目）。
 */
import { describe, it, expect, vi } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createMemoryHistory, createRouter } from 'vue-router'
import ts from 'typescript'
import { parse as parseSfc } from '@vue/compiler-sfc'

vi.mock('nprogress', () => ({ default: { start: vi.fn(), done: vi.fn(), configure: vi.fn() } }))

import { routes } from '@/router'

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
function repoRoot(): string {
  let dir = SRC
  for (let i = 0; i < 8; i += 1) {
    if (existsSync(join(dir, 'backend', 'data', 'acnr', 'global_catalog.json'))) return dir
    dir = dirname(dir)
  }
  throw new Error('未找到仓库根（哨兵 backend/data/acnr/global_catalog.json）')
}
const ROOT = repoRoot()
const SAMPLE_ID = '8c8cd491-2d21-48ce-9622-e2d9bca0d499'

type ShapeEntry = { file: string; shape: string }
const SOURCE_SHAPES = (JSON.parse(readFileSync(
  join(ROOT, 'backend', 'tests', 'acnr', 'fixtures', 'frontend_route_shapes.json'), 'utf-8',
)) as { source_shapes: ShapeEntry[] }).source_shapes

const CATALOG = JSON.parse(readFileSync(join(ROOT, 'backend', 'data', 'acnr', 'global_catalog.json'), 'utf-8')) as {
  sheets: { jump_route_template?: string }[]
}
/** 目录模板形态：sheet= 的值归一成占位（1225 个 sheet 只差 sheet 值） */
const CATALOG_SHAPES = [...new Set(CATALOG.sheets.map((s) => s.jump_route_template || '')
  .filter(Boolean).map((t) => t.replace(/([?&]sheet=)[^&]*/, '$1{sheet_code}')))]

/** 他域形态：落到 404、不归本 spec（只许删；修好后 `still unroutable` 一例会红） */
const KNOWN_UNROUTABLE: Record<string, string> = {
  'routers/linkage_resolve.py /projects/{…}/workpapers/{…}': '联动跳转缺 /edit',
  'services/linkage_contract_builder.py /projects/{…}/workpapers/{…}': '联动契约缺 /edit',
  'services/linkage_facade_service.py /projects/{…}/workpapers/{…}': '联动契约缺 /edit（部分还用 wp_code 当 id）',
}

function sample(shape: string): string {
  return shape.replace(/\{[^}]*\}/g, (m) => (m === '{sheet_code}' ? 'E1-14' : SAMPLE_ID))
}

function makeRouter() {
  return createRouter({ history: createMemoryHistory(), routes })
}

function resolvesToPage(path: string): { ok: boolean; name: string } {
  const r = makeRouter().resolve(path)
  const name = String(r.matched[r.matched.length - 1]?.name ?? '')
  return { ok: r.matched.length > 0 && name !== 'NotFound', name }
}

describe('后端跳转路由形态能命中前端路由（不落 404）', () => {
  it('夹具与目录都非空（防空转），且五个已知产出方都在', () => {
    expect(CATALOG_SHAPES.length).toBeGreaterThan(0)
    const files = new Set(SOURCE_SHAPES.map((e) => e.file))
    for (const f of ['services/acnr/resolver.py', 'services/acnr/loaders/from_classification.py',
      'services/custom_query/acnr_target_values.py', 'services/ai_chat/mention_service.py',
      'services/evidence_governance/typed_adapters.py']) expect(files.has(f), f).toBe(true)
  })

  it.each(CATALOG_SHAPES)('目录 jump_route_template %s', (shape) => {
    const res = resolvesToPage(sample(shape))
    expect(res.ok, `${sample(shape)} 命中 ${res.name || '无'}`).toBe(true)
  })

  it.each(SOURCE_SHAPES.filter((e) => !(`${e.file} ${e.shape}` in KNOWN_UNROUTABLE)).map((e) => [e.file, e.shape]))(
    '源码 %s：%s', (_file, shape) => {
      const res = resolvesToPage(sample(shape))
      expect(res.ok, `${sample(shape)} 命中 ${res.name || '无'}`).toBe(true)
    })

  it('KNOWN_UNROUTABLE 每条都仍在夹具里、且确实仍落到 404（修好或删掉后须删条目）', () => {
    const present = new Set(SOURCE_SHAPES.map((e) => `${e.file} ${e.shape}`))
    for (const key of Object.keys(KNOWN_UNROUTABLE)) {
      expect(present.has(key), `失效条目：${key}`).toBe(true)
      expect(resolvesToPage(sample(key.split(' ')[1])).ok, `${key} 已能命中，请删条目`).toBe(false)
    }
  })

  it('布局对短链渲染路由内容：DefaultLayout 的全宽前缀含 /workpapers/（否则落进浏览模式、短链页不挂载）', () => {
    const sfc = parseSfc(readFileSync(join(SRC, 'layouts', 'DefaultLayout.vue'), 'utf-8')).descriptor
    const sf = ts.createSourceFile('DefaultLayout.ts', sfc.scriptSetup?.content || '', ts.ScriptTarget.Latest, true)
    let prefixes: string[] | null = null
    const visit = (n: ts.Node) => {
      if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === 'FULLWIDTH_PREFIXES'
        && n.initializer && ts.isArrayLiteralExpression(n.initializer)) {
        prefixes = n.initializer.elements.filter(ts.isStringLiteral).map((e) => e.text)
      }
      ts.forEachChild(n, visit)
    }
    visit(sf)
    expect(prefixes, '未找到 FULLWIDTH_PREFIXES').not.toBeNull()
    expect(prefixes!.some((p) => `/workpapers/${SAMPLE_ID}`.startsWith(p))).toBe(true)
  })

  it('短链命中 WorkpaperShortLink、在需要登录的布局下，查询串原样保留', () => {
    const r = makeRouter().resolve(`/workpapers/${SAMPLE_ID}?sheet=E1-14&cell=C10`)
    expect(r.name).toBe('WorkpaperShortLink')
    expect(r.params.wpId).toBe(SAMPLE_ID)
    expect(r.query).toEqual({ sheet: 'E1-14', cell: 'C10' })
    expect(r.matched.some((m) => m.meta.requireAuth)).toBe(true)
  })
})
