#!/usr/bin/env node
/**
 * CI 守卫：检测绕过 displayPrefs 统一出口的裸金额/货币格式化
 *
 * 规则：在 src/**\/*.{vue,ts} 中（排除出口文件），
 * 若出现 `toLocaleString('zh-CN'` 且同行含 minimumFractionDigits/maximumFractionDigits,
 * 或出现 `style: 'currency'` / `style: "currency"`，
 * 且不在豁免清单中，即视为绕过统一出口。
 *
 * 用法：
 *   node scripts/check-format-single-source.mjs
 *
 * 退出码：0=无新增违规，1=有新增违规
 */
import { readFileSync, readdirSync, existsSync } from 'fs'
import { join, relative } from 'path'

const SRC_DIR = join(import.meta.dirname, '..', 'src')
const ALLOWLIST_PATH = join(import.meta.dirname, 'format-legacy-allowlist.json')

// 出口文件不检查
const EXCLUDE_FILES = [
  'stores/displayPrefs.ts',
  'utils/formatters.ts',
  'utils/formatAmount.ts',
]

// 匹配裸金额格式化
const AMOUNT_FMT_RE = /toLocaleString\('zh-CN'.*(?:minimumFractionDigits|maximumFractionDigits)/
const CURRENCY_RE = /style:\s*['"]currency['"]/

function walk(dir) {
  const results = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.nuxt') continue
      results.push(...walk(full))
    } else if (/\.(vue|ts)$/.test(entry.name)) {
      results.push(full)
    }
  }
  return results
}

// 加载豁免清单
let allowlist = new Set()
if (existsSync(ALLOWLIST_PATH)) {
  try {
    const raw = JSON.parse(readFileSync(ALLOWLIST_PATH, 'utf-8'))
    allowlist = new Set(raw) // ["file:line", ...]
  } catch { /* ignore */ }
}

const violations = []

for (const file of walk(SRC_DIR)) {
  const rel = relative(SRC_DIR, file).replace(/\\/g, '/')
  if (EXCLUDE_FILES.some(ex => rel === ex)) continue

  const lines = readFileSync(file, 'utf-8').split('\n')
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (AMOUNT_FMT_RE.test(line) || CURRENCY_RE.test(line)) {
      const key = `${rel}:${i + 1}`
      if (!allowlist.has(key)) {
        violations.push({ key, content: line.trim().slice(0, 120) })
      }
    }
  }
}

if (violations.length > 0) {
  console.error(`\n❌ 发现 ${violations.length} 处绕过 displayPrefs 的裸金额格式化（不在豁免清单中）：\n`)
  for (const v of violations.slice(0, 20)) {
    console.error(`  ${v.key}`)
  }
  if (violations.length > 20) console.error(`  ... 及另外 ${violations.length - 20} 处`)
  console.error('\n请改用 useDisplayPrefsStore().fmt(v) / fmtAmount(v)。')
  console.error('若为存量代码尚未迁移，可添加到 scripts/format-legacy-allowlist.json。\n')
  process.exit(1)
} else {
  console.log('✅ 无新增裸金额格式化（存量豁免清单内的不告警）')
  process.exit(0)
}
