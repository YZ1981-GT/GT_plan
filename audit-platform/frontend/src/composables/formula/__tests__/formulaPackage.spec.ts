/**
 * 本项目公式包（spec formula-governance-coverage-closure R4.2）：
 * 导出只收本项目适配、域清单取后端；导入走 PUT overrides + 本地修订号，相同不写、适用范围不同 / 已归档整类跳过，
 * 失败逐类如实报告。只替换 formulaSettingsApi 网络层。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  domains: vi.fn(),
  effective: vi.fn(),
  saveOverrides: vi.fn(),
}))
vi.mock('@/services/formulaSettingsApi', () => ({ formulaSettingsApi: api }))

import {
  ADAPTATION_LAYERS, applyFormulaPackage, buildProjectPackage, describeApplyReport, parseFormulaPackage,
  sameDefinition,
} from '../formulaPackage'

const INFOS = [
  { key: 'report', label: '报表公式', scope_kind: 'standard', wired: true, scopes: [], exec_fields: [], desc_fields: [] },
  { key: 'cross_check', label: '表间审核', scope_kind: 'any', wired: true, scopes: [], exec_fields: [], desc_fields: [] },
  { key: 'push', label: '公式推送', scope_kind: 'template_type', wired: true, scopes: [], exec_fields: [], desc_fields: [] },
]

const slot = (slot_key: string, layer: string, definition: any, extra: Record<string, any> = {}) => ({
  slot_key, label: `L-${slot_key}`, layer, layer_label: layer, definition, disabled: false, pending: false,
  structure: {}, global_definition: null, global_version: null, preset_definition: null,
  local_definition: null, local_version: null, base_definition: null, base_version: null, base_origin: null,
  base_template_id: null, pinned: false, ...extra,
})

const EFFECTIVE: Record<string, any> = {
  report: { domain: 'report', project_id: 'p1', scope: 'soe_standalone', frozen: false, can_edit_global: false, slots: [
    slot('balance_sheet:BS-001', 'preset', { formula: "TB('1001','期末余额')" }),
    slot('balance_sheet:BS-002', 'project', { formula: "TB('1002','期末余额')" }, { local_version: 3,
      structure: { row_name: '货币资金' } }),
    slot('balance_sheet:BS-003', 'global', { formula: 'X' }),
    slot('balance_sheet:BS-004', 'template', { formula: 'Y' }, { local_version: 1 }),
    slot('balance_sheet:BS-005', 'pinned', { formula: 'Z' }, { local_version: 2 }),
  ] },
  cross_check: { domain: 'cross_check', project_id: 'p1', scope: '*', frozen: false, can_edit_global: false, slots: [
    slot('cross_report_note#r1', 'global', { left_ref: 'A', right_ref: 'B' }),
  ] },
  push: { domain: 'push', project_id: 'p1', scope: 'soe', frozen: false, can_edit_global: false, slots: [
    slot('E1:rule-1', 'project', { disabled: true }, { local_version: 1 }),
  ] },
}

beforeEach(() => {
  vi.clearAllMocks()
  api.domains.mockResolvedValue({ domains: INFOS, is_admin: false })
  api.effective.mockImplementation(async (_pid: string, d: string) => EFFECTIVE[d])
  api.saveOverrides.mockResolvedValue({ saved: [] })
})

describe('导出本项目公式包', () => {
  it('域清单取后端（含推送规则）；只收本项目适配（本项目 / 模板 / 暂缓），带行结构', async () => {
    const { pack, count } = await buildProjectPackage('p1')
    expect(api.effective.mock.calls.map((c) => c[1])).toEqual(['report', 'cross_check', 'push'])
    expect(ADAPTATION_LAYERS).toEqual(['project', 'template', 'pinned'])
    expect(Object.keys(pack.domains)).toEqual(['report', 'push'])
    expect(pack.domains.report.slots.map((s) => s.slot_key)).toEqual([
      'balance_sheet:BS-002', 'balance_sheet:BS-004', 'balance_sheet:BS-005'])
    expect(pack.domains.report.scope).toBe('soe_standalone')
    expect(pack.domains.report.slots[0].structure).toEqual({ row_name: '货币资金' })
    expect(pack.domains.report.slots[1].structure).toBeNull()
    // 停用也是本项目适配
    expect(pack.domains.push.slots[0].definition).toEqual({ disabled: true })
    expect(count).toBe(4)
    expect(pack.format).toBe('gt_formula_package')
    expect(pack.source).toBe('project:p1')
  })

  it('任何一类读取失败：整体失败并写明哪一类，不生成缺类的包', async () => {
    api.effective.mockImplementation(async (_pid: string, d: string) => {
      if (d === 'cross_check') throw { response: { status: 500, data: { detail: '库忙' } } }
      return EFFECTIVE[d]
    })
    await expect(buildProjectPackage('p1')).rejects.toThrow('读取「表间审核」失败：库忙')
  })
})

describe('解析公式包', () => {
  it('不是 JSON / 不是公式包：给出原因', () => {
    expect(parseFormulaPackage('{', INFOS)).toEqual({ error: '文件不是合法的 JSON 格式' })
    expect('error' in parseFormulaPackage('{"format":"x"}', INFOS)).toBe(true)
  })

  it('未知类别与缺字段条目记提醒并剔除；同一公式位重复取最后一条', () => {
    const text = JSON.stringify({ format: 'gt_formula_package', domains: {
      report: { scope: 'soe_standalone', slots: [
        { slot_key: 'a', definition: { formula: '1' } },
        { slot_key: 'a', definition: { formula: '2' } },
        { slot_key: '', definition: { formula: '3' } },
        { slot_key: 'b' },
      ] },
      nope: { slots: [{ slot_key: 'x', definition: {} }] },
    } })
    const r = parseFormulaPackage(text, INFOS)
    if ('error' in r) throw new Error(r.error)
    expect(r.total).toBe(1)
    expect(r.domains.report.slots).toEqual([{ slot_key: 'a', label: '', layer: '', definition: { formula: '2' }, structure: null }])
    expect(r.warnings).toEqual(['「报表公式」有 3 条缺公式位或定义（或重复），已忽略', '跳过未知的公式类别「nope」'])
  })
})

describe('导入为本项目适配', () => {
  const pkg = (scope: string, slots: any[]) => ({ report: { scope, slot_count: slots.length, slots } })

  it('PUT overrides：已有适配带本地修订号，新适配不带；与现有定义相同的不写', async () => {
    const r = await applyFormulaPackage('p1', pkg('soe_standalone', [
      { slot_key: 'balance_sheet:BS-002', label: '', layer: 'project', definition: { formula: 'NEW' }, structure: null },
      { slot_key: 'balance_sheet:BS-001', label: '', layer: 'project', definition: { formula: "TB('1001','期末余额')" } },
      { slot_key: 'balance_sheet:BS-003', label: '', layer: 'project', definition: { formula: 'X2' } },
      { slot_key: 'balance_sheet:NEW-9', label: '新行', layer: 'project', definition: { formula: 'N' },
        structure: { row_name: '新行' } },
    ]), INFOS)
    expect(api.saveOverrides).toHaveBeenCalledTimes(1)
    const [pid, domain, items] = api.saveOverrides.mock.calls[0]
    expect([pid, domain]).toEqual(['p1', 'report'])
    expect(items).toEqual([
      { slot_key: 'balance_sheet:BS-002', definition: { formula: 'NEW' }, expected_version: 3, label: 'L-balance_sheet:BS-002',
        structure: { row_name: '货币资金' } },
      { slot_key: 'balance_sheet:BS-003', definition: { formula: 'X2' }, expected_version: null, label: 'L-balance_sheet:BS-003',
        structure: null },
      { slot_key: 'balance_sheet:NEW-9', definition: { formula: 'N' }, expected_version: null, label: '新行',
        structure: { row_name: '新行' } },
    ])
    expect(r).toEqual({ written: 3, unchanged: 1, writtenDomains: ['report'], skipped: [], failed: [] })
    expect(describeApplyReport(r)).toBe('已写入 3 条；1 条与本项目相同未改')
  })

  it('适用范围不同 / 项目已归档：整类跳过并写明原因，不发写请求', async () => {
    const r1 = await applyFormulaPackage('p1', pkg('listed_standalone', [
      { slot_key: 'balance_sheet:BS-002', label: '', layer: 'project', definition: { formula: 'NEW' } }]), INFOS)
    expect(api.saveOverrides).not.toHaveBeenCalled()
    expect(r1.skipped).toEqual([{ domain: 'report', label: '报表公式', count: 1,
      reason: '适用范围不同（包：listed_standalone，本项目：soe_standalone）' }])
    api.effective.mockResolvedValueOnce({ ...EFFECTIVE.report, frozen: true })
    const r2 = await applyFormulaPackage('p1', pkg('soe_standalone', [
      { slot_key: 'balance_sheet:BS-002', label: '', layer: 'project', definition: { formula: 'NEW' } }]), INFOS)
    expect(r2.skipped[0].reason).toBe('本项目已归档（只读）')
    expect(api.saveOverrides).not.toHaveBeenCalled()
  })

  it('写入被拒（并发修改 409）：该类记失败并带原因，其余类照常写', async () => {
    api.saveOverrides.mockImplementation(async (_p: string, d: string) => {
      if (d === 'report') throw { response: { status: 409, data: { detail: { message: '本项目公式已被他人修改，请刷新后重试' } } } }
      return { saved: [] }
    })
    const r = await applyFormulaPackage('p1', {
      ...pkg('soe_standalone', [{ slot_key: 'balance_sheet:BS-002', label: '', layer: 'project', definition: { formula: 'NEW' } }]),
      push: { scope: 'soe', slot_count: 1, slots: [{ slot_key: 'E1:rule-2', label: '', layer: 'project', definition: { disabled: true } }] },
    }, INFOS)
    expect(r.failed).toEqual([{ domain: 'report', label: '报表公式', count: 1, reason: '本项目公式已被他人修改，请刷新后重试' }])
    expect(r.writtenDomains).toEqual(['push'])
    expect(describeApplyReport(r)).toBe('已写入 1 条；「报表公式」1 条失败：本项目公式已被他人修改，请刷新后重试')
  })

  it('定义比较与键顺序无关', () => {
    expect(sameDefinition({ a: 1, b: { c: 2, d: 3 } }, { b: { d: 3, c: 2 }, a: 1 })).toBe(true)
    expect(sameDefinition({ a: 1 }, { a: 2 })).toBe(false)
    expect(sameDefinition(null, undefined)).toBe(true)
  })
})
