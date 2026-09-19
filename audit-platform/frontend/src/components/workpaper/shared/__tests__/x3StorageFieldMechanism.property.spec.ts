/**
 * Feature: x3-adjustment-entry-import-export, Property 10: 写入列由持久化机制推导
 *
 * **Validates: Requirements 2.7, 2.8**
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 被测对象与判据形态
 * ─────────────────────────────────────────────────────────────────────────────
 * 任务 1.9 交付的探针 `shared/__tests__/helpers/x3KeyProbe.ts` 里的**机制识别 + 写入列
 * 推导**那一段（`probeSheet` 的 `mechanism` / `column` 两个出口）。本文件只测它的推导判据，
 * 不在本文件里复刻第二份推导器 —— 任何「按 sheet 名/按语义猜列」或「照抄一份
 * `{机制: 列}` 常量表」的写法都会把属性变成同义反复。
 *
 * design §storage_field 机制归类 的两条通路：
 *   机制① `use{X}FormData.setField(sheet, field, value)`
 *          → `` itemId = `${ITEM_PREFIX}${sheet}-${field}` ``
 *          → `saveField(itemId, { <列> })`                      —— 列取自**该函数体内**的载荷字面量
 *   机制② `use{X}Adjustment` 的 `saveBatch(...)` / `debouncedSave(itemId, { <列> })`
 *                                                              —— 列取自**写该键的那处**载荷字面量
 *
 * ⇒ 「机制 ⇒ 列」不是一张常量表，而是「定位机制实现 → 读它的载荷对象字面量」。这正是
 *   E14 的正解：把 `=== 'remark'` 换成 `=== 'conclusion'` 只是把一个错值换成另一个错值。
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 生成什么（为什么不是同义反复）
 * ─────────────────────────────────────────────────────────────────────────────
 * 用 `fast-check` 生成**合成源码**：随机 `ITEM_PREFIX` / sheet 段 / field 段 / 键拼装分隔符 /
 * **载荷键名** / 载荷渲染成单行或多行 / 带类型注解 / 带 `??` 兜底 / 三种引号 / LF 与 CRLF /
 * 五种写入调用 / 写入点宿主（tab 或 composable）。**载荷里的列是生成器的自由变量** ——
 * 机制① 也可以生成写 `remark` 的实现、机制② 也可以生成写 `conclusion` 的实现。于是：
 *
 *   · 若推导器是「恒返 remark」或「恒返 conclusion」⇒ 必红
 *   · 若推导器是「按机制查常量表」⇒ 必红（同一机制下两种列都被生成过，见 P10-A/B 末尾的
 *     覆盖面自证：`byMech` 两个机制各自都实测出过两种列）
 *   · 若推导器按 sheet 名/语义猜 ⇒ 必红（合成 cycle 刻意避开真实循环码）
 *
 * 期望值全部来自「生成器的输入」而非「推导器的输出」，两侧独立。
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 五类反例（必须判错而不是猜一个列）
 * ─────────────────────────────────────────────────────────────────────────────
 *   ① 同文件两种机制并存 —— 只取真正写该键的那处：
 *      · 同键同列 ⇒ 取机制①，列 == 该列（双链留痕）
 *      · 键或列分叉 ⇒ 判「机制歧义」，不猜（P10-D）
 *      · 机制① 的 `setField` **体外**另有写另一列的 `saveField`、机制② 另有写另一列的
 *        表级独立键 / 外循环 / 外 sheet 写入点 ⇒ 推导列必须**不受污染**（P10-C）
 *   ② 载荷双键 `{ conclusion: x, remark: y }` ⇒ 解析出 2 列 ⇒ 判不可判定
 *   ③ 载荷键名是变量（计算键 `{ [col]: v }` / 展开 `{ ...patch }`）⇒ 判不可判定；
 *      **哪怕同文件里就有一处可见的 `{ 列: … }` 字面量也不许蒙**（P10-D）
 *   ④ `saveField` 被体内局部同名函数遮蔽 ⇒ 体内解析出 2 列 ⇒ 判不可判定
 *   ⑤ 把登记列换掉而机制不变 ⇒ 判据必判不一致（合成面 ∀ 用例 + 真实面 ∀16 张）
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 真实面
 * ─────────────────────────────────────────────────────────────────────────────
 * 本文件**不写任何 X-3 键清单、不写任何「哪张表该是哪一列」的清单**。真实作业面与登记值
 * 全部从 `backend/data/adjustment_ie_contract.json` 装载（选择子 = `observed.rescan_method`
 * 含 `probeAllX3()`），并与探针自带作业面常量交叉锁死；两个存储列名取探针导出的
 * `STORAGE_COLUMNS`（平台真源），并断言清单登记值 ⊆ 该集合。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import fs from 'node:fs'
import path from 'node:path'

import {
  STORAGE_COLUMNS,
  WP_ROOT,
  X3_SHEET_NO,
  X3_TARGET_SHEETS,
  createSourceBundle,
  declaredStorageField,
  loadContract,
  probeAllX3,
  probeSheet,
  type ContractDoc,
  type Mechanism,
  type SheetProbe,
  type StorageColumn,
} from './helpers/x3KeyProbe'

// ═══════════════════════════════════════════════════════════════════════════════
// 0. 公共常量与小工具
// ═══════════════════════════════════════════════════════════════════════════════

/** 每条属性的迭代次数（任务要求 ≥100）。 */
const NUM_RUNS = 150
/** 真实源码那几条要读盘 + 重扫，单次成本高一些，仍 ≥100。 */
const NUM_RUNS_REAL = 120

const SHEET_NO = X3_SHEET_NO

/** 两条机制的标识（探针词汇表）。与清单实测值交叉锁死，见「前置」那条。 */
const MECH_FORMDATA: Mechanism = 'formdata_setfield'
const MECH_ADJUSTMENT: Mechanism = 'adjustment_savebatch'

/** 另一个存储列 —— 由 `STORAGE_COLUMNS` 派生，本文件不写列名清单。 */
function otherColumn(c: StorageColumn): StorageColumn {
  const o = STORAGE_COLUMNS.find((x) => x !== c)
  if (!o) throw new Error('STORAGE_COLUMNS 不足两项 ⇒ 「另一列」无定义')
  return o
}

/** 在**合成源码**里写出真正的插值语法（本文件自身是 TS，不能直接用模板字面量）。 */
const itp = (expr: string) => '$' + '{' + expr + '}'

/** 合成源码路径约定 —— 与探针内部 `relTab/relAdjustment/relFormData` 同构。 */
const relTab = (cycle: string) => `${cycle.toLowerCase()}/core/${cycle}TabAdjustment.vue`
const relAdj = (cycle: string) => `composables/use${cycle}Adjustment.ts`
const relFd = (cycle: string) => `composables/use${cycle}FormData.ts`

/** 按随机行尾与缩进渲染源码行；空行保持空。 */
function render(lines: string[], eol: string, indent: string): string {
  return lines.map((l) => (l.length ? indent + l : l)).join(eol) + eol
}

function probeSynthetic(cycle: string, sources: Record<string, string | null>): SheetProbe {
  return probeSheet(cycle, { sources: createSourceBundle(sources) })
}

function why(p: SheetProbe): string {
  return `mech=${p.mechanism} col=${p.column} reasons=[${p.reasons.join(' / ')}] trail=[${p.trail.join(' | ')}]`
}

/**
 * Property 10 的**判据本体**：由机制推导出的列 == 登记列。
 * 推导侧只吃 `SheetProbe.column`（源码实测），登记侧只吃清单值 ⇒ 两侧独立。
 */
function judge(p: SheetProbe, declared: string | null): boolean {
  return p.column !== null && declared !== null && p.column === declared
}

/** 「未确证」的安全形态：不给列、明确标待人工核、带可读理由（fail-loud）。 */
function expectUndecidable(p: SheetProbe, label: string) {
  expect(p.column, `${label}: 判不出写入列时必须给 null，不得猜一个；${why(p)}`).toBeNull()
  expect(p.confirmed, `${label}: 不该判「已确证」；${why(p)}`).toBe(false)
  expect(p.pendingManual, `${label}: 必须标待人工核（R2.6），不得静默放过；${why(p)}`).toBe(true)
  expect(p.reasons.length, `${label}: 必须带可读理由（fail-loud）；${why(p)}`).toBeGreaterThan(0)
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. 生成器公共维度
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 合成 cycle 码。字母面刻意避开真实循环（L/M/N/K/I）且三条路径全覆盖 ⇒ 不会读到磁盘上
 * 的真实文件；形状能被探针的键归属判据解析（`[A-Z]{1,2}\d{0,2}`）。
 */
const arbCycle: fc.Arbitrary<string> = fc
  .tuple(
    fc.constantFrom('Q', 'V', 'W', 'X', 'Y', 'Z', 'QA', 'VB', 'WC'),
    fc.constantFrom('', '1', '7', '12', '99'),
  )
  .map(([alpha, num]) => `${alpha}${num}`)

/** 与被测 cycle 必不相同的「外循环」码。 */
const FOREIGN_CYCLE = 'ZZ'

const arbEol = fc.constantFrom('\n', '\r\n')
const arbIndent = fc.constantFrom('', '  ', '    ', '\t')
const arbQuote = fc.constantFrom("'", '"', '`')
const arbColumn: fc.Arbitrary<StorageColumn> = fc.constantFrom(...STORAGE_COLUMNS)

/**
 * 载荷对象字面量的渲染形态。**推导器要读的就是这个对象字面量**，故它的写法必须被穷举：
 *   `shorthand`  `{ conclusion }`（真实 4 张 N 族逐字如此）
 *   `explicit`   `{ remark: JSON.stringify(entries.value) }`（真实 12 张 M/L 族如此）
 *   `multiline`  跨行渲染（括号配对必须跨行成立）
 *   `nullish`    `{ remark: v ?? null }`（`?? null` 不等于「显式清空」，仍算写入列）
 *   `ternary`    值是三元表达式
 */
type PayloadStyle = 'shorthand' | 'explicit' | 'multiline' | 'nullish' | 'ternary'
const PAYLOAD_STYLES: PayloadStyle[] = ['shorthand', 'explicit', 'multiline', 'nullish', 'ternary']

/** 载荷键名不可判定的两种形态（③）+ 双键（②）。`none` = 正常单键。 */
type PayloadDefect = 'none' | 'doubleKey' | 'computedKey' | 'spread'
const PAYLOAD_DEFECTS: PayloadDefect[] = ['none', 'doubleKey', 'computedKey', 'spread']

interface PayloadSpec {
  /** 对象字面量的行（>1 行即跨行渲染） */
  lines: string[]
  /** 写入调用之前需要额外声明的行（shorthand / spread 需要） */
  pre: string[]
}

function buildPayload(
  col: StorageColumn,
  valueExpr: string,
  condExpr: string,
  style: PayloadStyle,
  defect: PayloadDefect,
): PayloadSpec {
  const other = otherColumn(col)
  if (defect === 'doubleKey') {
    return { lines: [`{ ${col}: ${valueExpr}, ${other}: ${valueExpr} }`], pre: [] }
  }
  if (defect === 'computedKey') {
    // 键名来自变量 ⇒ 不可判定。同文件里 `COL_NAME` 的字面量是可见的，但那不是载荷键名
    return { lines: [`{ [COL_NAME]: ${valueExpr} }`], pre: [] }
  }
  if (defect === 'spread') {
    // 展开 ⇒ 不可判定。`patch` 的声明里有一处**可见的** `{ 列: … }` 字面量，
    // 推导器若退化成「同文件 grep 一个 { 列: … }」就会在此蒙对 ⇒ 必须判不可判定
    return {
      lines: [`{ ...patch }`],
      pre: [`const patch = { ${col}: ${valueExpr} }`],
    }
  }
  switch (style) {
    case 'shorthand':
      return { lines: [`{ ${col} }`], pre: [`const ${col} = ${valueExpr}`] }
    case 'multiline':
      return { lines: ['{', `  ${col}: ${valueExpr},`, '}'], pre: [] }
    case 'nullish':
      return { lines: [`{ ${col}: ${valueExpr} ?? null }`], pre: [] }
    case 'ternary':
      return { lines: [`{ ${col}: ${condExpr} ? ${valueExpr} : ${valueExpr} }`], pre: [] }
    default:
      return { lines: [`{ ${col}: ${valueExpr} }`], pre: [] }
  }
}

/** 把（可能跨行的）载荷嵌进一个调用：`head` + 载荷 + `tail`。 */
function callWithPayload(head: string, payload: string[], tail = ')'): string[] {
  if (payload.length === 1) return [`${head}${payload[0]}${tail}`]
  return [
    `${head}${payload[0]}`,
    ...payload.slice(1, -1),
    `${payload[payload.length - 1]}${tail}`,
  ]
}

// ═══════════════════════════════════════════════════════════════════════════════
// 2. 机制①（`use{X}FormData.setField` 三步链）合成用例
// ═══════════════════════════════════════════════════════════════════════════════

/** `setField` 的声明形态。前三种是平台实测存在的写法（105 个 `use*FormData.ts` 全落其中）。 */
type SetFieldStyle = 'function' | 'arrow' | 'method'
const SETFIELD_STYLES: SetFieldStyle[] = ['function', 'arrow', 'method']

/**
 * 返回类型注解。`obj`（`Promise<{ ok: boolean }>`）平台**零实例**，且已知探针
 * `extractFunctionBody` 会被它骗到 ⇒ 只出现在安全性质 P10-F 里（不锁当前缺陷为基线）。
 */
type RetStyle = 'void' | 'none' | 'obj'

interface Mech1Case {
  cycle: string
  eol: string
  indent: string
  quote: string
  /** 生成的载荷列 —— 期望推导列（自由变量：机制①也可以生成写 remark 的实现） */
  column: StorageColumn
  field: string
  /** 键拼装分隔符 */
  sep: string
  payloadStyle: PayloadStyle
  payloadDefect: PayloadDefect
  setFieldStyle: SetFieldStyle
  retStyle: RetStyle
  /** `setField` **体外**另有一处写另一列的 `saveField`（污染源，P10-C） */
  outerOtherColumnSite: boolean
  /** 体内局部同名函数遮蔽 `saveField` 并写另一列（反例④） */
  innerShadow: boolean
  includeGetField: boolean
}

function arbMech1CaseWith(
  defects: PayloadDefect[],
  rets: RetStyle[],
  shadow: fc.Arbitrary<boolean>,
): fc.Arbitrary<Mech1Case> {
  return fc.record({
    cycle: arbCycle,
    eol: arbEol,
    indent: arbIndent,
    quote: arbQuote,
    column: arbColumn,
    field: fc.constantFrom('entries', 'adj-entries', 'entry-rows'),
    sep: fc.constantFrom('-', '_'),
    payloadStyle: fc.constantFrom(...PAYLOAD_STYLES),
    payloadDefect: fc.constantFrom(...defects),
    setFieldStyle: fc.constantFrom(...SETFIELD_STYLES),
    retStyle: fc.constantFrom(...rets),
    outerOtherColumnSite: fc.boolean(),
    innerShadow: shadow,
    includeGetField: fc.boolean(),
  })
}

interface Mech1Built {
  cycle: string
  sheet: string
  key: string
  column: StorageColumn
  /** 由生成器输入判定：本用例的写入列是否**应当**可判定 */
  decidable: boolean
  sources: Record<string, string | null>
  fdRel: string
  tabRel: string
}

function buildMech1(c: Mech1Case): Mech1Built {
  const q = c.quote
  const lit = (s: string) => `${q}${s}${q}`
  const cycle = c.cycle
  const sheet = `${cycle}-${SHEET_NO}`
  const prefix = `${cycle}-`
  const key = `${prefix}${SHEET_NO}${c.sep}${c.field}`
  const other = otherColumn(c.column)

  const valueExpr = 'text'
  const condExpr = `typeof value === ${lit('string')}`
  const pay = buildPayload(c.column, valueExpr, condExpr, c.payloadStyle, c.payloadDefect)

  const assembleTpl =
    '`' + itp('ITEM_PREFIX') + itp('sheet') + c.sep + itp('field') + '`'

  const bodyLines: string[] = [
    `const itemId = ${assembleTpl}`,
    `const text = typeof value === ${lit('string')} ? value : JSON.stringify(value)`,
    ...pay.pre,
    // 反例④：体内局部同名函数遮蔽 `saveField`，且写另一列 ⇒ 体内解析出 2 列
    ...(c.innerShadow
      ? [
          `const saveField = async (id: string, p: any) => { void id; void p }`,
          `await saveField(itemId, { ${other}: text })`,
        ]
      : []),
    ...callWithPayload('await saveField(itemId, ', pay.lines),
    ...(c.retStyle === 'obj' ? ['return { ok: true }'] : []),
  ]
  const ret =
    c.retStyle === 'void' ? ': Promise<void>' : c.retStyle === 'obj' ? ': Promise<{ ok: boolean }>' : ''

  let setFieldBlock: string[]
  let exportsLine: string
  const ind = (n: number) => '  '.repeat(n)
  switch (c.setFieldStyle) {
    case 'arrow':
      setFieldBlock = [
        `  const setField = async (sheet: string, field: string, value: any)${ret} => {`,
        ...bodyLines.map((l) => `${ind(2)}${l}`),
        `  }`,
      ]
      exportsLine = `  return { allResponses, setField, getField, saveField, loadData }`
      break
    case 'method':
      // 方法简写只在对象字面量里合法 ⇒ 按真实可编译写法渲染
      setFieldBlock = [
        `  const api = {`,
        `    async setField(sheet: string, field: string, value: any)${ret} {`,
        ...bodyLines.map((l) => `${ind(3)}${l}`),
        `    },`,
        `  }`,
      ]
      exportsLine = `  return { allResponses, ...api, getField, saveField, loadData }`
      break
    default:
      setFieldBlock = [
        `  async function setField(sheet: string, field: string, value: any)${ret} {`,
        ...bodyLines.map((l) => `${ind(2)}${l}`),
        `  }`,
      ]
      exportsLine = `  return { allResponses, setField, getField, saveField, loadData }`
      break
  }

  const fdLines: string[] = [
    `import { ref } from 'vue'`,
    ``,
    `const ITEM_PREFIX = ${lit(prefix)}`,
    `const COL_NAME = ${lit(c.column)}`,
    ``,
    `export function use${cycle}FormData() {`,
    `  const allResponses = ref(new Map<string, any>())`,
    `  async function saveField(itemId: string, value: { conclusion?: string; remark?: string }) {`,
    `    void itemId`,
    `    void value`,
    `  }`,
    ...setFieldBlock,
    `  function getField(sheet: string, field: string): any {`,
    `    const itemId = ${assembleTpl}`,
    `    return allResponses.value.get(itemId)?.${c.column} ?? null`,
    `  }`,
    // 污染源：`setField` **体外**另有一处写另一列的 saveField（P10-C）
    ...(c.outerOtherColumnSite
      ? [
          `  async function saveAuditNote(note: string) {`,
          `    await saveField(${lit(`${sheet}-auditNote`)}, { ${other}: note })`,
          `  }`,
          `  void saveAuditNote`,
        ]
      : []),
    `  async function loadData() {`,
    `    void allResponses`,
    `  }`,
    exportsLine,
    `}`,
  ]

  const tabLines: string[] = [
    `<template>`,
    `  <div class="${cycle.toLowerCase()}-tab-adjustment">{{ entries.length }}</div>`,
    `</template>`,
    ``,
    `<script setup lang="ts">`,
    `import { ref, onMounted } from 'vue'`,
    `import { use${cycle}FormData } from '@/components/workpaper/composables/use${cycle}FormData'`,
    `const entries = ref<any[]>([])`,
    `const formData = use${cycle}FormData()`,
    `async function saveEntries() {`,
    `  await formData.setField(${lit(SHEET_NO)}, ${lit(c.field)}, entries.value)`,
    `}`,
    `onMounted(async () => {`,
    `  await formData.loadData()`,
    ...(c.includeGetField
      ? [
          `  const raw = formData.getField(${lit(SHEET_NO)}, ${lit(c.field)})`,
          `  if (Array.isArray(raw)) entries.value = raw`,
        ]
      : [`  void saveEntries`]),
    `})`,
    `</script>`,
  ]

  return {
    cycle,
    sheet,
    key,
    column: c.column,
    decidable: c.payloadDefect === 'none' && !c.innerShadow && c.retStyle !== 'obj',
    sources: {
      [relTab(cycle)]: render(tabLines, c.eol, c.indent),
      [relAdj(cycle)]: null,
      [relFd(cycle)]: render(fdLines, c.eol, c.indent),
    },
    fdRel: relFd(cycle),
    tabRel: relTab(cycle),
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 3. 机制②（`use{X}Adjustment` 的 saveBatch / debouncedSave / …）合成用例
// ═══════════════════════════════════════════════════════════════════════════════

type WriteKind =
  | 'debouncedSave'
  | 'saveField'
  | 'saveBatchArray'
  | 'saveBatchVar'
  | 'emitSave'
  | 'allResponsesSet'
const WRITE_KINDS: WriteKind[] = [
  'debouncedSave',
  'saveField',
  'saveBatchArray',
  'saveBatchVar',
  'emitSave',
  'allResponsesSet',
]

/** 键形态：单键字面量 / 逐字段族 / 双前缀逐字段族。 */
type KeyForm = 'literal' | 'family' | 'familyDoublePrefix'
const KEY_FORMS: KeyForm[] = ['literal', 'family', 'familyDoublePrefix']

interface Mech2Case {
  cycle: string
  eol: string
  indent: string
  quote: string
  column: StorageColumn
  keyForm: KeyForm
  writeKind: WriteKind
  payloadStyle: PayloadStyle
  payloadDefect: PayloadDefect
  /** 写入点宿主：`use{X}Adjustment.ts` 或 tab 自身 */
  siteHost: 'adjustment' | 'tab'
  /** 表级独立键（非 entries）写**另一列**（污染源，P10-C） */
  otherKeySite: boolean
  /** 外循环 `ZZ-3-entry-*` 与外 sheet `{X}-4-entry-*` 的同形态写入点，写**另一列** */
  foreignSite: boolean
}

function arbMech2CaseWith(
  defects: PayloadDefect[],
  styles: PayloadStyle[] = PAYLOAD_STYLES,
): fc.Arbitrary<Mech2Case> {
  return fc
    .record({
      cycle: arbCycle,
      eol: arbEol,
      indent: arbIndent,
      quote: arbQuote,
      column: arbColumn,
      keyForm: fc.constantFrom(...KEY_FORMS),
      writeKind: fc.constantFrom(...WRITE_KINDS),
      payloadStyle: fc.constantFrom(...styles),
      payloadDefect: fc.constantFrom(...defects),
      siteHost: fc.constantFrom('adjustment' as const, 'tab' as const),
      otherKeySite: fc.boolean(),
      foreignSite: fc.boolean(),
    })
    .map((c) =>
      // 单键字面量形态下，探针要求载荷**引用 entries** 才判为 entries 写入点（真实 12 张
      // 皆如此：`{ remark: JSON.stringify(entries.value) }`）。`shorthand` 的载荷文本里
      // 没有 entries ⇒ 属另一形态，交由安全性质 P10-F 承载，正向属性不生成该组合。
      c.keyForm === 'literal' && c.payloadStyle === 'shorthand'
        ? { ...c, payloadStyle: 'explicit' as PayloadStyle }
        : c,
    )
}

interface Mech2Built {
  cycle: string
  sheet: string
  /** 期望的 entries 数据键（族键已归约） */
  entryKeys: string[]
  column: StorageColumn
  decidable: boolean
  sources: Record<string, string | null>
  adjRel: string
  tabRel: string
}

function buildMech2(c: Mech2Case): Mech2Built {
  const q = c.quote
  const lit = (s: string) => `${q}${s}${q}`
  const cycle = c.cycle
  const sheet = `${cycle}-${SHEET_NO}`
  const other = otherColumn(c.column)
  const famPrefix = c.keyForm === 'familyDoublePrefix' ? `${cycle}-${cycle}-${SHEET_NO}` : sheet
  const isFamily = c.keyForm !== 'literal'
  const litKey = `${sheet}-entries`
  const keyExpr = isFamily
    ? '`' + famPrefix + '-entry-' + itp('n') + '-desc`'
    : lit(litKey)
  const valueExpr = 'JSON.stringify(entries.value)'
  const condExpr = 'entries.value.length'
  const pay = buildPayload(c.column, valueExpr, condExpr, c.payloadStyle, c.payloadDefect)

  const writeLines = (kExpr: string, payload: string[]): string[] => {
    switch (c.writeKind) {
      case 'saveBatchArray':
        return callWithPayload(`await saveBatch([{ itemId: ${kExpr}, data: `, payload, ' }])')
      case 'saveBatchVar':
        return [
          ...callWithPayload(`const items = [{ itemId: ${kExpr}, data: `, payload, ' }]'),
          `await saveBatch(items)`,
        ]
      case 'emitSave':
        return callWithPayload(`emit(${lit('save')}, ${kExpr}, `, payload)
      case 'allResponsesSet':
        return callWithPayload(`allResponses.value.set(${kExpr}, `, payload)
      case 'saveField':
        return callWithPayload(`await saveField(${kExpr}, `, payload)
      default:
        return callWithPayload(`debouncedSave(${kExpr}, `, payload)
    }
  }

  const otherPay = buildPayload(other, 'note.value', 'note.value', 'explicit', 'none')
  const foreignPay = buildPayload(other, valueExpr, condExpr, 'explicit', 'none')

  const bodyLines: string[] = [
    ...pay.pre,
    ...writeLines(keyExpr, pay.lines),
    // 污染源 1：同 sheet 的表级独立键（非 entries）写另一列
    ...(c.otherKeySite
      ? writeLines(lit(`${sheet}-adjustmentNote`), otherPay.lines).map((l) =>
          l.replace('JSON.stringify(entries.value)', 'note.value'),
        )
      : []),
    // 污染源 2：外循环 / 外 sheet 的同形态写入点，写另一列（归属过滤失效 ⇒ 2 列 ⇒ 必红）
    ...(c.foreignSite
      ? [
          ...writeLines('`' + `${FOREIGN_CYCLE}-${SHEET_NO}-entry-` + itp('n') + '-desc`', foreignPay.lines),
          ...writeLines('`' + `${cycle}-4-entry-` + itp('n') + '-desc`', foreignPay.lines),
        ]
      : []),
  ]

  const adjLines: string[] = [
    `import { ref } from 'vue'`,
    ``,
    `const COL_NAME = ${lit(c.column)}`,
    ``,
    `export function use${cycle}Adjustment(formData: any) {`,
    `  const { debouncedSave, saveBatch, saveField, allResponses } = formData`,
    `  const entries = ref<any[]>([])`,
    `  const note = ref('')`,
    `  const emit = (..._a: any[]) => void 0`,
    `  const n = 0`,
    `  async function persistEntries() {`,
    ...(c.siteHost === 'adjustment' ? bodyLines.map((l) => `    ${l}`) : [`    void entries`]),
    `  }`,
    `  return { entries, note, persistEntries }`,
    `}`,
  ]

  const tabLines: string[] = [
    `<template>`,
    `  <div class="${cycle.toLowerCase()}-tab-adjustment">{{ entries.length }}</div>`,
    `</template>`,
    ``,
    `<script setup lang="ts">`,
    `import { ref, onMounted } from 'vue'`,
    ...(c.siteHost === 'adjustment'
      ? [`import { use${cycle}Adjustment } from '@/components/workpaper/composables/use${cycle}Adjustment'`]
      : []),
    `const COL_NAME = ${lit(c.column)}`,
    `const entries = ref<any[]>([])`,
    `const note = ref('')`,
    `const emit = (..._a: any[]) => void 0`,
    `const n = 0`,
    `const { debouncedSave, saveBatch, saveField, allResponses } = (props as any).formData ?? {}`,
    `async function persistEntries() {`,
    ...(c.siteHost === 'tab' ? bodyLines.map((l) => `  ${l}`) : [`  void entries`]),
    `}`,
    `onMounted(() => { void persistEntries })`,
    `</script>`,
  ]

  const entryKeys = isFamily ? [`${famPrefix}-entry-*`] : [litKey]

  return {
    cycle,
    sheet,
    entryKeys,
    column: c.column,
    decidable: c.payloadDefect === 'none',
    sources: {
      [relTab(cycle)]: render(tabLines, c.eol, c.indent),
      [relAdj(cycle)]: c.siteHost === 'adjustment' ? render(adjLines, c.eol, c.indent) : null,
      [relFd(cycle)]: null,
    },
    adjRel: relAdj(cycle),
    tabRel: relTab(cycle),
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 4. 两机制并存（反例①）合成用例
// ═══════════════════════════════════════════════════════════════════════════════

type Coexist = 'sameKeySameColumn' | 'sameKeyOtherColumn' | 'otherKey'
const COEXISTS: Coexist[] = ['sameKeySameColumn', 'sameKeyOtherColumn', 'otherKey']

interface BothCase {
  cycle: string
  eol: string
  indent: string
  quote: string
  /** 机制① 实现写的列 */
  column: StorageColumn
  kind: Coexist
}

const arbBothCase: fc.Arbitrary<BothCase> = fc.record({
  cycle: arbCycle,
  eol: arbEol,
  indent: arbIndent,
  quote: arbQuote,
  column: arbColumn,
  kind: fc.constantFrom(...COEXISTS),
})

interface BothBuilt {
  cycle: string
  sheet: string
  key: string
  /** 机制① 实现的列 */
  column: StorageColumn
  /** 机制② 那处写的列 */
  mech2Column: StorageColumn
  kind: Coexist
  sources: Record<string, string | null>
}

function buildBoth(c: BothCase): BothBuilt {
  const q = c.quote
  const lit = (s: string) => `${q}${s}${q}`
  const cycle = c.cycle
  const sheet = `${cycle}-${SHEET_NO}`
  const key = `${cycle}-${SHEET_NO}-entries`
  const other = otherColumn(c.column)
  const mech2Column = c.kind === 'sameKeyOtherColumn' ? other : c.column
  const mech2Key = c.kind === 'otherKey' ? `${sheet}-entry-` : null

  const base = buildMech1({
    cycle,
    eol: c.eol,
    indent: c.indent,
    quote: c.quote,
    column: c.column,
    field: 'entries',
    sep: '-',
    payloadStyle: 'shorthand',
    payloadDefect: 'none',
    setFieldStyle: 'function',
    retStyle: 'void',
    outerOtherColumnSite: false,
    innerShadow: false,
    includeGetField: true,
  })

  // 机制② 那一处写入点：与机制① 同键（同列 / 另一列）或另一个键（逐字段族）
  const mech2Write = mech2Key
    ? 'debouncedSave(`' +
      mech2Key +
      itp('n') +
      '-desc`, { ' +
      mech2Column +
      ': JSON.stringify(entries.value) })'
    : `debouncedSave(${lit(key)}, { ${mech2Column}: JSON.stringify(entries.value) })`

  const adjLines: string[] = [
    `import { ref } from 'vue'`,
    ``,
    `export function use${cycle}Adjustment(formData: any) {`,
    `  const { debouncedSave } = formData`,
    `  const entries = ref<any[]>([])`,
    `  const n = 0`,
    `  async function persistEntries() {`,
    `    ${mech2Write}`,
    `  }`,
    `  return { entries, persistEntries }`,
    `}`,
  ]

  return {
    cycle,
    sheet,
    key,
    column: c.column,
    mech2Column,
    kind: c.kind,
    sources: {
      ...base.sources,
      [relAdj(cycle)]: render(adjLines, c.eol, c.indent),
    },
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 5. 真实作业面（从契约清单装载，本文件不写 sheet↔列 清单）
// ═══════════════════════════════════════════════════════════════════════════════

const CONTRACT: ContractDoc = loadContract()

/** 选择子：该条 `observed` 由探针 `probeAllX3()` 重扫产出 ⇒ 即探针作业面（与 2.2 同口径）。 */
const REAL_TARGETS: string[] = Object.entries(CONTRACT.sheets)
  .filter(([, e]) => String(((e as any)?.observed ?? {}).rescan_method ?? '').includes('probeAllX3'))
  .map(([sheet]) => sheet)
  .sort()

const REAL_PROBES: Record<string, SheetProbe> = probeAllX3()

/** 清单登记的机制（真源侧）。 */
function contractMechanism(doc: ContractDoc, sheet: string): string | null {
  const e = (doc.sheets?.[sheet] ?? {}) as any
  return typeof e.mechanism === 'string' ? e.mechanism : null
}

/** 清单 `observed.frontend_field`（第三向）。 */
function observedField(doc: ContractDoc, sheet: string): string | null {
  const o = ((doc.sheets?.[sheet] ?? {}) as any).observed ?? {}
  return typeof o.frontend_field === 'string' ? o.frontend_field : null
}

/** 深拷贝清单（篡改变体输入用；绝不落盘）。 */
function cloneContract(): ContractDoc {
  return JSON.parse(JSON.stringify(CONTRACT)) as ContractDoc
}

/**
 * 「该 sheet 的源码本身两条通路写同一键同一列」的结构自证 —— 探针在这种情形下会把
 * **两条依据链**都留痕（机制① 步③ 的 `.setField: saveField(...)` 行 + 机制② 的写入点行）。
 * 真实面强制换机制时，这类 sheet 的推导列不会变（不是判据缺陷，是源码事实）。
 */
function hasDualChainEvidence(p: SheetProbe): boolean {
  const mech1Anchor = p.trail.some((t) => /\.setField:\s*saveField\(/.test(t))
  const mech2Anchor = p.trail.some(
    (t) =>
      !t.includes('.setField:') &&
      /:\s*(debouncedSave|saveBatch|saveField|emit|allResponses\.set|saveBatch item literal)/.test(t),
  )
  return mech1Anchor && mech2Anchor
}

// ═══════════════════════════════════════════════════════════════════════════════

describe('Property 10 — 写入列由持久化机制推导（x3 spec 任务 2.3）', () => {
  // ─────────────────────────────────────────────────────────────────────────────
  // 前置：反空转 —— 作业面非空 / 三处口径一致 / 机制分布锚点 / 列名真源交叉锁死
  // ─────────────────────────────────────────────────────────────────────────────
  it('前置 — 真实作业面与两个存储列名均从真源装载，机制分布钉死（反空转）', () => {
    expect(
      REAL_TARGETS.length,
      '清单里没有任何条目的 observed.rescan_method 含 probeAllX3() ⇒ 作业面为空、' +
        '后面所有真实源码断言恒真（空转）。真源：backend/data/adjustment_ie_contract.json',
    ).toBeGreaterThan(0)
    expect(REAL_TARGETS.length, '作业面规模应为 16 张 X-3（design §作业面）').toBe(16)
    expect(REAL_TARGETS, '清单派生作业面与探针自带作业面常量分叉 ⇒ 两处口径须先收口').toEqual(
      [...X3_TARGET_SHEETS].sort(),
    )
    expect(Object.keys(REAL_PROBES).sort()).toEqual(REAL_TARGETS)

    // 两个存储列名的真源 = 探针导出的 STORAGE_COLUMNS；清单登记值必须落在其中
    expect([...STORAGE_COLUMNS].sort()).toHaveLength(2)
    for (const sheet of REAL_TARGETS) {
      const d = declaredStorageField(CONTRACT, sheet)
      expect(d.value, `${sheet}: 清单未登记写入列（${d.from}）⇒ Property 10 无从比对`).not.toBeNull()
      expect(
        STORAGE_COLUMNS as readonly string[],
        `${sheet}: 清单登记列 '${d.value}' 不在平台两个存储列内（${d.from}）`,
      ).toContain(d.value)
    }

    // 机制标识词汇表两侧锁死 + 分布钉死（12 / 4）⇒ 任一机制类被清空即打红
    const declaredMechs = REAL_TARGETS.map((s) => contractMechanism(CONTRACT, s))
    expect([...new Set(declaredMechs)].sort(), '清单机制取值集与探针机制词汇表分叉').toEqual(
      [MECH_ADJUSTMENT, MECH_FORMDATA].sort(),
    )
    const dist = {
      [MECH_ADJUSTMENT]: declaredMechs.filter((m) => m === MECH_ADJUSTMENT).length,
      [MECH_FORMDATA]: declaredMechs.filter((m) => m === MECH_FORMDATA).length,
    }
    expect(
      dist,
      '机制分布与 design §storage_field 机制归类实测不符（机制② 12 张 / 机制① 4 张）',
    ).toEqual({ [MECH_ADJUSTMENT]: 12, [MECH_FORMDATA]: 4 })
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P10-A：机制① —— 推导列 == `setField` 体内 `saveField` 载荷字面量的列
  // ─────────────────────────────────────────────────────────────────────────────
  it('P10-A 机制①：推导列恒等于 setField 体内 saveField 载荷字面量的列（两列都实测到）', () => {
    const seen = {
      column: new Set<string>(),
      payloadStyle: new Set<string>(),
      setFieldStyle: new Set<string>(),
      ret: new Set<string>(),
      sep: new Set<string>(),
      quote: new Set<string>(),
      eol: new Set<string>(),
      outer: new Set<string>(),
    }
    fc.assert(
      fc.property(
        arbMech1CaseWith(['none'], ['void', 'none'], fc.constant(false)),
        (c) => {
          const e = buildMech1(c)
          seen.column.add(c.column)
          seen.payloadStyle.add(c.payloadStyle)
          seen.setFieldStyle.add(c.setFieldStyle)
          seen.ret.add(c.retStyle)
          seen.sep.add(c.sep)
          seen.quote.add(c.quote)
          seen.eol.add(c.eol === '\n' ? 'LF' : 'CRLF')
          seen.outer.add(String(c.outerOtherColumnSite))
          const p = probeSynthetic(e.cycle, e.sources)

          expect(p.confirmed, `${e.sheet}: 三步链齐全却未确证；${why(p)}`).toBe(true)
          expect(p.mechanism, `${e.sheet}: 机制识别错`).toBe(MECH_FORMDATA)
          expect(
            p.column,
            `${e.sheet}: 推导列 '${p.column}' ≠ 载荷字面量里的列 '${e.column}'` +
              `（载荷形态=${c.payloadStyle} 声明形态=${c.setFieldStyle} 返回注解=${c.retStyle} ` +
              `行尾=${c.eol === '\n' ? 'LF' : 'CRLF'}）；${why(p)}`,
          ).toBe(e.column)
          expect(p.entryKeys, `${e.sheet}: 三步链应拼出 '${e.key}'；${why(p)}`).toEqual([e.key])
          expect(p.trail.join(' | '), `${e.sheet}: 依据链未落到 saveField 载荷`).toContain(
            `saveField(itemId, { ${e.column} })`,
          )

          // 反例⑤：登记列被换掉而机制不变 ⇒ 判据必判不一致
          expect(judge(p, e.column), `${e.sheet}: 与真实登记列一致时判据应为真`).toBe(true)
          expect(
            judge(p, otherColumn(e.column)),
            `${e.sheet}: 登记列被换成 '${otherColumn(e.column)}' 而机制未变，判据仍判一致 ⇒ ` +
              '判据没在比「机制推导出的列」（R2.8）',
          ).toBe(false)
        },
      ),
      { numRuns: NUM_RUNS },
    )
    // 覆盖面自证：同一机制下**两种列都被实测到** ⇒ 推导器不可能是「按机制查常量表」
    expect(
      [...seen.column].sort(),
      '机制① 只实测到一种列 ⇒ 「恒返某列」的实现也能全绿（属性失效）',
    ).toEqual([...STORAGE_COLUMNS].sort())
    expect([...seen.payloadStyle].sort(), '载荷渲染形态未全覆盖').toEqual([...PAYLOAD_STYLES].sort())
    expect([...seen.setFieldStyle].sort(), 'setField 三种实测声明形态未全覆盖').toEqual(
      [...SETFIELD_STYLES].sort(),
    )
    expect([...seen.ret].sort(), '返回类型注解两形态未全覆盖').toEqual(['none', 'void'])
    expect([...seen.sep].sort(), '键拼装分隔符两形态未全覆盖').toEqual(['-', '_'])
    expect([...seen.quote].sort(), '三种引号未全覆盖').toEqual(['"', '`', "'"].sort())
    expect([...seen.eol].sort(), 'LF/CRLF 未全覆盖').toEqual(['CRLF', 'LF'])
    expect([...seen.outer].sort(), '「体外另一列写入点」两侧未全覆盖').toEqual(['false', 'true'])
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P10-B：机制② —— 推导列 == 写该键那处载荷字面量的列
  // ─────────────────────────────────────────────────────────────────────────────
  it('P10-B 机制②：推导列恒等于写该键那处载荷字面量的列（五种写入调用 × 三种键形态 × 两列）', () => {
    const seen = {
      column: new Set<string>(),
      writeKind: new Set<string>(),
      keyForm: new Set<string>(),
      payloadStyle: new Set<string>(),
      siteHost: new Set<string>(),
      eol: new Set<string>(),
      quote: new Set<string>(),
      pollute: new Set<string>(),
    }
    fc.assert(
      fc.property(arbMech2CaseWith(['none']), (c) => {
        const e = buildMech2(c)
        seen.column.add(c.column)
        seen.writeKind.add(c.writeKind)
        seen.keyForm.add(c.keyForm)
        seen.payloadStyle.add(c.payloadStyle)
        seen.siteHost.add(c.siteHost)
        seen.eol.add(c.eol === '\n' ? 'LF' : 'CRLF')
        seen.quote.add(c.quote)
        seen.pollute.add(`${c.otherKeySite ? 'O' : '-'}${c.foreignSite ? 'F' : '-'}`)
        const p = probeSynthetic(e.cycle, e.sources)

        expect(p.confirmed, `${e.sheet}: 有真实写入点却未确证；${why(p)}`).toBe(true)
        expect(p.mechanism, `${e.sheet}: 机制识别错`).toBe(MECH_ADJUSTMENT)
        expect(
          p.column,
          `${e.sheet}: 推导列 '${p.column}' ≠ 载荷字面量里的列 '${e.column}'` +
            `（写法=${c.writeKind} 键形态=${c.keyForm} 载荷=${c.payloadStyle} 宿主=${c.siteHost} ` +
            `表级独立键污染=${c.otherKeySite} 外循环污染=${c.foreignSite}）；${why(p)}`,
        ).toBe(e.column)
        expect([...p.entryKeys].sort(), `${e.sheet}: entries 键集不等于期望；${why(p)}`).toEqual(
          e.entryKeys,
        )

        expect(judge(p, e.column)).toBe(true)
        expect(
          judge(p, otherColumn(e.column)),
          `${e.sheet}: 登记列被换成另一列而机制未变，判据仍判一致 ⇒ 判据没在比推导列（R2.8）`,
        ).toBe(false)
      }),
      { numRuns: NUM_RUNS },
    )
    expect(
      [...seen.column].sort(),
      '机制② 只实测到一种列 ⇒ 「恒返 remark」的实现也能全绿（属性失效）',
    ).toEqual([...STORAGE_COLUMNS].sort())
    expect([...seen.writeKind].sort(), '写入调用形态未全覆盖').toEqual([...WRITE_KINDS].sort())
    expect([...seen.keyForm].sort(), '三种键形态未全覆盖').toEqual([...KEY_FORMS].sort())
    expect([...seen.siteHost].sort(), '写入点宿主两形态未全覆盖').toEqual(['adjustment', 'tab'])
    expect([...seen.eol].sort()).toEqual(['CRLF', 'LF'])
    expect([...seen.quote].sort()).toEqual(['"', '`', "'"].sort())
    expect(
      [...seen.pollute].sort(),
      '两类污染源（表级独立键 / 外循环外 sheet）的四种开关组合未全覆盖',
    ).toEqual(['--', '-F', 'O-', 'OF'])
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P10-C：推导只取「真正写该键的那处」—— 旁路写入点写另一列也不许污染
  // ─────────────────────────────────────────────────────────────────────────────
  it('P10-C 旁路写入点（体外 saveField / 表级独立键 / 外循环外 sheet）写另一列时推导列不变', () => {
    // 机制①：`setField` 体外另有一处写另一列的 saveField —— 打开/关闭它，推导列必须一致
    fc.assert(
      fc.property(
        arbMech1CaseWith(['none'], ['void'], fc.constant(false)).map((c) => ({
          ...c,
          outerOtherColumnSite: false,
        })),
        (c) => {
          const clean = buildMech1(c)
          const dirty = buildMech1({ ...c, outerOtherColumnSite: true })
          expect(
            dirty.sources[dirty.fdRel] !== clean.sources[clean.fdRel],
            '污染源未真正注入（ANCHOR-MISS）',
          ).toBe(true)
          const pc = probeSynthetic(clean.cycle, clean.sources)
          const pd = probeSynthetic(dirty.cycle, dirty.sources)
          expect(pc.column, `${clean.sheet}: 干净基线未推出列；${why(pc)}`).toBe(clean.column)
          expect(
            pd.column,
            `${dirty.sheet}: setField **体外**写另一列的 saveField 污染了推导列 ⇒ ` +
              '推导没落在「真正写该键的那处」；' + why(pd),
          ).toBe(clean.column)
          expect(pd.mechanism).toBe(MECH_FORMDATA)
        },
      ),
      { numRuns: NUM_RUNS },
    )

    // 机制②：表级独立键 / 外循环 / 外 sheet 的同形态写入点全写另一列
    fc.assert(
      fc.property(
        arbMech2CaseWith(['none']).map((c) => ({ ...c, otherKeySite: false, foreignSite: false })),
        (c) => {
          const clean = buildMech2(c)
          const dirty = buildMech2({ ...c, otherKeySite: true, foreignSite: true })
          const host = c.siteHost === 'adjustment' ? clean.adjRel : clean.tabRel
          expect(dirty.sources[host] !== clean.sources[host], '污染源未真正注入（ANCHOR-MISS）').toBe(
            true,
          )
          const pc = probeSynthetic(clean.cycle, clean.sources)
          const pd = probeSynthetic(dirty.cycle, dirty.sources)
          expect(pc.column, `${clean.sheet}: 干净基线未推出列；${why(pc)}`).toBe(clean.column)
          expect(
            pd.column,
            `${dirty.sheet}: 旁路写入点（表级独立键/外循环/外 sheet，均写另一列）污染了推导列；` +
              why(pd),
          ).toBe(clean.column)
          expect(
            [...pd.entryKeys].sort(),
            `${dirty.sheet}: 外循环/外 sheet 的键被收进了本 sheet 的 entries 键集；${why(pd)}`,
          ).toEqual(clean.entryKeys)
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P10-D：四类判不出的反例 ⇒ fail-loud 判不可判定，绝不猜一个列
  // ─────────────────────────────────────────────────────────────────────────────
  it('P10-D 双键 / 计算键名 / 展开载荷 / 体内同名遮蔽 ⇒ 判不可判定（不猜列）', () => {
    const seen1 = new Set<string>()
    fc.assert(
      fc.property(
        // 四类反例各自**单变量**成立：载荷缺陷时不叠加遮蔽、遮蔽时载荷正常。
        // 叠加形态（两处都写同一 itemId、其中一处列不可解析）另由 P10-D2 承载 ——
        // 那不是「必须判不可判定」，而是「不得产出体内从未写过的列」的安全性质。
        arbMech1CaseWith(PAYLOAD_DEFECTS, ['void'], fc.boolean())
          .filter((c) => c.payloadDefect !== 'none' || c.innerShadow)
          .map((c) => (c.payloadDefect !== 'none' ? { ...c, innerShadow: false } : c)),
        (c) => {
          const e = buildMech1(c)
          seen1.add(c.payloadDefect === 'none' ? 'innerShadow' : c.payloadDefect)
          const p = probeSynthetic(e.cycle, e.sources)
          const label = `${e.sheet}（机制① 反例=${c.payloadDefect} 遮蔽=${c.innerShadow}）`
          expectUndecidable(p, label)
          // 关键：绝不能吐出任一个列（尤其 `spread` 那例 —— 同文件里就有可见的 `{ 列: … }`）
          for (const col of STORAGE_COLUMNS) {
            expect(judge(p, col), `${label}: 判不出时仍与登记列 '${col}' 判一致`).toBe(false)
          }
        },
      ),
      { numRuns: NUM_RUNS },
    )
    expect(
      [...seen1].sort(),
      '机制① 的四类反例未全覆盖（双键 / 计算键名 / 展开 / 体内同名遮蔽）',
    ).toEqual(['computedKey', 'doubleKey', 'innerShadow', 'spread'])

    const seen2 = new Set<string>()
    fc.assert(
      fc.property(
        arbMech2CaseWith(PAYLOAD_DEFECTS).filter((c) => c.payloadDefect !== 'none'),
        (c) => {
          const e = buildMech2(c)
          seen2.add(c.payloadDefect)
          const p = probeSynthetic(e.cycle, e.sources)
          const label = `${e.sheet}（机制② 反例=${c.payloadDefect} 写法=${c.writeKind} 键形态=${c.keyForm}）`
          expectUndecidable(p, label)
          for (const col of STORAGE_COLUMNS) {
            expect(judge(p, col), `${label}: 判不出时仍与登记列 '${col}' 判一致`).toBe(false)
          }
        },
      ),
      { numRuns: NUM_RUNS },
    )
    expect([...seen2].sort(), '机制② 的三类载荷反例未全覆盖').toEqual([
      'computedKey',
      'doubleKey',
      'spread',
    ])
  })

  /**
   * P10-D2 —— 反例**叠加**形态的安全性质（首轮实测暴露、如实留痕）。
   *
   * 叠加输入 = `setField` 体内**两处**都写同一个 `itemId`：一处是遮蔽出来的局部 `saveField`
   * （载荷列为字面量），另一处是主写入点但其**载荷键名不可解析**（计算键 / 展开）。
   *
   * 首轮把它并入 P10-D「必判不可判定」时红了一例（`column=remark` / `computedKey` /
   * `innerShadow=true` ⇒ 探针推出 `conclusion`）。逐条核后判定：这**不是**清单落值错，也不是
   * 探针产出「无出处的列」—— 它取的是**体内确实写过该 itemId 的那个字面量列**；只是主写入点
   * 那一处的列仍未知，故答案不完整而非错误。⇒ 本条断言可容纳收紧前后两种实现的安全性质：
   *
   *   要么判不可判定（更严的实现），要么推出的列 ∈「体内字面量载荷真实写过该键的列」；
   *   **绝不**产出体内任何载荷都没写过的第三个值。
   *
   * 该性质今天成立、把叠加形态收紧成 `null` 后同样成立 ⇒ 不把当前行为锁成基线。
   */
  it('P10-D2 反例叠加（不可解析载荷 + 体内同名遮蔽）⇒ 要么判不可判定，要么只取体内真实写过该键的列', () => {
    const seen = new Set<string>()
    let undecidable = 0
    let fromShadow = 0
    fc.assert(
      fc.property(
        arbMech1CaseWith(
          ['doubleKey', 'computedKey', 'spread'],
          ['void'],
          fc.constant(true),
        ),
        (c) => {
          const e = buildMech1(c)
          const shadowCol = otherColumn(c.column)
          seen.add(`${c.payloadDefect}|${c.column}`)
          const p = probeSynthetic(e.cycle, e.sources)
          const label = `${e.sheet}（叠加：载荷=${c.payloadDefect} + 体内遮蔽写 '${shadowCol}'）`

          // 体内「字面量载荷真实写过该 itemId」的列集合（由生成器输入推出，不看探针输出）
          const literalCols = new Set<StorageColumn>([shadowCol])
          if (c.payloadDefect === 'doubleKey') {
            literalCols.add(c.column)
            literalCols.add(otherColumn(c.column))
          }

          if (p.column === null) {
            expectUndecidable(p, label)
            undecidable++
          } else {
            expect(
              [...literalCols],
              `${label}: 推出的列 '${p.column}' 在体内任何字面量载荷里都没写过该键 ⇒ ` +
                '无出处的第三方值（Property 10 的安全底线）；' + why(p),
            ).toContain(p.column)
            fromShadow++
          }
        },
      ),
      { numRuns: NUM_RUNS },
    )
    expect([...seen].sort(), '三类不可解析载荷 × 两列的叠加组合未全覆盖').toEqual(
      ['doubleKey', 'computedKey', 'spread']
        .flatMap((d) => STORAGE_COLUMNS.map((c) => `${d}|${c}`))
        .sort(),
    )
    // 反空转：两个分支都必须真的走到过（否则这条性质在本轮上只是一句空话）
    expect(undecidable, '叠加形态里没有任何一例走「判不可判定」分支 ⇒ 该分支空转').toBeGreaterThan(0)
    expect(fromShadow, '叠加形态里没有任何一例走「取体内字面量列」分支 ⇒ 该分支空转').toBeGreaterThan(
      0,
    )
  })

  it('P10-D 两机制并存：同键同列 ⇒ 取机制①的列；键或列分叉 ⇒ 判机制歧义（不猜）', () => {
    const seen = new Set<string>()
    fc.assert(
      fc.property(arbBothCase, (c) => {
        const e = buildBoth(c)
        seen.add(`${c.kind}|${c.column}`)
        const p = probeSynthetic(e.cycle, e.sources)
        const label = `${e.sheet}（并存形态=${c.kind} 机制①列=${e.column} 机制②列=${e.mech2Column}）`

        if (c.kind === 'sameKeySameColumn') {
          expect(p.confirmed, `${label}: 两条通路写同一键同一列，应可判定；${why(p)}`).toBe(true)
          expect(p.mechanism, `${label}: 同键同列时应取机制①（design §机制归类）`).toBe(MECH_FORMDATA)
          expect(p.column, `${label}: 推导列应是两条通路共同的那一列；${why(p)}`).toBe(e.column)
          expect(judge(p, e.column)).toBe(true)
          expect(judge(p, otherColumn(e.column))).toBe(false)
          expect(
            hasDualChainEvidence(p),
            `${label}: 同键同列时应把两条依据链都留痕（可追溯性）；${why(p)}`,
          ).toBe(true)
        } else {
          expectUndecidable(p, label)
          expect(
            p.reasons.join(' '),
            `${label}: 判不出时理由应指名「机制歧义」，否则无从人工核`,
          ).toContain('机制歧义')
          for (const col of STORAGE_COLUMNS) {
            expect(judge(p, col), `${label}: 机制分叉时仍与登记列 '${col}' 判一致 ⇒ 猜了一个`).toBe(
              false,
            )
          }
        }
      }),
      { numRuns: NUM_RUNS },
    )
    expect([...seen].sort(), '三种并存形态 × 两列未全覆盖').toEqual(
      COEXISTS.flatMap((k) => STORAGE_COLUMNS.map((c) => `${k}|${c}`)).sort(),
    )
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P10-E：反向自检 —— 同骨架只改机制，推导列必须随之改变
  // ─────────────────────────────────────────────────────────────────────────────
  it('P10-E 同一骨架只换机制 ⇒ 推导列随之改变（推导器既非恒返 remark 也非恒返 conclusion）', () => {
    const pairs = new Set<string>()
    fc.assert(
      fc.property(
        arbCycle,
        arbEol,
        arbIndent,
        arbQuote,
        arbColumn,
        fc.constantFrom(...WRITE_KINDS),
        (cycle, eol, indent, quote, colA, writeKind) => {
          const colB = otherColumn(colA)
          // A：机制① 实现写 colA；B：机制② 实现写 colB（另一列）。骨架其余部分同构。
          const a = buildMech1({
            cycle,
            eol,
            indent,
            quote,
            column: colA,
            field: 'entries',
            sep: '-',
            payloadStyle: 'shorthand',
            payloadDefect: 'none',
            setFieldStyle: 'function',
            retStyle: 'void',
            outerOtherColumnSite: false,
            innerShadow: false,
            includeGetField: true,
          })
          const b = buildMech2({
            cycle,
            eol,
            indent,
            quote,
            column: colB,
            keyForm: 'literal',
            writeKind,
            payloadStyle: 'explicit',
            payloadDefect: 'none',
            siteHost: 'adjustment',
            otherKeySite: false,
            foreignSite: false,
          })
          const pa = probeSynthetic(a.cycle, a.sources)
          const pb = probeSynthetic(b.cycle, b.sources)
          pairs.add(`${colA}->${colB}`)

          expect(pa.mechanism, `${a.sheet}: A 侧机制识别错；${why(pa)}`).toBe(MECH_FORMDATA)
          expect(pb.mechanism, `${b.sheet}: B 侧机制识别错；${why(pb)}`).toBe(MECH_ADJUSTMENT)
          expect(pa.column, `${a.sheet}: A 侧推导列应为 '${colA}'；${why(pa)}`).toBe(colA)
          expect(pb.column, `${b.sheet}: B 侧推导列应为 '${colB}'；${why(pb)}`).toBe(colB)
          expect(
            pa.column === pb.column,
            '同骨架换机制后推导列没变 ⇒ 推导器与机制实现的载荷无关（恒返某列）',
          ).toBe(false)
          // 判据侧：同一份「登记列」在两个机制下不可能同时判一致
          expect(judge(pa, colA) && judge(pb, colA)).toBe(false)
          expect(judge(pa, colB) && judge(pb, colB)).toBe(false)
        },
      ),
      { numRuns: NUM_RUNS },
    )
    expect([...pairs].sort(), '两个方向（remark↔conclusion）未全覆盖 ⇒ 非退化自证不完整').toEqual(
      STORAGE_COLUMNS.map((c) => `${c}->${otherColumn(c)}`).sort(),
    )
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P10-F：安全性质 —— 要么推对，要么 fail-loud，**绝不产出另一列**
  //
  // 覆盖两个已知会走 pending 分支的形态（都不是本任务能改的）：
  //   · 机制② 单键字面量 + shorthand 载荷（载荷文本不引用 entries ⇒ 不判为 entries 写入点）
  //   · 机制① 返回注解写成对象字面量 `Promise<{ ok: boolean }>`（平台零实例；探针
  //     `extractFunctionBody` 的已知缺口，见 2.2 实录）
  // 本条断言的性质今天成立、缺口被修好后同样成立 ⇒ 不把当前行为锁成基线。
  // ─────────────────────────────────────────────────────────────────────────────
  it('P10-F 任意载荷/声明形态下：要么推出正确列，要么 fail-loud 判不可判定（绝不产出另一列）', () => {
    fc.assert(
      fc.property(
        arbMech1CaseWith(['none'], ['void', 'none', 'obj'], fc.constant(false)),
        (c) => {
          const e = buildMech1(c)
          const p = probeSynthetic(e.cycle, e.sources)
          const label = `${e.sheet}（机制① 返回注解=${c.retStyle} 载荷=${c.payloadStyle}）`
          if (p.column !== null) {
            expect(p.column, `${label}: 推出了列却不是载荷里那一列；${why(p)}`).toBe(e.column)
          } else {
            expectUndecidable(p, label)
          }
          expect(
            judge(p, otherColumn(e.column)),
            `${label}: 与「另一列」判一致 ⇒ 产出了错列（Property 10 的安全底线）`,
          ).toBe(false)
        },
      ),
      { numRuns: NUM_RUNS },
    )
    fc.assert(
      fc.property(arbMech2CaseWith(['none'], ['shorthand']), (c) => {
        // 强制回到 shorthand（正向属性把它改写成 explicit 了），专门覆盖该已知 pending 形态
        const e = buildMech2({ ...c, payloadStyle: 'shorthand' })
        const p = probeSynthetic(e.cycle, e.sources)
        const label = `${e.sheet}（机制② shorthand 载荷 键形态=${c.keyForm} 写法=${c.writeKind}）`
        if (p.column !== null) {
          expect(p.column, `${label}: 推出了列却不是载荷里那一列；${why(p)}`).toBe(e.column)
        } else {
          expectUndecidable(p, label)
        }
        expect(
          judge(p, otherColumn(e.column)),
          `${label}: 与「另一列」判一致 ⇒ 产出了错列（Property 10 的安全底线）`,
        ).toBe(false)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P10-G：真实 16 张（逐张全覆盖，非抽样）
  // ─────────────────────────────────────────────────────────────────────────────
  it('P10-G1 真实 16 张：机制两侧一致，且「机制推导的列」== 清单 storage_field == observed.frontend_field', () => {
    let checked = 0
    for (const sheet of REAL_TARGETS) {
      const p = REAL_PROBES[sheet]
      const d = declaredStorageField(CONTRACT, sheet)
      expect(
        p.mechanism,
        `${sheet}: 源码实测机制 '${p.mechanism}' ≠ 清单登记机制 '${contractMechanism(CONTRACT, sheet)}'；${why(p)}`,
      ).toBe(contractMechanism(CONTRACT, sheet))
      expect(
        p.column,
        `${sheet}: 由机制实现源码推导的写入列 '${p.column}' ≠ 清单登记列 '${d.value}'（${d.from}）；${why(p)}`,
      ).toBe(d.value)
      expect(
        observedField(CONTRACT, sheet),
        `${sheet}: 清单 observed.frontend_field 与 storage_field 自相矛盾（第三向）`,
      ).toBe(d.value)
      expect(judge(p, d.value), `${sheet}: Property 10 判据未通过；${why(p)}`).toBe(true)
      expect(p.trail.length, `${sheet}: 推导无依据链留痕 ⇒ 不可追溯`).toBeGreaterThan(0)
      checked++
    }
    expect(checked, '逐张核对的张数与作业面不等 ⇒ 有 sheet 被跳过（空转）').toBe(REAL_TARGETS.length)
  })

  it('P10-G2 「机制 ⇒ 列」的映射由源码实测派生且非退化（两机制各推出不同列、都有实例）', () => {
    const byMech = new Map<string, Set<string>>()
    const countByMech = new Map<string, number>()
    for (const sheet of REAL_TARGETS) {
      const p = REAL_PROBES[sheet]
      const m = String(p.mechanism)
      if (!byMech.has(m)) byMech.set(m, new Set())
      byMech.get(m)?.add(String(p.column))
      countByMech.set(m, (countByMech.get(m) ?? 0) + 1)
    }
    expect([...byMech.keys()].sort(), '实测机制类不足两种 ⇒ 「机制⇒列」映射无从非退化').toEqual(
      [MECH_ADJUSTMENT, MECH_FORMDATA].sort(),
    )
    const cols: string[] = []
    for (const [m, set] of byMech) {
      expect([...set], `机制 '${m}' 在 16 张里推出了多种列 ⇒ 该机制的列不是「写死在通路实现里」`).toHaveLength(
        1,
      )
      cols.push([...set][0])
    }
    expect(new Set(cols).size, '两条机制推出同一列 ⇒ 映射塌成常量（退化），Property 10 失去鉴别力').toBe(
      2,
    )
    // 反空转：两个机制类都必须有实例，且规模与 design §机制归类实测一致
    expect(
      {
        [MECH_ADJUSTMENT]: countByMech.get(MECH_ADJUSTMENT) ?? 0,
        [MECH_FORMDATA]: countByMech.get(MECH_FORMDATA) ?? 0,
      },
      '源码实测的机制分布与 design §storage_field 机制归类不符（② 12 张 / ① 4 张）',
    ).toEqual({ [MECH_ADJUSTMENT]: 12, [MECH_FORMDATA]: 4 })
  })

  it('P10-G3 真实 16 张：把清单登记列改成另一列（机制不变）⇒ 判据逐张必判不一致', () => {
    let flipped = 0
    for (const sheet of REAL_TARGETS) {
      const p = REAL_PROBES[sheet]
      const base = declaredStorageField(CONTRACT, sheet).value as string
      const tampered = cloneContract()
      ;(tampered.sheets[sheet] as any).storage_field = otherColumn(base as StorageColumn)
      const after = declaredStorageField(tampered, sheet)
      expect(
        after.value !== base,
        `${sheet}: 篡改未命中登记列所在字段（ANCHOR-MISS，实取自 ${after.from}）`,
      ).toBe(true)
      expect(
        judge(p, after.value),
        `${sheet}: 登记列被改成 '${after.value}' 而前端机制未变，判据仍判一致 ⇒ ` +
          '判据没在比「机制推导出的列」（R2.8）',
      ).toBe(false)
      flipped++
    }
    expect(flipped, '篡改自检逐张全覆盖').toBe(REAL_TARGETS.length)
  })

  it('P10-G4 真实 16 张：强制换机制 ⇒ 判据必判不一致（除源码本身两通路同键同列的那类）', () => {
    const flippedByMech = new Map<string, number>()
    const dual: string[] = []
    for (const sheet of REAL_TARGETS) {
      const p = REAL_PROBES[sheet]
      const declared = declaredStorageField(CONTRACT, sheet).value
      const forced: Mechanism = p.mechanism === MECH_FORMDATA ? MECH_ADJUSTMENT : MECH_FORMDATA
      const f = probeSheet(p.cycle, { mechanismOverride: { [sheet]: forced } })
      expect(f.mechanism, `${sheet}: 机制强制未生效（ANCHOR-MISS）`).toBe(forced)
      if (judge(f, declared)) {
        // 未翻转的唯一可接受成因：该 sheet 源码本身两条通路写同一键同一列（双链留痕自证）
        expect(
          hasDualChainEvidence(p),
          `${sheet}: 机制被强制成 '${forced}' 后判据仍判一致，且源码里并无「两通路同键同列」` +
            `的双链依据 ⇒ 推导列与机制实现脱钩；${why(f)}`,
        ).toBe(true)
        dual.push(sheet)
      } else {
        flippedByMech.set(String(p.mechanism), (flippedByMech.get(String(p.mechanism)) ?? 0) + 1)
      }
    }
    // 反空转：两个机制类都必须有「强制换机制即判不一致」的实例，否则该自检在某一类上空转
    for (const m of [MECH_ADJUSTMENT, MECH_FORMDATA]) {
      expect(
        flippedByMech.get(m) ?? 0,
        `机制类 '${m}' 里没有任何一张在强制换机制后判不一致 ⇒ 反向自检对该类空转`,
      ).toBeGreaterThan(0)
    }
    expect(
      dual.length,
      `「两通路同键同列」的 sheet 数超过作业面 ⇒ 断言口径有误（实测集合 ${JSON.stringify(dual)}）`,
    ).toBeLessThan(REAL_TARGETS.length)
  })

  it('P10-G5 真实源码：把机制实现里的列标识符换成另一列 ⇒ 推导列随之改变、判据必判不一致（R2.8）', () => {
    const realCache = new Map<string, string>()
    const readReal = (rel: string) => {
      if (!realCache.has(rel)) realCache.set(rel, fs.readFileSync(path.join(WP_ROOT, rel), 'utf8'))
      return realCache.get(rel) as string
    }
    const seen = new Set<string>()

    fc.assert(
      fc.property(fc.constantFrom(...REAL_TARGETS), (sheet) => {
        const base = REAL_PROBES[sheet]
        const declared = declaredStorageField(CONTRACT, sheet).value as StorageColumn
        const swapTo = otherColumn(declared)
        const rels = [base.files.tab, base.files.adjustment, base.files.formData].filter(
          Boolean,
        ) as string[]
        expect(rels.length, `${sheet}: 探针一个源文件都没读到 ⇒ 扫描面为空`).toBeGreaterThan(0)

        // 把该 sheet 全部源文件里的列标识符整体换成另一列（粗粒度是刻意的：断言只看
        // 「判据是否翻转」，粗粒度不可能造成假通过；细粒度反而要在测试里复刻载荷定位逻辑）
        const overrides: Record<string, string | null> = {}
        let touched = 0
        for (const rel of rels) {
          const raw = readReal(rel)
          const swapped = raw.replace(new RegExp(`\\b${declared}\\b`, 'g'), swapTo)
          if (swapped !== raw) touched++
          overrides[rel] = swapped
        }
        expect(
          touched,
          `${sheet}: 列标识符 '${declared}' 在其源文件里一处都没命中（ANCHOR-MISS）`,
        ).toBeGreaterThan(0)

        const p = probeSheet(base.cycle, { sources: createSourceBundle(overrides) })
        seen.add(String(base.mechanism))
        expect(
          judge(p, declared),
          `${sheet}: 前端把写入列由 '${declared}' 改成 '${swapTo}' 后，判据仍判与清单一致 ⇒ ` +
            'R2.8「写入列改名必须打红」不成立；' + why(p),
        ).toBe(false)
        if (p.column !== null) {
          expect(
            p.column,
            `${sheet}: 改名后推出的列既不是新列也不是 null ⇒ 推导来源不明；${why(p)}`,
          ).toBe(swapTo)
        } else {
          expect(p.reasons.length, `${sheet}: 改名后判不出必须带理由（fail-loud）`).toBeGreaterThan(0)
        }
      }),
      { numRuns: NUM_RUNS_REAL },
    )
    expect([...seen].sort(), '列改名自检未覆盖到两个机制类 ⇒ 某一类上空转').toEqual(
      [MECH_ADJUSTMENT, MECH_FORMDATA].sort(),
    )
  })

  it('P10-G6 真实源码：注释里的「另一列写入调用」+ 行尾 LF/CRLF 互转 ⇒ 推导列与机制不变', () => {
    const realCache = new Map<string, string>()
    const readReal = (rel: string) => {
      if (!realCache.has(rel)) realCache.set(rel, fs.readFileSync(path.join(WP_ROOT, rel), 'utf8'))
      return realCache.get(rel) as string
    }
    const seenInBody = new Set<string>()

    fc.assert(
      fc.property(
        fc.constantFrom(...REAL_TARGETS),
        fc.constantFrom('lf' as const, 'crlf' as const),
        fc.constantFrom('head' as const, 'tail' as const, 'both' as const),
        (sheet, eolMode, where) => {
          const base = REAL_PROBES[sheet]
          const declared = declaredStorageField(CONTRACT, sheet).value as StorageColumn
          const decoyCol = otherColumn(declared)
          const decoyKey = `${sheet}-decoy`
          const rels = [base.files.tab, base.files.adjustment, base.files.formData].filter(
            Boolean,
          ) as string[]
          const eol = eolMode === 'crlf' ? '\r\n' : '\n'
          const overrides: Record<string, string | null> = {}
          let inBodyInjected = 0

          for (const rel of rels) {
            const raw = readReal(rel)
            const lf = raw.replace(/\r\n/g, '\n')
            const isVue = rel.endsWith('.vue')
            const wrap = (s: string) => (isVue ? `<!-- ${s} -->` : `/* ${s} */`)
            const decoyCall =
              `debouncedSave('${decoyKey}', { ${decoyCol}: JSON.stringify(entries.value) }) ` +
              `saveField('${decoyKey}', { ${decoyCol}: '1' })`
            const decoy = wrap(decoyCall)
            // 体内注入：`const itemId = …` 之后（机制① 的推导只看 setField 函数体，
            // 只在文件头尾放诱饵对它是空转）
            const lines = lf.split('\n')
            const withInBody: string[] = []
            for (const l of lines) {
              withInBody.push(l)
              if (/const\s+itemId\s*=/.test(l) && !isVue) {
                withInBody.push(`/* ${decoyCall} */`)
                inBodyInjected++
              }
            }
            const body = withInBody.join(eol)
            const head = where === 'head' || where === 'both' ? decoy + eol : ''
            const tail = where === 'tail' || where === 'both' ? eol + decoy + eol : ''
            overrides[rel] = head + body + tail
          }
          if (base.mechanism === MECH_FORMDATA) {
            expect(
              inBodyInjected,
              `${sheet}: 机制① 的诱饵没能注入 setField 体内（锚点 'const itemId =' 未命中）⇒ ` +
                '本用例对机制① 空转（ANCHOR-MISS）',
            ).toBeGreaterThan(0)
            seenInBody.add(sheet)
          }

          const p = probeSheet(base.cycle, { sources: createSourceBundle(overrides) })
          const label = `${sheet}（行尾=${eolMode} 诱饵位置=${where} 体内注入=${inBodyInjected} 处）`
          expect(p.mechanism, `${label}: 机制判定被注释诱饵改变了`).toBe(base.mechanism)
          expect(
            p.column,
            `${label}: 注释里的「另一列写入调用」污染了推导列 ⇒ stripComments 未生效或推导退化成 grep；` +
              why(p),
          ).toBe(base.column)
          expect(judge(p, declared), `${label}: 判据在语义无关扰动下翻转了`).toBe(true)
          expect(
            [...p.entryKeys, ...p.otherDataKeys].filter((k) => k.includes('-decoy')),
            `${label}: 诱饵键漏进了数据键集`,
          ).toEqual([])
        },
      ),
      { numRuns: NUM_RUNS_REAL },
    )
    expect(
      seenInBody.size,
      '没有任何一张机制① sheet 被体内注入过诱饵 ⇒ 该通道未被覆盖',
    ).toBeGreaterThan(0)
  })
})
