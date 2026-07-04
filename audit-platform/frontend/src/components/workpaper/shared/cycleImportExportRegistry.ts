/**
 * 各循环底稿支持导入导出的 sheet 清单（与后端 _f*_import_export.py 对齐）
 */
export interface CycleImportExportEntry {
  apiPrefix: string
  sheets: readonly string[]
}

/** 复合 sheet（一个底稿页含多个可导入区段） */
export interface CompoundImportExportGroup {
  baseSheet: string
  variants: readonly { label: string; sheet: string }[]
}

export const CYCLE_IMPORT_EXPORT: Record<string, CycleImportExportEntry> = {
  f1: {
    apiPrefix: 'f1',
    sheets: ['F1-2', 'F1-5', 'F1-6', 'F1-7', 'F1-7-post'],
  },
  f2: {
    apiPrefix: 'f2',
    sheets: [
      'F2-3', 'F2-4', 'F2-5', 'F2-6', 'F2-7', 'F2-8', 'F2-9', 'F2-10', 'F2-11', 'F2-12', 'F2-13',
      'F2-14', 'F2-19', 'F2-20', 'F2-29', 'F2-30', 'F2-31', 'F2-32',
    ],
  },
  'f2-val': {
    apiPrefix: 'f2-val',
    sheets: [
      'F2-33', 'F2-34', 'F2-35',
      'F2-38', 'F2-39', 'F2-40',
      'F2-41', 'F2-42', 'F2-43', 'F2-44',
      'F2-47', 'F2-48', 'F2-49', 'F2-52',
    ],
  },
  'f2-spe': {
    apiPrefix: 'f2-spe',
    sheets: [
      'F2-55', 'F2-56', 'F2-57', 'F2-58',
      'F2-61', 'F2-62', 'F2-63', 'F2-64',
      'F2-65', 'F2-66', 'F2-67', 'F2-68', 'F2-69', 'F2-70', 'F2-71', 'F2-72',
    ],
  },
  'f2-st': {
    apiPrefix: 'f2-st',
    sheets: ['F2-24', 'F2-25', 'F2-26'],
  },
  f3: {
    apiPrefix: 'f3',
    sheets: ['F3-2', 'F3-3', 'F3-4', 'F3-5', 'F3-6'],
  },
  f4: {
    apiPrefix: 'f4',
    sheets: [
      'F4-2', 'F4-3', 'F4-5', 'F4-6',
      'F4-7-purchase', 'F4-7-inbound', 'F4-7-invoice',
      'F4-8-debit', 'F4-8-credit',
      'F4-9-factoring', 'F4-9-note', 'F4-9-supply',
    ],
  },
  f5: {
    apiPrefix: 'f5',
    sheets: ['F5-2', 'F5-3', 'F5-4', 'F5-5', 'F5-6', 'F5-8'],
  },
}

export const COMPOUND_IMPORT_EXPORT: Record<string, CompoundImportExportGroup[]> = {
  f4: [
    {
      baseSheet: 'F4-7',
      variants: [
        { label: '期后采购', sheet: 'F4-7-purchase' },
        { label: '期后入库', sheet: 'F4-7-inbound' },
        { label: '期后收票', sheet: 'F4-7-invoice' },
      ],
    },
    {
      baseSheet: 'F4-8',
      variants: [
        { label: '借方检查', sheet: 'F4-8-debit' },
        { label: '贷方检查', sheet: 'F4-8-credit' },
      ],
    },
    {
      baseSheet: 'F4-9',
      variants: [
        { label: '保理融资', sheet: 'F4-9-factoring' },
        { label: '票据融资', sheet: 'F4-9-note' },
        { label: '供应链融资', sheet: 'F4-9-supply' },
      ],
    },
  ],
}

export function isImportExportSheet(cycleKey: keyof typeof CYCLE_IMPORT_EXPORT, sheetCode: string): boolean {
  const entry = CYCLE_IMPORT_EXPORT[cycleKey]
  if (!entry) return false
  if (entry.sheets.includes(sheetCode)) return true
  return (COMPOUND_IMPORT_EXPORT[cycleKey] ?? []).some((g) => g.baseSheet === sheetCode)
}

export function resolveImportExportSheet(
  cycleKey: keyof typeof CYCLE_IMPORT_EXPORT,
  sheetCode: string,
): { apiPrefix: string; sheet: string; variants?: CompoundImportExportGroup['variants'] } | null {
  const entry = CYCLE_IMPORT_EXPORT[cycleKey]
  if (!entry) return null
  if (entry.sheets.includes(sheetCode)) {
    return { apiPrefix: entry.apiPrefix, sheet: sheetCode }
  }
  const group = (COMPOUND_IMPORT_EXPORT[cycleKey] ?? []).find((g) => g.baseSheet === sheetCode)
  if (group) {
    return { apiPrefix: entry.apiPrefix, sheet: group.variants[0].sheet, variants: group.variants }
  }
  return null
}

export function getImportExportConfig(cycleKey: keyof typeof CYCLE_IMPORT_EXPORT): CycleImportExportEntry | undefined {
  return CYCLE_IMPORT_EXPORT[cycleKey]
}
