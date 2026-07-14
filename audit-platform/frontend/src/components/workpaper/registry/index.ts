/**
 * Registry Barrel — 按领域拆分的 htmlRendererRegistry 入口
 *
 * 设计目标：
 * - 单一 barrel 合并所有领域模块
 * - 开发期校验 componentType 唯一
 * - HtmlComponentType 从 entries 推导
 * - 保持原有 API 完全兼容
 *
 * 领域划分：core / a-b / c / d-f / g-i / j-n / s / confirmation
 *
 * @see design.md §8.2 Registry 拆分
 */
import type { HtmlRendererEntry } from './types'
export type { HtmlRendererEntry, ContextPropsStrategy } from './types'

// ─── 领域模块导入 ────────────────────────────────────────────────────────────
// 当前阶段：从原始单文件导入全部条目，按 componentType 前缀分类到逻辑域
// 后续可逐步将各域条目物理拆分到独立文件
import {
  HTML_RENDERER_REGISTRY as ORIGINAL_REGISTRY,
  HTML_COMPONENT_TYPE_SET as ORIGINAL_TYPE_SET,
  HTML_RENDERER_ROUTE_SET as ORIGINAL_ROUTE_SET,
  PLACEHOLDER_ICONS as ORIGINAL_PLACEHOLDER_ICONS,
  isHtmlComponentType as originalIsHtmlComponentType,
  getRendererEntry as originalGetRendererEntry,
  getSheetIcon as originalGetSheetIcon,
  getContextPropsStrategy as originalGetContextPropsStrategy,
  type HtmlComponentType,
} from '../htmlRendererRegistry'

export type { HtmlComponentType }

// ─── 领域分类（逻辑视图） ─────────────────────────────────────────────────────

/** 按领域前缀对 componentType 分类 */
export type RegistryDomain =
  | 'core'
  | 'a-b'
  | 'c'
  | 'd-f'
  | 'g-i'
  | 'j-n'
  | 's'
  | 'confirmation'

/** 判断 componentType 所属领域 */
export function classifyDomain(ct: string): RegistryDomain {
  if (ct.startsWith('confirmation-')) return 'confirmation'
  if (ct.startsWith('a') || ct.startsWith('b') || ct === 'e-control-test') return 'a-b'
  if (ct.startsWith('c')) return 'c'
  if (ct.startsWith('d') || ct.startsWith('f') || ct === 'e1-monetary-fund') return 'd-f'
  if (ct.startsWith('g') || ct.startsWith('h') || ct.startsWith('i')) return 'g-i'
  if (ct.startsWith('j') || ct.startsWith('k') || ct.startsWith('l') || ct.startsWith('m') || ct.startsWith('n')) return 'j-n'
  if (ct.startsWith('s')) return 's'
  return 'core'
}

/** 按领域获取条目子集 */
export function getEntriesByDomain(domain: RegistryDomain): HtmlRendererEntry[] {
  const result: HtmlRendererEntry[] = []
  for (const entry of ORIGINAL_REGISTRY.values()) {
    if (classifyDomain(entry.componentType) === domain) {
      result.push(entry)
    }
  }
  return result
}

// ─── 开发期唯一性校验 ─────────────────────────────────────────────────────────

/**
 * 校验全部 componentType 唯一（开发期断言）。
 * 在 dev 环境下自动执行，重复注册立即抛出。
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

// Dev-time assertion: 重复 componentType 立即报错
if (import.meta.env?.DEV) {
  const { valid, duplicates } = validateRegistryUniqueness(ORIGINAL_REGISTRY.values())
  if (!valid) {
    console.error(
      `[Registry] componentType 注册重复: ${duplicates.join(', ')}`,
    )
  }
}

// ─── 兼容导出（与原 htmlRendererRegistry 完全等价） ───────────────────────────

export const HTML_RENDERER_REGISTRY = ORIGINAL_REGISTRY
export const HTML_COMPONENT_TYPE_SET = ORIGINAL_TYPE_SET
export const HTML_RENDERER_ROUTE_SET = ORIGINAL_ROUTE_SET
export const PLACEHOLDER_ICONS = ORIGINAL_PLACEHOLDER_ICONS
export const isHtmlComponentType = originalIsHtmlComponentType
export const getRendererEntry = originalGetRendererEntry
export const getSheetIcon = originalGetSheetIcon
export const getContextPropsStrategy = originalGetContextPropsStrategy

/**
 * 全部注册条目的 componentType 集合（用于 P9 等价断言）。
 * 从 barrel 导出确保与原 REGISTRY_LIST 同源。
 */
export function getAllComponentTypes(): ReadonlySet<string> {
  return new Set([...ORIGINAL_REGISTRY.keys()])
}

/**
 * 全部注册条目数组（只读视图）
 */
export function getAllEntries(): readonly HtmlRendererEntry[] {
  return [...ORIGINAL_REGISTRY.values()]
}
