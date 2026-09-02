// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 32
//
// 统一 localStorage 键 + 旧键幂等迁移 + capability 回落。
//
// Validates: Requirements 11.1, 11.8
//
// ═══ 判据设计 ═══
//
// * 幂等的判据是「**跑两次的存储快照逐键相同**，且第二次不改用户在两次之间的手动值」，
//   不是「函数返回同一个值」——后者在「每次都覆盖成旧值」的实现下也全绿。
// * 前缀清单不写死：判据用真实源码里发现的 `*-dual-mode:` 前缀构造旧键，
//   于是「把扫描收窄成一张名单」这类变异会打红。
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'

import {
  WP_SYNC_MODE_KEY_PREFIX,
  migrateWorkpaperSyncMode,
  parseLegacyModeKey,
  persistWorkpaperSyncMode,
  supportedModesForCapability,
  workpaperSyncModeKey,
} from '../workpaperSyncModeStorage'
import { WorkpaperSyncContractError } from '../workpaperSyncDto'

const WP_ID = '11111111-1111-1111-1111-111111111111'
const ENTRY_ID = 'xlsx/d4/analysis/d4-tab-customer-price'

/** 内存 storage：`length`/`key(i)` 都要真实，否则扫描判据形同虚设。 */
class MemoryStorage {
  private readonly map = new Map<string, string>()

  get length(): number {
    return this.map.size
  }

  key(index: number): string | null {
    return [...this.map.keys()][index] ?? null
  }

  getItem(key: string): string | null {
    return this.map.has(key) ? (this.map.get(key) as string) : null
  }

  setItem(key: string, value: string): void {
    this.map.set(key, value)
  }

  removeItem(key: string): void {
    this.map.delete(key)
  }

  snapshot(): Record<string, string> {
    return Object.fromEntries([...this.map.entries()].sort())
  }
}

function expectRefusal(fn: () => unknown, code: string): void {
  let caught: unknown
  try {
    fn()
  } catch (error) {
    caught = error
  }
  expect(caught, `期望拒绝 code=${code}`).toBeInstanceOf(WorkpaperSyncContractError)
  expect((caught as WorkpaperSyncContractError).code).toBe(code)
}

const SCOPE = { entryId: ENTRY_ID, wpId: WP_ID, sheetKey: 'D4-1' }

// ═══════════════════════════════════════════════════════════════════════════
// A. 统一键
// ═══════════════════════════════════════════════════════════════════════════

describe('统一键按 entry/wp/sheet', () => {
  it('三段全部出现，缺段即拒', () => {
    expect(workpaperSyncModeKey(SCOPE)).toBe(
      `${WP_SYNC_MODE_KEY_PREFIX}${ENTRY_ID}:${WP_ID}:D4-1`,
    )
    expectRefusal(
      () => workpaperSyncModeKey({ entryId: '', wpId: WP_ID }),
      'mode_key_scope_incomplete',
    )
    expectRefusal(
      () => workpaperSyncModeKey({ entryId: ENTRY_ID, wpId: '  ' }),
      'mode_key_scope_incomplete',
    )
  })

  it('同 wp 不同 sheet / 同 sheet 不同 entry 都不撞键', () => {
    const a = workpaperSyncModeKey({ entryId: ENTRY_ID, wpId: WP_ID, sheetKey: 'D4-1' })
    const b = workpaperSyncModeKey({ entryId: ENTRY_ID, wpId: WP_ID, sheetKey: 'D4-2' })
    const c = workpaperSyncModeKey({ entryId: 'xlsx/other', wpId: WP_ID, sheetKey: 'D4-1' })
    expect(new Set([a, b, c]).size).toBe(3)
  })

  it('缺 sheet 时落到 default（与存量 `sheetCode || default` 同拼写）', () => {
    expect(workpaperSyncModeKey({ entryId: ENTRY_ID, wpId: WP_ID })).toBe(
      `${WP_SYNC_MODE_KEY_PREFIX}${ENTRY_ID}:${WP_ID}:default`,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// B. 旧键形态覆盖真实源码
// ═══════════════════════════════════════════════════════════════════════════

/** 递归扫源码，收集 `const STORAGE_PREFIX = 'xxx-dual-mode:'` 的真实前缀。 */
function discoverLegacyPrefixes(): string[] {
  const srcRoot = resolve(dirname(new URL(import.meta.url).pathname.replace(/^\//, '')), '../../../..')
  const found = new Set<string>()
  const re = /STORAGE_PREFIX\s*=\s*'([a-z0-9][a-z0-9-]*-dual-mode:)'/g
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir)) {
      if (name === 'node_modules' || name === '__tests__') continue
      const full = join(dir, name)
      const stat = statSync(full)
      if (stat.isDirectory()) {
        walk(full)
        continue
      }
      if (!name.endsWith('.ts') && !name.endsWith('.vue')) continue
      const body = readFileSync(full, 'utf-8')
      for (const match of body.matchAll(re)) found.add(match[1])
    }
  }
  walk(srcRoot)
  return [...found].sort()
}

describe('旧键形态覆盖存量全部前缀', () => {
  it('源码里真实存在的 *-dual-mode: 前缀足够多（分母非空）', () => {
    const prefixes = discoverLegacyPrefixes()
    expect(prefixes.length).toBeGreaterThan(30)
  })

  it('每个真实前缀构造的 per-wp 与 per-sheet 旧键都能被解析', () => {
    const prefixes = discoverLegacyPrefixes()
    for (const prefix of prefixes) {
      const perWp = parseLegacyModeKey(`${prefix}${WP_ID}`)
      expect(perWp, prefix).not.toBeNull()
      expect(perWp?.wpId, prefix).toBe(WP_ID)
      expect(perWp?.sheetKey, prefix).toBe('')
      const perSheet = parseLegacyModeKey(`${prefix}${WP_ID}:D4-1`)
      expect(perSheet?.wpId, prefix).toBe(WP_ID)
      expect(perSheet?.sheetKey, prefix).toBe('D4-1')
    }
  })

  it('非旧键形态返回 null（localStorage 里全是别的业务键）', () => {
    expect(parseLegacyModeKey('gt_wp_view_preset_user-1')).toBeNull()
    expect(parseLegacyModeKey('E1-cash-count-rmb-rows')).toBeNull()
    expect(parseLegacyModeKey(`${WP_SYNC_MODE_KEY_PREFIX}a:b:c`)).toBeNull()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// C. 迁移与幂等
// ═══════════════════════════════════════════════════════════════════════════

describe('旧键 → 统一键幂等迁移', () => {
  it('per-wp 旧枚举 onlyoffice 迁成统一键的 oo，并删除旧键', () => {
    const storage = new MemoryStorage()
    storage.setItem(`h4-dual-mode:${WP_ID}`, 'onlyoffice')
    const result = migrateWorkpaperSyncMode(SCOPE, 'bidirectional', { storage })
    expect(result.mode).toBe('oo')
    expect(result.consumedLegacyKeys).toEqual([`h4-dual-mode:${WP_ID}`])
    expect(result.wroteUnifiedKey).toBe(true)
    expect(storage.snapshot()).toEqual({ [workpaperSyncModeKey(SCOPE)]: 'oo' })
  })

  it('B60 的 structured 旧枚举归一成 html（一种拼写）', () => {
    const storage = new MemoryStorage()
    storage.setItem(`b60-dual-mode:${WP_ID}`, 'structured')
    const result = migrateWorkpaperSyncMode(SCOPE, 'bidirectional', { storage })
    expect(result.mode).toBe('html')
    expect(storage.getItem(workpaperSyncModeKey(SCOPE))).toBe('html')
  })

  it('per-sheet 旧键优先于 per-wp，且两者都被删掉', () => {
    const storage = new MemoryStorage()
    storage.setItem(`f2-st-dual-mode:${WP_ID}`, 'html')
    storage.setItem(`f2-st-dual-mode:${WP_ID}:D4-1`, 'onlyoffice')
    const result = migrateWorkpaperSyncMode(SCOPE, 'bidirectional', { storage })
    expect(result.mode).toBe('oo')
    expect([...result.consumedLegacyKeys].sort()).toEqual(
      [`f2-st-dual-mode:${WP_ID}`, `f2-st-dual-mode:${WP_ID}:D4-1`].sort(),
    )
    expect(storage.snapshot()).toEqual({ [workpaperSyncModeKey(SCOPE)]: 'oo' })
  })

  it('别的 wp / 别的 sheet 的旧键一个都不动', () => {
    const storage = new MemoryStorage()
    const otherWp = '22222222-2222-2222-2222-222222222222'
    storage.setItem(`h4-dual-mode:${otherWp}`, 'onlyoffice')
    storage.setItem(`h4-dual-mode:${WP_ID}:OTHER-SHEET`, 'onlyoffice')
    const result = migrateWorkpaperSyncMode(SCOPE, 'bidirectional', { storage })
    expect(result.consumedLegacyKeys).toEqual([])
    expect(result.mode).toBeNull()
    expect(storage.snapshot()).toEqual({
      [`h4-dual-mode:${otherWp}`]: 'onlyoffice',
      [`h4-dual-mode:${WP_ID}:OTHER-SHEET`]: 'onlyoffice',
    })
  })

  it('跑两次：第二次的存储快照逐键相同（幂等）', () => {
    const storage = new MemoryStorage()
    storage.setItem(`g5-dual-mode:${WP_ID}`, 'onlyoffice')
    migrateWorkpaperSyncMode(SCOPE, 'bidirectional', { storage })
    const afterFirst = storage.snapshot()
    const second = migrateWorkpaperSyncMode(SCOPE, 'bidirectional', { storage })
    expect(storage.snapshot()).toEqual(afterFirst)
    expect(second.consumedLegacyKeys).toEqual([])
    expect(second.wroteUnifiedKey).toBe(false)
  })

  it('用户在两次迁移之间手动改过模式 ⇒ 第二次不得覆盖回旧值', () => {
    const storage = new MemoryStorage()
    storage.setItem(`g5-dual-mode:${WP_ID}`, 'onlyoffice')
    expect(migrateWorkpaperSyncMode(SCOPE, 'bidirectional', { storage }).mode).toBe('oo')
    persistWorkpaperSyncMode(SCOPE, 'bidirectional', 'html', { storage })
    const second = migrateWorkpaperSyncMode(SCOPE, 'bidirectional', { storage })
    expect(second.mode).toBe('html')
    expect(second.wroteUnifiedKey).toBe(false)
    expect(storage.getItem(workpaperSyncModeKey(SCOPE))).toBe('html')
  })

  it('旧键值是未知枚举 ⇒ 不采用、旧键仍删除、原因可诊断', () => {
    const storage = new MemoryStorage()
    storage.setItem(`g5-dual-mode:${WP_ID}`, 'univer')
    const result = migrateWorkpaperSyncMode(SCOPE, 'bidirectional', { storage })
    expect(result.mode).toBeNull()
    expect(result.fallbackReason).toBe('legacy_value_unknown')
    expect(storage.snapshot()).toEqual({})
  })

  it('localStorage 不可用时显式上报，不静默当成「没有偏好」', () => {
    const result = migrateWorkpaperSyncMode(SCOPE, 'bidirectional', { storage: null })
    expect(result.storageUnavailable).toBe(true)
    expect(result.mode).toBeNull()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// D. capability 回落（AC 11.8 末句）
// ═══════════════════════════════════════════════════════════════════════════

describe('过期值不得打开不支持模式', () => {
  it('single_html 遇到存量 oo ⇒ 回落 html 并删旧值', () => {
    const storage = new MemoryStorage()
    storage.setItem(`h4-dual-mode:${WP_ID}`, 'onlyoffice')
    const result = migrateWorkpaperSyncMode(SCOPE, 'single_html', { storage })
    expect(result.mode).toBe('html')
    expect(result.fallbackApplied).toBe(true)
    expect(result.fallbackReason).toBe('capability_does_not_support_stored_mode')
    expect(storage.snapshot()).toEqual({ [workpaperSyncModeKey(SCOPE)]: 'html' })
  })

  it('single_onlyoffice 遇到存量 html ⇒ 回落 oo', () => {
    const storage = new MemoryStorage()
    storage.setItem(`h4-dual-mode:${WP_ID}`, 'html')
    const result = migrateWorkpaperSyncMode(SCOPE, 'single_onlyoffice', { storage })
    expect(result.mode).toBe('oo')
    expect(result.fallbackApplied).toBe(true)
  })

  it('unreachable 两侧都不可用 ⇒ 不采用任何模式且不写统一键', () => {
    const storage = new MemoryStorage()
    storage.setItem(`h4-dual-mode:${WP_ID}`, 'onlyoffice')
    storage.setItem(workpaperSyncModeKey(SCOPE), 'oo')
    const result = migrateWorkpaperSyncMode(SCOPE, 'unreachable', { storage })
    expect(result.mode).toBeNull()
    expect(result.fallbackReason).toBe('capability_unreachable')
    expect(result.wroteUnifiedKey).toBe(false)
    expect(storage.snapshot()).toEqual({})
  })

  it('bidirectional 支持两侧；单模式 capability 各只支持一侧', () => {
    expect([...supportedModesForCapability('bidirectional')]).toEqual(['html', 'oo'])
    expect([...supportedModesForCapability('single_html')]).toEqual(['html'])
    expect([...supportedModesForCapability('single_onlyoffice')]).toEqual(['oo'])
    expect([...supportedModesForCapability('unreachable')]).toEqual([])
  })

  it('持久化一个 capability 不支持的模式 ⇒ 拒绝且不落盘', () => {
    const storage = new MemoryStorage()
    expectRefusal(
      () => persistWorkpaperSyncMode(SCOPE, 'single_html', 'oo', { storage }),
      'mode_not_supported_by_capability',
    )
    expect(storage.snapshot()).toEqual({})
  })

  it('未登记的 capability 一律 fail visible', () => {
    expectRefusal(
      () =>
        migrateWorkpaperSyncMode(SCOPE, 'brand_new' as 'bidirectional', {
          storage: new MemoryStorage(),
        }),
      'mode_capability_unknown',
    )
    expectRefusal(
      () => supportedModesForCapability('brand_new' as 'bidirectional'),
      'mode_capability_unknown_on_query',
    )
  })
})
