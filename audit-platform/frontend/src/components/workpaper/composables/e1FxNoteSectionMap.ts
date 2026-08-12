/**
 * E1 外币货币性项目 → 附注 `五、73`（上市）/ `八、92`（国企）**行级合并**载荷。
 *
 * 🔴 这是平台级「行级合并」能力的**首个消费者**。该附注表是**跨循环共享表**：
 * 一张表内按科目分段，段首行带 `report_row_code`：
 *
 * | 段 | row_code | 归属循环 |
 * |----|----------|---------|
 * | 货币资金 | `BS-002` | **E1（本文件）** |
 * | 应收账款 | `BS-006` | D2 |
 * | 短期借款 | `BS-041` | K |
 * | 长期借款 | `BS-061` | L |
 * | 应付债券 | `BS-062` | L |
 *
 * 🔴 短期借款段的 row_code 曾错记为 `BS-031`（那是**使用权资产** = H8 的报表行），
 * 已由 `fix_note_e1_monetary_fund_structure.py` 改成 `BS-041`（`TB('2001')`，
 * `report_config` 四准则一致）。两类后果：K 循环按 `BS-041` 声明 `_row_scope` 会
 * fail-closed 整表跳过写入（表现为「推了但没进附注」）；H8 若接入该表会错配到短期
 * 借款段。段的 `account_codes:['2001']` 本来就是对的，只有 row_code 错。
 * （E-cycle spec R7.1 / R7.2，守卫 `test_note_e1_structure.py` Property 23/24）
 *
 * 故载荷必须声明 `sub_table_data._row_scope`，服务端只替换 `BS-002` 段、
 * 段外行原样保留；段边界解析不出时**整表跳过写入**（fail closed），
 * 绝不退化为整表覆盖（那会清掉 D2/K/L 已录的段）。
 *
 * 数据来源 = 底稿披露表的「外币性货币项目」+「货币资金（原币）」两张表
 * （源 xlsx R25~R62，**两变体逐字相同**）。底稿侧 7 列含期初，附注表 4 列仅期末
 * → 只投影期末口径（不单方面扩列，扩列会波及 D2/K/L）。
 *
 * spec: .kiro/specs/disclosure-note-row-level-merge/ Requirements 7.1~7.3
 */
import type { ColumnDef } from './disclosureColumnDefs'
import { resolveE1CurrentStandard, type E1DisclosureVariant } from './e1NoteSectionMap'
import { e1BaseCurrencyLabel } from './e1CurrencyScope'

/** 附注章节号（真源 `note_template_variant_matrix.json` 的 `wai_bi_huo_bi_xing_xiang_mu`）。 */
export const E1_FX_NOTE_SECTION = {
  listed: '五、73',
  soe: '八、92',
} as const satisfies Record<E1DisclosureVariant, string>

/** 底稿披露 sheet 真实 tab 名（半角括号，与 `e1NoteSectionMap` 同源同值）。 */
export const E1_FX_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息(上市公司)',
  soe: '附注披露信息(国企)',
} as const satisfies Record<E1DisclosureVariant, string>

/**
 * 附注子表名（逐字取自 `note_template_{listed,soe}.json`，错一个字就产生孤儿表）。
 * 两变体同名。
 */
export const E1_FX_TABLE = '外币货币性项目'

/** E1 负责的段 = 货币资金段（模板段首行的 `report_row_code`）。 */
export const E1_FX_OWNER_ROW_CODE = 'BS-002'

/** 段首行标签（与模板段首行 `label` 一致，便于与他段对照）。 */
export const E1_FX_SEGMENT_LABEL = '货币资金'

/** 币种明细行的「其中：」前缀（源模板 R29 首个币种带前缀，其余缩进无前缀）。 */
export const E1_FX_DETAIL_PREFIX = '其中：'

const AMT = 'amount' as const

/**
 * 列定义 —— **4 列全 `flat`**（单级表头），key 逐字镜像附注模板的 `columns[].key`。
 *
 * 🔴 `flat` 必须 seed 与推送**两处都加**（H8 踩过只加一侧的坑）：模板侧由
 * `fix_note_e1_monetary_fund_structure.py` 写入，推送侧就是这里。
 * 少了任一处，读时投影会用 `_infer_groups_from_headers` 凭空推出父表头。
 */
const FX_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'end_fc', label: '期末外币余额', format: AMT },
  { key: 'rate', label: '折算汇率', format: 'rate' },
  { key: 'end_rmb', label: '期末折算人民币余额', format: AMT },
]

/** **零入参**（平台 `disclosureColumnsCoverage` 的 sweep 用空参调用所有 `build*Columns`）。 */
export function buildE1FxColumns(): Record<string, ColumnDef[]> {
  return { [E1_FX_TABLE]: FX_COLUMNS }
}

/** 底稿外币行（形态与 `E1TabDisclosure` 的 `ForeignCurrencyRow` 对齐的最小子集）。 */
export interface E1FxRowLike {
  /** 分组 id（详细版 = 库存现金/银行存款/财务公司存款/其他货币资金；简版 = 货币资金） */
  groupId: string
  /** 币种名（分组行为空串） */
  currency: string
  isGroup: boolean
  endForeign: number
  endRate: number
  endRmb: number
}

export interface E1FxSyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)

/**
 * 金额取 2 位（平台口径）。
 *
 * 🔴 底稿的人民币金额是 `原币 × 折算率` 的浮点乘积（实测 14000 × 7.1884 落库成
 * `100637.59999999999`）—— UI 经 `fmtAmount` 显示无碍，但落进附注 JSONB 就是噪声，
 * 也会让「段内合计 = 各币种之和」的勾稽出现 1e-11 级假差异。
 */
const money = (v: number): number => Math.round(v * 100) / 100

/**
 * 按币种聚合底稿外币叶子行（源模板 R29 口径 `=B40+B46+B52+B58`：
 * 「外币性货币项目」各币种 = 原币表四个分组同币种之和）。
 *
 * - 排除**记账本位币**（源模板 R29~R32 只列外币，人民币不在「其中：」明细里）
 * - 折算汇率取该币种首个非零汇率（源模板 R29 列 C 即 `=C46`，取某一段的折算率）
 * - 保持底稿内首次出现的币种顺序（可增删币种 → 不写死币种表）
 */
export function aggregateE1FxByCurrency(
  rows: readonly E1FxRowLike[] | null | undefined,
): Array<{ currency: string; endForeign: number; rate: number | null; endRmb: number }> {
  const base = e1BaseCurrencyLabel()
  const order: string[] = []
  const acc = new Map<string, { endForeign: number; rate: number | null; endRmb: number }>()
  for (const r of rows || []) {
    if (r.isGroup) continue
    const cur = String(r.currency || '').trim()
    if (!cur || cur === base) continue
    if (!acc.has(cur)) {
      order.push(cur)
      acc.set(cur, { endForeign: 0, rate: null, endRmb: 0 })
    }
    const item = acc.get(cur)!
    item.endForeign += num(r.endForeign)
    item.endRmb += num(r.endRmb)
    if (item.rate === null && num(r.endRate) !== 0) item.rate = num(r.endRate)
  }
  return order.map((currency) => {
    const item = acc.get(currency)!
    return {
      currency,
      endForeign: money(item.endForeign),
      rate: item.rate,
      endRmb: money(item.endRmb),
    }
  })
}

export interface E1FxSnapshot {
  /** 底稿「货币资金（原币）」表的全部行（含分组行，本函数自行过滤） */
  fxRows: readonly E1FxRowLike[]
}

/**
 * 构建外币章节的行级合并载荷。**无外币明细时返回 `null`**（不推空段 —— 空推送会把
 * 段恢复成模板骨架，等于把审计师在附注模块手填的货币资金段清空）。
 *
 * 段内行 = 段首「货币资金」（`end_rmb` = 各币种人民币金额之和，外币余额/汇率留空
 * 因为币种混合无法求和）+ 各币种「其中：X」行。
 */
export function buildE1FxSyncPayload(
  variant: E1DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snapshot: E1FxSnapshot,
): E1FxSyncPayload | null {
  const detail = aggregateE1FxByCurrency(snapshot.fxRows)
  // 全零（默认骨架未填）也不推：避免把他人手填的段清成空骨架
  const hasValue = detail.some((d) => d.endForeign !== 0 || d.endRmb !== 0)
  if (!detail.length || !hasValue) return null

  const rows: Array<Record<string, unknown>> = [
    {
      label: E1_FX_SEGMENT_LABEL,
      end_fc: null,
      rate: null,
      end_rmb: money(detail.reduce((s, d) => s + d.endRmb, 0)),
    },
    ...detail.map((d, i) => ({
      label: i === 0 ? `${E1_FX_DETAIL_PREFIX}${d.currency}` : d.currency,
      end_fc: d.endForeign,
      rate: d.rate,
      end_rmb: d.endRmb,
    })),
  ]

  return {
    wp_id: wpId,
    sheet_name: E1_FX_DISCLOSURE_SHEET_NAME[variant],
    section_id: E1_FX_NOTE_SECTION[variant],
    current_standard: resolveE1CurrentStandard(variant, applicableStandards),
    sub_table_data: {
      [E1_FX_TABLE]: rows,
      // ★ 行级合并声明：本次只负责货币资金段，其余段服务端原样保留
      _row_scope: { [E1_FX_TABLE]: { owner_row_code: E1_FX_OWNER_ROW_CODE } },
    },
    columns: buildE1FxColumns(),
  }
}
