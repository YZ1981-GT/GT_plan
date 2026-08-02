/**
 * 四表库取数溯源 —— 跨循环共享视图模型（零 Vue 依赖纯函数）。
 *
 * 后端真源 = `app/services/four_table/report_line_accounts.ReportLineAccounts.as_dict()`
 * （各循环 render 策略透出 `html_data.tb_source_codes`）。字段名逐字对齐，改一侧必改另一侧。
 *
 * 链路：报表行（`BS-xxx`）→ `report_config.formula`（按项目适用准则）→ 标准码
 * → `account_mapping` 反解 → 客户原始码 → `tb_balance` 叶子聚合。
 *
 * 循环差异（报表行、原值/备抵中文名、附加科目名、提示文案）一律由**调用方**声明，
 * 本模块不含任何循环专属常量 —— 这样第 N 个循环接入时只写声明、不复制逻辑。
 *
 * 消费方：`shared/WpFourTableSourcePanel.vue`（K1 / K2 …）、`k1TbSourceCodes.ts`（re-export）。
 *
 * spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/ R1.7
 */

/**
 * 解析来源。
 *
 * 前两个来自 `report_line_accounts`（报表映射规则驱动）；
 * 后三个来自 `semantic_account_resolver`（**语义驱动、逐项目**，2026-08-01 新增）——
 * 因为标准码在项目间并不一致（`account_mapping` 同一原始码在不同项目映射到不同标准码；
 * 平台标准科目表本身各项目也不同），科目须按**科目名**在该项目自己的科目表里定位。
 */
export type TbResolvedFrom =
  | 'report_config'
  | 'fallback'
  /** 客户科目表按名称命中（最权威 —— 客户真实在用的科目） */
  | 'account_chart_client'
  /** 平台标准科目表按名称命中 */
  | 'account_chart_standard'
  /** 本项目确实没有该科目（**不是**取数失败，界面须显式区分） */
  | 'none'

/** 语义解析的单个槽（`semantic_account_resolver.ResolvedSlot`） */
export interface TbSemanticSlot {
  key: string
  label: string
  is_provision?: boolean
  codes?: string[]
  standard_codes?: string[]
  /** `[[科目码, 科目名], ...]` 命中明细 */
  matched?: Array<[string, string]>
  resolved_from?: TbResolvedFrom
  /** 名称是否**精确**命中（false = 走了包含匹配，展示时应提示复核） */
  exact?: boolean
  found?: boolean
}

export interface TbSourceCodes {
  /** 报表行次（如其他应收款 `BS-009`、其他流动资产 `BS-014`） */
  row_code?: string
  /** 原值科目 —— 客户原始码前缀集（tb_balance 用） */
  gross?: string[]
  /** 备抵科目 —— 客户原始码前缀集 */
  provision?: string[]
  /** 原值科目 —— 标准码集（trial_balance 用） */
  gross_standard?: string[]
  /** 备抵科目 —— 标准码集 */
  provision_standard?: string[]
  /** 附加科目 `{标准码: [原始码, ...]}`（报表公式引用但不并入原值的科目） */
  extra?: Record<string, string[]>
  /** 报表公式里各 TB() 的符号 `[[标准码, +1|-1], ...]` */
  signed_codes?: Array<[string, number]>
  /** 命中的报表公式原文 */
  formula?: string | null
  resolved_from?: TbResolvedFrom
  provision_resolved_from?: TbResolvedFrom
  /** 备抵标准码是否精确反解出原始码（false = 退化为宽前缀） */
  provision_exact?: boolean
  /** 是否叠加了备抵名称过滤（保守口径） */
  use_provision_name_filter?: boolean
  /**
   * 备抵**独立报表行**行次（如长期股权投资减值准备 `IMP-009`）。
   * 仅「原值行公式不引用备抵、备抵自成一行」的循环才有值（G7 / H·I 类的 `IMP-xxx`）；
   * 为空串表示该侧走了兜底码。
   */
  provision_row_code?: string
  /** 备抵报表行的公式原文 */
  provision_formula?: string | null
  /**
   * 叶子和 vs 父科目行金额的两口径自检。不相等时两个数都暴露（不静默取其一），
   * 供审计追溯 —— 差异通常意味着客户科目树被改动或数据集不一致。
   */
  parent_check?: { leaf_sum: number; parent: number; diff: number }

  // ── 语义解析专属（`semantic_account_resolver.SemanticAccountResult.as_dict()`）──
  /** 各语义槽（原值 / 备抵 / 累计折旧 …）。扁平字段是本对象主槽的投影 */
  slots?: Record<string, TbSemanticSlot>
  /** 报表公式解析出的标准码（**仅提示**，不是定位依据） */
  report_config_codes?: string[]
  /**
   * `report_config` 给的码与按科目名定位的结果不一致：`[[槽键, 报表码, 实际码], ...]`。
   * 实证 `report_config` 有 4 行错码（BS-022/025/026 连续偏移、IS-016↔IS-017 互换）
   * → 以名称结果为准，这里暴露差异供溯源面板橙色告警。
   */
  conflicts?: Array<[string, string, string]>
  /**
   * 本项目存在的**旧准则**同族科目 `[[码, 科目名], ...]`，需人工按 SPPI 拆分。
   * 代码不做跨准则推断（那是会计判断，见 G4-5/G4-6、G6-7/G6-8 底稿）。
   */
  unmapped_candidates?: Array<[string, string]>
  /** 本项目科目表是否可用。false = 未导入 / 查询失败（须与「无此科目」区分） */
  chart_available?: boolean
}

/** 中文化解析来源（UI 全中文化铁律） */
export function tbResolvedFromLabel(v: string | undefined | null): string {
  switch (v) {
    case 'report_config':
      return '报表规则映射'
    case 'account_chart_client':
      return '客户科目表'
    case 'account_chart_standard':
      return '标准科目表'
    case 'none':
      return '本项目无此科目'
    default:
      return '兜底科目'
  }
}

/**
 * 解析来源 → el-tag type。
 *
 * 🔴 `none`（本项目无此科目）用 `info` 而非 `danger` —— 它是**正确行为**
 * （宁缺勿造，不取错），不是错误；真正需要告警的是 `conflicts`。
 */
export function tbResolvedFromTagType(
  v: string | undefined | null,
): 'success' | 'warning' | 'info' {
  switch (v) {
    case 'report_config':
    case 'account_chart_client':
    case 'account_chart_standard':
      return 'success'
    case 'none':
      return 'info'
    default:
      return 'warning'
  }
}

/** 是否存在 `report_config` 与实际科目的冲突（溯源面板据此渲染告警条） */
export function hasTbConflicts(src: TbSourceCodes | null | undefined): boolean {
  return !!(src?.conflicts && src.conflicts.length)
}

/** 冲突的中文说明（逐条） */
export function tbConflictTexts(src: TbSourceCodes | null | undefined): string[] {
  return (src?.conflicts || []).map(
    ([slot, reportCode, actualCode]) =>
      `${slot}：报表公式引用 ${reportCode}，但本项目该科目实为 ${actualCode}（已按科目表取数）`,
  )
}

/** 需人工映射的旧准则科目说明（逐条） */
export function tbUnmappedTexts(src: TbSourceCodes | null | undefined): string[] {
  return (src?.unmapped_candidates || []).map(
    ([code, name]) => `${code} ${name}`,
  )
}

/** 语义槽列表（按声明顺序；`found=false` 的槽也返回，供界面显示「无此科目」） */
export function tbSemanticSlots(
  src: TbSourceCodes | null | undefined,
): TbSemanticSlot[] {
  const slots = src?.slots
  if (!slots) return []
  return Object.keys(slots).map((k) => slots[k])
}

/** 科目码集 → 展示串（空集显示占位符） */
export function tbCodeListText(codes: readonly string[] | undefined | null): string {
  const list = (codes || []).filter(Boolean)
  return list.length ? list.join('、') : '—'
}

/** 是否有可展示的溯源内容（全空时面板不渲染，避免空洞卡片） */
export function hasTbSourceCodes(src: TbSourceCodes | null | undefined): boolean {
  if (!src) return false
  return !!(
    (src.gross && src.gross.length)
    || (src.provision && src.provision.length)
    || (src.gross_standard && src.gross_standard.length)
  )
}

/** 附加科目条目（供 v-for） */
export interface TbExtraCodeEntry {
  standard: string
  originals: string[]
  label: string
}

/**
 * 附加科目条目（按标准码排序）。
 *
 * @param labels 标准码 → 中文名（调用方声明；未登记时回退标准码本身）
 */
export function tbExtraEntries(
  src: TbSourceCodes | null | undefined,
  labels: Readonly<Record<string, string>> = {},
): TbExtraCodeEntry[] {
  const extra = src?.extra || {}
  return Object.keys(extra)
    .sort()
    .map((standard) => ({
      standard,
      originals: extra[standard] || [],
      label: labels[standard] || standard,
    }))
}

/** 公式符号 → 可读串：`+ 1221　− 1231-03　+ 1131` */
export function tbSignedFormulaText(src: TbSourceCodes | null | undefined): string {
  const list = src?.signed_codes || []
  if (!list.length) return ''
  return list.map(([code, sign]) => `${sign < 0 ? '−' : '+'} ${code}`).join('　')
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
 * 会把父科目与子科目算两遍。本函数先按「是否被更长的同前缀码覆盖」剔除父级，再求和。
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

/**
 * 取查询口径（标准码集）；溯源缺失时回退调用方给的兜底码。
 *
 * @param codes 溯源里的标准码集（`gross_standard` / `provision_standard`）
 * @param fallback 兜底标准码（**必须是细分码**，如 `1231-03`，不是宽口径 `1231`）
 */
export function tbQueryCodes(
  codes: readonly string[] | undefined | null,
  fallback: string,
): string[] {
  const list = (codes || []).filter(Boolean)
  return list.length ? [...list] : [fallback]
}
