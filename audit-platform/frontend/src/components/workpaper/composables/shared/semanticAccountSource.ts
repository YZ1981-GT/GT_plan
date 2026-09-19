/**
 * 语义科目定位溯源 —— 跨循环共享视图模型（零 Vue 依赖纯函数）。
 *
 * 后端真源 = `app/services/four_table/semantic_account_resolver.SemanticAccountResult.as_dict()`
 * （E 循环 / G 循环 render 策略透出 `html_data.tb_source_codes`）。字段名逐字对齐，
 * 改一侧必改另一侧。
 *
 * **与 `tbSourceCodes.ts` 的分工**：那一份对应 `report_line_accounts.ReportLineAccounts`
 * （原值 / 备抵二分口径，K1/K2/D1/F1/G7 在用）；本文件对应**语义槽**口径
 * （按科目名逐项目定位，多槽并列、无备抵二分），两者结构不同不能混用。
 *
 * 定位链：报表行（`BS-xxx`，**仅提示 + 冲突检测**）→ 语义槽名称 → 本项目
 * `account_chart`（client 优先、standard 兜底）→ `account_mapping` → `tb_balance` 叶子。
 *
 * 循环差异（槽顺序、提示文案、面板标题）由调用方声明，本模块无任何循环专属常量。
 *
 * spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/ Requirements 2.7, 9.3
 */

/** 槽命中来源（与后端 `RESOLVED_FROM_*` 常量逐字一致） */
export type SemanticResolvedFrom =
  | 'account_chart_client'
  | 'account_chart_standard'
  | 'report_config'
  | 'fallback'
  | 'none'

export interface SemanticSlotSource {
  key: string
  label: string
  is_provision?: boolean
  /** 原始码前缀集（`tb_balance` 用） */
  codes?: string[]
  /** 标准码集（`trial_balance` 用） */
  standard_codes?: string[]
  /** `[[码, 科目名], ...]` 命中明细 */
  matched?: Array<[string, string]> | string[][]
  resolved_from?: SemanticResolvedFrom | string
  /** 名称是否精确命中（false = 走了包含匹配，需审计师复核） */
  exact?: boolean
  found?: boolean
}

export interface SemanticParentCheckEntry {
  slot?: string
  parent_closing?: number
  leaf_closing?: number
  diff?: number
}

export interface SemanticAccountSource {
  row_code?: string
  formula?: string | null
  /** 报表公式解析出的标准码（**仅提示**，不是定位依据） */
  report_config_codes?: string[]
  /** `[[slot_key, 报表码, 实际码], ...]` —— 报表公式与按名定位结果不一致 */
  conflicts?: Array<[string, string, string]> | string[][]
  /** `[[码, 科目名], ...]` —— 本项目存在的同族旧准则科目，需人工映射 */
  unmapped_candidates?: Array<[string, string]> | string[][]
  /** 本项目科目表是否可用（false → 提示「科目表未导入」而非「无该科目」） */
  chart_available?: boolean
  slots?: Record<string, SemanticSlotSource>
  /** 叶子和 vs 父科目额自检 `{原始码: {...}}` */
  parent_check?: Record<string, SemanticParentCheckEntry>
}

/** 归一化（后端可能整体缺失 / 字段缺省） */
export function normalizeSemanticAccountSource(raw: unknown): SemanticAccountSource {
  const s = (raw ?? {}) as Record<string, any>
  return {
    row_code: typeof s.row_code === 'string' ? s.row_code : '',
    formula: typeof s.formula === 'string' ? s.formula : null,
    report_config_codes: Array.isArray(s.report_config_codes) ? s.report_config_codes.map(String) : [],
    conflicts: Array.isArray(s.conflicts) ? s.conflicts : [],
    unmapped_candidates: Array.isArray(s.unmapped_candidates) ? s.unmapped_candidates : [],
    chart_available: !!s.chart_available,
    slots: (s.slots && typeof s.slots === 'object' ? s.slots : {}) as Record<string, SemanticSlotSource>,
    parent_check: (s.parent_check && typeof s.parent_check === 'object' ? s.parent_check : {}) as Record<
      string,
      SemanticParentCheckEntry
    >,
  }
}

/** 中文化命中来源（UI 全中文化铁律） */
export function semanticResolvedFromLabel(v: string | undefined | null): string {
  switch (v) {
    case 'account_chart_client':
      return '客户科目表'
    case 'account_chart_standard':
      return '标准科目表'
    case 'report_config':
      return '报表规则映射'
    case 'fallback':
      return '兜底科目'
    default:
      return '未命中'
  }
}

/** 命中来源 → el-tag type（客户科目表最可信，兜底/未命中需提示） */
export function semanticResolvedFromTagType(
  v: string | undefined | null,
): 'success' | 'primary' | 'warning' | 'info' {
  switch (v) {
    case 'account_chart_client':
      return 'success'
    case 'account_chart_standard':
      return 'primary'
    case 'report_config':
      return 'primary'
    case 'fallback':
      return 'warning'
    default:
      return 'info'
  }
}

/** 科目码集 → 展示串（空集显示占位符） */
export function semanticCodeListText(codes: readonly string[] | undefined | null): string {
  const list = (codes || []).filter(Boolean)
  return list.length ? list.join('、') : '—'
}

/** 面板展示行（按调用方给的槽顺序，缺失的槽也列出以显式暴露「本项目无此科目」） */
export interface SemanticSlotRow {
  key: string
  label: string
  found: boolean
  exact: boolean
  resolvedFrom: string
  resolvedFromLabel: string
  resolvedFromTag: 'success' | 'primary' | 'warning' | 'info'
  codesText: string
  standardCodesText: string
  /** 命中科目名（去重后 join） */
  matchedNames: string
  /** 该槽下各原始码的父子自检（有差异才非空） */
  parentDiffs: Array<{ code: string; leaf: number; parent: number; diff: number }>
}

/**
 * 槽展示行。
 *
 * @param src 归一后的溯源对象
 * @param order 槽 key 顺序（调用方声明，如 `['cash','bank','other','finance_co','digital']`）
 * @param labels 槽 key → 中文名兜底（后端已给 label 时优先用后端的）
 */
export function semanticSlotRows(
  src: SemanticAccountSource | null | undefined,
  order: readonly string[],
  labels: Readonly<Record<string, string>> = {},
): SemanticSlotRow[] {
  const slots = src?.slots || {}
  const parentCheck = src?.parent_check || {}
  const keys = order.length ? order : Object.keys(slots)
  return keys.map((key) => {
    const slot = slots[key] || ({} as SemanticSlotSource)
    const codes = (slot.codes || []).filter(Boolean)
    const matched = (slot.matched || []) as Array<string[] | [string, string]>
    const names = [...new Set(matched.map((m) => String(m?.[1] ?? '')).filter(Boolean))]
    const parentDiffs: SemanticSlotRow['parentDiffs'] = []
    for (const code of codes) {
      const pc = parentCheck[code]
      if (!pc) continue
      const diff = Number(pc.diff) || 0
      if (Math.abs(diff) <= 0.01) continue
      parentDiffs.push({
        code,
        leaf: Number(pc.leaf_closing) || 0,
        parent: Number(pc.parent_closing) || 0,
        diff,
      })
    }
    return {
      key,
      label: slot.label || labels[key] || key,
      found: !!slot.found,
      exact: !!slot.exact,
      resolvedFrom: String(slot.resolved_from || 'none'),
      resolvedFromLabel: semanticResolvedFromLabel(slot.resolved_from),
      resolvedFromTag: semanticResolvedFromTagType(slot.resolved_from),
      codesText: semanticCodeListText(codes),
      standardCodesText: semanticCodeListText(slot.standard_codes),
      matchedNames: names.length ? names.join('、') : '—',
      parentDiffs,
    }
  })
}

/** 是否有可展示内容（全空时面板不渲染，避免空洞卡片） */
export function hasSemanticAccountSource(src: SemanticAccountSource | null | undefined): boolean {
  if (!src) return false
  const slots = Object.values(src.slots || {})
  return slots.some((s) => !!s.found) || !!(src.row_code || '').length
}

export interface SemanticConflictRow {
  slotKey: string
  reportCode: string
  actualCode: string
}

/** 冲突条目：`report_config` 给的码与按名称定位结果不一致（面板橙色告警） */
export function semanticConflictRows(
  src: SemanticAccountSource | null | undefined,
): SemanticConflictRow[] {
  return ((src?.conflicts || []) as Array<string[]>).map((c) => ({
    slotKey: String(c?.[0] ?? ''),
    reportCode: String(c?.[1] ?? ''),
    actualCode: String(c?.[2] ?? ''),
  }))
}

export interface SemanticUnmappedRow {
  code: string
  name: string
}

/** 旧准则同族科目（需人工映射；平台不猜跨准则拆分） */
export function semanticUnmappedRows(
  src: SemanticAccountSource | null | undefined,
): SemanticUnmappedRow[] {
  return ((src?.unmapped_candidates || []) as Array<string[]>).map((c) => ({
    code: String(c?.[0] ?? ''),
    name: String(c?.[1] ?? ''),
  }))
}

/** 全部父子自检差异（跨槽汇总，供面板顶部一行提示） */
export function semanticParentDiffCount(src: SemanticAccountSource | null | undefined): number {
  return Object.values(src?.parent_check || {}).filter(
    (v) => Math.abs(Number(v?.diff) || 0) > 0.01,
  ).length
}
