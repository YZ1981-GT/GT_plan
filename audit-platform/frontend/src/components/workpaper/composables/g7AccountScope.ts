/**
 * G7 长期股权投资 —— 科目口径**单一真源**（零 Vue 依赖纯函数）。
 *
 * 改造前科目码散落在 5 处各写各的：宿主 `G7_ACCOUNT_CODE`/`G7_IMPAIRMENT_CODE`
 * （`writebackTB` + `substantive:adjudicated` 事件过滤）、`G7TabAdjudication` 的
 * `ACCOUNT_GROSS`/`ACCOUNT_IMPAIRMENT` + `account_prefix: '151'` 请求参数 +
 * `/^1511/`·`/^1512/` 正则、两个披露 Tab 各自的 `ACCOUNT_CODE`。
 * 换客户科目编码或改报表映射时，这 5 处必然漂移。
 *
 * `report_config` 只读实证（DB）::
 *
 *     BS-024  长期股权投资            = TB('1511','期末余额')   ← 四准则完全一致
 *     IMP-009 八、长期股权投资减值准备 = TB('1512','期末余额')   ← 仅 soe_standalone 有公式
 *                                                              soe_consolidated NULL / listed 无该行
 *
 * **运行态一律取 render 下发的 `tb_source_codes`**（报表映射解析 + `account_mapping`
 * 反解的结果），本文件常量只作**兜底与展示**。禁止在组件里再写字面量科目码。
 *
 * spec: .kiro/specs/g7-four-table-extraction-and-disclosure-alignment/ R11.1，Property 15
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** 原值报表行次：长期股权投资 */
export const G7_REPORT_ROW_CODE = 'BS-024'

/**
 * 备抵**独立报表行**行次：八、长期股权投资减值准备。
 * `BS-024` 的公式不引用备抵，故备抵自成一行（后端 `G7_ACCOUNT_SPEC.provision_row_code`）。
 */
export const G7_PROVISION_REPORT_ROW_CODE = 'IMP-009'

/** 原值兜底标准码（仅 fail-open 与展示用；运行态取 `tb_source_codes.gross_standard`） */
export const G7_GROSS_FALLBACK_STANDARD = '1511'

/** 备抵兜底标准码（同上） */
export const G7_PROVISION_FALLBACK_STANDARD = '1512'

/** 科目中文名（UI 文案 / AI 上下文统一取此常量） */
export const G7_ACCOUNT_NAME = '长期股权投资'
export const G7_PROVISION_ACCOUNT_NAME = '长期股权投资减值准备'

/**
 * 试算平衡表按前缀批量拉取时的**共同前缀**（原值与备抵的最长公共前缀）。
 *
 * `G7TabAdjudication.fetchTrialBalance` 用它一次拉回两组再在前端分流；
 * 由解析结果派生而非写死 `'151'` —— 客户改编码时自动跟着变。
 */
export function g7TrialBalancePrefix(src?: TbSourceCodes | null): string {
  const codes = [...g7GrossQueryCodes(src), ...g7ProvisionQueryCodes(src)]
  return commonPrefix(codes)
}

/** 原值查询口径（标准码集）；溯源缺失时回退兜底码 */
export function g7GrossQueryCodes(src?: TbSourceCodes | null): string[] {
  return tbQueryCodes(src?.gross_standard, G7_GROSS_FALLBACK_STANDARD)
}

/** 备抵查询口径（标准码集）；溯源缺失时回退兜底码 */
export function g7ProvisionQueryCodes(src?: TbSourceCodes | null): string[] {
  return tbQueryCodes(src?.provision_standard, G7_PROVISION_FALLBACK_STANDARD)
}

/** 单一原值科目码（回写 TB / EventBus 载荷 / 事件过滤用） */
export function g7AccountCode(src?: TbSourceCodes | null): string {
  return g7GrossQueryCodes(src)[0]
}

/** 单一备抵科目码 */
export function g7ImpairmentAccountCode(src?: TbSourceCodes | null): string {
  return g7ProvisionQueryCodes(src)[0]
}

/**
 * 某科目码是否属原值侧（点号边界，`1511` 不命中 `15110`）。
 *
 * 平台标准码用 `-` 分级、客户原始码用 `.` 分级 → 两种分隔符都认。
 */
export function isG7GrossCode(code: unknown, src?: TbSourceCodes | null): boolean {
  return matchesAny(code, g7GrossQueryCodes(src))
}

/** 某科目码是否属备抵侧（点号边界） */
export function isG7ProvisionCode(code: unknown, src?: TbSourceCodes | null): boolean {
  return matchesAny(code, g7ProvisionQueryCodes(src))
}

/**
 * 调整分录可选科目 —— `G7TabAdjustment.vue` 与 `g7AdjustmentModel.ts` 共用一份。
 *
 * ⚠️ 这里是**会计科目选项**（用户在分录里挑哪个科目），不是取数口径：
 * `6111 投资收益` / `6701 资产减值损失` 是分录对方科目，不由报表映射决定。
 * 原值与备抵两项的 code 由本文件兜底常量派生，保持与取数口径同源。
 */
export interface G7AccountOption {
  code: string
  name: string
}

export const G7_ADJUSTMENT_ACCOUNT_OPTIONS: readonly G7AccountOption[] = [
  { code: G7_GROSS_FALLBACK_STANDARD, name: G7_ACCOUNT_NAME },
  { code: G7_PROVISION_FALLBACK_STANDARD, name: G7_PROVISION_ACCOUNT_NAME },
  { code: '6111', name: '投资收益' },
  { code: '6701', name: '资产减值损失' },
]

/**
 * 单个科目码是否落在给定前缀下（点号/横杠边界）。
 *
 * 用于按科目分流调整分录 —— 裸 `String.startsWith(prefix)` 会让 `1511` 命中 `15110`。
 */
export function g7CodeMatchesPrefix(code: unknown, prefix: string): boolean {
  return matchesAny(code, [prefix])
}

// ─── 内部纯函数 ─────────────────────────────────────────────────────────────

/** 科目码分级分隔符（标准码 `-` / 客户原始码 `.`） */
const CODE_SEPARATORS = ['.', '-'] as const

function matchesAny(code: unknown, prefixes: readonly string[]): boolean {
  const c = String(code ?? '').trim()
  if (!c) return false
  return prefixes.some(
    (p) => c === p || CODE_SEPARATORS.some((sep) => c.startsWith(p + sep)),
  )
}

/** 字符串集的最长公共前缀（空集返空串） */
function commonPrefix(list: readonly string[]): string {
  const items = list.filter(Boolean)
  if (!items.length) return ''
  let prefix = items[0]
  for (const item of items.slice(1)) {
    let i = 0
    while (i < prefix.length && i < item.length && prefix[i] === item[i]) i += 1
    prefix = prefix.slice(0, i)
    if (!prefix) break
  }
  return prefix
}
