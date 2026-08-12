/**
 * E1 受限表动态类别 UI + 稳定序号守卫（spec e-cycle Task 16）
 *
 * 覆盖四条判据：
 * 1. **Property 28 稳定序号** —— `nextRestrictedSeq` 必须走 `max(现有最大, 已存计数器) + 1`，
 *    删掉高序号行后**不得复用**该序号；`parseRestrictedSeq` 对脏值三态归一。
 * 2. **行序** —— ②表按 `displayOrder`（= 源 docx 行序）排，自定义类别追加在六类之后。
 * 3. **Property 29 防回退** —— 自定义类别删空后仍走 `[]` 分支（条件表语义不被打破）。
 *    ⚠️ 条件表本体语义（`undefined` 不进 removed / `[]` 进 removed）已由
 *    `e1NoteSubtableContract.spec.ts` 与 `e1NoteTextsAndPayload.spec.ts` 覆盖，
 *    本文件**只加一条**「新增/删空自定义类别不改变该语义」的防回退断言，不重造判据。
 * 4. **组件接线** —— `nextRestrictedSeq` / `parseRestrictedSeq` / `partitionUnclassified`
 *    的调用必须在**函数体内**（不是只在 import 行或注释里），且计数器随行落库。
 *
 * 🔴 每条判据都配**反向自检**（替身复现旧/错实现必打红），否则断言可能空转。
 *
 * 🔴 判据形态而非字符：`toContain('符号名')` 会被 import 行 / 注释 / 模板里的同名
 *    字样骗过 ⇒ 一律「截函数体后再断言」。截 TS/Vue 函数体要**先用圆括号配对跳过
 *    参数列表**（第一个 `{` 可能是参数的内联类型字面量或返回类型注解）。
 *
 * 金额控件裁决（本轮实证，2026-08-09）：②表三个金额列**已经是** `WpAmountInput`
 *    （段内 `el-input-number` 与 `:formatter` 计数均为 0）⇒ 只加正向断言、**不下调**
 *    `E1_LEGACY_FORMATTER_BUDGET`（该表不含 `E1TabDisclosure.vue` —— 它在
 *    `e1AmountControlIronLaw.spec.ts` 的 `SCOPED` 里已被逐个断言）。文件里剩余的 2 处
 *    `el-input-number` 是**折算率**（`:precision="4"`，endRate/openRate），属「反向边界：
 *    汇率/比例不得套 WpAmountInput」，不得替换。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  customBucketKey,
  e1RestrictedRowId,
  e1RestrictedSeqKey,
  isCustomBucketKey,
  nextRestrictedSeq,
  parseRestrictedSeq,
  partitionUnclassified,
  resolveRestrictedRows,
  type E1RestrictedBucketDef,
  type E1RestrictedRow,
} from '../e1RestrictedScope'

// ─── 源码读取与函数体截取 ────────────────────────────────────────────────────

const VUE = resolve(__dirname, '../../e1/E1TabDisclosure.vue')
const TS = resolve(__dirname, '../e1RestrictedScope.ts')

function readVue(): string {
  return readFileSync(VUE, 'utf-8')
}
function readTs(): string {
  return readFileSync(TS, 'utf-8')
}

/**
 * 剥注释（`//`、块注释、HTML 注释）。
 *
 * 🔴 必须剥 —— 本模块与组件的注释里**如实写着**被禁的反例形态
 * （「朴素实现 `max(现有) + 1` 必被守卫打红」「禁 length/max+1」），
 * 不剥会把说明文字数成真实代码。
 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/** 从 `from` 起做括号配对，返回配对结束位置（含闭合符）；找不到返回 -1。 */
function matchPair(src: string, from: number, open: string, close: string): number {
  if (src[from] !== open) return -1
  let depth = 0
  for (let i = from; i < src.length; i++) {
    const c = src[i]
    // 跳过字符串字面量（模板串里可能有裸括号）
    if (c === '"' || c === "'" || c === '`') {
      const q = c
      i++
      while (i < src.length && src[i] !== q) {
        if (src[i] === '\\') i++
        i++
      }
      continue
    }
    if (c === open) depth++
    else if (c === close) {
      depth--
      if (depth === 0) return i
    }
  }
  return -1
}

/**
 * 截具名函数体（块体形态）。
 *
 * 🔴 先用**圆括号配对**跳过参数列表，再找第一个含语句特征的 `{`
 *    —— 直接取「声明后第一个 `{`」会命中参数的内联类型字面量
 *    （`function f(o: { a: string })`）或返回类型注解（`(): { a: X } {`）。
 */
function fnBody(src: string, name: string): string {
  const re = new RegExp(
    `(?:export\\s+)?(?:async\\s+function|function)\\s+${name}\\s*(?:<[^(]*>)?\\s*\\(`,
    'g',
  )
  const m = re.exec(src)
  if (!m) return ''
  const parenOpen = src.indexOf('(', m.index + m[0].length - 1)
  const parenClose = matchPair(src, parenOpen, '(', ')')
  if (parenClose < 0) return ''
  // 从参数列表之后逐个候选 `{` 做配对，取第一个含语句特征的块
  let cursor = parenClose + 1
  for (let guard = 0; guard < 8; guard++) {
    const brace = src.indexOf('{', cursor)
    if (brace < 0) return ''
    const end = matchPair(src, brace, '{', '}')
    if (end < 0) return ''
    const body = src.slice(brace + 1, end)
    if (/\b(return|const|let|await|if|for|throw)\b/.test(body)) return body
    cursor = end + 1
  }
  return ''
}

/** 截 `const name = ... => { ... }` 或 `const name = computed(() => ...)` 的实参区。 */
function constInitializer(src: string, name: string): string {
  const re = new RegExp(`const\\s+${name}\\s*(?::[^=]*)?=\\s*`, 'g')
  const m = re.exec(src)
  if (!m) return ''
  const from = m.index + m[0].length
  // 优先取圆括号配对（`computed(...)` / `useX(...)` 形态）
  const paren = src.indexOf('(', from)
  const brace = src.indexOf('{', from)
  if (paren >= 0 && (brace < 0 || paren < brace)) {
    const end = matchPair(src, paren, '(', ')')
    if (end > 0) return src.slice(paren + 1, end)
  }
  if (brace >= 0) {
    const end = matchPair(src, brace, '{', '}')
    if (end > 0) return src.slice(brace + 1, end)
  }
  return ''
}

/** 取 `<template>` 区（模板里的字样不算 script 消费）。 */
function templateBlock(src: string): string {
  const i = src.indexOf('<template>')
  return i < 0 ? '' : src.slice(i)
}

/** 取 `<script setup ...>` 区。 */
function scriptBlock(src: string): string {
  const m = /<script[^>]*>/.exec(src)
  if (!m) return ''
  const start = m.index + m[0].length
  const end = src.indexOf('</script>', start)
  return end < 0 ? src.slice(start) : src.slice(start, end)
}

// ─── 替身：朴素实现（用于反向自检）──────────────────────────────────────────

/** 旧/错实现之一：只看现有行的最大序号（删掉高序号行后必复用）。 */
function naiveMaxPlusOne(existingRows: readonly { id: string }[]): number {
  let maxSeq = 0
  for (const r of existingRows) {
    const m = /_(\d+)$/.exec(String(r.id ?? ''))
    if (!m) continue
    const n = Number(m[1])
    if (Number.isFinite(n) && n > maxSeq) maxSeq = n
  }
  return maxSeq + 1
}

/** 旧/错实现之二：按行数派生（删一行再增必复用）。 */
function naiveRowsLength(existingRows: readonly unknown[]): number {
  return existingRows.length + 1
}

// ─── fixture ────────────────────────────────────────────────────────────────

/**
 * 桶定义样本 —— **声明序刻意 ≠ docx 行序**（`letter_of_credit` 在 `bank_acceptance`
 * 之前），`displayOrder` 复现源 docx 行序（银行承兑在信用证之前）。
 *
 * 🔴 若样本按 docx 序排列，「行序按数组下标」的旧实现也能通过 ⇒ 掩盖既存缺陷
 *    （memory 已记：E1 受限桶那条铁律的成因正是 fixture 顺序与真源顺序不一致）。
 */
const DEFS: E1RestrictedBucketDef[] = [
  { key: 'letter_of_credit', label: '信用证保证金', isPlatformExtra: false, displayOrder: 1 },
  { key: 'bank_acceptance', label: '银行承兑汇票保证金', isPlatformExtra: false, displayOrder: 0 },
  { key: 'performance', label: '履约保证金', isPlatformExtra: false, displayOrder: 2 },
  { key: 'overseas', label: '存放在境外且资金汇回受到限制的款项', isPlatformExtra: false, displayOrder: 4 },
  { key: 'pledged_deposit', label: '用于担保的定期存款或通知存款', isPlatformExtra: false, displayOrder: 3 },
  { key: 'statutory_reserve', label: '金融企业法定存款准备金或备付金', isPlatformExtra: false, displayOrder: 5 },
  { key: 'other', label: '其他受限资金', isPlatformExtra: true, displayOrder: 12 },
]

function manualRow(bucketKey: string, seq: number, label: string): E1RestrictedRow {
  return {
    id: e1RestrictedRowId(bucketKey, seq),
    bucketKey,
    label,
    openingAmount: 0,
    endingAmount: 0,
    reason: '',
    codes: [],
    fromFourTable: false,
  }
}

// ────────────────────────────────────────────────────────────────────────────

describe('E1 受限表稳定序号（Property 28）', () => {
  it('parseRestrictedSeq：合法正整数原样返回', () => {
    expect(parseRestrictedSeq('7')).toBe(7)
    expect(parseRestrictedSeq(7)).toBe(7)
    expect(parseRestrictedSeq(' 12 ')).toBe(12)
  })

  it('parseRestrictedSeq：非数值 / 空 / 负数 / 零一律归 0（不抛）', () => {
    for (const bad of [undefined, null, '', '  ', 'abc', 'NaN', {}, [], '-3', -3, '0', 0, Number.NaN]) {
      expect(parseRestrictedSeq(bad as unknown), `输入 ${JSON.stringify(bad)}`).toBe(0)
    }
  })

  it('parseRestrictedSeq：小数向下取整（计数器语义是整数序号）', () => {
    expect(parseRestrictedSeq('3.9')).toBe(3)
    expect(parseRestrictedSeq(3.2)).toBe(3)
  })

  it('parseRestrictedSeq：Infinity 不得当成合法序号', () => {
    expect(parseRestrictedSeq('Infinity')).toBe(0)
    expect(parseRestrictedSeq(Number.POSITIVE_INFINITY)).toBe(0)
  })

  it('正向：空表 + 无计数器 → 1', () => {
    expect(nextRestrictedSeq([], undefined)).toBe(1)
  })

  it('🔴 核心：删掉最高序号行后，新 key 序号 > 历史最大（计数器兜住）', () => {
    // 历史：连续新增 3 个自定义类别，计数器落库为 3
    const rows = [
      manualRow(customBucketKey('甲'), 1, '甲'),
      manualRow(customBucketKey('乙'), 2, '乙'),
      manualRow(customBucketKey('丙'), 3, '丙'),
    ]
    const storedSeq = '3'

    // 审计师删掉「丙」（序号 3）后再新增
    const afterDelete = rows.filter((r) => r.label !== '丙')
    const next = nextRestrictedSeq(afterDelete, storedSeq)

    expect(next).toBe(4)
    // 新 row id 不得与任何历史 id 相同（含已删除的那个）
    const newId = e1RestrictedRowId(customBucketKey('丁'), next)
    for (const r of rows) expect(newId).not.toBe(r.id)
  })

  it('🔴 反向自检：朴素 max+1 会复用已删序号（证明判据非空转）', () => {
    const rows = [
      manualRow(customBucketKey('甲'), 1, '甲'),
      manualRow(customBucketKey('乙'), 2, '乙'),
      manualRow(customBucketKey('丙'), 3, '丙'),
    ]
    const afterDelete = rows.filter((r) => r.label !== '丙')

    // 朴素实现回落到 3 —— 与已删除的「丙」撞号
    expect(naiveMaxPlusOne(afterDelete)).toBe(3)
    // 被测实现不会
    expect(nextRestrictedSeq(afterDelete, '3')).toBe(4)
    expect(nextRestrictedSeq(afterDelete, '3')).not.toBe(naiveMaxPlusOne(afterDelete))
  })

  it('🔴 反向自检：按行数派生同样会复用（rows.length + 1）', () => {
    const afterDelete = [
      manualRow(customBucketKey('甲'), 1, '甲'),
      manualRow(customBucketKey('乙'), 2, '乙'),
    ]
    expect(naiveRowsLength(afterDelete)).toBe(3)
    expect(nextRestrictedSeq(afterDelete, '3')).toBe(4)
  })

  it('计数器落后于行集时以行集为准（防「计数器未落库就连续新增」撞号）', () => {
    const rows = [manualRow(customBucketKey('甲'), 5, '甲')]
    // 计数器还是 0（未落库），但行里已有 5 → 必须给 6
    expect(nextRestrictedSeq(rows, '0')).toBe(6)
    expect(nextRestrictedSeq(rows, undefined)).toBe(6)
  })

  it('计数器脏值不得让序号回落（走 parseRestrictedSeq 归一）', () => {
    const rows = [manualRow(customBucketKey('甲'), 2, '甲')]
    for (const dirty of ['abc', '', null, '-9']) {
      expect(nextRestrictedSeq(rows, dirty as unknown)).toBe(3)
    }
  })

  it('四表命中行的 id 不带自定义前缀，不影响自定义序号推进', () => {
    const ftRow: E1RestrictedRow = {
      ...manualRow('bank_acceptance', 0, '银行承兑汇票保证金'),
      fromFourTable: true,
    }
    // 四表行 id 是 `restricted_bank_acceptance_0`，尾号 0 不抬高计数
    expect(nextRestrictedSeq([ftRow], '2')).toBe(3)
  })

  it('e1RestrictedSeqKey 两变体键名不同且形态稳定（改名会丢已录计数器）', () => {
    expect(e1RestrictedSeqKey('listed')).toBe('E1-disclosure-listed-restricted-seq')
    expect(e1RestrictedSeqKey('soe')).toBe('E1-disclosure-soe-restricted-seq')
    expect(e1RestrictedSeqKey('listed')).not.toBe(e1RestrictedSeqKey('soe'))
  })

  it('单一真源：nextRestrictedSeq 的脏值归一必须复用 parseRestrictedSeq', () => {
    const body = fnBody(stripComments(readTs()), 'nextRestrictedSeq')
    expect(body, 'nextRestrictedSeq 函数体未截到（守卫自身缺陷）').not.toBe('')
    expect(body).toContain('parseRestrictedSeq(')
    // 反向：不得在函数体内自己再写一份 Number.isFinite 归一
    expect(
      /Number\.isFinite\(\s*stored/.test(body),
      'nextRestrictedSeq 内不得再写一份计数器归一逻辑（双真源会漂移）',
    ).toBe(false)
  })
})

describe('E1 受限表行序（displayOrder，非数组下标）', () => {
  function rowsOf(defs: E1RestrictedBucketDef[], existing: E1RestrictedRow[] = []) {
    return resolveRestrictedRows({
      prefill: {
        leaves: [
          { code: '1002.01', name: '银行承兑汇票保证金', opening: 1, closing: 1, slot: 'bank', autoBucket: 'bank_acceptance' },
          { code: '1002.02', name: '信用证保证金', opening: 2, closing: 2, slot: 'bank', autoBucket: 'letter_of_credit' },
          { code: '1002.03', name: '履约保证金', opening: 3, closing: 3, slot: 'bank', autoBucket: 'performance' },
          { code: '1002.04', name: '用于担保的定期存款', opening: 4, closing: 4, slot: 'bank', autoBucket: 'pledged_deposit' },
          { code: '1002.05', name: '境外冻结存款', opening: 5, closing: 5, slot: 'bank', autoBucket: 'overseas' },
          { code: '1002.06', name: '法定存款准备金', opening: 6, closing: 6, slot: 'bank', autoBucket: 'statutory_reserve' },
        ],
        bucketDefs: defs,
        source: {} as never,
      },
      manualMap: {},
      existingRows: existing,
    })
  }

  it('六类行序 == docx 行序（银行承兑在信用证之前），不按数组下标', () => {
    const keys = rowsOf(DEFS).map((r) => r.bucketKey)
    expect(keys).toEqual([
      'bank_acceptance',
      'letter_of_credit',
      'performance',
      'pledged_deposit',
      'overseas',
      'statutory_reserve',
    ])
    // 数组下标序（声明序）是另一个顺序 —— 证明排序键真的是 displayOrder
    const declOrder = DEFS.filter((d) => d.key !== 'other').map((d) => d.key)
    expect(keys).not.toEqual(declOrder)
  })

  it('🔴 反向自检：改回数组下标排序会产出与 docx 不符的行序', () => {
    const legacyDefs = DEFS.map(({ displayOrder: _drop, ...rest }) => rest)
    const keys = rowsOf(legacyDefs as E1RestrictedBucketDef[]).map((r) => r.bucketKey)
    // 缺 displayOrder 时退化为数组下标 ⇒ 信用证被排到第一（复现旧缺陷形态）
    expect(keys[0]).toBe('letter_of_credit')
    expect(keys).not.toEqual([
      'bank_acceptance',
      'letter_of_credit',
      'performance',
      'pledged_deposit',
      'overseas',
      'statutory_reserve',
    ])
  })

  it('自定义类别追加在源 docx 六类之后', () => {
    const custom = manualRow(customBucketKey('司法冻结'), 7, '司法冻结')
    const rows = rowsOf(DEFS, [custom])
    const keys = rows.map((r) => r.bucketKey)
    const customIdx = keys.indexOf(custom.bucketKey)

    expect(customIdx).toBeGreaterThan(-1)
    // 六个源类桶全部排在自定义类别之前
    for (const k of ['bank_acceptance', 'letter_of_credit', 'performance', 'pledged_deposit', 'overseas', 'statutory_reserve']) {
      expect(keys.indexOf(k), `${k} 应排在自定义类别之前`).toBeLessThan(customIdx)
    }
  })

  it('多个自定义类别之间保持稳定序（不因 Map 迭代顺序抖动）', () => {
    const c1 = manualRow(customBucketKey('司法冻结'), 7, '司法冻结')
    const c2 = manualRow(customBucketKey('监管专户'), 8, '监管专户')
    const a = rowsOf(DEFS, [c1, c2]).map((r) => r.bucketKey)
    const b = rowsOf(DEFS, [c1, c2]).map((r) => r.bucketKey)
    expect(a).toEqual(b)
    expect(a.indexOf(c1.bucketKey)).toBeLessThan(a.indexOf(c2.bucketKey))
  })
})

describe('E1 受限表序号端到端（Property 28 落库口径）', () => {
  // 🔴 本组补的是一处**真实缺陷**留下的口子（2026-08-10 浏览器实测发现）：
  //    `nextRestrictedSeq` 算得对（计数器 3），但 `resolveRestrictedRows` 末尾曾用
  //    **数组下标**重算全部行 id ⇒ 新行 id 被覆盖成 `_2`（刚删那行的序号），
  //    而 `saveAll` 序列化的正是 `resolveRestrictedRows` 的输出 ⇒ 落库 id 复用。
  //
  //    原有断言只测「`nextRestrictedSeq` 返回值」与「行序」两件事，中间那一跳
  //    （返回值能否活到落库）无人断言 ⇒ 42 例全绿而缺陷仍在。
  //    判据必须落在 **`resolveRestrictedRows` 的输出**上，不是纯函数返回值上。
  const emptyPrefill = { leaves: [], bucketDefs: DEFS, source: {} as never }

  /** 复现审计师动作：新增 → 删除 → 再新增，返回每步落库行。 */
  function addThenDeleteThenAdd(): { firstId: string; secondId: string; storedSeq: string } {
    // ① 新增「甲」：空表 + 无计数器 ⇒ seq 1
    const seq1 = nextRestrictedSeq([], undefined)
    const first = manualRow(customBucketKey('甲'), seq1, '甲')
    const afterAdd1 = resolveRestrictedRows({
      prefill: emptyPrefill,
      manualMap: {},
      existingRows: [first],
    })
    expect(afterAdd1).toHaveLength(1)

    // ② 删除「甲」→ 行集空，但计数器保留 seq1
    const afterDelete = resolveRestrictedRows({
      prefill: emptyPrefill,
      manualMap: {},
      existingRows: [],
    })
    expect(afterDelete).toHaveLength(0)

    // ③ 再新增「乙」：计数器兜住 ⇒ seq 2
    const seq2 = nextRestrictedSeq(afterDelete, String(seq1))
    const second = manualRow(customBucketKey('乙'), seq2, '乙')
    const afterAdd2 = resolveRestrictedRows({
      prefill: emptyPrefill,
      manualMap: {},
      existingRows: [second],
    })
    expect(afterAdd2).toHaveLength(1)

    return {
      firstId: afterAdd1[0].id,
      secondId: afterAdd2[0].id,
      storedSeq: String(seq2),
    }
  }

  it('🔴 核心：删除后再新增，resolveRestrictedRows 输出的 id 不复用已删序号', () => {
    const { firstId, secondId } = addThenDeleteThenAdd()
    // 这条断言正是缺陷态下会红的那条（缺陷态 secondId === firstId 的尾号）
    expect(secondId).not.toBe(firstId)
    expect(secondId.endsWith('_2'), `第二行 id 应带 seq 2，实际 ${secondId}`).toBe(true)
    expect(firstId.endsWith('_1'), `第一行 id 应带 seq 1，实际 ${firstId}`).toBe(true)
  })

  it('🔴 resolveRestrictedRows 不得改写 existingRows 已有行的 id（id 是稳定主键）', () => {
    // 传入一个「序号远高于数组下标」的手工行 —— 下标是 0，seq 是 9
    const high = manualRow(customBucketKey('丙'), 9, '丙')
    const rows = resolveRestrictedRows({
      prefill: emptyPrefill,
      manualMap: {},
      existingRows: [high],
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].id, 'id 被按数组下标重算了（历史 cell/备注会串行）').toBe(high.id)
    expect(rows[0].id).toBe('restricted_custom_丙_9')
  })

  it('🔴 与四表行混排时，自定义行 id 仍保序号不取下标', () => {
    const custom = manualRow(customBucketKey('丁'), 7, '丁')
    const rows = resolveRestrictedRows({
      prefill: {
        leaves: [
          { code: '1002.01', name: '银行承兑汇票保证金', opening: 1, closing: 1, slot: 'bank', autoBucket: 'bank_acceptance' },
          { code: '1002.02', name: '信用证保证金', opening: 2, closing: 2, slot: 'bank', autoBucket: 'letter_of_credit' },
        ],
        bucketDefs: DEFS,
        source: {} as never,
      },
      manualMap: {},
      existingRows: [custom],
    })
    const customRow = rows.find((r) => r.bucketKey === customBucketKey('丁'))
    expect(customRow, '自定义行丢失').toBeDefined()
    expect(customRow!.id).toBe(custom.id)
    // 自定义行排在四表六类之后（行序判据不受本次改动影响）
    expect(rows[rows.length - 1].bucketKey).toBe(customBucketKey('丁'))
  })

  it('🔴 反向自检：按数组下标生成 id 会与已删序号撞号（证明判据非空转）', () => {
    // 复现缺陷实现：下标即 id 序号
    const naiveIdOf = (rows: readonly E1RestrictedRow[]) =>
      rows.map((r, i) => e1RestrictedRowId(r.bucketKey, i))

    const first = manualRow(customBucketKey('甲'), 1, '甲')
    // 删掉「甲」后新增「乙」，计数器给 2，但缺陷实现按下标 0 生成
    const second = manualRow(customBucketKey('乙'), nextRestrictedSeq([], '1'), '乙')
    expect(second.id).toBe('restricted_custom_乙_2')

    // 缺陷实现把两者都压成 `_0` ⇒ 不同类别同 id
    const naiveFirst = naiveIdOf([first])[0]
    const naiveSecond = naiveIdOf([second])[0]
    expect(naiveFirst).toBe('restricted_custom_甲_0')
    expect(naiveSecond).toBe('restricted_custom_乙_0')
    expect(naiveFirst.endsWith('_0') && naiveSecond.endsWith('_0')).toBe(true)

    // 被测实现保住了各自的 seq
    const kept = resolveRestrictedRows({
      prefill: emptyPrefill,
      manualMap: {},
      existingRows: [second],
    })
    expect(kept[0].id).toBe(second.id)
    expect(kept[0].id).not.toBe(naiveSecond)
  })

  it('🔴 源码级：id 必须先查已持久化 id，下标只能作新桶兜底', () => {
    const body = fnBody(stripComments(readTs()), 'resolveRestrictedRows')
    expect(body, 'resolveRestrictedRows 函数体未截到（守卫自身缺陷）').not.toBe('')

    // 🔴 判据不是「禁止 e1RestrictedRowId(bucketKey, i) 出现」——
    //    四表新归集出来的桶本就没有历史 id，必须由它兜底生成，禁掉会把正确实现判红
    //    （本守卫初版就犯了这个错：行为级断言全绿、只有源码级判据打红正确代码）。
    //    真判据 = id 表达式**先查 existingRows 的 id 映射**，兜底在 `??` 右侧。
    const idExpr = /id:\s*(\w+)\.get\(\s*bucketKey\s*\)\s*\?\?\s*e1RestrictedRowId\(/.exec(body)
    expect(
      idExpr,
      'id 必须形如 `<map>.get(bucketKey) ?? e1RestrictedRowId(...)`，即已持久化 id 优先',
    ).not.toBeNull()

    // 该映射必须由 existingRows（`existing`）填充，而不是从聚合结果派生
    const mapName = idExpr![1]
    expect(body).toMatch(
      new RegExp(`${mapName}\\.set\\(`),
      `${mapName} 必须被 set 填充，否则恒为空 = 等价于没修`,
    )
    expect(body).toMatch(
      new RegExp(`for\\s*\\(\\s*const\\s+\\w+\\s+of\\s+existing\\s*\\)[\\s\\S]{0,200}${mapName}\\.set\\(`),
      `${mapName} 必须遍历 existing 填充（从 agg 派生拿不到历史 id）`,
    )
  })
})

describe('E1 受限表条件表语义防回退（Property 29，复用不重造）', () => {
  it('自定义类别删空后受限行集为 []（而非 undefined）—— 走「进 _removed_table_keys」分支', () => {
    // 无叶子 + 无手工行 ⇒ 空数组，不是 undefined
    const rows = resolveRestrictedRows({
      prefill: { leaves: [], bucketDefs: DEFS, source: {} as never },
      manualMap: {},
      existingRows: [],
    })
    expect(Array.isArray(rows)).toBe(true)
    expect(rows).toHaveLength(0)
    // 🔴 关键：是 `[]` 而不是 undefined —— 两者在条件表语义里处置相反
    expect(rows).not.toBeUndefined()
  })

  it('新增再删空全部自定义类别后仍返回 []（新增功能不改变条件表语义）', () => {
    const custom = manualRow(customBucketKey('司法冻结'), 3, '司法冻结')
    const withCustom = resolveRestrictedRows({
      prefill: { leaves: [], bucketDefs: DEFS, source: {} as never },
      manualMap: {},
      existingRows: [custom],
    })
    expect(withCustom).toHaveLength(1)

    const afterDelete = resolveRestrictedRows({
      prefill: { leaves: [], bucketDefs: DEFS, source: {} as never },
      manualMap: {},
      existingRows: [],
    })
    expect(afterDelete).toHaveLength(0)
    expect(Array.isArray(afterDelete)).toBe(true)
  })
})

describe('E1 待归类面板分区（R8.4）', () => {
  const parent = { code: '1002', name: '银行存款', opening: 10, closing: 20, slot: 'bank', autoBucket: null }
  const detailDot = { code: '1002.07', name: '某专户', opening: 1, closing: 2, slot: 'bank', autoBucket: null }
  const detailDash = { code: '1002-07', name: '某专户', opening: 1, closing: 2, slot: 'bank', autoBucket: null }

  it('父科目行（无分隔符一级码）与真明细行分区正确', () => {
    const { parents, details } = partitionUnclassified([parent, detailDot, detailDash])
    expect(parents.map((p) => p.code)).toEqual(['1002'])
    expect(details.map((d) => d.code)).toEqual(['1002.07', '1002-07'])
  })

  it('分区不丢行、不重复（并集 == 输入）', () => {
    const input = [parent, detailDot, detailDash]
    const { parents, details } = partitionUnclassified(input)
    expect(parents.length + details.length).toBe(input.length)
    expect([...parents, ...details].map((x) => x.code).sort()).toEqual(
      input.map((x) => x.code).sort(),
    )
  })

  it('🔴 判据只看科目码形态不看金额（金额大的父科目 vs 小额明细）', () => {
    const bigParent = { ...parent, closing: 1e9 }
    const smallDetail = { ...detailDot, closing: 0.01 }
    const { parents, details } = partitionUnclassified([bigParent, smallDetail])
    expect(parents).toHaveLength(1)
    expect(details).toHaveLength(1)
  })

  it('空输入返回两个空数组（不抛）', () => {
    const { parents, details } = partitionUnclassified([])
    expect(parents).toEqual([])
    expect(details).toEqual([])
  })
})

describe('E1TabDisclosure 组件接线（源码级，判据落在函数体内）', () => {
  it('新增受限类别的 prompt → customBucketKey → nextRestrictedSeq 链在 addRestrictedRow 体内', () => {
    const body = fnBody(stripComments(readVue()), 'addRestrictedRow')
    expect(body, 'addRestrictedRow 函数体未截到（守卫自身缺陷）').not.toBe('')
    expect(body, '必须先 prompt 输名称再建行（平台铁律：动态行需命名）').toContain('ElMessageBox.prompt')
    expect(body).toContain('customBucketKey(')
    expect(body).toContain('nextRestrictedSeq(')
    expect(body).toContain('e1RestrictedSeqKey(')
    expect(body).toContain('e1RestrictedRowId(')
  })

  it('🔴 addRestrictedRow 体内不得出现朴素序号派生（length / max+1）', () => {
    const body = fnBody(stripComments(readVue()), 'addRestrictedRow')
    expect(body).not.toMatch(/\.length\s*\+\s*1/)
    expect(body).not.toMatch(/Math\.max\([^)]*\)\s*\+\s*1/)
  })

  it('计数器读回走 parseRestrictedSeq（在 loadRestricted 体内）', () => {
    const body = fnBody(stripComments(readVue()), 'loadRestricted')
    expect(body, 'loadRestricted 函数体未截到（守卫自身缺陷）').not.toBe('')
    expect(body).toContain('parseRestrictedSeq(')
    expect(body).toContain('e1RestrictedSeqKey(')
  })

  it('🔴 计数器随行落库：buildItems 体内往 items 推 seqKey', () => {
    const script = stripComments(scriptBlock(readVue()))
    // 落库函数名可能是 buildItems / persistAll 等，逐个尝试
    const candidates = ['buildItems', 'persistAll', 'buildPayload', 'saveAll']
    const bodies = candidates.map((n) => fnBody(script, n)).filter((b) => b !== '')
    expect(bodies.length, `落库函数未截到（尝试过 ${candidates.join('/')}）`).toBeGreaterThan(0)
    const joined = bodies.join('\n')
    expect(joined).toContain('e1RestrictedSeqKey(')
    expect(joined, '计数器必须作为一个 item 落库，否则刷新后序号回落').toMatch(
      /items\.push\(\s*\{[^}]*seqKey/,
    )
  })

  it('待归类分区在 script 里被真实消费（computed 实参区内调 partitionUnclassified）', () => {
    const script = stripComments(scriptBlock(readVue()))
    const init = constInitializer(script, 'restrictedPendingParts')
    expect(init, 'restrictedPendingParts 的初始化未截到（守卫自身缺陷）').not.toBe('')
    expect(init).toContain('partitionUnclassified(')
  })

  it('🔴 反向自检：符号只在 import 行出现时不算消费（判据是形态而非字符）', () => {
    const script = stripComments(scriptBlock(readVue()))
    // 构造一份「只有 import、函数体被掏空」的替身
    const fake = script.replace(
      /const\s+restrictedPendingParts\s*=[\s\S]*?\n\)/,
      'const restrictedPendingParts = computed(() => ({ parents: [], details: [] }))',
    )
    const init = constInitializer(fake, 'restrictedPendingParts')
    expect(init).not.toContain('partitionUnclassified(')
    // 而 import 行里 partitionUnclassified 仍在 —— 证明「全文 toContain」会被骗过
    expect(fake).toContain('partitionUnclassified')
  })

  it('模板两区分别渲染（父科目行 / 真明细行各有独立 data-testid）', () => {
    const tmpl = templateBlock(readVue())
    expect(tmpl).toContain('data-testid="pending-group-parents"')
    expect(tmpl).toContain('data-testid="pending-group-details"')
    expect(tmpl).toContain('restrictedPendingParts.parents')
    expect(tmpl).toContain('restrictedPendingParts.details')
  })

  it('「+ 新增受限类别」按钮在模板里可达且绑到 addRestrictedRow', () => {
    const tmpl = templateBlock(readVue())
    const m = /<el-button[^>]*@click="addRestrictedRow"[^>]*>([^<]*)<\/el-button>/.exec(tmpl)
    expect(m, '未找到绑定 addRestrictedRow 的按钮').not.toBeNull()
    expect(m![0]).toContain('v-if="!isReadonly"')
    expect(m![1]).toContain('新增受限类别')
  })
})

describe('E1 受限表金额控件（裁决：已是 WpAmountInput，只加正向断言）', () => {
  /**
   * 截②表区段（模板里的 `<h4>② 受限制的货币资金明细</h4>` 起，到「待归类科目」注释前）。
   *
   * 🔴 **必须先取 `<template>` 区** —— script 区的分节注释里也有
   * 「② 受限制的货币资金明细（两变体共用）」这行字样，从全文件 `indexOf` 会命中
   * 那条注释、截出一段没有任何模板标签的文本 ⇒ 「必须有 WpAmountInput」在**正确
   * 实现**上假红（本守卫首轮实测踩中）。
   */
  function restrictedSection(): string {
    const tmpl = templateBlock(readVue())
    const start = tmpl.indexOf('<h4 class="section-title">② 受限制的货币资金明细')
    expect(start, '未定位到②表区段（模板锚点变了？）').toBeGreaterThan(-1)
    const end = tmpl.indexOf('待归类科目', start)
    expect(end, '未定位到②表区段结尾').toBeGreaterThan(start)
    return tmpl.slice(start, end)
  }

  it('🔴 守卫自检：②表区段取的是模板不是 script 注释（否则金额断言会假红）', () => {
    const sec = restrictedSection()
    expect(sec, '②表区段里必须有表格标签').toContain('<el-table')
    expect(sec).toContain(':data="restrictedRows"')
    // 反向自检：从全文件 indexOf 会命中 script 分节注释，截出的段没有表格标签
    const naive = (() => {
      const src = readVue()
      const s = src.indexOf('② 受限制的货币资金明细')
      return src.slice(s, src.indexOf('待归类科目', s))
    })()
    expect(naive, '朴素取法应命中 script 注释（证明本自检非空转）').not.toContain('<el-table')
  })

  it('②表可编辑金额列用 WpAmountInput（期初/期末各一处）', () => {
    const sec = restrictedSection()
    expect((sec.match(/<WpAmountInput/g) ?? []).length).toBe(2)
  })

  it('🔴 ②表内不得出现 el-input-number（EP 2.13.6 无 formatter prop = 千分符空操作）', () => {
    const sec = stripComments(restrictedSection())
    expect(sec).not.toContain('el-input-number')
    expect(sec).not.toContain(':formatter')
  })

  it('②表只读金额走 displayPrefs.fmtAmount（不自造 toLocaleString）', () => {
    const sec = stripComments(restrictedSection())
    expect(sec).toContain('displayPrefs.fmtAmount(')
    expect(sec).not.toContain('toLocaleString')
    expect(sec).not.toContain('Intl.NumberFormat')
  })

  it('待归类两区金额只读且走 fmtAmount', () => {
    const src = readVue()
    const start = src.indexOf('data-testid="pending-group-details"')
    const end = src.indexOf('</details>', start)
    expect(start).toBeGreaterThan(-1)
    const sec = stripComments(src.slice(start, end))
    expect(sec).toContain('displayPrefs.fmtAmount(')
    expect(sec).not.toContain('el-input-number')
  })

  it('🔴 反向边界：文件里剩余的 el-input-number 只许是折算率（precision 4），不得替换成 WpAmountInput', () => {
    const src = stripComments(readVue())
    const tags = src.match(/<el-input-number[\s\S]*?\/>/g) ?? []
    expect(tags.length, '折算率控件应存在（扫描面非空自检）').toBeGreaterThan(0)
    for (const t of tags) {
      expect(/endRate|openRate/.test(t), `非折算率的 el-input-number：${t.slice(0, 80)}`).toBe(true)
      expect(t).toContain(':precision="4"')
    }
  })

  it('displayPrefs 走 setup 顶层 inject + store 回退（禁模块级命名导入 fmtAmount）', () => {
    const script = readVue()
    expect(script).toContain("import { DisplayPrefs_Key } from '../composables/displayPrefsKey'")
    expect(script).toMatch(/const\s+displayPrefs\s*=\s*inject\(DisplayPrefs_Key,\s*null\)\s*\?\?\s*useDisplayPrefsStore\(\)/)
    // 🔴 `fmtAmount` 是 store 成员，不是 @/stores/displayPrefs 的模块命名导出
    expect(script).not.toMatch(/import\s*\{[^}]*\bfmtAmount\b[^}]*\}\s*from\s*'@\/stores\/displayPrefs'/)
  })
})

describe('守卫自身自检（防空转）', () => {
  it('stripComments 真的剥掉了注释里的反例字样', () => {
    const raw = readTs()
    // 原文注释里写着「朴素实现 `max(现有) + 1` 必被守卫打红」
    expect(raw).toContain('max(现有)')
    expect(stripComments(raw)).not.toContain('max(现有)')
  })

  it('fnBody 能跳过参数列表里的内联类型字面量', () => {
    const fixture = `
export function demo(opts: { a: string; b: number }): { ok: boolean } {
  const x = opts.a
  return { ok: true }
}`
    const body = fnBody(fixture, 'demo')
    expect(body).toContain('const x = opts.a')
    expect(body).not.toContain('a: string')
  })

  it('fnBody 对多行参数列表同样有效（真实签名形态）', () => {
    const fixture = `
export function demo(
  rows: readonly { id: string }[],
  stored: unknown,
): number {
  return 1
}`
    const body = fnBody(fixture, 'demo')
    expect(body).toContain('return 1')
    expect(body).not.toContain('rows: readonly')
  })

  it('fnBody 对不存在的函数返回空串（不静默命中别的函数）', () => {
    expect(fnBody(readTs(), 'thisFunctionDoesNotExist')).toBe('')
  })

  it('templateBlock / scriptBlock 分区有效（模板字样不进 script 判据）', () => {
    const src = readVue()
    const tmpl = templateBlock(src)
    const script = scriptBlock(src)
    expect(tmpl).toContain('<el-table')
    expect(script).not.toContain('data-testid="pending-group-parents"')
    expect(script).toContain('import')
  })

  /**
   * 抽「从某模块具名导入的符号名」。
   *
   * 🔴 **必须从 `from '模块'` 反向找它自己的 `{`，再用花括号配对取内容** ——
   * 正则 `import\s*\{([\s\S]*?)\}\s*from\s*'模块'` 的非贪婪段会从**文件里第一个**
   * `import {` 一路吃到目标模块的 `}`，把中间十几个 import 块全卷进来（首轮实测抽出
   * 28 个「缺失符号」，其中 `ref`/`computed` 全是别的模块的）⇒ 断言以假红形态失败。
   */
  function namedImportsFrom(src: string, moduleSpec: string): string[] {
    const fromIdx = src.indexOf(`} from '${moduleSpec}'`)
    if (fromIdx < 0) return []
    // 从 `}` 反向做花括号配对，找到与之匹配的 `{`
    let depth = 0
    let open = -1
    for (let i = fromIdx; i >= 0; i--) {
      const c = src[i]
      if (c === '}') depth++
      else if (c === '{') {
        depth--
        if (depth === 0) {
          open = i
          break
        }
      }
    }
    if (open < 0) return []
    return stripComments(src.slice(open + 1, fromIdx))
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s !== '')
      // 类型导入被编译期擦除，不参与运行时 link
      .filter((s) => !s.startsWith('type '))
      .map((s) => (s.includes(' as ') ? s.split(' as ')[0].trim() : s))
  }

  it('🔴 守卫自检：import 抽取器只取目标模块的符号（不卷入相邻 import 块）', () => {
    const src = readVue()
    const names = namedImportsFrom(src, '../composables/e1RestrictedScope')
    expect(names.length).toBeGreaterThan(5)
    // 相邻模块的符号不得混入
    for (const alien of ['ref', 'computed', 'inject', 'watch', 'e1MainRows', 'computeE1Consistency']) {
      expect(names, `抽取器把 ${alien} 误当成 e1RestrictedScope 的导入`).not.toContain(alien)
    }
    // 目标模块自己的符号必须在
    for (const own of ['nextRestrictedSeq', 'parseRestrictedSeq', 'partitionUnclassified']) {
      expect(names).toContain(own)
    }
    // 反向自检：朴素非贪婪正则确实会卷入别的模块（证明本自检非空转）
    const naive = /import\s*\{([\s\S]*?)\}\s*from\s*'\.\.\/composables\/e1RestrictedScope'/.exec(src)
    expect(naive).not.toBeNull()
    expect(naive![1], '朴素正则应卷入相邻 import（否则本自检无意义）').toContain('from ')
  })

  it('🔴 ESM link 自检：组件从 e1RestrictedScope 导入的每个具名符号都必须真实存在', async () => {
    const mod = (await import('../e1RestrictedScope')) as Record<string, unknown>
    const names = namedImportsFrom(readVue(), '../composables/e1RestrictedScope')

    expect(names.length, 'import 名单为空（守卫自身缺陷）').toBeGreaterThan(5)
    const missing = names.filter((n) => !(n in mod))
    expect(
      missing,
      `组件导入了不存在的具名导出 ${JSON.stringify(missing)} —— 浏览器会抛 ` +
        `"does not provide an export named"，而 get_diagnostics / vitest / Vite transform 全绿`,
    ).toEqual([])
  })

  it('🔴 反向自检：link 判据对不存在的符号确实会打红', async () => {
    const mod = (await import('../e1RestrictedScope')) as Record<string, unknown>
    expect('parseRestrictedSeq' in mod).toBe(true)
    expect('thisExportDoesNotExist' in mod).toBe(false)
  })
})
