/**
 * 调整分录导入导出 —— 前端契约守卫（对 backend/data/adjustment_ie_contract.json）
 *
 * spec: adjustment-import-export-contract / Task 4.2 + Task 4.3（既有）
 *       x3-adjustment-entry-import-export / 任务 1.9（本轮扩：GS9 前端侧 + 四形态键提取）
 *
 * 后端测试读不到 `.vue`，前端 vitest 读不到 Python `_SPECS` → 两侧各自对照**同一份清单**断言：
 *   * Property 9  清单内 aligned 的 sheet：其 `item_id`（或 `ITEM_PREFIX` 拼接形态）必须在前端源码中
 *                 真实出现，且写入列与清单 `storage_field` 一致 —— **应有列由源码实测得出，
 *                 不是常量比较**（见下「E14」）。
 *   * Property 11 注册完整性：前端调整分录持久化键所属的每张 sheet，必须出现在清单
 *                 `sheets` 或 `exempt` 中；遗漏即失败（守卫遍历源码，不硬编码逐条清单）。
 *
 * ───────────────────────────────────────────────────────────────────────────────
 * 本轮（x3 spec 任务 1.9）改了什么
 * ───────────────────────────────────────────────────────────────────────────────
 * **E14 —— 守卫自身把错值锁成基线**：`Property 9 — storage_field 一致` 原文是
 * `expect(entry.storage_field).toBe('remark')`（硬常量）。该判据会把机制 ①
 * （`use{X}FormData.setField` ⇒ 恒写 `conclusion`）的 `N1-3`/`N2-3`/`N3-3`/`N5-3`
 * 判成违规。修法**不是**把常量换成 `'conclusion'`（那只是换一个错值），而是：
 *
 *   前端源码 ──实测──> 持久化机制 ──实测该机制实现的载荷键──> 应有列  ==  清单 storage_field
 *
 * 两条机制（design E18，16/16 无例外）：
 *   ① `use{X}FormData.setField(sheet, field, v)` → `saveField(itemId, { conclusion })`
 *   ② `use{X}Adjustment` 的 `saveBatch` / `debouncedSave(itemId, { remark })`
 * 列不写死在判据里 —— 由 `x3KeyProbe` 读机制实现源码的载荷对象字面量得出。
 *
 * **与后端守卫的分工（design §GS9 的完整判据 = 两侧之和）**：
 *   后端 `backend/tests/test_x3_key_ledger.py`（任务 1.1）的 `mechanism` **取清单登记值**
 *   ⇒ 只抓「清单内机制与列自相矛盾」；「机制本身是否与前端源码一致」后端读不到 `.vue`，
 *   由本文件承担。缺前端侧 ⇒ 一份「内部自洽但与前端不符」的清单能让后端全绿。
 *
 * **四形态键提取（design §C6 / R7.4）**：判据实现在 helper `x3KeyProbe.ts`，本文件是它的
 * 唯一消费方（helper 与消费方同任务交付；无消费方的 helper = additive 死代码）。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  X3_TARGET_CYCLES,
  X3_TARGET_SHEETS,
  X3_SHEET_NO,
  FORM3_RE,
  FORM3_SKELETON_FROM_TASK,
  LEGACY_HARDCODED_STORAGE_FIELD,
  STORAGE_COLUMNS,
  WP_ROOT,
  createSourceBundle,
  declaredEntryTypeCasing,
  declaredKeys,
  declaredStorageField,
  extractItemPrefixKeys,
  extractQuotedKeys,
  extractTemplateFamilyKeys,
  legacyConstantJudgement,
  loadContract,
  observeStorageColumn,
  probeAllX3,
  probeEntryTypeCasing,
  probeSheet,
  stripComments,
  type Mechanism,
  type SheetProbe,
  type StorageColumn,
} from '../../shared/__tests__/helpers/x3KeyProbe'

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

  /**
   * E14 修法：写入列由**源码实测**得出，再与清单比对。
   *
   * 旧判据 `expect(entry.storage_field).toBe('remark')` 是「守卫把错值锁成基线」的教科书
   * 形态 —— 一旦机制 ① 的 sheet 迁进 `sheets`（x3 spec 任务 2.1），它会把实测正确的
   * `conclusion` 判成违规。这里改为：`observeStorageColumn` 在全部调整分录源文件里找该
   * `item_id` 的写入点（`emit('save')` / `debouncedSave` / `saveField` / `saveBatch` /
   * `allResponses.set` 五种实测形态），取载荷对象字面量里的存储列 ⇒ 与清单登记值比对。
   * 判据内**不出现任何列名常量**。
   */
  it.each(alignedSheets.map(([s]) => s))(
    'Property 9 — %s 的写入列（源码实测）与清单 storage_field 一致',
    (sheet) => {
      const entry = CONTRACT.sheets[sheet]
      const itemId: string = entry.item_id
      const observed = observeStorageColumn(itemId, SOURCES)
      expect(
        observed.columns.length,
        `${sheet}: 在前端源码里实测不出 '${itemId}' 的唯一写入列（实测 ${observed.columns.length} 个：` +
          `${observed.columns.join('/') || '无'}）；依据链：${observed.trail.join(' | ') || '（空）'}`,
      ).toBe(1)
      expect(
        entry.storage_field,
        `${sheet}: 清单 storage_field='${entry.storage_field}'，但源码实测写入列是 ` +
          `'${observed.columns[0]}'（依据：${observed.trail.join(' | ')}）。` +
          '判据是「源码实测列」而非常量 —— 请改清单，不要改判据里的常量',
      ).toBe(observed.columns[0])
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

// ═══════════════════════════════════════════════════════════════════════════════
// x3-adjustment-entry-import-export / 任务 1.9
//   16 张 X-3 的四形态键提取判据 + 机制↔列判据（GS9 前端侧 / Property 8 / Property 10）
//
// 判据实现全在 helper `shared/__tests__/helpers/x3KeyProbe.ts`；本块是它的唯一消费方。
// 本块**只改判据**：不改 `adjustment_ie_contract.json`、不改任何生产代码。
// ⇒ 对清单**当前值**打红是预期（清单迁入与改值是 Wave 1 任务 2.1 的作业面）。
// ═══════════════════════════════════════════════════════════════════════════════

const PROBES: Record<string, SheetProbe> = probeAllX3()
const CONTRACT_DOC = loadContract()

/**
 * 清单 `status` 的两个取值。
 * - `aligned` = 后端 spec 已注册且与前端三重键对齐（既有 14 张，与本文件上方
 *   `alignedSheets` 的筛选口径同一个字面量）
 * - `pending_shared_impl` = 已迁入 `sheets`、但后端共享实现（`X3_SHEET_SPECS`）尚未交付，
 *   由 `backend/tests/test_adjustment_ie_contract_guard.py` 按该值**暂缓放行**（绿但 warning 报数）
 *   ⇒ 这两个字面量是与后端守卫共用的口径，不是本文件自造的常量
 */
const X3_ALIGNED_STATUS = 'aligned'
const X3_PENDING_STATUS = 'pending_shared_impl'
const X3_STANDIN_CYCLE = 'ZZ'
const X3_STANDIN_SHEET = `${X3_STANDIN_CYCLE}-${X3_SHEET_NO}`

/** 替身 A：完全没有持久化调用 ⇒ 键不可确证（R2.6 的 IF 分支，真实 16 张零实例）。 */
const STANDIN_TAB_NO_KEY = [
  '<template><div>zz 替身</div></template>',
  '<script setup lang="ts">',
  'import { ref } from "vue"',
  'const entries = ref<any[]>([])',
  'function saveEntries() { void entries }',
  '</script>',
].join('\n')

/**
 * 替身 B：形态④三步链在**步②断链**（`use{X}FormData` 无模块级 `ITEM_PREFIX`），
 * 但 tab 内**故意留一个同名字面量** `ZZ-3-entries`（中央同步键）。
 * 按「字面量 grep」会判「键已确证」，按三步链必须判「键不可确证」——
 * 这正是 design E12 → E17 / G11 那个坑的可执行复现。
 */
const STANDIN_TAB_CHAIN_BROKEN = [
  '<script setup lang="ts">',
  'import { ref } from "vue"',
  'import { useZZFormData } from "@/components/workpaper/composables/useZZFormData"',
  'import { useAdjustmentCentralSync } from "@/components/workpaper/composables/useAdjustmentCentralSync"',
  'const entries = ref<any[]>([])',
  'const formData = useZZFormData()',
  'useAdjustmentCentralSync({ wpCode: "ZZ", itemId: "ZZ-3-entries" })',
  'async function saveEntries() { await formData.setField("3", "entries", entries.value) }',
  '</script>',
].join('\n')

const STANDIN_FORMDATA_NO_PREFIX = [
  'export function useZZFormData() {',
  '  async function saveField(itemId: string, value: { conclusion?: string }) { void itemId; void value }',
  '  async function setField(sheet: string, field: string, value: any): Promise<void> {',
  "    const itemId = sheet + '-' + field",
  '    await saveField(itemId, { conclusion: String(value) })',
  '  }',
  '  return { setField, saveField }',
  '}',
].join('\n')

function readReal(rel: string): string {
  return fs.readFileSync(path.join(WP_ROOT, rel), 'utf8')
}

describe('X-3 四形态键提取 + 机制↔列判据（x3 spec 任务 1.9）', () => {
  // ─── 守卫自身有效性（反空转 / 反恒真） ─────────────────────────────────────

  it('探针扫描面非空且恰好覆盖 16 张作业面（否则判据恒真）', () => {
    expect(X3_TARGET_CYCLES).toHaveLength(16)
    expect(X3_TARGET_SHEETS).toHaveLength(16)
    expect(Object.keys(PROBES).sort()).toEqual([...X3_TARGET_SHEETS].sort())

    const noTab = X3_TARGET_SHEETS.filter((s) => !PROBES[s].files.tab)
    expect(noTab, '以下 sheet 的 {X}TabAdjustment.vue 读不到 ⇒ 判据无输入（空转）').toEqual([])
    const noComposable = X3_TARGET_SHEETS.filter(
      (s) => !PROBES[s].files.adjustment && !PROBES[s].files.formData,
    )
    expect(noComposable, '以下 sheet 既无 use{X}Adjustment.ts 也无 use{X}FormData.ts').toEqual([])
    const noTrail = X3_TARGET_SHEETS.filter((s) => PROBES[s].trail.length === 0)
    expect(noTrail, '以下 sheet 无任何依据链留痕 ⇒ 探针没真读到东西').toEqual([])
  })

  /**
   * 目标态判据（本条原文是 `expect(overlap).toEqual([])` = 「无任何 X-3 在 sheets 段」）。
   *
   * 🔴 那是**陈旧基线**，与本 spec 目标反向：任务 2.1 的作业面正是把 16 张迁进 `sheets`，
   * 迁完那刻它必红，而红的理由是「有人开始干活了」不是「目标态未达成」—— 属 memory
   * 「假绿三源」第③条「把错值当基线锁死」的镜像（任务 1.6 的缺陷 A 同型）。
   *
   * 改判后保留原意「不得与既有 `aligned` 段条目串味」，但把它落在**可观察事实**上而不是
   * 任务号或当前数字：
   *   `status === 'aligned'` ⟺ `backend_current.spec_registered === true` 且 `drift_dimensions` 为空
   * 今天 16 张的后端 spec 尚未交付（`_x3_adjustment_import_export.X3_SHEET_SPECS`，Wave 2
   * 任务 4.1）⇒ 谁被误标 `aligned` 谁红；任务 4.1 交付并回填 `backend_current` 之后，
   * 状态翻成 `aligned` 仍绿 ⇒ **不留第二个陈旧基线**。
   */
  it('作业面 16 张必须都在 sheets 段，且后端 spec 未就绪前不得串成 aligned', () => {
    const missing = X3_TARGET_SHEETS.filter((s) => !(s in CONTRACT_DOC.sheets))
    const registered = X3_TARGET_SHEETS.filter((s) => s in CONTRACT_DOC.sheets)
    expect(
      registered.length,
      `作业面 ${X3_TARGET_SHEETS.length} 张里只有 ${registered.length} 张在 sheets 段；` +
        `未登记 ${missing.length} 条：${missing.join(',') || '（无）'} —— 尚未迁入（Wave 1 任务 2.1）`,
    ).toBe(X3_TARGET_SHEETS.length)

    // 反空转：'aligned' 这个字面量必须在清单里真有实例（拼错/改名则本条判据形同虚设）
    const legacyAligned = Object.entries(CONTRACT_DOC.sheets)
      .filter(([s, e]) => !X3_TARGET_SHEETS.includes(s) && (e as any).status === X3_ALIGNED_STATUS)
      .map(([s]) => s)
    expect(
      legacyAligned.length,
      `清单里没有任何非 X-3 条目的 status === '${X3_ALIGNED_STATUS}' ⇒ 「不得误标 aligned」` +
        '这条判据无实例可比（空转）；请核对状态枚举是否已改名',
    ).toBeGreaterThanOrEqual(14)
    expect(
      legacyAligned.filter((s) => X3_TARGET_SHEETS.includes(s)),
      '既有 aligned 段与作业面串味（同一 sheet 两套口径）',
    ).toEqual([])

    // 逐张：状态必须与「后端 spec 是否已注册」这一事实一致
    const mislabeled: string[] = []
    const wrongPending: string[] = []
    const noOwner: string[] = []
    for (const s of registered) {
      const e = CONTRACT_DOC.sheets[s] as any
      const backendReady = (e.backend_current ?? {}).spec_registered === true
      const drift = (e.drift_dimensions ?? []) as string[]
      if (e.status === X3_ALIGNED_STATUS) {
        if (!backendReady || drift.length) {
          mislabeled.push(
            `${s}（backend_current.spec_registered=${backendReady} / drift_dimensions=${JSON.stringify(drift)}）`,
          )
        }
        continue
      }
      if (!backendReady && e.status !== X3_PENDING_STATUS) {
        wrongPending.push(`${s}: status='${e.status}'`)
      }
      if (!e.aligns_in_task) noOwner.push(s)
    }
    expect(
      mislabeled,
      `以下 X-3 被标成 '${X3_ALIGNED_STATUS}'，但后端 spec 尚未注册（或仍带漂移维度）⇒ ` +
        '与既有 aligned 段串味了。后端共享实现由 Wave 2 任务 4.1 交付，交付并回填 ' +
        'backend_current.spec_registered=true / 清空 drift_dimensions 之后才允许标 aligned',
    ).toEqual([])
    expect(
      wrongPending,
      `后端 spec 未就绪的条目其 status 必须是清单/后端守卫共用的暂缓态 '${X3_PENDING_STATUS}'` +
        '（backend/tests/test_adjustment_ie_contract_guard.py 按该值暂缓放行）',
    ).toEqual([])
    expect(noOwner, '未对齐的条目必须用 aligns_in_task 自报承接任务（否则无人认领）').toEqual([])
  })

  it('注释剥离器生效，且不误剥普通字面量（stripComments 反向自检）', () => {
    const src = [
      "// const FAKE = 'M4-3-entry-1-desc'",
      "/* const ALSO_FAKE = 'M4-3-entry-2-desc' */",
      "const REAL = 'M4-3-real-key'",
      '`M4-3-entry-${n}-desc`',
    ].join('\n')
    const stripped = stripComments(src)
    expect(extractQuotedKeys(stripped)).toEqual(['M4-3-real-key'])
    expect(extractTemplateFamilyKeys(stripped).map((h) => h.familyKey)).toEqual(['M4-3-entry-*'])
    // 偏移量保持（剥掉的字符用空格/换行替换）⇒ 长度不变，任何按位置回看的判据不串行
    expect(stripped.length).toBe(src.length)
  })

  it('四个形态提取器各有正负对照（防恒真/恒假）', () => {
    // 形态①
    expect(extractQuotedKeys("const A = 'L2-L2-3-entries'")).toEqual(['L2-L2-3-entries'])
    expect(extractQuotedKeys("const A = 'hello world'")).toEqual([])
    // 形态②
    const form2 = ["const ITEM_PREFIX = 'K3-3-adj'", 'save(`${ITEM_PREFIX}-entries`)'].join('\n')
    expect(extractItemPrefixKeys(form2)).toEqual(['K3-3-adj-entries'])
    expect(extractItemPrefixKeys('save(`${ITEM_PREFIX}-entries`)')).toEqual([])
    // 形态③（含双前缀变体、camelCase 后缀）
    expect(extractTemplateFamilyKeys('`M4-3-entry-${n}-desc`').map((h) => h.familyKey)).toEqual([
      'M4-3-entry-*',
    ])
    expect(extractTemplateFamilyKeys('`L6-L6-3-entry-${n}-type`').map((h) => h.keyPrefix)).toEqual([
      'L6-L6-3',
    ])
    expect(extractTemplateFamilyKeys('`M9-3-entry-${n}-ociBlock`')[0].suffix).toBe('ociBlock')
    expect(extractTemplateFamilyKeys("'M4-3-adjustment'")).toEqual([])
    // 形态④由 probeSheet 的三步链承担，正对照 = 真实 4 张、负对照 = 下方替身两条
  })

  it('形态② 在既有源码里有真实命中（否则该形态判据在本仓库无实例可证）', () => {
    const hits = [...SOURCES.entries()].filter(
      ([, raw]) => extractItemPrefixKeys(stripComments(raw)).length > 0,
    )
    expect(hits.length, '全库无一处 ITEM_PREFIX 拼接形态 ⇒ 形态②提取器无实例').toBeGreaterThan(0)
  })

  // ─── R2.3 / R2.6：逐张键可确证 ──────────────────────────────────────────────

  it.each(X3_TARGET_SHEETS)('R2.3 — %s 的数据键可从前端源码确证（四形态）', (sheet) => {
    const p = PROBES[sheet]
    expect(
      p.confirmed,
      `${sheet}: 键不可确证 ⇒ ${p.reasons.join(' / ') || '（无理由，探针缺陷）'}；` +
        `已取得依据链：${p.trail.join(' | ') || '（空）'}`,
    ).toBe(true)
    expect(p.entryKeys.length, `${sheet}: 未取得任何 entries 数据键`).toBeGreaterThan(0)
    expect(p.mechanism, `${sheet}: 持久化机制判不出`).not.toBeNull()
    expect(p.column, `${sheet}: 写入列实测不出`).not.toBeNull()
  })

  it('R2.6 — 真实 16 张的 pending_manual 集合为空（用户裁决 1）', () => {
    const pending = X3_TARGET_SHEETS.filter((s) => PROBES[s].pendingManual)
    expect(
      pending,
      '裁决 1 已把 16 张全部纳入作业面（含 N5-3，其键由形态④三步链确证）⇒ 不应有待人工核项',
    ).toEqual([])
  })

  it('R2.6 — 键不可确证的 sheet 替身被标 pending_manual（零实例分支用替身覆盖）', () => {
    const sources = createSourceBundle({
      [`${X3_STANDIN_CYCLE.toLowerCase()}/core/${X3_STANDIN_CYCLE}TabAdjustment.vue`]:
        STANDIN_TAB_NO_KEY,
      [`composables/use${X3_STANDIN_CYCLE}Adjustment.ts`]: null,
      [`composables/use${X3_STANDIN_CYCLE}FormData.ts`]: null,
    })
    const p = probeSheet(X3_STANDIN_CYCLE, { sources })
    expect(p.sheet).toBe(X3_STANDIN_SHEET)
    expect(p.confirmed).toBe(false)
    expect(p.pendingManual, '键不可确证的 sheet 必须被标待人工核，而不是静默放过').toBe(true)
    expect(p.reasons.length, 'pending 必须带可读理由（fail-loud）').toBeGreaterThan(0)
    expect(p.entryKeys).toEqual([])
  })

  it('R2.6 — 形态④链断（步②无 ITEM_PREFIX）亦标 pending_manual，且不被同名字面量蒙对', () => {
    const tabRel = `${X3_STANDIN_CYCLE.toLowerCase()}/core/${X3_STANDIN_CYCLE}TabAdjustment.vue`
    const sources = createSourceBundle({
      [tabRel]: STANDIN_TAB_CHAIN_BROKEN,
      [`composables/use${X3_STANDIN_CYCLE}Adjustment.ts`]: null,
      [`composables/use${X3_STANDIN_CYCLE}FormData.ts`]: STANDIN_FORMDATA_NO_PREFIX,
    })
    // 前提：替身 tab 里**确实**有 `ZZ-3-entries` 这个字面量（按字面量 grep 会判「已确证」）
    expect(STANDIN_TAB_CHAIN_BROKEN).toContain(`'${X3_STANDIN_SHEET}-entries'`.replace(/'/g, '"'))
    const p = probeSheet(X3_STANDIN_CYCLE, { sources })
    expect(p.centralSyncKeys, '同名字面量应被识别为中央同步键').toContain(
      `${X3_STANDIN_SHEET}-entries`,
    )
    expect(p.pendingManual, '三步链断在步② ⇒ 必须判键不可确证（不得因同名字面量蒙对）').toBe(true)
    expect(p.reasons.join(' ')).toContain('ITEM_PREFIX')
    expect(p.entryKeys).toEqual([])
  })

  // ─── R2.4：排除复核键与中央同步键 ───────────────────────────────────────────

  it('R2.4 — 复核键排除集非空，且不与数据键相交', () => {
    const withReview = X3_TARGET_SHEETS.filter((s) => PROBES[s].reviewKeys.length > 0)
    // 反空转：11 张实测有复核键（L2-3 + M1-3~M10-3），正是清单缺陷 B 的那 11 条
    expect(
      withReview.length,
      '一张复核键都没抓到 ⇒ 排除判据空转（M 族实测写法是 openReviewDialog?.(…) 可选调用）',
    ).toBeGreaterThanOrEqual(11)
    const bad: string[] = []
    for (const s of X3_TARGET_SHEETS) {
      const p = PROBES[s]
      for (const k of p.entryKeys) if (p.reviewKeys.includes(k)) bad.push(`${s}: ${k}`)
    }
    expect(bad, '复核键被收进了数据键集（R2.4 违反）').toEqual([])
  })

  it('R2.4 — 中央同步键不进数据键，除非该键另由形态④三步链确证（G11）', () => {
    const bad: string[] = []
    for (const s of X3_TARGET_SHEETS) {
      const p = PROBES[s]
      for (const k of p.entryKeys) {
        if (!p.centralSyncKeys.includes(k)) continue
        // 同名但来源已证（形态④）⇒ 合法；否则即「把中央同步键当数据键」
        if (!p.forms.includes('cross_file_runtime')) bad.push(`${s}: ${k}`)
      }
    }
    expect(bad, '中央同步键被当成数据键收录（且无形态④链证）').toEqual([])
  })

  it('G11 实证 — N5-3 的中央同步键与真数据键同名不同源，键仍被确证', () => {
    const p = PROBES['N5-3']
    expect(p.centralSyncKeys, 'tab 内那个字面量属中央同步键').toContain('N5-3-entries')
    expect(p.entryKeys, '真数据键由 ITEM_PREFIX + sheet + field 三段在运行期拼出').toEqual([
      'N5-3-entries',
    ])
    expect(p.forms, '该键的来源必须是形态④（跨文件运行期拼装）').toContain('cross_file_runtime')
    expect(p.confirmed, 'E12 的结论已被 E17 推翻：N5-3 键可确证').toBe(true)
    expect(p.trail.join(' | ')).toContain('ITEM_PREFIX')
  })

  // ─── R7.4：形态③ 骨架与旧判据的洞 ──────────────────────────────────────────

  it('R7.4 — 形态③ 在真实源码里有命中并归约为族键', () => {
    const families = new Map<string, string[]>()
    for (const s of X3_TARGET_SHEETS) {
      const p = PROBES[s]
      const fam = p.entryKeys.filter((k) => k.endsWith('-entry-*'))
      if (fam.length) families.set(s, fam)
    }
    // 实测 11 张走逐字段族（L6-3 / M1-3 ~ M10-3）
    expect(families.size, '形态③在真实源码零命中 ⇒ 该形态判据空转').toBeGreaterThanOrEqual(11)
    // M9-3 的后缀实测 11 项（多一个 ociBlock，design E20）；其余为 10 项
    expect(PROBES['M9-3'].perFieldSuffixes).toContain('ociBlock')
    expect(PROBES['M9-3'].perFieldSuffixes.length).toBe(11)
    expect(PROBES['M4-3'].perFieldSuffixes.length).toBe(10)
    // 双前缀变体实测存在（L6 / M1 / M2 / M3）
    const doublePrefix = X3_TARGET_SHEETS.filter((s) =>
      PROBES[s].entryKeys.some((k) => /^([A-Z]\d{0,2})-\1-/.test(k)),
    )
    expect(doublePrefix.length, '双前缀变体一个都没命中 ⇒ 骨架漏了该变体').toBeGreaterThan(0)
  })

  it('R7.4 — 任务原文骨架对真实源码零命中（留痕：实现用 FORM3_RE，形态语义不变）', () => {
    let skeletonHits = 0
    let implHits = 0
    for (const [, raw] of SOURCES) {
      const s = stripComments(raw)
      skeletonHits += [...s.matchAll(FORM3_SKELETON_FROM_TASK)].length
      implHits += [...s.matchAll(FORM3_RE)].length
    }
    expect(
      skeletonHits,
      '任务/design 原文骨架要求键前缀本身来自插值（`${M4}-3-entry-…`），而实测写法是字面量前缀' +
        '（`M4-3-entry-…`）⇒ 原文骨架零命中；实现改用 FORM3_RE，形态语义不变',
    ).toBe(0)
    expect(implHits, 'FORM3_RE 在真实源码必须有命中').toBeGreaterThan(0)
  })

  it('旧提取判据抓不到形态③、且把复核键当数据键（证明新判据补的是真洞）', () => {
    const missedFamily: string[] = []
    const legacyTookReviewKey: string[] = []
    for (const s of X3_TARGET_SHEETS) {
      const p = PROBES[s]
      if (!p.entryKeys.some((k) => k.endsWith('-entry-*'))) continue
      const rels = [p.files.tab, p.files.adjustment].filter(Boolean) as string[]
      const legacy = new Set<string>()
      for (const rel of rels) {
        const abs = path.join(WP_ROOT, rel)
        if (!fs.existsSync(abs)) continue
        for (const k of extractKeys(fs.readFileSync(abs, 'utf8'))) legacy.add(k)
      }
      if (![...legacy].some((k) => k.includes('-entry-'))) missedFamily.push(s)
      if (p.reviewKeys.some((k) => legacy.has(k))) legacyTookReviewKey.push(s)
    }
    expect(
      missedFamily.length,
      '旧判据本应抓不到形态③族键（这是缺陷 B 的成因之一）；若现在抓到了，说明旧判据已被别处改过',
    ).toBeGreaterThanOrEqual(11)
    expect(
      legacyTookReviewKey.length,
      '旧判据本应把复核键当数据键收录（缺陷 B 的 11 条成因）',
    ).toBeGreaterThanOrEqual(10)
  })

  // ─── Property 10 / GS9 前端侧：机制↔列 ─────────────────────────────────────

  it('机制划分非退化：两条机制各推出不同的列且都有实例（防判据塌成常量）', () => {
    const byMech = new Map<Mechanism, Set<StorageColumn>>()
    for (const s of X3_TARGET_SHEETS) {
      const p = PROBES[s]
      if (!p.mechanism || !p.column) continue
      if (!byMech.has(p.mechanism)) byMech.set(p.mechanism, new Set())
      byMech.get(p.mechanism)!.add(p.column)
    }
    expect([...byMech.keys()].sort()).toEqual(['adjustment_savebatch', 'formdata_setfield'])
    for (const [m, cols] of byMech) {
      expect([...cols].length, `机制 ${m} 推出多个列 ${[...cols].join('/')} ⇒ 机制不足以定列`).toBe(1)
    }
    const cols = [...byMech.values()].map((set) => [...set][0])
    expect(new Set(cols).size, '两条机制推出同一个列 ⇒「机制推导」已退化成常量比较').toBe(2)
    for (const c of cols) expect(STORAGE_COLUMNS).toContain(c)
    // 机制分布钉死 design E18 §机制归类：① 4 张 / ② 12 张
    const m1 = X3_TARGET_SHEETS.filter((s) => PROBES[s].mechanism === 'formdata_setfield')
    const m2 = X3_TARGET_SHEETS.filter((s) => PROBES[s].mechanism === 'adjustment_savebatch')
    expect(m1).toEqual(['N1-3', 'N2-3', 'N3-3', 'N5-3'])
    expect(m2).toHaveLength(12)
  })

  it.each(X3_TARGET_SHEETS)(
    'Property 10 — %s 的清单 storage_field == 由持久化机制推导的列',
    (sheet) => {
      const p = PROBES[sheet]
      expect(p.mechanism, `${sheet}: 机制判不出（${p.reasons.join(' / ')}）`).not.toBeNull()
      expect(p.column, `${sheet}: 机制实现源码里实测不出写入列`).not.toBeNull()
      const decl = declaredStorageField(CONTRACT_DOC, sheet)
      expect(
        decl.value,
        `${sheet}: 清单未登记写入列（${decl.from}）—— 尚未登记（Wave 1 任务 2.1）；` +
          `源码实测机制=${p.mechanism} ⇒ 应有列 '${p.column}'（依据：${p.trail.join(' | ')}）`,
      ).not.toBeNull()
      expect(
        decl.value,
        `${sheet}: 清单登记列 '${decl.value}'（${decl.from}）≠ 机制 ${p.mechanism} 推导列 ` +
          `'${p.column}'（依据：${p.trail.join(' | ')}）。判据锚在源码实测上，请改清单不要改判据`,
      ).toBe(p.column)
    },
  )

  it('E14 回归锚点 — 旧常量判据会把机制①的 4 张判违规，机制判据不会', () => {
    const mech1 = X3_TARGET_SHEETS.filter((s) => PROBES[s].mechanism === 'formdata_setfield')
    expect(mech1).toEqual(['N1-3', 'N2-3', 'N3-3', 'N5-3'])
    const legacyViolations = mech1.filter((s) => !legacyConstantJudgement(PROBES[s].column))
    expect(
      legacyViolations,
      '旧判据（硬断言 storage_field === 常量）本应把这 4 张全判违规 —— 这就是 E14 的守卫缺陷本体',
    ).toEqual(mech1)
    for (const s of mech1) {
      expect(PROBES[s].column, `${s}: 机制①的实测列不该等于旧常量`).not.toBe(
        LEGACY_HARDCODED_STORAGE_FIELD,
      )
    }
    // 机制②的 12 张实测列恰是旧常量 ⇒ 旧判据「碰对了 12 张」正是它长期被误认为正确的原因
    const mech2 = X3_TARGET_SHEETS.filter((s) => PROBES[s].mechanism === 'adjustment_savebatch')
    for (const s of mech2) {
      expect(PROBES[s].column, `${s}: 机制②实测列应为旧常量同值`).toBe(
        LEGACY_HARDCODED_STORAGE_FIELD,
      )
    }
  })

  // ─── R7.5：重扫结果与清单 observed 逐条一致 ────────────────────────────────

  it.each(X3_TARGET_SHEETS)('R7.5 — %s 清单 observed 键集 == 修正判据后的重扫键集', (sheet) => {
    const p = PROBES[sheet]
    const decl = declaredKeys(CONTRACT_DOC, sheet)
    const rescanned = [...new Set([...p.entryKeys, ...p.otherDataKeys])].sort()
    expect(
      decl.keys.length,
      `${sheet}: 清单无任何 observed 键（${decl.from}）—— 尚未登记（Wave 1 任务 2.1）；` +
        `重扫结果应为 ${JSON.stringify(rescanned)}`,
    ).toBeGreaterThan(0)
    // 防「扩口径」变成绕过 item_id 的口子：`declaredKeys` 现在读 observed 的两个数组
    // （任务 3：一张表可以有 entries 族键 + 表级独立键两个数据落点），故必须另行钉住
    // 三重键之一的 `item_id` 仍在这个键集里，否则 observed 可以与 item_id 各说各话。
    const declaredItemId = (CONTRACT_DOC.sheets?.[sheet] ?? {}).item_id
    if (typeof declaredItemId === 'string') {
      expect(
        decl.keys,
        `${sheet}: 清单 item_id='${declaredItemId}' 不在 observed 键集 ${JSON.stringify(decl.keys)} 里 ` +
          `（${decl.from}）⇒ 三重键与实测键集自相矛盾`,
      ).toContain(declaredItemId)
    }
    const stray = decl.keys.filter((k) => p.reviewKeys.includes(k))
    expect(
      stray,
      `${sheet}: 清单 observed 记的是复核键 ${JSON.stringify(stray)}（openReviewDialog 的实参，` +
        `R2.4 要求排除）—— 尚未修正（Wave 1 任务 2.1）；重扫的真数据键为 ${JSON.stringify(rescanned)}`,
    ).toEqual([])
    expect(
      decl.keys,
      `${sheet}: 清单 observed ${JSON.stringify(decl.keys)} 与重扫键集 ${JSON.stringify(rescanned)} 不一致`,
    ).toEqual(rescanned)
  })

  // ─── 四条反向自检落成永久断言（每次跑都机器校验，不靠一次性手工变异） ───────

  /**
   * 篡改点必须落在**该 sheet 实际的登记位置**上。
   *
   * 🔴 本条原文把路径硬编码成 `tampered.exempt['N1-3'].observed.frontend_field`，而任务 2.1
   * 的目的正是把 `N1-3` 迁出 `exempt` ⇒ 迁完后该路径为 `undefined`，自检本体先抛
   * `TypeError: Cannot read properties of undefined`。结构上不可能两全：要满足旧写法就得让
   * `N1-3` 留在 `exempt`，那会同时打红后端 `test_no_x3_left_in_exempt_section` 与
   * `test_class_b_worksheet_scope_locked_by_contract`。改为按 `declaredStorageField` 实际
   * 读取的那一处篡改 ⇒ 对「已迁入 sheets」与「仍在 exempt」两种位置都成立。
   */
  it('反向自检(a) — 篡改清单登记列 ⇒ 判据必判不一致', () => {
    const sheet = 'N1-3'
    const p = PROBES[sheet]
    const base = declaredStorageField(CONTRACT_DOC, sheet)
    expect(base.value, `${sheet} 基线：清单登记列应与机制推导列一致`).toBe(p.column)
    const otherColumn = STORAGE_COLUMNS.find((c) => c !== p.column) as StorageColumn
    const tampered = JSON.parse(JSON.stringify(CONTRACT_DOC))

    // 按实际登记位置篡改（两种位置都覆盖），并断言篡改真的落到了判据读取的那一处
    let hit = ''
    if (tampered.sheets?.[sheet] && typeof tampered.sheets[sheet].storage_field === 'string') {
      tampered.sheets[sheet].storage_field = otherColumn
      hit = `sheets.${sheet}.storage_field`
    } else if (tampered.exempt?.[sheet]?.observed) {
      tampered.exempt[sheet].observed.frontend_field = otherColumn
      hit = `exempt.${sheet}.observed.frontend_field`
    }
    expect(
      hit,
      `${sheet} 在清单里既不在 sheets 段也不在 exempt 段 ⇒ 篡改锚点未命中（ANCHOR-MISS），` +
        '本自检对该 sheet 无效，请先核对清单结构',
    ).not.toBe('')
    expect(
      hit,
      `篡改位置 '${hit}' 与判据实际读取位置 '${base.from}' 不一致 ⇒ 自检打不到判据身上`,
    ).toBe(base.from)

    expect(declaredStorageField(tampered, sheet).value).toBe(otherColumn)
    expect(
      declaredStorageField(tampered, sheet).value === p.column,
      '把清单登记列改成另一列后判据仍认为一致 ⇒ 判据对清单值不敏感（空转）',
    ).toBe(false)
  })

  it('反向自检(b) — 强制机制探针返另一种机制 ⇒ 判据必判不一致', () => {
    const sheet = 'N2-3'
    const cycle = 'N2'
    const base = probeSheet(cycle)
    expect(base.mechanism).toBe('formdata_setfield')
    expect(declaredStorageField(CONTRACT_DOC, sheet).value, '基线应一致（绿）').toBe(base.column)
    const forced = probeSheet(cycle, { mechanismOverride: { [sheet]: 'adjustment_savebatch' } })
    expect(forced.mechanism).toBe('adjustment_savebatch')
    expect(forced.column, '被强制的机制必须重新推出它自己的列').not.toBe(base.column)
    expect(
      declaredStorageField(CONTRACT_DOC, sheet).value === forced.column,
      '换了机制而判据结论不变 ⇒「机制推导」是摆设，判据实际仍在比常量',
    ).toBe(false)
  })

  it('反向自检(c) — 改 use{X}FormData 的 ITEM_PREFIX ⇒ 该 sheet 判键不可确证', () => {
    const fdRel = 'composables/useN5FormData.ts'
    const tabRel = 'n5/core/N5TabAdjustment.vue'
    const fdReal = readReal(fdRel)
    const tabReal = readReal(tabRel)
    // 前提留痕：tab 内**确实**有巧合同名的 'N5-3-entries' 字面量（中央同步键）
    expect(tabReal).toContain("'N5-3-entries'")
    expect(fdReal).toMatch(/ITEM_PREFIX\s*=\s*'N5-'/)

    // (c1) 改名：ITEM_PREFIX → 别的标识符 ⇒ 步②取不到键前缀
    const renamed = probeSheet('N5', {
      sources: createSourceBundle({
        [fdRel]: fdReal.replace(/\bITEM_PREFIX\b/g, 'ITEM_PREFIX_RENAMED'),
      }),
    })
    expect(
      renamed.pendingManual,
      'ITEM_PREFIX 改名后仍判「键已确证」⇒ 说明是被 tab 里那个同名字面量蒙对的',
    ).toBe(true)
    expect(renamed.entryKeys).toEqual([])

    // (c2) 改值：ITEM_PREFIX 'N5-' → 'N5X-' ⇒ 拼出的键无法归属本 sheet
    const revalued = probeSheet('N5', {
      sources: createSourceBundle({
        [fdRel]: fdReal.replace(/ITEM_PREFIX\s*=\s*'N5-'/, "ITEM_PREFIX = 'N5X-'"),
      }),
    })
    expect(revalued.pendingManual, 'ITEM_PREFIX 改值后必须判键不可确证').toBe(true)
    expect(revalued.reasons.join(' ')).toContain('N5X-3-entries')
  })

  it('反向自检(d) — 改 tab 的 setField 实参 ⇒ 键判据必红', () => {
    const tabRel = 'n5/core/N5TabAdjustment.vue'
    const tabReal = readReal(tabRel)
    expect(tabReal).toMatch(/setField\('3',\s*'entries'/)

    // (d1) 改 field 实参 ⇒ 拼出的键变了 ⇒ 与清单登记键不再相等（R7.5 判据红）
    const fieldChanged = probeSheet('N5', {
      sources: createSourceBundle({
        [tabRel]: tabReal.replace(/setField\('3',\s*'entries'/g, "setField('3', 'entriesX'"),
      }),
    })
    expect(fieldChanged.entryKeys).toEqual(['N5-3-entriesX'])
    expect(
      fieldChanged.entryKeys.includes('N5-3-entries'),
      'setField 实参改了而拼出的键没变 ⇒ 键其实是从 tab 里那个同名字面量读来的（蒙对）',
    ).toBe(false)

    // (d2) 改 sheet 实参 ⇒ 该调用不属本 sheet ⇒ 键不可确证
    const sheetChanged = probeSheet('N5', {
      sources: createSourceBundle({
        [tabRel]: tabReal.replace(/setField\('3',\s*'entries'/g, "setField('9', 'entries'"),
      }),
    })
    expect(sheetChanged.pendingManual, 'sheet 实参改掉后必须判键不可确证').toBe(true)
    expect(sheetChanged.entryKeys).toEqual([])
  })
})

// ─── R3.5 · AJE / RJE 枚举**大小写**：清单登记值 ↔ 前端源码实测值（任务 2.4）──────
//
// 🔴 这一组补的是一个**实测出来的 GREEN**（任务 2.4 变异 MUT-1）：把 `M4-3` 的登记从
// 大写改成小写 `取值 'aje' | 'rje'` 后，后端 `test_x3_key_ledger.py` 的 235 条判据
// **一条都没红** —— 因为后端只能「实现落的值 ↔ 清单登记的值」互比，清单错了实现照错落，
// 两侧逐字相等。用户侧的后果是导入的行从界面按 AJE / RJE 分区的视图里消失
// （`filter` 全不命中 = 静默丢行）。大小写的真源只有前端源码里「界面按什么值 filter」，
// 而后端读不到 `.vue` ⇒ 这一路只能落在这里（与 §GS9 机制探针同一分工）。
describe('X-3 entryType 枚举大小写（x3 spec 任务 2.4，R3.5 / R2.8）', () => {
  const CASING_DECLARED = X3_TARGET_SHEETS.map((sheet) => ({
    sheet,
    declared: declaredEntryTypeCasing(CONTRACT_DOC, sheet),
  }))

  function probeFor(sheet: string, field: string) {
    return probeEntryTypeCasing(sheet.split('-')[0], field)
  }

  it('反空转 — 16 张必须都能从源码判出两个方向，且实测出 ≥2 种拼写', () => {
    expect(X3_TARGET_SHEETS).toHaveLength(16)
    const broken: string[] = []
    const spellings = new Set<string>()
    let evidenceLines = 0
    for (const { sheet, declared } of CASING_DECLARED) {
      const field = declared.field
      if (!field) {
        broken.push(`${sheet}: 清单未登记 entryType 字段名（${declared.from}）`)
        continue
      }
      const probe = probeFor(sheet, field)
      evidenceLines += probe.trail.length
      if (probe.reasons.length) {
        broken.push(`${sheet}: ${probe.reasons.join(' / ')}`)
        continue
      }
      spellings.add(`${probe.values.AJE}|${probe.values.RJE}`)
    }
    expect(broken, '源码侧判不出大小写 ⇒ 下面那条「清单 == 实测」会退化成空转').toEqual([])
    expect(evidenceLines, '证据行总数过少 ⇒ 探针大概率什么都没扫到').toBeGreaterThan(60)
    // 实测两种：15 张大写 `AJE|RJE` + `N5-3` 小写 `aje|rje`。塌成 1 种 ⇒ 探针在返常量
    expect(
      spellings.size,
      `作业面只实测出 ${spellings.size} 种拼写 ${JSON.stringify([...spellings])} ⇒ ` +
        '探针可能在返回常量而不是真读源码（已知 N5-3 是小写、其余 15 张是大写）',
    ).toBeGreaterThanOrEqual(2)
  })

  it.each(X3_TARGET_SHEETS)('逐张 %s — 清单登记的大小写 == 前端源码实测字面量', (sheet) => {
    const declared = declaredEntryTypeCasing(CONTRACT_DOC, sheet)
    expect(declared.field, `${sheet} 清单未登记 entryType 字段名（${declared.from}）`).toBeTruthy()
    const probe = probeFor(sheet, declared.field as string)
    expect(probe.reasons, `${sheet} 源码侧判不出大小写：${probe.reasons.join(' / ')}`).toEqual([])

    const observed = { AJE: probe.values.AJE, RJE: probe.values.RJE }
    expect(
      declared.values,
      `${sheet} 的 AJE/RJE 枚举大小写尚未登记在清单（${declared.from}）。` +
        `前端实测 ${JSON.stringify(observed)} ⇒ 未登记时共享实现拒写该键，` +
        '界面按 AJE / RJE 分区的视图看不到导入的行（补登去向 = 任务 2.4）',
    ).not.toBeNull()
    expect(
      declared.values,
      `${sheet} 清单登记 ${JSON.stringify(declared.values)} 与前端源码实测 ` +
        `${JSON.stringify(observed)} 不一致 ⇒ **登记错了大小写**。后端守卫抓不到这一类` +
        '（它只能拿实现和清单互比），而导入行会从两个分区里同时消失。依据链：\n' +
        probe.trail.map((t) => `    ${t}`).join('\n'),
    ).toEqual(observed)
  })

  it('反向自检 — 篡改清单登记的大小写 ⇒ 判据必判不一致', () => {
    const victim = 'M4-3'
    const tampered = JSON.parse(JSON.stringify(CONTRACT_DOC))
    const items: any[] = tampered.sheets?.[victim]?.unmapped_fields ?? []
    const idx = items.findIndex(
      (it) => it && typeof it.handling === 'string' && /AJE\s*\/\s*RJE\s*标记/.test(it.handling),
    )
    expect(idx, `篡改锚点未命中（ANCHOR-MISS）：${victim} 无「AJE/RJE 标记」条目`).toBeGreaterThanOrEqual(0)
    const before: string = items[idx].handling
    const after = before.replace(/取值\s*'AJE'\s*\|\s*'RJE'/, "取值 'aje' | 'rje'")
    expect(after, `篡改锚点未命中（ANCHOR-MISS）：${victim} 的「取值 'AJE' | 'RJE'」未替换`).not.toBe(before)
    items[idx].handling = after

    const declared = declaredEntryTypeCasing(tampered, victim)
    expect(declared.values).toEqual({ AJE: 'aje', RJE: 'rje' })
    const probe = probeFor(victim, declared.field as string)
    expect(probe.reasons).toEqual([])
    // 判据的核心：篡改后「清单 == 实测」必须不成立
    expect(
      declared.values,
      '篡改了清单登记的大小写，判据却仍判一致 ⇒ 判据没在比前端实测值（空转）',
    ).not.toEqual({ AJE: probe.values.AJE, RJE: probe.values.RJE })
    // 真实清单未被动过（只改内存副本）
    expect(declaredEntryTypeCasing(CONTRACT_DOC, victim).values).toEqual({ AJE: 'AJE', RJE: 'RJE' })
  })

  it('反向自检 — 改前端源码的 filter 字面量 ⇒ 实测值随之改变（不是在读清单）', () => {
    const rel = 'composables/useM4Adjustment.ts'
    const real = readReal(rel)
    expect(real, '锚点未命中（ANCHOR-MISS）').toMatch(/e\.type === 'AJE'/)
    const mutated = probeEntryTypeCasing('M4', 'type', {
      sources: createSourceBundle({
        [rel]: real
          .replace(/'AJE' \| 'RJE'/g, "'Aje' | 'Rje'")
          .replace(/e\.type === 'AJE'/g, "e.type === 'Aje'")
          .replace(/e\.type === 'RJE'/g, "e.type === 'Rje'")
          .replace(/activeType\.value === 'AJE'/g, "activeType.value === 'Aje'")
          .replace(/ref<M4AdjustmentType>\('AJE'\)/g, "ref<M4AdjustmentType>('Aje')"),
      }),
    })
    expect(
      mutated.values,
      `改了源码里的字面量而实测值没变 ⇒ 探针在读清单或返常量（reasons=${mutated.reasons.join(' / ')}）`,
    ).toEqual({ AJE: 'Aje', RJE: 'Rje' })
  })

  it('刻意不采信跨底稿推送载荷的 adjustmentType（16 张实测全小写，误采信会全判矛盾）', () => {
    // `adjustmentType: activeType.value === 'RJE' ? 'rje' : 'aje'` 是 A13 / B50 推送载荷
    // 的字段，与行模型 `type` 是两个字段。若把它当证据，15 张大写 sheet 会全部「自相矛盾」。
    const rel = 'l6/core/L6TabAdjustment.vue'
    const real = readReal(rel)
    expect(real, '锚点未命中（ANCHOR-MISS）').toMatch(/adjustmentType:\s*activeType\.value === 'RJE' \? 'rje' : 'aje'/)
    const probe = probeEntryTypeCasing('L6', 'type')
    expect(probe.reasons).toEqual([])
    expect(probe.values).toEqual({ AJE: 'AJE', RJE: 'RJE' })
    expect(probe.trail.join('\n')).not.toContain('adjustmentType')
  })
})
