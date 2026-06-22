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

// 状态机
export {
  CONFIRMATION_STATUSES,
  TRANSITION_TABLE,
  canTransition,
  transition,
  availableEvents,
  useConfirmationStatus,
  type ConfirmationStatus,
  type StatusEvent,
  type Transition,
  type StatusRecord,
  type StatusDistribution,
  type UseConfirmationStatusOptions,
} from './useConfirmationStatus'

// 共享 UI Kit
export {
  STATUS_BADGE_MAP,
  getStatusBadge,
  formatAmount,
  GRID_PALETTE,
  SOURCE_INDICATOR_MAP,
  getSourceIndicator,
  WARN_LEVEL_COLORS,
  COVERAGE_THRESHOLDS,
  type StatusBadgeConfig,
  type StatusColorLevel,
  type AmountFormatOptions,
  type DataSource,
  type SourceIndicatorConfig,
} from './ConfirmationKit'

// D0-1 枢纽分发
export {
  useConfirmationDispatch,
  routeAlternative,
  type DispatchTarget,
  type DispatchEntry,
  type DispatchResult,
  type UseConfirmationDispatchOptions,
} from './useConfirmationDispatch'

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
