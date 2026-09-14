/**
 * K2 其他流动资产 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * 🔴 全循环原本硬编码 `1231`（12 处），但 `1231` 是**应收款项的坏账准备**（贷方备抵）。
 * `report_config` 只读实证（四个准则一致）::
 *
 *     BS-014 其他流动资产
 *       soe_standalone / soe_consolidated / listed_consolidated : TB('1901','期末余额')
 *       listed_standalone : TB('1901','期末余额') + TB('1131','期末余额')
 *
 * 错误科目造成的后果不止「数字不对」——「从序时账导入」会把坏账准备子科目导进
 * K2-2 明细、抽凭引擎会抽坏账准备的凭证、`writebackTB` 会往 `1231` 写审定数
 * （覆盖 D1/D2/K1 的坏账口径），且与那三个循环**重复计入资产**。
 *
 * 运行态口径以 render 下发的 `tb_source_codes.gross_standard` 为准（报表映射解析结果），
 * 本文件的常量只作**兜底 + 展示**。禁止在组件里再写字面量科目码。
 *
 * spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/ Requirements 1.1~1.3
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行次（`BS-017` 是同名但 formula 为 NULL 的行 → 必须按 row_code 精确匹配 `BS-014`） */
export const K2_REPORT_ROW_CODE = 'BS-014'

/** 原值兜底标准码：1901 待处理财产损溢（报表公式实际引用的科目） */
export const K2_GROSS_FALLBACK_STANDARD = '1901'

/**
 * 报表公式引用但**不并入**其他流动资产的科目：1131 应收股利已属
 * `BS-009 其他应收款`（K1 循环），并入会重复计入资产。
 */
export const K2_EXCLUDED_STANDARD_CODES: readonly string[] = ['1131']

/** 科目中文名（AI 上下文 / UI 文案统一取此常量） */
export const K2_ACCOUNT_NAME = '其他流动资产'

/**
 * 🔴 曾被误当作其他流动资产的科目族 —— 守卫用（源码不得再出现该字面量作科目码）。
 * `1231` = 坏账准备；其细分 `1231-01/-02/-03/-05` 分属应收票据/应收账款/其他应收款/长期应收款。
 */
export const K2_WRONG_LEGACY_ACCOUNT = '1231'

/** 试算平衡表 / 余额表查询口径（标准码集）；溯源缺失时回退 `1901` */
export function k2GrossQueryCodes(src: TbSourceCodes | null | undefined): string[] {
  return tbQueryCodes(src?.gross_standard, K2_GROSS_FALLBACK_STANDARD)
}

/** 单一科目码（回写 TB / EventBus / 抽凭引擎用）；溯源缺失时回退 `1901` */
export function k2AccountCode(src?: TbSourceCodes | null): string {
  return k2GrossQueryCodes(src)[0]
}
