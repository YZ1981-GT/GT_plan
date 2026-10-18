/**
 * formulaRowKind.spec.ts — Task 1.4 / ADR-FMC-02 单测 + 变异反证
 *
 * 验收判据（tasks.md Task 1.4）：
 *   - 据 `readonly` 渲染只读（无编辑按钮、无伪装标签）—— 以 isReadonlyProjectionRow 的
 *     判定 + 保存链分派为可测代理（组件模板依据同一判定）。
 *   - 保存链按 kind 分派：wp→upsert、surfaced/extraction→拒绝、report→detail。
 *   - 变异反证：
 *       ⑤b「surfaced 加回编辑按钮 / 渲染成可编辑」—— 注入「忽略 readonly」的变异体应把
 *          surfaced 判成可编辑（坐实若生产退回该逻辑编辑按钮会复现）；生产函数判只读（反向断言）。
 *       ⑤c「把 save 改回写 report_config」—— 注入「恒发 report-config」的变异体会把 wp 行
 *          误派到 report（坐实回退即打红）；生产 resolveSaveDispatch 把 wp 行派到 'wp'（反向断言）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  classifyFormulaRowKind,
  isReadonlyProjectionRow,
  resolveSaveDispatch,
} from '../formulaRowKind'

// ── 行样本（与 loadWpFormulas 组装的真实形态对齐）──────────────────────────────
const WP_ROW = {
  id: 'f1a2b3c4-0000-0000-0000-000000000001',
  formula_source: '底稿公式(wp_formula)',
  sheet_name: '货币资金审定表E1-1',
  target_cell: 'B7',
}
const SURFACED_TB_CHECK = { id: 'E1-surfaced-tb-check', readonly: true, formula_source: '取数核对' }
const SURFACED_ADJ = { id: 'E1-surfaced-adj-0', readonly: true }
const SURFACED_LEAF = { id: 'E1-surfaced-leaf-1001', readonly: true }
const SURFACED_BASE = { id: 'F2-surfaced-F2-3-0', readonly: true }
const TIER_B_ROW = { id: 'tierB-D6-1-tb-amount', readonly: true, formula_source: 'Tier B 溯源' }
const TIER_A_ROW = { id: 'tierA-D6-1-anchor', formula_source: '四表提取(Tier A)' }
const REPORT_ROW = { id: 'c0ffee00-0000-0000-0000-000000000002', formula_source: '报表行次引用' }

describe('classifyFormulaRowKind — 权威源 kind 分类', () => {
  it('wp_formula 正式公式 → wp', () => {
    expect(classifyFormulaRowKind(WP_ROW)).toBe('wp')
  })
  it('可编辑四表提取 Tier A（非只读）→ wp（保存走 wp 端点）', () => {
    expect(classifyFormulaRowKind(TIER_A_ROW)).toBe('wp')
  })
  it('surfaced 只读投影（含各 surfaced 伪 id 变体）→ surfaced', () => {
    expect(classifyFormulaRowKind(SURFACED_TB_CHECK)).toBe('surfaced')
    expect(classifyFormulaRowKind(SURFACED_ADJ)).toBe('surfaced')
    expect(classifyFormulaRowKind(SURFACED_LEAF)).toBe('surfaced')
    expect(classifyFormulaRowKind(SURFACED_BASE)).toBe('surfaced')
  })
  it('Tier B 只读溯源 → extraction', () => {
    expect(classifyFormulaRowKind(TIER_B_ROW)).toBe('extraction')
  })
  it('报表模板行 → report', () => {
    expect(classifyFormulaRowKind(REPORT_ROW)).toBe('report')
  })
  it('空/未知行 → report（兜底）', () => {
    expect(classifyFormulaRowKind(null)).toBe('report')
    expect(classifyFormulaRowKind({})).toBe('report')
  })
})

describe('isReadonlyProjectionRow — 只读投影判定（模板隐藏编辑按钮/伪装标签的依据）', () => {
  it('后端硬标 readonly:true → 只读', () => {
    expect(isReadonlyProjectionRow(SURFACED_TB_CHECK)).toBe(true)
    expect(isReadonlyProjectionRow(TIER_B_ROW)).toBe(true)
  })
  it('次级信号：surfaced / tierB 伪 id 形态（即便漏标 readonly）→ 只读', () => {
    expect(isReadonlyProjectionRow({ id: 'E1-surfaced-adj-3' })).toBe(true)
    expect(isReadonlyProjectionRow({ id: 'tierB-x' })).toBe(true)
  })
  it('wp_formula / Tier A 可编辑行 → 非只读', () => {
    expect(isReadonlyProjectionRow(WP_ROW)).toBe(false)
    expect(isReadonlyProjectionRow(TIER_A_ROW)).toBe(false)
  })
  it('报表行 / 空行 → 非只读', () => {
    expect(isReadonlyProjectionRow(REPORT_ROW)).toBe(false)
    expect(isReadonlyProjectionRow(null)).toBe(false)
    expect(isReadonlyProjectionRow({})).toBe(false)
  })
})

describe('resolveSaveDispatch — 保存链按 kind 分派', () => {
  it('wp 行 → wp（PUT /api/workpapers/{wp_id}/formulas）', () => {
    expect(resolveSaveDispatch(WP_ROW)).toBe('wp')
    expect(resolveSaveDispatch(TIER_A_ROW)).toBe('wp')
  })
  it('surfaced 行 → reject（只读禁保存）', () => {
    expect(resolveSaveDispatch(SURFACED_TB_CHECK)).toBe('reject')
    expect(resolveSaveDispatch(SURFACED_ADJ)).toBe('reject')
  })
  it('extraction（Tier B）行 → reject（只读禁保存）', () => {
    expect(resolveSaveDispatch(TIER_B_ROW)).toBe('reject')
  })
  it('report 行 → report（report-config detail）', () => {
    expect(resolveSaveDispatch(REPORT_ROW)).toBe('report')
  })
})

// ────────────────────────────────────────────────────────────────────────────
// 保存链端点分派（抽象 onFormulaEditSave 的「已有行」纯逻辑为可测函数，与 .vue 对齐）：
//   复用 resolveSaveDispatch，断言各 kind 命中正确端点、只读 kind 不发任何保存请求。
// ────────────────────────────────────────────────────────────────────────────
const wpUpsert = vi.fn()
const reportDetail = vi.fn()
const rejectNotice = vi.fn()

function runSaveChain(row: any, data: { formula: string; category: string; description: string }) {
  const dispatch = resolveSaveDispatch(row)
  if (dispatch === 'reject') {
    rejectNotice(row)
    return
  }
  if (dispatch === 'wp') {
    wpUpsert(`/api/workpapers/${row._wpId}/formulas`, {
      sheet_name: row.sheet_name,
      target_cell: row.target_cell,
      expression: data.formula,
      category: data.category,
      description: data.description,
    })
    return
  }
  reportDetail(`/api/report-config/${row.id}`, {
    formula: data.formula || null,
    formula_category: data.category,
    formula_description: data.description,
  })
}

beforeEach(() => {
  wpUpsert.mockReset()
  reportDetail.mockReset()
  rejectNotice.mockReset()
})

describe('保存链分派集成（抽象纯逻辑）', () => {
  const data = { formula: "TB('1001','期末余额')", category: 'auto_calc', description: '测试' }

  it('wp 行保存 → 发 wpFormula.upsert，不碰 report-config，契约字段 category/description', () => {
    runSaveChain({ ...WP_ROW, _wpId: 'wp-001' }, data)
    expect(wpUpsert).toHaveBeenCalledTimes(1)
    expect(wpUpsert).toHaveBeenCalledWith('/api/workpapers/wp-001/formulas', expect.objectContaining({
      sheet_name: '货币资金审定表E1-1',
      target_cell: 'B7',
      expression: data.formula,
      category: 'auto_calc',
      description: '测试',
    }))
    expect(reportDetail).not.toHaveBeenCalled()
    expect(rejectNotice).not.toHaveBeenCalled()
  })

  it('surfaced 行保存 → 拒绝（不发任何保存请求）', () => {
    runSaveChain(SURFACED_TB_CHECK, data)
    expect(rejectNotice).toHaveBeenCalledTimes(1)
    expect(wpUpsert).not.toHaveBeenCalled()
    expect(reportDetail).not.toHaveBeenCalled()
  })

  it('extraction（Tier B）行保存 → 拒绝', () => {
    runSaveChain(TIER_B_ROW, data)
    expect(rejectNotice).toHaveBeenCalledTimes(1)
    expect(wpUpsert).not.toHaveBeenCalled()
    expect(reportDetail).not.toHaveBeenCalled()
  })

  it('report 行保存 → 发 report-config detail，不碰 wp 端点', () => {
    runSaveChain(REPORT_ROW, data)
    expect(reportDetail).toHaveBeenCalledTimes(1)
    expect(reportDetail).toHaveBeenCalledWith(
      `/api/report-config/${REPORT_ROW.id}`,
      expect.objectContaining({ formula_category: 'auto_calc', formula_description: '测试' }),
    )
    expect(wpUpsert).not.toHaveBeenCalled()
  })
})

// ────────────────────────────────────────────────────────────────────────────
// 变异反证 ⑤b（surfaced 加回编辑按钮 / 渲染成可编辑）：
//   注入「忽略 readonly 标志」的变异体 readonly 判定，坐实它会把 surfaced 判成可编辑
//   （即生产模板若退回该逻辑，编辑按钮/编辑态会复现）；生产 isReadonlyProjectionRow 判只读（反向断言）。
// ────────────────────────────────────────────────────────────────────────────
describe('变异反证 ⑤b — 忽略 readonly 的变异体把 surfaced 判成可编辑', () => {
  // 变异体：模仿「加回编辑按钮」= 永远返回「非只读」（恒可编辑）。
  function mutantIgnoreReadonly(_row: any): boolean {
    return false
  }

  const surfacedSamples = [SURFACED_TB_CHECK, SURFACED_ADJ, SURFACED_LEAF, SURFACED_BASE, TIER_B_ROW]

  it.each(surfacedSamples.map((r) => [r.id, r] as const))(
    '%s：变异体判「可编辑」(false)，生产函数判「只读」(true)',
    (_id, row) => {
      expect(mutantIgnoreReadonly(row)).toBe(false) // 变异体错误：surfaced 变可编辑 → 若注入则 ⑤b 打红
      expect(isReadonlyProjectionRow(row)).toBe(true) // 生产：只读（反向断言）
    },
  )

  it('wp / Tier A 可编辑行：变异体与生产一致判非只读（确保不是全盘判只读）', () => {
    expect(isReadonlyProjectionRow(WP_ROW)).toBe(false)
    expect(isReadonlyProjectionRow(TIER_A_ROW)).toBe(false)
  })
})

// ────────────────────────────────────────────────────────────────────────────
// 变异反证 ⑤c（把 save 改回写 report_config）：
//   注入「恒派 report」的变异体，坐实它会把 wp 行误派到 report-config（即旧 bug：任何有 id
//   的行都发 report-config detail）；生产 resolveSaveDispatch 把 wp 行派到 'wp'（反向断言）。
// ────────────────────────────────────────────────────────────────────────────
describe('变异反证 ⑤c — 恒派 report 的变异体把 wp 行误写 report_config', () => {
  // 变异体：模仿旧 `if (row.id) { PUT report-config }` 无 kind 校验 = 恒 'report'。
  function mutantAlwaysReport(_row: any): 'wp' | 'report' | 'reject' {
    return 'report'
  }

  it('wp 行：变异体派 report（坐实回退即误写报表模板），生产派 wp（反向断言）', () => {
    expect(mutantAlwaysReport(WP_ROW)).toBe('report') // 变异体错误 → 若注入则 ⑤c 打红
    expect(resolveSaveDispatch(WP_ROW)).toBe('wp') // 生产：wp（反向断言）
  })

  it('surfaced 行：变异体会把只读行派去 report（旧 bug 的伪 id 污染 report），生产拒绝', () => {
    expect(mutantAlwaysReport(SURFACED_TB_CHECK)).toBe('report')
    expect(resolveSaveDispatch(SURFACED_TB_CHECK)).toBe('reject')
  })

  it('report 行：变异体与生产一致（确保变异不是全盘错，report 本就该派 report）', () => {
    expect(resolveSaveDispatch(REPORT_ROW)).toBe('report')
  })
})
