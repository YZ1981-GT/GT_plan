#!/usr/bin/env node
/**
 * CI 守卫：检测绕过 cyclePalette.ts 的循环色值内联硬编码
 *
 * 规则：在 src/**\/*.{vue,ts} 中（排除 constants/cyclePalette.ts），
 * 若出现形如 `[A-S字母]: '#xxxxxx'` 且上下文 5 行内含 CYCLE/cycle/Palette/palette，
 * 即视为绕过统一真源的内联色定义。
 *
 * 用法：
 *   node scripts/check-cycle-palette-single-source.mjs          # 正常检查
 *   node scripts/check-cycle-palette-single-source.mjs --fix    # 仅列出，不阻断
 *
 * 退出码：0=无违规，1=有违规
 */
import { readFileSync, readdirSync, statSync } from 'fs'
import { join, relative } from 'path'

const SRC_DIR = join(import.meta.dirname, '..', 'src')
const EXCLUDE = ['constants/cyclePalette.ts']

// 匹配 "X: '#hex6'" 或 "X: \"#hex6\"" 其中 X 是 A-S
const INLINE_HEX_RE = /\b([A-S]):\s*['"]#[0-9A-Fa-f]{6}['"]/
// 上下文关键词
const CONTEXT_KEYWORDS = /CYCLE|cycle|Palette|palette|COLOR_MAP|COLORS/i

function walk(dir) {
  const results = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '__tests__') continue
      results.push(...walk(full))
    } else if (/\.(vue|ts)$/.test(entry.name)) {
      results.push(full)
    }
  }
  return results
}

const violations = []

for (const file of walk(SRC_DIR)) {
  const rel = relative(SRC_DIR, file).replace(/\\/g, '/')
  if (EXCLUDE.some(ex => rel === ex)) continue

  const lines = readFileSync(file, 'utf-8').split('\n')
  for (let i = 0; i < lines.length; i++) {
    if (!INLINE_HEX_RE.test(lines[i])) continue
    // 检查上下文 5 行内是否含关键词
    const context = lines.slice(Math.max(0, i - 5), i + 6).join('\n')
    if (CONTEXT_KEYWORDS.test(context)) {
      violations.push({ file: rel, line: i + 1, content: lines[i].trim() })
    }
  }
}

if (violations.length > 0) {
  console.error(`\n❌ 发现 ${violations.length} 处绕过 cyclePalette 的内联循环色定义：\n`)
  for (const v of violations) {
    console.error(`  ${v.file}:${v.line}  ${v.content}`)
  }
  console.error('\n请使用 import { cycleColor } from "@/constants/cyclePalette" 替代内联色值。\n')
  process.exit(1)
} else {
  console.log('✅ 未发现绕过 cyclePalette 的内联循环色定义')
  process.exit(0)
}
