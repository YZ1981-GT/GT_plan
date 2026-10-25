/**
 * Registry Barrel — 显式装配 6 个物理域模块
 *
 * 职责边界：
 * - 本文件**只装配、不分类**。每条条目属于哪个域，由 entries/*.ts 的显式数组
 *   决定（membership is the array itself），barrel 不做任何字符串前缀推断。
 * - 逻辑审计域的前缀分类在 ./domain.ts，通过 `export *` re-export。
 *
 * 装配时序（fail-closed）：
 *   1. 各域数组 flat 成 REGISTRY_LIST
 *   2. 立即对 REGISTRY_LIST 跑唯一性断言 —— 重复 componentType 在模块加载期就抛，
 *      而不是等到 Map 构造时静默后写覆盖
 *   3. 构造 O(1) 查找 Map
 *
 * 兼容面：与原 htmlRendererRegistry 等价（HTML_RENDERER_REGISTRY /
 * HTML_COMPONENT_TYPE_SET / HTML_RENDERER_ROUTE_SET / PLACEHOLDER_ICONS 及工具函数），
 * 因此 20 个直接 import 单体的生产文件与 import barrel 的测试可继续并行使用。
 *
 * @see design.md §8.2 Registry 拆分
 */
import type { HtmlRendererEntry } from './types'
import { coreEntries } from './entries/core'
import { formsEntries } from './entries/forms'
import { programsEntries } from './entries/programs'
import { confirmationsEntries } from './entries/confirmations'
import { reportsEntries } from './entries/reports'
import { specializedEntries } from './entries/specialized'
import { entriesByLogicalDomain } from './logic'

export type { HtmlRendererEntry, ContextPropsStrategy } from './types'
// 逻辑审计域分类（物理装配与逻辑分类分离，见 ./domain.ts 头注）
export * from './domain'

// ─── 物理域装配表 ────────────────────────────────────────────────────────────

/** 物理域的显式条目数组。键为物理域名，值即该域的条目数组本体。 */
export const DOMAIN_ENTRY_ARRAYS: Record<string, readonly HtmlRendererEntry[]> = {
  core: coreEntries,
  forms: formsEntries,
  programs: programsEntries,
  confirmations: confirmationsEntries,
  reports: reportsEntries,
  specialized: specializedEntries,
}

/**
 * 领域键：物理域（DOMAIN_ENTRY_ARRAYS 的键）∪ 逻辑审计域。
 * 两个消费方用不同子集：registryDomainSplit 按物理域取显式数组，
 * registrySplitEquivalence.pbt 按逻辑域投影，getEntriesByDomain 对两者都响应。
 */
export type RegistryDomain = keyof typeof DOMAIN_ENTRY_ARRAYS | import('./domain').RegistryDomain

// ─── 开发期校验 ─────────────────────────────────────────────────────────────

/** 校验 componentType 唯一，重复立即 fail-closed。 */
export function assertUniqueRegistryComponentTypes(
  entries: Iterable<HtmlRendererEntry>,
): void {
  const seen = new Set<string>()
  for (const entry of entries) {
    if (seen.has(entry.componentType)) {
      throw new Error(`registry componentType 重复声明: ${entry.componentType}`)
    }
    seen.add(entry.componentType)
  }
}

/**
 * 校验显式域数组全部被消费。
 * 漏拼一个域文件时 REGISTRY_LIST 会静默缩水，这个断言把「少引用一个数组」变成
 * 加载期抛错而不是运行时随机缺组件。
 */
export function assertAllDomainArraysConsumed(
  consumed: readonly (readonly HtmlRendererEntry[])[],
  expected: Record<string, readonly HtmlRendererEntry[]>,
): void {
  const consumedSet = new Set<readonly HtmlRendererEntry[]>(consumed)
  for (const [domain, arr] of Object.entries(expected)) {
    if (!consumedSet.has(arr)) {
      throw new Error(`domain ${domain} entries not consumed by REGISTRY_LIST`)
    }
  }
}

/**
 * 返回唯一性报告（非抛异常版本），供 PBT / 契约测试断言。
 * 与 assertUniqueRegistryComponentTypes 同源，保证两种消费方式判定一致。
 */
export function validateRegistryUniqueness(entries: Iterable<HtmlRendererEntry>): {
  valid: boolean
  duplicates: string[]
} {
  const seen = new Set<string>()
  const duplicates: string[] = []
  for (const entry of entries) {
    if (seen.has(entry.componentType)) {
      duplicates.push(entry.componentType)
    }
    seen.add(entry.componentType)
  }
  return { valid: duplicates.length === 0, duplicates }
}

// ─── 装配 ───────────────────────────────────────────────────────────────────

export const REGISTRY_LIST: HtmlRendererEntry[] = [
  ...coreEntries,
  ...formsEntries,
  ...programsEntries,
  ...confirmationsEntries,
  ...reportsEntries,
  ...specializedEntries,
]

// Map 构造前先跑两道断言：漏拼域 / 重复声明都在加载期暴露
assertAllDomainArraysConsumed(
  [coreEntries, formsEntries, programsEntries, confirmationsEntries, reportsEntries, specializedEntries],
  DOMAIN_ENTRY_ARRAYS,
)
assertUniqueRegistryComponentTypes(REGISTRY_LIST)

// ─── 派生视图 ───────────────────────────────────────────────────────────────

/** 注册表 Map（O(1) 查找） */
export const HTML_RENDERER_REGISTRY: ReadonlyMap<string, HtmlRendererEntry> = new Map(
  REGISTRY_LIST.map((e) => [e.componentType, e]),
)

/** 全部注册条目（只读视图） */
export function getAllEntries(): readonly HtmlRendererEntry[] {
  return REGISTRY_LIST
}

/** 全部注册条目的 componentType 集合 */
export function getAllComponentTypes(): ReadonlySet<string> {
  return new Set(REGISTRY_LIST.map((e) => e.componentType))
}

/** HTML 类型集合（仅 registry 注册的真实组件，不含 skip placeholder） */
export const HTML_COMPONENT_TYPE_SET: ReadonlySet<string> = getAllComponentTypes()

/** placeholder 类型（univer/skip）的图标，渲染走 GtWpRenderer 内部 fallback */
export const PLACEHOLDER_ICONS: Readonly<Record<string, string>> = {
  univer: '📊',
  skip: '⏭️',
}

/**
 * GtWpRenderer 路由集合（含 skip / confirmation-hub placeholder）。
 * 集合内但不在 registry 中的两个 placeholder：
 * - skip：由 GtWpRenderer 内部分支渲染 SkippedSheetPlaceholder。
 * - confirmation-hub：函证枢纽的 **workbook 级** componentType，只用于判定走
 *   HTML 渲染器而非 Univer；每个 sheet 自身的 componentType 已单独注册。
 */
export const HTML_RENDERER_ROUTE_SET: ReadonlySet<string> = new Set([
  ...HTML_COMPONENT_TYPE_SET,
  'skip',
  'confirmation-hub',
])

/**
 * 按领域取条目。双模分发，两个消费方语义不同：
 * - **物理域**（core/forms/programs/confirmations/reports/specialized）：命中
 *   DOMAIN_ENTRY_ARRAYS 就返回该域的显式数组本体 —— membership is the array
 *   itself，不做任何字符串推断。registryDomainSplit.spec.ts 走这条。
 * - **逻辑审计域**（a-b/c/d-f/g-i/j-n/s/confirmation）：物理表未命中时，按
 *   componentType 前缀归类后过滤返回。registrySplitEquivalence.pbt.spec.ts 走这条。
 *
 * 逻辑域的前缀分类在 ./logic.ts（barrel 只装配、不分类，见文件头注）。
 * 这里只拿结果，不重复实现。
 */
export function getEntriesByDomain(
  domain: RegistryDomain,
): readonly HtmlRendererEntry[] {
  const physical = DOMAIN_ENTRY_ARRAYS[domain as keyof typeof DOMAIN_ENTRY_ARRAYS]
  if (physical) return physical
  return entriesByLogicalDomain(domain, REGISTRY_LIST)
}

// ─── 工具函数（与 htmlRendererRegistry 同名同义，保持双入口兼容） ─────────────

export function isHtmlComponentType(ct: string): boolean {
  return HTML_COMPONENT_TYPE_SET.has(ct)
}

export function getRendererEntry(ct: string): HtmlRendererEntry | undefined {
  return HTML_RENDERER_REGISTRY.get(ct)
}

export function getSheetIcon(ct: string): string {
  return getRendererEntry(ct)?.icon ?? PLACEHOLDER_ICONS[ct] ?? '📄'
}

/** 获取 componentType 的上下文 props 策略，GtWpRenderer 用它替代硬编码 if 链。 */
export function getContextPropsStrategy(ct: string): 'standard' | 'custom' | 'form-type' | 'none' {
  return getRendererEntry(ct)?.contextProps ?? 'none'
}

/**
 * lazy 组件类型。
 * 域文件里的 componentType 是字符串字面量，这里收集其字面量并集，
 * 保持与 htmlRendererRegistry 的 HtmlComponentType 可互换。
 */
export type HtmlComponentType = HtmlRendererEntry['componentType']
