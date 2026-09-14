/**
 * Feature: x3-adjustment-entry-import-export, Property 8: 键提取判据覆盖四形态且排除非数据键
 *
 * **Validates: Requirements 2.3, 2.4, 2.6, 7.4, 7.5**
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 被测对象
 * ─────────────────────────────────────────────────────────────────────────────
 * 任务 1.9 交付的探针 `shared/__tests__/helpers/x3KeyProbe.ts`（`probeSheet` / `probeAllX3`
 * 及其四形态提取器）。本文件**只测它的提取判据**，不重写第二份提取器 —— 任何在本文件里
 * 复刻正则/链式解析的写法都会变成同义反复（判据自证），故一律经 `probeSheet()` 的公开出口。
 *
 * 四形态（design §C6 / R7.4）：
 *   ① 引号字面量              `const ITEM_ID_ENTRIES = 'L2-L2-3-entries'`（或调用点内联）
 *   ② `ITEM_PREFIX` 同文件拼接  `` `${ITEM_PREFIX}-entries` ``
 *   ③ 模板字面量逐字段族        `` `M4-3-entry-${n}-desc` `` / 双前缀 `` `L6-L6-3-entry-${n}-type` ``
 *   ④ 跨文件运行期拼装          tab 的 `setField('3','entries',…)` + `use{X}FormData.ITEM_PREFIX`
 *                              + `setField` 体内拼装表达式（三步链）
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 生成什么（为什么不是同义反复）
 * ─────────────────────────────────────────────────────────────────────────────
 * 生成的是**合成源码片段**（随机 cycle 码 / 行号变量 / 后缀集 / 缩进 / 三种引号 / LF 与 CRLF /
 * 前后噪声 / 写入调用五形态 / 单前缀与双前缀），按四形态的语法骨架拼出真实写入点，再断言
 * 探针提取出的**键集 / 键族 / 后缀集 / 写入列 / 形态标记**逐项等于生成时已知的期望值；同时
 * 注入干扰片段（注释里的键 · `openReviewDialog` 复核键三形态 · `useAdjustmentCentralSync`
 * 的中央同步键 · 悬挂字面量 · 外循环/外 sheet 的同形态键）并断言它们**不进**数据键集。
 * ⇒ 期望值来自「生成器的输入」而非「提取器的输出」，两侧独立。
 *
 * 「同名不同源」反例（design E12 → E17 / `Deviation_Registry` G11）：形态④拼出的真数据键
 * 与 `useAdjustmentCentralSync` 的中央同步键**同名纯属巧合**（真实 `N5-3` 即此例）。按字面量
 * 排除会误剔真数据键 ⇒ 属性覆盖两侧：同名时键必须保留（来源已由三步链证明），而把三步链
 * 任一步改名的变体输入必须判「键不可确证」（R2.6）而不是被那个同名字面量蒙对。
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 真实 sheet 面的来源
 * ─────────────────────────────────────────────────────────────────────────────
 * 本文件**不写任何 X-3 键清单**。真实作业面从 `backend/data/adjustment_ie_contract.json` 装载
 * （选择子 = `observed.rescan_method` 含 `probeAllX3()`，即「该条 observed 由本探针重扫产出」），
 * 并与探针自带的作业面常量交叉锁死。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import fs from 'node:fs'
import path from 'node:path'

import {
  WP_ROOT,
  X3_SHEET_NO,
  X3_TARGET_SHEETS,
  createSourceBundle,
  loadContract,
  probeAllX3,
  probeSheet,
  type KeyFamily,
  type SheetProbe,
  type StorageColumn,
} from './helpers/x3KeyProbe'

// ═══════════════════════════════════════════════════════════════════════════════
// 0. 公共常量与小工具
// ═══════════════════════════════════════════════════════════════════════════════

/** 每条属性的迭代次数（任务要求 ≥100）。 */
const NUM_RUNS = 150
/** 真实源码扰动那条要读盘 + 重扫，单次成本高一些，仍 ≥100。 */
const NUM_RUNS_REAL = 120

const SHEET_NO = X3_SHEET_NO

/** 在**合成源码**里写出真正的插值语法（本文件自身是 TS，故不能直接用模板字面量）。 */
const itp = (expr: string) => '$' + '{' + expr + '}'

/**
 * 合成源码的文件路径约定 —— 与探针内部 `relTab/relAdjustment/relFormData` 同构。
 * 探针未导出这三个私有函数，注入替身必须自己拼；三条路径全部经 `createSourceBundle`
 * 的 `overrides` 覆盖（含显式 `null` = 视为不存在）⇒ 合成用例**零磁盘回退**。
 */
const relTab = (cycle: string) => `${cycle.toLowerCase()}/core/${cycle}TabAdjustment.vue`
const relAdj = (cycle: string) => `composables/use${cycle}Adjustment.ts`
const relFd = (cycle: string) => `composables/use${cycle}FormData.ts`

/** 按随机行尾与缩进渲染源码行。`indent` 只加在非空行上，空行保持空。 */
function render(lines: string[], eol: string, indent: string): string {
  return lines.map((l) => (l.length ? indent + l : l)).join(eol) + eol
}

function uniqSorted(xs: string[]): string[] {
  return [...new Set(xs)].sort()
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. 生成器公共维度
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 合成 cycle 码。须能被形态③骨架的 `[A-Z]{1,2}\d{0,2}` 解析（否则测的不是判据而是生成器），
 * 字母面刻意避开真实循环（L/M/N/K/I），且三条路径全覆盖 ⇒ 不会读到磁盘上的真实文件。
 */
const arbCycle: fc.Arbitrary<string> = fc
  .tuple(
    fc.constantFrom('Q', 'V', 'W', 'X', 'Y', 'Z', 'QA', 'VB', 'WC'),
    fc.constantFrom('', '1', '7', '12', '99'),
  )
  .map(([alpha, num]) => `${alpha}${num}`)

/** 与被测 cycle 必不相同的「外循环」码（同形态但不该被收进本 sheet 的键集）。 */
const FOREIGN_CYCLE = 'ZZ'

const arbEol = fc.constantFrom('\n', '\r\n')
const arbIndent = fc.constantFrom('', '  ', '    ', '\t')
/** 三种引号（反引号取无插值形态）。 */
const arbQuote = fc.constantFrom("'", '"', '`')
const arbColumn: fc.Arbitrary<StorageColumn> = fc.constantFrom('remark', 'conclusion')
/** 行号插值表达式：标识符与算式两类都要能解析。 */
const arbIdxVar = fc.constantFrom('n', 'i', 'idx', 'rowIndex', 'i + 1')
/** 逐字段族后缀池（含实测存在的 camelCase：`ociBlock`）。 */
const SUFFIX_POOL = [
  'type',
  'desc',
  'category',
  'report',
  'account',
  'note',
  'debit',
  'credit',
  'ref',
  'remark',
  'ociBlock',
]

// ═══════════════════════════════════════════════════════════════════════════════
// 2. 机制②（形态 ①②③）合成用例
// ═══════════════════════════════════════════════════════════════════════════════

type Form123 = 'L' | 'P' | 'F'
/** 形态组合：非空子集，覆盖「同文件多形态并存」。 */
const FORM_PICKS: Form123[][] = [['L'], ['P'], ['F'], ['L', 'P'], ['L', 'F'], ['P', 'F'], ['L', 'P', 'F']]

type WriteKind = 'saveBatchArray' | 'saveBatchVar' | 'debouncedSave' | 'saveField' | 'emitSave' | 'allResponsesSet'

interface Mech2Case {
  cycle: string
  eol: string
  indent: string
  quote: string
  column: StorageColumn
  picks: Form123[]
  /** 写入点宿主文件（形态②的标记只在 `use{X}Adjustment.ts` 内被识别 ⇒ 选 P 时强制该宿主）。 */
  siteHostRaw: 'adjustment' | 'tab'
  doublePrefix: boolean
  literalViaConst: boolean
  suffixes: string[]
  hasData: boolean
  idxVar: string
  writeKind: WriteKind
  includeReviewCall: boolean
  includeReviewOptional: boolean
  includeReviewTrigger: boolean
  includeCentralSync: boolean
  includeNoteKey: boolean
  includeForeignCycleSite: boolean
  includeForeignSheetSite: boolean
  includeCommentDecoy: boolean
  includeDangling: boolean
  includeReadBack: boolean
}

const arbMech2Case: fc.Arbitrary<Mech2Case> = fc.record({
  cycle: arbCycle,
  eol: arbEol,
  indent: arbIndent,
  quote: arbQuote,
  column: arbColumn,
  picks: fc.constantFrom(...FORM_PICKS),
  siteHostRaw: fc.constantFrom('adjustment' as const, 'tab' as const),
  doublePrefix: fc.boolean(),
  literalViaConst: fc.boolean(),
  suffixes: fc.uniqueArray(fc.constantFrom(...SUFFIX_POOL), { minLength: 1, maxLength: 4 }),
  hasData: fc.boolean(),
  idxVar: arbIdxVar,
  writeKind: fc.constantFrom(
    'saveBatchArray' as const,
    'saveBatchVar' as const,
    'debouncedSave' as const,
    'saveField' as const,
    'emitSave' as const,
    'allResponsesSet' as const,
  ),
  includeReviewCall: fc.boolean(),
  includeReviewOptional: fc.boolean(),
  includeReviewTrigger: fc.boolean(),
  includeCentralSync: fc.boolean(),
  includeNoteKey: fc.boolean(),
  includeForeignCycleSite: fc.boolean(),
  includeForeignSheetSite: fc.boolean(),
  includeCommentDecoy: fc.boolean(),
  includeDangling: fc.boolean(),
  includeReadBack: fc.boolean(),
})

interface Mech2Expect {
  cycle: string
  sheet: string
  /** 期望的 entries 数据键集（族键已归约） */
  entryKeys: string[]
  otherDataKeys: string[]
  keyFamily: KeyFamily
  perFieldSuffixes: string[]
  column: StorageColumn
  forms: string[]
  reviewKeys: string[]
  centralSyncKeys: string[]
  /** 必须**不出现**在任何数据键集里的干扰键 */
  mustNotBeData: string[]
  sources: Record<string, string | null>
}

/** 按用例拼出合成源文件组，并同步算出期望值（期望取自生成器输入，不看提取器输出）。 */
function buildMech2(c: Mech2Case): Mech2Expect {
  const q = c.quote
  const lit = (s: string) => `${q}${s}${q}`
  const cycle = c.cycle
  const sheet = `${cycle}-${SHEET_NO}`
  const col = c.column
  const other: StorageColumn = col === 'remark' ? 'conclusion' : 'remark'

  const famPrefix = c.doublePrefix ? `${cycle}-${cycle}-${SHEET_NO}` : `${cycle}-${SHEET_NO}`
  const familyKey = `${famPrefix}-entry-*`
  const literalKey = `${sheet}-entries`
  const prefixConst = `${sheet}-adj`
  const prefixKey = `${prefixConst}-entries`
  const noteKey = `${sheet}-adjustmentNote`
  const reviewKeyA = `${sheet}-adjustment`
  const reviewKeyB = `${sheet}-调整分录`
  const reviewKeyC = `${sheet}-review-trigger`
  const centralKey = `${sheet}-central`
  const danglingKey = `${sheet}-entries-label`
  const commentKey = `${sheet}-entries-in-comment`

  const wantLiteral = c.picks.includes('L')
  const wantPrefix = c.picks.includes('P')
  const wantFamily = c.picks.includes('F')
  // 形态②的标记只在 `use{X}Adjustment.ts` 内被识别 ⇒ 选 P 时写入点必须落在该文件
  const siteHost: 'adjustment' | 'tab' = wantPrefix ? 'adjustment' : c.siteHostRaw

  const famSuffixes = wantFamily ? c.suffixes : []
  const famAll = wantFamily ? (c.hasData ? [...famSuffixes, 'data'] : famSuffixes) : []

  // ── 写入点渲染 ────────────────────────────────────────────────────────────
  const famTpl = (suffix: string, prefix = famPrefix) =>
    '`' + prefix + '-entry-' + itp(c.idxVar) + '-' + suffix + '`'
  const payload = (column: string, expr: string) => `{ ${column}: ${expr} }`

  const writes: string[] = []
  const emitFamily = (suffix: string, prefix = famPrefix, column = col) => {
    const keyExpr = famTpl(suffix, prefix)
    const body = suffix === 'data' ? `JSON.stringify(entries.value[${c.idxVar}])` : `entry.${suffix} || null`
    switch (c.writeKind) {
      case 'saveBatchArray':
        writes.push(`await saveBatch([{ itemId: ${keyExpr}, data: ${payload(column, body)} }])`)
        break
      case 'saveBatchVar':
        writes.push(`const items_${suffix} = [{ itemId: ${keyExpr}, data: ${payload(column, body)} }]`)
        writes.push(`await saveBatch(items_${suffix})`)
        break
      case 'debouncedSave':
        writes.push(`debouncedSave(${keyExpr}, ${payload(column, body)})`)
        break
      case 'saveField':
        writes.push(`await saveField(${keyExpr}, ${payload(column, body)})`)
        break
      case 'emitSave':
        writes.push(`emit('save', ${keyExpr}, ${payload(column, body)})`)
        break
      case 'allResponsesSet':
        writes.push(`allResponses.value.set(${keyExpr}, ${payload(column, body)})`)
        break
    }
  }
  const emitSingle = (keyExpr: string) => {
    const body = 'JSON.stringify(entries.value)'
    switch (c.writeKind) {
      case 'saveBatchArray':
      case 'saveBatchVar':
        writes.push(`await saveBatch([{ itemId: ${keyExpr}, data: ${payload(col, body)} }])`)
        break
      case 'debouncedSave':
        writes.push(`debouncedSave(${keyExpr}, ${payload(col, body)})`)
        break
      case 'saveField':
        writes.push(`await saveField(${keyExpr}, ${payload(col, body)})`)
        break
      case 'emitSave':
        writes.push(`emit('save', ${keyExpr}, ${payload(col, body)})`)
        break
      case 'allResponsesSet':
        writes.push(`allResponses.value.set(${keyExpr}, ${payload(col, body)})`)
        break
    }
  }

  if (wantLiteral) emitSingle(c.literalViaConst ? 'ITEM_ID_ENTRIES' : lit(literalKey))
  if (wantPrefix) emitSingle('`' + itp('ITEM_PREFIX') + '-entries`')
  for (const s of famAll) emitFamily(s)

  // 干扰写入点：外循环 / 外 sheet 的同形态键（刻意用**另一个列**，若归属判据失效则
  // 写入列会解析出 2 个 ⇒ 探针判「无法唯一确定写入列」⇒ 断言必红）
  if (c.includeForeignCycleSite) emitFamily('desc', `${FOREIGN_CYCLE}-${SHEET_NO}`, other)
  if (c.includeForeignSheetSite) emitFamily('desc', `${cycle}-4`, other)
  // 表级独立键（非 entries：载荷不提 entries）⇒ 应落 otherDataKeys 而非 entryKeys
  if (c.includeNoteKey) writes.push(`debouncedSave(${lit(noteKey)}, ${payload(col, 'note.value')})`)

  const decoyLines = c.includeCommentDecoy
    ? [
        `// debouncedSave(${lit(commentKey)}, ${payload(col, 'JSON.stringify(entries.value)')})`,
        `/* debouncedSave(${famTpl('desc')}, ${payload(col, 'JSON.stringify(entries.value)')}) */`,
        `/* openReviewDialog(${lit(`${sheet}-review-in-comment`)}) */`,
      ]
    : []
  const danglingLines = c.includeDangling ? [`const LABEL_TEXT = ${lit(danglingKey)}`] : []

  // 键常量必须与引用它的写入点**同文件** —— 形态①②是「同文件」形态（跨文件是形态④的事），
  // 探针的 `resolveKeyExpr` 也只在同一文件里解析标识符。放错文件测的就不是判据而是生成器。
  const keyConstDecls: string[] = [
    ...(wantPrefix ? [`const ITEM_PREFIX = ${lit(prefixConst)}`] : []),
    ...(wantLiteral && c.literalViaConst ? [`const ITEM_ID_ENTRIES = ${lit(literalKey)}`] : []),
  ]

  // ── use{X}Adjustment.ts ───────────────────────────────────────────────────
  const adjLines: string[] = [
    `import { ref } from 'vue'`,
    ``,
    ...(siteHost === 'adjustment' ? keyConstDecls : []),
    ``,
    `export function use${cycle}Adjustment(formData: any) {`,
    `  const { debouncedSave, saveBatch, saveField, allResponses } = formData`,
    `  const entries = ref<any[]>([])`,
    `  const note = ref('')`,
    `  const emit = (..._a: any[]) => void 0`,
    ...decoyLines.map((l) => `  ${l}`),
    ...danglingLines.map((l) => `  ${l}`),
    `  async function saveAndPublish() {`,
    ...(siteHost === 'adjustment' ? writes.map((w) => `    ${w}`) : [`    void entries`]),
    `  }`,
    `  return { entries, note, saveAndPublish }`,
    `}`,
  ]

  // ── {X}TabAdjustment.vue ──────────────────────────────────────────────────
  const readBackSuffix = wantFamily ? (c.hasData ? 'data' : famSuffixes[0]) : null
  const tabLines: string[] = [
    `<template>`,
    `  <div class="${cycle.toLowerCase()}-tab-adjustment">`,
    ...(c.includeReviewTrigger ? [`    <GtReviewTrigger section-id="${reviewKeyC}" />`] : []),
    ...(c.includeCommentDecoy ? [`    <!-- debouncedSave(${lit(commentKey)}) -->`] : []),
    `    <el-button @click="saveAll">保存</el-button>`,
    `  </div>`,
    `</template>`,
    ``,
    `<script setup lang="ts">`,
    `import { ref, onMounted } from 'vue'`,
    ...(siteHost === 'tab'
      ? []
      : [`import { use${cycle}Adjustment } from '@/components/workpaper/composables/use${cycle}Adjustment'`]),
    ...(c.includeCentralSync
      ? [`import { useAdjustmentCentralSync } from '@/components/workpaper/composables/useAdjustmentCentralSync'`]
      : []),
    `const props = defineProps<{ wpId: number; allResponses?: Map<string, any> }>()`,
    `const entries = ref<any[]>([])`,
    `const note = ref('')`,
    `const emit = (..._a: any[]) => void 0`,
    `const { debouncedSave, saveBatch, saveField, allResponses } = (props as any).formData ?? {}`,
    ...(siteHost === 'tab' ? keyConstDecls : []),
    ...(c.includeCentralSync
      ? [`useAdjustmentCentralSync({ wpCode: '${cycle}', itemId: ${lit(centralKey)} })`]
      : []),
    ...(c.includeReviewCall ? [`function review() { openReviewDialog(${lit(reviewKeyA)}) }`] : []),
    ...(c.includeReviewOptional ? [`function review2() { openReviewDialog?.(${lit(reviewKeyB)}) }`] : []),
    ...decoyLines,
    ...danglingLines,
    ...(c.includeReadBack && readBackSuffix
      ? [
          `function restoreEntries() {`,
          `  const resp = props.allResponses?.get(${famTpl(readBackSuffix)})`,
          `  if (resp) entries.value.push(JSON.parse(resp.${col}))`,
          `}`,
        ]
      : []),
    `async function saveAll() {`,
    ...(siteHost === 'tab' ? writes.map((w) => `  ${w}`) : [`  void entries`]),
    `}`,
    `onMounted(() => { void saveAll })`,
    `</script>`,
  ]

  // ── 期望值（全部由生成器输入推出） ────────────────────────────────────────
  const entryKeys: string[] = []
  if (wantLiteral) entryKeys.push(literalKey)
  if (wantPrefix) entryKeys.push(prefixKey)
  if (wantFamily) entryKeys.push(familyKey)

  const forms: string[] = []
  if (wantLiteral || wantPrefix) forms.push('quoted_literal')
  if (wantPrefix) forms.push('item_prefix_concat')
  if (wantFamily) forms.push('template_per_field')

  const reviewKeys: string[] = []
  if (c.includeReviewCall) reviewKeys.push(reviewKeyA)
  if (c.includeReviewOptional) reviewKeys.push(reviewKeyB)
  if (c.includeReviewTrigger) reviewKeys.push(reviewKeyC)

  const mustNotBeData = [
    ...reviewKeys,
    ...(c.includeCentralSync ? [centralKey] : []),
    ...(c.includeCommentDecoy ? [commentKey, `${sheet}-review-in-comment`] : []),
    ...(c.includeDangling ? [danglingKey] : []),
    ...(c.includeForeignCycleSite ? [`${FOREIGN_CYCLE}-${SHEET_NO}-entry-*`] : []),
    ...(c.includeForeignSheetSite ? [`${cycle}-4-entry-*`] : []),
  ]

  return {
    cycle,
    sheet,
    entryKeys: uniqSorted(entryKeys),
    otherDataKeys: c.includeNoteKey ? [noteKey] : [],
    keyFamily: wantFamily ? (c.hasData ? 'per_field_plus_data' : 'per_field') : 'single_json',
    perFieldSuffixes: uniqSorted(famSuffixes),
    column: col,
    forms: uniqSorted(forms),
    reviewKeys: uniqSorted(reviewKeys),
    centralSyncKeys: c.includeCentralSync ? [centralKey] : [],
    mustNotBeData: uniqSorted(mustNotBeData),
    sources: {
      [relTab(cycle)]: render(tabLines, c.eol, c.indent),
      [relAdj(cycle)]: siteHost === 'tab' && !wantPrefix ? null : render(adjLines, c.eol, c.indent),
      [relFd(cycle)]: null,
    },
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 3. 机制①（形态④ 三步链）合成用例
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * `setField` 的声明形态。
 *
 * 前三种是平台实测存在的写法（105 个 `use*FormData.ts` 全部落在这三种里）。
 * `functionTypedObj`（返回类型注解写成对象字面量 `: Promise<{ ok: boolean }>`）**当前零实例**
 * （已实测 105/105 无一处），单独由 P8-H 承载 —— 它揭示了探针 `extractFunctionBody` 的一处
 * 潜在健壮性缺口：该函数只「跳参数列表」，而对象字面量返回注解里的 `{` 出现在参数列表**之后**，
 * 于是 `indexOf('{', pEnd)` 会落在注解上。后果是 **fail-loud 判「键不可确证」**（不是产出错键），
 * 故 P8-H 断言的是「要么拼对、要么明确判不可确证」这条安全性质 —— 该性质今天成立、缺口被修好后
 * 也成立，不把当前缺陷锁成基线。
 */
type SetFieldStyle = 'function' | 'arrow' | 'method' | 'functionTypedObj'
const REAL_SETFIELD_STYLES: SetFieldStyle[] = ['function', 'arrow', 'method']
const ALL_SETFIELD_STYLES: SetFieldStyle[] = [...REAL_SETFIELD_STYLES, 'functionTypedObj']
type AssembleStyle = 'dash' | 'underscore'

interface Mech4Case {
  cycle: string
  eol: string
  indent: string
  quote: string
  column: StorageColumn
  field: string
  setFieldStyle: SetFieldStyle
  assemble: AssembleStyle
  /** 与真数据键**同名**的中央同步键（N5-3 那个巧合） */
  coincidentalCentralSync: boolean
  /** N1-3 那种「同键同列的直呼形态」并存 */
  directCall: boolean
  includeReviewCall: boolean
  includeCommentDecoy: boolean
  includeGetFieldPair: boolean
}

function arbMech4CaseWith(styles: SetFieldStyle[]): fc.Arbitrary<Mech4Case> {
  return fc
  .record({
    cycle: arbCycle,
    eol: arbEol,
    indent: arbIndent,
    quote: arbQuote,
    column: arbColumn,
    field: fc.constantFrom('entries', 'adj-entries', 'entry-rows'),
    setFieldStyle: fc.constantFrom(...styles),
    assemble: fc.constantFrom('dash' as const, 'underscore' as const),
    coincidentalCentralSync: fc.boolean(),
    directCall: fc.boolean(),
    includeReviewCall: fc.boolean(),
    includeCommentDecoy: fc.boolean(),
    includeGetFieldPair: fc.boolean(),
  })
  // 直呼形态与「同名中央同步键」并存时，直呼那条键会先被排除集剔掉 ⇒ 两者不同时生成，
  // 使每个用例的期望形态集唯一可判（两种子形态各自都有覆盖）
  .map((c) => (c.coincidentalCentralSync ? { ...c, directCall: false } : c))
}

/** 形态④主属性用平台实测存在的三种声明形态。 */
const arbMech4Case: fc.Arbitrary<Mech4Case> = arbMech4CaseWith(REAL_SETFIELD_STYLES)

interface Mech4Expect {
  cycle: string
  sheet: string
  /** 三步链拼出的真数据键 */
  key: string
  column: StorageColumn
  forms: string[]
  centralSyncKeys: string[]
  reviewKeys: string[]
  sources: Record<string, string | null>
  tabRel: string
  fdRel: string
}

function buildMech4(c: Mech4Case): Mech4Expect {
  const q = c.quote
  const lit = (s: string) => `${q}${s}${q}`
  const cycle = c.cycle
  const sheet = `${cycle}-${SHEET_NO}`
  const prefix = `${cycle}-`
  const sep = c.assemble === 'dash' ? '-' : '_'
  const key = `${prefix}${SHEET_NO}${sep}${c.field}`
  const reviewKey = `${sheet}-adjustment`
  const commentKey = `${sheet}-entries-in-comment`

  const assembleTpl = '`' + itp('ITEM_PREFIX') + itp('sheet') + sep + itp('field') + '`'
  const payloadExpr = c.column === 'conclusion' ? '{ conclusion }' : '{ remark }'

  const bodyLines = (ind: string) => [
    `${ind}const itemId = ${assembleTpl}`,
    `${ind}const ${c.column} = typeof value === 'string' ? value : JSON.stringify(value)`,
    `${ind}await saveField(itemId, ${payloadExpr})`,
  ]
  let setFieldBlock: string[]
  let exportsLine: string
  switch (c.setFieldStyle) {
    case 'arrow':
      setFieldBlock = [
        `  const setField = async (sheet: string, field: string, value: any): Promise<void> => {`,
        ...bodyLines('    '),
        `  }`,
      ]
      exportsLine = `  return { allResponses, setField, getField, saveField, loadData }`
      break
    case 'method':
      // 方法简写形态只在对象字面量里合法 ⇒ 按真实可编译写法渲染（不写成裸语句）
      setFieldBlock = [
        `  const api = {`,
        `    async setField(sheet: string, field: string, value: any) {`,
        ...bodyLines('      '),
        `    },`,
        `  }`,
      ]
      exportsLine = `  return { allResponses, ...api, getField, saveField, loadData }`
      break
    case 'functionTypedObj':
      // 返回类型注解写成对象字面量 —— 参数列表**之后**还有一个 `{`（见 SetFieldStyle 注释）
      setFieldBlock = [
        `  async function setField(sheet: string, field: string, value: any): Promise<{ ok: boolean }> {`,
        ...bodyLines('    '),
        `    return { ok: true }`,
        `  }`,
      ]
      exportsLine = `  return { allResponses, setField, getField, saveField, loadData }`
      break
    default:
      setFieldBlock = [
        `  async function setField(sheet: string, field: string, value: any): Promise<void> {`,
        ...bodyLines('    '),
        `  }`,
      ]
      exportsLine = `  return { allResponses, setField, getField, saveField, loadData }`
      break
  }

  const fdLines: string[] = [
    `import { ref } from 'vue'`,
    ``,
    `const ITEM_PREFIX = ${lit(prefix)}`,
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
    `import { useAdjustmentCentralSync } from '@/components/workpaper/composables/useAdjustmentCentralSync'`,
    `const entries = ref<any[]>([])`,
    `const formData = use${cycle}FormData()`,
    // 同名巧合：字面量属中央同步键，与三步链拼出的真数据键逐字相同（design E12 → E17 / G11）
    ...(c.coincidentalCentralSync
      ? [`useAdjustmentCentralSync({ wpCode: '${cycle}', itemId: ${lit(key)} })`]
      : [`useAdjustmentCentralSync({ wpCode: '${cycle}', itemId: ${lit(`${sheet}-central`)} })`]),
    ...(c.includeReviewCall ? [`function review() { openReviewDialog?.(${lit(reviewKey)}) }`] : []),
    ...(c.includeCommentDecoy
      ? [`// await formData.debouncedSave(${lit(commentKey)}, { ${c.column}: '1' })`]
      : []),
    `async function saveEntries() {`,
    `  await formData.setField(${lit(SHEET_NO)}, ${lit(c.field)}, entries.value)`,
    ...(c.directCall
      ? [`  await formData.debouncedSave(${lit(key)}, { ${c.column}: JSON.stringify(entries.value) })`]
      : []),
    `}`,
    `onMounted(async () => {`,
    `  await formData.loadData()`,
    ...(c.includeGetFieldPair
      ? [
          `  const raw = formData.getField(${lit(SHEET_NO)}, ${lit(c.field)})`,
          `  if (Array.isArray(raw)) entries.value = raw`,
        ]
      : [`  void saveEntries`]),
    `})`,
    `</script>`,
  ]

  const forms = ['cross_file_runtime']
  if (c.directCall) forms.push('quoted_literal')

  return {
    cycle,
    sheet,
    key,
    column: c.column,
    forms: uniqSorted(forms),
    centralSyncKeys: [c.coincidentalCentralSync ? key : `${sheet}-central`],
    reviewKeys: c.includeReviewCall ? [reviewKey] : [],
    sources: {
      [relTab(cycle)]: render(tabLines, c.eol, c.indent),
      [relAdj(cycle)]: null,
      [relFd(cycle)]: render(fdLines, c.eol, c.indent),
    },
    tabRel: relTab(cycle),
    fdRel: relFd(cycle),
  }
}

function probeSynthetic(cycle: string, sources: Record<string, string | null>): SheetProbe {
  return probeSheet(cycle, { sources: createSourceBundle(sources) })
}

function why(p: SheetProbe): string {
  return `reasons=[${p.reasons.join(' / ')}] trail=[${p.trail.join(' | ')}]`
}

// ═══════════════════════════════════════════════════════════════════════════════
// 4. 真实作业面（从契约清单装载，本文件不写键清单）
// ═══════════════════════════════════════════════════════════════════════════════

const CONTRACT = loadContract()

/** 选择子：该条 `observed` 由本探针 `probeAllX3()` 重扫产出 ⇒ 即探针作业面。 */
const REAL_TARGETS: string[] = Object.entries(CONTRACT.sheets)
  .filter(([, e]) => String(((e as any)?.observed ?? {}).rescan_method ?? '').includes('probeAllX3'))
  .map(([sheet]) => sheet)
  .sort()

const REAL_PROBES: Record<string, SheetProbe> = probeAllX3()

// ═══════════════════════════════════════════════════════════════════════════════

describe('Property 8 — 键提取判据覆盖四形态且排除非数据键（x3 spec 任务 2.2）', () => {
  // ─────────────────────────────────────────────────────────────────────────────
  // 反空转前置：作业面必须非空且两处口径一致（否则后面所有真实源码断言恒真）
  // ─────────────────────────────────────────────────────────────────────────────
  it('前置 — 真实作业面从契约清单装载且与探针作业面逐条相等（反空转）', () => {
    expect(
      REAL_TARGETS.length,
      '契约清单里没有任何条目的 observed.rescan_method 含 probeAllX3() ⇒ 作业面为空、' +
        '真实源码那几条属性会恒真（空转）。清单真源：backend/data/adjustment_ie_contract.json',
    ).toBeGreaterThan(0)
    expect(
      REAL_TARGETS,
      '清单派生的作业面与探针自带的作业面常量分叉 ⇒ 两处口径不一致，必须先收口',
    ).toEqual([...X3_TARGET_SHEETS].sort())
    expect(Object.keys(REAL_PROBES).sort()).toEqual(REAL_TARGETS)
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P8-A：形态 ①②③（机制②）—— 合成源码全部被识别，且键集/键族/后缀/列逐项等于期望
  // ─────────────────────────────────────────────────────────────────────────────
  it('P8-A 形态①②③ 在任意合成写入点上均被识别，键集与键族逐项等于生成期望', () => {
    const seen = {
      picks: new Set<string>(),
      writeKind: new Set<string>(),
      quote: new Set<string>(),
      eol: new Set<string>(),
      doublePrefix: new Set<string>(),
      siteHost: new Set<string>(),
      family: new Set<string>(),
      column: new Set<string>(),
    }
    fc.assert(
      fc.property(arbMech2Case, (c) => {
        const e = buildMech2(c)
        seen.picks.add(c.picks.join('+'))
        seen.writeKind.add(c.writeKind)
        seen.quote.add(c.quote)
        seen.eol.add(c.eol === '\n' ? 'LF' : 'CRLF')
        seen.doublePrefix.add(String(c.doublePrefix))
        seen.siteHost.add(e.sources[relAdj(c.cycle)] === null ? 'tab-only' : 'adjustment')
        seen.family.add(e.keyFamily)
        seen.column.add(c.column)
        const p = probeSynthetic(e.cycle, e.sources)

        expect(p.confirmed, `${e.sheet}: 合成源码里有真实写入点却判「键不可确证」；${why(p)}`).toBe(true)
        expect(p.pendingManual).toBe(false)
        expect(p.trail.length, `${e.sheet}: 无任何依据链留痕 ⇒ 探针没真解析到写入点`).toBeGreaterThan(0)
        expect(p.mechanism).toBe('adjustment_savebatch')
        expect(
          [...p.entryKeys].sort(),
          `${e.sheet}: 键集不等于期望（形态=${c.picks.join('+')} 写法=${c.writeKind} ` +
            `双前缀=${c.doublePrefix} 行尾=${c.eol === '\n' ? 'LF' : 'CRLF'}）；${why(p)}`,
        ).toEqual(e.entryKeys)
        expect(p.keyFamily, `${e.sheet}: 键族判定不等于期望`).toBe(e.keyFamily)
        expect([...p.perFieldSuffixes].sort(), `${e.sheet}: 逐字段族后缀集不等于期望`).toEqual(
          e.perFieldSuffixes,
        )
        expect(
          p.column,
          `${e.sheet}: 写入列实测值 '${p.column}' ≠ 载荷对象字面量里的列 '${e.column}'`,
        ).toBe(e.column)
        for (const f of e.forms) {
          expect(p.forms, `${e.sheet}: 形态标记缺 '${f}'（实测 ${p.forms.join(',')}）`).toContain(f)
        }
        expect([...p.otherDataKeys].sort(), `${e.sheet}: 表级独立键归属不等于期望`).toEqual(
          e.otherDataKeys,
        )
      }),
      { numRuns: NUM_RUNS },
    )
    // 生成器覆盖面自证（否则「覆盖四形态」只是一句话）：各维度取值必须都被真的跑到
    expect([...seen.picks].sort(), '形态组合未全覆盖').toEqual(
      FORM_PICKS.map((p) => p.join('+')).sort(),
    )
    expect([...seen.writeKind].sort(), '写入调用五形态未全覆盖').toEqual(
      ['allResponsesSet', 'debouncedSave', 'emitSave', 'saveBatchArray', 'saveBatchVar', 'saveField'],
    )
    expect([...seen.quote].sort(), '三种引号未全覆盖').toEqual(['"', '`', "'"].sort())
    expect([...seen.eol].sort(), 'LF/CRLF 未全覆盖').toEqual(['CRLF', 'LF'])
    expect([...seen.doublePrefix].sort(), '单前缀/双前缀未全覆盖').toEqual(['false', 'true'])
    expect([...seen.siteHost].sort(), '写入点宿主（tab / composable）未全覆盖').toEqual([
      'adjustment',
      'tab-only',
    ])
    expect([...seen.family].sort(), '三种键族未全覆盖').toEqual([
      'per_field',
      'per_field_plus_data',
      'single_json',
    ])
    expect([...seen.column].sort(), '两个存储列未全覆盖').toEqual(['conclusion', 'remark'])
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P8-B：干扰片段一律不进数据键集（R2.4 + 注释剥离 + 归属过滤）
  // ─────────────────────────────────────────────────────────────────────────────
  it('P8-B 复核键/中央同步键/注释内键/悬挂字面量/外循环外 sheet 键一律不进数据键集', () => {
    fc.assert(
      fc.property(arbMech2Case, (c) => {
        const e = buildMech2(c)
        const p = probeSynthetic(e.cycle, e.sources)
        const dataKeys = new Set([...p.entryKeys, ...p.otherDataKeys])

        for (const k of e.mustNotBeData) {
          expect(
            dataKeys.has(k),
            `${e.sheet}: 非数据键 '${k}' 被收进了数据键集（entryKeys=${JSON.stringify(p.entryKeys)} ` +
              `otherDataKeys=${JSON.stringify(p.otherDataKeys)}）`,
          ).toBe(false)
        }
        // 排除集必须**认出**注入的非数据键（否则「排除」这件事在本用例上整条空转）
        for (const k of e.reviewKeys) {
          expect(p.reviewKeys, `${e.sheet}: 复核键 '${k}' 没被识别 ⇒ R2.4 在本用例上空转`).toContain(k)
        }
        for (const k of e.centralSyncKeys) {
          expect(p.centralSyncKeys, `${e.sheet}: 中央同步键 '${k}' 没被识别`).toContain(k)
        }
        // 注释里的键既不进数据键集，也不进任何排除集（应在词法阶段被剥掉）
        if (c.includeCommentDecoy) {
          const all = [...p.entryKeys, ...p.otherDataKeys, ...p.reviewKeys, ...p.centralSyncKeys]
          expect(
            all.filter((k) => k.includes('in-comment')),
            `${e.sheet}: 注释里的键漏进了某个集合 ⇒ stripComments 未生效`,
          ).toEqual([])
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P8-C：形态④ 三步链 —— 含「同名不同源」巧合时键仍被确证（G11）
  // ─────────────────────────────────────────────────────────────────────────────
  it('P8-C 形态④三步链拼出的键被确证；与中央同步键同名时不得被误剔（G11）', () => {
    const seen = {
      style: new Set<string>(),
      assemble: new Set<string>(),
      coincidence: new Set<string>(),
      direct: new Set<string>(),
      eol: new Set<string>(),
      column: new Set<string>(),
    }
    fc.assert(
      fc.property(arbMech4Case, (c) => {
        const e = buildMech4(c)
        seen.style.add(c.setFieldStyle)
        seen.assemble.add(c.assemble)
        seen.coincidence.add(String(c.coincidentalCentralSync))
        seen.direct.add(String(c.directCall))
        seen.eol.add(c.eol === '\n' ? 'LF' : 'CRLF')
        seen.column.add(c.column)
        const p = probeSynthetic(e.cycle, e.sources)

        expect(p.confirmed, `${e.sheet}: 三步链齐全却判「键不可确证」；${why(p)}`).toBe(true)
        expect(p.mechanism).toBe('formdata_setfield')
        expect(p.keyFamily).toBe('single_json')
        expect(
          p.entryKeys,
          `${e.sheet}: 三步链应拼出 '${e.key}'（ITEM_PREFIX + sheet 实参 + field 实参，` +
            `setField 声明形态=${c.setFieldStyle}）；${why(p)}`,
        ).toEqual([e.key])
        expect(
          p.column,
          `${e.sheet}: 写入列应取 setField 体内 saveField 载荷的列 '${e.column}'`,
        ).toBe(e.column)
        for (const f of e.forms) expect(p.forms).toContain(f)
        expect(p.trail.join(' | ')).toContain('ITEM_PREFIX')

        if (c.coincidentalCentralSync) {
          // 同名不同源：字面量属中央同步键，真数据键由三步链拼出 ⇒ 两者都在，且键不得被剔
          expect(p.centralSyncKeys, `${e.sheet}: 同名字面量应被识别为中央同步键`).toContain(e.key)
          expect(
            p.entryKeys,
            `${e.sheet}: 真数据键与中央同步键同名，但来源已由三步链证明 ⇒ 不得按字面量剔除` +
              '（design E12 → E17 / Deviation_Registry G11）',
          ).toContain(e.key)
        } else {
          expect(p.centralSyncKeys).toEqual(e.centralSyncKeys)
          expect(p.entryKeys.some((k) => p.centralSyncKeys.includes(k))).toBe(false)
        }
        for (const k of e.reviewKeys) {
          expect(p.reviewKeys).toContain(k)
          expect(p.entryKeys).not.toContain(k)
        }
      }),
      { numRuns: NUM_RUNS },
    )
    expect([...seen.style].sort(), 'setField 三种实测声明形态未全覆盖').toEqual(
      [...REAL_SETFIELD_STYLES].sort(),
    )
    expect([...seen.assemble].sort(), '键拼装分隔符两形态未全覆盖').toEqual(['dash', 'underscore'])
    expect([...seen.coincidence].sort(), '「同名不同源」反例未被覆盖（G11）').toEqual([
      'false',
      'true',
    ])
    expect([...seen.direct].sort(), 'N1-3 那种同键同列直呼形态未被覆盖').toEqual(['false', 'true'])
    expect([...seen.eol].sort()).toEqual(['CRLF', 'LF'])
    expect([...seen.column].sort()).toEqual(['conclusion', 'remark'])
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P8-D：三步链任一步被改名 ⇒ 判「键不可确证」（R2.6），且不被同名字面量蒙对
  // ─────────────────────────────────────────────────────────────────────────────
  type ChainBreak = 'renamePrefixIdent' | 'changePrefixValue' | 'changeSheetArg' | 'dropImport' | 'renameSetField' | 'dropPayloadColumn'
  const arbChainBreak: fc.Arbitrary<ChainBreak> = fc.constantFrom(
    'renamePrefixIdent',
    'changePrefixValue',
    'changeSheetArg',
    'dropImport',
    'renameSetField',
    'dropPayloadColumn',
  )

  it('P8-D 三步链任一步改名/断链 ⇒ 判键不可确证（同名字面量仍在，不得蒙对）', () => {
    const seenBreaks = new Set<string>()
    fc.assert(
      fc.property(
        arbMech4Case.map((c) => ({ ...c, coincidentalCentralSync: true, directCall: false })),
        arbChainBreak,
        (c, brk) => {
          seenBreaks.add(brk)
          const e = buildMech4(c)
          const base = probeSynthetic(e.cycle, e.sources)
          // 基线必须先绿（否则「变红」不可归因 —— 可能本就没确证过）
          expect(base.entryKeys, `${e.sheet}: 变异前基线应确证；${why(base)}`).toEqual([e.key])

          const tab = e.sources[e.tabRel] as string
          const fd = e.sources[e.fdRel] as string
          const mutated: Record<string, string | null> = { ...e.sources }
          switch (brk) {
            case 'renamePrefixIdent':
              mutated[e.fdRel] = fd.replace(/\bITEM_PREFIX\b/g, 'ITEM_PREFIX_RENAMED')
              break
            case 'changePrefixValue':
              mutated[e.fdRel] = fd.replace(`${e.cycle}-`, `${e.cycle}X-`)
              break
            case 'changeSheetArg':
              mutated[e.tabRel] = tab.replace(
                new RegExp(`setField\\((['"\`])${SHEET_NO}\\1`),
                (m) => m.replace(SHEET_NO, '9'),
              )
              break
            case 'dropImport':
              mutated[e.tabRel] = tab
                .split(/\r?\n/)
                .filter((l) => !new RegExp(`import\\s*\\{[^}]*use${e.cycle}FormData`).test(l))
                .join('\n')
              break
            case 'renameSetField':
              mutated[e.fdRel] = fd.replace(/\bsetField\b/g, 'setFieldRenamed')
              break
            case 'dropPayloadColumn':
              mutated[e.fdRel] = fd
                .replace('{ conclusion }', '{}')
                .replace('{ remark }', '{}')
              break
          }
          // 变异后源码**必须真的变了**（否则是 ANCHOR-MISS 而不是判据结论）
          expect(
            mutated[e.tabRel] !== e.sources[e.tabRel] || mutated[e.fdRel] !== e.sources[e.fdRel],
            `变异 ${brk} 未命中任何锚点 ⇒ 本次断言不成立（ANCHOR-MISS）`,
          ).toBe(true)
          // 巧合同名的那个字面量在变异后**仍在** tab 里 ⇒ 若判据回退成字面量 grep 就会蒙对
          if (brk !== 'changeSheetArg') {
            expect(
              (mutated[e.tabRel] as string).includes(e.key),
              '前提留痕：巧合同名字面量必须仍在变异后的 tab 里',
            ).toBe(true)
          }

          const p = probeSynthetic(e.cycle, mutated)
          expect(
            p.pendingManual,
            `${e.sheet}: 变异 ${brk} 后仍判「键已确证」⇒ 键其实是从同名字面量蒙来的；${why(p)}`,
          ).toBe(true)
          expect(p.entryKeys, `${e.sheet}: 变异 ${brk} 后不应产出任何 entries 数据键`).toEqual([])
          expect(p.reasons.length, `${e.sheet}: 判不出必须带可读理由（fail-loud）`).toBeGreaterThan(0)
        },
      ),
      { numRuns: NUM_RUNS },
    )
    expect([...seenBreaks].sort(), '六种断链变异未全覆盖').toEqual(
      [
        'changePrefixValue',
        'changeSheetArg',
        'dropImport',
        'dropPayloadColumn',
        'renamePrefixIdent',
        'renameSetField',
      ],
    )
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P8-E：改 `setField` 的 field 实参 ⇒ 键必须随之改变（不得回到同名字面量）
  // ─────────────────────────────────────────────────────────────────────────────
  it('P8-E 改 setField 的 field 实参 ⇒ 拼出的键随之改变，绝不退回同名字面量', () => {
    fc.assert(
      fc.property(
        arbMech4Case.map((c) => ({ ...c, coincidentalCentralSync: true, directCall: false })),
        fc.constantFrom('X', '-v2', '2'),
        (c, suffix) => {
          const e = buildMech4(c)
          const tab = e.sources[e.tabRel] as string
          const mutatedTab = tab.replace(
            new RegExp(`(setField\\((['"\`])${SHEET_NO}\\2,\\s*(['"\`]))${c.field}\\3`),
            (_m, head: string, _q1: string, q2: string) => `${head}${c.field}${suffix}${q2}`,
          )
          expect(mutatedTab !== tab, `field 实参锚点未命中（ANCHOR-MISS）`).toBe(true)
          expect(mutatedTab.includes(e.key), '前提留痕：原键的同名字面量仍在 tab 里').toBe(true)

          const p = probeSynthetic(e.cycle, { ...e.sources, [e.tabRel]: mutatedTab })
          expect(p.entryKeys, `${e.sheet}: field 实参改了，键必须随之改变；${why(p)}`).toEqual([
            `${e.key}${suffix}`,
          ])
          expect(
            p.entryKeys.includes(e.key),
            `${e.sheet}: field 实参改了而键没变 ⇒ 键是从 tab 里那个同名字面量读来的（蒙对）`,
          ).toBe(false)
        },
      ),
      { numRuns: NUM_RUNS_REAL },
    )
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P8-H：任意 `setField` 声明形态下「要么拼对、要么明确判不可确证」，绝不产出错键
  //
  // 覆盖面比 P8-C 多一种：返回类型注解写成对象字面量（`: Promise<{ ok: boolean }>`）。
  // 该形态**平台当前零实例**（105 个 `use*FormData.ts` 实测无一处），而探针
  // `extractFunctionBody` 只跳参数列表、不跳返回类型注解 ⇒ 会把注解里的 `{…}` 当函数体，
  // 结果落在 **fail-loud 判「键不可确证」** 分支（不是产出错键）。
  //
  // 本条断言的是安全性质「never a wrong key」：今天成立（走 pending 分支且带理由），
  // 缺口被修好后同样成立（走拼对分支）⇒ 不把当前缺陷锁成基线（R10.4 / 反假绿）。
  // ─────────────────────────────────────────────────────────────────────────────
  it('P8-H 任意 setField 声明形态下：要么拼出正确键，要么 fail-loud 判不可确证（绝不产出错键）', () => {
    fc.assert(
      fc.property(arbMech4CaseWith(ALL_SETFIELD_STYLES), (c) => {
        const e = buildMech4(c)
        const p = probeSynthetic(e.cycle, e.sources)

        if (p.confirmed) {
          expect(
            p.entryKeys,
            `${e.sheet}: 判「键已确证」时键必须恰是三步链拼出的 '${e.key}'（声明形态=${c.setFieldStyle}）；${why(p)}`,
          ).toEqual([e.key])
          expect(p.column, `${e.sheet}: 确证时写入列必须取 saveField 载荷列`).toBe(e.column)
        } else {
          // 判不出时必须**明确**判不出并带可读理由，且绝不能吐出任何似是而非的键
          expect(
            p.pendingManual,
            `${e.sheet}: 未确证却没标待人工核 ⇒ 静默放过（R2.6 违反）；${why(p)}`,
          ).toBe(true)
          expect(
            p.reasons.length,
            `${e.sheet}: 未确证必须给出理由（fail-loud），声明形态=${c.setFieldStyle}`,
          ).toBeGreaterThan(0)
          expect(
            p.entryKeys,
            `${e.sheet}: 未确证却产出了键 ⇒ 那只能是从字面量蒙来的；${why(p)}`,
          ).toEqual([])
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('P8-H 留痕 — 对象字面量返回类型注解形态的当前实测行为（零实例的潜在缺口）', () => {
    // 固定输入（非随机）：只记录当前行为，便于下一轮回看时定位，不做「必须 pending」的断言
    const withAnnotation = buildMech4({
      cycle: 'QA',
      eol: '\n',
      indent: '',
      quote: "'",
      column: 'conclusion',
      field: 'entries',
      setFieldStyle: 'functionTypedObj',
      assemble: 'dash',
      coincidentalCentralSync: true,
      directCall: false,
      includeReviewCall: false,
      includeCommentDecoy: false,
      includeGetFieldPair: true,
    })
    const annotated = probeSynthetic(withAnnotation.cycle, withAnnotation.sources)
    const plain = buildMech4({
      cycle: 'QA',
      eol: '\n',
      indent: '',
      quote: "'",
      column: 'conclusion',
      field: 'entries',
      setFieldStyle: 'function',
      assemble: 'dash',
      coincidentalCentralSync: true,
      directCall: false,
      includeReviewCall: false,
      includeCommentDecoy: false,
      includeGetFieldPair: true,
    })
    const baseline = probeSynthetic(plain.cycle, plain.sources)

    // 对照：同一份链路只把返回类型注解换成 `Promise<void>` 就能确证 ⇒ 差异只来自注解
    expect(baseline.entryKeys, '对照组（Promise<void>）应确证').toEqual([plain.key])
    // 当前实测：带对象字面量注解时**不产出错键**（这是安全底线，与 P8-H 同向）
    expect(
      annotated.entryKeys.filter((k) => k !== withAnnotation.key),
      '带对象字面量返回注解时若吐出别的键，就是「被同名字面量蒙对」的反面证据',
    ).toEqual([])
    if (!annotated.confirmed) {
      expect(
        annotated.reasons.join(' '),
        '当前走 fail-loud 分支时，理由应指向三步链的步③（取函数体/键拼装模板）',
      ).toContain('setField')
    }
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P8-F：只有非数据键的文件组 ⇒ 数据键集为空且判待人工核（R2.6 的 IF 分支）
  // ─────────────────────────────────────────────────────────────────────────────
  interface DistractorCase {
    cycle: string
    eol: string
    indent: string
    quote: string
    column: StorageColumn
    reviewAsWriteKey: boolean
    includeReadOnlyFamily: boolean
    includeDangling: boolean
    includeCommentWrite: boolean
    includeForeign: boolean
    idxVar: string
  }
  const arbDistractor: fc.Arbitrary<DistractorCase> = fc.record({
    cycle: arbCycle,
    eol: arbEol,
    indent: arbIndent,
    quote: arbQuote,
    column: arbColumn,
    reviewAsWriteKey: fc.boolean(),
    includeReadOnlyFamily: fc.boolean(),
    includeDangling: fc.boolean(),
    includeCommentWrite: fc.boolean(),
    includeForeign: fc.boolean(),
    idxVar: arbIdxVar,
  })

  it('P8-F 只含非数据键（含出现在写入位置的复核键）的文件组 ⇒ 数据键集为空且判待人工核', () => {
    fc.assert(
      fc.property(arbDistractor, (c) => {
        const q = c.quote
        const lit = (s: string) => `${q}${s}${q}`
        const cycle = c.cycle
        const sheet = `${cycle}-${SHEET_NO}`
        const reviewKey = `${sheet}-adjustment`
        const centralKey = `${sheet}-entries`
        const danglingKey = `${sheet}-entries-label`
        const commentKey = `${sheet}-entries-in-comment`
        const famTpl = (prefix: string, suffix: string) =>
          '`' + prefix + '-entry-' + itp(c.idxVar) + '-' + suffix + '`'

        const tabLines: string[] = [
          `<template>`,
          `  <div><GtReviewTrigger section-id="${reviewKey}" /></div>`,
          ...(c.includeCommentWrite
            ? [`  <!-- debouncedSave(${lit(commentKey)}, { ${c.column}: JSON.stringify(entries) }) -->`]
            : []),
          `</template>`,
          ``,
          `<script setup lang="ts">`,
          `import { ref, onMounted } from 'vue'`,
          `import { useAdjustmentCentralSync } from '@/components/workpaper/composables/useAdjustmentCentralSync'`,
          `const props = defineProps<{ allResponses?: Map<string, any> }>()`,
          `const entries = ref<any[]>([])`,
          `const { debouncedSave } = (props as any).formData ?? {}`,
          `useAdjustmentCentralSync({ wpCode: '${cycle}', itemId: ${lit(centralKey)} })`,
          `function review() { openReviewDialog?.(${lit(reviewKey)}) }`,
          ...(c.includeDangling ? [`const LABEL_TEXT = ${lit(danglingKey)}`] : []),
          ...(c.includeCommentWrite
            ? [`// debouncedSave(${lit(commentKey)}, { ${c.column}: JSON.stringify(entries.value) })`]
            : []),
          // 复核键即使出现在**写入调用位置**也必须被排除（R2.4：复核键不是数据落点）
          ...(c.reviewAsWriteKey
            ? [`function bad() { debouncedSave(${lit(reviewKey)}, { ${c.column}: JSON.stringify(entries.value) }) }`]
            : []),
          // 只读引用同族键（无写入点 ⇒ 取不到写入列 ⇒ 不构成「键已确证」）
          ...(c.includeReadOnlyFamily
            ? [
                `function restoreEntries() {`,
                `  const resp = props.allResponses?.get(${famTpl(`${cycle}-${SHEET_NO}`, 'data')})`,
                `  if (resp) entries.value.push(JSON.parse(resp.${c.column}))`,
                `}`,
              ]
            : []),
          // 外循环的同形态写入点（归属过滤必须把它挡在外面）
          ...(c.includeForeign
            ? [
                `function foreign() {`,
                `  debouncedSave(${famTpl(`${FOREIGN_CYCLE}-${SHEET_NO}`, 'desc')}, { ${c.column}: JSON.stringify(entries.value) })`,
                `}`,
              ]
            : []),
          `onMounted(() => { void review })`,
          `</script>`,
        ]

        const sources: Record<string, string | null> = {
          [relTab(cycle)]: render(tabLines, c.eol, c.indent),
          [relAdj(cycle)]: null,
          [relFd(cycle)]: null,
        }
        const p = probeSynthetic(cycle, sources)

        expect(
          p.entryKeys,
          `${sheet}: 文件组里没有任何合法 entries 写入点，却产出了数据键；${why(p)}`,
        ).toEqual([])
        expect(p.confirmed).toBe(false)
        expect(
          p.pendingManual,
          `${sheet}: 键不可确证必须标待人工核（R2.6），不得静默放过；${why(p)}`,
        ).toBe(true)
        expect(p.reasons.length, `${sheet}: 必须带可读理由（fail-loud）`).toBeGreaterThan(0)
        // 反空转：注入的两类非数据键必须真被认出来
        expect(p.reviewKeys, `${sheet}: 复核键未被识别 ⇒ 排除判据空转`).toContain(reviewKey)
        expect(p.centralSyncKeys, `${sheet}: 中央同步键未被识别`).toContain(centralKey)
        if (c.includeCommentWrite) {
          expect(
            [...p.entryKeys, ...p.otherDataKeys, ...p.reviewKeys, ...p.centralSyncKeys].filter((k) =>
              k.includes('in-comment'),
            ),
            `${sheet}: 注释里的写入调用被当真了 ⇒ stripComments 未生效`,
          ).toEqual([])
        }
        if (c.includeDangling) {
          expect([...p.entryKeys, ...p.otherDataKeys]).not.toContain(danglingKey)
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // ─────────────────────────────────────────────────────────────────────────────
  // P8-G：真实 16 张 —— 重扫结果 == 契约清单 observed，且对语义无关扰动不变（R7.5）
  // ─────────────────────────────────────────────────────────────────────────────
  /** 从清单取一条 `observed` 的机器可读重扫记录。 */
  function observedOf(sheet: string) {
    const e = (CONTRACT.sheets[sheet] ?? {}) as any
    const o = (e.observed ?? {}) as any
    return {
      entriesKeys: [...(o.entries_keys ?? [])].sort() as string[],
      otherDataKeys: [...(o.other_data_keys ?? [])].sort() as string[],
      otherDataKeysNote: String(o.other_data_keys_note ?? ''),
      reviewKeys: [...(o.excluded_review_keys ?? [])].sort() as string[],
      centralSyncKeys: [...(o.excluded_central_sync_keys ?? [])].sort() as string[],
      field: (o.frontend_field ?? null) as string | null,
      mechanism: (e.mechanism ?? null) as string | null,
      keyFamily: (e.key_family ?? null) as string | null,
      itemId: (e.item_id ?? null) as string | null,
    }
  }

  it('P8-G 真实 16 张的重扫结果与契约清单 observed 逐条相等（R7.5，逐张全覆盖）', () => {
    for (const sheet of REAL_TARGETS) {
      const p = REAL_PROBES[sheet]
      const o = observedOf(sheet)
      expect([...p.entryKeys].sort(), `${sheet}: 重扫 entries 键集 ≠ 清单 observed.entries_keys`).toEqual(
        o.entriesKeys,
      )
      expect(
        [...p.reviewKeys].sort(),
        `${sheet}: 重扫复核键排除集 ≠ 清单 observed.excluded_review_keys`,
      ).toEqual(o.reviewKeys)
      expect(
        [...p.centralSyncKeys].sort(),
        `${sheet}: 重扫中央同步键排除集 ≠ 清单 observed.excluded_central_sync_keys`,
      ).toEqual(o.centralSyncKeys)
      expect(p.column, `${sheet}: 机制推导的写入列 ≠ 清单 observed.frontend_field`).toBe(o.field)
      expect(p.mechanism, `${sheet}: 实测机制 ≠ 清单 mechanism`).toBe(o.mechanism)
      expect(p.keyFamily, `${sheet}: 实测键族 ≠ 清单 key_family`).toBe(o.keyFamily)
      expect(p.entryKeys, `${sheet}: 清单 item_id 不在重扫键集内`).toContain(o.itemId)
      // 重扫到的表级独立键必须已登记；清单登记而重扫取不到的（探针写入点形态未覆盖）
      // 必须由清单自身写明理由 ⇒ 「有登记或有理由」，不得静默两侧不等
      for (const k of p.otherDataKeys) {
        expect(o.otherDataKeys, `${sheet}: 重扫到未登记的表级独立键 '${k}'`).toContain(k)
      }
      const missed = o.otherDataKeys.filter((k) => !p.otherDataKeys.includes(k))
      if (missed.length) {
        expect(
          o.otherDataKeysNote.length,
          `${sheet}: 清单登记的表级独立键 ${JSON.stringify(missed)} 不在重扫集里，` +
            '却没有 observed.other_data_keys_note 说明该差异的可复算成因',
        ).toBeGreaterThan(20)
      }
    }
  })

  it('P8-G 真实源码在语义无关扰动（行尾 LF/CRLF · 注释内诱饵）下重扫结果不变', () => {
    const realCache = new Map<string, string>()
    const readReal = (rel: string) => {
      if (!realCache.has(rel)) realCache.set(rel, fs.readFileSync(path.join(WP_ROOT, rel), 'utf8'))
      return realCache.get(rel) as string
    }

    fc.assert(
      fc.property(
        fc.constantFrom(...REAL_TARGETS),
        fc.constantFrom('lf' as const, 'crlf' as const),
        fc.constantFrom('prepend' as const, 'append' as const, 'both' as const),
        (sheet, eolMode, where) => {
          const base = REAL_PROBES[sheet]
          const cycle = base.cycle
          const decoyKey = `${sheet}-entries-decoy`
          const overrides: Record<string, string | null> = {}
          const rels = [base.files.tab, base.files.adjustment, base.files.formData].filter(
            Boolean,
          ) as string[]
          expect(rels.length, `${sheet}: 探针一个源文件都没读到 ⇒ 扫描面为空`).toBeGreaterThan(0)

          for (const rel of rels) {
            const raw = readReal(rel)
            const lf = raw.replace(/\r\n/g, '\n')
            const body = eolMode === 'crlf' ? lf.replace(/\n/g, '\r\n') : lf
            const isVue = rel.endsWith('.vue')
            const decoy = isVue
              ? `<!-- debouncedSave('${decoyKey}', { remark: 1 }) openReviewDialog('${decoyKey}') -->`
              : `/* debouncedSave('${decoyKey}', { remark: 1 }) openReviewDialog('${decoyKey}') */`
            const eol = eolMode === 'crlf' ? '\r\n' : '\n'
            const head = where === 'prepend' || where === 'both' ? decoy + eol : ''
            const tail = where === 'append' || where === 'both' ? eol + decoy + eol : ''
            overrides[rel] = head + body + tail
          }

          const p = probeSheet(cycle, { sources: createSourceBundle(overrides) })
          const label = `${sheet}（行尾=${eolMode} 诱饵位置=${where}）`
          expect([...p.entryKeys].sort(), `${label}: 键集随语义无关扰动变了`).toEqual(
            [...base.entryKeys].sort(),
          )
          expect([...p.otherDataKeys].sort(), `${label}: 表级独立键集变了`).toEqual(
            [...base.otherDataKeys].sort(),
          )
          expect([...p.reviewKeys].sort(), `${label}: 复核键排除集变了`).toEqual(
            [...base.reviewKeys].sort(),
          )
          expect([...p.centralSyncKeys].sort(), `${label}: 中央同步键排除集变了`).toEqual(
            [...base.centralSyncKeys].sort(),
          )
          expect(p.column, `${label}: 写入列变了`).toBe(base.column)
          expect(p.mechanism, `${label}: 机制判定变了`).toBe(base.mechanism)
          expect(p.keyFamily, `${label}: 键族判定变了`).toBe(base.keyFamily)
          expect(p.confirmed, `${label}: 确证性变了`).toBe(base.confirmed)
          expect(
            [...p.entryKeys, ...p.otherDataKeys, ...p.reviewKeys, ...p.centralSyncKeys].filter((k) =>
              k.includes('-decoy'),
            ),
            `${label}: 注释里的诱饵键漏进了某个集合 ⇒ stripComments 对真实源码失效`,
          ).toEqual([])
        },
      ),
      { numRuns: NUM_RUNS_REAL },
    )
  })

  it('P8-G 真实源码里确实存在「中央同步键与真数据键同名」的那一例（G11 反空转）', () => {
    const collided = REAL_TARGETS.filter((s) => {
      const p = REAL_PROBES[s]
      return p.entryKeys.some((k) => p.centralSyncKeys.includes(k))
    })
    expect(
      collided.length,
      '真实源码里一例都没有「同名不同源」⇒ P8-C/P8-D 的那个反例在本仓库无实例可证；' +
        'design E12 → E17 / G11 记载该例存在，请复核探针是否已退化',
    ).toBeGreaterThan(0)
    for (const s of collided) {
      const p = REAL_PROBES[s]
      expect(
        p.forms,
        `${s}: 键与中央同步键同名却不是形态④来源 ⇒ 就是「把中央同步键当数据键」`,
      ).toContain('cross_file_runtime')
      expect(p.confirmed, `${s}: 同名不同源的键仍应被确证（E12 的结论已被 E17 推翻）`).toBe(true)
    }
  })
})
