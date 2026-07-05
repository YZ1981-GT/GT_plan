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
