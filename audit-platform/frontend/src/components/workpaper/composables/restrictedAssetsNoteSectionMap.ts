/**
 * 附注「所有权或使用权受到限制的资产」→ **八循环共享**的行级合并载荷构造件。
 *
 * | 段 owner | 段标签 | 归属循环 | listed `五、32` | soe `八、93` |
 * |----------|--------|---------|----------------|-------------|
 * | `BS-002` | 货币资金 | E1 | ✅ | ✅ |
 * | `BS-005` | 应收票据 | D1 | ✅ | ✅ |
 * | `BS-006` | 应收账款 | D2 | ✅ | ✅ |
 * | `BS-007` | 应收款项融资 | D5 | — | ✅ |
 * | `BS-010` | 存货 | F2 | ✅ | ✅ |
 * | `BS-028` | 固定资产 | H1 | ✅ | ✅ |
 * | `BS-029` | 在建工程 | H2 | — | ✅ |
 * | `BS-032` | 无形资产 | I1 | ✅ | ✅ |
 *
 * 🔴 **这是多段共享表** —— 每个循环只负责自己那一段，载荷必须带
 * `sub_table_data._row_scope`，服务端只替换该段、段外行原样保留；
 * 段边界解析不出时整表跳过写入（fail closed），绝不退化为整表覆盖。
 *
 * 🔴 **listed 是双期拆两张表**（主表=期末 / 「（续：上年年末）」=上年年末）
 * → 同一 owner 要发**两个 payload**；soe 是单表 3 列（含受限原因）。
 *
 * 🔴 **表级合计行与 soe 末行「其他」不属于任何 owner**：前者由平台
 * `Segment.data_end` 保住，后者由模板 `row_type: "unowned"` 保住（本 spec Task 1/3）。
 *
 * 文件名不匹配 `WP_CODE_RE`（`^([a-z]+\d+)NoteSectionMap\.ts$`）是**故意的** ——
 * 共享表一个章节有多个 owner，不该进 section→wp 的 1:1 反查 registry
 * （同 `e1FxNoteSectionMap.ts` 与 M 循环共享 map 的既有机制）。
 *
 * spec: .kiro/specs/restricted-assets-note-row-scope-rollout/ Requirements 3.1~3.6
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type RestrictedAssetsVariant = 'listed' | 'soe'

/** 附注章节号（真源 `note_template_variant_matrix.json`）。 */
export const RESTRICTED_ASSETS_NOTE_SECTION = {
  listed: '五、32',
  soe: '八、93',
} as const satisfies Record<RestrictedAssetsVariant, string>

/**
 * 附注子表名（**逐字**取自 `note_template_{listed,soe}.json`）。
 * 错一个字就产生孤儿表（`sub_table_data` 以表名为键）。
 */
export const RESTRICTED_ASSETS_TABLE = {
  /** listed 主表：项目 / 期末 */
  listedMain: '所有权或使用权受到限制的资产',
  /** listed 续表：项目 / 上年年末（本 spec Task 3 由裸名「续：」正名而来） */
  listedPrior: '所有权或使用权受到限制的资产（续：上年年末）',
  /** soe 单表：项目 / 期末账面价值 / 受限原因（注意是「和」不是「或」） */
  soe: '所有权和使用权受到限制的资产',
} as const

/** 段 owner code → 段标签（与模板段首行 `label` 逐字一致）。 */
export const RESTRICTED_ASSETS_OWNERS = Object.freeze({
  'BS-002': '货币资金',
  'BS-005': '应收票据',
  'BS-006': '应收账款',
  'BS-007': '应收款项融资',
  'BS-010': '存货',
  'BS-028': '固定资产',
  'BS-029': '在建工程',
  'BS-032': '无形资产',
} as const)

export type RestrictedAssetsOwner = keyof typeof RESTRICTED_ASSETS_OWNERS

/** 仅 soe 有的段（listed `五、32` 无这两行）。 */
export const RESTRICTED_ASSETS_SOE_ONLY_OWNERS: readonly RestrictedAssetsOwner[] =
  Object.freeze(['BS-007', 'BS-029'])

/** 该 owner 在指定变体下是否有落点。 */
export function isRestrictedAssetsOwnerApplicable(
  variant: RestrictedAssetsVariant,
  owner: RestrictedAssetsOwner,
): boolean {
  if (variant === 'soe') return owner in RESTRICTED_ASSETS_OWNERS
  return !RESTRICTED_ASSETS_SOE_ONLY_OWNERS.includes(owner)
}

const AMT = 'amount' as const

// ── 列定义 ───────────────────────────────────────────────────────────────────
// 🔴 单级表头必标 `flat`，且 **seed 与推送两处都要标**（H8 踩过只加一侧的坑）。
//    模板侧由 `fix_note_restricted_assets_structure.py` 写入，推送侧就是这里。
const COLS_LISTED_MAIN: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'end_amount', label: '期末', format: AMT },
]
const COLS_LISTED_PRIOR: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'prior_amount', label: '上年年末', format: AMT },
]
const COLS_SOE: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'end_carrying', label: '期末账面价值', format: AMT },
  { key: 'reason', label: '受限原因', format: 'text' },
]

/** **零入参**（平台 `disclosureColumnsCoverage` 的 sweep 用空参调用所有 `build*Columns`）。 */
export function buildRestrictedAssetsColumns(): Record<string, ColumnDef[]> {
  return {
    [RESTRICTED_ASSETS_TABLE.listedMain]: COLS_LISTED_MAIN,
    [RESTRICTED_ASSETS_TABLE.listedPrior]: COLS_LISTED_PRIOR,
    [RESTRICTED_ASSETS_TABLE.soe]: COLS_SOE,
  }
}

/**
 * 底稿披露 sheet 真实 tab 名 —— 由各 owner 循环传入。
 *
 * `_last_sync_sheet` 供附注侧「打开同步底稿」反查，故必须是源 xlsx 的真实 tab 名，
 * 不能用 `X-note-listed` 这类合成标识。
 */
export interface RestrictedAssetsSheetNames {
  listed: string
  soe: string
}

/**
 * 段内一行。段内行数**允许 ≠ 模板段行数**（行级合并按整段替换），
 * 但本表语义是「按资产类别分项披露」→ 常规就是**一行**（段标签 + 受限金额 + 原因），
 * 明细留在各循环自己的附注章节（如 E1 的 ②表受限明细在 `五、1`/`八、1`）。
 */
export interface RestrictedAssetsRowLike {
  /** 行标签；常规 = 段标签（`RESTRICTED_ASSETS_OWNERS[owner]`） */
  label: string
  /** 期末（listed 主表 `end_amount` / soe `end_carrying`） */
  endAmount: number
  /** 上年年末（listed 续表 `prior_amount`）；soe 无该列 */
  priorAmount?: number
  /** 受限原因（soe `reason`）；listed 源模板无该列 → 不推 */
  reason?: string
}

export interface RestrictedAssetsSpec {
  ownerRowCode: RestrictedAssetsOwner
  rows: readonly RestrictedAssetsRowLike[]
}

export interface RestrictedAssetsPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

/**
 * `current_standard` 解析（与各循环 `resolveXCurrentStandard` 同款语义）。
 *
 * 🟡 平台现有 40+ 份同逻辑拷贝（每个 `xNoteSectionMap.ts` 一份），收敛属另一笔账；
 * 本文件是八循环共享件，故在此定义一份而不是引某个循环的版本。
 */
export function resolveRestrictedAssetsStandard(
  variant: RestrictedAssetsVariant,
  applicableStandards: readonly string[] | null | undefined,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  const consolidated = (prefix: string) =>
    list.some((s) => s === `${prefix}_consolidated` || (s.includes(prefix) && s.includes('consol')))
  if (variant === 'listed') {
    return consolidated('listed') ? 'listed_consolidated' : 'listed_standalone'
  }
  return consolidated('soe') ? 'soe_consolidated' : 'soe_standalone'
}

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
/** 金额取 2 位（平台口径）；消除底稿侧浮点乘积噪声。 */
const money = (v: number): number => Math.round(v * 100) / 100

/** 是否有实质数据（全零/空行不推 —— 空推送会把段恢复成模板骨架）。 */
function hasValue(rows: readonly RestrictedAssetsRowLike[]): boolean {
  return rows.some(
    (r) => num(r.endAmount) !== 0 || num(r.priorAmount) !== 0 || !!String(r.reason ?? '').trim(),
  )
}

/**
 * 把多行受限明细归纳成**一行**段内行（本表按资产类别披露的常规形态）。
 *
 * - 金额求和（期末 / 上年年末各自求和）
 * - 受限原因去重拼接（`；` 分隔），空值跳过
 *
 * 各 owner 循环若本就是「一个科目一行」可直接自建 `rows`，不必用本函数。
 */
export function summarizeRestrictedRows(
  label: string,
  details: readonly { endAmount?: number; priorAmount?: number; reason?: string }[],
): RestrictedAssetsRowLike[] {
  const reasons: string[] = []
  let end = 0
  let prior = 0
  // 🔴 「一条 detail 都没声明 priorAmount」与「声明了但是 0」必须区分 ——
  //    前者是「本循环没有上年年末数据」（如 D1 的质押表只有期末），
  //    此时不能推 0 去覆盖审计师在附注续表手填的上年年末值。
  let hasPrior = false
  for (const d of details || []) {
    end += num(d.endAmount)
    if (d.priorAmount !== undefined && d.priorAmount !== null) {
      hasPrior = true
      prior += num(d.priorAmount)
    }
    const reason = String(d.reason ?? '').trim()
    if (reason && !reasons.includes(reason)) reasons.push(reason)
  }
  return [
    {
      label,
      endAmount: money(end),
      ...(hasPrior ? { priorAmount: money(prior) } : {}),
      reason: reasons.join('；'),
    },
  ]
}

/**
 * 构建行级合并载荷。**无实质数据时返回 `[]`**（不推空段）。
 *
 * listed → 2 个 payload（主表期末 + 续表上年年末，各自带 `_row_scope`）；
 * soe → 1 个。该 owner 在本变体无落点时同样返回 `[]`（如 H2 在 listed 侧）。
 */
export function buildRestrictedAssetsPayloads(
  variant: RestrictedAssetsVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  spec: RestrictedAssetsSpec,
  sheetNames: RestrictedAssetsSheetNames,
): RestrictedAssetsPayload[] {
  const owner = spec.ownerRowCode
  if (!isRestrictedAssetsOwnerApplicable(variant, owner)) return []
  const rows = (spec.rows || []).filter((r) => !!String(r.label ?? '').trim())
  if (!rows.length || !hasValue(rows)) return []

  const allCols = buildRestrictedAssetsColumns()
  const base = {
    wp_id: wpId,
    section_id: RESTRICTED_ASSETS_NOTE_SECTION[variant],
    current_standard: resolveRestrictedAssetsStandard(variant, applicableStandards),
    sheet_name: sheetNames[variant],
  }
  const scope = (table: string) => ({ [table]: { owner_row_code: owner } })

  if (variant === 'soe') {
    const table = RESTRICTED_ASSETS_TABLE.soe
    return [
      {
        ...base,
        sub_table_data: {
          [table]: rows.map((r) => ({
            label: r.label,
            end_carrying: money(num(r.endAmount)),
            // 受限原因是 soe 源模板的第 3 列；空串而非 null，避免附注显示「-」
            reason: String(r.reason ?? '').trim(),
          })),
          _row_scope: scope(table),
        },
        columns: { [table]: allCols[table] },
      },
    ]
  }

  // listed：双期拆两张表 → 最多两个 payload（两次都带 `_row_scope`，owner 相同、表名不同）
  const main = RESTRICTED_ASSETS_TABLE.listedMain
  const prior = RESTRICTED_ASSETS_TABLE.listedPrior
  const out: RestrictedAssetsPayload[] = [
    {
      ...base,
      sub_table_data: {
        [main]: rows.map((r) => ({ label: r.label, end_amount: money(num(r.endAmount)) })),
        _row_scope: scope(main),
      },
      columns: { [main]: allCols[main] },
    },
  ]
  // 🔴 只有当**至少一行声明了** `priorAmount` 才推续表。
  //    「没声明」= 本循环没有上年年末数据（如 D1 的「期末已质押的应收票据」表只有期末）
  //    → 推 0 会覆盖审计师在附注续表手填的上年年末值（宁缺勿造）。
  const hasPrior = rows.some((r) => r.priorAmount !== undefined && r.priorAmount !== null)
  if (hasPrior) {
    out.push({
      ...base,
      sub_table_data: {
        [prior]: rows.map((r) => ({ label: r.label, prior_amount: money(num(r.priorAmount)) })),
        _row_scope: scope(prior),
      },
      columns: { [prior]: allCols[prior] },
    })
  }
  return out
}
