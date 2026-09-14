/**
 * 模式偏好的**统一 localStorage 键**与旧键幂等迁移。
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 32
 * Requirements: 11.1, 11.8 · Property 46（桥是唯一状态机，键也只能有一份）
 *
 * ═══ 为什么迁移要「扫描」而不是「按前缀清单」═══
 *
 * 存量里有 **50 余个** `const STORAGE_PREFIX = 'xx-dual-mode:'`（`f1/f2/f2-spe/f2-st/
 * f2-val/f3/f5/g1/g3/g4-main/g4-ecl/g4-sppi/g5/g6-main/g6-ecl/g6-sppi/g8…g14/
 * h1…h10/i1…i6/b60` 等），
 * 键形态只有两种：`{prefix}{wpId}` 与 `{prefix}{wpId}:{sheet}`。抄一份前缀清单进来，
 * 漏掉任何一个 = 那些底稿的存量偏好永远迁不过来，而「迁移函数被调用了」的判据全绿。
 * 所以这里按**键形态**扫描：真源是键的结构，不是一张会漂移的名单。
 *
 * ═══ 幂等的确切含义 ═══
 *
 * 第一次迁移：读旧键 → 归一化 → 写统一键 → **删旧键**（design §legacy migration
 * 「迁移后不再写旧 key」）。第二次迁移：找不到旧键，于是**不得**改写统一键 ——
 * 用户在两次之间手动切过模式，第二次迁移把它覆盖回旧值就是数据丢失。
 *
 * ═══ 「过期值不得打开不支持模式」═══
 *
 * AC 11.8 末句。capability 是 manifest 的 source-backed 事实：`single_html` 只支持
 * 表单侧、`single_onlyoffice` 只支持 OO 侧、`unreachable` 两侧都不支持。存量值落在
 * 不支持的那一侧时**回落到真实可用模式并删旧值**，绝不按存量值打开。
 */
import type { WorkpaperSyncCapability } from './workpaperSyncManifest.generated'
import { WorkpaperSyncContractError } from './workpaperSyncDto'

function refuse(code: string, message: string): never {
  throw new WorkpaperSyncContractError(code, message)
}

/** 桥的模式域（与 `workpaperSyncBridgeMachine` 的 `WorkpaperSyncBridgeMode` 同域）。 */
export type WorkpaperSyncStoredMode = 'html' | 'oo'

/** 统一键前缀。design §legacy migration 逐字给出的模板。 */
export const WP_SYNC_MODE_KEY_PREFIX = 'workpaper-sync-mode:'

/** 旧键形态：`{任意前缀}-dual-mode:{wp_id}[:{sheet}]`。 */
const LEGACY_KEY_RE = /^([a-z0-9][a-z0-9-]*)-dual-mode:(.+)$/

/**
 * 旧值枚举 → 统一模式。
 *
 * `structured` 是 B60 的表单侧拼写（`useB60DualMode` 的 `B60RenderMode`），
 * `html` 是其余全部 composable 的拼写；两者语义相同，统一键只保留一种拼写。
 */
const LEGACY_VALUE_MAP: Readonly<Record<string, WorkpaperSyncStoredMode>> = Object.freeze({
  html: 'html',
  structured: 'html',
  onlyoffice: 'oo',
  oo: 'oo',
})

/** capability → 真实可用模式集合（source-backed manifest 的封闭域）。 */
const CAPABILITY_MODES: Readonly<
  Record<WorkpaperSyncCapability, readonly WorkpaperSyncStoredMode[]>
> = Object.freeze({
  bidirectional: ['html', 'oo'],
  single_html: ['html'],
  single_onlyoffice: ['oo'],
  unreachable: [],
})

export interface WorkpaperSyncModeScope {
  readonly entryId: string
  readonly wpId: string
  /** 缺省 `default`，与存量 `useF2StocktakeDualMode` 的 `sheetCode || 'default'` 同拼写。 */
  readonly sheetKey?: string
}

/** 统一键。三段全部参与，缺一段即拒绝（AC 11.8 的「按 entry_id/wp_id/sheet」）。 */
export function workpaperSyncModeKey(scope: WorkpaperSyncModeScope): string {
  const entryId = String(scope.entryId ?? '').trim()
  const wpId = String(scope.wpId ?? '').trim()
  if (entryId === '' || wpId === '') {
    refuse(
      'mode_key_scope_incomplete',
      `统一模式键需要 entry_id 与 wp_id 全在，实得 entry=${JSON.stringify(entryId)} ` +
        `wp=${JSON.stringify(wpId)} —— 少一段就会与另一张 sheet/另一份底稿撞键`,
    )
  }
  const sheetKey = String(scope.sheetKey ?? '').trim() || 'default'
  return `${WP_SYNC_MODE_KEY_PREFIX}${entryId}:${wpId}:${sheetKey}`
}

export interface WorkpaperSyncModeMigration {
  /** 迁移后应当采用的模式（`null` = 没有任何可采用的持久化偏好）。 */
  readonly mode: WorkpaperSyncStoredMode | null
  /** 本次真正读到并消费掉的旧键（已删除）。 */
  readonly consumedLegacyKeys: readonly string[]
  /** 统一键在本次调用**之前**就已存在的值。 */
  readonly existingUnifiedMode: WorkpaperSyncStoredMode | null
  /** 因 capability 不支持而回落。 */
  readonly fallbackApplied: boolean
  /** 回落/丢弃的原因码（`null` = 未发生）。 */
  readonly fallbackReason: string | null
  /** 本次是否写了统一键。 */
  readonly wroteUnifiedKey: boolean
  /** localStorage 不可用（隐私模式 / SSR）。**不静默**，交给调用方决定可见性。 */
  readonly storageUnavailable: boolean
}

interface StorageLike {
  readonly length: number
  key(index: number): string | null
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

/**
 * `undefined` = 用平台 localStorage；**`null` = 显式声明「没有存储」**。
 *
 * 🔴 两者必须分开：`if (injected) return injected` 会把显式的 `null` 悄悄升级成全局
 * localStorage。宿主写 `storage: canPersist ? store : null` 时那就是一次 fail-open ——
 * 「不该持久化」被执行成「持久化到全局」，而任何「迁移函数被调用了」的判据全绿。
 */
function resolveStorage(injected?: StorageLike | null): StorageLike | null {
  if (injected !== undefined) return injected
  try {
    const candidate = globalThis.localStorage
    // 访问即可能抛（Safari 隐私模式）；能取到再做一次读写探针没有必要 ——
    // 后续每个操作各自受 try 保护，探针只会多写一个键。
    return candidate ? (candidate as unknown as StorageLike) : null
  } catch {
    return null
  }
}

/** 解析旧键；不符合形态返回 `null`（不是抛 —— localStorage 里全是别的业务键）。 */
export function parseLegacyModeKey(
  key: string,
): { readonly prefix: string; readonly wpId: string; readonly sheetKey: string } | null {
  const match = LEGACY_KEY_RE.exec(key)
  if (!match) return null
  const [wpId, ...rest] = match[2].split(':')
  if (!wpId) return null
  return {
    prefix: match[1],
    wpId,
    sheetKey: rest.length > 0 ? rest.join(':') : '',
  }
}

/**
 * 按 entry/wp/sheet 幂等迁移旧键，并按 capability 拦住不支持的存量值。
 *
 * 优先级：**per-sheet 旧键 > per-wp 旧键**（前者更精确）。两者都存在时两者都被消费，
 * 采用前者的值 —— 留着 per-wp 旧键会在下次迁移时又覆盖一遍统一键。
 */
export function migrateWorkpaperSyncMode(
  scope: WorkpaperSyncModeScope,
  capability: WorkpaperSyncCapability,
  options: { readonly storage?: StorageLike | null } = {},
): WorkpaperSyncModeMigration {
  const supported = CAPABILITY_MODES[capability]
  if (!supported) {
    refuse(
      'mode_capability_unknown',
      `capability ${JSON.stringify(capability)} 未登记可用模式 —— 新增 capability ` +
        '必须显式裁决，不得默认放行',
    )
  }
  const unifiedKey = workpaperSyncModeKey(scope)
  const storage = resolveStorage(options.storage)
  if (!storage) {
    return {
      mode: null,
      consumedLegacyKeys: [],
      existingUnifiedMode: null,
      fallbackApplied: false,
      fallbackReason: null,
      wroteUnifiedKey: false,
      storageUnavailable: true,
    }
  }

  const wpId = String(scope.wpId ?? '').trim()
  const sheetKey = String(scope.sheetKey ?? '').trim() || 'default'

  const existingRaw = storage.getItem(unifiedKey)
  const existingUnifiedMode =
    existingRaw !== null ? (LEGACY_VALUE_MAP[existingRaw] ?? null) : null

  // ── 扫描旧键（形态匹配，不靠前缀清单）
  const legacyKeys: string[] = []
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index)
    if (key === null) continue
    const parsed = parseLegacyModeKey(key)
    if (!parsed || parsed.wpId !== wpId) continue
    if (parsed.sheetKey !== '' && parsed.sheetKey !== sheetKey) continue
    legacyKeys.push(key)
  }
  // per-sheet 优先：sheet 段非空的排前面，其余按键名稳定排序。
  legacyKeys.sort((a, b) => {
    const sheetA = parseLegacyModeKey(a)?.sheetKey ? 0 : 1
    const sheetB = parseLegacyModeKey(b)?.sheetKey ? 0 : 1
    return sheetA - sheetB || a.localeCompare(b)
  })

  let legacyMode: WorkpaperSyncStoredMode | null = null
  let unknownLegacyValue = false
  const consumed: string[] = []
  for (const key of legacyKeys) {
    const raw = storage.getItem(key)
    consumed.push(key)
    storage.removeItem(key)
    if (raw === null) continue
    const mapped = LEGACY_VALUE_MAP[raw.trim()]
    if (mapped === undefined) {
      unknownLegacyValue = true
      continue
    }
    if (legacyMode === null) legacyMode = mapped
  }

  // ── 采用哪个值：本次消费到的旧值优先（它才是「读一次后转换」的对象）
  const candidate = legacyMode ?? existingUnifiedMode
  if (candidate === null) {
    return {
      mode: null,
      consumedLegacyKeys: consumed,
      existingUnifiedMode,
      fallbackApplied: false,
      fallbackReason: unknownLegacyValue ? 'legacy_value_unknown' : null,
      wroteUnifiedKey: false,
      storageUnavailable: false,
    }
  }

  if (supported.includes(candidate)) {
    // 🔴 只有「本次真的消费了旧键」才写统一键。否则第二次调用会把用户在两次之间
    // 手动切换的模式覆盖回旧值 —— 幂等的反面。
    const shouldWrite = legacyMode !== null && existingRaw !== candidate
    if (shouldWrite) storage.setItem(unifiedKey, candidate)
    return {
      mode: candidate,
      consumedLegacyKeys: consumed,
      existingUnifiedMode,
      fallbackApplied: false,
      fallbackReason: null,
      wroteUnifiedKey: shouldWrite,
      storageUnavailable: false,
    }
  }

  // ── capability 不支持存量值：回落真实可用模式并删旧值（旧值已在上面删掉）
  const fallback = supported[0] ?? null
  if (fallback === null) {
    // `unreachable`：两侧都不可用。此时**不写**统一键 —— 写进去等于宣称它可用。
    storage.removeItem(unifiedKey)
    return {
      mode: null,
      consumedLegacyKeys: consumed,
      existingUnifiedMode,
      fallbackApplied: true,
      fallbackReason: 'capability_unreachable',
      wroteUnifiedKey: false,
      storageUnavailable: false,
    }
  }
  storage.setItem(unifiedKey, fallback)
  return {
    mode: fallback,
    consumedLegacyKeys: consumed,
    existingUnifiedMode,
    fallbackApplied: true,
    fallbackReason: 'capability_does_not_support_stored_mode',
    wroteUnifiedKey: true,
    storageUnavailable: false,
  }
}

/** 写统一键（桥在用户显式切换后调用）。不支持的模式一律拒绝，不落盘。 */
export function persistWorkpaperSyncMode(
  scope: WorkpaperSyncModeScope,
  capability: WorkpaperSyncCapability,
  mode: WorkpaperSyncStoredMode,
  options: { readonly storage?: StorageLike | null } = {},
): boolean {
  const supported = CAPABILITY_MODES[capability]
  if (!supported) {
    refuse(
      'mode_capability_unknown_on_persist',
      `capability ${JSON.stringify(capability)} 未登记可用模式`,
    )
  }
  if (!supported.includes(mode)) {
    refuse(
      'mode_not_supported_by_capability',
      `capability=${capability} 不支持模式 ${mode} —— 持久化一个打不开的模式会在下次 ` +
        '加载时打开不支持的编辑器（AC 11.8 末句）',
    )
  }
  const storage = resolveStorage(options.storage)
  if (!storage) return false
  storage.setItem(workpaperSyncModeKey(scope), mode)
  return true
}

/** capability 支持的模式集合（判据与 UI 的模式开关共用同一真源）。 */
export function supportedModesForCapability(
  capability: WorkpaperSyncCapability,
): readonly WorkpaperSyncStoredMode[] {
  const supported = CAPABILITY_MODES[capability]
  if (!supported) {
    refuse(
      'mode_capability_unknown_on_query',
      `capability ${JSON.stringify(capability)} 未登记可用模式`,
    )
  }
  return supported
}
