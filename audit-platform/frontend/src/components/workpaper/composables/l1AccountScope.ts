/**
 * L1 短期借款 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * report_config 实证（四准则一致）::
 *
 *     BS-044 / BS-055 短期借款 = TB('2001','期末余额')
 *
 * 运行态口径以 render 下发的 `tb_source_codes.gross_standard` 为准（报表映射解析结果），
 * 本文件的常量只作**兜底 + 展示**。禁止在组件里再写字面量科目码。
 *
 * spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R1, R4
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行次（上市 BS-044 / 国企 BS-055） */
export const L1_REPORT_ROW_CODE = 'BS-044'

/** 原值兜底标准码 */
export const L1_GROSS_FALLBACK_STANDARD = '2001'

/** 科目中文名 */
export const L1_ACCOUNT_NAME = '短期借款'

/** 试算平衡表 / 余额表查询口径；溯源缺失时回退兜底码 */
export function l1GrossQueryCodes(src: TbSourceCodes | null | undefined): string[] {
  return tbQueryCodes(src?.gross_standard, L1_GROSS_FALLBACK_STANDARD)
}

/** 单一科目码（回写 TB / EventBus 用） */
export function l1AccountCode(src?: TbSourceCodes | null): string {
  return l1GrossQueryCodes(src)[0]
}
