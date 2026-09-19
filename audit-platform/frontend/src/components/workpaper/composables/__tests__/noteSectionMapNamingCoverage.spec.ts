/**
 * 附注映射文件命名覆盖守卫（Property 9）
 *
 * `gen_note_wp_sync_registry.py` 与 `disclosureSheetNameRegistry.spec.ts` 都按
 * `{code}NoteSectionMap.ts` 命名 glob 来发现循环。命名不匹配 = 该循环在
 * 「同步就绪度」视角里**不存在**：
 *
 * - H4 曾只有 `h4DisclosureSyncPayload.ts` / `h4SoeDisclosureSyncPayload.ts`，无 map 文件 → registry 缺 H4；
 * - H6 有 map 文件但写 `H6_NOTE_SECTION = H1_NOTE_SECTION`（标识符引用），生成器 text-scan 抽不到 → registry 缺 H6；
 * - `mEquityChangeNoteSectionMap.ts` 是三循环共享件，文件名不匹配 `{code}` 形态，
 *   由 `m4/m5/m7NoteSectionMap.ts` 三个薄壳代表进入 registry。
 *
 * 本守卫从**文件系统**（而非 import）派生循环码全集，与 registry 求差集。
 *
 * spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R4
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'

const COMPOSABLES_DIR = resolve(__dirname, '..')
const REPO_ROOT = resolve(__dirname, '../../../../../../..')

/** 与生成脚本 `_WP_CODE` 同口径 */
const MAP_RE = /^([a-z]+\d+)NoteSectionMap\.ts$/
/** 载荷构建文件命名（各循环形态不一，统一按前缀取循环码） */
const PAYLOAD_RE = /^([a-z]+\d+)(?:Soe)?DisclosureSyncPayload\.ts$/

/**
 * 允许「有映射/载荷文件但不进 registry」的例外。
 * 每条必须写明理由；修好后必须移出（否则守卫失去意义）。
 *
 * 目前为空 —— 2026-07-31 本 spec 已把 G1/G3/G10/H4/H6 五个缺口全部补齐
 * （entries 62→67）。新增循环若在此出现，先按下面三种根因排查，不要图省事加豁免。
 */
const REGISTRY_EXEMPT: Record<string, string> = {}

/**
 * 允许「文件名不匹配 `{code}NoteSectionMap.ts`」的共享映射件。
 * 每条须说明由哪些薄壳代表。
 */
const SHARED_MAP_FILES: Record<string, string> = {
  'mEquityChangeNoteSectionMap.ts': 'M4/M5/M7 共享标准变动表映射；由 m4/m5/m7NoteSectionMap.ts 三个薄壳代表进 registry',
}

interface RegistryEntry {
  wp_code?: string
  listed?: string | null
  soe?: string | null
}

const registry: RegistryEntry[] = (() => {
  const path = resolve(REPO_ROOT, 'backend/data/note_workpaper_sync_registry.json')
  const doc = JSON.parse(readFileSync(path, 'utf-8')) as { entries?: RegistryEntry[] }
  return doc.entries ?? []
})()

const registryCodes = new Set(registry.filter((e) => e.wp_code).map((e) => String(e.wp_code).toUpperCase()))

const files = readdirSync(COMPOSABLES_DIR).filter((f) => f.endsWith('.ts'))

const mapFiles = files.filter((f) => f.endsWith('NoteSectionMap.ts'))
const codeFromMap = new Map<string, string>()
const unmatchedMapFiles: string[] = []
for (const f of mapFiles) {
  const m = MAP_RE.exec(f)
  if (m) codeFromMap.set(m[1].toUpperCase(), f)
  else unmatchedMapFiles.push(f)
}

const codeFromPayload = new Map<string, string>()
for (const f of files) {
  const m = PAYLOAD_RE.exec(f)
  if (m) codeFromPayload.set(m[1].toUpperCase(), f)
}

describe('附注映射命名覆盖', () => {
  it('扫描到的文件与 registry 都非空（防 glob / 路径失效导致断言空转）', () => {
    expect(files.length, `${COMPOSABLES_DIR} 下未扫到 .ts 文件`).toBeGreaterThan(100)
    expect(codeFromMap.size, '未扫到 {code}NoteSectionMap.ts').toBeGreaterThan(40)
    expect(registryCodes.size, 'registry entries 为空').toBeGreaterThan(40)
  })

  it('Property 9: 凡有 NoteSectionMap 或 DisclosureSyncPayload 文件的循环码都在 registry', () => {
    const allCodes = new Set([...codeFromMap.keys(), ...codeFromPayload.keys()])
    const missing: string[] = []
    for (const code of [...allCodes].sort()) {
      if (registryCodes.has(code)) continue
      if (code in REGISTRY_EXEMPT) continue
      const where = codeFromMap.get(code) ?? codeFromPayload.get(code)
      missing.push(`${code}（${where}）`)
    }
    expect(
      missing,
      `以下循环有披露映射/载荷文件但不在 note_workpaper_sync_registry.json 中：${missing.join(' / ')}。`
        + '三种根因：① 缺 {code}NoteSectionMap.ts 薄壳（H4 曾如此）；'
        + '② 章节号写成标识符引用而非内联字面量（G3/H6 曾如此）；'
        + '③ 一个循环覆盖两个章节的嵌套形态未被生成器支持（G1/G10 曾如此）。'
        + '修好后重跑 python backend/scripts/gen_note_wp_sync_registry.py --write',
    ).toHaveLength(0)
  })

  it('文件名不匹配 `{code}NoteSectionMap.ts` 的共享件必须在 allowlist 且写明理由', () => {
    const undeclared = unmatchedMapFiles.filter((f) => !(f in SHARED_MAP_FILES))
    expect(
      undeclared,
      `以下映射文件名不被生成器 glob 命中且未登记：${undeclared.join(' / ')}`,
    ).toHaveLength(0)
    for (const [file, reason] of Object.entries(SHARED_MAP_FILES)) {
      expect(reason.length, `${file} 的 allowlist 理由过短`).toBeGreaterThan(10)
    }
  })

  it('allowlist 不得残留已修好的条目（否则守卫形同虚设）', () => {
    const stale = Object.keys(REGISTRY_EXEMPT).filter((code) => registryCodes.has(code))
    expect(stale, `以下循环已进 registry，请从 REGISTRY_EXEMPT 移出：${stale.join(' / ')}`).toHaveLength(0)
    const staleShared = Object.keys(SHARED_MAP_FILES).filter((f) => !unmatchedMapFiles.includes(f))
    expect(
      staleShared,
      `以下文件已不存在或已改名，请从 SHARED_MAP_FILES 移出：${staleShared.join(' / ')}`,
    ).toHaveLength(0)
  })

  it('H1~H10 全部在 registry（本 spec 的直接交付）', () => {
    const hCodes = ['H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'H7', 'H8', 'H9', 'H10']
    const missing = hCodes.filter((c) => !registryCodes.has(c))
    expect(missing, `H 循环缺失：${missing.join(' / ')}`).toHaveLength(0)
  })

  it('G1 / G10 双章节条目带 *_sections 全集，且 listed/soe 取首个子章节', () => {
    for (const code of ['G1', 'G10']) {
      const e = registry.find((x) => x.wp_code === code) as
        | (RegistryEntry & { listed_sections?: Record<string, string>; soe_sections?: Record<string, string> })
        | undefined
      expect(e, `${code} 不在 registry`).toBeTruthy()
      const ls = e?.listed_sections
      const ss = e?.soe_sections
      expect(Object.keys(ls ?? {}).length, `${code} 缺 listed_sections`).toBeGreaterThan(1)
      expect(Object.keys(ss ?? {}).length, `${code} 缺 soe_sections`).toBeGreaterThan(1)
      expect(e?.listed).toBe(Object.values(ls ?? {})[0])
      expect(e?.soe).toBe(Object.values(ss ?? {})[0])
    }
  })

  it('G3 薄壳章节号内联且与 G2 真源一致（共用其他应收款汇总章节）', () => {
    const g2 = registry.find((x) => x.wp_code === 'G2')
    const g3 = registry.find((x) => x.wp_code === 'G3')
    expect(g3, 'G3 不在 registry').toBeTruthy()
    expect(g3?.listed).toBe(g2?.listed)
    expect(g3?.soe).toBe(g2?.soe)
    const s = readFileSync(resolve(COMPOSABLES_DIR, 'g3NoteSectionMap.ts'), 'utf-8')
    expect(s, 'G3_NOTE_SECTION 必须内联字面量，否则 G3 从 registry 消失').toMatch(
      /export const G3_NOTE_SECTION\s*=\s*\{/,
    )
  })

  it('registry 里每条至少有一个变体的章节号（否则是空壳条目）', () => {
    const empty = registry
      .filter((e) => e.wp_code)
      .filter((e) => !e.listed && !e.soe)
      .map((e) => String(e.wp_code))
    expect(empty, `以下 registry 条目两个变体章节号都为空：${empty.join(' / ')}`).toHaveLength(0)
  })
})
