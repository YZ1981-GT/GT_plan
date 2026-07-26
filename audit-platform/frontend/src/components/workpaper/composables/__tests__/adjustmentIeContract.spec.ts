/**
 * 调整分录导入导出 —— 前端契约守卫（对 backend/data/adjustment_ie_contract.json）
 *
 * spec: adjustment-import-export-contract / Task 4.2 + Task 4.3
 *
 * 后端测试读不到 `.vue`，前端 vitest 读不到 Python `_SPECS` → 两侧各自对照**同一份清单**断言：
 *   * Property 9  清单内 aligned 的 sheet：其 `item_id`（或 `ITEM_PREFIX` 拼接形态）必须在前端源码中
 *                 真实出现，且写入列与清单 `storage_field` 一致（一律 `remark`）。
 *   * Property 11 注册完整性：前端调整分录持久化键所属的每张 sheet，必须出现在清单
 *                 `sheets` 或 `exempt` 中；遗漏即失败（守卫遍历源码，不硬编码逐条清单）。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// ─── 定位仓库根与契约清单 ─────────────────────────────────────────────────────

const HERE = path.dirname(fileURLToPath(import.meta.url))

function findRepoRoot(start: string): string {
  let dir = start
  for (let i = 0; i < 12; i++) {
    if (fs.existsSync(path.join(dir, 'backend', 'data', 'adjustment_ie_contract.json'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error('未找到仓库根（backend/data/adjustment_ie_contract.json）')
}

const REPO_ROOT = findRepoRoot(HERE)
const CONTRACT = JSON.parse(
  fs.readFileSync(path.join(REPO_ROOT, 'backend', 'data', 'adjustment_ie_contract.json'), 'utf8'),
) as {
  sheets: Record<string, any>
  exempt: Record<string, any>
}

const WP_ROOT = path.resolve(HERE, '../..') // src/components/workpaper

// ─── 扫描前端调整分录源文件 ───────────────────────────────────────────────────

function walkAdjustmentFiles(dir: string, out: string[] = []): string[] {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) {
      if (e.name === '__tests__') continue
      walkAdjustmentFiles(p, out)
    } else if (/(TabAdjustment\.vue|Adjustment\.ts)$/.test(e.name)) {
      out.push(p)
    }
  }
  return out
}

const FILES = walkAdjustmentFiles(WP_ROOT)
const SOURCES = new Map<string, string>(
  FILES.map((f) => [path.relative(REPO_ROOT, f).replace(/\\/g, '/'), fs.readFileSync(f, 'utf8')]),
)

/** 键形态：'K3-3-adj-entries' / 'G8-adjustment-rows' / 'H10-aje-rows' / 'K12-3-rows' */
const KEY_RE = /['"`]([A-Z]{1,2}\d{1,2}(?:-\d{1,2})?(?:-[A-Za-z0-9]+)*)['"`]/g
const INTEREST_RE = /(rows|entries|aje|rje|adjustment|adj)/i

function extractKeys(src: string): string[] {
  const keys = new Set<string>()
  KEY_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = KEY_RE.exec(src))) {
    const k = m[1]
    if (!k.includes('-')) continue
    if (!INTEREST_RE.test(k)) continue
    keys.add(k)
  }
  // ITEM_PREFIX 拼接形态：const ITEM_PREFIX = 'K3-3-adj' … `${ITEM_PREFIX}-entries`
  const pm = src.match(/ITEM_PREFIX\s*=\s*['"`]([^'"`]+)['"`]/)
  if (pm) {
    for (const sm of src.matchAll(/\$\{ITEM_PREFIX\}-([A-Za-z0-9-]+)/g)) {
      keys.add(`${pm[1]}-${sm[1]}`)
    }
  }
  return [...keys]
}

/** 清单里已登记的全部键（sheets.item_id + exempt.observed.* ） */
function registeredKeys(): Set<string> {
  const out = new Set<string>()
  for (const e of Object.values(CONTRACT.sheets)) out.add(e.item_id)
  for (const [k, v] of Object.entries(CONTRACT.exempt)) {
    if (k.startsWith('_') || typeof v !== 'object' || v === null) continue
    const obs = (v as any).observed ?? {}
    for (const kk of ['backend_item_id', 'frontend_key']) {
      if (obs[kk]) out.add(obs[kk])
    }
    for (const kk of obs.frontend_keys ?? []) out.add(kk)
  }
  return out
}

const REGISTERED_SHEETS = new Set([
  ...Object.keys(CONTRACT.sheets),
  ...Object.keys(CONTRACT.exempt).filter((k) => !k.startsWith('_')),
])
const REGISTERED_KEYS = registeredKeys()

// ─── 守卫自身有效性 ───────────────────────────────────────────────────────────

describe('adjustment_ie_contract.json —— 前端契约守卫', () => {
  it('能扫描到调整分录源文件（否则守卫空转）', () => {
    expect(FILES.length).toBeGreaterThan(100)
    expect(Object.keys(CONTRACT.sheets).length).toBeGreaterThanOrEqual(14)
  })

  // ─── Property 9：清单 item_id 必须在前端源码真实存在，且写 remark 列 ───────

  const alignedSheets = Object.entries(CONTRACT.sheets).filter(
    ([, e]) => (e as any).status === 'aligned',
  )

  it.each(alignedSheets.map(([s]) => s))(
    'Property 9 — %s 的 item_id 在前端源码中真实存在（字面量或 ITEM_PREFIX 拼接）',
    (sheet) => {
      const entry = CONTRACT.sheets[sheet]
      const itemId: string = entry.item_id
      const prefixForm = itemId.replace(/-entries$/, '') // ITEM_PREFIX 形态
      const hits: string[] = []
      for (const [rel, src] of SOURCES) {
        const keys = extractKeys(src)
        if (keys.includes(itemId)) {
          hits.push(rel)
          continue
        }
        // ITEM_PREFIX = 'K3-3-adj' 且模板里用 `${ITEM_PREFIX}-entries`
        const pm = src.match(/ITEM_PREFIX\s*=\s*['"`]([^'"`]+)['"`]/)
        if (pm && pm[1] === prefixForm && /\$\{ITEM_PREFIX\}-entries/.test(src)) hits.push(rel)
      }
      expect(
        hits.length,
        `清单 ${sheet}.item_id='${itemId}' 在前端调整分录源码中找不到；` +
          '若前端键已改名，请同步契约清单与后端 Sheet_Spec（三重键必须同时对齐）',
      ).toBeGreaterThan(0)
    },
  )

  it.each(alignedSheets.map(([s]) => s))(
    'Property 9 — %s 的写入列与清单 storage_field 一致',
    (sheet) => {
      const entry = CONTRACT.sheets[sheet]
      expect(entry.storage_field, `${sheet}: 契约 storage_field 应为 remark（前端一律写 remark）`).toBe(
        'remark',
      )
      const itemId: string = entry.item_id
      const prefixForm = itemId.replace(/-entries$/, '')
      const owners = [...SOURCES.entries()].filter(([, src]) => {
        if (src.includes(`'${itemId}'`) || src.includes(`"${itemId}"`) || src.includes(`\`${itemId}\``)) {
          return true
        }
        const pm = src.match(/ITEM_PREFIX\s*=\s*['"`]([^'"`]+)['"`]/)
        return !!pm && pm[1] === prefixForm
      })
      expect(owners.length).toBeGreaterThan(0)
      // 写入侧必须出现 remark 列（emit('save', key, { remark }) / debouncedSave(..., { remark })）
      const writesRemark = owners.some(([, src]) => /remark\s*:/.test(src))
      expect(
        writesRemark,
        `${sheet} 的前端源文件（${owners.map(([r]) => r).join(', ')}）未见 remark 写入列`,
      ).toBe(true)
    },
  )

  // ─── Property 11：注册完整性（前端键 → 清单必有归属） ──────────────────────

  it('Property 11 — 前端每个调整分录持久化键都能归属到清单 sheets 或 exempt', () => {
    const uncovered: Record<string, string[]> = {}
    for (const [rel, src] of SOURCES) {
      for (const key of extractKeys(src)) {
        if (REGISTERED_KEYS.has(key)) continue
        const m = key.match(/^([A-Z]{1,2}\d{1,2})(?:-(\d{1,2}))?/)
        if (!m) continue
        const [, cycle, num] = m
        const sheetGuess = num ? `${cycle}-${num}` : cycle
        if (REGISTERED_SHEETS.has(sheetGuess)) continue
        if ([...REGISTERED_SHEETS].some((r) => r === cycle || r.startsWith(`${cycle}-`))) continue
        ;(uncovered[sheetGuess] ??= []).push(`${key} @ ${rel}`)
      }
    }
    expect(
      uncovered,
      '以下调整分录键未在契约清单登记（补 sheets 或 exempt，并写明豁免原因）',
    ).toEqual({})
  })

  // ─── 清单自身卫生 ──────────────────────────────────────────────────────────

  it('exempt 每条都有已登记的 kind + 非空 reason', () => {
    const kinds = new Set(Object.keys(CONTRACT.exempt._exempt_kinds))
    const bad: string[] = []
    for (const [sheet, e] of Object.entries(CONTRACT.exempt)) {
      if (sheet.startsWith('_')) continue
      const entry = e as any
      if (!kinds.has(entry?.kind) || !entry?.reason) bad.push(sheet)
    }
    expect(bad).toEqual([])
  })

  it('同一 sheet 不得既在 sheets 又在 exempt', () => {
    const dup = Object.keys(CONTRACT.sheets).filter((s) => s in CONTRACT.exempt)
    expect(dup).toEqual([])
  })

  it('K12-3 前端已迁 JSON 单键（Wave 2）', () => {
    const src = SOURCES.get('audit-platform/frontend/src/components/workpaper/composables/useK12Adjustment.ts')
    expect(src, '未找到 useK12Adjustment.ts').toBeTruthy()
    expect(src!).toContain("K12_ADJ_ROWS_KEY = 'K12-3-rows'")
    // 写路径不得再逐字段写 per-field 键
    expect(/debouncedSave\(\s*`\$\{ITEM_PREFIX\}-entry-/.test(src!)).toBe(false)
  })
})
