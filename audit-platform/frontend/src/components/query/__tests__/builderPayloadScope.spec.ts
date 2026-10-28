/**
 * builderPayloadScope.spec.ts — 构建器请求体的项目范围、翻页与导出表头（advanced-query-linkage-closure 任务 30；R3.5、R2.6、R8.1）
 *
 * 构造函数仍是 acnr-foundation-defect-closure T16 的唯一一处（`custom-query/queryPayloads.buildBuilderPayload`），本 spec 只在它
 * 上面加三个可选参数：不传时输出与原先逐键相同（T16 的契约用例照旧成立）；传了时发出的键仍是后端模型字段的子集
 * （字段表读 acnr 的 `backend/tests/acnr/fixtures/query_request_fields.json`，后端用 pydantic model_fields 守它不过期）。
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { buildBuilderPayload, type BuilderDslState } from '@/components/custom-query/queryPayloads'

function repoRoot(): string {
  let dir = resolve(dirname(fileURLToPath(import.meta.url)))
  for (let i = 0; i < 10; i += 1) {
    if (existsSync(join(dir, 'backend', 'tests', 'acnr', 'fixtures', 'query_request_fields.json'))) return dir
    dir = dirname(dir)
  }
  throw new Error('未找到仓库根（哨兵 backend/tests/acnr/fixtures/query_request_fields.json）')
}
type ModelShape = { fields: string[]; required: string[] }
const FIELDS = JSON.parse(readFileSync(join(repoRoot(), 'backend', 'tests', 'acnr', 'fixtures', 'query_request_fields.json'), 'utf-8')) as
  Record<'QueryDSL' | 'ExportDSL', ModelShape>

const DSL: BuilderDslState = {
  table: 'tb_ledger', fields: ['voucher_date', 'debit_amount'], filters: [{ field: 'debit_amount', op: 'gt', value: '100' }],
  filter_logic: 'and', order_by: [{ field: 'debit_amount', direction: 'desc' }], joins: [], aggregates: [], group_by: [], limit: 100,
}

describe('buildBuilderPayload — 项目范围（R3.5）', () => {
  it('限定当前项目：不选单元格也带项目与审计年度', () => {
    const p = buildBuilderPayload(DSL, [], { projectId: 'p1', year: 2025, scopeToProject: true })
    expect(p).toMatchObject({ project_id: 'p1', year: 2025 })
    expect('acnr_targets' in p).toBe(false)
  })

  it('跨项目（或不传）：与 T16 原规则逐键相同——只有单元格目标才带项目', () => {
    const plain = buildBuilderPayload(DSL, [], { projectId: 'p1', year: 2025 })
    expect(buildBuilderPayload(DSL, [], { projectId: 'p1', year: 2025, scopeToProject: false })).toEqual(plain)
    expect(['project_id', 'year', 'acnr_targets'].filter((k) => k in plain)).toEqual([])
    expect(buildBuilderPayload(DSL, ['E1/E1-18/B20'], { projectId: 'p1', year: 2025, scopeToProject: false }))
      .toMatchObject({ project_id: 'p1', year: 2025, acnr_targets: ['E1/E1-18/B20'] })
  })

  it('没有项目上下文：限定项目也不带（不会发空串项目）；年度未知不发', () => {
    const none = buildBuilderPayload(DSL, [], { projectId: '', year: 2025, scopeToProject: true })
    expect(['project_id', 'year'].filter((k) => k in none)).toEqual([])
    const noYear = buildBuilderPayload(DSL, [], { projectId: 'p1', year: null, scopeToProject: true })
    expect(noYear.project_id).toBe('p1')
    expect('year' in noYear).toBe(false)
  })
})

describe('buildBuilderPayload — 翻页与导出表头（R2.6、R8.1）', () => {
  it('offset > 0 才发；表头只在传入时发', () => {
    expect('offset' in buildBuilderPayload(DSL, [], { offset: 0 })).toBe(false)
    expect(buildBuilderPayload(DSL, [], { offset: 200 }).offset).toBe(200)
    expect('headers' in buildBuilderPayload(DSL, [], { headers: {} })).toBe(false)
    expect(buildBuilderPayload(DSL, [], { headers: { voucher_date: '凭证日期' } }).headers).toEqual({ voucher_date: '凭证日期' })
  })

  it('发出的键是后端模型字段的子集：翻页请求对 QueryDSL，导出请求对 ExportDSL', () => {
    const page = buildBuilderPayload(DSL, ['E1/E1-18/B20'], { projectId: 'p1', year: 2025, scopeToProject: true, offset: 100 })
    expect(Object.keys(page).filter((k) => !FIELDS.QueryDSL.fields.includes(k))).toEqual([])
    const exp = buildBuilderPayload(DSL, [], { projectId: 'p1', year: 2025, scopeToProject: true, headers: { voucher_date: '凭证日期' } })
    expect(Object.keys(exp).filter((k) => !FIELDS.ExportDSL.fields.includes(k))).toEqual([])
    expect(FIELDS.QueryDSL.required.filter((k) => !(k in page))).toEqual([])
  })
})
