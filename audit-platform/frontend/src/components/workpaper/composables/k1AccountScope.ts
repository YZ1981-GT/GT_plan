/**
 * K1 其他应收款 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * 后端真源 = `backend/app/services/four_table/k_cycle_specs.py` 的 `K_CYCLE_SPECS['K1']`：
 *
 *     row_code            BS-009 其他应收款
 *     fallback_standard   1221（原值）
 *     extra_standard      1131 应收股利 / 1132 应收利息（报表公式引用但不并入本表第一段）
 *     fallback_provision  1231-03（**其他应收款专属**坏账准备，不是宽口径 1231）
 *
 * 本文件与后端由 `__tests__/kCycleAccountScopeCrossLock.spec.ts` 交叉锁死
 * （守卫直读后端 py 源码，不使用冻结期望表）。
 *
 * 运行态口径以 render 下发的 `tb_source_codes` 为准，本文件常量只作**兜底 + 展示**。
 * 禁止在组件里再写字面量科目码。
 *
 * spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/ Requirement 3.5
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行次（必须按 row_code 精确匹配，同名行的 formula 可能为 NULL） */
export const K1_REPORT_ROW_CODE = 'BS-009'

/** 原值兜底标准码：1221 其他应收款 */
export const K1_GROSS_FALLBACK_STANDARD = '1221'

/**
 * 坏账准备兜底标准码 —— 其他应收款**专属**备抵。
 * 🔴 **不是** 宽口径 `1231`：`1231` 下 `-01/-02/-03/-05` 分属应收票据/应收账款/
 * 其他应收款/长期应收款，用宽口径会把 D1/D2 的坏账一起吃进来。
 */
export const K1_BAD_DEBT_FALLBACK_STANDARD = '1231-03'

/** 报表公式引用但**不并入**本表第一段的附加科目 */
export const K1_EXTRA_STANDARD_CODES: readonly string[] = ['1131', '1132']

/** 备抵科目名称过滤词（后端 `provision_name_filter`，用于从坏账明细里筛本循环口径） */
export const K1_PROVISION_NAME_FILTER = '其他应收款'

/** 科目中文名（AI 上下文 / UI 文案统一取此常量） */
export const K1_ACCOUNT_NAME = '其他应收款'

/** 原值查询口径（标准码集）；溯源缺失时回退 `1221` */
export function k1GrossQueryCodes(src?: TbSourceCodes | null): string[] {
  return tbQueryCodes(src?.gross_standard, K1_GROSS_FALLBACK_STANDARD)
}

/** 坏账查询口径（标准码集）；溯源缺失时回退 `1231-03` */
export function k1ProvisionQueryCodes(src?: TbSourceCodes | null): string[] {
  return tbQueryCodes(src?.provision_standard, K1_BAD_DEBT_FALLBACK_STANDARD)
}

/** 单一科目码（回写 TB / EventBus / 抽凭引擎用）；溯源缺失时回退 `1221` */
export function k1AccountCode(src?: TbSourceCodes | null): string {
  return k1GrossQueryCodes(src)[0]
}
