/**
 * queryPayloads.contract.spec.ts — 高级查询请求体契约（acnr-foundation-defect-closure T16，design §2.6 / §2.8，R2-F10）
 *
 * 1. 两个构造函数发出的键是后端模型字段的子集、后端必填项都在：字段表读 `backend/tests/acnr/fixtures/query_request_fields.json`
 *    （后端 `test_query_request_fields_fixture.py` 用 pydantic `model_fields` 守它不过期，不解析 Python 源码文本）。
 * 2. 单元格取值目标的发送规则：有项目才发；构建器的 project_id / year 只随目标发送，年度未知不发（不用日历年兜底）。
 * 3. 全部生产调用点（TS 语法树）：`/api/custom-query/execute` 的请求体必须是 `buildBusinessPayload(...)` 调用，
 *    `/api/query/{preview,execute,export-excel}` 的请求体必须是 `buildBuilderPayload(...)`（或本文件内直接返回它的函数）。
 *    调用点文件集合与登记相等（扫描器读不到任何调用点会红，不会空转）。
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'
import { parse as parseSfc } from '@vue/compiler-sfc'
import { buildBuilderPayload, buildBusinessPayload, type BuilderDslState } from '../queryPayloads'

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')

function repoRoot(): string {
  let dir = SRC
  for (let i = 0; i < 8; i += 1) {
    if (existsSync(join(dir, 'backend', 'tests', 'acnr', 'test_query_request_fields_fixture.py'))) return dir
    dir = dirname(dir)
  }
  throw new Error('未找到仓库根（哨兵 backend/tests/acnr/test_query_request_fields_fixture.py）')
}

type ModelShape = { fields: string[]; required: string[] }
const FIELDS = JSON.parse(readFileSync(
  join(repoRoot(), 'backend', 'tests', 'acnr', 'fixtures', 'query_request_fields.json'), 'utf-8',
)) as Record<'QueryDSL' | 'ExportDSL' | 'QueryRequest', ModelShape>

const FULL_DSL: BuilderDslState = {
  table: 'trial_balance', fields: ['standard_account_code'],
  filters: [{ field: 'year', op: 'between', value: '2024,2025' }, { field: 'x', op: 'is_null', value: 'y' }],
  filter_logic: 'or', order_by: [{ field: 'year', direction: 'desc' }], joins: [{ table: 'wp_index', type: 'left' }],
  aggregates: [{ func: 'sum', field: 'audited_amount', alias: '' }], group_by: ['year'], limit: 50,
}
const TARGETS = ['E1/E1-18/B20', 'E1/E1-19/B20']

function expectWithin(payload: Record<string, unknown>, model: ModelShape) {
  const keys = Object.keys(payload)
  expect(keys.filter((k) => !model.fields.includes(k)), '发送了后端未声明的字段（生产上 422）').toEqual([])
  expect(model.required.filter((k) => !keys.includes(k)), '缺后端必填字段').toEqual([])
}

describe('构造的键是后端模型字段的子集', () => {
  it('业务视图：全部入参 + 单元格目标', () => {
    const p = buildBusinessPayload({
      projectId: 'p1', year: 2025, source: 'tb_detail', filters: { a: 1 }, columns: ['c'], limit: 20, offset: 40,
    }, TARGETS)
    expectWithin(p, FIELDS.QueryRequest)
    expect(p).toEqual({ project_id: 'p1', year: 2025, source: 'tb_detail', filters: { a: 1 }, columns: ['c'],
      limit: 20, offset: 40, acnr_targets: TARGETS })
  })

  it('构建器：全部 DSL + 项目 + 年度 + 单元格目标（预览 / 执行 / 导出三模型）', () => {
    const p = buildBuilderPayload(FULL_DSL, TARGETS, { projectId: 'p1', year: 2025 })
    for (const m of [FIELDS.QueryDSL, FIELDS.ExportDSL]) expectWithin(p, m)
    expect(p).toMatchObject({ project_id: 'p1', year: 2025, acnr_targets: TARGETS })
    expect(p.filters).toEqual([{ field: 'year', op: 'between', value: [2024, 2025] }, { field: 'x', op: 'is_null', value: null }])
    expect(p.aggregates).toEqual([{ func: 'sum', field: 'audited_amount', alias: 'sum_audited_amount' }])
  })
})

describe('单元格取值目标的发送规则（需求 1.6）', () => {
  it('业务视图没有项目：不发 acnr_targets，project_id 仍为空串（模板浏览模式原样）', () => {
    const p = buildBusinessPayload({ projectId: '', year: 2025, source: 'report_balance_sheet' }, TARGETS)
    expect(p).toEqual({ project_id: '', year: 2025, source: 'report_balance_sheet', filters: {} })
  })

  it('业务视图年度无效不发（不用日历年兜底），目标为空不发 acnr_targets', () => {
    const p = buildBusinessPayload({ projectId: 'p1', year: null, source: 'tb_detail' })
    expect(p).toEqual({ project_id: 'p1', source: 'tb_detail', filters: {} })
  })

  it('构建器没有项目上下文：不发 project_id / year / acnr_targets', () => {
    const p = buildBuilderPayload(FULL_DSL, TARGETS, { projectId: '', year: 2025 })
    expect(['project_id', 'year', 'acnr_targets'].filter((k) => k in p)).toEqual([])
  })

  it('构建器在项目内、审计年度未知：带项目与目标、不带年度（由后端补齐）', () => {
    const p = buildBuilderPayload(FULL_DSL, TARGETS, { projectId: 'p1', year: null })
    expect(p).toMatchObject({ project_id: 'p1', acnr_targets: TARGETS })
    expect('year' in p).toBe(false)
  })

  it('构建器在项目内但没选单元格：常规查询保持原来的跨项目范围（不发 project_id）', () => {
    const p = buildBuilderPayload(FULL_DSL, [], { projectId: 'p1', year: 2025 })
    expect(['project_id', 'year', 'acnr_targets'].filter((k) => k in p)).toEqual([])
  })
})

// ── 全部生产调用点（TS 语法树） ─────────────────────────────────────────────────────────────────

const BUSINESS_URL = '/api/custom-query/execute'
const BUILDER_URLS = new Set(['/api/query/preview', '/api/query/execute', '/api/query/export-excel'])

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) {
      if (name !== 'node_modules' && name !== '__tests__' && name !== 'tests') walk(p, out)
    } else if ((name.endsWith('.ts') || name.endsWith('.vue')) && !/\.(spec|test)\.ts$/.test(name)) out.push(p)
  }
  return out
}

function scripts(abs: string): string[] {
  const text = readFileSync(abs, 'utf-8')
  if (!abs.endsWith('.vue')) return [text]
  const { descriptor } = parseSfc(text)
  return [descriptor.script, descriptor.scriptSetup].filter((b) => b?.content).map((b) => b!.content)
}

type Site = { file: string; kind: 'business' | 'builder'; body: string; ok: boolean }

/** 一份脚本里的调用点：post(url, body) 的 url 是业务视图 / 构建器端点（字符串字面量，或 apiPaths 的 customQuery.execute）。 */
function sitesOf(file: string, code: string): Site[] {
  const sf = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const customQueryAliases = new Set<string>()
  const wrappers = new Set<string>()
  const isCallTo = (n: ts.Node | undefined, names: Set<string>) =>
    !!n && ts.isCallExpression(n) && ts.isIdentifier(n.expression) && names.has(n.expression.text)
  const visitDecl = (node: ts.Node) => {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)
      && node.moduleSpecifier.text.includes('apiPaths') && node.importClause?.namedBindings
      && ts.isNamedImports(node.importClause.namedBindings)) {
      for (const el of node.importClause.namedBindings.elements) {
        if ((el.propertyName ?? el.name).text === 'customQuery') customQueryAliases.add(el.name.text)
      }
    }
    if (ts.isFunctionDeclaration(node) && node.name && node.body) {
      const ret = node.body.statements.filter(ts.isReturnStatement)
      if (ret.length === 1 && isCallTo(ret[0].expression, new Set(['buildBuilderPayload']))) wrappers.add(node.name.text)
    }
    ts.forEachChild(node, visitDecl)
  }
  visitDecl(sf)
  const out: Site[] = []
  const visit = (node: ts.Node) => {
    if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)
      && node.expression.name.text === 'post' && node.arguments.length >= 1) {
      const [url, body] = node.arguments
      let kind: Site['kind'] | null = null
      if (ts.isStringLiteralLike(url)) {
        if (url.text === BUSINESS_URL) kind = 'business'
        else if (BUILDER_URLS.has(url.text)) kind = 'builder'
      } else if (ts.isPropertyAccessExpression(url) && url.name.text === 'execute'
        && ts.isIdentifier(url.expression) && customQueryAliases.has(url.expression.text)) kind = 'business'
      if (kind) {
        const ok = kind === 'business'
          ? isCallTo(body, new Set(['buildBusinessPayload']))
          : isCallTo(body, new Set(['buildBuilderPayload', ...wrappers]))
        out.push({ file, kind, body: body ? body.getText(sf).slice(0, 60) : '（无请求体）', ok })
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return out
}

function scan(): Site[] {
  const sites: Site[] = []
  for (const abs of walk(SRC)) {
    const rel = relative(SRC, abs).replace(/\\/g, '/')
    for (const code of scripts(abs)) sites.push(...sitesOf(rel, code))
  }
  return sites
}

describe('全部生产调用点都经构造函数（R2-F10）', () => {
  const sites = scan()

  it('调用点文件集合与登记相等（4 个业务视图 / 构建器入口；useBatchQuery 已被 advanced-query d606c25dd 删除）', () => {
    const byKind = (k: Site['kind']) => [...new Set(sites.filter((s) => s.kind === k).map((s) => s.file))].sort()
    expect(byKind('business')).toEqual([
      'components/query/CustomQueryDialog.vue',
      'components/query/SheetCellRangePicker.vue',
      'components/template-library/CustomQueryTab.vue',
    ])
    expect(byKind('builder')).toEqual(['views/AdvancedQueryBuilder.vue'])
    expect(sites.filter((s) => s.kind === 'builder')).toHaveLength(3)
  })

  it('每个调用点的请求体都是构造函数调用', () => {
    expect(sites.filter((s) => !s.ok).map((s) => `${s.file}：${s.body}`)).toEqual([])
  })

  it('反向自检：对象字面量请求体会被判违规（扫描器不是恒真）', () => {
    const bad = sitesOf('x.ts', "import { customQuery as P } from '@/services/apiPaths'\n"
      + "api.post(P.execute, { project_id: 'p', year: 2025, source: 's' })\n"
      + "api.post('/api/query/execute', buildPayload())\n")
    expect(bad.map((s) => [s.kind, s.ok])).toEqual([['business', false], ['builder', false]])
  })

  it('SheetCellRangePicker 不再用日历年兜底（无 getFullYear 调用）', () => {
    const code = scripts(join(SRC, 'components/query/SheetCellRangePicker.vue')).join('\n')
    const sf = ts.createSourceFile('p.ts', code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
    let n = 0
    const v = (node: ts.Node) => {
      if (ts.isPropertyAccessExpression(node) && node.name.text === 'getFullYear') n += 1
      ts.forEachChild(node, v)
    }
    v(sf)
    expect(n).toBe(0)
  })
})
