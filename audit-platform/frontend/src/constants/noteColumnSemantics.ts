/**
 * 附注列语义清单（前端硬编码副本）.
 *
 * Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 3 Task 3.1
 * Source: backend/app/services/note_column_semantics.py::VALID_SEMANTICS
 *
 * 与后端 `note_column_semantics.py` 的 25 项严格一致；后端引擎是真源，
 * 任何改动需同步两侧（CI 卡点 grep 同步性）。本文件仅给前端 UI 下拉列
 * 表使用，不参与值校验。
 */

export interface NoteColumnSemanticOption {
  /** semantic_id（后端枚举值） */
  value: string
  /** 中文显示名 */
  label: string
  /** 简短说明（hover tooltip 用） */
  description?: string
}

/**
 * 25 项标准列语义（顺序与后端 STANDARD_SEMANTICS keys 一致）.
 */
export const NOTE_COLUMN_SEMANTIC_OPTIONS: ReadonlyArray<NoteColumnSemanticOption> =
  Object.freeze([
    // 账龄分桶 5 桶
    { value: 'aging_bucket_within_1y', label: '1 年以内', description: '账龄分桶' },
    { value: 'aging_bucket_1_2y', label: '1-2 年', description: '账龄分桶' },
    { value: 'aging_bucket_2_3y', label: '2-3 年', description: '账龄分桶' },
    { value: 'aging_bucket_3_5y', label: '3-5 年', description: '账龄分桶' },
    { value: 'aging_bucket_over_5y', label: '5 年以上', description: '账龄分桶' },
    // 计提比例
    { value: 'provision_ratio', label: '计提比例', description: '减值/坏账计提比例' },
    // 本期计提
    { value: 'current_year_provision', label: '本期计提', description: '本期/本年计提坏账或减值' },
    // 本期增减
    { value: 'current_year_increase', label: '本期增加', description: '变动表父列' },
    { value: 'current_year_decrease', label: '本期减少', description: '变动表父列' },
    // 本期具体动作
    { value: 'current_period_acquisition', label: '本期购置', description: '具体动作子列' },
    { value: 'current_period_disposal', label: '本期处置', description: '具体动作子列' },
    { value: 'current_period_writeoff', label: '本期核销', description: '具体动作子列' },
    { value: 'current_period_recover', label: '本期收回', description: '具体动作子列' },
    // 期末/期初
    { value: 'closing_balance', label: '期末余额', description: '期末数 / 期末账面价值' },
    { value: 'opening_balance', label: '期初余额', description: '期初数 / 期初账面价值' },
    // 累计折旧 / 减值
    { value: 'accumulated_depreciation', label: '累计折旧/摊销/减值' },
    { value: 'impairment_provision', label: '减值准备' },
    // 原值 / 账面价值
    { value: 'original_value', label: '原值', description: '账面原值 / 资产原值' },
    { value: 'carrying_value', label: '账面价值', description: '净值（仅在期末/原值/累计未命中时）' },
    // 上年值
    { value: 'prior_year_value', label: '上年金额', description: '上年同期 / 上期数' },
    // 成本 / 公允价值
    { value: 'cost', label: '账面成本' },
    { value: 'fair_value', label: '公允价值' },
    // 小计
    { value: 'category_subtotal', label: '小计' },
    // 公式计算
    { value: 'formula_result', label: '公式计算', description: '"=" 前缀自动归类' },
    // 行标识列（默认兜底）
    { value: 'manual_text', label: '行标识列（项目/名称）', description: '默认兜底语义' },
  ])

/** 默认语义（与后端 DEFAULT_SEMANTIC 对齐） */
export const DEFAULT_NOTE_COLUMN_SEMANTIC = 'manual_text'

/** semantic_id 总数（CI 卡点：必须 = 25） */
export const NOTE_COLUMN_SEMANTIC_COUNT = NOTE_COLUMN_SEMANTIC_OPTIONS.length

if (NOTE_COLUMN_SEMANTIC_COUNT !== 25) {
  // 静态自检：避免漏同步后端 25 项
  // eslint-disable-next-line no-console
  console.error(
    '[noteColumnSemantics] expected 25 semantics, got',
    NOTE_COLUMN_SEMANTIC_COUNT,
  )
}
