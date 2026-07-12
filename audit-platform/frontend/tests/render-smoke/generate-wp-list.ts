/**
 * generate-wp-list.ts — 从 wp_code_overrides.json + registry 生成可测 wp_code 清单
 *
 * 过滤规则：
 * - 排除 componentType = "skip" 的条目（被父底稿吞的子 sheet）
 * - 排除非底稿相关的描述性文本键（如 "1.文号规则"）
 * - 仅保留有效 wp_code 格式：A-Z 开头，如 A1, D2-1, B22A, C24-5 等
 *
 * Feature: platform-global-hardening
 * Requirements: 3.5, 3.6
 */
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

/** 有效 wp_code 正则：A-Z 开头，后跟字母数字/-/小写字母组合 */
const WP_CODE_RE = /^[A-Z]\d+[A-Za-z0-9\-]*$/

/** 已知不渲染为独立底稿的 componentType（跳过） */
const SKIP_COMPONENT_TYPES = new Set(['skip'])

export interface WpCodeEntry {
  wpCode: string
  componentType: string
}

/**
 * 从 wp_code_overrides.json 读取并筛选可渲染的 wp_code 列表
 */
export function generateWpCodeList(): WpCodeEntry[] {
  const overridesPath = resolve(
    __dirname,
    '../../../../backend/app/data/wp_code_overrides.json',
  )
  const raw = readFileSync(overridesPath, 'utf-8')
  const overrides: Record<string, string> = JSON.parse(raw)

  const entries: WpCodeEntry[] = []

  for (const [wpCode, componentType] of Object.entries(overrides)) {
    // 跳过非 wp_code 格式的键（描述性文本）
    if (!WP_CODE_RE.test(wpCode)) continue
    // 跳过被标记为 skip 的子 sheet
    if (SKIP_COMPONENT_TYPES.has(componentType)) continue

    entries.push({ wpCode, componentType })
  }

  // 按 wp_code 排序确保稳定顺序
  entries.sort((a, b) => a.wpCode.localeCompare(b.wpCode, 'en', { numeric: true }))

  return entries
}

/**
 * 获取 wp_code 清单（缓存）
 */
let _cached: WpCodeEntry[] | null = null
export function getWpCodeList(): WpCodeEntry[] {
  if (!_cached) {
    _cached = generateWpCodeList()
  }
  return _cached
}
