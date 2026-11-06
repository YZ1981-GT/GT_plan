import type { AmountUnit, FontSize } from '@/utils/formatters'

export const DISPLAY_PREFERENCES_CACHE_PREFIX = 'gt_display_prefs:v3:'
export const DISPLAY_PREFERENCES_LEGACY_KEY = 'gt_display_prefs'
export const DISPLAY_PREFERENCES_CACHE_TTL_MS = 30 * 24 * 60 * 60 * 1000
export const DISPLAY_PREFERENCES_MAX_FIXED_PAGE_KEYS = 100
export const DISPLAY_PREFERENCES_MAX_FIXED_COLUMNS_PER_PAGE = 20
export const DISPLAY_PREFERENCES_MAX_FIXED_STORAGE_BYTES = 64 * 1024

export type TableDensity = 'compact' | 'default' | 'comfortable'
export type GridEditMode = 'excel' | 'click' | 'classic'

export interface FixedColumnsEntry {
  columns: string[]
  savedAt: string
}

export type FixedColumnsConfig = Record<string, FixedColumnsEntry>

export interface DisplayPreferencesState {
  amountUnitOverride: AmountUnit | null
  fontSize: FontSize
  showZero: boolean
  decimals: number
  negativeRed: boolean
  highlightThreshold: number
  density: TableDensity
  gridEditMode: GridEditMode
  fixedColumns: FixedColumnsConfig
  revision: number
  updatedAt: string | null
}

export type DisplayPreferenceScalar = Exclude<
  keyof DisplayPreferencesState,
  'fixedColumns' | 'revision' | 'updatedAt'
>

export type DisplayPreferencesPatch = {
  baseRevision: number
} & Partial<Pick<DisplayPreferencesState, DisplayPreferenceScalar>> & {
  fixedColumns?: Record<string, { columns: string[] }>
}

const DEFAULTS: Omit<DisplayPreferencesState, 'fixedColumns'> = {
  amountUnitOverride: null,
  fontSize: 'sm',
  showZero: false,
  decimals: 2,
  negativeRed: true,
  highlightThreshold: 0.2,
  density: 'default',
  gridEditMode: 'excel',
  revision: 0,
  updatedAt: null,
}

const AMOUNT_UNITS: readonly AmountUnit[] = ['yuan', 'qian', 'wan']
const FONT_SIZES: readonly FontSize[] = ['xs', 'sm', 'md', 'lg']
const TABLE_DENSITIES: readonly TableDensity[] = ['compact', 'default', 'comfortable']
const GRID_EDIT_MODES: readonly GridEditMode[] = ['excel', 'click', 'classic']

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function hasOwn(record: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key)
}

function fieldValue(record: Record<string, unknown>, camel: string, snake: string): unknown {
  if (hasOwn(record, camel)) return record[camel]
  return record[snake]
}

function hasField(record: Record<string, unknown>, camel: string, snake: string): boolean {
  return hasOwn(record, camel) || hasOwn(record, snake)
}

function isOneOf<T extends string>(value: unknown, values: readonly T[]): value is T {
  return typeof value === 'string' && (values as readonly string[]).includes(value)
}

export function isAmountUnit(value: unknown): value is AmountUnit {
  return isOneOf(value, AMOUNT_UNITS)
}

export function isFontSize(value: unknown): value is FontSize {
  return isOneOf(value, FONT_SIZES)
}

export function isTableDensity(value: unknown): value is TableDensity {
  return isOneOf(value, TABLE_DENSITIES)
}

export function isGridEditMode(value: unknown): value is GridEditMode {
  return isOneOf(value, GRID_EDIT_MODES)
}

export function createDefaultDisplayPreferences(): DisplayPreferencesState {
  return { ...DEFAULTS, fixedColumns: {} }
}

export function normalizeDecimals(value: unknown): number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 6
    ? value
    : DEFAULTS.decimals
}

function normalizeThreshold(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 1) {
    return DEFAULTS.highlightThreshold
  }
  const text = String(value)
  const decimalPart = text.includes('.') ? text.split('.')[1] : ''
  if (decimalPart.length > 4 || /e/i.test(text)) return DEFAULTS.highlightThreshold
  return value
}

function normalizeTimestamp(value: unknown): string | null {
  if (typeof value !== 'string' || !value || !Number.isFinite(Date.parse(value))) return null
  return value
}

export function isValidFixedColumnsPageKey(value: unknown): value is string {
  return typeof value === 'string' && value.length >= 1 && value.length <= 100
}

export function normalizeFixedColumnsColumns(value: unknown): string[] | null {
  if (!Array.isArray(value) || value.length > DISPLAY_PREFERENCES_MAX_FIXED_COLUMNS_PER_PAGE) return null
  if (value.some((column) => typeof column !== 'string' || column.length < 1 || column.length > 100)) return null
  if (new Set(value).size !== value.length) return null
  return [...value]
}

function normalizeFixedColumnsEntry(value: unknown): FixedColumnsEntry | null {
  const record = asRecord(value)
  if (!record) return null
  const columns = normalizeFixedColumnsColumns(record.columns)
  const savedAt = normalizeTimestamp(fieldValue(record, 'savedAt', 'saved_at'))
  if (!columns || !savedAt) return null
  return { columns, savedAt }
}

export function fixedColumnsStorageSize(value: FixedColumnsConfig | Record<string, { columns: string[] }>): number {
  const entries: Record<string, { columns: string[]; saved_at: string }> = {}
  for (const [pageKey, entry] of Object.entries(value)) {
    entries[pageKey] = {
      columns: [...entry.columns],
      saved_at: '9999-12-31T23:59:59.999999+00:00',
    }
  }
  const json = JSON.stringify(entries)
  if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(json).byteLength
  return typeof Blob !== 'undefined' ? new Blob([json]).size : json.length
}

export function fixedColumnsFitStorage(value: FixedColumnsConfig | Record<string, { columns: string[] }>): boolean {
  return fixedColumnsStorageSize(value) <= DISPLAY_PREFERENCES_MAX_FIXED_STORAGE_BYTES
}

export function normalizeFixedColumns(value: unknown): FixedColumnsConfig {
  const record = asRecord(value)
  if (!record) return {}

  const normalized: FixedColumnsConfig = {}
  for (const pageKey of Object.keys(record).sort()) {
    if (Object.keys(normalized).length >= DISPLAY_PREFERENCES_MAX_FIXED_PAGE_KEYS) break
    if (!isValidFixedColumnsPageKey(pageKey)) continue
    const entry = normalizeFixedColumnsEntry(record[pageKey])
    if (entry) normalized[pageKey] = entry
  }
  return fixedColumnsFitStorage(normalized) ? normalized : {}
}

function normalizeRevision(value: unknown): number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
    ? value
    : DEFAULTS.revision
}

/**
 * 将 API 响应或本地缓存逐字段归一为安全的前端状态。
 * 无效字段只回落自身默认值，避免一处损坏阻塞登录或触发 RangeError。
 */
export function normalizeDisplayPreferences(value: unknown): DisplayPreferencesState {
  const record = asRecord(value)
  if (!record) return createDefaultDisplayPreferences()

  const defaults = createDefaultDisplayPreferences()
  const amountUnitOverride = fieldValue(record, 'amountUnitOverride', 'amount_unit_override')
  const fontSize = fieldValue(record, 'fontSize', 'font_size')
  const showZero = fieldValue(record, 'showZero', 'show_zero')
  const decimals = fieldValue(record, 'decimals', 'decimals')
  const negativeRed = fieldValue(record, 'negativeRed', 'negative_red')
  const highlightThreshold = fieldValue(record, 'highlightThreshold', 'highlight_threshold')
  const density = fieldValue(record, 'density', 'density')
  const gridEditMode = fieldValue(record, 'gridEditMode', 'grid_edit_mode')
  const fixedColumns = fieldValue(record, 'fixedColumns', 'fixed_columns')
  const revision = fieldValue(record, 'revision', 'revision')
  const updatedAt = fieldValue(record, 'updatedAt', 'updated_at')

  return {
    amountUnitOverride: amountUnitOverride === null || isAmountUnit(amountUnitOverride)
      ? amountUnitOverride
      : defaults.amountUnitOverride,
    fontSize: isFontSize(fontSize) ? fontSize : defaults.fontSize,
    showZero: typeof showZero === 'boolean' ? showZero : defaults.showZero,
    decimals: normalizeDecimals(decimals),
    negativeRed: typeof negativeRed === 'boolean' ? negativeRed : defaults.negativeRed,
    highlightThreshold: normalizeThreshold(highlightThreshold),
    density: isTableDensity(density) ? density : defaults.density,
    gridEditMode: isGridEditMode(gridEditMode) ? gridEditMode : defaults.gridEditMode,
    fixedColumns: normalizeFixedColumns(fixedColumns),
    revision: normalizeRevision(revision),
    updatedAt: normalizeTimestamp(updatedAt),
  }
}

export function isValidDisplayPreferenceScalar<K extends DisplayPreferenceScalar>(
  key: K,
  value: unknown,
): value is DisplayPreferencesState[K] {
  switch (key) {
    case 'amountUnitOverride':
      return value === null || isAmountUnit(value)
    case 'fontSize':
      return isFontSize(value)
    case 'showZero':
    case 'negativeRed':
      return typeof value === 'boolean'
    case 'decimals':
      return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 6
    case 'highlightThreshold':
      return typeof value === 'number' && normalizeThreshold(value) === value
    case 'density':
      return isTableDensity(value)
    case 'gridEditMode':
      return isGridEditMode(value)
  }
  return false
}

/** 将一个运行时值归一到指定偏好字段的安全范围。 */
export function normalizeDisplayPreferenceScalar<K extends DisplayPreferenceScalar>(
  key: K,
  value: unknown,
): DisplayPreferencesState[K] {
  const defaults = createDefaultDisplayPreferences()
  switch (key) {
    case 'amountUnitOverride':
      return (value === null || isAmountUnit(value) ? value : defaults.amountUnitOverride) as DisplayPreferencesState[K]
    case 'fontSize':
      return (isFontSize(value) ? value : defaults.fontSize) as DisplayPreferencesState[K]
    case 'showZero':
      return (typeof value === 'boolean' ? value : defaults.showZero) as DisplayPreferencesState[K]
    case 'decimals':
      return normalizeDecimals(value) as DisplayPreferencesState[K]
    case 'negativeRed':
      return (typeof value === 'boolean' ? value : defaults.negativeRed) as DisplayPreferencesState[K]
    case 'highlightThreshold':
      return normalizeThreshold(value) as DisplayPreferencesState[K]
    case 'density':
      return (isTableDensity(value) ? value : defaults.density) as DisplayPreferencesState[K]
    case 'gridEditMode':
      return (isGridEditMode(value) ? value : defaults.gridEditMode) as DisplayPreferencesState[K]
  }
  return defaults[key] as DisplayPreferencesState[K]
}

export function cloneDisplayPreferences(value: DisplayPreferencesState): DisplayPreferencesState {
  return {
    ...value,
    fixedColumns: Object.fromEntries(
      Object.entries(value.fixedColumns).map(([pageKey, entry]) => [
        pageKey,
        { columns: [...entry.columns], savedAt: entry.savedAt },
      ]),
    ),
  }
}

export function toDisplayPreferencesPatchWire(patch: DisplayPreferencesPatch): Record<string, unknown> {
  const wire: Record<string, unknown> = { base_revision: patch.baseRevision }
  const fields: Array<[DisplayPreferenceScalar, string]> = [
    ['amountUnitOverride', 'amount_unit_override'],
    ['fontSize', 'font_size'],
    ['showZero', 'show_zero'],
    ['decimals', 'decimals'],
    ['negativeRed', 'negative_red'],
    ['highlightThreshold', 'highlight_threshold'],
    ['density', 'density'],
    ['gridEditMode', 'grid_edit_mode'],
  ]
  for (const [local, remote] of fields) {
    if (hasOwn(patch as Record<string, unknown>, local)) wire[remote] = patch[local]
  }
  if (hasOwn(patch as Record<string, unknown>, 'fixedColumns')) {
    wire.fixed_columns = patch.fixedColumns
  }
  return wire
}

export function hasPatchField(patch: DisplayPreferencesPatch, key: keyof DisplayPreferencesPatch): boolean {
  return hasOwn(patch as Record<string, unknown>, key)
}

export function hasDisplayPreferenceField(value: unknown, camel: string, snake: string): boolean {
  const record = asRecord(value)
  return !!record && hasField(record, camel, snake)
}
