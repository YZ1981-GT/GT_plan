// @generated DO NOT EDIT — 由 gen_formula_function_catalog.py 生成
// spec: formula-grammar-resolver-unification · S1 ADR-FGR-01

export type FormulaEngine = 'l1' | 'note' | 'cell'

export interface FunctionSpec {
  name: string
  arityMin: number
  arityMax: number | null
  engines: readonly FormulaEngine[]
  category: string
  syntax: string
  description: string
}

export const FUNCTIONS: readonly FunctionSpec[] = [
  { name: 'TB', arityMin: 1, arityMax: 2, engines: ['l1', 'note'], category: '取数', syntax: 'TB(\'科目编码\'[,\'列名\'])', description: '取科目余额' },
  { name: 'SUM_TB', arityMin: 1, arityMax: 2, engines: ['l1'], category: '取数', syntax: 'SUM_TB(\'起始~结束\'[,\'列名\'])', description: '范围科目求和' },
  { name: 'PREV', arityMin: 2, arityMax: 3, engines: ['l1'], category: '取数', syntax: 'PREV(\'科目\',\'列名\') / PREV(\'底稿\',\'表\',\'字段\')', description: '上年同期值' },
  { name: 'AUX', arityMin: 2, arityMax: 4, engines: ['l1'], category: '取数', syntax: 'AUX(\'科目\',\'维度\'[,\'辅助项\'],\'列名\')', description: '辅助核算取值' },
  { name: 'NOTE', arityMin: 2, arityMax: 3, engines: ['l1', 'note'], category: '取数', syntax: 'NOTE(\'章节\',\'行\'[,\'列\'])', description: '附注数据取值' },
  { name: 'WP', arityMin: 2, arityMax: 3, engines: ['l1', 'note'], category: '取数', syntax: 'WP(\'底稿编码\',\'列名|单元格\') / WP(\'底稿\',\'表\',\'锚点\')', description: '底稿数据取值' },
  { name: 'ADJ', arityMin: 1, arityMax: 2, engines: ['l1'], category: '取数', syntax: 'ADJ(\'科目编码\'[,\'aje_net|rje_net\'])', description: '调整额实时汇总（净额）' },
  { name: 'ROW', arityMin: 1, arityMax: 1, engines: ['l1'], category: '引用', syntax: 'ROW(\'行次编码\')', description: '引用其他行次' },
  { name: 'SUM_ROW', arityMin: 2, arityMax: 2, engines: ['l1'], category: '引用', syntax: 'SUM_ROW(\'起始\',\'结束\')', description: '范围行次求和' },
  { name: 'REPORT', arityMin: 1, arityMax: 2, engines: ['l1', 'note'], category: '引用', syntax: 'REPORT(\'行次编码\'[,\'期间\'])', description: '跨报表引用' },
  { name: 'ABS', arityMin: 1, arityMax: 1, engines: ['cell', 'l1', 'note'], category: '数学', syntax: 'ABS(值)', description: '绝对值' },
  { name: 'ROUND', arityMin: 1, arityMax: 2, engines: ['cell', 'l1', 'note'], category: '数学', syntax: 'ROUND(值[,位数])', description: '四舍五入' },
  { name: 'MAX', arityMin: 2, arityMax: null, engines: ['cell', 'l1', 'note'], category: '数学', syntax: 'MAX(值1, 值2[, ...])', description: '最大值' },
  { name: 'MIN', arityMin: 2, arityMax: null, engines: ['cell', 'l1', 'note'], category: '数学', syntax: 'MIN(值1, 值2[, ...])', description: '最小值' },
  { name: 'IF', arityMin: 3, arityMax: 3, engines: ['cell', 'l1', 'note'], category: '逻辑', syntax: 'IF(条件, 真值, 假值)', description: '条件判断' },
  { name: 'LEDGER', arityMin: 2, arityMax: 3, engines: ['l1'], category: '底稿取数', syntax: 'LEDGER(\'科目\',\'方向\'[,\'范围\'])', description: '序时账取数' },
  { name: 'LEDGER_DETAIL', arityMin: 1, arityMax: 3, engines: ['l1'], category: '底稿取数', syntax: 'LEDGER_DETAIL(\'科目\'[,\'期间\'][,\'金额条件\'])', description: '序时账明细筛选' },
  { name: 'TB_AUX', arityMin: 3, arityMax: 3, engines: ['l1'], category: '底稿取数', syntax: 'TB_AUX(\'科目\',\'维度\',\'列名\')', description: '辅助维度汇总' },
  { name: 'COUNT_LEDGER', arityMin: 1, arityMax: 2, engines: ['l1'], category: '底稿取数', syntax: 'COUNT_LEDGER(\'科目\'[,\'范围\'])', description: '序时账笔数统计' },
  { name: 'PLACEHOLDER', arityMin: 0, arityMax: 1, engines: ['l1'], category: '底稿取数', syntax: 'PLACEHOLDER()', description: '预留占位' },
  { name: 'PRIOR', arityMin: 2, arityMax: 3, engines: ['note'], category: '附注取数', syntax: 'PRIOR(\'科目|章节\',\'期末|期初\') / PRIOR(\'章节\',\'行\',\'期末|期初\')', description: '上年附注取数（附注域专属，L1 请用 PREV）' },
  { name: 'AGING', arityMin: 2, arityMax: 2, engines: ['note'], category: '附注取数', syntax: 'AGING(\'科目\',\'桶名\')', description: '账龄分桶取数' },
  { name: 'REGION', arityMin: 2, arityMax: 3, engines: ['note'], category: '附注取数', syntax: 'REGION(\'区域名\',\'列\'[,agg=\'sum\'])', description: '表内动态区域取数' },
  { name: 'SUM', arityMin: 2, arityMax: 2, engines: ['note'], category: '附注取数', syntax: 'SUM(起始行:结束行, 列)', description: '表内行范围求和（附注域）' },
  { name: 'cell', arityMin: 2, arityMax: 2, engines: ['note'], category: '附注取数', syntax: 'cell(行, 列)', description: '表内单元格引用（附注域）' },
] as const

/** 按引擎取函数名集合 */
export const FUNCTION_NAMES_BY_ENGINE: Record<FormulaEngine, ReadonlySet<string>> = {
  l1: new Set(['ABS', 'ADJ', 'AUX', 'COUNT_LEDGER', 'IF', 'LEDGER', 'LEDGER_DETAIL', 'MAX', 'MIN', 'NOTE', 'PLACEHOLDER', 'PREV', 'REPORT', 'ROUND', 'ROW', 'SUM_ROW', 'SUM_TB', 'TB', 'TB_AUX', 'WP']),
  note: new Set(['ABS', 'AGING', 'IF', 'MAX', 'MIN', 'NOTE', 'PRIOR', 'REGION', 'REPORT', 'ROUND', 'SUM', 'TB', 'WP', 'cell']),
  cell: new Set(['ABS', 'IF', 'MAX', 'MIN', 'ROUND']),
}

/** 按引擎取参数范围 [min, max] */
export const ARITY_BY_ENGINE: Record<FormulaEngine, Record<string, [number, number | null]>> = {
  l1: {
    ABS: [1, 1],
    ADJ: [1, 2],
    AUX: [2, 4],
    COUNT_LEDGER: [1, 2],
    IF: [3, 3],
    LEDGER: [2, 3],
    LEDGER_DETAIL: [1, 3],
    MAX: [2, null],
    MIN: [2, null],
    NOTE: [2, 3],
    PLACEHOLDER: [0, 1],
    PREV: [2, 3],
    REPORT: [1, 2],
    ROUND: [1, 2],
    ROW: [1, 1],
    SUM_ROW: [2, 2],
    SUM_TB: [1, 2],
    TB: [1, 2],
    TB_AUX: [3, 3],
    WP: [2, 3],
  },
  note: {
    ABS: [1, 1],
    AGING: [2, 2],
    IF: [3, 3],
    MAX: [2, null],
    MIN: [2, null],
    NOTE: [2, 3],
    PRIOR: [2, 3],
    REGION: [2, 3],
    REPORT: [1, 2],
    ROUND: [1, 2],
    SUM: [2, 2],
    TB: [1, 2],
    WP: [2, 3],
    cell: [2, 2],
  },
  cell: {
    ABS: [1, 1],
    IF: [3, 3],
    MAX: [2, null],
    MIN: [2, null],
    ROUND: [1, 2],
  },
}

/** 按引擎取运算符集合 */
export const OPERATORS_BY_ENGINE: Record<FormulaEngine, ReadonlySet<string>> = {
  l1: new Set(['!=', '*', '+', '-', '/', '<', '<=', '=', '>', '>=']),
  note: new Set(['*', '+', '-', '/']),
  cell: new Set(['*', '+', '-', '/']),
}

/** 函数提示列表（用于自动补全） */
export const FUNCTION_HINTS_BY_ENGINE: Record<FormulaEngine, readonly { name: string; minArgs: number; maxArgs: number | null; description: string }[]> = {
  l1: [
    { name: 'ABS', minArgs: 1, maxArgs: 1, description: "ABS(值)" },
    { name: 'ADJ', minArgs: 1, maxArgs: 2, description: "ADJ('科目编码'[,'aje_net|rje_net'])" },
    { name: 'AUX', minArgs: 2, maxArgs: 4, description: "AUX('科目','维度'[,'辅助项'],'列名')" },
    { name: 'COUNT_LEDGER', minArgs: 1, maxArgs: 2, description: "COUNT_LEDGER('科目'[,'范围'])" },
    { name: 'IF', minArgs: 3, maxArgs: 3, description: "IF(条件, 真值, 假值)" },
    { name: 'LEDGER', minArgs: 2, maxArgs: 3, description: "LEDGER('科目','方向'[,'范围'])" },
    { name: 'LEDGER_DETAIL', minArgs: 1, maxArgs: 3, description: "LEDGER_DETAIL('科目'[,'期间'][,'金额条件'])" },
    { name: 'MAX', minArgs: 2, maxArgs: null, description: "MAX(值1, 值2[, ...])" },
    { name: 'MIN', minArgs: 2, maxArgs: null, description: "MIN(值1, 值2[, ...])" },
    { name: 'NOTE', minArgs: 2, maxArgs: 3, description: "NOTE('章节','行'[,'列'])" },
    { name: 'PLACEHOLDER', minArgs: 0, maxArgs: 1, description: "PLACEHOLDER()" },
    { name: 'PREV', minArgs: 2, maxArgs: 3, description: "PREV('科目','列名') / PREV('底稿','表','字段')" },
    { name: 'REPORT', minArgs: 1, maxArgs: 2, description: "REPORT('行次编码'[,'期间'])" },
    { name: 'ROUND', minArgs: 1, maxArgs: 2, description: "ROUND(值[,位数])" },
    { name: 'ROW', minArgs: 1, maxArgs: 1, description: "ROW('行次编码')" },
    { name: 'SUM_ROW', minArgs: 2, maxArgs: 2, description: "SUM_ROW('起始','结束')" },
    { name: 'SUM_TB', minArgs: 1, maxArgs: 2, description: "SUM_TB('起始~结束'[,'列名'])" },
    { name: 'TB', minArgs: 1, maxArgs: 2, description: "TB('科目编码'[,'列名'])" },
    { name: 'TB_AUX', minArgs: 3, maxArgs: 3, description: "TB_AUX('科目','维度','列名')" },
    { name: 'WP', minArgs: 2, maxArgs: 3, description: "WP('底稿编码','列名|单元格') / WP('底稿','表','锚点')" },
  ],
  note: [
    { name: 'ABS', minArgs: 1, maxArgs: 1, description: "ABS(值)" },
    { name: 'AGING', minArgs: 2, maxArgs: 2, description: "AGING('科目','桶名')" },
    { name: 'IF', minArgs: 3, maxArgs: 3, description: "IF(条件, 真值, 假值)" },
    { name: 'MAX', minArgs: 2, maxArgs: null, description: "MAX(值1, 值2[, ...])" },
    { name: 'MIN', minArgs: 2, maxArgs: null, description: "MIN(值1, 值2[, ...])" },
    { name: 'NOTE', minArgs: 2, maxArgs: 3, description: "NOTE('章节','行'[,'列'])" },
    { name: 'PRIOR', minArgs: 2, maxArgs: 3, description: "PRIOR('科目|章节','期末|期初') / PRIOR('章节','行','期末|期初')" },
    { name: 'REGION', minArgs: 2, maxArgs: 3, description: "REGION('区域名','列'[,agg='sum'])" },
    { name: 'REPORT', minArgs: 1, maxArgs: 2, description: "REPORT('行次编码'[,'期间'])" },
    { name: 'ROUND', minArgs: 1, maxArgs: 2, description: "ROUND(值[,位数])" },
    { name: 'SUM', minArgs: 2, maxArgs: 2, description: "SUM(起始行:结束行, 列)" },
    { name: 'TB', minArgs: 1, maxArgs: 2, description: "TB('科目编码'[,'列名'])" },
    { name: 'WP', minArgs: 2, maxArgs: 3, description: "WP('底稿编码','列名|单元格') / WP('底稿','表','锚点')" },
    { name: 'cell', minArgs: 2, maxArgs: 2, description: "cell(行, 列)" },
  ],
  cell: [
    { name: 'ABS', minArgs: 1, maxArgs: 1, description: "ABS(值)" },
    { name: 'IF', minArgs: 3, maxArgs: 3, description: "IF(条件, 真值, 假值)" },
    { name: 'MAX', minArgs: 2, maxArgs: null, description: "MAX(值1, 值2[, ...])" },
    { name: 'MIN', minArgs: 2, maxArgs: null, description: "MIN(值1, 值2[, ...])" },
    { name: 'ROUND', minArgs: 1, maxArgs: 2, description: "ROUND(值[,位数])" },
  ],
}
