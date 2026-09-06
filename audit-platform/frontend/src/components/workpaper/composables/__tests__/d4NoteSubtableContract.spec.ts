/**
 * D4 营业收入/营业成本披露载荷契约守卫（上市 §五、62 / 国企 §八、64）。
 *
 * 接共享 helper P1~P6 + D4 专属：
 * - Property 12: 两版（3）按地区叶子列名不得统一（listed "主营业务收入" ≠ soe "收入"）
 * - Property 12b: 两版（4）表名不得统一（listed ≠ soe）
 * - （8）仅上市: SOE payload 不得含试运行表
 * - Property 14: flat 双侧一致（载荷声明 flat 的表，模板 seed columns 也标 flat）
 *
 * spec: d4-four-table-extraction-and-disclosure-alignment (Task 5.6)
 * Requirements: 9.1, 9.5, 9.6
 *
 * **Validates: Requirements 9.1, 9.5, 9.6**
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  D4_NOTE_SECTION,
  D4_DISCLOSURE_SHEET_NAME,
  buildD4SyncPayload,
  type D4DisclosureSnapshot,
} from '../d4NoteSectionMap'
import {
  buildD4TwoPeriodColumns,
  buildD4TransposeColumns,
  buildD4ObligationColumns,
  D4_DEFAULT_CATEGORIES,
} from '../d4DisclosureModel'

// ─── 表名常量（与 d4NoteSectionMap.ts 的 T 对象一致）────────────────────

const LISTED_SUBTABLE = {
  main: '营业收入和营业成本',
  industry: '营业收入、营业成本按行业（或产品类型）划分',
  region: '营业收入、营业成本按地区划分',
  timing: '营业收入、营业成本按分解信息',
  obligation: '与剩余履约义务有关的信息',
  trialRun: '试运行销售收入',
} as const

const SOE_SUBTABLE = {
  main: '营业收入、营业成本',
  industry: '按行业（或产品类型）划分',
  region: '营业收入、营业成本按地区划分',
  timing: '营业收入分解信息',
  obligation: '与剩余履约义务有关的信息',
} as const

// ─── 列构造器（从真实 payload 提取 → 保证与 buildD4SyncPayload 同源）──

/** 构造一个最小快照用于提取 columns */
function minimalSnapshot(): D4DisclosureSnapshot {
  return {
    revenueRows: [{ label: 'x', currentRevenue: 0, currentCost: 0, priorRevenue: 0, priorCost: 0 }],
    revenueTotal: { label: '合计', currentRevenue: 0, currentCost: 0, priorRevenue: 0, priorCost: 0 },
    industryRows: [{ label: 'x', currentRevenue: 0, currentCost: 0, priorRevenue: 0, priorCost: 0 }],
    regionRows: [{ label: 'x', currentRevenue: 0, currentCost: 0, priorRevenue: 0, priorCost: 0 }],
    timingRows: [{ label: 'x', cat_1_revenue: 0, cat_1_cost: 0, total_revenue: 0, total_cost: 0 }],
    timingCategories: [...D4_DEFAULT_CATEGORIES],
    section6Rows: [{ label: 'x', year_2026: 0, year_2027: 0 }],
    section8Rows: [{ label: 'x', endRevenue: 0, endCost: 0, priorRevenue: 0, priorCost: 0 }],
    auditYear: 2025,
    notes: {},
  }
}

function buildListedColumns(): Record<string, any[]> {
  const p = buildD4SyncPayload('listed', 'wp-test', null, minimalSnapshot())
  return p.columns
}

function buildSoeColumns(): Record<string, any[]> {
  const p = buildD4SyncPayload('soe', 'wp-test', null, minimalSnapshot())
  return p.columns
}

// ─── 共享 helper P1~P6 ──────────────────────────────────────────────

/**
 * P3 说明：D4 的两级表头表（主表/行业/地区/分解/试运行）使用混合分组 ——
 * ═══ 2026-09-06：删除原 `columnsPending` 豁免 ═══
 *
 * 原注释称「标签列 flat + 数据列 group 是附注投影器已支持的混合分组形态（H1 范式）」，
 * 并据此把 5 + 4 张表登记进 `columnsPending` 跳过 P3。**该前提与后端实现相反**：
 * `note_sub_table_projector._extract_column_groups` 里
 * `if any(isinstance(d, dict) and d.get("flat") for d in defs): return []`
 * —— 任一列带 `flat` 就**整表**返回空分组、禁止任何分组渲染。
 * 也就是说这些表的 `group` 声明全被标签列那个 `flat` 抑制掉了，两级表头从未生效。
 *
 * 生产侧已移除标签列的 `flat`（见 `d4DisclosureModel.ts`），这些表现在能正常表态，
 * 故豁免登记按「已修好必删」一并移除，让 P3 真正把关。
 */
runDisclosureSubtableContract({
  cycle: 'D4',
  variants: [
    {
      variant: 'listed',
      section: D4_NOTE_SECTION.listed,
      subtables: LISTED_SUBTABLE,
      columns: buildListedColumns(),
    },
    {
      variant: 'soe',
      section: D4_NOTE_SECTION.soe,
      subtables: SOE_SUBTABLE,
      columns: buildSoeColumns(),
    },
  ],
})

// ─── D4 专属断言 ────────────────────────────────────────────────────

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

type NoteSection = { tables?: Array<{ name?: string; columns?: Array<{ flat?: boolean; group?: string }> }> }

function loadD4Section(variant: 'listed' | 'soe'): NoteSection {
  const file = variant === 'listed' ? 'note_template_listed.json' : 'note_template_soe.json'
  const raw = JSON.parse(
    readFileSync(resolve(REPO_ROOT, 'backend/data', file), 'utf-8'),
  ) as { sections?: NoteSection[] }
  const hit = (raw.sections ?? []).find(
    (s: any) => String(s.section_number) === D4_NOTE_SECTION[variant],
  )
  expect(hit, `模板缺章节 ${D4_NOTE_SECTION[variant]}`).toBeDefined()
  return hit!
}

function snapshot(): D4DisclosureSnapshot {
  return {
    revenueRows: [
      { label: '主营业务', currentRevenue: 1000, currentCost: 600, priorRevenue: 900, priorCost: 550 },
    ],
    revenueTotal: { label: '合计', currentRevenue: 1000, currentCost: 600, priorRevenue: 900, priorCost: 550 },
    industryRows: [{ label: '消费品', currentRevenue: 700, currentCost: 400, priorRevenue: 600, priorCost: 350 }],
    regionRows: [{ label: '华东', currentRevenue: 500, currentCost: 300, priorRevenue: 450, priorCost: 270 }],
    timingRows: [{ label: '在某一时点确认', cat_1_revenue: 300, cat_1_cost: 180, total_revenue: 300, total_cost: 180 }],
    timingCategories: [...D4_DEFAULT_CATEGORIES],
    section6Rows: [{ label: 'A合同', year_2026: 500, year_2027: 300 }],
    section8Rows: [{ label: '固定资产试运行收入', endRevenue: 100, endCost: 50, priorRevenue: 80, priorCost: 40 }],
    auditYear: 2025,
    notes: {},
  }
}

describe('Property 12: 两版列名不得统一', () => {
  it('（3）按地区叶子列名 listed ≠ soe', () => {
    const listedCols = buildD4TwoPeriodColumns('region_listed')
    const soeCols = buildD4TwoPeriodColumns('region_soe')
    // 上市 = 主营业务收入/主营业务成本
    expect(listedCols[1].label).toBe('主营业务收入')
    expect(listedCols[2].label).toBe('主营业务成本')
    // 国企 = 收入/成本
    expect(soeCols[1].label).toBe('收入')
    expect(soeCols[2].label).toBe('成本')
    // 两版不同
    expect(listedCols[1].label).not.toBe(soeCols[1].label)
    expect(listedCols[2].label).not.toBe(soeCols[2].label)
  })

  it('（4）分解信息表名 listed ≠ soe', () => {
    expect(LISTED_SUBTABLE.timing).not.toBe(SOE_SUBTABLE.timing)
    expect(LISTED_SUBTABLE.timing).toBe('营业收入、营业成本按分解信息')
    expect(SOE_SUBTABLE.timing).toBe('营业收入分解信息')
  })

  it('（2）按行业表名 listed ≠ soe', () => {
    expect(LISTED_SUBTABLE.industry).not.toBe(SOE_SUBTABLE.industry)
  })

  it('（1）主表名 listed ≠ soe', () => {
    expect(LISTED_SUBTABLE.main).not.toBe(SOE_SUBTABLE.main)
  })
})

describe('（8）试运行销售收入仅上市', () => {
  it('SOE payload 不含试运行表', () => {
    const p = buildD4SyncPayload('soe', 'wp-1', null, snapshot())
    const dataKeys = Object.keys(p.sub_table_data).filter(k => !k.startsWith('_'))
    expect(dataKeys).not.toContain('试运行销售收入')
  })

  it('listed payload 含试运行表', () => {
    const p = buildD4SyncPayload('listed', 'wp-1', null, snapshot())
    const dataKeys = Object.keys(p.sub_table_data).filter(k => !k.startsWith('_'))
    expect(dataKeys).toContain('试运行销售收入')
  })

  it('SOE 模板无试运行表', () => {
    const sec = loadD4Section('soe')
    const names = (sec.tables ?? []).map(t => t.name)
    expect(names).not.toContain('试运行销售收入')
  })
})

describe('Property 14: flat 双侧一致', () => {
  it('载荷声明 flat 的表，模板 seed columns 也标 flat', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const sec = loadD4Section(variant)
      const cols = variant === 'listed' ? buildListedColumns() : buildSoeColumns()
      const subtables = variant === 'listed' ? LISTED_SUBTABLE : SOE_SUBTABLE

      for (const tableName of Object.values(subtables)) {
        const payloadCols = cols[tableName] ?? []
        const payloadHasFlat = payloadCols.some((c: any) => c.flat === true)
        const payloadHasGroup = payloadCols.some((c: any) => c.group)

        // Find template table
        const tplTable = (sec.tables ?? []).find(t => t.name === tableName)
        if (!tplTable || !tplTable.columns || tplTable.columns.length === 0) continue

        const tplHasFlat = tplTable.columns.some(c => c.flat === true)
        const tplHasGroup = tplTable.columns.some(c => !!c.group)

        if (payloadHasFlat && !payloadHasGroup) {
          // Payload says flat → template must also say flat (not group)
          expect(
            tplHasFlat,
            `${variant} 表「${tableName}」载荷声明 flat 但模板 seed columns 未标 flat → 推送路径会被 _infer_groups_from_headers 塞凭空父表头`,
          ).toBe(true)
          expect(tplHasGroup, `${variant}「${tableName}」flat 表模板不得有 group`).toBe(false)
        }

        if (payloadHasGroup && !payloadHasFlat) {
          // Payload says group → template must also say group (not just flat)
          expect(
            tplHasGroup,
            `${variant} 表「${tableName}」载荷声明 group 但模板 seed columns 只标 flat → seed 路径丢分组`,
          ).toBe(true)
        }
      }
    }
  })
})
