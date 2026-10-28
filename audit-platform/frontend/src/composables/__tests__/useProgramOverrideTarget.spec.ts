/**
 * 程序表字段覆盖写入位置 —— spec audit-year-calendar-fallback-ratchet R0 / 任务 0.3
 * scope 以 render-config 回传的 override_scope 为准、年度取项目审计年度；任一取不到不写。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick, ref } from 'vue'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const warn = vi.hoisted(() => vi.fn())
vi.mock('@/services/apiProxy', () => ({ api }))
vi.mock('element-plus', () => ({ ElMessage: { warning: warn, error: vi.fn(), success: vi.fn() } }))

import { UNKNOWN_SCOPE_MESSAGE, useProgramOverrideTarget } from '../useProgramOverrideTarget'
import { MISSING_AUDIT_YEAR_MESSAGE } from '../useProjectAuditYear'

beforeEach(() => {
  api.get.mockReset().mockResolvedValue({ audit_year: 2025 })
  api.post.mockReset().mockResolvedValue({})
  warn.mockReset()
})

function lastPost() {
  return api.post.mock.calls.at(-1)
}

describe('useProgramOverrideTarget.writeField', () => {
  it('scope 用 html_data 回传的 override_scope，年度用项目审计年度', async () => {
    const t = useProgramOverrideTarget({
      projectId: () => 'p1',
      htmlData: () => ({ override_scope: 'procedure_table:A7' }),
      sheetName: () => '审计程序A7',
    })
    expect(await t.writeField(2, 'status', 'in_progress')).toBe(true)
    expect(lastPost()).toEqual(['/api/workpapers/field-overrides', {
      project_id: 'p1', year: 2025, scope: 'procedure_table:A7', item_key: '2', field: 'status', value: 'in_progress',
    }])
  })

  it('没有 override_scope 时按表名解析循环程序表码（表码 / 整表名都认）', async () => {
    for (const [sheet, scope] of [['H1A', 'procedure_table:H1A'], ['应收账款实质性程序表D2A', 'procedure_table:D2A']]) {
      const t = useProgramOverrideTarget({ projectId: () => 'p1', htmlData: () => ({}), sheetName: () => sheet })
      await t.writeField(1, 'execution_summary', '已执行')
      expect(lastPost()?.[1].scope).toBe(scope)
    }
  })

  it('固定表码兜底（A1 / A2 / A3）', async () => {
    const t = useProgramOverrideTarget({ projectId: () => 'p1', htmlData: () => null, fallbackCode: () => 'A2' })
    await t.writeField(3, 'status', 'completed')
    expect(lastPost()?.[1].scope).toBe('procedure_table:A2')
  })

  it('位置取不到 ⇒ 不写并提示（原来写进 A1 或拿表名当 scope）', async () => {
    const t = useProgramOverrideTarget({ projectId: () => 'p1', htmlData: () => ({}), sheetName: () => '审计程序A7' })
    expect(await t.writeField(1, 'status', 'completed')).toBe(false)
    expect(api.post).not.toHaveBeenCalled()
    expect(warn).toHaveBeenCalledWith(UNKNOWN_SCOPE_MESSAGE)
  })

  it('项目没填审计年度 ⇒ 不写并提示（原来按路由年度 → 今年写）', async () => {
    api.get.mockResolvedValue({ audit_year: null })
    const t = useProgramOverrideTarget({ projectId: () => 'p1', htmlData: () => ({ override_scope: 'procedure_table:H1A' }) })
    expect(await t.writeField(1, 'status', 'completed')).toBe(false)
    expect(api.post).not.toHaveBeenCalled()
    expect(warn).toHaveBeenCalledWith(`${MISSING_AUDIT_YEAR_MESSAGE}（本次保存未提交）`)
  })

  it('自加载结果的 override_scope 被采纳；html_data 更新但不带它时不清空', async () => {
    const html = ref<Record<string, any>>({})
    const t = useProgramOverrideTarget({ projectId: () => 'p1', htmlData: () => html.value })
    t.adoptScope('procedure_table:G8A')
    html.value = { programs: [] }
    await nextTick()
    await t.writeField(5, 'status', 'completed')
    expect(lastPost()?.[1].scope).toBe('procedure_table:G8A')
    html.value = { override_scope: 'procedure_table:G9A' }
    await nextTick()
    await t.writeField(5, 'status', 'completed')
    expect(lastPost()?.[1].scope).toBe('procedure_table:G9A')
  })
})
