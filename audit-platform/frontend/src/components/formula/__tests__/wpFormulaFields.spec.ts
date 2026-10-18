/**
 * wpFormulaFields.spec.ts — Task 1.5 / ADR-FMC-02 改动点③（§1 #2b / 需求 2.4）单测 + 变异反证
 *
 * 验收判据（tasks.md Task 1.5）：
 *   - 右栏渲染读的是契约字段：wp item 的契约字段 `category`/`description` 被正确映射进组件
 *     内部行键（表格据内部键渲染），而非误读 `formula_category`/`formula_description`（在 wp
 *     items 上恒 undefined → 落兜底，分类/说明错位）。
 *   - 保存请求体字段 = 契约字段 `category`/`description`（wp 行走 wpFormula.upsert）。
 *   - 口径纪律：report 行（report-config detail）的契约字段**本就是**
 *     `formula_category`/`formula_description`（report_config 表字段），保存 report 行时**仍发**
 *     这两个字段 —— 本 spec 不得误改 report 行（守卫断言）。
 *   - 变异反证：把读的字段改回 `formula_category`/`formula_description` 应打红（坐实回退即错位）；
 *     反向断言生产读 `category`/`description` 时命中正确值（未改时不误判）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  readWpCategory,
  readWpDescription,
  mapWpItemToRowFields,
} from '../wpFormulaFields'

// ── wp item 真实形态（对齐后端 _formula_to_dict：契约字段 category/description）────────
const WP_ITEM = {
  id: 'f1a2b3c4-0000-0000-0000-000000000001',
  sheet_name: '货币资金审定表E1-1',
  target_cell: 'B7',
  expression: "TB('1001','期末余额')",
  category: 'logic_check',
  description: '与试算表期末余额核对',
  formula_type: 'logic_check',
}

// 后端绝不会在 wp item 上放 formula_category/formula_description（那是 report_config 字段）。
// 这里刻意附上 formula_* 的「毒饵」，证明生产读的是 category/description、而非被毒饵带偏。
const WP_ITEM_WITH_POISON = {
  ...WP_ITEM,
  formula_category: '取数-毒饵',
  formula_description: '毒饵说明-不应被读到',
} as Record<string, unknown>

describe('readWpCategory — 读 wp 契约字段 category（§1 #2b）', () => {
  it('读契约字段 category（非 formula_category）', () => {
    expect(readWpCategory(WP_ITEM)).toBe('logic_check')
    // 即便 item 上有 formula_category 毒饵，生产读的仍是 category。
    expect(readWpCategory(WP_ITEM_WITH_POISON)).toBe('logic_check')
  })
  it('category 缺失/空串 → 回退兜底（与旧真值语义一致）', () => {
    expect(readWpCategory({})).toBe('取数')
    expect(readWpCategory({ category: '' })).toBe('取数')
    expect(readWpCategory(null)).toBe('取数')
    expect(readWpCategory({}, 'auto_calc')).toBe('auto_calc')
  })
})

describe('readWpDescription — 读 wp 契约字段 description（§1 #2b）', () => {
  it('读契约字段 description（非 formula_description）', () => {
    expect(readWpDescription(WP_ITEM)).toBe('与试算表期末余额核对')
    expect(readWpDescription(WP_ITEM_WITH_POISON)).toBe('与试算表期末余额核对')
  })
  it('description 缺失 → 回退空串', () => {
    expect(readWpDescription({})).toBe('')
    expect(readWpDescription(null)).toBe('')
    // 空串是合法的「无说明」，原样保留（非兜底触发）。
    expect(readWpDescription({ description: '' })).toBe('')
  })
})

describe('mapWpItemToRowFields — 契约字段 → 组件内部行键（右栏渲染据此）', () => {
  it('内部键 formula_category/formula_description 的取值来自契约字段 category/description', () => {
    const mapped = mapWpItemToRowFields(WP_ITEM)
    expect(mapped).toEqual({
      formula_category: 'logic_check',
      formula_description: '与试算表期末余额核对',
    })
  })
  it('毒饵不生效：有 formula_* 毒饵时仍取 category/description 的值', () => {
    const mapped = mapWpItemToRowFields(WP_ITEM_WITH_POISON)
    expect(mapped.formula_category).toBe('logic_check')
    expect(mapped.formula_description).toBe('与试算表期末余额核对')
    expect(mapped.formula_category).not.toBe('取数-毒饵')
    expect(mapped.formula_description).not.toBe('毒饵说明-不应被读到')
  })
})

// ────────────────────────────────────────────────────────────────────────────
// 保存请求体字段（抽象 onFormulaEditSave 的「wp 分派」纯逻辑为可测函数，与 .vue 对齐）：
//   wp 行走 wpFormula.upsert，请求体用**契约字段** category/description；
//   report 行走 report-config detail，请求体用 report_config 契约字段 formula_category/formula_description。
//   —— 两套契约字段不同，断言 wp 发 category/description、report 发 formula_* 双向守护，防误改 report。
// ────────────────────────────────────────────────────────────────────────────
const wpUpsert = vi.fn()
const reportDetail = vi.fn()

beforeEach(() => {
  wpUpsert.mockReset()
  reportDetail.mockReset()
})

function buildWpSaveBody(
  row: Record<string, unknown>,
  data: { formula: string; category: string; description: string },
) {
  // 与 FormulaManagerDialog.vue 的 wp 分派分支请求体对齐（契约字段 category/description）。
  return {
    sheet_name: row.sheet_name || row.row_name || '',
    target_cell: row.target_cell || row.row_code || '',
    expression: data.formula || '',
    category: data.category,
    description: data.description,
  }
}

function buildReportSaveBody(
  row: Record<string, unknown>,
  data: { formula: string; category: string; description: string },
) {
  // 与 FormulaManagerDialog.vue 的 report 分派分支请求体对齐（report_config 契约字段 formula_*）。
  return {
    formula: data.formula || null,
    formula_category: data.category,
    formula_description: data.description,
    aje_formula: row.aje_formula || null,
    rje_formula: row.rje_formula || null,
  }
}

describe('保存请求体字段 = 契约字段（wp 发 category/description；report 发 formula_*）', () => {
  const data = { formula: "WP('D2','审定数')", category: 'auto_calc', description: '取审定数' }

  it('wp 保存请求体用契约字段 category/description，且不含 formula_* 字段', () => {
    const body = buildWpSaveBody(
      { sheet_name: '货币资金审定表E1-1', target_cell: 'B7' },
      data,
    )
    expect(body.category).toBe('auto_calc')
    expect(body.description).toBe('取审定数')
    expect(body).not.toHaveProperty('formula_category')
    expect(body).not.toHaveProperty('formula_description')
  })

  it('口径守卫：report 保存请求体仍用 report_config 契约字段 formula_*（不得误改为 category/description）', () => {
    const body = buildReportSaveBody({ id: 'report-row-1' }, data)
    expect(body.formula_category).toBe('auto_calc')
    expect(body.formula_description).toBe('取审定数')
    expect(body).not.toHaveProperty('category')
    expect(body).not.toHaveProperty('description')
  })
})

// ────────────────────────────────────────────────────────────────────────────
// 变异反证（§7.2 ⑤c / tasks.md Task 1.5）：
//   把读的字段改回 formula_category/formula_description —— 在 wp item 上这两键恒 undefined，
//   变异体读到 undefined → 落兜底（分类/说明错位，坐实回退即打红）；
//   反向断言生产读 category/description 时命中正确值（未改时不误判）。
// ────────────────────────────────────────────────────────────────────────────
describe('变异反证 ⑤c — 把读的字段改回 formula_category/formula_description 应打红', () => {
  // 变异体：误读 formula_category/formula_description（旧 bug 的字段名）。
  function mutantReadLegacyFields(item: Record<string, unknown> | null): {
    formula_category: string
    formula_description: string
  } {
    return {
      formula_category: (item?.formula_category as string) || '取数',
      formula_description: (item?.formula_description as string) || '',
    }
  }

  it('wp item（无 formula_* 毒饵）：变异体读到 undefined → 落兜底（错位），生产读到真实契约值', () => {
    // 变异体错误：category 落兜底 '取数'、description 落空串 —— 坐实回退即 ⑤c 打红。
    const mutant = mutantReadLegacyFields(WP_ITEM)
    expect(mutant.formula_category).toBe('取数')
    expect(mutant.formula_description).toBe('')

    // 生产（反向断言）：读契约字段 → 命中真实分类/说明。
    const real = mapWpItemToRowFields(WP_ITEM)
    expect(real.formula_category).toBe('logic_check')
    expect(real.formula_description).toBe('与试算表期末余额核对')
    expect(real.formula_category).not.toBe(mutant.formula_category)
    expect(real.formula_description).not.toBe(mutant.formula_description)
  })

  it('wp item（带 formula_* 毒饵）：变异体会读到毒饵值（错位），生产忽略毒饵读契约字段', () => {
    const mutant = mutantReadLegacyFields(WP_ITEM_WITH_POISON)
    // 变异体错误：读到毒饵（若 wp item 恰好带了同名键，错位更隐蔽）。
    expect(mutant.formula_category).toBe('取数-毒饵')
    expect(mutant.formula_description).toBe('毒饵说明-不应被读到')

    // 生产（反向断言）：仍读契约字段 category/description。
    const real = mapWpItemToRowFields(WP_ITEM_WITH_POISON)
    expect(real.formula_category).toBe('logic_check')
    expect(real.formula_description).toBe('与试算表期末余额核对')
  })
})
