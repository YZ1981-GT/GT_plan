/**
 * coordination/index.ts — 函证模块横切协同层入口
 *
 * 导出统一枚举 + 状态机 + UI Kit + 分发 + 舞弊收集 + 交互基线
 * 各 D0 组件统一从此处引入共享基础设施
 */

// 统一枚举字典
export {
  CONFIRMATION_DICTS,
  ALL_CONFIRMATION_DICT_KEYS,
  D01_DICT_KEYS,
  D02_DICT_KEYS,
  D03_DICT_KEYS,
  D04_DICT_KEYS,
  D04B_DICT_KEYS,
  D05_D06_DICT_KEYS,
  D07_DICT_KEYS,
  D08_DICT_KEYS,
  type ConfirmationDictKey,
} from './confirmationDicts'

// 共享 UI Kit
// 注：原 12 态状态机（useConfirmationStatus）+ 状态徽章（STATUS_BADGE_MAP/getStatusBadge）
// 已于 2026-07-17（G3）删除——零运行时消费者，真实 UI 用 match_status 3 态 / Hub 5 态。
export {
  formatAmount,
  GRID_PALETTE,
  SOURCE_INDICATOR_MAP,
  getSourceIndicator,
  WARN_LEVEL_COLORS,
  COVERAGE_THRESHOLDS,
  type AmountFormatOptions,
  type DataSource,
  type SourceIndicatorConfig,
} from './ConfirmationKit'

// D0-1 枢纽分发 — DEPRECATED: dispatch_records 机制从未被前端组件采用，
// 由 coordination/importFromSummary.ts 取代。保留 routeAlternative 纯函数供参考。
// useConfirmationDispatch 及相关类型已删除（2026-07-27 confirmation-linkage-completion R3）。

// 舞弊信号收集
export {
  useFraudSignalCollector,
  type FraudSignal,
  type FraudSignalSource,
  type FraudSignalType,
  type UseFraudSignalCollectorOptions,
} from './useFraudSignalCollector'

// 交互能力基线
export {
  INTERACTION_CAPABILITIES,
  FULL_BASELINE,
  CHECKLIST_BASELINE,
  COMPONENT_BASELINES,
  auditBaseline,
  auditAllBaselines,
  DEFAULT_KEYBOARD_NAV,
  READONLY_KEYBOARD_NAV,
  type InteractionCapability,
  type ComponentBaseline,
  type BaselineAuditResult,
  type KeyboardNavConfig,
} from './useInteractionBaseline'
