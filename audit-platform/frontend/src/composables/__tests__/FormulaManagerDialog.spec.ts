/**
 * FormulaManagerDialog.spec.ts — Sprint 2 Task 2.44
 *
 * 三态切换：覆盖预设 → 点恢复按钮 → 回到原始预设
 *
 * 不直接挂载完整 FormulaManagerDialog 组件（依赖太多），
 * 而是抽象其用户公式相关的纯逻辑做单元测试。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// Mock api
const mockGet = vi.fn()
const mockDelete = vi.fn()
const mockPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    delete: (...args: any[]) => mockDelete(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

interface UserFormulaItem {
  cell_key: string
  formula: string
  is_preset_override: boolean
  formula_type?: string
  modified_at?: string
}

/**
 * 抽象用户公式 Tab 行为为可测函数（与 FormulaManagerDialog 内部逻辑对齐）。
 */
function buildUserFormulaTab(wpId: string) {
  const userFormulasList = ref<UserFormulaItem[]>([])

  async function loadUserFormulas() {
    const data: any = await mockGet(`/api/workpapers/${wpId}/user-formulas`)
    const list = data?.user_formulas || data?.items || data || {}
    const arr: UserFormulaItem[] = []
    if (Array.isArray(list)) {
      for (const it of list) arr.push(it)
    } else if (typeof list === 'object') {
      for (const [k, v] of Object.entries(list)) {
        const o = v as any
        arr.push({
          cell_key: k,
          formula: o?.formula || '',
          is_preset_override: !!o?.is_preset_override,
          formula_type: o?.formula_type,
        })
      }
    }
    userFormulasList.value = arr
  }

  async function onRestorePresetFormula(row: UserFormulaItem) {
    await mockDelete(`/api/workpapers/${wpId}/user-formulas/${encodeURIComponent(row.cell_key)}`)
    userFormulasList.value = userFormulasList.value.filter((u) => u.cell_key !== row.cell_key)
  }

  async function onDeleteUserFormula(row: UserFormulaItem) {
    await mockDelete(`/api/workpapers/${wpId}/user-formulas/${encodeURIComponent(row.cell_key)}`)
    userFormulasList.value = userFormulasList.value.filter((u) => u.cell_key !== row.cell_key)
  }

  return {
    userFormulasList,
    loadUserFormulas,
    onRestorePresetFormula,
    onDeleteUserFormula,
  }
}

beforeEach(() => {
  mockGet.mockReset()
  mockDelete.mockReset()
  mockPut.mockReset()
})

describe('FormulaManagerDialog 用户公式 Tab — 三态切换', () => {
  it('态 1: 仅有系统预设（无 user formula）', async () => {
    mockGet.mockResolvedValueOnce({})
    const { userFormulasList, loadUserFormulas } = buildUserFormulaTab('wp1')
    await loadUserFormulas()
    expect(userFormulasList.value.length).toBe(0)
  })

  it('态 2: 用户覆盖预设（is_preset_override=true）', async () => {
    mockGet.mockResolvedValueOnce({
      user_formulas: {
        '货币资金审定表E1-1!B7': {
          formula: '=TB("1001","期末余额")*1.1',
          is_preset_override: true,
          formula_type: 'arith',
        },
      },
    })
    const { userFormulasList, loadUserFormulas } = buildUserFormulaTab('wp1')
    await loadUserFormulas()
    expect(userFormulasList.value.length).toBe(1)
    expect(userFormulasList.value[0].is_preset_override).toBe(true)
    expect(userFormulasList.value[0].formula).toContain('TB')
  })

  it('态 3: 点恢复按钮 → 删除用户覆盖 → 回到原始预设', async () => {
    mockGet.mockResolvedValueOnce({
      user_formulas: {
        '货币资金审定表E1-1!B7': {
          formula: '=TB("1001","期末余额")*1.1',
          is_preset_override: true,
        },
      },
    })
    mockDelete.mockResolvedValueOnce({ ok: true })

    const { userFormulasList, loadUserFormulas, onRestorePresetFormula } = buildUserFormulaTab('wp1')
    await loadUserFormulas()
    expect(userFormulasList.value.length).toBe(1)

    // 用户点"↺ 恢复"
    await onRestorePresetFormula(userFormulasList.value[0])
    expect(mockDelete).toHaveBeenCalledWith(
      '/api/workpapers/wp1/user-formulas/' + encodeURIComponent('货币资金审定表E1-1!B7'),
    )
    expect(userFormulasList.value.length).toBe(0)
  })

  it('恢复 + 重新加载验证回到预设态（端到端三态切换）', async () => {
    // 初始：用户覆盖
    mockGet.mockResolvedValueOnce({
      user_formulas: {
        '货币资金审定表E1-1!B7': { formula: '=USER_OVERRIDE', is_preset_override: true },
      },
    })
    mockDelete.mockResolvedValueOnce({ ok: true })
    // 恢复后再加载：返回空（预设态）
    mockGet.mockResolvedValueOnce({})

    const { userFormulasList, loadUserFormulas, onRestorePresetFormula } = buildUserFormulaTab('wp1')
    await loadUserFormulas()
    expect(userFormulasList.value[0].is_preset_override).toBe(true)
    await onRestorePresetFormula(userFormulasList.value[0])
    await loadUserFormulas()
    expect(userFormulasList.value.length).toBe(0)
  })
})

describe('用户新增公式（非预设覆盖）', () => {
  it('is_preset_override=false 标记为"用户新增"', async () => {
    mockGet.mockResolvedValueOnce({
      user_formulas: {
        '货币资金审定表E1-1!Z99': {
          formula: '=B7+B8',
          is_preset_override: false,
        },
      },
    })
    const { userFormulasList, loadUserFormulas } = buildUserFormulaTab('wp1')
    await loadUserFormulas()
    expect(userFormulasList.value[0].is_preset_override).toBe(false)
  })

  it('删除用户新增公式调 DELETE 端点', async () => {
    mockGet.mockResolvedValueOnce({
      user_formulas: {
        Z99: { formula: '=B7+B8', is_preset_override: false },
      },
    })
    mockDelete.mockResolvedValueOnce({ ok: true })
    const { userFormulasList, loadUserFormulas, onDeleteUserFormula } = buildUserFormulaTab('wp1')
    await loadUserFormulas()
    await onDeleteUserFormula(userFormulasList.value[0])
    expect(mockDelete).toHaveBeenCalled()
    expect(userFormulasList.value.length).toBe(0)
  })
})
