/**
 * E1 货币资金 — 科目码单一真源。
 *
 * spec: voucher-sampling-account-scope-and-attach-closure（任务 2.3）
 *
 * ## 为什么需要这个模块
 *
 * E1 的科目码此前散落在各宿主里硬编码：
 * - `E1TabLargeCheck.MF_ACCOUNT_PREFIXES = ['1001','1002','1012']`（路径 B 的科目前缀）
 * - `E1TabLargeCheck` / `E1TabBankFlowReconcile` 的 `account-code="1002"`（路径 A 的抽凭科目）
 *
 * 两条路径各写一份，且一处只写 `1002`、另一处写三码 —— 对「E1 是什么科目」给出了
 * **不同答案**。本模块把两条路径收敛到同一真源（spec R4.1：路径 A 与路径 B 必须同源）。
 *
 * ## 取值实证（DB 只读，2026-09-28）
 *
 * | 码 | `tb_balance` 科目名 | 覆盖项目数 |
 * |---|---|---|
 * | `1001` | 库存现金 | 8 |
 * | `1002` | 银行存款 | 10（另有 `1002.001`~ 等大量账户级子科目） |
 * | `1012` | 其他货币资金 | 6 |
 *
 * `wp_account_mapping.json` 的 `E1` / `E1-1` / `E1-23` 三条目一致为
 * `['1001','1002','1012']`，报表行 `BS-002`（货币资金）。
 * 🔴 本模块与该 json **恰好一致**（不同于 K10/K12/H5 三处 json 有错的情形），
 * 但仍以本模块为真源 —— json 的消费面是附注绑定/地址库，不是底稿运行态。
 *
 * ## 两种口径不可混用
 *
 * - `e1QueryCodes()` → **原始码前缀集**，供 `tb_ledger` / `tb_balance` 前缀匹配
 *   （抽凭查的是 `tb_ledger` ⇒ 用这个；账户级子科目 `1002.001` 会被前缀命中）
 * - `e1AccountCode()` → **标准码单值**，供 `trial_balance` 回写口径
 */

/** 报表行（资产负债表「货币资金」） */
export const E1_REPORT_ROW_CODE = 'BS-002'

/**
 * 兜底标准码：`1002` 银行存款。
 *
 * 🔴 单值兜底取 `1002` 而非 `1001`，因为银行存款在真实库覆盖 10/10 个项目（最广），
 * 且大额收支检查的主体是银行流水。需要全部三码时用 `e1QueryCodes()`，不要用本常量。
 */
export const E1_FALLBACK_STANDARD = '1002'

/**
 * 货币资金三科目族（库存现金 / 银行存款 / 其他货币资金）。
 *
 * 🔴 顺序固定为 1001 → 1002 → 1012（与 `wp_account_mapping.json` 一致），
 * 便于与既有断言逐项对齐。
 */
export const E1_ACCOUNT_FAMILY = ['1001', '1002', '1012'] as const

/** 科目中文名（展示用） */
export const E1_ACCOUNT_NAME = '货币资金'

/** 各码的中文名（用于回填时标注「这条分录是哪个科目」） */
export const E1_ACCOUNT_NAMES: Readonly<Record<string, string>> = {
  '1001': '库存现金',
  '1002': '银行存款',
  '1012': '其他货币资金',
}

/** render 解析结果（与其他循环的 `*TbSourceCodes` 同构） */
export interface E1TbSourceCodes {
  /** 原始码（客户科目表口径） */
  gross_raw?: string[] | null
  /** 标准码（`trial_balance.standard_account_code` 口径） */
  gross_standard?: string[] | null
  /** 解析来源，`report_config` 表示运行态解析成功 */
  resolved_from?: string | null
}

function normalize(list?: string[] | null): string[] {
  return (list ?? []).map((c) => String(c ?? '').trim()).filter(Boolean)
}

/**
 * `tb_ledger` / `tb_balance` 查询用的**原始码前缀集**。
 *
 * 运行态优先用 render 解析结果；缺失时退到三科目族全集
 * （🔴 退到**全集**而非 `E1_FALLBACK_STANDARD` 单值 —— 货币资金检查覆盖现金与
 * 其他货币资金，只查银行存款会漏掉库存现金盘点与保证金）。
 */
export function e1QueryCodes(src?: E1TbSourceCodes | null): string[] {
  const raw = normalize(src?.gross_raw)
  if (raw.length) return raw
  const std = normalize(src?.gross_standard)
  if (std.length) return std
  return [...E1_ACCOUNT_FAMILY]
}

/**
 * 标准码单值（`trial_balance` 回写口径）。解析不出时退到 `E1_FALLBACK_STANDARD`。
 */
export function e1AccountCode(src?: E1TbSourceCodes | null): string {
  const resolved = normalize(src?.gross_standard)
  return resolved[0] || E1_FALLBACK_STANDARD
}

/**
 * 抽凭引擎 `account-code` 实参（逗号拼接）。
 *
 * 依据：`useVoucherSampling.buildDefaultConfig()` 对 `accountCode` 做 `split(',')`，
 * 故多码用逗号拼接是既有契约，无需改引擎。
 */
export function e1SamplingAccountCode(src?: E1TbSourceCodes | null): string {
  return e1QueryCodes(src).join(',')
}

/** 溯源展示文案：`1001,1002,1012（报表行 BS-002）` / 解析失败时标注「兜底」 */
export function e1SourceLabel(src?: E1TbSourceCodes | null): string {
  const codes = e1QueryCodes(src).join(',')
  const suffix = src?.resolved_from === 'report_config' ? '' : '，兜底'
  return `${codes}（报表行 ${E1_REPORT_ROW_CODE}${suffix}）`
}
