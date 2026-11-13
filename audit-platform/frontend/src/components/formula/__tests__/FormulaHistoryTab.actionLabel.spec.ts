/**
 * 公式历史操作类型全中文（UI 全中文化）：回滚条目原先显示英文原值「rollback」、不展示公式变化。
 * 2026-11-09 浏览器走查（【测试】公式同步甲 BS-003 本项目适配 → 一键回滚）发现。
 */
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get, post: vi.fn() } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { role: 'partner' } }) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import FormulaHistoryTab from '@/components/formula/FormulaHistoryTab.vue'

const BASE = {
  module: 'report', row_code: 'BS-003', result_value: null, trace: null, created_at: null,
  operation: null, rollbackable: false, rollback_blocked_reason: null,
}

describe('公式历史：操作类型标签', () => {
  it('回滚显示「回滚」并展示新旧公式；未登记类型不露英文原值', async () => {
    get.mockResolvedValue([
      { ...BASE, id: 'a', action: 'rollback', old_formula: "TB('1101','期末余额') + 0", new_formula: "TB('1101','期末余额')" },
      { ...BASE, id: 'b', action: 'some_future_action', old_formula: null, new_formula: null },
    ])
    const w = mount(FormulaHistoryTab, { props: { projectId: 'p1', year: 2025 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    const text = w.text()
    expect(text).toContain('回滚')
    expect(text).not.toContain('rollback')
    expect(text).not.toContain('some_future_action')
    expect(text).toContain('其他操作')
    // 回滚条目展示公式变化
    expect(w.findAll('.gt-fh-entry-body').length).toBe(1)
    expect(text).toContain("TB('1101','期末余额') + 0")
    w.unmount()
  })
})
