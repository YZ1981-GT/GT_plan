/**
 * K1 四表库取数溯源（render 下发 `html_data.tb_source_codes` 的前端视图）。
 *
 * 后端真源 = `app/services/four_table/report_line_accounts.ReportLineAccounts.as_dict()`
 * （`_k1_other_receivables.render` 透出）。字段名逐字对齐，改一侧必改另一侧。
 *
 * 链路：报表行 `BS-009` → `report_config.formula`（按项目适用准则）→ 标准码
 * → `account_mapping` 反解 → 客户原始码 → `tb_balance` 叶子聚合。
 *
 * spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/ R1.7
 */

/** 解析来源：报表规则映射 / 兜底 */
export type K1ResolvedFrom = 'report_config' | 'fallback'

export interface K1TbSourceCodes {
  /** 报表行次（其他应收款 = BS-009） */
  row_code?: string
  /** 原值科目 —— 客户原始码前缀集（tb_balance 用） */
  gross?: string[]
  /** 备抵科目 —— 客户原始码前缀集 */
  provision?: string[]
  /** 原值科目 —— 标准码集（trial_balance 用） */
  gross_standard?: string[]
  /** 备抵科目 —— 标准码集 */
  provision_standard?: string[]
  /** 附加科目 `{标准码: [原始码, ...]}`（1131 应收股利 / 1132 应收利息） */
  extra?: Record<string, string[]>
  /** 报表公式里各 TB() 的符号 `[[标准码, +1|-1], ...]` */
  signed_codes?: Array<[string, number]>
  /** 命中的报表公式原文 */
  formula?: string | null
  resolved_from?: K1ResolvedFrom
  provision_resolved_from?: K1ResolvedFrom
  /** 备抵标准码是否精确反解出原始码（false = 退化为宽前缀） */
  provision_exact?: boolean
  /** 是否叠加了「其他应收款」名称过滤（保守口径） */
  use_provision_name_filter?: boolean
}

/** 中文化解析来源（UI 全中文化铁律） */
export function k1ResolvedFromLabel(v: string | undefined | null): string {
  return v === 'report_config' ? '报表规则映射' : '兜底科目'
}

/** 解析来源 → el-tag type */
export function k1ResolvedFromTagType(v: string | undefined | null): 'success' | 'warning' {
  return v === 'report_config' ? 'success' : 'warning'
}

/** 科目码集 → 展示串（空集显示占位符） */
export function k1CodeListText(codes: readonly string[] | undefined | null): string {
  const list = (codes || []).filter(Boolean)
  return list.length ? list.join('、') : '—'
}

/** 是否有可展示的溯源内容（全空时面板不渲染，避免空洞卡片） */
export function hasK1TbSourceCodes(src: K1TbSourceCodes | null | undefined): boolean {
  if (!src) return false
  return !!(
    (src.gross && src.gross.length)
    || (src.provision && src.provision.length)
    || (src.gross_standard && src.gross_standard.length)
  )
}

/** 附加科目条目（供 v-for） */
export interface K1ExtraCodeEntry {
  standard: string
  originals: string[]
  label: string
}

const EXTRA_LABELS: Record<string, string> = {
  '1131': '应收股利',
  '1132': '应收利息',
}

export function k1ExtraEntries(src: K1TbSourceCodes | null | undefined): K1ExtraCodeEntry[] {
  const extra = src?.extra || {}
  return Object.keys(extra)
    .sort()
    .map((standard) => ({
      standard,
      originals: extra[standard] || [],
      label: EXTRA_LABELS[standard] || standard,
    }))
}

/** 公式符号 → 可读串：`+ 1221　− 1231-03　+ 1131` */
export function k1SignedFormulaText(src: K1TbSourceCodes | null | undefined): string {
  const list = src?.signed_codes || []
  if (!list.length) return ''
  return list.map(([code, sign]) => `${sign < 0 ? '−' : '+'} ${code}`).join('　')
}

/** 坏账准备兜底标准码（其他应收款专属备抵；**不是** 宽口径 `1231`） */
export const K1_BAD_DEBT_FALLBACK_STANDARD = '1231-03'

/** 原值兜底标准码 */
export const K1_GROSS_FALLBACK_STANDARD = '1221'

/** 从溯源取坏账查询口径（标准码集）；缺省回退 `1231-03` */
export function k1ProvisionQueryCodes(
  src: K1TbSourceCodes | null | undefined,
): string[] {
  const list = (src?.provision_standard || []).filter(Boolean)
  return list.length ? list : [K1_BAD_DEBT_FALLBACK_STANDARD]
}

/** 从溯源取原值查询口径（标准码集）；缺省回退 `1221` */
export function k1GrossQueryCodes(
  src: K1TbSourceCodes | null | undefined,
): string[] {
  const list = (src?.gross_standard || []).filter(Boolean)
  return list.length ? list : [K1_GROSS_FALLBACK_STANDARD]
}

export interface TbCodedAmountRow {
  code: string
  unadjusted: number
  audited: number
}

/**
 * 试算平衡表行集求和 —— **只累加互不为前缀的最长码**，消除父子双计。
 *
 * 🔴 `trial_balance` 里 `1231` 与 `1231-01..05` 并存：直接把 `LIKE '1231%'` 的行全加
 * 会把父科目与子科目算两遍（旧实现的兜底请求即如此）。本函数先按「是否被更长的
 * 同前缀码覆盖」剔除父级，再求和。
 *
 * @param rows 行集（code 为 `standard_account_code`）
 * @param wanted 目标码集（如 `['1231-03']`）；行 code 须等于目标码或以其为前缀
 */
export function sumLongestPrefixOnly(
  rows: readonly TbCodedAmountRow[],
  wanted: readonly string[],
): { unadjusted: number; audited: number } {
  const targets = (wanted || []).filter(Boolean)
  const matched = (rows || []).filter((r) => {
    const c = String(r.code || '')
    return targets.some((t) => c === t || c.startsWith(t))
  })
  const codes = matched.map((r) => String(r.code || ''))
  let unadjusted = 0
  let audited = 0
  for (const r of matched) {
    const c = String(r.code || '')
    // 存在更长的、以 c 为前缀的兄弟码 → c 是父级，跳过（其金额已由子级承载）
    const hasLongerChild = codes.some((o) => o !== c && o.startsWith(c))
    if (hasLongerChild) continue
    unadjusted += Number(r.unadjusted) || 0
    audited += Number(r.audited) || 0
  }
  return { unadjusted, audited }
}
