/**
 * s-checklist/ — S 类检查表型底稿内部子 sheet 组件
 *
 * S9（电子商务）和 S10（环境事项）等检查表型底稿使用 a-program-console
 * 作为顶层 componentType，但其附属 sheet（审定表/内控调查表/法规参考）
 * 需要专属组件提供更好的交互体验。
 *
 * 这些组件通过 GtWpRenderer 的 sheet tab 机制分发，
 * 或在未来作为 a-program-console 内部的 embedded sheet 渲染。
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 5.1, 5.2, 5.3
 */

// ─── S1 违反法规行为 ─────────────────────────────────────────────────────────
export { default as S1RegulationRecordSheet } from './S1RegulationRecordSheet.vue'

// ─── S8 租赁 ─────────────────────────────────────────────────────────────────
export { default as S8AdjudicationSheet } from './S8AdjudicationSheet.vue'

// ─── S9 电子商务 ─────────────────────────────────────────────────────────────
export { default as S9AdjudicationSheet } from './S9AdjudicationSheet.vue'
export { default as S9InternalControlSheet } from './S9InternalControlSheet.vue'
export { default as S9LegalRegulationsSheet } from './S9LegalRegulationsSheet.vue'
export { default as S9ProgramDescriptionSheet } from './S9ProgramDescriptionSheet.vue'

// ─── S10 环境事项 ────────────────────────────────────────────────────────────
export { default as S10AdjudicationSheet } from './S10AdjudicationSheet.vue'
export { default as S10InternalControlSheet } from './S10InternalControlSheet.vue'
export { default as S10EnvironmentalRegulationsSheet } from './S10EnvironmentalRegulationsSheet.vue'

// ─── S17 非经常性损益 ────────────────────────────────────────────────────────
export { default as S17NonRecurringDetailSheet } from './S17NonRecurringDetailSheet.vue'
export { default as S17ReconciliationSheet } from './S17ReconciliationSheet.vue'
export { default as S17TaxImpactSheet } from './S17TaxImpactSheet.vue'
