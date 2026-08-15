/**
 * G7 披露表列结构「三向对齐」守卫 —— 边③（源 xlsx ↔ 运行时）
 *
 * spec: g7-column-alignment-and-extraction-closure Task 3
 *
 * ## 为什么需要这个文件
 *
 * G7 披露表列结构有三个真源：**源 xlsx** / **模板 seed（note_template JSON）** / **运行时
 * （前端 build*Columns）**。既有守卫只锁两条边：
 *
 * - `backend/tests/test_note_g7_structure.py` 覆盖 源xlsx↔seed（对运行时模型引用数 **0**）
 * - `.../composables/__tests__/_disclosureSubtableContract.helper.ts` 覆盖 seed↔运行时
 *   （对 xlsx 引用数 **0**，且其 group/flat 判据只对主章节生效）
 *
 * 于是 seed 可以同时「与源 xlsx 一致」且「与运行时不一致」—— 两条边各自全绿多轮，
 * 而列偏差长期存在。本文件建立第三条边。
 *
 * ## 🔴 本守卫完成时**预期是红的**，但要区分两种红
 *
 * - ✅ **期望的红** = `describe('六维逐表比对 …')` 里报出偏差（Wave 2/3 才修代码）。
 * - ❌ **不期望的红** = `describe('判据自检与结构性防回退 …')` 里的任何失败
 *   （反向自检 / 扫描面自检 / 源码结构断言 / 三端文件读不到）—— 说明**守卫本身坏了**，
 *   此时六维比对的红是噪声，不可作为「代码有偏差」的证据。
 *
 * 故两组断言**必须留在不同的 describe 块**：前者必须全绿，后者预期红。
 *
 * ## 三个数据端
 *
 * 1. 源 xlsx 端 = `backend/data/g7_column_source_facts.json`（派生投影，由
 *    `backend/tests/four_table/test_g7_column_source_facts.py` 钉死「与实时 openpyxl 读取
 *    逐字相等」，故本守卫可直接信任它；动态列占位记作 `<DYNAMIC:cN>`）。
 * 2. 模板 seed 端 = `backend/data/note_template_{listed,soe}.json`，
 *    **索引必须带章节**（实测 listed 63 个表名跨章节重复、soe 40 个，按表名全局索引会
 *    匹配到会计政策章的空壳版）。
 * 3. 运行时端 = 真调 `buildG7ListedColumns()` / `buildG7SoeColumns()`；其 key **不带章节**
 *    ⇒ 章节归属从 `G7_*_DISCLOSURE_SECTIONS` 建（`noteSectionId` + `templateTableKey ?? title`）。
 */
import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import {
  G7_LISTED_DISCLOSURE_SECTIONS,
  buildG7ListedColumns,
} from '../../g7-long-term-equity-main/disclosure/g7ListedDisclosureModel'
import {
  G7_SOE_DISCLOSURE_SECTIONS,
  buildG7SoeColumns,
} from '../../g7-long-term-equity-main/disclosure/g7SoeDisclosureModel'
import {
  buildG7HeaderBlocks,
  hasG7TwoLevelHeader,
} from '../../g7-long-term-equity-main/disclosure/g7DisclosureHeaderBlocks'

// ─────────────────────────────────────────────────────────────────────────────
// 仓库根定位：**双哨兵具体文件**向上查找
// 禁写死回退级数（本目录到仓库根 8 级，抄别处的 6/7 级会静默解析到 audit-platform，
// 表现为「文件级失败」而非断言失败）；禁用目录作哨兵（`audit-platform/backend/app/routers`
// 是历史遗留空目录，会骗停在错误层）。
// ─────────────────────────────────────────────────────────────────────────────
const SENTINELS = ['backend/data/g7_column_source_facts.json', '.kiro/steering/memory.md'] as const

function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 14; i += 1) {
    if (SENTINELS.every((s) => existsSync(resolve(dir, s)))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`仓库根定位失败（双哨兵 ${SENTINELS.join(' + ')} 未同时命中）`)
}

const REPO_ROOT = findRepoRoot()

/** 读文本并统一行尾（工作树多为 CRLF，含 `\n` 的字面量断言在 CRLF 上必失效）。 */
function readText(rel: string): string {
  const p = resolve(REPO_ROOT, rel)
  if (!existsSync(p)) throw new Error(`文件不存在：${rel}`)
  return readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

function readJson<T>(rel: string): T {
  return JSON.parse(readText(rel)) as T
}

// ─────────────────────────────────────────────────────────────────────────────
// 类型
// ─────────────────────────────────────────────────────────────────────────────
interface ColumnLike {
  key?: string
  label?: string
  is_label?: boolean
  group?: string
  flat?: boolean
  format?: string
}

interface FactsColumn {
  label: string
  group: string | null
}

/**
 * 单槽占位豁免（登记 1）的下发形态。
 *
 * 🔴 **一处登记两端消费**：唯一真源是后端 `SOURCE_PLACEHOLDER_SINGLE_SLOT`，本文件读
 * 下发字段、**不得**在 TS 里再抄一份表名清单（两份必然漂移，且后端 stale 检测管不到
 * TS 里那份）。stale 检测在后端 `_sc_single_slot_still_single()`：源侧段数不再是 1 即打红。
 */
interface SingleSlotExemption {
  /** 可豁免的维度（实测恒为 `['flat','group']`；其余维度照常比对） */
  exempt_kinds: string[]
  source_ref: string
  source_text: string
  basis: string[]
  platform_intent: string
  expected_source_runs: number
}

/** 转角标题豁免（登记 3）的依据下发。 */
interface CornerBasis {
  source_ref: string
  row_titled: string[]
  data_row_samples: string[]
  platform_intent: string
}

interface FactsTable {
  label_header: string
  label_header_parts: string[]
  /**
   * 标签列头的**未归一化原文**（保留内部空格）。
   *
   * 🔴 `label_header` 经后端 `_norm()` 去掉全部空白，无法表达 `项  目` 与 `项目` 的差异；
   * 逐字判据一律用本字段（见 `compareTableTriple` 里 `headerExpected` 的说明）。
   */
  label_header_raw?: string
  label_header_parts_raw?: string[]
  label_xlsx_span: number
  /**
   * 标签列表头语义二态（后端 `CORNER_TITLE_EXEMPTIONS` 下发）：
   * - `'name'`   = 源 xlsx 给了行标识列名 ⇒ `label_header` 可逐字比对
   * - `'corner'` = **转角标题**，源 xlsx 未给行标识列名 ⇒ `label_header` 是拼接出的
   *   **幻影**，禁止用它比对；改用 `label_header_seed`
   */
  label_header_kind?: 'name' | 'corner'
  /** `label_header_kind === 'corner'` 时的平台实现值（实测为「项目」） */
  label_header_seed?: string
  label_header_corner_basis?: CornerBasis
  single_slot_exemption?: SingleSlotExemption
  is_two_level: boolean
  level_count: number
  source_rows: string
  columns: FactsColumn[]
}

type FactsFile = {
  _meta: Record<string, unknown>
} & Record<'listed' | 'soe', Record<string, Record<string, FactsTable>>>

interface SeedTable {
  name?: string
  headers?: string[]
  columns?: ColumnLike[]
}

interface SeedSection {
  section_number?: string
  section_id?: string
  tables?: SeedTable[]
}

type Variant = 'listed' | 'soe'

/** 一张表的三端切片（比对函数的唯一入参形态，便于用替身做反向自检）。 */
interface TableTriple {
  variant: Variant
  section: string
  table: string
  runtime: ColumnLike[]
  runtimeLabelHeader: string | null
  seed: ColumnLike[] | null
  facts: FactsTable | null
}

type DevKind =
  | 'A-group'
  | 'A源-group'
  | 'B-labelKey'
  | 'C-dataKey'
  | 'D-labelText'
  | 'E-colCount'
  | 'flat-stance'
  | 'flat-group-conflict'
  | 'isLabel'
  | 'labelKeyCjk'
  | 'labelHeaderText'
  | 'orphan'
  | 'factsMissing'

interface Deviation {
  kind: DevKind
  variant: Variant
  section: string
  table: string
  /** seed 侧观测值 */
  seed?: string
  /** 运行时侧观测值 */
  runtime?: string
  /** 源 xlsx 侧观测值 */
  source?: string
  note?: string
}

// ─────────────────────────────────────────────────────────────────────────────
// 纯函数
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 压缩成 `[{group, start, span}]`，**口径与后端 `_extract_column_groups` 逐字一致**：
 * 跳过 `is_label` 列 + `header_idx` 从 1 起（headers[0] 是标签列）。
 *
 * 🔴 两侧 `is_label` 表态不一致会让 `start` **整体偏移一位**（父子对应关系错开而
 * 列名列数看着都对）—— 这是把 `is_label` 单列一维的原因。
 */
export function compressGroups(cols: ColumnLike[], opts?: { skipLabel?: boolean }) {
  const skipLabel = opts?.skipLabel ?? true
  const segs: { group: string; start: number; span: number }[] = []
  let idx = 1
  for (const c of cols) {
    if (skipLabel && c.is_label) continue
    const g = c.group
    if (g) {
      const last = segs[segs.length - 1]
      if (last && last.group === g) last.span += 1
      else segs.push({ group: g, start: idx, span: 1 })
    }
    idx += 1
  }
  return segs
}

function factsGroups(f: FactsTable) {
  return compressGroups(
    f.columns.map((c) => ({ label: c.label, group: c.group ?? undefined })),
    { skipLabel: false },
  )
}

const DYNAMIC_GROUP_RE = /^<DYNAMIC:c\d+>$/

function segShape(segs: { start: number; span: number }[]) {
  return segs.map((s) => `${s.start}+${s.span}`).join(',')
}

function segFull(segs: { group: string; start: number; span: number }[]) {
  return segs.map((s) => `${s.group}@${s.start}+${s.span}`).join(',')
}

const CJK_RE = /[\u3400-\u4dbf\u4e00-\u9fff]/

/**
 * 六维比对（纯函数）。同输入同输出、无 IO，供替身反向自检直接调用。
 *
 * 返回两个列表：
 * - `deviations` = **计入**的偏差（该修的）
 * - `exempted`   = **已裁决豁免**的偏差点（后端登记表下发，不计入但必须可见）
 *
 * 🔴 豁免判据**只来自 facts JSON 的下发字段**（`single_slot_exemption` /
 * `label_header_kind`），后端 `SOURCE_PLACEHOLDER_SINGLE_SLOT` 与
 * `CORNER_TITLE_EXEMPTIONS` 是唯一真源。**禁在本文件另抄表名清单** —— 抄第二份
 * 必然与后端漂移，且后端的 stale 检测管不到 TS 里的副本。
 */
export function compareTableTriple(t: TableTriple): {
  deviations: Deviation[]
  exempted: Deviation[]
} {
  const out: Deviation[] = []
  const exempted: Deviation[] = []
  const base = { variant: t.variant, section: t.section, table: t.table }
  const push = (d: Omit<Deviation, 'variant' | 'section' | 'table'>) => out.push({ ...base, ...d })

  if (t.seed === null) {
    push({ kind: 'orphan', note: '运行时表在对应变体的对应章节找不到 seed 表' })
    return { deviations: out, exempted }
  }
  if (t.facts === null) {
    push({ kind: 'factsMissing', note: '源 xlsx facts 缺该 (variant, section, table)' })
    return { deviations: out, exempted }
  }
  const rt = t.runtime
  const sd = t.seed
  const fx = t.facts

  // ── 维度 1：is_label（两侧各恰有 1 个）────────────────────────────────────
  const rtLabels = rt.filter((c) => c.is_label)
  const sdLabels = sd.filter((c) => c.is_label)
  if (rtLabels.length !== 1 || sdLabels.length !== 1) {
    push({
      kind: 'isLabel',
      runtime: `${rtLabels.length} 个 is_label`,
      seed: `${sdLabels.length} 个 is_label`,
      note: '两侧表态不一致会让 group 的 start 整体偏移一位（父子对应错开而列名列数看着都对）',
    })
  }

  // ── 维度 2：flat 表态（表级；投影器见任一 flat 即整表返 []）────────────────
  const rtAnyFlat = rt.some((c) => c.flat)
  const sdAnyFlat = sd.some((c) => c.flat)
  const rtAnyGroup = rt.some((c) => c.group)
  const sdAnyGroup = sd.some((c) => c.group)
  if (rtAnyFlat !== sdAnyFlat) {
    push({
      kind: 'flat-stance',
      runtime: `anyFlat=${rtAnyFlat}`,
      seed: `anyFlat=${sdAnyFlat}`,
      note: 'flat 为真常是「丢了 group」的症状，不是「忘标 flat」',
    })
  }
  if (rtAnyFlat && rtAnyGroup) {
    push({ kind: 'flat-group-conflict', runtime: 'flat 与 group 并存（投影器会把 group 永久打掉）' })
  }
  if (sdAnyFlat && sdAnyGroup) {
    push({ kind: 'flat-group-conflict', seed: 'flat 与 group 并存（投影器会把 group 永久打掉）' })
  }

  // ── 维度 3：group（runtime↔seed 同名同跨度；runtime↔源 只比段数与跨度）─────
  const rtSegs = compressGroups(rt)
  const sdSegs = compressGroups(sd)
  if (segFull(rtSegs) !== segFull(sdSegs)) {
    push({ kind: 'A-group', runtime: segFull(rtSegs) || '<无分组>', seed: segFull(sdSegs) || '<无分组>' })
  }
  const fxSegs = factsGroups(fx)
  if (segShape(rtSegs) !== segShape(fxSegs)) {
    const dyn = fxSegs.some((s) => DYNAMIC_GROUP_RE.test(s.group))
    // 🔴 单槽占位豁免（登记 1，后端下发）：源侧「1 段动态占位跨 2」而运行时「无分组」
    //    是**已裁决豁免**，不是待修偏差 —— 源模板自身只填 1 个实体槽（同表另两组合并
    //    的叶子行全空），平台按单槽 flat 实现。判据取下发的 `exempt_kinds`，
    //    不在 TS 里另抄表名清单。
    const slotEx = fx.single_slot_exemption
    if (slotEx?.exempt_kinds.includes('group')) {
      exempted.push({
        ...base,
        kind: 'A源-group',
        runtime: segShape(rtSegs) || '<无分组>',
        source: segFull(fxSegs) || '<无分组>',
        note: `单槽占位豁免 @ ${slotEx.source_ref}：${slotEx.platform_intent}`,
      })
    } else {
      push({
        kind: 'A源-group',
        runtime: segShape(rtSegs) || '<无分组>',
        source: (segFull(fxSegs) || '<无分组>') + (dyn ? '（含动态列占位，只比段数与跨度）' : ''),
      })
    }
  }

  // ── 维度 4：标签列 key（两侧一致 + 不得用中文字面量当 key）──────────────────
  const rtLabelKey = rtLabels[0]?.key
  const sdLabelKey = sdLabels[0]?.key
  if (rtLabelKey !== sdLabelKey) {
    push({ kind: 'B-labelKey', runtime: String(rtLabelKey), seed: String(sdLabelKey) })
  }
  if (rtLabelKey && CJK_RE.test(rtLabelKey)) {
    push({ kind: 'labelKeyCjk', runtime: String(rtLabelKey), note: '中文字面量当 key 违反禁硬编码' })
  }

  // ── 维度 5：数据列 key（seed 与运行时逐位相等）──────────────────────────────
  const rtDataKeys = rt.filter((c) => !c.is_label).map((c) => c.key)
  const sdDataKeys = sd.filter((c) => !c.is_label).map((c) => c.key)
  if (JSON.stringify(rtDataKeys) !== JSON.stringify(sdDataKeys)) {
    push({ kind: 'C-dataKey', runtime: JSON.stringify(rtDataKeys), seed: JSON.stringify(sdDataKeys) })
  }

  // ── 维度 6：label 文字 + 列数（运行时数据列 vs 源 xlsx）─────────────────────
  const rtDataLabels = rt.filter((c) => !c.is_label).map((c) => c.label ?? '')
  const fxLabels = fx.columns.map((c) => c.label)
  if (rtDataLabels.length !== fxLabels.length) {
    push({
      kind: 'E-colCount',
      runtime: `${rtDataLabels.length} 个数据列`,
      source: `${fxLabels.length} 个数据列`,
    })
  } else {
    const bad = rtDataLabels
      .map((l, i) => (l === fxLabels[i] ? null : `[${i}] 运行时=${quoted(l)} 源=${quoted(fxLabels[i])}`))
      .filter((x): x is string => x !== null)
    if (bad.length) push({ kind: 'D-labelText', note: bad.join(' / ') })
  }

  // ── 附带发现（超出六维口径）：标签列文字 vs 源 label_header ────────────────
  //
  // 🔴 转角标题豁免（登记 3，后端下发 `label_header_kind`）：源 xlsx 对行标识列
  //    **根本没给列名**，两行文字各自标注**表头行本身**（上行放公司名、下行放
  //    日期/期间）⇒ 拼出来的 `label_header` 是**幻影**，用它比对必产假偏差。
  //    该表的裁决值是 `label_header_seed`（实测「项目」，按数据行语义定）。
  //    判据取下发字段，**不在 TS 里另抄一份表名清单**（两份必然漂移）。
  const rtHeaderText = t.runtimeLabelHeader ?? rtLabels[0]?.label ?? ''
  const headerIsCorner = fx.label_header_kind === 'corner'
  // 🔴 判据取 `label_header_raw`（**未归一化原文**）而不是 `label_header`：
  //    后者经后端 `_norm()` 去掉了全部空白，故源模板的 `项  目`（双空格 13 张）/
  //    `项 目`（单空格 3 张）在它上面**结构上不可见** —— 运行时长期写 `项目` 而本守卫
  //    与边① 双双判绿，直到 Task 12 把契约扩到 38 张、helper 的 P5（直接比 seed
  //    `headers[0]` 原文）才抓出 15 处。R4.4 要求「源 xlsx 自身用了两种写法时以该表
  //    原文为准，禁统一成好看的那种」⇒ 逐字判据必须落在 raw 上。
  //    `label_header_raw` 缺失（旧版 facts）时回退归一化值，并由下方扫描面自检打红。
  const headerExpected = headerIsCorner
    ? (fx.label_header_seed ?? '')
    : (fx.label_header_raw ?? fx.label_header)
  if (rtHeaderText !== headerExpected) {
    push({
      kind: 'labelHeaderText',
      runtime: rtHeaderText,
      source: headerIsCorner
        ? `${headerExpected}（转角标题：源拼接值 '${fx.label_header}' 是幻影，裁决值取 label_header_seed）`
        : headerExpected,
    })
  } else if (headerIsCorner) {
    exempted.push({
      ...base,
      kind: 'labelHeaderText',
      runtime: rtHeaderText,
      source: fx.label_header,
      note:
        `转角标题豁免 @ ${fx.label_header_corner_basis?.source_ref ?? '?'}：` +
        `源未给行标识列名，按数据行语义（${(fx.label_header_corner_basis?.data_row_samples ?? []).join('/')}）取「${headerExpected}」`,
    })
  }

  return { deviations: out, exempted }
}

/**
 * 只取「计入偏差」那一半（反向自检用）。
 *
 * 🔴 存在的理由：反向自检要断言「改坏一处 ⇒ 必打红」，判据必须落在**计入偏差**上。
 * 若自检直接读 `.exempted`，豁免登记一旦被写宽（把真偏差吞进 exempted），自检仍绿
 * —— 那正是「豁免变逃逸阀」的形态。故自检与汇总一律走本函数。
 */
export function devsOf(t: TableTriple): Deviation[] {
  return compareTableTriple(t).deviations
}

/** 引号包裹（让消息里的空串可见）。 */
function quoted(v: unknown): string {
  return `'${String(v)}'`
}

/**
 * **弱判据对照**：只断言「本表 flat 或 group 至少表态其一」的朴素判据。
 *
 * 它是本 spec 之前那一版口径（「flat 不一致约 15 处」的来源）。反向自检要证明：
 * 同一组替身在弱判据下**仍然通过**，在六维判据下打红 ⇒ 六维强于旧判据。
 */
export function weakVerdictFlatStanceOnly(rt: ColumnLike[]): string[] {
  const anyFlat = rt.some((c) => c.flat)
  const anyGroup = rt.some((c) => c.group)
  return anyFlat || anyGroup ? [] : ['本表 flat/group 均未表态']
}

// ─────────────────────────────────────────────────────────────────────────────
// 剥注释（源码判据前置）
// ─────────────────────────────────────────────────────────────────────────────

/** 剥 TS 的 `//` 行注释与块注释（带字符串状态，避免被 URL 与 `image/*` 骗）。 */
export function stripTsComments(src: string): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < src.length) {
    const ch = src[i]
    const next = src[i + 1]
    if (quote) {
      out += ch
      if (ch === '\\') {
        out += next ?? ''
        i += 2
        continue
      }
      if (ch === quote) quote = null
      i += 1
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch
      out += ch
      i += 1
      continue
    }
    if (ch === '/' && next === '/') {
      while (i < src.length && src[i] !== '\n') i += 1
      continue
    }
    if (ch === '/' && next === '*') {
      i += 2
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) i += 1
      i += 2
      continue
    }
    out += ch
    i += 1
  }
  return out
}

/** 剥 Python 的 `#` 行注释（带引号状态；三引号 docstring 里的 `#` 不剥）。 */
export function stripPyComments(src: string): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < src.length) {
    const three = src.slice(i, i + 3)
    if (!quote && (three === '"""' || three === "'''")) {
      quote = three
      out += three
      i += 3
      continue
    }
    if (quote && quote.length === 3 && three === quote) {
      out += three
      quote = null
      i += 3
      continue
    }
    const ch = src[i]
    if (quote) {
      out += ch
      if (ch === '\\') {
        out += src[i + 1] ?? ''
        i += 2
        continue
      }
      if (quote.length === 1 && ch === quote) quote = null
      i += 1
      continue
    }
    if (ch === '"' || ch === "'") {
      quote = ch
      out += ch
      i += 1
      continue
    }
    if (ch === '#') {
      while (i < src.length && src[i] !== '\n') i += 1
      continue
    }
    out += ch
    i += 1
  }
  return out
}

// ─────────────────────────────────────────────────────────────────────────────
// 三端加载
// ─────────────────────────────────────────────────────────────────────────────
const FACTS_REL = 'backend/data/g7_column_source_facts.json'
const TEMPLATE_REL: Record<Variant, string> = {
  listed: 'backend/data/note_template_listed.json',
  soe: 'backend/data/note_template_soe.json',
}
const MODEL_REL: Record<Variant, string> = {
  listed:
    'audit-platform/frontend/src/components/workpaper/g7-long-term-equity-main/disclosure/g7ListedDisclosureModel.ts',
  soe: 'audit-platform/frontend/src/components/workpaper/g7-long-term-equity-main/disclosure/g7SoeDisclosureModel.ts',
}
const PROJECTOR_REL = 'backend/app/services/note_sub_table_projector.py'

const facts = readJson<FactsFile>(FACTS_REL)

function seedIndex(variant: Variant) {
  const tpl = readJson<{ sections?: SeedSection[] }>(TEMPLATE_REL[variant])
  const byKey = new Map<string, SeedTable>()
  const sectionNumbers = new Set<string>()
  const dupNamesGlobal = new Map<string, number>()
  const dupNamesInSection: string[] = []
  for (const s of tpl.sections ?? []) {
    const sec = s.section_number ?? ''
    sectionNumbers.add(sec)
    const seen = new Set<string>()
    for (const t of s.tables ?? []) {
      const name = t.name ?? ''
      byKey.set(`${sec}\u0000${name}`, t)
      dupNamesGlobal.set(name, (dupNamesGlobal.get(name) ?? 0) + 1)
      if (seen.has(name)) dupNamesInSection.push(`${sec}/${name}`)
      seen.add(name)
    }
  }
  return { byKey, sectionNumbers, dupNamesGlobal, dupNamesInSection }
}

const SEED = { listed: seedIndex('listed'), soe: seedIndex('soe') } as const

interface RuntimeEntry {
  variant: Variant
  section: string
  table: string
  labelHeader: string | null
  columns: ColumnLike[]
}

function runtimeEntries(): RuntimeEntry[] {
  const out: RuntimeEntry[] = []
  const pairs = [
    ['listed', G7_LISTED_DISCLOSURE_SECTIONS, buildG7ListedColumns()],
    ['soe', G7_SOE_DISCLOSURE_SECTIONS, buildG7SoeColumns()],
  ] as const
  for (const [variant, sections, cols] of pairs) {
    for (const section of sections as readonly Record<string, any>[]) {
      for (const table of (section.tables ?? []) as Record<string, any>[]) {
        const key: string = table.templateTableKey ?? table.title
        out.push({
          variant: variant as Variant,
          section: String(section.noteSectionId ?? ''),
          table: key,
          labelHeader: (table.labelHeader as string | undefined) ?? null,
          columns: ((cols as Record<string, ColumnLike[]>)[key] ?? []) as ColumnLike[],
        })
      }
    }
  }
  return out
}

const RUNTIME = runtimeEntries()

function tripleOf(e: RuntimeEntry): TableTriple {
  return {
    variant: e.variant,
    section: e.section,
    table: e.table,
    runtime: e.columns,
    runtimeLabelHeader: e.labelHeader,
    seed: SEED[e.variant].byKey.get(`${e.section}\u0000${e.table}`)?.columns ?? null,
    facts: facts[e.variant]?.[e.section]?.[e.table] ?? null,
  }
}

const TRIPLES = RUNTIME.map(tripleOf)
const ALL_DEVIATIONS = TRIPLES.flatMap(devsOf)
/** 已裁决豁免的偏差点（后端登记表下发）—— 必须可见、必须非空、必须有依据。 */
const ALL_EXEMPTED = TRIPLES.flatMap((t) => compareTableTriple(t).exempted)

function byKind(kind: DevKind): Deviation[] {
  return ALL_DEVIATIONS.filter((d) => d.kind === kind)
}

function render(devs: Deviation[]): string {
  return devs
    .map(
      (d) =>
        `  [${d.kind}] ${d.variant}/${d.section}/${d.table}` +
        (d.seed !== undefined ? `\n        seed = ${d.seed}` : '') +
        (d.runtime !== undefined ? `\n        运行时 = ${d.runtime}` : '') +
        (d.source !== undefined ? `\n        源xlsx = ${d.source}` : '') +
        (d.note ? `\n        说明 = ${d.note}` : ''),
    )
    .join('\n')
}

const CLASS_LABEL: Partial<Record<DevKind, string>> = {
  'A-group': 'A 丢 group（运行时 vs seed）',
  'A源-group': 'A源 丢 group（运行时 vs 源 xlsx，只比段数与跨度）',
  'B-labelKey': 'B 标签列 key',
  'C-dataKey': 'C 数据列 key',
  'D-labelText': 'D label 文字',
  'E-colCount': 'E 列数',
  'flat-stance': 'flat 表态（A 的症状）',
  labelKeyCjk: '标签列 key 为中文字面量',
  labelHeaderText: '标签列文字（附带发现，超出六维口径）',
}

// ═════════════════════════════════════════════════════════════════════════════
// ✅ 组一：判据自检与结构性防回退 —— **必须全绿**
//    这里任何一条红都说明「守卫自己坏了」，此时组二的红是噪声。
// ═════════════════════════════════════════════════════════════════════════════
describe('G7 三向对齐守卫｜判据自检与结构性防回退（必须全绿）', () => {
  // ── 扫描面自检（防空转）────────────────────────────────────────────────────
  describe('扫描面自检', () => {
    it('源 xlsx facts 覆盖 ≥38 张表（listed 15 + soe 23）', () => {
      const count = (v: Variant) =>
        Object.values(facts[v]).reduce((n, tables) => n + Object.keys(tables).length, 0)
      expect(count('listed')).toBe(15)
      expect(count('soe')).toBe(23)
      expect(count('listed') + count('soe')).toBeGreaterThanOrEqual(38)
    })

    it('facts 每张表都下发 label_header_raw（缺了会让标签列头判据静默退化成归一化比对）', () => {
      const missing: string[] = []
      const noSpaceDiff: string[] = []
      for (const v of ['listed', 'soe'] as Variant[]) {
        for (const [sec, tables] of Object.entries(facts[v])) {
          for (const [name, tf] of Object.entries(tables)) {
            if (typeof tf.label_header_raw !== 'string') missing.push(`${v}/${sec}/${name}`)
            else if (tf.label_header_raw !== tf.label_header) noSpaceDiff.push(`${v}/${sec}/${name}`)
          }
        }
      }
      expect(missing, '缺 label_header_raw ⇒ 请重跑 --emit-facts').toEqual([])
      // 🔴 反面锚定：raw 与 norm **确有**差异（实测 14 张），证明这个字段不是冗余摆设。
      // 若哪天归零，要么源模板改了排版（该重新裁决），要么 raw 被误写成归一化值。
      expect(noSpaceDiff.length, `raw ≠ norm 的表数（源模板空格排版）：${noSpaceDiff.join(', ')}`).toBe(14)
    })

    it('运行时构造函数产出 ≥38 张表，且两个 build*Columns 零入参可调', () => {
      expect(Object.keys(buildG7ListedColumns()).length).toBe(15)
      expect(Object.keys(buildG7SoeColumns()).length).toBe(23)
      expect(RUNTIME.length).toBeGreaterThanOrEqual(38)
      // 每张表都必须真拿到列（拿不到 = 章节归属或 key 解析坏了，会让比对静默空转）
      const empty = RUNTIME.filter((e) => e.columns.length === 0)
      expect(empty.map((e) => `${e.variant}/${e.section}/${e.table}`)).toEqual([])
    })

    it('seed 侧命中数 == 运行时表数（章节 + 表名二元索引全部命中）', () => {
      const matched = TRIPLES.filter((t) => t.seed !== null)
      expect(matched.length).toBe(RUNTIME.length)
      const sections = new Set(RUNTIME.map((e) => `${e.variant}/${e.section}`))
      expect(sections.size).toBeGreaterThanOrEqual(11)
      for (const key of sections) {
        const [v, sec] = key.split('/') as [Variant, string]
        expect(SEED[v].sectionNumbers.has(sec), `seed 模板缺章节 ${key}`).toBe(true)
      }
    })

    it('facts 每张表都被运行时消费（无只在源侧存在的表 ⇒ 扫描面无缺口）', () => {
      const rtKeys = new Set(RUNTIME.map((e) => `${e.variant}\u0000${e.section}\u0000${e.table}`))
      const missing: string[] = []
      for (const v of ['listed', 'soe'] as Variant[]) {
        for (const [sec, tables] of Object.entries(facts[v])) {
          for (const name of Object.keys(tables)) {
            if (!rtKeys.has(`${v}\u0000${sec}\u0000${name}`)) missing.push(`${v}/${sec}/${name}`)
          }
        }
      }
      expect(missing).toEqual([])
    })

    it('比对确实产出了记录（判据非空转）', () => {
      expect(TRIPLES.length).toBe(38)

      // 🔴 判据不能写成 `ALL_DEVIATIONS.length > 0`（改造前如此）：
      // 那等于把「机器在转」错当成「必须存在偏差」，偏差修完后本用例必然翻红，
      // 逼着后人要么留一条真偏差不修、要么删掉自检 —— 两条路都毁掉守卫。
      // 非空转要证的是**比对真的走到了六个维度**，与偏差数是 0 还是 49 无关。

      // ① 没有一张表在开头就 early-return（seed/facts 缺一个就直接返回，六维全部跳过）
      const earlyReturn = TRIPLES.filter((t) => t.seed === null || t.facts === null)
      expect(
        earlyReturn.map((t) => `${t.variant}/${t.section}/${t.table}`),
        'seed/facts 缺失会让该表在六维之前 early-return ⇒ 该表实际未被检查',
      ).toEqual([])

      // ② 每张表两侧都真拿到了列（空数组会让所有逐列比对静默通过）
      const emptySide = TRIPLES.filter((t) => t.runtime.length === 0 || (t.seed ?? []).length === 0)
      expect(
        emptySide.map((t) => `${t.variant}/${t.section}/${t.table}`),
        '任一侧列集为空 ⇒ 逐列比对退化成恒真',
      ).toEqual([])

      // ③ 豁免登记真的流过了比对（后端下发的 13 条裁决必须可见；空了说明登记断链）
      expect(ALL_EXEMPTED.length, '豁免登记为空 ⇒ 后端 exempt_kinds/label_header_kind 没被消费').toBeGreaterThan(0)

      // ④ 活性探针：拿**真实生产数据**的每一张表各改坏一处，必须逐张打红。
      //    这一条才是「机器在转」的充分证据 —— 它不依赖当前存在偏差，
      //    且比 `baselineTriple()` 那组替身更强（替身是合成数据，可能与真实结构脱节）。
      const silent: string[] = []
      for (const t of TRIPLES) {
        const clone = JSON.parse(JSON.stringify(t)) as TableTriple
        const victim = clone.runtime.find((c) => !c.is_label)
        if (!victim) continue
        victim.key = `${victim.key}__mutated__`
        if (devsOf(clone).length === 0) silent.push(`${t.variant}/${t.section}/${t.table}`)
      }
      expect(silent, '改坏数据列 key 后仍零偏差 ⇒ 该表的比对是空转').toEqual([])
    })
  })

  // ── B 组：四项防回退（实测当前已绿，必须锁死）────────────────────────────
  describe('防回退（实测当前已绿）', () => {
    it('is_label 表态两侧一致（0 偏差）', () => {
      const devs = byKind('isLabel')
      expect(devs.length, `is_label 偏差：\n${render(devs)}`).toBe(0)
    })

    it('孤儿表 0（运行时每张表都能在对应变体的对应章节找到 seed 表）', () => {
      const devs = byKind('orphan')
      expect(devs.length, `孤儿表：\n${render(devs)}`).toBe(0)
      expect(byKind('factsMissing').length, `facts 缺表：\n${render(byKind('factsMissing'))}`).toBe(0)
    })

    it('运行时 templateTableKey 撞名 0', () => {
      for (const v of ['listed', 'soe'] as Variant[]) {
        const keys = RUNTIME.filter((e) => e.variant === v).map((e) => e.table)
        const dup = keys.filter((k, i) => keys.indexOf(k) !== i)
        expect([...new Set(dup)], `${v} 运行时 templateTableKey 撞名`).toEqual([])
      }
    })

    it('模板同章节内表名唯一（撞名会让 sub_table_data 字典去重丢整张表）', () => {
      for (const v of ['listed', 'soe'] as Variant[]) {
        expect(SEED[v].dupNamesInSection, `${v} 同章节内表名撞名`).toEqual([])
      }
    })

    it('反面锚定：模板里确有跨章节重名表名 ⇒ 证明「索引必须带章节」不是空谈', () => {
      for (const v of ['listed', 'soe'] as Variant[]) {
        const dup = [...SEED[v].dupNamesGlobal.entries()].filter(([, n]) => n > 1)
        const top = dup.sort((a, b) => b[1] - a[1])[0]
        expect(dup.length, `${v} 跨章节重名表名数`).toBeGreaterThan(0)
        expect(top?.[1] ?? 0, `${v} 最高重名次数（top=${JSON.stringify(top)}）`).toBeGreaterThan(1)
      }
      // 🔴 本 spec 关注的 G7 表名本身就在重名之列：`长期股权投资` 在 **listed** 模板跨章节
      // 出现 3 次（项目注释章的真表 + 会计政策章等空壳版）⇒ 按表名全局索引必匹配到空壳。
      // （memory 曾记「soe 出现 3 次」，实测是 listed；soe 侧该名唯一。）
      expect(SEED.listed.dupNamesGlobal.get('长期股权投资') ?? 0).toBeGreaterThan(1)
      expect(SEED.soe.dupNamesGlobal.get('长期股权投资') ?? 0).toBe(1)
    })
  })

  // ── C 组：结构性防回退（读源码）─────────────────────────────────────────
  describe('结构性防回退（源码判据）', () => {
    it('剥注释确实生效（自检）', () => {
      const rawTs = readText(MODEL_REL.listed)
      const strippedTs = stripTsComments(rawTs)
      expect(rawTs).toContain('🔴 flat/group 必须在此处透传')
      expect(strippedTs).not.toContain('🔴 flat/group 必须在此处透传')
      // 字符串字面量不得被剥（否则 group 名之类的判据会假红）
      expect(stripTsComments(`const a = "// not a comment"`)).toContain('// not a comment')
      expect(stripTsComments(`const b = 'a /* keep */ b'`)).toContain('/* keep */')

      const rawPy = readText(PROJECTOR_REL)
      const strippedPy = stripPyComments(rawPy)
      expect(rawPy).toContain('# 显式单级声明：标在任意一列即对整表生效')
      expect(strippedPy).not.toContain('# 显式单级声明：标在任意一列即对整表生效')
      expect(stripPyComments(`x = "# not a comment"`)).toContain('# not a comment')
    })

    it('两个 Model.ts 的 `...(hasGroup ? {} : { flat: true })` 三元表达式仍在', () => {
      // 它保证运行时 flat/group 互斥且不留 undefined 三态：
      // 有 group 的表标签列不标 flat（混合分组）；无 group 的表标签列标 flat（抑制前缀推断）。
      const re = /\.\.\.\(\s*hasGroup\s*\?\s*\{\s*\}\s*:\s*\{\s*flat\s*:\s*true\s*,?\s*\}\s*\)/
      for (const v of ['listed', 'soe'] as Variant[]) {
        const src = stripTsComments(readText(MODEL_REL[v]))
        expect(re.test(src), `${MODEL_REL[v]} 缺 hasGroup 三元表达式`).toBe(true)
        // hasGroup 必须由 columns 派生（写死 true/false 会让整表表态失真）
        expect(/const\s+hasGroup\s*=\s*columns\.some\(\s*c\s*=>\s*c\.group\s*\)/.test(src)).toBe(true)
      }
    })

    it('替身反向自检：三元表达式判据能区分正确形态与被改坏的形态', () => {
      const re = /\.\.\.\(\s*hasGroup\s*\?\s*\{\s*\}\s*:\s*\{\s*flat\s*:\s*true\s*,?\s*\}\s*\)/
      expect(re.test('...(hasGroup ? {} : { flat: true })')).toBe(true)
      expect(re.test('...({ flat: true })')).toBe(false)
      expect(re.test('...(hasGroup ? { flat: true } : {})')).toBe(false)
      expect(re.test('...(true ? {} : { flat: true })')).toBe(false)
    })

    it('投影器「见任一 flat 即整表返 []」的短路仍在（维度 2 判据的前提）', () => {
      const src = stripPyComments(readText(PROJECTOR_REL))
      const re =
        /if\s+any\(\s*isinstance\(\s*d\s*,\s*dict\s*\)\s+and\s+d\.get\(\s*["']flat["']\s*\)\s+for\s+d\s+in\s+defs\s*\)\s*:\s*\n\s*return\s+\[\s*\]/
      expect(re.test(src), 'note_sub_table_projector._extract_column_groups 的 flat 短路已丢').toBe(true)
    })

    it('投影器「跳过 is_label 列 + header_idx 从 1 起」仍在（start 偏移一位的成因）', () => {
      const src = stripPyComments(readText(PROJECTOR_REL))
      expect(/header_idx\s*=\s*1/.test(src)).toBe(true)
      expect(/if\s+d\.get\(\s*["']is_label["']\s*\)\s*:\s*\n\s*continue/.test(src)).toBe(true)
    })

    it('投影器**两处**标签列双向兜底分支仍在（标签列 key 改动零数据风险的前提）', () => {
      const src = stripPyComments(readText(PROJECTOR_REL))
      // ① 逆投影侧：任意标签 key ← 规范 `label`
      const inverseCond =
        /if\s+label_key\s+and\s+label_key\s*!=\s*["']label["']\s+and\s+label_key\s+not\s+in\s+out\s+and\s+["']label["']\s+in\s+out\s*:/
      const inverseAssign = /out\[\s*label_key\s*\]\s*=\s*out\[\s*["']label["']\s*\]/
      expect(inverseCond.test(src), '逆投影侧兜底条件已丢').toBe(true)
      expect(inverseAssign.test(src), '逆投影侧兜底赋值已丢').toBe(true)
      // ② 投影侧：标签列值为空 → 回退规范 `label`
      const projectCond =
        /if\s*\(\s*label_val\s+is\s+None\s+or\s+label_val\s*==\s*(?:""|'')\s*\)\s+and\s+label_key\s*!=\s*["']label["']\s*:/
      const projectAssign = /label_val\s*=\s*r\.get\(\s*["']label["']\s*,\s*label_val\s*\)/
      expect(projectCond.test(src), '投影侧兜底条件已丢').toBe(true)
      expect(projectAssign.test(src), '投影侧兜底赋值已丢').toBe(true)
    })

    it('替身反向自检：兜底分支判据匹配**条件形态**而非只匹配标识符', () => {
      // 平台已记「只断言标识符抓不住 `if False:`」⇒ 判据必须是条件表达式的形态。
      const inverseCond =
        /if\s+label_key\s+and\s+label_key\s*!=\s*["']label["']\s+and\s+label_key\s+not\s+in\s+out\s+and\s+["']label["']\s+in\s+out\s*:/
      expect(
        inverseCond.test(
          'if label_key and label_key != "label" and label_key not in out and "label" in out:',
        ),
      ).toBe(true)
      expect(inverseCond.test('if False:  # label_key label out')).toBe(false)
      expect(inverseCond.test('label_key = None')).toBe(false)

      const projectCond =
        /if\s*\(\s*label_val\s+is\s+None\s+or\s+label_val\s*==\s*(?:""|'')\s*\)\s+and\s+label_key\s*!=\s*["']label["']\s*:/
      expect(projectCond.test('if (label_val is None or label_val == "") and label_key != "label":')).toBe(
        true,
      )
      expect(projectCond.test('if False:  # label_val label_key')).toBe(false)
    })
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// ✅ 组一（续）：反向自检 —— **必须全绿**
//    每条都真做：从一张当前**该维度零偏差**的表出发造替身，证明判据抓得住；
//    并用弱判据对照证明六维强于旧判据。
// ═════════════════════════════════════════════════════════════════════════════

/** 基准替身：listed 五、18「长期股权投资」—— 当前六维里除中文 key 外零偏差。 */
function baselineTriple(): TableTriple {
  const t = TRIPLES.find((x) => x.variant === 'listed' && x.section === '五、18')
  if (!t) throw new Error('基准替身取不到：listed 五、18')
  return t
}

function cloneCols(cols: ColumnLike[]): ColumnLike[] {
  return cols.map((c) => ({ ...c }))
}

function mutate(fn: (cols: ColumnLike[]) => void): TableTriple {
  const base = baselineTriple()
  const runtime = cloneCols(base.runtime)
  fn(runtime)
  return { ...base, runtime }
}

describe('G7 三向对齐守卫｜反向自检（必须全绿）', () => {
  it('基准替身在四个被检维度上零偏差（否则反向自检是「骑在既有红上」）', () => {
    const devs = devsOf(baselineTriple())
    const kinds = devs.map((d) => d.kind)
    for (const k of ['D-labelText', 'A-group', 'A源-group', 'B-labelKey', 'isLabel'] as DevKind[]) {
      expect(kinds, `基准替身本身已有 ${k} 偏差，不能用作反向自检基准`).not.toContain(k)
    }
    // 🔴 Wave 2 Task 4/5 后基准替身已**完全**零偏差（含中文 key 维度）。
    // 建档时这里曾断言 `toContain('labelKeyCjk')`（当时运行时标签列 key 是中文 `项目`，
    // 全 38 张表共性）；Task 4 把运行时统一为 `'label'`、Task 5 把 seed 统一为 `'label'`
    // 之后该断言必红 —— 它锁定的是**已被修好的旧状态**，故诚实改写为「一条偏差都没有」。
    expect(kinds, `基准替身应零偏差，实际：${JSON.stringify(kinds)}`).toEqual([])
  })

  it('改一个 label → 必打红（D 类）', () => {
    const t = mutate((cols) => {
      const target = cols.find((c) => !c.is_label)!
      target.label = `${target.label}【已改动】`
    })
    const devs = devsOf(t)
    expect(devs.map((d) => d.kind)).toContain('D-labelText')
    expect(weakVerdictFlatStanceOnly(t.runtime), '弱判据对照：应仍通过').toEqual([])
  })

  it('删一个 group → 必打红（A / A源 类）', () => {
    const t = mutate((cols) => {
      const target = cols.find((c) => c.group)!
      delete target.group
    })
    const devs = devsOf(t)
    expect(devs.map((d) => d.kind)).toContain('A-group')
    expect(devs.map((d) => d.kind)).toContain('A源-group')
    expect(weakVerdictFlatStanceOnly(t.runtime), '弱判据对照：应仍通过').toEqual([])
  })

  it('标签列 key 改成别的 → 必打红（B 类）', () => {
    const t = mutate((cols) => {
      cols.find((c) => c.is_label)!.key = 'someOtherKey'
    })
    const devs = devsOf(t)
    expect(devs.map((d) => d.kind)).toContain('B-labelKey')
    expect(weakVerdictFlatStanceOnly(t.runtime), '弱判据对照：应仍通过').toEqual([])
  })

  it('去掉 is_label → 必打红（is_label 维度）', () => {
    const t = mutate((cols) => {
      delete cols.find((c) => c.is_label)!.is_label
    })
    const devs = devsOf(t)
    expect(devs.map((d) => d.kind)).toContain('isLabel')
    expect(weakVerdictFlatStanceOnly(t.runtime), '弱判据对照：应仍通过').toEqual([])
  })

  it('改数据列 key → 必打红（C 类）', () => {
    const t = mutate((cols) => {
      cols.filter((c) => !c.is_label)[0].key = 'renamedKey'
    })
    expect(devsOf(t).map((d) => d.kind)).toContain('C-dataKey')
    expect(weakVerdictFlatStanceOnly(t.runtime)).toEqual([])
  })

  it('删一列 → 必打红（E 类）', () => {
    const t = mutate((cols) => {
      cols.splice(cols.length - 1, 1)
    })
    expect(devsOf(t).map((d) => d.kind)).toContain('E-colCount')
    expect(weakVerdictFlatStanceOnly(t.runtime)).toEqual([])
  })

  it('flat 与 group 并存 → 必打红（投影器会把 group 永久打掉）', () => {
    const t = mutate((cols) => {
      cols.find((c) => c.is_label)!.flat = true
    })
    const kinds = devsOf(t).map((d) => d.kind)
    expect(kinds).toContain('flat-group-conflict')
    expect(kinds).toContain('flat-stance')
    expect(weakVerdictFlatStanceOnly(t.runtime)).toEqual([])
  })

  it('弱判据对照总结：七个替身六维全打红、弱判据全通过 ⇒ 六维严格强于旧判据', () => {
    const substitutes: [string, DevKind, TableTriple][] = [
      [
        '改 label',
        'D-labelText',
        mutate((c) => {
          c.find((x) => !x.is_label)!.label = 'X'
        }),
      ],
      [
        '删 group',
        'A-group',
        mutate((c) => {
          delete c.find((x) => x.group)!.group
        }),
      ],
      [
        '改标签列 key',
        'B-labelKey',
        mutate((c) => {
          c.find((x) => x.is_label)!.key = 'k'
        }),
      ],
      [
        '去 is_label',
        'isLabel',
        mutate((c) => {
          delete c.find((x) => x.is_label)!.is_label
        }),
      ],
      [
        '改数据列 key',
        'C-dataKey',
        mutate((c) => {
          c.filter((x) => !x.is_label)[0].key = 'k2'
        }),
      ],
      [
        '删一列',
        'E-colCount',
        mutate((c) => {
          c.splice(c.length - 1, 1)
        }),
      ],
      [
        'flat 与 group 并存',
        'flat-group-conflict',
        mutate((c) => {
          c.find((x) => x.is_label)!.flat = true
        }),
      ],
    ]
    // 基准替身在这七个维度上一条偏差都没有（Wave 2 后它在全部维度上零偏差）
    const baseKinds = devsOf(baselineTriple()).map((d) => d.kind)
    for (const [name, kind, s] of substitutes) {
      expect(baseKinds, `基准替身已含 ${kind}，${name} 的反向自检会「骑在既有红上」`).not.toContain(kind)
      expect(devsOf(s).map((d) => d.kind), `${name}：六维判据应打红 ${kind}`).toContain(kind)
      expect(weakVerdictFlatStanceOnly(s.runtime), `${name}：弱判据应仍通过`).toEqual([])
    }
  })

  it('compareTableTriple 是纯函数（同输入同输出，不修改入参）', () => {
    const t = baselineTriple()
    const snapshot = JSON.stringify(t)
    const a = devsOf(t)
    const b = devsOf(t)
    expect(JSON.stringify(a)).toBe(JSON.stringify(b))
    expect(JSON.stringify(t)).toBe(snapshot)
  })

  it('compressGroups 与后端 _extract_column_groups 口径一致（跳 is_label + start 从 1）', () => {
    const cols: ColumnLike[] = [
      { key: 'lbl', label: 'L', is_label: true },
      { key: 'a', label: 'A', group: 'G1' },
      { key: 'b', label: 'B', group: 'G1' },
      { key: 'c', label: 'C' },
      { key: 'd', label: 'D', group: 'G2' },
    ]
    expect(compressGroups(cols)).toEqual([
      { group: 'G1', start: 1, span: 2 },
      { group: 'G2', start: 4, span: 1 },
    ])
    // 反向：若不跳 is_label，start 会整体偏移一位（这正是要防的错位形态）
    expect(compressGroups(cols, { skipLabel: false })[0]).toEqual({ group: 'G1', start: 2, span: 2 })
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// 🔴 组二：六维逐表比对 —— **对当前代码状态预期打红**
//    Wave 2/3 修完代码后这些用例才会转绿。红在这里是「已如实报出偏差」，不是守卫坏了。
// ═════════════════════════════════════════════════════════════════════════════
describe('G7 三向对齐守卫｜六维逐表比对（已全部收口，转为防回退）', () => {
  it('分类计数汇总（A~E + 附带维度）', () => {
    const order: DevKind[] = [
      'A-group',
      'A源-group',
      'B-labelKey',
      'C-dataKey',
      'D-labelText',
      'E-colCount',
      'flat-stance',
      'flat-group-conflict',
      'labelKeyCjk',
      'labelHeaderText',
    ]
    const rows = order.map((k) => `  ${CLASS_LABEL[k] ?? k}: ${byKind(k).length}`)
    const ae = (['A-group', 'B-labelKey', 'C-dataKey', 'D-labelText', 'E-colCount'] as DevKind[])
      .map((k) => byKind(k).length)
      .reduce((a, b) => a + b, 0)
    const msg =
      `G7 列结构三向对齐偏差（扫描 ${TRIPLES.length} 张表）：\n${rows.join('\n')}\n` +
      `  A~E 五类合计 = ${ae}\n  全部维度合计 = ${ALL_DEVIATIONS.length}\n` +
      '（六维已全部收口；本用例转为防回退闸：任一维度回升即打红）'
    expect(ae, msg).toBe(0)
  })

  it('A 类：丢 group（运行时 vs seed，同名同跨度）', () => {
    const devs = byKind('A-group')
    expect(devs.length, `A 类偏差 ${devs.length} 处：\n${render(devs)}`).toBe(0)
  })

  it('A源 类：运行时分组段数/跨度与源 xlsx 不符（动态占位只比段数与跨度）', () => {
    const devs = byKind('A源-group')
    expect(devs.length, `A源 类偏差 ${devs.length} 处：\n${render(devs)}`).toBe(0)
  })

  it('B 类：标签列 key 两侧不一致', () => {
    const devs = byKind('B-labelKey')
    expect(devs.length, `B 类偏差 ${devs.length} 处：\n${render(devs)}`).toBe(0)
  })

  it('B 类附条：运行时标签列 key 不得用中文字面量', () => {
    const devs = byKind('labelKeyCjk')
    expect(devs.length, `中文字面量当 key ${devs.length} 处：\n${render(devs)}`).toBe(0)
  })

  it('C 类：数据列 key 与 seed 不逐位相等（唯一有数据风险的一类）', () => {
    const devs = byKind('C-dataKey')
    expect(devs.length, `C 类偏差 ${devs.length} 处：\n${render(devs)}`).toBe(0)
  })

  it('D 类：运行时数据列 label 与源 xlsx 不逐字相等', () => {
    const devs = byKind('D-labelText')
    expect(devs.length, `D 类偏差 ${devs.length} 处：\n${render(devs)}`).toBe(0)
  })

  it('E 类：运行时数据列数与源 xlsx 不等', () => {
    const devs = byKind('E-colCount')
    expect(devs.length, `E 类偏差 ${devs.length} 处：\n${render(devs)}`).toBe(0)
  })

  it('flat 表态两侧不一致（A 类的症状，不得靠「补 flat」修）', () => {
    const devs = byKind('flat-stance')
    expect(devs.length, `flat 表态偏差 ${devs.length} 处：\n${render(devs)}`).toBe(0)
  })

  it('附带发现：标签列文字与源 xlsx label_header 不符（超出六维口径）', () => {
    const devs = byKind('labelHeaderText')
    expect(devs.length, `标签列文字偏差 ${devs.length} 处：\n${render(devs)}`).toBe(0)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 第四边：**渲染层**两级表头（2026-08-12 浏览器实测补齐）
//
// 🔴 立项理由（前三边结构性看不见的假绿）：
// 前三边只比「源 xlsx ↔ 附注 seed ↔ 运行时模型」，**从不看 DOM**。浏览器实测发现
// 两个披露 Tab 原本都是扁平 `v-for="column in effectiveColumns(table)"`、模板只读
// `label/width/type`、**`column.group` 一次都没读** ⇒ 模型里的分组是 additive 死代码：
//
//   源模板物理两级：listed 11/15 张、soe 13/23 张
//   浏览器实测两级：**0 张**（38 张表的 headRows 直方图 `{1: 38}`）
//
// 用户可见后果：国企「重要非全资子公司/主要财务信息」这类 5 家 × (期末数/期初数) 的表，
// DOM 里是 5 组一模一样的表头、没有公司名父行 —— 审计师无法分辨哪对属于哪家被投资单位。
//
// 修复后实测：listed 9 张、soe 11 张两级（合计 20），与本节期望逐张吻合。
//
// 期望值**不是**直接取 `is_two_level` —— 必须剔除 `single_slot_exemption` 且
// `exempt_kinds` 含 `group` 的表：那些表源侧父表头行是**空白合并单元格**（只填了 1 个
// 实体槽，如 soe C229:D229 空白 + C230='期末数' D230='期初数'），平台裁决为单级。
// 实测正是这 4 张（listed 2 + soe 2）把「24 张」修正为「20 张」。
// ─────────────────────────────────────────────────────────────────────────────

const SOE_TAB_REL =
  'audit-platform/frontend/src/components/workpaper/g7-long-term-equity-main/disclosure/G7TabDisclosureSOE.vue'
const LISTED_TAB_REL =
  'audit-platform/frontend/src/components/workpaper/g7-long-term-equity-main/disclosure/G7TabDisclosureListed.vue'
const HEADER_BLOCKS_REL =
  'audit-platform/frontend/src/components/workpaper/g7-long-term-equity-main/disclosure/g7DisclosureHeaderBlocks.ts'
const CELL_REL =
  'audit-platform/frontend/src/components/workpaper/g7-long-term-equity-main/disclosure/G7DisclosureCell.vue'

/**
 * 剥掉注释再做源码形态判据。
 *
 * 🔴 必需，不是洁癖：本节的反面断言是「不得保留扁平 `v-for="column in effectiveColumns(table)"`」，
 * 而改造后的 .vue 注释里正解释了「改造前是扁平 v-for」——不剥注释，这条断言会被
 * 注释里的同名字样骗成打红（假红），或反过来在真退回时被注释掩盖。
 *
 * 只剥 `<!-- -->` 与 `/* *\/`，以及**行首**的 `//`：不剥行内 `//` 以免打断 `https://`
 * 之类（平台已记过 `strip_comments` 连 SQL 一起剥掉的坑）。
 */
function stripBlockComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
}

/** 该表**应当**渲染两级表头：源侧物理两级 ∧ 未被单槽占位豁免掉 `group` 维度。 */
function shouldRenderTwoLevel(f: FactsTable | null): boolean {
  if (!f?.is_two_level) return false
  const ex = f.single_slot_exemption
  if (ex && ex.exempt_kinds.includes('group')) return false
  return true
}

/** 运行时模型是否真给出了父表头（= 至少一列带非空 `group`）。 */
function runtimeHasGroup(cols: ColumnLike[]): boolean {
  return cols.some((c) => !c.is_label && !!c.group)
}

/**
 * 模板是否**真的按分组渲染**（防退回扁平 v-for）。
 *
 * 判据是**形态**而非「字样存在」：必须同时满足
 *   ① 遍历 `headerBlocks(table)`；
 *   ② 存在 `v-if="blk.group"` 的外层 `el-table-column`；
 *   ③ 该外层列内**嵌套** `v-for="column in blk.columns"` 的内层 `el-table-column`。
 * 只查 ①②③ 之一都可能被「留着字样但改回扁平」骗过（平台已踩过 grep 式守卫的坑）。
 */
function templateRendersGroupedHeader(src: string): boolean {
  const iteratesBlocks = /v-for="\(blk, bi\) in headerBlocks\(table\)"/.test(src)
  const outerGrouped = /<el-table-column\s+v-if="blk\.group"\s+:label="blk\.group"/.test(src)
  const innerLeaf = /v-for="column in blk\.columns"/.test(src)
  // 嵌套关系：外层 group 列必须出现在内层叶子列之前，且两者之间没有闭合外层列
  const outerIdx = src.search(/<el-table-column\s+v-if="blk\.group"/)
  const innerIdx = src.search(/v-for="column in blk\.columns"/)
  const nested = outerIdx >= 0 && innerIdx > outerIdx
  return iteratesBlocks && outerGrouped && innerLeaf && nested
}

describe('G7 三向对齐守卫｜第四边：渲染层两级表头（DOM 判据的可测投影）', () => {
  it('分块函数与单元格组件存在，且分块逻辑只有一份实现（两个 Tab 共用）', () => {
    expect(existsSync(resolve(findRepoRoot(), HEADER_BLOCKS_REL))).toBe(true)
    expect(existsSync(resolve(findRepoRoot(), CELL_REL))).toBe(true)
    const soe = readText(SOE_TAB_REL)
    const listed = readText(LISTED_TAB_REL)
    for (const [name, src] of [['soe', soe], ['listed', listed]] as const) {
      expect(
        src.includes("from './g7DisclosureHeaderBlocks'"),
        `${name} Tab 未引用共享分块实现 ⇒ 可能在本地另写了一套 group 归并逻辑`,
      ).toBe(true)
      // 反面锚定：不得在 .vue 里自造分块（那会与共享实现漂移）
      expect(
        /function\s+buildG7HeaderBlocks/.test(src),
        `${name} Tab 里出现了 buildG7HeaderBlocks 的第二份实现`,
      ).toBe(false)
    }
  })

  it('两个 Tab 的模板都按分组渲染（嵌套 el-table-column），不是扁平 v-for', () => {
    for (const [name, rel] of [['soe', SOE_TAB_REL], ['listed', LISTED_TAB_REL]] as const) {
      const src = stripBlockComments(readText(rel))
      expect(
        templateRendersGroupedHeader(src),
        `${name} Tab 未按 headerBlocks 渲染两级表头 ⇒ 模型的 group 又成了死代码`,
      ).toBe(true)
      // 旧扁平形态必须消失（否则两套并存，谁生效取决于顺序）
      expect(
        /<el-table-column\s+v-for="column in (?:effectiveColumns|tableColumns)\(table\)"/.test(src),
        `${name} Tab 仍保留扁平 v-for 列渲染`,
      ).toBe(false)
    }
  })

  it('反向自检：把模板换回扁平形态 → 判据必须打红', () => {
    const flatLike = `
      <el-table-column
        v-for="column in effectiveColumns(table)"
        :key="column.key"
        :label="column.label"
      />`
    expect(templateRendersGroupedHeader(flatLike)).toBe(false)
    // 只留字样、不成形态（留 headerBlocks 调用但仍扁平）也必须打红
    const halfWay = `
      <template v-for="(blk, bi) in headerBlocks(table)" :key="bi">
        <el-table-column :label="blk.columns[0].label" />
      </template>`
    expect(templateRendersGroupedHeader(halfWay)).toBe(false)
    // 正确形态必须命中（否则判据恒假 = 守卫形同虚设）
    const good = `
      <template v-for="(blk, bi) in headerBlocks(table)" :key="\`blk-\${bi}\`">
        <el-table-column v-if="blk.group" :label="blk.group" align="center">
          <el-table-column v-for="column in blk.columns" :key="column.key" :label="column.label" />
        </el-table-column>
      </template>`
    expect(templateRendersGroupedHeader(good)).toBe(true)
  })

  it('逐表：运行时是否给出父表头 == 源侧是否应两级（剔除单槽占位豁免）', () => {
    const mismatched = TRIPLES.filter((t) => {
      if (!t.facts) return false
      return shouldRenderTwoLevel(t.facts) !== runtimeHasGroup(t.runtime)
    }).map(
      (t) =>
        `  ${t.variant}/${t.section}/${t.table}` +
        `\n        源应两级 = ${shouldRenderTwoLevel(t.facts)}` +
        `（is_two_level=${t.facts?.is_two_level}` +
        `, 单槽豁免=${!!t.facts?.single_slot_exemption}）` +
        `\n        运行时有 group = ${runtimeHasGroup(t.runtime)}`,
    )
    expect(mismatched, `以下表「源侧应两级」与「运行时给父表头」不一致：\n${mismatched.join('\n')}`)
      .toHaveLength(0)
  })

  it('两级表头张数锁死（反面锚定：listed 9 / soe 11，合计 20）', () => {
    const count = (v: Variant) =>
      TRIPLES.filter((t) => t.variant === v && t.facts && shouldRenderTwoLevel(t.facts)).length
    // 🔴 改造前浏览器实测 0 张；这两个数字是修复后的实测值，回退即打红。
    expect({ listed: count('listed'), soe: count('soe') }).toEqual({ listed: 9, soe: 11 })
  })

  it('单槽占位豁免恰 4 张（listed 2 + soe 2）且都确实物理两级 —— 否则期望值失去依据', () => {
    const exempted = TRIPLES.filter(
      (t) => t.facts?.single_slot_exemption?.exempt_kinds.includes('group'),
    )
    expect(exempted.map((t) => `${t.variant}/${t.table}`).sort()).toHaveLength(4)
    for (const t of exempted) {
      expect(
        t.facts?.is_two_level,
        `${t.variant}/${t.table} 被登记为单槽占位豁免，却不是物理两级 ⇒ 登记 stale`,
      ).toBe(true)
      expect(
        t.facts?.single_slot_exemption?.expected_source_runs,
        `${t.variant}/${t.table} 单槽豁免的 expected_source_runs 必须是 1`,
      ).toBe(1)
    }
  })

  it('分块函数：相邻同 group 合并、非相邻同名不合并（跨列合并不可能跳格）', () => {
    const cols = [
      { key: 'a', label: '期末数', group: '甲' },
      { key: 'b', label: '期初数', group: '甲' },
      { key: 'c', label: '合计', group: undefined },
      { key: 'd', label: '期末数', group: '甲' },
    ]
    const blocks = buildG7HeaderBlocks(cols as never)
    expect(blocks.map((b) => `${b.group ?? '-'}x${b.columns.length}`)).toEqual([
      '甲x2',
      '-x1',
      '甲x1',
    ])
    expect(hasG7TwoLevelHeader(cols as never)).toBe(true)
    expect(hasG7TwoLevelHeader([{ key: 'x', label: 'y' }] as never)).toBe(false)
    expect(buildG7HeaderBlocks(null)).toEqual([])
  })
})
