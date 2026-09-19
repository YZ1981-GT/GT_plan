/**
 * K5 预计负债 — 科目码单一真源。
 *
 * 🔴 **历史缺陷（DB 只读实证）**：K5 全循环写死 `'2701'`，但 `account_chart` 实证
 * `2701` 在**全部项目**中一律是**长期应付款**（L5 循环科目，带
 * `2701.01 应付融资租赁款` / `.02 应付长期保证金` / `.03 应付长期借款` /
 * `.99 一年内到期` 四个子科目）。`2801` 才是预计负债
 * （`account_chart` 5 条 / `tb_balance` 39 行 / `trial_balance` 4 条均存在），
 * `report_config` 的 `BS-068`（上市）/ `BS-094`（国企）公式也是 `TB('2801','期末余额')`。
 *
 * 破坏面不止「数字不对」：
 * - `writebackTB` 把**预计负债审定数写进长期应付款**的 `trial_balance` → 污染 L5 口径
 * - `loadTbData` 回退请求 `account_prefix: '2701'` → 取到长期应付款余额当预计负债显示
 * - EventBus `substantive:adjudicated` 载荷带错科目码 → 下游附注刷新定位到错科目
 *
 * 🔴 **2026-08-09 报表行改正**（与上面的科目码缺陷是**两件不同的事**）：
 * 后端 `k_cycle_specs.py` 已按 `report_config` 连库对账把两侧改为 **`BS-065`**，
 * 本文件同步跟进（判据在 `kCycleAccountScopeCrossLock.spec.ts`）::
 *
 *     原值 listed=BS-068  实为**其他非流动负债**（L7 的行，`TB('2911')` 且 2911 全库零命中）
 *     原值 soe=BS-094     row_name 是「预计负债」名对，但 **formula 为 NULL**
 *                         ⇒ 后果 TRACE_ONLY（退兜底 2801，金额对、溯源失真）
 *
 * `BS-065` 四变体一致 `TB('2801','期末余额')`；两准则**同号**（K 循环没有一个科目
 * 在 listed / soe 下用不同 row_code，此前「两侧必须不同」的假设本身就是错的）。
 *
 * **使用铁律**：运行态一律取 render 下发的 `tb_source_codes.gross`（报表映射解析结果），
 * 本文件的常量只作**兜底 + 展示**。范式同 `k2AccountScope.ts`。
 *
 * spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/ (Task 7)
 *       Requirements 1.4, 3.5 / Property 2, 10
 */

/** 报表行编码 —— 上市准则（两准则同号，保留两个常量以兼容既有 import） */
export const K5_REPORT_ROW_CODE_LISTED = 'BS-065'

/** 报表行编码 —— 国企准则（实测与 listed 同号） */
export const K5_REPORT_ROW_CODE_SOE = 'BS-065'

/**
 * 兜底标准码：`2801` 预计负债。
 *
 * 🔴 **不是** `2701`（长期应付款）。改动本常量前先查 `account_chart`。
 */
export const K5_FALLBACK_STANDARD = '2801'

/** 科目中文名（展示用，与 `account_chart.account_name` 一致） */
export const K5_ACCOUNT_NAME = '预计负债'

/** render 下发的取数溯源结构（只取本文件需要的字段） */
export interface K5TbSourceCodes {
  /** 原值科目原始码前缀集（用于 `tb_balance` / `tb_aux_balance` 前缀匹配） */
  gross?: string[] | null
  /** 原值科目标准码集（用于 `trial_balance` / writeback） */
  gross_standard?: string[] | null
  /** `report_config` | `fallback` */
  resolved_from?: string | null
}

function normalize(codes: unknown): string[] {
  if (!Array.isArray(codes)) return []
  const out: string[] = []
  for (const c of codes) {
    const s = String(c ?? '').trim()
    if (s && !out.includes(s)) out.push(s)
  }
  return out
}

/**
 * `tb_balance` / 明细查询用的**原始码**前缀集。
 *
 * 运行态优先用 render 解析结果；缺失时退到 `2801`。
 */
export function k5QueryCodes(src?: K5TbSourceCodes | null): string[] {
  const resolved = normalize(src?.gross)
  return resolved.length ? resolved : [K5_FALLBACK_STANDARD]
}

/**
 * 单一科目码 —— 供 `writebackTB` / EventBus 载荷 / AI 上下文使用。
 *
 * 取**标准码**（`trial_balance.standard_account_code` 口径），因为回写端点写的是
 * `trial_balance`；解析不出时退到 `2801`。
 */
export function k5AccountCode(src?: K5TbSourceCodes | null): string {
  const resolved = normalize(src?.gross_standard)
  return resolved[0] || K5_FALLBACK_STANDARD
}

/** 溯源展示文案：`2801（报表行 BS-094）` / 解析失败时标注「兜底」 */
export function k5SourceLabel(src?: K5TbSourceCodes | null, isListed = false): string {
  const code = k5AccountCode(src)
  const row = isListed ? K5_REPORT_ROW_CODE_LISTED : K5_REPORT_ROW_CODE_SOE
  const suffix = src?.resolved_from === 'report_config' ? '' : '，兜底'
  return `${code}（报表行 ${row}${suffix}）`
}
