/**
 * K1 四表库取数溯源（render 下发 `html_data.tb_source_codes` 的前端视图）。
 *
 * 通用部分已提升为跨循环共享件 `composables/shared/tbSourceCodes.ts`（K2 起复用），
 * 本文件只保留 **K1 专属声明**（报表行 `BS-009` 的兜底标准码、附加科目中文名）
 * 并 re-export 共享件以保持既有 import 路径不变。
 *
 * 链路：报表行 `BS-009` → `report_config.formula`（按项目适用准则）→ 标准码
 * → `account_mapping` 反解 → 客户原始码 → `tb_balance` 叶子聚合。
 *
 * spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/ R1.7
 */
import {
  hasTbSourceCodes,
  tbCodeListText,
  tbExtraEntries,
  tbQueryCodes,
  tbResolvedFromLabel,
  tbResolvedFromTagType,
  tbSignedFormulaText,
  type TbExtraCodeEntry,
  type TbResolvedFrom,
  type TbSourceCodes,
} from './shared/tbSourceCodes'

export type { TbCodedAmountRow as TbCodedAmountRow } from './shared/tbSourceCodes'
export { sumLongestPrefixOnly } from './shared/tbSourceCodes'

/** 解析来源：报表规则映射 / 兜底 */
export type K1ResolvedFrom = TbResolvedFrom

/** K1 的溯源载荷形态与共享件一致（后端同一个 `as_dict()`） */
export type K1TbSourceCodes = TbSourceCodes

export type K1ExtraCodeEntry = TbExtraCodeEntry

/** 中文化解析来源（UI 全中文化铁律） */
export const k1ResolvedFromLabel = tbResolvedFromLabel

/** 解析来源 → el-tag type */
export const k1ResolvedFromTagType = tbResolvedFromTagType

/** 科目码集 → 展示串（空集显示占位符） */
export const k1CodeListText = tbCodeListText

/** 是否有可展示的溯源内容（全空时面板不渲染，避免空洞卡片） */
export const hasK1TbSourceCodes = hasTbSourceCodes

/** 公式符号 → 可读串：`+ 1221　− 1231-03　+ 1131` */
export const k1SignedFormulaText = tbSignedFormulaText

/** K1 附加科目中文名（报表公式引用但不并入本表第一段） */
export const K1_EXTRA_CODE_LABELS: Record<string, string> = {
  '1131': '应收股利',
  '1132': '应收利息',
}

export function k1ExtraEntries(src: K1TbSourceCodes | null | undefined): K1ExtraCodeEntry[] {
  return tbExtraEntries(src, K1_EXTRA_CODE_LABELS)
}

/**
 * 科目口径真源已收敛至 `k1AccountScope.ts`（与后端 `K_CYCLE_SPECS['K1']` 交叉锁死）。
 * 此处仅 re-export 以保持既有 import 路径不变，**不得**在本文件重复声明科目码。
 */
export {
  K1_ACCOUNT_NAME,
  K1_BAD_DEBT_FALLBACK_STANDARD,
  K1_EXTRA_STANDARD_CODES,
  K1_GROSS_FALLBACK_STANDARD,
  K1_PROVISION_NAME_FILTER,
  K1_REPORT_ROW_CODE,
  k1AccountCode,
  k1GrossQueryCodes,
  k1ProvisionQueryCodes,
} from './k1AccountScope'
