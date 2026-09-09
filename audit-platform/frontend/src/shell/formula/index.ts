export {
  DOMAIN_OWNED_FORMULA_EXCLUSIONS,
  isDomainOwnedRelativePath,
  type DomainOwnedExclusion,
} from './domainExclusions'

export {
  registerHostAdapterTelemetry,
  unregisterHostAdapterTelemetry,
  resetHostAdapterTelemetry,
  listHostAdapterTelemetry,
  type HostAdapterTelemetryFact,
  type HostAdapterKind,
  type OutletSupport,
} from './hostAdapterTelemetry'

export {
  HOST_INVENTORY_VERSION,
  PRIMARY_OUTLET_SLOT,
  COMPATIBILITY_OUTLET_SLOT,
  GT_WP_TOOLBAR_RIGHT_CSS_CLASS,
  buildWorkpaperHostInventory,
  assertCssClassIsNotOutletCapability,
  type WorkpaperHostCapabilityRecord,
  type HostInventoryRun,
  type DuplicateCapabilityFinding,
  type BuildHostInventoryInput,
  type HostPolicyProjection,
  type RuntimeCustomInventoryEntry,
} from './workpaperHostInventory'

export {
  CAPABILITY_SNAPSHOT_VERSION,
  CAPABILITY_KEYS,
  assertCapabilityAllowed,
  denialLeaksSensitiveMetadata,
  type CapabilityKey,
  type CapabilityDecision,
  type WorkpaperCapabilitySnapshot,
  type CapabilityGateVerdict,
} from './workpaperCapabilitySnapshot'

export {
  GID_CONTRACT_ID,
  GID_CONTRACT_VERSION,
  buildStableSheetIdentity,
  assertGidSheetIdentity,
  type StableSheetIdentity,
} from './gidSheetIdentity'

export {
  createInitialLocationRuntime,
  reduceLocationFact,
  acceptAsyncLanding,
  readyLocationOf,
  type CanonicalLocationState,
  type HostLocationFact,
  type LocationReducerBag,
  type AsyncLandingTicket,
  type LocationBaseContext,
} from './canonicalLocationState'

export {
  ToolbarOutletArbiter,
  getToolbarOutletArbiter,
  resetToolbarOutletArbiter,
  type ToolbarOutletKind,
  type ToolbarOutletRegistration,
  type ToolbarPlacementState,
  type ToolbarHostAdapter,
} from './toolbarOutletArbiter'

export {
  OPEN_FORMULA_MANAGER_COMMAND_VERSION,
  createOpenFormulaManagerCommand,
  openSessionFromCommand,
  onLocationChangedWhileOpen,
  markSessionDirty,
  discardDraftAndFollowLatest,
  decideSaveDraft,
  resolvePageEntryTarget,
  legacyPayloadToPartialCommand,
  emptyStateForAggregate,
  type OpenFormulaManagerCommand,
  type FormulaManagerSession,
  type OpenFormulaManagerResult,
  type SaveDraftDecision,
} from './openFormulaManagerCommand'

export {
  FORMULA_TRUTH_SOURCE_MATRIX,
  FormulaProviderRegistry,
  createDefaultFormulaProviderRegistry,
  aggregateProviderResults,
  enrichAggregateWithLineage,
  semanticDigestOf,
  type FormulaDescriptor,
  type FormulaAggregateResult,
  type FormulaProviderAdapter,
  type FormulaOrigin,
  type FormulaRuleKind,
  type FormulaEngine,
  type FormulaProtection,
} from './formulaProviderRegistry'

export {
  HUMAN_REVIEW_KEY_VERSION,
  buildCanonicalReviewThreadKey,
  buildLegacyReviewThreadKey,
  parseLegacyReviewThreadKey,
  dryRunReviewKeyMigration,
  applyReviewKeyMigration,
  createHumanReviewProvider,
  type CanonicalReviewThreadKey,
  type HumanReviewAction,
  type HumanReviewProvider,
  type ReviewKeyMigrationReport,
} from './humanReviewProvider'

export {
  AI_ACTION_TAXONOMY_VERSION,
  AI_ACTION_DESCRIPTORS,
  assertAiReviewScope,
  assertAiAssistCarrier,
  assertTaxonomyA11yUnique,
  descriptorFor,
  type AiActionFamily,
  type AiActionDescriptor,
  type AiActionScope,
} from './aiActionTaxonomy'

export {
  USER_FORMULA_V2_COMMAND_VERSION,
  assertFunctionCategorySplit,
  type UserFormulaV2Command,
  type UserFormulaV2BatchResult,
  type UserFormulaV2Action,
} from './userFormulaV2'

export {
  SHELL_RAIL_ORDER,
  RightRailArbiter,
  getRightRailArbiter,
  resetRightRailArbiter,
  createReviewShellRail,
  createGuidanceShellRail,
  createAiAssistShellRail,
  type ShellRailId,
  type ShellRailAdapter,
  type RightRailLayoutSlot,
  type RailOpenState,
} from './rightRailArbiter'

export {
  SHELL_LAYOUT_TOKEN_VERSION,
  DEFAULT_SHELL_LAYOUT_TOKENS,
  shellLayoutCssVars,
  type ShellLayoutTokens,
} from './shellLayoutTokens'

export {
  SHELL_VIEWPORTS,
  classifyShellViewport,
  resolveShellLayoutTokens,
  assertShellLayoutNonOverlap,
  type ShellViewportWidth,
  type ShellViewportBand,
} from './shellResponsiveLayout'

export {
  SHELL_A11Y_NAMES,
  acquireShellScrollLock,
  releaseShellScrollLock,
  beginShellFocusSession,
  endShellFocusSession,
  handleShellEscapeKey,
  assertChineseAccessibleName,
  type ShellFocusable,
} from './shellA11y'

export {
  createShellStructuredError,
  toShellSafeLog,
  containsSensitiveShellPayload,
  assertNotBroadCatchSuccess,
  type ShellStructuredError,
  type ShellErrorDomain,
} from './shellStructuredError'

export {
  fetchWorkpaperCapabilitySnapshot,
  parseCapabilitySnapshotPayload,
  CAPABILITY_SNAPSHOT_PATH,
} from './fetchCapabilitySnapshot'

export {
  DSH_ASSIST_BRIDGE_KEY,
  WORKPAPER_SHELL_ACTIVE_KEY,
  type DshAssistBridge,
} from './dshAssistBridge'

export {
  scanFixedReviewRailSource,
  scanNodeKeyIdentityConsumer,
  scanAuditWarningThenCommit,
  scanBareAiMount,
  scanHardcodedCapabilityAvailability,
  type LegacyCleanupFinding,
} from './legacyCleanupScanners'

export {
  FSHELL_CONTRACT_ID,
  FSHELL_CONTRACT_VERSION,
  FSHELL_CONSUMERS,
  FSHELL_CAPABILITIES,
  FSHELL_NON_CAPABILITIES,
  buildFShellContractSnapshot,
  buildFShellEvidencePayload,
  assertFShellConsumerCompatible,
  type FShellContractSnapshot,
} from './fShellContract'

export {
  inspectGtWpToolbarOutlets,
  loadGtWpToolbarSource,
  scanDuplicateCapabilityFindings,
} from './hostInventoryScanners'

export {
  DENOMINATOR_HOSTS,
  runFullInventoryGate,
  buildT15EvidencePayload,
  type FullInventoryGateResult,
  type HostAdjudication,
  type DenominatorHost,
} from './fullInventoryGate'
