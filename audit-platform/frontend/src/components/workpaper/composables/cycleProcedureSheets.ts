/**
 * D 循环程序表（*A）→ render-config sheet_name 与 sheet_code 配置
 * 程序控制台统一走 GtAProgramConsole（force_component_type=a-program-console）
 */
import { D1_SHEET_LABEL_MAP } from './d1SheetLabels'
import { D3_SHEET_LABEL_MAP } from './d3SheetLabels'
import { D4_SHEET_LABEL_MAP } from './d4SheetLabels'
import { D5_SHEET_LABEL_MAP } from './d5SheetLabels'
import { D6_SHEET_LABEL_MAP } from './d6SheetLabels'
import { D7_SHEET_LABEL_MAP } from './d7SheetLabels'

export interface CycleProcedureSheetConfig {
  sheetCode: string
  sheetLabel: string
  reviewSectionId: string
}

export const D_CYCLE_PROCEDURE_SHEETS: Record<string, CycleProcedureSheetConfig> = {
  D1A: {
    sheetCode: 'D1A',
    sheetLabel: D1_SHEET_LABEL_MAP.D1A,
    reviewSectionId: 'D1A-procedure',
  },
  D2A: {
    sheetCode: 'D2A',
    sheetLabel: '应收账款实质性程序表D2A',
    reviewSectionId: 'D2A-procedure',
  },
  D3A: {
    sheetCode: 'D3A',
    sheetLabel: D3_SHEET_LABEL_MAP.D3A,
    reviewSectionId: 'D3A-procedure',
  },
  D4A: {
    sheetCode: 'D4A',
    sheetLabel: D4_SHEET_LABEL_MAP.D4A,
    reviewSectionId: 'D4A-procedure',
  },
  D5A: {
    sheetCode: 'D5A',
    sheetLabel: D5_SHEET_LABEL_MAP.D5A,
    reviewSectionId: 'D5A-procedure',
  },
  D6A: {
    sheetCode: 'D6A',
    sheetLabel: D6_SHEET_LABEL_MAP.D6A,
    reviewSectionId: 'D6A-procedure',
  },
  D7A: {
    sheetCode: 'D7A',
    sheetLabel: D7_SHEET_LABEL_MAP.D7A,
    reviewSectionId: 'D7A-procedure',
  },
}

/** G 循环程序表（*A）— 统一 CycleProgramConsoleTab，对齐 D4A */
export const G_CYCLE_PROCEDURE_SHEETS: Record<string, CycleProcedureSheetConfig> = {
  G1A: {
    sheetCode: 'G1A',
    sheetLabel: '交易性金融资产实质性程序表G1A',
    reviewSectionId: 'G1A-procedure',
  },
  G2A: {
    sheetCode: 'G2A',
    sheetLabel: '应收利息实质性程序表G2A',
    reviewSectionId: 'G2A-procedure',
  },
  G3A: {
    sheetCode: 'G3A',
    sheetLabel: '应收股利实质性程序表G3A',
    reviewSectionId: 'G3A-procedure',
  },
  G4A: {
    sheetCode: 'G4A',
    sheetLabel: '债权投资实质性程序表G4A',
    reviewSectionId: 'G4A-procedure',
  },
  G5A: {
    sheetCode: 'G5A',
    sheetLabel: '长期应收款实质性程序表G5A',
    reviewSectionId: 'G5A-procedure',
  },
  G6A: {
    sheetCode: 'G6A',
    sheetLabel: '其他债权投资实质性程序表G6A',
    reviewSectionId: 'G6A-procedure',
  },
  G7A: {
    sheetCode: 'G7A',
    sheetLabel: '长期股权投资实质性程序表G7A',
    reviewSectionId: 'G7A-procedure',
  },
  G8A: {
    sheetCode: 'G8A',
    sheetLabel: '其他权益工具投资实质性程序表G8A',
    reviewSectionId: 'G8A-procedure',
  },
  G9A: {
    sheetCode: 'G9A',
    sheetLabel: '其他非流动金融资产实质性程序表G9A',
    reviewSectionId: 'G9A-procedure',
  },
  G10A: {
    sheetCode: 'G10A',
    sheetLabel: '交易性金融负债实质性程序表G10A',
    reviewSectionId: 'G10A-procedure',
  },
  G11A: {
    sheetCode: 'G11A',
    sheetLabel: '投资收益实质性程序表G11A',
    reviewSectionId: 'G11A-procedure',
  },
  G12A: {
    sheetCode: 'G12A',
    sheetLabel: '净敞口套期收益审计程序表G12A',
    reviewSectionId: 'G12A-procedure',
  },
  G13A: {
    sheetCode: 'G13A',
    sheetLabel: '公允价值变动收益审计程序表G13A',
    reviewSectionId: 'G13A-procedure',
  },
  G14A: {
    sheetCode: 'G14A',
    sheetLabel: '信用减值损失审计程序表G14A',
    reviewSectionId: 'G14A-procedure',
  },
}

/** F/H 等循环程序表（*A） */
export const FH_CYCLE_PROCEDURE_SHEETS: Record<string, CycleProcedureSheetConfig> = {
  F1A: {
    sheetCode: 'F1A',
    sheetLabel: '预付账款实质性程序表F1A',
    reviewSectionId: 'F1A-procedure',
  },
  F2A: {
    sheetCode: 'F2A',
    sheetLabel: '存货实质性程序表F2A',
    reviewSectionId: 'F2A-procedure',
  },
  F3A: {
    sheetCode: 'F3A',
    sheetLabel: '应付票据实质性程序表F3A',
    reviewSectionId: 'F3A-procedure',
  },
  F4A: {
    sheetCode: 'F4A',
    sheetLabel: '应付账款实质性程序表F4A',
    reviewSectionId: 'F4A-procedure',
  },
  F5A: {
    sheetCode: 'F5A',
    sheetLabel: '营业成本实质性程序表F5A',
    reviewSectionId: 'F5A-procedure',
  },
  H10A: {
    sheetCode: 'H10A',
    sheetLabel: '资产处置损益实质性程序表H10A',
    reviewSectionId: 'H10A-procedure',
  },
}

/** E 循环程序表（*A） */
export const E_CYCLE_PROCEDURE_SHEETS: Record<string, CycleProcedureSheetConfig> = {
  E1A: {
    sheetCode: 'E1A',
    sheetLabel: '货币资金实质性程序表E1A',
    reviewSectionId: 'E1A-procedure',
  },
  E26A: {
    sheetCode: 'E26A',
    sheetLabel: '货币资金实质性程序表E26A',
    reviewSectionId: 'E26A-procedure',
  },
}

/** I 循环程序表（*A） */
export const I_CYCLE_PROCEDURE_SHEETS: Record<string, CycleProcedureSheetConfig> = {
  I1A: { sheetCode: 'I1A', sheetLabel: '无形资产实质性程序表I1A', reviewSectionId: 'I1A-procedure' },
  I2A: { sheetCode: 'I2A', sheetLabel: '开发支出实质性程序表I2A', reviewSectionId: 'I2A-procedure' },
  I3A: { sheetCode: 'I3A', sheetLabel: '商誉实质性程序表I3A', reviewSectionId: 'I3A-procedure' },
  I4A: { sheetCode: 'I4A', sheetLabel: '长期待摊费用实质性程序表I4A', reviewSectionId: 'I4A-procedure' },
  I5A: { sheetCode: 'I5A', sheetLabel: '其他非流动资产实质性程序表I5A', reviewSectionId: 'I5A-procedure' },
  I6A: { sheetCode: 'I6A', sheetLabel: '研发费用实质性程序表I6A', reviewSectionId: 'I6A-procedure' },
}

/** J 循环程序表（*A） */
export const J_CYCLE_PROCEDURE_SHEETS: Record<string, CycleProcedureSheetConfig> = {
  J1A: { sheetCode: 'J1A', sheetLabel: '应付职工薪酬实质性程序表J1A', reviewSectionId: 'J1A-procedure' },
  J2A: { sheetCode: 'J2A', sheetLabel: '长期应付职工薪酬（设定受益计划）实质性程序表J2A', reviewSectionId: 'J2A-procedure' },
  J3A: { sheetCode: 'J3A', sheetLabel: '股份支付实质性程序表J3A', reviewSectionId: 'J3A-procedure' },
}

/** K 循环程序表（*A） */
export const K_CYCLE_PROCEDURE_SHEETS: Record<string, CycleProcedureSheetConfig> = {
  K0A: { sheetCode: 'K0A', sheetLabel: '管理循环函证程序表K0A', reviewSectionId: 'K0A-procedure' },
  K1A: { sheetCode: 'K1A', sheetLabel: '其他应收款实质性程序表K1A', reviewSectionId: 'K1A-procedure' },
  K2A: { sheetCode: 'K2A', sheetLabel: '其他流动资产实质性程序表K2A', reviewSectionId: 'K2A-procedure' },
  K3A: { sheetCode: 'K3A', sheetLabel: '其他应付款实质性程序表K3A', reviewSectionId: 'K3A-procedure' },
  K4A: { sheetCode: 'K4A', sheetLabel: '其他流动负债实质性程序表K4A', reviewSectionId: 'K4A-procedure' },
  K5A: { sheetCode: 'K5A', sheetLabel: '预计负债实质性程序表K5A', reviewSectionId: 'K5A-procedure' },
  K6A: { sheetCode: 'K6A', sheetLabel: '持有待售资产和负债实质性程序表K6A', reviewSectionId: 'K6A-procedure' },
  K7A: { sheetCode: 'K7A', sheetLabel: '递延收益实质性程序表K7A', reviewSectionId: 'K7A-procedure' },
  K8A: { sheetCode: 'K8A', sheetLabel: '销售费用实质性程序表K8A', reviewSectionId: 'K8A-procedure' },
  K9A: { sheetCode: 'K9A', sheetLabel: '管理费用实质性程序表K9A', reviewSectionId: 'K9A-procedure' },
  K10A: { sheetCode: 'K10A', sheetLabel: '其他收益实质性程序表K10A', reviewSectionId: 'K10A-procedure' },
  K11A: { sheetCode: 'K11A', sheetLabel: '资产减值损失实质性程序表K11A', reviewSectionId: 'K11A-procedure' },
  K12A: { sheetCode: 'K12A', sheetLabel: '营业外收入实质性程序表K12A', reviewSectionId: 'K12A-procedure' },
  K13A: { sheetCode: 'K13A', sheetLabel: '营业外支出实质性程序表K13A', reviewSectionId: 'K13A-procedure' },
}

/** L 循环程序表（*A） */
export const L_CYCLE_PROCEDURE_SHEETS: Record<string, CycleProcedureSheetConfig> = {
  L0A: { sheetCode: 'L0A', sheetLabel: '筹资循环函证实质性程序表L0A', reviewSectionId: 'L0A-procedure' },
  L1A: { sheetCode: 'L1A', sheetLabel: '短期借款实质性程序表L1A', reviewSectionId: 'L1A-procedure' },
  L2A: { sheetCode: 'L2A', sheetLabel: '应付利息实质性程序表L2A', reviewSectionId: 'L2A-procedure' },
  L3A: { sheetCode: 'L3A', sheetLabel: '长期借款实质性程序表L3A', reviewSectionId: 'L3A-procedure' },
  L4A: { sheetCode: 'L4A', sheetLabel: '应付债券实质性程序表L4A', reviewSectionId: 'L4A-procedure' },
  L5A: { sheetCode: 'L5A', sheetLabel: '长期应付款实质性程序表L5A', reviewSectionId: 'L5A-procedure' },
  L6A: { sheetCode: 'L6A', sheetLabel: '专项应付款实质性程序表L6A', reviewSectionId: 'L6A-procedure' },
  L7A: { sheetCode: 'L7A', sheetLabel: '其他非流动负债实质性程序表L7A', reviewSectionId: 'L7A-procedure' },
  L8A: { sheetCode: 'L8A', sheetLabel: '财务费用实质性程序表L8A', reviewSectionId: 'L8A-procedure' },
}

/** M 循环程序表（*A） */
export const M_CYCLE_PROCEDURE_SHEETS: Record<string, CycleProcedureSheetConfig> = {
  M1A: { sheetCode: 'M1A', sheetLabel: '应付股利实质性程序表M1A', reviewSectionId: 'M1A-procedure' },
  M2A: { sheetCode: 'M2A', sheetLabel: '实收资本（股本）实质性程序表M2A', reviewSectionId: 'M2A-procedure' },
  M3A: { sheetCode: 'M3A', sheetLabel: '库存股实质性程序表M3A', reviewSectionId: 'M3A-procedure' },
  M4A: { sheetCode: 'M4A', sheetLabel: '资本公积实质性程序表M4A', reviewSectionId: 'M4A-procedure' },
  M5A: { sheetCode: 'M5A', sheetLabel: '盈余公积实质性程序表M5A', reviewSectionId: 'M5A-procedure' },
  M6A: { sheetCode: 'M6A', sheetLabel: '未分配利润实质性程序表M6A', reviewSectionId: 'M6A-procedure' },
  M7A: { sheetCode: 'M7A', sheetLabel: '专项储备实质性程序表M7A', reviewSectionId: 'M7A-procedure' },
  M8A: { sheetCode: 'M8A', sheetLabel: '一般风险准备实质性程序表M8A', reviewSectionId: 'M8A-procedure' },
  M9A: { sheetCode: 'M9A', sheetLabel: '其他综合收益实质性程序表M9A', reviewSectionId: 'M9A-procedure' },
  M10A: { sheetCode: 'M10A', sheetLabel: '其他权益工具实质性程序表M10A', reviewSectionId: 'M10A-procedure' },
}

/** N 循环程序表（*A） */
export const N_CYCLE_PROCEDURE_SHEETS: Record<string, CycleProcedureSheetConfig> = {
  N1A: { sheetCode: 'N1A', sheetLabel: '递延所得税资产实质性程序表N1A', reviewSectionId: 'N1A-procedure' },
  N2A: { sheetCode: 'N2A', sheetLabel: '应交税费实质性程序表N2A', reviewSectionId: 'N2A-procedure' },
  N3A: { sheetCode: 'N3A', sheetLabel: '递延所得税负债实质性程序表N3A', reviewSectionId: 'N3A-procedure' },
  N4A: { sheetCode: 'N4A', sheetLabel: '税金及附加实质性程序表N4A', reviewSectionId: 'N4A-procedure' },
  N5A: { sheetCode: 'N5A', sheetLabel: '所得税费用实质性程序表N5A', reviewSectionId: 'N5A-procedure' },
}

export const ALL_CYCLE_PROCEDURE_SHEETS: Record<string, CycleProcedureSheetConfig> = {
  ...D_CYCLE_PROCEDURE_SHEETS,
  ...G_CYCLE_PROCEDURE_SHEETS,
  ...FH_CYCLE_PROCEDURE_SHEETS,
  ...E_CYCLE_PROCEDURE_SHEETS,
  ...I_CYCLE_PROCEDURE_SHEETS,
  ...J_CYCLE_PROCEDURE_SHEETS,
  ...K_CYCLE_PROCEDURE_SHEETS,
  ...L_CYCLE_PROCEDURE_SHEETS,
  ...M_CYCLE_PROCEDURE_SHEETS,
  ...N_CYCLE_PROCEDURE_SHEETS,
}

const CYCLE_PROCEDURE_CODE_RE = /([A-Z]\d+A)\s*$/i

/** 从 sheet_name 提取已注册的循环程序表编码（如「应付账款实质性程序表F4A」→ F4A） */
export function extractCycleProcedureSheetCode(sheetName: string): string | null {
  if (!sheetName) return null
  const trimmed = sheetName.trim()
  const direct = trimmed.toUpperCase()
  if (ALL_CYCLE_PROCEDURE_SHEETS[direct]) return direct
  const m = trimmed.match(CYCLE_PROCEDURE_CODE_RE)
  const code = m ? m[1].toUpperCase() : null
  return code && ALL_CYCLE_PROCEDURE_SHEETS[code] ? code : null
}

export function getCycleProcedureSheetConfig(
  sheetCode: string,
): CycleProcedureSheetConfig | undefined {
  return ALL_CYCLE_PROCEDURE_SHEETS[sheetCode]
}
