import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { AMOUNT_UNITS, FONT_SIZES, fmtDateTime as formatDateTime, unitLabel, type AmountUnit, type FontSize } from '@/utils/formatters'
import { useProjectStore } from '@/stores/project'
import {
  DisplayPreferencesRevisionConflict,
  getDisplayPreferences,
  patchDisplayPreferences,
} from '@/services/displayPreferencesApi'
import { formatDisplayAmount, isFiniteDisplayAmount } from '@/utils/displayAmount'
import {
  DISPLAY_PREFERENCES_CACHE_PREFIX,
  DISPLAY_PREFERENCES_CACHE_TTL_MS,
  DISPLAY_PREFERENCES_LEGACY_KEY,
  DISPLAY_PREFERENCES_MAX_FIXED_PAGE_KEYS,
  cloneDisplayPreferences,
  createDefaultDisplayPreferences,
  fixedColumnsFitStorage,
  isValidDisplayPreferenceScalar,
  isValidFixedColumnsPageKey,
  normalizeDecimals,
  normalizeDisplayPreferenceScalar,
  normalizeDisplayPreferences,
  normalizeFixedColumnsColumns,
  type DisplayPreferenceScalar,
  type DisplayPreferencesPatch,
  type DisplayPreferencesState,
  type FixedColumnsConfig,
  type GridEditMode,
  type TableDensity,
} from '@/utils/displayPreferencesNormalizer'

export type { FixedColumnsConfig, GridEditMode, TableDensity }

export const TABLE_DENSITIES: Record<TableDensity, {
  label: string
  rowHeight: string
  padding: string
  elSize: 'small' | 'default' | 'large'
}> = {
  compact: { label: '紧凑', rowHeight: '32px', padding: '4px 8px', elSize: 'small' },
  default: { label: '标准', rowHeight: '40px', padding: '8px 12px', elSize: 'default' },
  comfortable: { label: '宽松', rowHeight: '48px', padding: '12px 16px', elSize: 'large' },
}

export const GRID_EDIT_MODES: Record<GridEditMode, { label: string; hint: string }> = {
  excel: { label: 'Excel', hint: '单击选中；双击、F2 或直接输入开始编辑；Enter / Tab 提交并移动，Esc 取消' },
  click: { label: '单击编辑', hint: '单击可编辑的格直接编辑；键盘与 Excel 方式相同' },
  classic: { label: '经典', hint: '单元格里的输入框一直显示，不启用表格选中与键盘' },
}

export type DisplayPreferencesLoadState = 'idle' | 'loading' | 'ready' | 'offline'
export type DisplayPreferencesSyncState = 'idle' | 'pending' | 'syncing' | 'offline' | 'conflict'

type FixedOperationInput =
  | { kind: 'upsert'; columns: string[]; savedAt: string }
  | { kind: 'delete' }

type FixedOperation = FixedOperationInput & { epoch: number }

type ScalarOperation = {
  epoch: number
  value: DisplayPreferencesState[DisplayPreferenceScalar]
}

interface PatchSnapshot {
  ownerUserId: string
  generation: number
  patch: DisplayPreferencesPatch
  scalars: Map<DisplayPreferenceScalar, ScalarOperation>
  fixed: Map<string, FixedOperation>
}

interface CachedDisplayPreferences {
  version: 3
  prefs: DisplayPreferencesState
  revision: number
  pendingScalars: Record<string, ScalarOperation>
  pendingFixedOps: Record<string, FixedOperation>
  cachedAt: number
}

const SCALAR_FIELDS: readonly DisplayPreferenceScalar[] = [
  'amountUnitOverride',
  'fontSize',
  'showZero',
  'decimals',
  'negativeRed',
  'highlightThreshold',
  'density',
  'gridEditMode',
]

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function own(record: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key)
}

function sameColumns(left: string[] | undefined, right: string[]): boolean {
  return !!left && left.length === right.length && left.every((value, index) => value === right[index])
}

function isSafeEpoch(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}

function isSafeCachedAt(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
}

function cacheKey(userId: string): string {
  return `${DISPLAY_PREFERENCES_CACHE_PREFIX}${userId}`
}

function browserStorage(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    return null
  }
}

function safeRemoveStorage(key: string): void {
  try {
    browserStorage()?.removeItem(key)
  } catch {
    // Safari 私密模式和受限 iframe 可能拒绝 Storage；显示偏好必须可降级。
  }
}

function parseCachedScalars(value: unknown): Map<DisplayPreferenceScalar, ScalarOperation> {
  const record = isRecord(value) ? value : {}
  const result = new Map<DisplayPreferenceScalar, ScalarOperation>()
  for (const key of SCALAR_FIELDS) {
    const raw = record[key]
    if (!isRecord(raw) || !isSafeEpoch(raw.epoch) || !own(raw, 'value')) continue
    if (!isValidDisplayPreferenceScalar(key, raw.value)) continue
    result.set(key, { epoch: raw.epoch, value: raw.value })
  }
  return result
}

function parseCachedFixedOperations(value: unknown): Map<string, FixedOperation> {
  const record = isRecord(value) ? value : {}
  const result = new Map<string, FixedOperation>()
  for (const [pageKey, raw] of Object.entries(record)) {
    if (!isValidFixedColumnsPageKey(pageKey) || !isRecord(raw) || !isSafeEpoch(raw.epoch)) continue
    if (raw.kind === 'delete') {
      result.set(pageKey, { epoch: raw.epoch, kind: 'delete' })
      continue
    }
    const columns = raw.kind === 'upsert' ? normalizeFixedColumnsColumns(raw.columns) : null
    const savedAt = raw.kind === 'upsert' && typeof raw.savedAt === 'string' && Number.isFinite(Date.parse(raw.savedAt))
      ? raw.savedAt
      : null
    if (columns && savedAt) result.set(pageKey, { epoch: raw.epoch, kind: 'upsert', columns, savedAt })
  }
  return result
}

function parseCache(userId: string): {
  prefs: DisplayPreferencesState
  scalars: Map<DisplayPreferenceScalar, ScalarOperation>
  fixed: Map<string, FixedOperation>
  maxEpoch: number
} | null {
  const storage = browserStorage()
  if (!storage) return null

  let raw: string | null
  try {
    raw = storage.getItem(cacheKey(userId))
  } catch {
    return null
  }
  if (!raw) return null

  try {
    const parsed = JSON.parse(raw) as unknown
    if (!isRecord(parsed) || parsed.version !== 3 || !isRecord(parsed.prefs) || !isSafeCachedAt(parsed.cachedAt)) {
      safeRemoveStorage(cacheKey(userId))
      return null
    }
    const age = Date.now() - parsed.cachedAt
    if (age < 0 || age > DISPLAY_PREFERENCES_CACHE_TTL_MS) {
      safeRemoveStorage(cacheKey(userId))
      return null
    }

    const prefs = normalizeDisplayPreferences(parsed.prefs)
    prefs.revision = typeof parsed.revision === 'number' && Number.isSafeInteger(parsed.revision) && parsed.revision >= 0
      ? parsed.revision
      : prefs.revision
    const scalars = parseCachedScalars(parsed.pendingScalars)
    const fixed = parseCachedFixedOperations(parsed.pendingFixedOps)
    const maxEpoch = Math.max(
      0,
      ...[...scalars.values(), ...fixed.values()].map((operation) => operation.epoch),
    )
    return { prefs, scalars, fixed, maxEpoch }
  } catch {
    safeRemoveStorage(cacheKey(userId))
    return null
  }
}

function buildFixedRequest(
  base: FixedColumnsConfig,
  operations: Map<string, FixedOperation>,
): Record<string, { columns: string[] }> {
  const result: Record<string, { columns: string[] }> = Object.fromEntries(
    Object.entries(base).map(([pageKey, entry]) => [pageKey, { columns: [...entry.columns] }]),
  )
  for (const [pageKey, operation] of operations) {
    if (operation.kind === 'delete') delete result[pageKey]
    else result[pageKey] = { columns: [...operation.columns] }
  }
  return result
}

function cloneOperation(operation: FixedOperation): FixedOperation {
  return operation.kind === 'delete'
    ? { epoch: operation.epoch, kind: 'delete' }
    : { epoch: operation.epoch, kind: 'upsert', columns: [...operation.columns], savedAt: operation.savedAt }
}

function requestWasCanceled(error: unknown): boolean {
  return (error as { code?: unknown })?.code === 'ERR_CANCELED'
}

export const useDisplayPrefsStore = defineStore('displayPrefs', () => {
  const projectStore = useProjectStore()
  const serverPreferences = ref<DisplayPreferencesState>(createDefaultDisplayPreferences())
  const visiblePreferences = ref<DisplayPreferencesState>(createDefaultDisplayPreferences())
  const ownerUserId = ref<string | null>(null)
  const loadState = ref<DisplayPreferencesLoadState>('idle')
  const syncState = ref<DisplayPreferencesSyncState>('idle')
  const syncMessage = ref<string | null>(null)
  const requestGeneration = ref(0)
  const pendingVersion = ref(0)

  const dirtyScalars = new Map<DisplayPreferenceScalar, ScalarOperation>()
  const dirtyFixedOperations = new Map<string, FixedOperation>()
  const mountedFixedPages = new Set<string>()
  let nextMutationEpoch = 0
  let flushTimer: ReturnType<typeof setTimeout> | null = null
  let loadController: AbortController | null = null
  let writeController: AbortController | null = null
  let inFlightFixedKeys = new Set<string>()

  function touchPending(): void {
    pendingVersion.value += 1
  }

  function clearFlushTimer(): void {
    if (flushTimer) clearTimeout(flushTimer)
    flushTimer = null
  }

  function isCurrentRequest(owner: string, generation: number): boolean {
    return ownerUserId.value === owner && requestGeneration.value === generation
  }

  function setVisibleFromServer(): void {
    const merged = cloneDisplayPreferences(serverPreferences.value)
    for (const [key, operation] of dirtyScalars) {
      merged[key] = operation.value as never
    }
    for (const [pageKey, operation] of dirtyFixedOperations) {
      if (operation.kind === 'delete') delete merged.fixedColumns[pageKey]
      else merged.fixedColumns[pageKey] = { columns: [...operation.columns], savedAt: operation.savedAt }
    }
    visiblePreferences.value = merged
  }

  function cacheCurrentState(): void {
    const userId = ownerUserId.value
    const storage = browserStorage()
    if (!userId || !storage) return

    const pendingScalars = Object.fromEntries(
      [...dirtyScalars.entries()].map(([key, operation]) => [key, { ...operation }]),
    )
    const pendingFixedOps = Object.fromEntries(
      [...dirtyFixedOperations.entries()].map(([key, operation]) => [key, cloneOperation(operation)]),
    )
    const payload: CachedDisplayPreferences = {
      version: 3,
      prefs: cloneDisplayPreferences(serverPreferences.value),
      revision: serverPreferences.value.revision,
      pendingScalars,
      pendingFixedOps,
      cachedAt: Date.now(),
    }
    try {
      storage.setItem(cacheKey(userId), JSON.stringify(payload))
    } catch {
      // 缓存只是非权威副本，配额或安全限制不应阻塞当前屏幕状态和服务端同步。
    }
  }

  function scheduleFlush(delay = 300): void {
    clearFlushTimer()
    if (!ownerUserId.value || !dirtyScalars.size && !dirtyFixedOperations.size) return
    syncState.value = 'pending'
    flushTimer = setTimeout(() => {
      flushTimer = null
      void flushPending()
    }, delay)
  }

  function snapshotFrom(
    owner: string,
    generation: number,
    scalars = new Map(dirtyScalars),
    fixed = new Map(dirtyFixedOperations),
  ): PatchSnapshot | null {
    if (!scalars.size && !fixed.size) return null
    const patch: DisplayPreferencesPatch = { baseRevision: serverPreferences.value.revision }
    for (const [key, operation] of scalars) patch[key] = operation.value as never
    if (fixed.size) patch.fixedColumns = buildFixedRequest(serverPreferences.value.fixedColumns, fixed)
    return {
      ownerUserId: owner,
      generation,
      patch,
      scalars: new Map([...scalars.entries()].map(([key, operation]) => [key, { ...operation }])),
      fixed: new Map([...fixed.entries()].map(([key, operation]) => [key, cloneOperation(operation)])),
    }
  }

  function pendingOriginalOperations(snapshot: PatchSnapshot): {
    scalars: Map<DisplayPreferenceScalar, ScalarOperation>
    fixed: Map<string, FixedOperation>
  } {
    const scalars = new Map<DisplayPreferenceScalar, ScalarOperation>()
    const fixed = new Map<string, FixedOperation>()
    for (const [key, sent] of snapshot.scalars) {
      const current = dirtyScalars.get(key)
      if (current?.epoch === sent.epoch) scalars.set(key, { ...sent })
    }
    for (const [pageKey, sent] of snapshot.fixed) {
      const current = dirtyFixedOperations.get(pageKey)
      if (current?.epoch === sent.epoch) fixed.set(pageKey, cloneOperation(sent))
    }
    return { scalars, fixed }
  }

  function discardConfirmedOperations(snapshot: PatchSnapshot): void {
    for (const [key, sent] of snapshot.scalars) {
      if (dirtyScalars.get(key)?.epoch === sent.epoch) dirtyScalars.delete(key)
    }
    for (const [pageKey, sent] of snapshot.fixed) {
      if (dirtyFixedOperations.get(pageKey)?.epoch === sent.epoch) dirtyFixedOperations.delete(pageKey)
    }
    touchPending()
  }

  function completeSuccessfulPatch(snapshot: PatchSnapshot, result: DisplayPreferencesState): void {
    if (!isCurrentRequest(snapshot.ownerUserId, snapshot.generation)) return
    serverPreferences.value = normalizeDisplayPreferences(result)
    discardConfirmedOperations(snapshot)
    setVisibleFromServer()
    syncMessage.value = null
    syncState.value = dirtyScalars.size || dirtyFixedOperations.size ? 'pending' : 'idle'
    cacheCurrentState()
    if (dirtyScalars.size || dirtyFixedOperations.size) scheduleFlush()
  }

  async function sendSnapshot(snapshot: PatchSnapshot, retryCount: number): Promise<void> {
    if (!isCurrentRequest(snapshot.ownerUserId, snapshot.generation)) return
    const controller = new AbortController()
    writeController = controller
    inFlightFixedKeys = new Set(snapshot.fixed.keys())
    syncState.value = 'syncing'

    try {
      const result = await patchDisplayPreferences(snapshot.patch, controller.signal)
      completeSuccessfulPatch(snapshot, result)
    } catch (error) {
      if (!isCurrentRequest(snapshot.ownerUserId, snapshot.generation) || requestWasCanceled(error)) return
      if (error instanceof DisplayPreferencesRevisionConflict) {
        serverPreferences.value = normalizeDisplayPreferences(error.current)
        const original = pendingOriginalOperations(snapshot)
        setVisibleFromServer()
        cacheCurrentState()
        if (retryCount === 0 && (original.scalars.size || original.fixed.size)) {
          const retry = snapshotFrom(snapshot.ownerUserId, snapshot.generation, original.scalars, original.fixed)
          if (retry) {
            await sendSnapshot(retry, 1)
            return
          }
        }
        if (retryCount === 0 && (dirtyScalars.size || dirtyFixedOperations.size)) {
          // 旧代际已无需要重放的项（全部 epoch 都被在途编辑前移）：冲突返回的 current
          // 就是新基底，更新后的 epoch 由下一代 PATCH 提交，不能停在 conflict 上等人工重试。
          syncMessage.value = null
          syncState.value = 'pending'
          scheduleFlush()
          return
        }
        syncState.value = 'conflict'
        syncMessage.value = '显示偏好版本冲突，仍有更改待同步'
        cacheCurrentState()
        return
      }
      syncState.value = 'offline'
      syncMessage.value = '显示偏好暂未同步，请在网络恢复后重试'
      cacheCurrentState()
    } finally {
      if (writeController === controller) writeController = null
      if (inFlightFixedKeys.size && writeController === null) inFlightFixedKeys = new Set()
    }
  }

  async function flushPending(): Promise<void> {
    if (writeController || !ownerUserId.value) return
    const snapshot = snapshotFrom(ownerUserId.value, requestGeneration.value)
    if (!snapshot) {
      syncState.value = 'idle'
      return
    }
    await sendSnapshot(snapshot, 0)
  }

  async function retryPending(): Promise<void> {
    if (!ownerUserId.value || !dirtyScalars.size && !dirtyFixedOperations.size) return
    syncMessage.value = null
    await flushPending()
  }

  function resetIdentityState(userId: string | null): void {
    requestGeneration.value += 1
    clearFlushTimer()
    loadController?.abort()
    writeController?.abort()
    loadController = null
    writeController = null
    inFlightFixedKeys = new Set()
    dirtyScalars.clear()
    dirtyFixedOperations.clear()
    mountedFixedPages.clear()
    touchPending()
    nextMutationEpoch = 0
    ownerUserId.value = userId
    serverPreferences.value = createDefaultDisplayPreferences()
    visiblePreferences.value = createDefaultDisplayPreferences()
    syncMessage.value = null
    syncState.value = 'idle'
  }

  /**
   * 绑定当前逻辑账号并异步取得服务端完整偏好。
   * 账号变化时先使旧请求、定时器和本机 mutation epoch 全部失效。
   */
  async function loadForUser(userId: string | null | undefined, options: { force?: boolean } = {}): Promise<void> {
    const normalizedUserId = typeof userId === 'string' && userId.length > 0 ? userId : null
    if (!options.force && normalizedUserId === ownerUserId.value) return

    resetIdentityState(normalizedUserId)
    safeRemoveStorage(DISPLAY_PREFERENCES_LEGACY_KEY)
    if (!normalizedUserId) {
      loadState.value = 'idle'
      return
    }

    const cached = parseCache(normalizedUserId)
    if (cached) {
      serverPreferences.value = cached.prefs
      dirtyScalars.clear()
      dirtyFixedOperations.clear()
      for (const [key, operation] of cached.scalars) dirtyScalars.set(key, { ...operation })
      for (const [pageKey, operation] of cached.fixed) dirtyFixedOperations.set(pageKey, cloneOperation(operation))
      touchPending()
      nextMutationEpoch = cached.maxEpoch
      setVisibleFromServer()
      syncState.value = dirtyScalars.size || dirtyFixedOperations.size ? 'pending' : 'idle'
    }

    const generation = requestGeneration.value
    const controller = new AbortController()
    loadController = controller
    loadState.value = 'loading'
    try {
      const result = await getDisplayPreferences(controller.signal)
      if (!isCurrentRequest(normalizedUserId, generation)) return
      const normalized = normalizeDisplayPreferences(result)
      if (normalized.revision >= serverPreferences.value.revision) {
        serverPreferences.value = normalized
      }
      setVisibleFromServer()
      loadState.value = 'ready'
      if (dirtyScalars.size || dirtyFixedOperations.size) scheduleFlush()
      cacheCurrentState()
    } catch (error) {
      if (!isCurrentRequest(normalizedUserId, generation) || requestWasCanceled(error)) return
      loadState.value = 'offline'
      syncState.value = dirtyScalars.size || dirtyFixedOperations.size ? 'pending' : 'offline'
      syncMessage.value = '显示偏好暂时无法加载，当前使用本机或默认设置'
      cacheCurrentState()
    } finally {
      if (loadController === controller) loadController = null
    }
  }

  function recordScalar<K extends DisplayPreferenceScalar>(key: K, value: unknown): void {
    const normalized = normalizeDisplayPreferenceScalar(key, value)
    // 本机设置入口的非法值一律忽略，不回落默认：回落会把用户当前的选择清掉
    // （spec excel-style-table-editing R1「非法值忽略」）。合法域只有归一函数一份，不另写判据。
    if (!Object.is(normalized, value)) {
      syncMessage.value = '显示设置的取值不在允许范围内，未改动'
      return
    }
    visiblePreferences.value = { ...visiblePreferences.value, [key]: normalized }
    if (!ownerUserId.value) return
    const epoch = ++nextMutationEpoch
    dirtyScalars.set(key, { epoch, value: normalized })
    touchPending()
    syncMessage.value = null
    cacheCurrentState()
    scheduleFlush()
  }

  function recordFixedOperation(pageKey: string, operation: FixedOperationInput): void {
    const epoch = ++nextMutationEpoch
    dirtyFixedOperations.set(pageKey, { ...operation, epoch })
    touchPending()
  }

  function findEvictionCandidate(excludedPageKey: string): string | null {
    const candidates = Object.entries(visiblePreferences.value.fixedColumns)
      .filter(([pageKey]) => (
        pageKey !== excludedPageKey
        && !mountedFixedPages.has(pageKey)
        && !inFlightFixedKeys.has(pageKey)
      ))
      .sort(([leftKey, left], [rightKey, right]) => {
        const delta = Date.parse(left.savedAt) - Date.parse(right.savedAt)
        return delta || leftKey.localeCompare(rightKey)
      })
    return candidates[0]?.[0] ?? null
  }

  function setFixedColumns(pageKey: string, columns: string[]): boolean {
    const normalizedColumns = normalizeFixedColumnsColumns(columns)
    if (!isValidFixedColumnsPageKey(pageKey) || !normalizedColumns) {
      syncMessage.value = '固定列设置不符合要求，未保存'
      return false
    }

    const existing = visiblePreferences.value.fixedColumns[pageKey]
    if (sameColumns(existing?.columns, normalizedColumns)) return true
    const evictionCandidate = !existing && Object.keys(visiblePreferences.value.fixedColumns).length >= DISPLAY_PREFERENCES_MAX_FIXED_PAGE_KEYS
      ? findEvictionCandidate(pageKey)
      : null
    if (!existing && Object.keys(visiblePreferences.value.fixedColumns).length >= DISPLAY_PREFERENCES_MAX_FIXED_PAGE_KEYS && !evictionCandidate) {
      syncMessage.value = '固定列设置已达 100 张表的上限，本次未保存'
      return false
    }

    const next = { ...visiblePreferences.value.fixedColumns }
    if (evictionCandidate) delete next[evictionCandidate]
    next[pageKey] = { columns: [...normalizedColumns], savedAt: new Date().toISOString() }
    if (!fixedColumnsFitStorage(next)) {
      syncMessage.value = '固定列设置超过存储限制，本次未保存'
      return false
    }
    visiblePreferences.value = { ...visiblePreferences.value, fixedColumns: next }
    // 到达上限后的淘汰必须让用户看见：被清掉的是别的表的设置，不能静默发生。
    const evictionNotice = evictionCandidate
      ? '已清除最久未修改的 1 张表的固定列设置'
      : null
    if (ownerUserId.value) {
      if (evictionCandidate) recordFixedOperation(evictionCandidate, { kind: 'delete' })
      recordFixedOperation(pageKey, {
        kind: 'upsert',
        columns: [...normalizedColumns],
        savedAt: next[pageKey].savedAt,
      })
      cacheCurrentState()
      scheduleFlush()
    }
    syncMessage.value = evictionNotice
    return true
  }

  function clearFixedColumns(pageKey: string): boolean {
    if (!isValidFixedColumnsPageKey(pageKey) || !visiblePreferences.value.fixedColumns[pageKey]) return false
    const next = { ...visiblePreferences.value.fixedColumns }
    delete next[pageKey]
    visiblePreferences.value = { ...visiblePreferences.value, fixedColumns: next }
    if (ownerUserId.value) {
      recordFixedOperation(pageKey, { kind: 'delete' })
      syncMessage.value = null
      cacheCurrentState()
      scheduleFlush()
    }
    return true
  }

  function setFixedPageMounted(pageKey: string, mounted: boolean): void {
    if (!isValidFixedColumnsPageKey(pageKey)) return
    if (mounted) mountedFixedPages.add(pageKey)
    else mountedFixedPages.delete(pageKey)
  }

  const amountUnitOverride = computed({
    get: () => visiblePreferences.value.amountUnitOverride,
    set: (value: AmountUnit | null) => recordScalar('amountUnitOverride', value),
  })
  const amountUnit = computed({
    get: () => amountUnitOverride.value ?? projectStore.projectAmountUnit ?? 'yuan',
    set: (value: AmountUnit) => recordScalar('amountUnitOverride', value),
  })
  const fontSize = computed({
    get: () => visiblePreferences.value.fontSize,
    set: (value: FontSize) => recordScalar('fontSize', value),
  })
  const showZero = computed({
    get: () => visiblePreferences.value.showZero,
    set: (value: boolean) => recordScalar('showZero', value),
  })
  const decimals = computed({
    get: () => visiblePreferences.value.decimals,
    set: (value: number) => recordScalar('decimals', value),
  })
  const negativeRed = computed({
    get: () => visiblePreferences.value.negativeRed,
    set: (value: boolean) => recordScalar('negativeRed', value),
  })
  const highlightThreshold = computed({
    get: () => visiblePreferences.value.highlightThreshold,
    set: (value: number) => recordScalar('highlightThreshold', value),
  })
  const density = computed({
    get: () => visiblePreferences.value.density,
    set: (value: TableDensity) => recordScalar('density', value),
  })
  const gridEditMode = computed({
    get: () => visiblePreferences.value.gridEditMode,
    set: (value: GridEditMode) => recordScalar('gridEditMode', value),
  })
  const fixedColumns = computed(() => visiblePreferences.value.fixedColumns)

  function setUnit(unit: AmountUnit): void { recordScalar('amountUnitOverride', unit) }
  function followProjectUnit(): void { recordScalar('amountUnitOverride', null) }
  function setFontSize(size: FontSize): void { recordScalar('fontSize', size) }
  function setShowZero(value: boolean): void { recordScalar('showZero', value) }
  function setDecimals(value: number): void { recordScalar('decimals', value) }
  function setNegativeRed(value: boolean): void { recordScalar('negativeRed', value) }
  function setHighlightThreshold(value: number): void { recordScalar('highlightThreshold', value) }
  function setDensity(value: TableDensity): void { recordScalar('density', value) }
  function setGridEditMode(value: GridEditMode): void { recordScalar('gridEditMode', value) }

  function getFixedColumns(pageKey: string): string[] {
    return visiblePreferences.value.fixedColumns[pageKey]?.columns.slice() ?? []
  }

  function fmt(value: unknown, options?: { rawUnit?: boolean }): string {
    return formatDisplayAmount(value, {
      amountUnit: amountUnit.value,
      decimals: decimals.value,
      showZero: showZero.value,
      rawUnit: options?.rawUnit,
    })
  }

  const fmtAmount = fmt

  function fmtPercent(value: unknown, digits = 1): string {
    if (!isFiniteDisplayAmount(value)) return '—'
    const safeDigits = normalizeDecimals(digits)
    const numeric = Number(value)
    return `${numeric.toFixed(safeDigits)}%`
  }

  function fmtDateTime(value: string | Date | null | undefined): string {
    return formatDateTime(value)
  }

  function amountClass(value: unknown, priorValue?: unknown): string {
    if (!isFiniteDisplayAmount(value)) return ''
    const current = Number(value)
    const classes: string[] = []
    if (negativeRed.value && current < 0) classes.push('gt-amount--negative')
    if (highlightThreshold.value > 0 && priorValue != null && isFiniteDisplayAmount(priorValue)) {
      const prior = Number(priorValue)
      if (prior === 0 ? current !== 0 : Math.abs((current - prior) / prior) >= highlightThreshold.value) {
        classes.push('gt-amount--highlight')
      }
    }
    return classes.join(' ')
  }

  const unitSuffix = computed(() => unitLabel(amountUnit.value))
  const unitDivisor = computed(() => AMOUNT_UNITS[amountUnit.value].divisor)
  const fontConfig = computed(() => FONT_SIZES[fontSize.value])
  const densityConfig = computed(() => TABLE_DENSITIES[density.value])
  const tableDensity = computed(() => TABLE_DENSITIES[density.value].elSize)
  const pendingPatch = computed(() => {
    void pendingVersion.value
    return {
      scalars: [...dirtyScalars.keys()],
      fixedPageKeys: [...dirtyFixedOperations.keys()],
    }
  })
  const hasPendingChanges = computed(() => {
    void pendingVersion.value
    return dirtyScalars.size > 0 || dirtyFixedOperations.size > 0
  })
  const unitOptions = Object.entries(AMOUNT_UNITS).map(([value, item]) => ({ value, label: item.label }))
  const fontOptions = Object.entries(FONT_SIZES).map(([value, item]) => ({ value, label: item.label }))
  const densityOptions = Object.entries(TABLE_DENSITIES).map(([value, item]) => ({ value, label: item.label }))
  const gridEditModeOptions = (Object.keys(GRID_EDIT_MODES) as GridEditMode[])
    .map((value) => ({ value, label: GRID_EDIT_MODES[value].label, hint: GRID_EDIT_MODES[value].hint }))

  return {
    amountUnitOverride,
    amountUnit,
    fontSize,
    showZero,
    decimals,
    negativeRed,
    highlightThreshold,
    density,
    gridEditMode,
    fixedColumns,
    serverPreferences,
    ownerUserId,
    loadState,
    syncState,
    syncMessage,
    requestGeneration,
    pendingPatch,
    hasPendingChanges,
    loadForUser,
    flushPending,
    retryPending,
    setUnit,
    followProjectUnit,
    setFontSize,
    setShowZero,
    setDecimals,
    setNegativeRed,
    setHighlightThreshold,
    setDensity,
    setGridEditMode,
    setFixedColumns,
    clearFixedColumns,
    getFixedColumns,
    setFixedPageMounted,
    fmt,
    fmtAmount,
    fmtPercent,
    fmtDateTime,
    amountClass,
    unitSuffix,
    unitDivisor,
    fontConfig,
    densityConfig,
    tableDensity,
    unitOptions,
    fontOptions,
    densityOptions,
    gridEditModeOptions,
  }
})
