/**
 * E1 受限资金 L2 链路（E1-3 逐户归集）守卫 —— E-cycle spec Task 14。
 *
 * Property 26：两条链路并存不互相覆盖
 * Property 38：L2 受限原因不进 ②表列（只落 `_note_texts`）
 *
 * 判据取向：
 * - **纯函数层**用真实数据形状断言（不挂载组件）
 * - **接线层**读 `E1TabDisclosure.vue` 源码断言三段链（解析 → 汇总 → 勾稽入参）
 * - 每条关键判据都配反向自检，防判据空转
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  E1_BANK_DETAIL_ROWS_KEY,
  buildRestrictedReasonText,
  matchNatureToBucket,
  parseBankDetailRowsForL2,
  resolveRestrictedFromAccounts,
  summarizeRestrictedFromAccounts,
  type E1BankDetailRowLike,
  type E1RestrictedBucketDef,
} from '../e1RestrictedScope'
import { computeE1Consistency, type E1ConsistencyInput } from '../e1DisclosureConsistency'

// ─── 仓库根定位（双哨兵，禁写死回退级数）─────────────────────────────────────
function repoRoot(): string {
  let dir = resolve(__dirname)
  for (let i = 0; i < 12; i += 1) {
    const a = resolve(dir, 'backend/app/services/four_table/e1_restricted_buckets.py')
    const b = resolve(dir, '.kiro/steering/memory.md')
    try {
      readFileSync(a)
      readFileSync(b)
      return dir
    } catch {
      dir = resolve(dir, '..')
    }
  }
  throw new Error('repoRoot 未找到（双哨兵均不命中）')
}
const ROOT = repoRoot()

function readSrc(rel: string): string {
  return readFileSync(resolve(ROOT, rel), 'utf-8').replace(/\r\n/g, '\n')
}

const TAB = 'audit-platform/frontend/src/components/workpaper/e1/E1TabDisclosure.vue'
const SCOPE = 'audit-platform/frontend/src/components/workpaper/composables/e1RestrictedScope.ts'
const ENGINE =
  'audit-platform/frontend/src/components/workpaper/composables/e1DisclosureConsistency.ts'
const BUCKETS_PY = 'backend/app/services/four_table/e1_restricted_buckets.py'

/** 取某函数体（圆括号配对跳参数列表 + 花括号配对，含语句特征筛选）。 */
function fnBody(src: string, name: string): string {
  const decl = new RegExp(`(?:export\\s+)?(?:async\\s+function|function)\\s+${name}\\s*\\(`)
  const m = decl.exec(src)
  if (!m) throw new Error(`未找到函数声明: ${name}`)
  // 跳参数列表
  let i = src.indexOf('(', m.index)
  let depth = 0
  for (; i < src.length; i += 1) {
    if (src[i] === '(') depth += 1
    else if (src[i] === ')') {
      depth -= 1
      if (depth === 0) {
        i += 1
        break
      }
    }
  }
  // 找第一个含语句特征的花括号块
  for (let j = i; j < src.length; j += 1) {
    if (src[j] !== '{') continue
    let d = 0
    let end = -1
    for (let k = j; k < src.length; k += 1) {
      if (src[k] === '{') d += 1
      else if (src[k] === '}') {
        d -= 1
        if (d === 0) {
          end = k
          break
        }
      }
    }
    if (end < 0) break
    const body = src.slice(j + 1, end)
    if (/\b(return|const|let|for|if|throw|await)\b/.test(body)) return body
    j = end
  }
  throw new Error(`未截到函数体: ${name}`)
}

/** 取 `const NAME = computed(...)` 或 `const NAME = expr` 的值表达式（支持块体与表达式体）。 */
function constValue(src: string, name: string): string {
  const re = new RegExp(`const\\s+${name}\\s*(?::[^=]+)?=\\s*`)
  const m = re.exec(src)
  if (!m) throw new Error(`未找到常量: ${name}`)
  let i = m.index + m[0].length
  // 若是 computed(...) / computed<T>(...) / 函数调用，做圆括号配对。
  // 🔴 必须容忍**泛型实参** `computed<E1BankDetailRowLike[]>(...)` —— 只写
  //    `/^\w+\s*\(/` 会因为 `computed` 后面紧跟 `<` 而不匹配，落到「取到行尾」
  //    的兜底分支 ⇒ 截出 `computed<T>(() =>` 这半句，后续 toContain 断言在
  //    残缺文本上求值 = **在正确实现上打红**（同族：「第一个 `{` 命中类型注解」）。
  if (src[i] === '(' || /^[A-Za-z_$][\w$]*\s*(?:<[^(]*>\s*)?\(/.test(src.slice(i, i + 80))) {
    const open = src.indexOf('(', i)
    let d = 0
    for (let k = open; k < src.length; k += 1) {
      if (src[k] === '(') d += 1
      else if (src[k] === ')') {
        d -= 1
        if (d === 0) return src.slice(open + 1, k)
      }
    }
  }
  // 否则取到行尾
  const nl = src.indexOf('\n', i)
  return src.slice(i, nl < 0 ? src.length : nl)
}

// ─── 真实桶定义（镜像后端声明序 + docx 展示序）────────────────────────────────
// 🔴 声明序 = 匹配优先级（后端 E1_RESTRICTED_BUCKETS 顺序）；displayOrder = docx 行序。
const DEFS: E1RestrictedBucketDef[] = [
  { key: 'letter_of_credit', label: '信用证保证金', isPlatformExtra: false, displayOrder: 1 },
  { key: 'bank_acceptance', label: '银行承兑汇票保证金', isPlatformExtra: false, displayOrder: 0 },
  { key: 'performance_bond', label: '履约保证金', isPlatformExtra: false, displayOrder: 2 },
  { key: 'overseas_frozen', label: '存放在境外且资金汇回受限制的款项', isPlatformExtra: false, displayOrder: 4 },
  { key: 'pledged_deposit', label: '质押、冻结的定期存款', isPlatformExtra: false, displayOrder: 3 },
  {
    key: 'statutory_reserve',
    label: '金融企业法定存款准备金或备付金',
    isPlatformExtra: false,
    displayOrder: 5,
  },
  { key: 'other', label: '其他受限资金', isPlatformExtra: true, displayOrder: 99 },
]

function row(p: Partial<E1BankDetailRowLike>): E1BankDetailRowLike {
  return {
    accountType: '',
    restrictedAmount: 0,
    restrictedReason: '',
    opening: 0,
    accountNo: '',
    bankName: '',
    ...p,
  }
}

// ════════════════════════════════════════════════════════════════════════════
describe('E1 L2 判据基础设施（先证明判据本身有效）', () => {
  it('仓库根双哨兵命中，四个源文件可读且非空', () => {
    for (const rel of [TAB, SCOPE, ENGINE, BUCKETS_PY]) {
      const src = readSrc(rel)
      expect(src.length, `${rel} 应非空`).toBeGreaterThan(1000)
    }
  })

  it('fnBody 能跳过返回类型注解（fixture 自检）', () => {
    const fixture = `
export function f(p: { a: string }): Promise<{ ok: boolean }> {
  const x = 1
  return x
}
`
    const body = fnBody(fixture, 'f')
    expect(body).toContain('const x = 1')
    expect(body).not.toContain('ok: boolean')
  })

  it('constValue 支持表达式体 computed（fixture 自检）', () => {
    const fixture = `const a = computed(() => foo(bar.value))\n`
    expect(constValue(fixture, 'a')).toContain('foo(bar.value)')
  })

  it('DEFS 复现后端两序分离的形态（声明序 ≠ 展示序）', () => {
    const declOrder = DEFS.map((d) => d.key)
    const dispOrder = [...DEFS].sort((a, b) => (a.displayOrder ?? 99) - (b.displayOrder ?? 99)).map((d) => d.key)
    expect(declOrder).not.toEqual(dispOrder)
    // 后端真源交叉锁死：这两个 key 必须都在后端声明里
    const py = readSrc(BUCKETS_PY)
    for (const k of ['letter_of_credit', 'bank_acceptance', 'statutory_reserve']) {
      expect(py, `后端应声明桶 ${k}`).toContain(k)
    }
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 26 之一：L2 归集口径（源模板 SUMIF）', () => {
  it('按「账户性质·主要用途」匹配桶，取 restrictedAmount 汇总', () => {
    const res = resolveRestrictedFromAccounts({
      rows: [
        row({ accountType: '银行承兑汇票保证金', restrictedAmount: 100, accountNo: 'A1' }),
        row({ accountType: '银行承兑汇票保证金', restrictedAmount: 50, accountNo: 'A2' }),
        row({ accountType: '信用证保证金', restrictedAmount: 30, accountNo: 'A3' }),
      ],
      bucketDefs: DEFS,
    })
    const byKey = new Map(res.rows.map((r) => [r.bucketKey, r]))
    expect(byKey.get('bank_acceptance')!.endingAmount).toBe(150)
    expect(byKey.get('letter_of_credit')!.endingAmount).toBe(30)
    expect(res.totals.ending).toBe(180)
  })

  it('只收 restrictedAmount !== 0 的行（未填受限金额的账户不算受限资金）', () => {
    const res = resolveRestrictedFromAccounts({
      rows: [
        row({ accountType: '银行承兑汇票保证金', restrictedAmount: 0, accountNo: 'A1' }),
        row({ accountType: '履约保证金', restrictedAmount: 0 }),
      ],
      bucketDefs: DEFS,
    })
    expect(res.rows).toEqual([])
    expect(res.unmatched).toEqual([])
    expect(res.totals.ending).toBe(0)
  })

  it('性质文本匹配不上 → 进 unmatched，不落兜底桶（不臆造归属）', () => {
    const res = resolveRestrictedFromAccounts({
      rows: [row({ accountType: '某种说不清的用途', restrictedAmount: 77, accountNo: 'A9' })],
      bucketDefs: DEFS,
    })
    expect(res.rows).toEqual([])
    expect(res.unmatched).toHaveLength(1)
    expect(res.unmatched[0]).toMatchObject({ amount: 77, account: 'A9' })
    // 反向自检：兜底桶 key 不得出现在任何行里
    expect(res.rows.some((r) => r.bucketKey === 'other')).toBe(false)
  })

  it('L2 行序按 displayOrder（docx 序）不按声明序', () => {
    const res = resolveRestrictedFromAccounts({
      rows: [
        row({ accountType: '信用证保证金', restrictedAmount: 10 }),
        row({ accountType: '银行承兑汇票保证金', restrictedAmount: 20 }),
        row({ accountType: '质押、冻结的定期存款', restrictedAmount: 30 }),
        row({ accountType: '存放在境外且资金汇回受限制的款项', restrictedAmount: 40 }),
      ],
      bucketDefs: DEFS,
    })
    expect(res.rows.map((r) => r.bucketKey)).toEqual([
      'bank_acceptance',
      'letter_of_credit',
      'pledged_deposit',
      'overseas_frozen',
    ])
  })

  it('matchNatureToBucket 沿匹配优先级序（宽标签不抢走具体项）', () => {
    // 「信用证保证金」同时含「保证金」，声明序里它在前 ⇒ 必须命中 letter_of_credit
    expect(matchNatureToBucket('信用证保证金', DEFS)).toBe('letter_of_credit')
    // 平台补充桶不参与自动匹配
    expect(matchNatureToBucket('其他受限资金', DEFS)).toBeNull()
    // 空文本不匹配
    expect(matchNatureToBucket('', DEFS)).toBeNull()
    expect(matchNatureToBucket('   ', DEFS)).toBeNull()
  })

  it('性质文本归一：忽略空白与全/半角括号', () => {
    expect(matchNatureToBucket(' 银行承兑汇票保证金 ', DEFS)).toBe('bank_acceptance')
    expect(matchNatureToBucket('履约保证金（工程）', DEFS)).toBe('performance_bond')
  })

  it('桶 label 只从 bucketDefs 取；未下发时退化显示 key 且全部落 unmatched', () => {
    const res = resolveRestrictedFromAccounts({
      rows: [row({ accountType: '银行承兑汇票保证金', restrictedAmount: 100 })],
      bucketDefs: [],
    })
    expect(res.rows).toEqual([])
    expect(res.unmatched).toHaveLength(1)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('summarizeRestrictedFromAccounts：空态返 null 不返 0', () => {
  it('无任何受限行 → ending/opening 均为 null（与「确实为 0」可区分）', () => {
    const s = summarizeRestrictedFromAccounts([], DEFS)
    expect(s.ending).toBeNull()
    expect(s.opening).toBeNull()
    expect(s.rows).toEqual([])
    expect(s.reasonText).toBe('')
  })

  it('有受限行 → 返数值（含未匹配行金额，避免假一致）', () => {
    const s = summarizeRestrictedFromAccounts(
      [
        row({ accountType: '银行承兑汇票保证金', restrictedAmount: 100 }),
        row({ accountType: '说不清', restrictedAmount: 23 }),
      ],
      DEFS,
    )
    expect(s.ending).toBe(123)
    expect(s.unmatched).toHaveLength(1)
  })

  it('未匹配金额若不计入 L2 合计会产出假一致（反向自检）', () => {
    const rows = [
      row({ accountType: '银行承兑汇票保证金', restrictedAmount: 100 }),
      row({ accountType: '说不清', restrictedAmount: 23 }),
    ]
    const s = summarizeRestrictedFromAccounts(rows, DEFS)
    const naive = resolveRestrictedFromAccounts({ rows, bucketDefs: DEFS }).totals.ending
    expect(naive).toBe(100)
    expect(s.ending).not.toBe(naive)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('parseBankDetailRowsForL2：容错解析', () => {
  it('非 JSON / 非数组 / 空串一律返 []（不抛）', () => {
    for (const raw of ['', '   ', 'not json', '{}', '123', null, undefined, 42]) {
      expect(parseBankDetailRowsForL2(raw as unknown)).toEqual([])
    }
  })

  it('真实形状解析出 L2 需要的六个字段', () => {
    const raw = JSON.stringify([
      {
        id: 'x',
        accountType: '银行承兑汇票保证金',
        restrictedAmount: 100,
        restrictedReason: '开票保证',
        opening: 5,
        accountNo: '622',
        bankName: '工行',
        note: '无关字段',
      },
    ])
    const rows = parseBankDetailRowsForL2(raw)
    expect(rows).toHaveLength(1)
    expect(rows[0]).toEqual({
      accountType: '银行承兑汇票保证金',
      restrictedAmount: 100,
      restrictedReason: '开票保证',
      opening: 5,
      accountNo: '622',
      bankName: '工行',
    })
  })

  it('持久化键与 useE1BankDetail.STORAGE_KEY 逐字一致（交叉锁死）', () => {
    const bank = readSrc(
      'audit-platform/frontend/src/components/workpaper/composables/useE1BankDetail.ts',
    )
    const m = /const\s+STORAGE_KEY\s*=\s*'([^']+)'/.exec(bank)
    expect(m, 'useE1BankDetail 应声明 STORAGE_KEY').toBeTruthy()
    expect(E1_BANK_DETAIL_ROWS_KEY).toBe(m![1])
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 38：受限原因落 _note_texts，不进 ②表列', () => {
  it('buildRestrictedReasonText 按类别前缀拼接，去重', () => {
    const res = resolveRestrictedFromAccounts({
      rows: [
        row({ accountType: '银行承兑汇票保证金', restrictedAmount: 10, restrictedReason: '开票保证' }),
        row({ accountType: '银行承兑汇票保证金', restrictedAmount: 20, restrictedReason: '开票保证' }),
        row({ accountType: '履约保证金', restrictedAmount: 5, restrictedReason: '工程履约' }),
      ],
      bucketDefs: DEFS,
    })
    const text = buildRestrictedReasonText(res.rows)
    expect(text).toContain('银行承兑汇票保证金：开票保证')
    expect(text).toContain('履约保证金：工程履约')
    // 去重：同一原因只出现一次
    expect(text.match(/开票保证/g)).toHaveLength(1)
  })

  it('无原因时返空串（不产出「类别：」空壳句）', () => {
    const res = resolveRestrictedFromAccounts({
      rows: [row({ accountType: '银行承兑汇票保证金', restrictedAmount: 10 })],
      bucketDefs: DEFS,
    })
    expect(buildRestrictedReasonText(res.rows)).toBe('')
  })

  it('L2 行类型不含可作②表第 4 列的标量字段（reasons 是数组、accounts 是数组）', () => {
    const res = resolveRestrictedFromAccounts({
      rows: [row({ accountType: '履约保证金', restrictedAmount: 5, restrictedReason: 'r' })],
      bucketDefs: DEFS,
    })
    const r = res.rows[0]
    expect(Array.isArray(r.reasons)).toBe(true)
    expect(Array.isArray(r.accounts)).toBe(true)
    // 不得出现单值 reason 字段（那会诱导直接塞进②表列）
    expect('reason' in (r as unknown as Record<string, unknown>)).toBe(false)
  })

  it('②表列定义仍为 3 列（既有契约不得被 L2 改动）', () => {
    const map = readSrc(
      'audit-platform/frontend/src/components/workpaper/composables/e1NoteSectionMap.ts',
    )
    // 受限表列 key 恒为 label / end_amount / prior_amount，且不得出现 reason 列
    expect(map).toMatch(/end_amount/)
    expect(map).toMatch(/prior_amount/)
    expect(map).not.toMatch(/key:\s*'reason'/)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 26 之二：L1/L2 对照勾稽（warn 级，不是 error）', () => {
  function baseInput(over: Partial<E1ConsistencyInput> = {}): E1ConsistencyInput {
    return {
      variant: 'soe',
      mainRows: [
        { key: 'cash', label: '现金', endingAmount: 100, openingAmount: 90 },
        { key: 'total', label: '合计', endingAmount: 100, openingAmount: 90, isTotal: true },
      ],
      restrictedRows: [{ label: '银行承兑汇票保证金', endingAmount: 150, openingAmount: 0 }],
      reportEnding: 100,
      reportOpening: 90,
      ...over,
    }
  }

  /**
   * 🔴 按 label **前缀**定位而不是关键词 `'L1'` —— 真实 label 是
   * `受限两口径对比（期末）`，`L1` 只出现在 `rule` 说明文本里。首版按 `'L1'` 找
   * 恒返 undefined ⇒ 四条断言全在 undefined 上求值（表现像「引擎没产出条目」，
   * 实为守卫判据写错）。同族：memory 已记「按名字找位置要落到真实字面」。
   */
  const L2_LABEL_PREFIX = '受限两口径对比'
  const findL2 = (out: ReturnType<typeof computeE1Consistency>, period: '期末' | '期初') =>
    out.find((r) => r.label === `${L2_LABEL_PREFIX}（${period}）`)

  it('引擎确实产出该条目（判据自检：label 字面与实现一致）', () => {
    const out = computeE1Consistency(baseInput({ restrictedL2Ending: 150 }))
    expect(findL2(out, '期末'), `未找到 label 以「${L2_LABEL_PREFIX}」开头的条目`).toBeTruthy()
    // 反向自检：`L1` 只在 rule 里，不在 label 里（防判据退回按 'L1' 找）
    expect(out.find((r) => r.label.includes('L1'))).toBeUndefined()
    expect(findL2(out, '期末')!.rule).toContain('L1')
  })

  it('L2 未提供（null）→ 该条 skip，不误报', () => {
    const out = computeE1Consistency(baseInput({ restrictedL2Ending: null }))
    const c = findL2(out, '期末')
    expect(c, '应产出 L1/L2 对照条目').toBeTruthy()
    expect(c!.level).toBe('skip')
  })

  it('L1 == L2 → ok', () => {
    const out = computeE1Consistency(baseInput({ restrictedL2Ending: 150 }))
    const c = findL2(out, '期末')!
    expect(c.level).toBe('ok')
    expect(c.diff).toBe(0)
  })

  it('L1 != L2 → warn（审计判断，不是错报）', () => {
    const out = computeE1Consistency(baseInput({ restrictedL2Ending: 120 }))
    const c = findL2(out, '期末')!
    expect(c.level).toBe('warn')
    expect(c.diff).toBe(30)
  })

  it('warn 级不得进错报推送（只推 error）', () => {
    const engine = readSrc(ENGINE)
    const body = fnBody(engine, 'buildE1MisstatementPayload')
    expect(body).toMatch(/level\s*!==\s*'error'/)
  })

  it('L1/L2 对照条目在 L1 无行时也不误报（restrictedRows 为空 → L1 为 null → skip）', () => {
    const out = computeE1Consistency(
      baseInput({ restrictedRows: [], restrictedL2Ending: 150 }),
    )
    const c = findL2(out, '期末')!
    expect(c.level).toBe('skip')
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('判据自检：constValue 必须跳过泛型实参', () => {
  // 🔴 `computed<T[]>(() => f(x))` 的第一个 `<` 后是**类型实参**不是值表达式。
  //    首版 helper 按「标识符后紧跟 (」定位，被 `computed<E1BankDetailRowLike[]>(`
  //    骗到（`<` 出现在 `(` 之前）→ 截出来的是类型文本 → 断言在无关文本上求值
  //    （报错形如 expected 'computed<E1BankDetailRowLike[]>(() =>' to contain 'x'）。
  //    同族已记：「取声明后第一个 `{` 会命中返回类型注解」。
  it('泛型调用与非泛型调用都能取到实参', () => {
    const withGeneric = 'const a = computed<Foo[]>(() => parse(bar.get(KEY)?.remark))\n'
    const withoutGeneric = 'const b = computed(() => parse(bar.get(KEY)?.remark))\n'
    for (const src of [withGeneric, withoutGeneric]) {
      const v = constValue(src, src.includes('const a') ? 'a' : 'b')
      expect(v).toContain('parse')
      expect(v).toContain('KEY')
      expect(v).not.toContain('Foo[]')
    }
  })

  it('复现旧行为：正则闸被泛型挡掉 → 落入非调用分支（反向自检）', () => {
    const src = 'const a = computed<Foo[]>(() => parse(x))\n'
    // 🔴 首版 helper 的调用判定闸是 `^ident\s*\(` —— 对 `computed<Foo[]>(` **不成立**
    //    （标识符后紧跟的是 `<` 不是 `(`）⇒ 走 else 分支（按语句结尾截）⇒ 截出来是
    //    含类型文本的整段（报错形如 expected 'computed<E1BankDetailRowLike[]>(() =>'
    //    to contain 'parseBankDetailRowsForL2'）。这才是当时真实的失效机理 ——
    //    不是 indexOf('(') 定位错（它恰好也能命中正确的左括号）。
    const m = /const\s+a\s*=\s*/.exec(src)!
    const i = m.index + m[0].length
    const naiveGate = /^[A-Za-z_$][\w$]*\s*\(/.test(src.slice(i, i + 40))
    expect(naiveGate, '首版闸门对泛型调用必须为 false（这就是缺陷根因）').toBe(false)
    // 修好的闸门放宽为 `^ident\s*[<(]`
    const fixedGate = /^[A-Za-z_$][\w$]*\s*[<(]/.test(src.slice(i, i + 40))
    expect(fixedGate).toBe(true)
    // 且最终取到的是值表达式而非类型文本
    expect(constValue(src, 'a')).toBe('() => parse(x)')
    expect(constValue(src, 'a')).not.toContain('Foo[]')
  })})

// ════════════════════════════════════════════════════════════════════════════
describe('接线：三段链（解析 → 汇总 → 勾稽入参）', () => {
  const tab = readSrc(TAB)

  it('组件从 E1_BANK_DETAIL_ROWS_KEY 读 remark 并解析', () => {
    const v = constValue(tab, 'bankDetailRowsForL2')
    expect(v).toContain('parseBankDetailRowsForL2')
    expect(v).toContain('E1_BANK_DETAIL_ROWS_KEY')
  })

  it('组件调 summarizeRestrictedFromAccounts 并传 bucketDefs（label 真源）', () => {
    const v = constValue(tab, 'restrictedL2')
    expect(v).toContain('summarizeRestrictedFromAccounts')
    expect(v).toMatch(/bucketDefs/)
  })

  it('勾稽入参真的收到 L2 合计（否则整条链是 dead output）', () => {
    const v = constValue(tab, 'consistencyResults')
    // 🔴 必须**逐字段**断言实参真的读了 `restrictedL2.value.X` ——
    //    首版写成 `toMatch(/restrictedL2Ending\s*:/)` + `toMatch(/restrictedL2\.value/)`
    //    两条宽正则，把 `restrictedL2Ending: null` 这个**最核心的 dead output 变异**
    //    放过了（键名还在、且另一行 `restrictedL2Opening: restrictedL2.value.opening`
    //    仍满足第二条）。变异检验 M6 首轮 GREEN 即此。
    //    同族已记：「只断言标识符存在抓不住把值换成常量」。
    expect(v).toMatch(/restrictedL2Ending\s*:\s*restrictedL2\.value\.ending\b/)
    expect(v).toMatch(/restrictedL2Opening\s*:\s*restrictedL2\.value\.opening\b/)
    // 反向自检：宽判据在「值被换成 null」时不打红 —— 证明收紧是必要的
    const weakened = v.replace(/restrictedL2Ending\s*:\s*restrictedL2\.value\.ending/, 'restrictedL2Ending: null')
    expect(/restrictedL2Ending\s*:/.test(weakened), '宽判据放过了 dead output 变异').toBe(true)
    expect(/restrictedL2Ending\s*:\s*restrictedL2\.value\.ending\b/.test(weakened)).toBe(false)
  })

  it('L2 不覆盖 L1：组件仍用 restrictedRows 产出②表载荷', () => {
    // ②表推送侧必须仍是 L1 的 restrictedRows（L2 只作对照与文本）
    expect(tab).toMatch(/restrictedRows:\s*restrictedRows\.value\.map/)
    // 反向自检：不得出现「用 L2 覆盖 L1」的形态
    expect(tab).not.toMatch(/restrictedRows\.value\s*=\s*restrictedL2/)
    expect(tab).not.toMatch(/restrictedL2\.value\.rows\s*\.map\([^)]*\)\s*:\s*restrictedRows/)
  })

  it('两条链路在 scope 源码里都以独立导出存在（不是二选一）', () => {
    const scope = readSrc(SCOPE)
    expect(scope).toMatch(/export function resolveRestrictedRows/)
    expect(scope).toMatch(/export function resolveRestrictedFromAccounts/)
    // 不得出现「若 L2 有数据则跳过 L1」这类互斥分支
    expect(scope).not.toMatch(/if\s*\(\s*l2[\w.]*\s*\)\s*return\s+\[\]/i)
  })
})
