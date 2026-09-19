/**
 * 披露同步 `sheet_name` 单一口径守卫（Property 11）
 *
 * 口径链路：
 * ```
 * {x}NoteSectionMap.ts  X_DISCLOSURE_SHEET_{NAME|LISTED|SOE}   ← 唯一真源（= 源 xlsx 真实 tab 名）
 *        ├──> build{X}SyncPayload().sheet_name
 *        │        └──> disclosure_notes._last_sync_sheet
 *        │                 └──> 附注「打开同步底稿」→ GtWpRenderer ?sheet={name} 精确匹配
 *        └──(python backend/scripts/gen_note_wp_sync_registry.py --write)──>
 *              backend/data/note_workpaper_sync_registry.json  { sheet_listed, sheet_soe }
 * ```
 *
 * 用合成标识（`F3-note-soe`）或短名（`附注上市`）都会让 `?sheet=` 匹配不上 →
 * 反向跳转落到底稿首个 sheet，审计师看不到刚同步的那张表。
 *
 * 本守卫同时拦两个方向的漂移：
 * 1. 改了 `*NoteSectionMap.ts` 忘了重跑生成脚本 → 常量 ≠ registry；
 * 2. 手工编辑了 registry → 同上。
 *
 * 覆盖面自动扩展：按 `import.meta.glob` 扫全部 `*NoteSectionMap.ts`，新循环声明
 * 常量后自动纳入，无需在此登记。
 *
 * spec: .kiro/specs/disclosure-columns-coverage-rollout/ R8（Task 16.5）
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const REPO_ROOT = resolve(__dirname, '../../../../../../..')
const REGEN_HINT = '请重跑 python backend/scripts/gen_note_wp_sync_registry.py --write'

interface RegistryEntry {
  wp_code?: string
  sheet_listed?: string | null
  sheet_soe?: string | null
  source_file?: string
}

const registry: RegistryEntry[] = (() => {
  const path = resolve(REPO_ROOT, 'backend/data/note_workpaper_sync_registry.json')
  const doc = JSON.parse(readFileSync(path, 'utf-8')) as { entries?: RegistryEntry[] }
  return doc.entries ?? []
})()

const registryByCode = new Map(
  registry.filter((e) => e.wp_code).map((e) => [String(e.wp_code), e]),
)

// ─── 从各 *NoteSectionMap.ts 收集 sheet 名常量 ────────────────────────────────

/** 与生成脚本 `_WP_CODE` 同口径：`g10NoteSectionMap.ts` → `G10` */
const WP_CODE_RE = /^([a-z]+\d+)NoteSectionMap\.ts$/
/** 与生成脚本 `_SHEET_CONST` 同口径 */
const SHEET_CONST_RE = /_DISCLOSURE_SHEET_(NAME|LISTED|SOE)$/

type Variant = 'listed' | 'soe'

const modules = import.meta.glob<Record<string, unknown>>('../**/*NoteSectionMap.ts', {
  eager: true,
})

interface Declared {
  wpCode: string
  file: string
  sheets: Partial<Record<Variant, string>>
}

function pickSheets(mod: Record<string, unknown>): Partial<Record<Variant, string>> {
  const out: Partial<Record<Variant, string>> = {}
  for (const [name, value] of Object.entries(mod)) {
    const m = SHEET_CONST_RE.exec(name)
    if (!m) continue
    const kind = m[1]
    if (typeof value === 'string') {
      // X_DISCLOSURE_SHEET_LISTED = '…' / _SOE = '…' / _NAME = '…'（两版共用一个名）
      if (kind === 'LISTED') out.listed ??= value
      else if (kind === 'SOE') out.soe ??= value
      else {
        out.listed ??= value
        out.soe ??= value
      }
      continue
    }
    if (value && typeof value === 'object') {
      const rec = value as Record<string, unknown>
      if (typeof rec.listed === 'string') out.listed ??= rec.listed
      if (typeof rec.soe === 'string') out.soe ??= rec.soe
    }
  }
  return out
}

const declared: Declared[] = Object.entries(modules)
  .map(([path, mod]) => {
    const base = path.split('/').pop() ?? ''
    const m = WP_CODE_RE.exec(base)
    if (!m) return null
    const sheets = pickSheets(mod)
    if (!sheets.listed && !sheets.soe) return null
    return { wpCode: m[1].toUpperCase(), file: base, sheets }
  })
  .filter((x): x is Declared => x !== null)
  .sort((a, b) => a.wpCode.localeCompare(b.wpCode))

const declaredPairs = declared.flatMap((d) =>
  (['listed', 'soe'] as const)
    .filter((v) => d.sheets[v])
    .map((v) => ({ wpCode: d.wpCode, variant: v, value: d.sheets[v] as string })),
)

// ─── 断言 ────────────────────────────────────────────────────────────────────

describe('披露 sheet_name 口径守卫', () => {
  it('registry 与 NoteSectionMap 常量都不为空（防 glob/路径失效导致静默零覆盖）', () => {
    expect(registry.length, 'note_workpaper_sync_registry.json 读不到 entries').toBeGreaterThan(20)
    expect(declared.length, 'import.meta.glob 未扫到 *NoteSectionMap.ts').toBeGreaterThan(20)
    expect(declaredPairs.length).toBeGreaterThan(40)
  })

  it('Property 11: 常量值与 registry 的 sheet_listed / sheet_soe 逐字一致', () => {
    const mismatches: string[] = []
    let compared = 0
    for (const { wpCode, variant, value } of declaredPairs) {
      const entry = registryByCode.get(wpCode)
      if (!entry) continue // registry 未收录该循环（无章节号），不做断言
      const expected = variant === 'listed' ? entry.sheet_listed : entry.sheet_soe
      if (expected == null) continue // 生成脚本未提取到（不臆造），跳过
      compared += 1
      if (expected !== value) {
        mismatches.push(`${wpCode}.${variant}: 常量「${value}」≠ registry「${expected}」`)
      }
    }
    expect(mismatches, `${mismatches.join(' / ')}；${REGEN_HINT}`).toHaveLength(0)
    // 比对数下限：防「registry 全为 null 时断言空转」
    expect(compared, '有效比对数过低，registry 可能未重新生成').toBeGreaterThan(40)
  })

  it('禁止合成标识（`X-note-listed`）当 sheet 名', () => {
    const bad = declaredPairs.filter((p) => /-note-(listed|soe)$/i.test(p.value))
    expect(
      bad.map((p) => `${p.wpCode}.${p.variant}=${p.value}`),
      'sheet_name 必须是源 xlsx 真实 tab 名，不是 wp_code 形态的合成标识',
    ).toHaveLength(0)
  })

  it('禁止短名（`附注上市` / `附注国企`）当 sheet 名', () => {
    const SHORT = new Set(['附注上市', '附注国企', '附注国有企业', '附注披露'])
    const bad = declaredPairs.filter((p) => SHORT.has(p.value.trim()))
    expect(
      bad.map((p) => `${p.wpCode}.${p.variant}=${p.value}`),
      '短名是组件内部分发编码，不能当同步载荷的 sheet_name',
    ).toHaveLength(0)
  })

  it('sheet 名形如「附注披露…」且含变体标识（上市/国企/国有企业）', () => {
    const bad = declaredPairs.filter((p) => {
      const v = p.value.trim()
      if (!v.startsWith('附注披露')) return true
      return p.variant === 'listed' ? !v.includes('上市') : !(v.includes('国企') || v.includes('国有'))
    })
    expect(bad.map((p) => `${p.wpCode}.${p.variant}=${p.value}`)).toHaveLength(0)
  })

  it('registry 侧同样不含合成标识 / 短名（防手工编辑绕过）', () => {
    const bad: string[] = []
    for (const e of registry) {
      for (const [variant, value] of [
        ['listed', e.sheet_listed],
        ['soe', e.sheet_soe],
      ] as const) {
        if (!value) continue
        if (/-note-(listed|soe)$/i.test(value) || ['附注上市', '附注国企'].includes(value.trim())) {
          bad.push(`${e.wp_code}.${variant}=${value}`)
        }
      }
    }
    expect(bad, `${bad.join(' / ')}；${REGEN_HINT}`).toHaveLength(0)
  })
})
