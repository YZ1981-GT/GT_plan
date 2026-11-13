/**
 * useTbDetailFormulas —— 试算表科目明细 composable（spec formula-global-settings-sync S2）
 *
 * 守护：buildRows 给覆盖行挂层级标签 + pending、加载 / 保存 / 应用范围委托。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { flushPromises } from '@vue/test-utils'

const fs = vi.hoisted(() => ({ domains: vi.fn() }))
vi.mock('@/services/formulaSettingsApi', () => ({ formulaSettingsApi: fs }))

import { useTbDetailFormulas } from '../useTbDetailFormulas'

function makeDeps(overrides: Record<string, any> = {}) {
  return {
    projectId: ref('p1'),
    year: ref(2025 as number | string | undefined),
    rows: ref<any[] | undefined>(undefined),
    addrStore: { loaded: false, tbAddresses: [] as any[] },
    api: { get: vi.fn().mockResolvedValue({}), put: vi.fn().mockResolvedValue({}) },
    reportConfigFormula: { tbDetail: (pid: string) => `/api/report-config/tb-detail-formulas/${pid}` },
    guardFormulaMutation: vi.fn(() => true),
    showFormulaError: vi.fn(),
    askApplyScope: vi.fn(),
    ...overrides,
  }
}

describe('buildRows', () => {
  it('覆盖行挂层级标签与 pending，未覆盖行无标签', () => {
    const deps = makeDeps()
    const { overrides, added, buildRows } = useTbDetailFormulas(deps)
    overrides.value = { '1001': { formula: "TB('1001','期末余额')*2", layer: 'project', pending: false } }
    added.value = [{ row_code: 'X1', formula: 'TB()', layer: 'global', pending: true }]
    const rows = buildRows([
      { code: '1001', name: '库存现金' },
      { code: '1002', name: '银行存款' },
    ])
    const r1 = rows.find(r => r.row_code === '1001')!
    expect(r1._layer).toBe('project')
    expect(r1._layer_label).toBe('本项目')
    expect(r1._pending).toBe(false)
    expect(r1._overridden).toBe(true)
    const r2 = rows.find(r => r.row_code === '1002')!
    expect(r2._layer).toBeUndefined()
    expect(r2._layer_label).toBe('')
    const x1 = rows.find(r => r.row_code === 'X1')!
    expect(x1._layer).toBe('global')
    expect(x1._layer_label).toBe('全局')
    expect(x1._pending).toBe(true)
  })
})

describe('persist', () => {
  it('成功后调 askApplyScope 传 changed_slot_keys', async () => {
    const deps = makeDeps()
    deps.api.put.mockResolvedValue({ loaded: { '1001': 'L2' }, changed_slot_keys: ['1001'] })
    const { persist } = useTbDetailFormulas(deps)
    const ok = await persist()
    expect(ok).toBe(true)
    expect(deps.askApplyScope).toHaveBeenCalledWith('tb_detail', ['1001'])
  })

  it('guardFormulaMutation 拒绝时不发请求', async () => {
    const deps = makeDeps({ guardFormulaMutation: vi.fn(() => false) })
    const { persist } = useTbDetailFormulas(deps)
    expect(await persist()).toBe(false)
    expect(deps.api.put).not.toHaveBeenCalled()
  })

  it('PUT 失败时调 showFormulaError', async () => {
    const deps = makeDeps()
    deps.api.put.mockRejectedValue({ response: { status: 409 } })
    const { persist } = useTbDetailFormulas(deps)
    expect(await persist()).toBe(false)
    expect(deps.showFormulaError).toHaveBeenCalled()
  })
})

// spec formula-management-repair-closure R3.1：试算表科目明细节点显示后端「未接入计算」说明
describe('notWired', () => {
  const ROWS = [{ standard_account_code: '1001', account_name: '库存现金' }]

  it('加载时取 tb_detail 的 wired_reason；已接入则为空', async () => {
    fs.domains.mockResolvedValueOnce({ domains: [
      { key: 'report', wired: true },
      { key: 'tb_detail', wired: false, wired_reason: '试算表科目明细公式目前只保存、不参与计算' },
    ] })
    const deps = makeDeps({ rows: ref(ROWS) })
    const { notWired, load } = useTbDetailFormulas(deps)
    await load()
    await flushPromises()
    expect(notWired.value).toBe('试算表科目明细公式目前只保存、不参与计算')

    fs.domains.mockResolvedValueOnce({ domains: [{ key: 'tb_detail', wired: true }] })
    const other = useTbDetailFormulas(makeDeps({ rows: ref(ROWS) }))
    await other.load()
    await flushPromises()
    expect(other.notWired.value).toBe('')
  })

  it('域清单取不到：不提示，科目明细照常加载', async () => {
    fs.domains.mockRejectedValueOnce(new Error('network'))
    const deps = makeDeps({ rows: ref(ROWS) })
    deps.api.get.mockResolvedValue({ overrides: { '1001': { formula: 'X' } } })
    const { notWired, overrides, load } = useTbDetailFormulas(deps)
    await load()
    await flushPromises()
    expect(notWired.value).toBe('')
    expect(overrides.value).toEqual({ '1001': { formula: 'X' } })
  })
})
