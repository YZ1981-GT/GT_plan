/**
 * useS34FormulaEngine.ts — S34 子检查表公式引擎（纯函数）
 *
 * P1.4: 公式定义以 S34 hasSubTable workbook 为准，覆盖 12 个父码（含 S34-3）。
 *
 * 边界：本模块是前端 runtime 计算层。它不读取或写入后端 formula_settings，
 * 也不接入 formula_push；S 类继续保持 formula_push_rules.json 中无规则。
 * formula_settings 负责定义治理，runtime 负责给当前网格计算值，两者正交。
 *
 * 设计原则：
 * - 纯函数 composable，无副作用
 * - 支持 SUM 范围求和、安全除法、占比计算
 * - 公式单元格始终 readonly（不可手工覆盖）
 * - 只实现模板中真实存在的计算公式；无计算公式的结构化子表显式登记为空
 */

// ─── Types ───

export type FormulaDataRow = Record<string, number | string | null | undefined>

export interface FormulaCell {
  /** 行索引（0-based） */
  row: number
  /** 列标识 */
  col: string
  /** 人类可读/模板来源公式描述 */
  formula: string
  /** 计算函数：接收数据网格，返回计算值（null 表示除零/无效） */
  compute: (data: FormulaDataRow[]) => number | null
  /** 公式单元格始终只读 */
  readonly: true
}

export interface FormulaResult {
  /** "row:col" → 计算值 */
  [cellKey: string]: number | null
}

// ─── 核心纯函数 ───

/**
 * 安全数值解析：null/undefined/NaN/空 → 0
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

/**
 * 通用 SUM：对数值数组求和
 */
export function sumRange(values: number[]): number {
  return values.reduce((acc, v) => acc + v, 0)
}

/**
 * 安全除法：分母为 0 时返回 null（避免 Infinity/NaN）
 */
export function safeDivide(numerator: number, denominator: number): number | null {
  if (denominator === 0) return null
  return numerator / denominator
}

/**
 * 占比计算：numerator / denominator × 100（百分比形式）
 * 分母为 0 → null
 */
export function calcRatio(numerator: number, denominator: number): number | null {
  if (denominator === 0) return null
  return (numerator / denominator) * 100
}

/**
 * 从数据网格中提取某列某行范围的数值数组
 * @param data 数据行数组
 * @param col 列标识
 * @param startRow 起始行（0-based，含）
 * @param endRow 结束行（0-based，含）
 */
export function extractColumnRange(
  data: FormulaDataRow[],
  col: string,
  startRow: number,
  endRow: number,
): number[] {
  const result: number[] = []
  for (let i = startRow; i <= endRow && i < data.length; i++) {
    result.push(parseNum(data[i]?.[col]))
  }
  return result
}

/**
 * 获取单个单元格值
 */
export function getCellValue(
  data: FormulaDataRow[],
  row: number,
  col: string,
): number {
  if (row < 0 || row >= data.length) return 0
  return parseNum(data[row]?.[col])
}

function createFormulaCell(
  row: number,
  col: string,
  formula: string,
  compute: (data: FormulaDataRow[]) => number | null,
): FormulaCell {
  return { row, col, formula, compute, readonly: true }
}

function createUnsupportedTemplateFormula(
  row: number,
  col: string,
  formula: string,
): FormulaCell {
  // 例如模板中的裸 #REF!：保留来源事实，但不把错误引用扩散成一个假数。
  return createFormulaCell(row, col, formula, () => null)
}

function createErrorFallbackZeroFormula(
  row: number,
  col: string,
  formula: string,
): FormulaCell {
  // 模板用 IF(ISERROR(...),0,...) 包住 #REF!，其可观察结果是 0，而不是未定义值。
  return createFormulaCell(row, col, formula, () => 0)
}

function createCellReferenceFormula(
  row: number,
  col: string,
  formula: string,
  sourceRow: number,
  sourceCol: string,
): FormulaCell {
  return createFormulaCell(row, col, formula, (data) =>
    getCellValue(data, sourceRow, sourceCol),
  )
}

function createRatioOfCellsFormula(
  row: number,
  col: string,
  formula: string,
  numeratorRow: number,
  numeratorCol: string,
  denominatorRow: number,
  denominatorCol: string,
): FormulaCell {
  return createFormulaCell(row, col, formula, (data) =>
    safeDivide(
      getCellValue(data, numeratorRow, numeratorCol),
      getCellValue(data, denominatorRow, denominatorCol),
    ),
  )
}

function createRatioOrZeroFormula(
  row: number,
  col: string,
  formula: string,
  numeratorRow: number,
  numeratorCol: string,
  denominatorRow: number,
  denominatorCol: string,
): FormulaCell {
  return createFormulaCell(row, col, formula, (data) =>
    safeDivide(
      getCellValue(data, numeratorRow, numeratorCol),
      getCellValue(data, denominatorRow, denominatorCol),
    ) ?? 0,
  )
}

function createDifferenceRatioFormula(
  row: number,
  col: string,
  formula: string,
  leftRow: number,
  leftCol: string,
  rightRow: number,
  rightCol: string,
  denominatorRow: number,
  denominatorCol: string,
): FormulaCell {
  return createFormulaCell(row, col, formula, (data) =>
    safeDivide(
      getCellValue(data, leftRow, leftCol) - getCellValue(data, rightRow, rightCol),
      getCellValue(data, denominatorRow, denominatorCol),
    ),
  )
}

function createTemplateSumFormula(
  row: number,
  col: string,
  startRow: number,
  endRow: number,
  sourceFormula: string,
): FormulaCell {
  return createFormulaCell(row, col, sourceFormula, (data) =>
    sumRange(extractColumnRange(data, col, startRow, endRow)),
  )
}

// ─── S34-16 公式定义（按 workbook 实读） ───

/**
 * S34-16-1 第三方回款情况检查表。
 * workbook 的计算公式只有 E19、F19、C24、C25；C23「当期营业收入」是人工输入，
 * 不能按编号猜成 E19 的引用。
 */
export const S34_16_1_FORMULAS: FormulaCell[] = [
  createTemplateSumFormula(18, 'E', 7, 17, '=SUM(E8:E18)'),
  createTemplateSumFormula(18, 'F', 7, 17, '=SUM(F8:F18)'),
  createCellReferenceFormula(23, 'C', '=F19', 18, 'F'),
  createRatioOfCellsFormula(24, 'C', '=C24/C23', 23, 'C', 22, 'C'),
]

/**
 * S34-16-2 同行业第三方回款对比表。
 * 实际模板不是逐行 F/E 占比：G19 是合计，E24 保留为 #REF!，E25 依赖 E24/E23。
 */
export const S34_16_2_FORMULAS: FormulaCell[] = [
  createTemplateSumFormula(18, 'G', 7, 17, '=SUM(G8:G18)'),
  createUnsupportedTemplateFormula(23, 'E', '=#REF!'),
  createFormulaCell(24, 'E', '=E24/E23', (data) => {
    const rawNumerator = data[23]?.E
    if (rawNumerator === null || rawNumerator === undefined || rawNumerator === '') return null
    return safeDivide(parseNum(rawNumerator), parseNum(data[22]?.E))
  }),
]

// ─── S34-20-1 公式定义（重要劳务外包公司分析） ───

const S34_20_RATIO_ROWS = [15, 16, 17] // Excel rows 16~18

export const S34_20_1_FORMULAS: FormulaCell[] = [
  ...S34_20_RATIO_ROWS.flatMap((row) => [
    createRatioOrZeroFormula(
      row,
      'D',
      `=IF(ISERROR(C${row + 1}/$C$13),0,C${row + 1}/$C$13)`,
      row,
      'C',
      12,
      'C',
    ),
    createRatioOrZeroFormula(
      row,
      'F',
      `=IF(ISERROR(E${row + 1}/$G$13),0,E${row + 1}/$G$13)`,
      row,
      'E',
      12,
      'G',
    ),
  ]),
  // 原模板 D19/F19/D20/F20 含 #REF!，但外层 ISERROR 明确把错误分支记为 0。
  createErrorFallbackZeroFormula(18, 'D', '=IF(ISERROR(C19/#REF!),0,C19/#REF!)'),
  createErrorFallbackZeroFormula(18, 'F', '=IF(ISERROR(E19/#REF!),0,E19/#REF!)'),
  createErrorFallbackZeroFormula(19, 'D', '=IF(ISERROR(C20/#REF!),0,C20/#REF!)'),
  createErrorFallbackZeroFormula(19, 'F', '=IF(ISERROR(E20/#REF!),0,E20/#REF!)'),
  createTemplateSumFormula(20, 'C', 15, 17, '=SUM(C16:C18)'),
  createTemplateSumFormula(20, 'D', 15, 19, '=SUM(D16:D20)'),
  createTemplateSumFormula(20, 'E', 15, 19, '=SUM(E16:E20)'),
  createTemplateSumFormula(20, 'F', 15, 19, '=SUM(F16:F20)'),
  createTemplateSumFormula(30, 'C', 23, 29, '=SUM(C24:C30)'),
  createTemplateSumFormula(30, 'D', 23, 29, '=SUM(D24:D30)'),
  createTemplateSumFormula(30, 'E', 23, 29, '=SUM(E24:E30)'),
  ...[34, 35, 36].flatMap((row) => [
    createRatioOfCellsFormula(row, 'E', `=C${row + 1}/D${row + 1}`, row, 'C', row, 'D'),
    createRatioOfCellsFormula(row, 'I', `=G${row + 1}/H${row + 1}`, row, 'G', row, 'H'),
    createDifferenceRatioFormula(
      row,
      'J',
      `=(E${row + 1}-I${row + 1})/D${row + 1}`,
      row,
      'E',
      row,
      'I',
      row,
      'D',
    ),
  ]),
]

// ─── S34-34-1/2 公式定义（自然人客户/供应商检查表） ───

function createS34_34Formulas(): FormulaCell[] {
  const formulas: FormulaCell[] = [
    createRatioOfCellsFormula(8, 'E', '=D9/D10', 8, 'D', 9, 'D'),
    createRatioOfCellsFormula(8, 'O', '=N9/N10', 8, 'N', 9, 'N'),
  ]

  for (let row = 11; row <= 20; row += 1) {
    formulas.push(
      createRatioOfCellsFormula(
        row,
        'H',
        `=G${row + 1}/$D$10`,
        row,
        'G',
        9,
        'D',
      ),
      createRatioOfCellsFormula(
        row,
        'J',
        `=I${row + 1}/$N$10`,
        row,
        'I',
        9,
        'N',
      ),
    )
  }

  // workbook 自身把 G22/I22 写成包含自身的范围；runtime 按业务意图只汇总明细行 12~21，
  // 避免把用户旧值或循环引用带入结果，同时保留原始公式文本供溯源。
  formulas.push(
    createTemplateSumFormula(21, 'G', 11, 20, '=SUM(G12:G22)'),
    createRatioOfCellsFormula(21, 'H', '=G22/D10', 21, 'G', 9, 'D'),
    createTemplateSumFormula(21, 'I', 11, 20, '=SUM(I12:I22)'),
    createRatioOfCellsFormula(21, 'J', '=I22/N10', 21, 'I', 9, 'N'),
  )
  return formulas
}

export const S34_34_1_FORMULAS: FormulaCell[] = createS34_34Formulas()
export const S34_34_2_FORMULAS: FormulaCell[] = createS34_34Formulas()

// ─── 12 个 hasSubTable 父码与 workbook 清册 ───

export const S34_HAS_SUBTABLE_PARENTS = [
  'S34-2',
  'S34-3',
  'S34-4',
  'S34-8',
  'S34-9',
  'S34-11',
  'S34-16',
  'S34-18',
  'S34-20',
  'S34-25',
  'S34-30',
  'S34-34',
] as const

export type S34HasSubTableParent = typeof S34_HAS_SUBTABLE_PARENTS[number]

export interface S34SubTableDefinition {
  parentCode: S34HasSubTableParent
  /** 运行时逻辑 sheet code（与 S34_TAB_CONFIG.subSheets 对齐） */
  sheetCode: string
  /** workbook 中实读的精确 sheet 名；部分模板存在空格/错码，不能猜测 */
  templateSheetName: string
  /** workbook 公式单元数量（含表头引用），用于清册对账 */
  templateFormulaCount: number
  /** runtime 实际计算定义；表头引用不在数据网格 runtime 内 */
  formulas: FormulaCell[]
}

const S34_SHEET_FORMULA_DEFS: Record<string, FormulaCell[]> = {
  // 结构化核查子表：模板没有计算公式，显式为空，不人为添加公式。
  'S34-2-1': [],
  'S34-2-2': [],
  'S34-3-1': [],
  'S34-4-1': [],
  'S34-8-1': [],
  'S34-8-2': [],
  'S34-9-1': [],
  'S34-11-1': [],
  'S34-16-1': S34_16_1_FORMULAS,
  'S34-16-2': S34_16_2_FORMULAS,
  'S34-18-1': [],
  'S34-20-1': S34_20_1_FORMULAS,
  'S34-25-1': [],
  'S34-25-2': [],
  'S34-25-3': [],
  'S34-30-1': [],
  'S34-34-1': S34_34_1_FORMULAS,
  'S34-34-2': S34_34_2_FORMULAS,
}

export const S34_SUBTABLE_DEFINITIONS: readonly S34SubTableDefinition[] = [
  { parentCode: 'S34-2', sheetCode: 'S34-2-1', templateSheetName: 'S34-2-1期权激励对象、数量核查', templateFormulaCount: 0, formulas: S34_SHEET_FORMULA_DEFS['S34-2-1'] },
  { parentCode: 'S34-2', sheetCode: 'S34-2-2', templateSheetName: 'S34-2-2期后执行及信息披露情况', templateFormulaCount: 0, formulas: S34_SHEET_FORMULA_DEFS['S34-2-2'] },
  { parentCode: 'S34-3', sheetCode: 'S34-3-1', templateSheetName: 'S34-3-1股份支付核查', templateFormulaCount: 0, formulas: S34_SHEET_FORMULA_DEFS['S34-3-1'] },
  { parentCode: 'S34-4', sheetCode: 'S34-4-1', templateSheetName: 'S34-4-1 关联交易核查', templateFormulaCount: 0, formulas: S34_SHEET_FORMULA_DEFS['S34-4-1'] },
  { parentCode: 'S34-8', sheetCode: 'S34-8-1', templateSheetName: 'S34-8-1非同一控制合并无形资产确认', templateFormulaCount: 0, formulas: S34_SHEET_FORMULA_DEFS['S34-8-1'] },
  { parentCode: 'S34-8', sheetCode: 'S34-8-2', templateSheetName: 'S34-8-2客户资源或客户关系确认为无形资产', templateFormulaCount: 0, formulas: S34_SHEET_FORMULA_DEFS['S34-8-2'] },
  { parentCode: 'S34-9', sheetCode: 'S34-9-1', templateSheetName: 'S34-9-1 共同投资核查', templateFormulaCount: 0, formulas: S34_SHEET_FORMULA_DEFS['S34-9-1'] },
  { parentCode: 'S34-11', sheetCode: 'S34-11-1', templateSheetName: 'S34-11 -1同一控制合并判断', templateFormulaCount: 0, formulas: S34_SHEET_FORMULA_DEFS['S34-11-1'] },
  { parentCode: 'S34-16', sheetCode: 'S34-16-1', templateSheetName: 'S34-16-1第三方回款情况检查表', templateFormulaCount: 10, formulas: S34_SHEET_FORMULA_DEFS['S34-16-1'] },
  { parentCode: 'S34-16', sheetCode: 'S34-16-2', templateSheetName: 'S34-16-2 同行业第三方回款对比表', templateFormulaCount: 9, formulas: S34_SHEET_FORMULA_DEFS['S34-16-2'] },
  { parentCode: 'S34-18', sheetCode: 'S34-18-1', templateSheetName: 'S34-18 -1引用第三方数据', templateFormulaCount: 6, formulas: S34_SHEET_FORMULA_DEFS['S34-18-1'] },
  { parentCode: 'S34-20', sheetCode: 'S34-20-1', templateSheetName: 'S34-20-1重要劳务外包公司分析', templateFormulaCount: 32, formulas: S34_SHEET_FORMULA_DEFS['S34-20-1'] },
  { parentCode: 'S34-25', sheetCode: 'S34-25-1', templateSheetName: 'S34-25-1第三方资金流水核查范围', templateFormulaCount: 4, formulas: S34_SHEET_FORMULA_DEFS['S34-25-1'] },
  { parentCode: 'S34-25', sheetCode: 'S34-25-2', templateSheetName: 'S34-25-2银行账户信息完整性承诺（参考格式）', templateFormulaCount: 0, formulas: S34_SHEET_FORMULA_DEFS['S34-25-2'] },
  { parentCode: 'S34-25', sheetCode: 'S34-25-3', templateSheetName: 'S34-25-3第三方资金流水核查', templateFormulaCount: 0, formulas: S34_SHEET_FORMULA_DEFS['S34-25-3'] },
  { parentCode: 'S34-30', sheetCode: 'S34-30-1', templateSheetName: 'S34-34 -1对赌协议', templateFormulaCount: 0, formulas: S34_SHEET_FORMULA_DEFS['S34-30-1'] },
  { parentCode: 'S34-34', sheetCode: 'S34-34-1', templateSheetName: 'S34-34-1自然人客户检查表', templateFormulaCount: 26, formulas: S34_SHEET_FORMULA_DEFS['S34-34-1'] },
  { parentCode: 'S34-34', sheetCode: 'S34-34-2', templateSheetName: 'S34-34-2自然人供应商检查表', templateFormulaCount: 26, formulas: S34_SHEET_FORMULA_DEFS['S34-34-2'] },
]

/** 获取某个子 sheet 的 runtime 公式定义。 */
export function getS34FormulaDefinitions(sheetCode: string): FormulaCell[] {
  return S34_SHEET_FORMULA_DEFS[sheetCode] ?? []
}

/** 获取某个父码下全部子表的清册定义。 */
export function getS34SubTableDefinitions(parentCode: string): S34SubTableDefinition[] {
  return S34_SUBTABLE_DEFINITIONS.filter((definition) => definition.parentCode === parentCode)
}

/** 获取某个父码下全部 runtime 公式（结构化无公式父码返回空数组）。 */
export function getS34ParentFormulaDefinitions(parentCode: string): FormulaCell[] {
  return getS34SubTableDefinitions(parentCode).flatMap((definition) => definition.formulas)
}

/** 按子 sheet 计算 runtime 公式；不触发网络、持久化或 formula_settings。 */
export function computeS34SubTableFormulas(
  sheetCode: string,
  data: FormulaDataRow[],
): FormulaResult {
  return computeFormulas(data, getS34FormulaDefinitions(sheetCode))
}

// ─── 通用公式计算引擎 ───

/**
 * 计算所有公式值，返回 "row:col" → 计算结果 的映射。
 *
 * 公式按定义顺序计算，并把已计算值写入内部副本，支持模板中的
 * `=F19`、`=C24/C23` 等依赖，同时绝不修改调用方传入的 data。
 */
export function computeFormulas(
  data: FormulaDataRow[],
  formulaDefs: FormulaCell[],
): FormulaResult {
  const result: FormulaResult = {}
  const calculatedData = data.map((row) => ({ ...row }))
  for (const def of formulaDefs) {
    const value = def.compute(calculatedData)
    const key = `${def.row}:${def.col}`
    result[key] = value
    calculatedData[def.row] = {
      ...(calculatedData[def.row] ?? {}),
      [def.col]: value,
    }
  }
  return result
}

/** 获取公式单元格位置集合（用于标记只读）。 */
export function getReadonlyCells(formulaDefs: FormulaCell[]): Set<string> {
  return new Set(formulaDefs.map((def) => `${def.row}:${def.col}`))
}

/** 判断某单元格是否为公式单元格（只读）。 */
export function isFormulaCell(
  row: number,
  col: string,
  formulaDefs: FormulaCell[],
): boolean {
  return formulaDefs.some((def) => def.row === row && def.col === col)
}

// ─── 公式单元描述（统一治理接入元数据） ──────────────────────────────────────

/** S34 公式单元描述：单元键 + 表达式 + ACNR 稳定 addr_id。 */
export interface S34FormulaCellDescriptor {
  cellKey: string
  row: number
  col: string
  expression: string
  addrId: string
}

/**
 * 获取某子 sheet 的公式单元描述清单（供 GtFormulaSourceTooltip 展示表达式+来源）。
 * 无 runtime 公式的结构化子表返回空数组；表头链接公式不进入数据网格 runtime。
 */
export function getS34FormulaDescriptors(sheetCode: string): S34FormulaCellDescriptor[] {
  return getS34FormulaDefinitions(sheetCode).map((def) => ({
    cellKey: `${def.row}:${def.col}`,
    row: def.row,
    col: def.col,
    expression: def.formula,
    addrId: `S34/${sheetCode}/${def.col}${def.row + 1}`,
  }))
}

// ─── 工厂函数 ───

/** 创建阈值判断公式：IF(源值 > threshold, 1, 0)。 */
export function createThresholdFormula(
  row: number,
  col: string,
  sourceCol: string,
  threshold = 0,
): FormulaCell {
  return createFormulaCell(
    row,
    col,
    `=IF(${sourceCol}${row + 1}>${threshold}, 1, 0)`,
    (data) => {
      const val = parseNum(data[row]?.[sourceCol])
      return val > threshold ? 1 : 0
    },
  )
}

/** 创建占比公式：某行值 / 合计行值。 */
export function createRatioFormula(
  row: number,
  col: string,
  valueCol: string,
  totalRow: number,
): FormulaCell {
  return createFormulaCell(
    row,
    col,
    `=${valueCol}${row + 1}/${valueCol}${totalRow + 1} (占比)`,
    (data) => safeDivide(parseNum(data[row]?.[valueCol]), parseNum(data[totalRow]?.[valueCol])),
  )
}

/** 创建 SUM 公式。 */
export function createSumFormula(
  row: number,
  col: string,
  startRow: number,
  endRow: number,
): FormulaCell {
  return createTemplateSumFormula(row, col, startRow, endRow, `=SUM(${col}${startRow + 1}:${col}${endRow + 1})`)
}
