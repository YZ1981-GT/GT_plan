/**
 * K2 其他流动资产 披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源（三源互证，裁决见 spec design §概览）：
 * - 源 xlsx `backend/wp_templates/K/K2 其他流动资产.xlsx` 的
 *   `附注披露信息（上市公司）` / `附注披露信息（国企）`：两版都只有一张三列明细表
 *   （项目 / 期末 / 期初），数据引 `'明细表K2-2'!A11~A14,A17`。
 * - `note_template_{listed,soe}.json` §五、13 / §八、14（交付物权威）：列名与固定行名。
 * - `note_check_preset_formulas.json` F13-1 / F13-1a / F13-2：只对①明细表设勾稽，
 *   故表②合同取得成本、表③碳排放配额变动是**上市条件性披露表**。
 *
 * 报表行: BS-014 其他流动资产（实证 TB('1901')；历史误写 account_code 1231 = 坏账准备）
 *
 * spec: .kiro/specs/k2-other-current-assets-disclosure-alignment/ R5
 */
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'

export type K2DisclosureVariant = 'listed' | 'soe'

export const K2_NOTE_SECTION = {
  listed: '五、13',
  soe: '八、14',
} as const satisfies Record<K2DisclosureVariant, string>

/**
 * 源 xlsx 真实 tab 名 —— **全角括号**，勿"修正"为半角。
 * 用半角会让附注「打开同步底稿」的 `?sheet=` 精确匹配落空，跳到底稿首个 sheet。
 */
export const K2_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<K2DisclosureVariant, string>

// ── 子表名（与 note_template `tables[].name` 逐字一致）────────────────────────

export const K2_LISTED_SUBTABLE = {
  main: '其他流动资产',
  contractCost: '合同取得成本',
  carbon: '碳排放配额变动情况',
} as const

export const K2_SOE_SUBTABLE = {
  main: '其他流动资产',
} as const

/**
 * md 重建产物的历史表名（`fix_note_k2_structure.py` 已在模板侧改名）。
 * 既有项目的 `sub_table_data` 若残留这些键，同步时经 `_removed_table_keys` 清掉。
 */
export const K2_LEGACY_OBSOLETE_TABLES: readonly string[] = [
  '[披露与合同取得成本有关的资产相关的信息，包括确定该资产金额所做的判断、'
  + '该资产的摊销方法、按该资产主要类别披露的期末账面价值以及本期确认的摊销及'
  + '减值损失金额等。例如：',
  '项  目',
]

// ── 固定行名（逐字取自 note_template）─────────────────────────────────────────

export const K2_LISTED_MAIN_ROWS: readonly string[] = [
  '进项税额',
  '多交或预缴的增值税额',
  '待抵扣进项税额',
  '待认证进项税额',
  '增值税留抵税额',
  '预缴所得税',
  '委托贷款',
  '预缴其他税费',
  '短期债权投资',
  '短期其他债权投资',
  '合同取得成本',
  '应收退货成本',
  '碳排放权资产',
]

export const K2_SOE_MAIN_ROWS: readonly string[] = [
  '待抵扣进项税额',
  '预缴税金',
  '委托贷款',
  '短期债权投资',
  '短期其他债权投资',
  '合同取得成本',
  '应收退货成本',
  '碳排放权资产',
]

/** 合同取得成本变动表行序（转置结构：行=变动项目，列=资产主要类别） */
export const K2_CONTRACT_COST_ROWS: readonly string[] = [
  '期初余额',
  '本年增加',
  '本年摊销',
  '本年计提减值损失',
  '期末余额',
]

/** 合同取得成本公式行：期末余额 = 期初 + 增加 − 摊销 − 减值 */
export const K2_CONTRACT_COST_FORMULA_ROW = '期末余额'

/** 源模版示例类别（可改名可增删） */
export const K2_DEFAULT_CONTRACT_COST_CATEGORIES: readonly string[] = ['佣金支出']

export const K2_CARBON_ROWS: readonly string[] = [
  '1．本期期初碳排放配额',
  '2．本期增加的碳排放配额',
  '（1）免费分配取得的配额',
  '（2）购入取得的配额',
  '（3）其他方式增加的配额',
  '3．本期减少的碳排放配额',
  '（1）履约使用的配额',
  '（2）出售的配额',
  '（3）其他方式减少的配额',
  '4．本期期末碳排放配额',
]

export const K2_TOTAL_ROW_LABEL = '合计'

// ── 列定义 ───────────────────────────────────────────────────────────────────

/** 类别列键（`cat_1` 起，与 `categories` 下标一一对应） */
export function k2ContractCostCategoryKey(index: number): string {
  return `cat_${index + 1}`
}

function normalizeCategories(categories?: readonly string[]): string[] {
  const list = Array.isArray(categories)
    ? categories.map(c => String(c ?? '').trim()).filter(Boolean)
    : []
  return list.length ? list : [...K2_DEFAULT_CONTRACT_COST_CATEGORIES]
}

/**
 * 上市三张表列头。`categories` 可选 —— 零参调用返回 seed 形态（示例类别一列），
 * 满足 `disclosureColumnsCoverage` sweep 的空入参调用且列头非空。
 *
 * 源 xlsx 三列均为单行表头 → 全部显式 `flat`（抑制后端 `_infer_groups_from_headers`）。
 */
export function buildK2ListedColumns(categories?: readonly string[]): Record<string, ColumnDef[]> {
  const cats = normalizeCategories(categories)
  return {
    [K2_LISTED_SUBTABLE.main]: defineColumns([
      { key: 'label', label: '项目', is_label: true, flat: true },
      { key: 'end_amount', label: '期末余额', format: 'amount', align: 'right' },
      { key: 'prior_amount', label: '上年年末余额', format: 'amount', align: 'right' },
    ]),
    [K2_LISTED_SUBTABLE.contractCost]: defineColumns([
      { key: 'label', label: '项目', is_label: true, flat: true },
      ...cats.map((name, i) => ({
        key: k2ContractCostCategoryKey(i),
        label: name,
        format: 'amount' as const,
        align: 'right' as const,
      })),
      { key: 'total', label: '合计', format: 'amount', align: 'right' },
    ]),
    [K2_LISTED_SUBTABLE.carbon]: defineColumns([
      { key: 'label', label: '项目', is_label: true, flat: true },
      { key: 'current_amount', label: '本期发生额', format: 'amount', align: 'right' },
      { key: 'prior_amount', label: '上期发生额', format: 'amount', align: 'right' },
    ]),
  }
}

/** 国企单表列头（末列是「期初余额」，与上市的「上年年末余额」不同，故独立声明） */
export function buildK2SoeColumns(): Record<string, ColumnDef[]> {
  return {
    [K2_SOE_SUBTABLE.main]: defineColumns([
      { key: 'label', label: '项目', is_label: true, flat: true },
      { key: 'end_amount', label: '期末余额', format: 'amount', align: 'right' },
      { key: 'prior_amount', label: '期初余额', format: 'amount', align: 'right' },
    ]),
  }
}

// ── 快照 → 载荷 ──────────────────────────────────────────────────────────────

export interface K2MainRow {
  label: string
  endAmount: number
  priorAmount: number
}

export interface K2ContractCostSnapshot {
  enabled: boolean
  categories: string[]
  /** `cells[rowIdx][catIdx]`，行序同 `K2_CONTRACT_COST_ROWS` */
  cells: number[][]
}

export interface K2CarbonRow {
  label: string
  currentAmount: number
  priorAmount: number
}

export interface K2CarbonSnapshot {
  enabled: boolean
  rows: K2CarbonRow[]
}

export interface K2NoteText {
  section: string
  title: string
  text: string
}

export interface K2DisclosureSnapshot {
  mainRows: K2MainRow[]
  contractCost?: K2ContractCostSnapshot
  carbon?: K2CarbonSnapshot
  texts?: K2NoteText[]
}

export interface K2SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

function resolveCurrentStandard(variant: K2DisclosureVariant): string {
  return variant === 'listed' ? 'listed_standalone' : 'soe_standalone'
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 明细行 + 合计行（合计 = 各明细行之和，逐列） */
function buildMainTableRows(rows: readonly K2MainRow[]): Array<Record<string, unknown>> {
  const data = rows
    .filter(r => String(r?.label ?? '').trim())
    .map(r => ({
      label: String(r.label).trim(),
      end_amount: num(r.endAmount),
      prior_amount: num(r.priorAmount),
    }))
  return [
    ...data,
    {
      label: K2_TOTAL_ROW_LABEL,
      end_amount: data.reduce((s, r) => s + r.end_amount, 0),
      prior_amount: data.reduce((s, r) => s + r.prior_amount, 0),
      is_total: true,
    },
  ]
}

/** 合同取得成本：每行按类别列展开 + 合计列（= 各类别之和） */
function buildContractCostRows(snap: K2ContractCostSnapshot): Array<Record<string, unknown>> {
  const cats = normalizeCategories(snap.categories)
  return K2_CONTRACT_COST_ROWS.map((label, rowIdx) => {
    const row: Record<string, unknown> = { label }
    let total = 0
    cats.forEach((_c, catIdx) => {
      const v = num(snap.cells?.[rowIdx]?.[catIdx])
      row[k2ContractCostCategoryKey(catIdx)] = v
      total += v
    })
    row.total = total
    return row
  })
}

function buildCarbonRows(snap: K2CarbonSnapshot): Array<Record<string, unknown>> {
  const byLabel = new Map(
    (snap.rows ?? []).map(r => [String(r?.label ?? '').trim(), r] as const),
  )
  return K2_CARBON_ROWS.map(label => {
    const hit = byLabel.get(label)
    return {
      label,
      current_amount: num(hit?.currentAmount),
      prior_amount: num(hit?.priorAmount),
    }
  })
}

/**
 * 构建同步载荷。
 *
 * - 上市：主表恒推；合同取得成本 / 碳排放两张条件性表按 `enabled` 推送，
 *   关闭时表名进 `_removed_table_keys`（源模板「不存在的项目请删除」）。
 * - 国企：只有主表。
 * - 历史表名恒列入 `_removed_table_keys`（本次推送的键由后端跳过）。
 */
export function buildK2SyncPayload(
  variant: K2DisclosureVariant,
  wpId: string,
  snapshot: K2DisclosureSnapshot,
): K2SyncPayload {
  const sub: Record<string, unknown> = {}
  let columns: Record<string, ColumnDef[]>
  const removed: string[] = [...K2_LEGACY_OBSOLETE_TABLES]

  if (variant === 'listed') {
    const cc = snapshot.contractCost
    const cats = normalizeCategories(cc?.categories)
    columns = buildK2ListedColumns(cats)
    sub[K2_LISTED_SUBTABLE.main] = buildMainTableRows(snapshot.mainRows ?? [])

    if (cc?.enabled) {
      sub[K2_LISTED_SUBTABLE.contractCost] = buildContractCostRows(cc)
    } else {
      removed.push(K2_LISTED_SUBTABLE.contractCost)
      delete columns[K2_LISTED_SUBTABLE.contractCost]
    }

    const carbon = snapshot.carbon
    if (carbon?.enabled) {
      sub[K2_LISTED_SUBTABLE.carbon] = buildCarbonRows(carbon)
    } else {
      removed.push(K2_LISTED_SUBTABLE.carbon)
      delete columns[K2_LISTED_SUBTABLE.carbon]
    }
  } else {
    columns = buildK2SoeColumns()
    sub[K2_SOE_SUBTABLE.main] = buildMainTableRows(snapshot.mainRows ?? [])
  }

  const texts = (snapshot.texts ?? []).filter(t => String(t?.text ?? '').trim())
  if (texts.length) {
    sub._note_texts = texts.map(t => ({
      section: t.section,
      title: t.title,
      text: String(t.text).trim(),
    }))
  }
  // 本次推送的表名不进 removed（后端也会跳过，双保险）
  const pushed = new Set(Object.keys(sub))
  sub._removed_table_keys = removed.filter(name => !pushed.has(name))

  return {
    wp_id: wpId,
    sheet_name: K2_DISCLOSURE_SHEET_NAME[variant],
    section_id: K2_NOTE_SECTION[variant],
    current_standard: resolveCurrentStandard(variant),
    sub_table_data: sub,
    columns,
  }
}
