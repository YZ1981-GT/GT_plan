/**
 * saveCustomPreset + 来源判定/权限门控纯逻辑测试
 * （template-library-formula-preset-custom Wave 4 · Task 5.1）
 *
 * 覆盖 Property 3/5：
 * - saveCustomPreset 打正确 URL/载荷、成功返 stats、422 悬空友好提示
 * - 来源判定纯逻辑（is_custom / source==='custom' → 自定义，其余 → 通用，Property 3）
 * - 权限门控纯逻辑（admin/partner → 可编辑，其余 → 隐藏入口，Property 5 前端侧）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/http', () => ({
  default: { post: vi.fn() },
}))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

import http from '@/utils/http'
import { ElMessage } from 'element-plus'
import { useFormulaImportExport } from '@/composables/useFormulaImportExport'

const mockPost = http.post as ReturnType<typeof vi.fn>

// ── 来源判定纯逻辑（复刻 GtFormulaPresetDialog.isCustomEntry，Property 3） ──
function isCustomEntry(row: { is_custom?: boolean; source?: string }): boolean {
  return row.is_custom === true || row.source === 'custom'
}

// ── 权限门控纯逻辑（复刻 FormulaTab.canEditPreset，Property 5 前端侧） ──
function canEditPreset(role: string): boolean {
  return role === 'admin' || role === 'partner'
}

describe('来源判定（Property 3）', () => {
  it('is_custom=true → 自定义', () => {
    expect(isCustomEntry({ is_custom: true, source: 'seed' })).toBe(true)
  })
  it("source='custom' → 自定义", () => {
    expect(isCustomEntry({ source: 'custom' })).toBe(true)
  })
  it.each(['seed', 'prefill_formula_mapping', 'check_presets', 'wide_table_presets'])(
    'source=%s → 通用',
    (source) => {
      expect(isCustomEntry({ source })).toBe(false)
    },
  )
})

describe('权限门控（Property 5 前端侧）', () => {
  it.each(['admin', 'partner'])('%s → 可编辑', (role) => {
    expect(canEditPreset(role)).toBe(true)
  })
  it.each(['assistant', 'manager', 'qc_partner', 'eqcr', ''])('%s → 隐藏入口', (role) => {
    expect(canEditPreset(role)).toBe(false)
  })
})

describe('saveCustomPreset', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('打正确 URL + 载荷，成功返 stats', async () => {
    mockPost.mockResolvedValueOnce({
      data: { data: { ok: true, inserted: 1, updated: 0, total: 3 } },
    })
    const { saveCustomPreset } = useFormulaImportExport()
    const res = await saveCustomPreset({
      page_key: 'note:X',
      target_cell: 'R1C1',
      expression: "=TB('1001')",
      formula_type: 'auto_calc',
      refs: [{ formula_ref: "TB('1001')" }],
      description: 'd',
    })
    expect(mockPost).toHaveBeenCalledWith(
      '/api/formula-management/presets/custom',
      expect.objectContaining({ page_key: 'note:X', target_cell: 'R1C1' }),
      expect.objectContaining({ params: {} }),
    )
    expect(res).toEqual({ ok: true, inserted: 1, updated: 0, total: 3 })
    expect(ElMessage.success).toHaveBeenCalled()
  })

  it('带 projectId 时透传 project_id 参数', async () => {
    mockPost.mockResolvedValueOnce({ data: { ok: true, inserted: 0, updated: 1, total: 1 } })
    const { saveCustomPreset } = useFormulaImportExport()
    await saveCustomPreset(
      { page_key: 'p', target_cell: 'c', expression: 'e', formula_type: 'logic_check' },
      'proj-1',
    )
    expect(mockPost).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(Object),
      expect.objectContaining({ params: { project_id: 'proj-1' } }),
    )
  })

  it('422 悬空引用 → 友好提示 + 返回 null（Property 6 前端侧）', async () => {
    mockPost.mockRejectedValueOnce({
      response: {
        status: 422,
        data: { detail: { message: '公式引用悬空', dangling_refs: ["TB('9999')"] } },
      },
    })
    const { saveCustomPreset } = useFormulaImportExport()
    const res = await saveCustomPreset({
      page_key: 'p',
      target_cell: 'c',
      expression: 'e',
      formula_type: 'auto_calc',
    })
    expect(res).toBeNull()
    expect(ElMessage.error).toHaveBeenCalledWith(expect.stringContaining("TB('9999')"))
  })

  it('其他错误 → 通用错误提示 + 返回 null', async () => {
    mockPost.mockRejectedValueOnce({ response: { status: 403, data: { detail: '权限不足' } } })
    const { saveCustomPreset } = useFormulaImportExport()
    const res = await saveCustomPreset({
      page_key: 'p',
      target_cell: 'c',
      expression: 'e',
      formula_type: 'auto_calc',
    })
    expect(res).toBeNull()
    expect(ElMessage.error).toHaveBeenCalledWith('权限不足')
  })
})
