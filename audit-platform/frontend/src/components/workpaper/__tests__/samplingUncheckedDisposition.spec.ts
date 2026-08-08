/**
 * 未检查样本处置 — 守卫
 *
 * spec: sampling-evaluation-and-governance-closure
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6, 11.2, 11.3
 * Properties: Property 8, Property 9, Property 10
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  UNCHECKED_DISPOSITION_HINTS,
  UNCHECKED_DISPOSITION_LABELS,
  UNCHECKED_DISPOSITION_MODES,
  applyAlternativeTreatment,
  applyDeviationTreatment,
  applyUncheckedDisposition,
  buildUncheckedDispositionPayload,
  countTreatedAsDeviation,
  isUnchecked,
  resolveUncheckedDisposition,
  type UncheckedDispositionMap,
} from '../composables/samplingUncheckedDisposition'
import { projectMisstatement, type SampledVoucher } from '../composables/useSamplingAlgorithms'

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    const a = path.join(dir, 'backend', 'app', 'routers', 'voucher_sampling.py')
    const b = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('未找到仓库根（双哨兵均未命中）')
}

const sample = (over: Partial<SampledVoucher> = {}): SampledVoucher => ({
  voucherNo: 'V-1',
  voucherDate: '2025-06-01',
  summary: null,
  debitAmount: '1000.00',
  creditAmount: null,
  accountCode: '1122',
  accountName: null,
  counterpartAccount: null,
  voucherType: null,
  accountingPeriod: 6,
  checkResult: '',
  abnormal: false,
  remark: '',
  selected: true,
  phase: 'final',
  editTrail: [],
  ...over,
})

// ─── Property 8：未处置即阻断；无未检查样本即零阻断 ──────────────────────────

describe('Property 8：未检查样本处置门控', () => {
  it('无未检查样本 → 四个集合全空（R3.6 零回归）', () => {
    const r = resolveUncheckedDisposition(
      [sample({ checkResult: 'Y' }), sample({ voucherNo: 'V-2', checkResult: 'N' })],
      {},
    )
    expect(r).toEqual({ pending: [], missingNote: [], asDeviation: [], alternative: [] })
  })

  it('未检查且未选处置 → 进 pending', () => {
    const r = resolveUncheckedDisposition([sample()], {})
    expect(r.pending).toEqual(['V-1'])
  })

  it('非法 mode 视为未选（两种处置的审计后果完全不同，不猜）', () => {
    const bad = { 'V-1': { mode: 'skip' } } as unknown as UncheckedDispositionMap
    expect(resolveUncheckedDisposition([sample()], bad).pending).toEqual(['V-1'])
  })

  it('已选视同偏差 → 进 asDeviation，不再 pending', () => {
    const map: UncheckedDispositionMap = { 'V-1': { mode: 'treated_as_deviation' } }
    const r = resolveUncheckedDisposition([sample()], map)
    expect(r.pending).toEqual([])
    expect(r.asDeviation.map(v => v.voucherNo)).toEqual(['V-1'])
  })

  it('isUnchecked 只认空 checkResult', () => {
    expect(isUnchecked(sample({ checkResult: '' }))).toBe(true)
    expect(isUnchecked(sample({ checkResult: 'Y' }))).toBe(false)
    expect(isUnchecked(sample({ checkResult: 'N' }))).toBe(false)
    expect(isUnchecked(sample({ checkResult: '异常' }))).toBe(false)
  })
})

// ─── Property 10：替代程序须有说明 ───────────────────────────────────────────

describe('Property 10：替代程序说明必填', () => {
  it.each([[undefined], [null], [''], ['   ']])('说明为 %s → 进 missingNote', note => {
    const map: UncheckedDispositionMap = {
      'V-1': { mode: 'alternative_performed', note: note as string },
    }
    const r = resolveUncheckedDisposition([sample()], map)
    expect(r.missingNote).toEqual(['V-1'])
    expect(r.alternative).toHaveLength(1)
  })

  it('说明非空 → 不阻断', () => {
    const map: UncheckedDispositionMap = {
      'V-1': { mode: 'alternative_performed', note: '已核对银行流水与合同' },
    }
    expect(resolveUncheckedDisposition([sample()], map).missingNote).toEqual([])
  })

  it('视同偏差不要求说明', () => {
    const map: UncheckedDispositionMap = { 'V-1': { mode: 'treated_as_deviation' } }
    expect(resolveUncheckedDisposition([sample()], map).missingNote).toEqual([])
  })
})

// ─── Property 9：视同偏差按 100% 污染率计入 ──────────────────────────────────

describe('Property 9：视同偏差按账面金额全额计入推断', () => {
  it('改写后 actualMisstatement == 账面金额且 checkResult 变 N', () => {
    const map: UncheckedDispositionMap = { 'V-1': { mode: 'treated_as_deviation' } }
    const [out] = applyDeviationTreatment([sample({ debitAmount: '1234.56' })], map)
    expect(out.actualMisstatement).toBe('1234.56')
    expect(out.checkResult).toBe('N')
  })

  it('账面金额取借贷绝对值较大者', () => {
    const map: UncheckedDispositionMap = { 'V-1': { mode: 'treated_as_deviation' } }
    const [out] = applyDeviationTreatment(
      [sample({ debitAmount: '100.00', creditAmount: '-900.00' })],
      map,
    )
    expect(out.actualMisstatement).toBe('900.00')
  })

  it('不改原样本（评价派生 ≠ 审计师录入值，必须可回退）', () => {
    const original = sample({ actualMisstatement: '0.00' })
    const map: UncheckedDispositionMap = { 'V-1': { mode: 'treated_as_deviation' } }
    applyDeviationTreatment([original], map)
    expect(original.actualMisstatement).toBe('0.00')
    expect(original.checkResult).toBe('')
  })

  it('替代程序处置不改写金额', () => {
    const map: UncheckedDispositionMap = {
      'V-1': { mode: 'alternative_performed', note: 'x' },
    }
    const [out] = applyDeviationTreatment([sample()], map)
    expect(out.actualMisstatement).toBeUndefined()
    expect(out.checkResult).toBe('')
  })

  it('已检查样本不受影响', () => {
    const map: UncheckedDispositionMap = { 'V-1': { mode: 'treated_as_deviation' } }
    const [out] = applyDeviationTreatment([sample({ checkResult: 'Y' })], map)
    expect(out.actualMisstatement).toBeUndefined()
  })

  it('改写后推断结果确实变大（端到端验证 100% 污染率生效）', () => {
    const samples = [sample({ debitAmount: '10000.00' })]
    const before = projectMisstatement(samples, 'random', '0', '1000000.00')
    const map: UncheckedDispositionMap = { 'V-1': { mode: 'treated_as_deviation' } }
    const after = projectMisstatement(
      applyDeviationTreatment(samples, map),
      'random',
      '0',
      '1000000.00',
    )
    expect(parseFloat(before.projected)).toBe(0)
    expect(parseFloat(after.projected)).toBeGreaterThan(0)
  })

  it('countTreatedAsDeviation 计入 deviation_count 的笔数', () => {
    const samples = [sample(), sample({ voucherNo: 'V-2' }), sample({ voucherNo: 'V-3' })]
    const map: UncheckedDispositionMap = {
      'V-1': { mode: 'treated_as_deviation' },
      'V-2': { mode: 'alternative_performed', note: 'x' },
      'V-3': { mode: 'treated_as_deviation' },
    }
    expect(countTreatedAsDeviation(samples, map)).toBe(2)
  })
})

// ─── 载荷 ────────────────────────────────────────────────────────────────────

describe('持久化载荷', () => {
  it('全空返回 null（与后端「缺省即 None」对齐）', () => {
    expect(buildUncheckedDispositionPayload([sample()], {})).toBeNull()
  })

  it('只输出当前仍未检查的样本处置（补录核查结果后处置记录失效）', () => {
    const samples = [sample({ checkResult: 'Y' }), sample({ voucherNo: 'V-2' })]
    const map: UncheckedDispositionMap = {
      'V-1': { mode: 'treated_as_deviation' },
      'V-2': { mode: 'alternative_performed', note: '已核对' },
    }
    const payload = buildUncheckedDispositionPayload(samples, map)
    expect(Object.keys(payload!)).toEqual(['V-2'])
  })

  it('空白说明归一为 null（不存空串）', () => {
    const map: UncheckedDispositionMap = {
      'V-1': { mode: 'alternative_performed', note: '   ' },
    }
    expect(buildUncheckedDispositionPayload([sample()], map)).toEqual({
      'V-1': { mode: 'alternative_performed', note: null },
    })
  })
})

// ─── 枚举与文案 ──────────────────────────────────────────────────────────────

describe('枚举与文案', () => {
  it('两种处置恰为准则规定的二选一', () => {
    expect([...UNCHECKED_DISPOSITION_MODES]).toEqual([
      'treated_as_deviation',
      'alternative_performed',
    ])
  })

  it('标签全中文且不等于 key', () => {
    for (const mode of UNCHECKED_DISPOSITION_MODES) {
      const label = UNCHECKED_DISPOSITION_LABELS[mode]
      expect(label).not.toBe(mode)
      expect(/[\u4e00-\u9fa5]/.test(label)).toBe(true)
    }
  })

  it('每种处置的提示语写明准则口径', () => {
    expect(UNCHECKED_DISPOSITION_HINTS.treated_as_deviation).toContain('CAS 1314')
    expect(UNCHECKED_DISPOSITION_HINTS.treated_as_deviation).toContain('100%')
    expect(UNCHECKED_DISPOSITION_HINTS.alternative_performed).toContain('替代程序')
  })

  it('后端取值域与前端逐字相等', () => {
    const src = fs.readFileSync(
      path.join(repoRoot(), 'backend/app/routers/voucher_sampling.py'),
      'utf-8',
    )
    const m = src.match(/_EVAL_UNCHECKED_MODES\s*=\s*\(([^)]*)\)/)
    expect(m, '后端未找到 _EVAL_UNCHECKED_MODES（改名会让本守卫空转）').toBeTruthy()
    const backend = [...m![1].matchAll(/"([a-z_]+)"/g)].map(x => x[1])
    expect(backend.sort()).toEqual([...UNCHECKED_DISPOSITION_MODES].sort())
  })

  it('反向自检：旧行为（只计数不处置）在本判据下必打红', () => {
    // 旧行为等价于「所有未检查样本都没有处置记录」→ pending 非空 → 阻断
    const r = resolveUncheckedDisposition([sample(), sample({ voucherNo: 'V-2' })], {})
    expect(r.pending).toHaveLength(2)
    expect(r.asDeviation).toHaveLength(0)
    expect(r.alternative).toHaveLength(0)
  })
})

// ─── Property 28：已实施替代程序的样本必须进入推断基数（R3.3） ────────────────
//
// 2026-08-08 Task 19 浏览器实测取证的缺陷：`alternative_performed` 的样本
// `checkResult` 仍为空 ⇒ 被 `inferMisstatement` 的
// `treated.filter(v => v.checkResult !== '')` 整体排除 ⇒ 既不进分子也不进分母，
// 比率估计基数被静默缩小、推断错报被放大。R3.3 要求它「按替代程序结论参与推断」。

/** 按花括号配对截取具名函数体（禁用固定字符窗口：会越过函数尾部命中邻居）。 */
function fnBody(src: string, decl: string): string {
  const at = src.indexOf(decl)
  if (at < 0) throw new Error(`未找到声明：${decl}（改名会让本守卫空转）`)
  // 先用圆括号配对跳过参数列表（多行签名 / 内联类型注解都不会误命中）
  let i = src.indexOf('(', at)
  if (i < 0) throw new Error(`未找到参数列表：${decl}`)
  let paren = 0
  for (; i < src.length; i++) {
    if (src[i] === '(') paren++
    else if (src[i] === ')') {
      paren--
      if (paren === 0) { i++; break }
    }
  }
  // 🔴 参数列表之后的第一个 `{` 可能是**内联返回类型注解**
  // （`function inferMisstatement(): { result: MisstatementResult ... } {`），
  // 直接取它会把"函数体"截成那段类型 ⇒ 后续断言全在无关文本上求值。
  // 故逐个候选块配对，取第一个含语句特征的块。
  const STATEMENT = /\b(const|let|return|if|for|await|function)\b/
  for (let k = i; k < src.length; k++) {
    if (src[k] !== '{') continue
    let brace = 0
    for (let j = k; j < src.length; j++) {
      if (src[j] === '{') brace++
      else if (src[j] === '}') {
        brace--
        if (brace === 0) {
          const block = src.slice(k, j + 1)
          if (STATEMENT.test(block)) return block
          k = j // 该块只是类型注解，跳过它继续找
          break
        }
      }
    }
  }
  throw new Error(`未找到函数体（或括号未配对）：${decl}`)
}

describe('Property 28：替代程序样本参与推断', () => {
  const altMap: UncheckedDispositionMap = {
    'V-ALT': { mode: 'alternative_performed', note: '已核对合同与收款记录' },
  }

  it('替代程序样本被改写为已检查（checkResult=Y）', () => {
    const [out] = applyAlternativeTreatment([sample({ voucherNo: 'V-ALT' })], altMap)
    expect(out.checkResult).toBe('Y')
  })

  it('不覆盖审计师录入的实际错报（留空则保持留空）', () => {
    const withVal = sample({ voucherNo: 'V-ALT', actualMisstatement: '123.45' })
    expect(applyAlternativeTreatment([withVal], altMap)[0].actualMisstatement).toBe('123.45')
    expect(applyAlternativeTreatment([sample({ voucherNo: 'V-ALT' })], altMap)[0].actualMisstatement)
      .toBeUndefined()
  })

  it('返回新数组，原样本不被改写', () => {
    const original = sample({ voucherNo: 'V-ALT' })
    applyAlternativeTreatment([original], altMap)
    expect(original.checkResult).toBe('')
  })

  it('视同偏差 / 未处置 / 已检查三类均不被本函数改写', () => {
    const samples = [
      sample({ voucherNo: 'V-DEV' }),
      sample({ voucherNo: 'V-PEND' }),
      sample({ voucherNo: 'V-DONE', checkResult: 'N' }),
    ]
    const map: UncheckedDispositionMap = { 'V-DEV': { mode: 'treated_as_deviation' } }
    const out = applyAlternativeTreatment(samples, map)
    expect(out.map(v => v.checkResult)).toEqual(['', '', 'N'])
  })

  it('统一入口同时处置两类（集合互斥，顺序无关）', () => {
    const samples = [sample({ voucherNo: 'V-DEV' }), sample({ voucherNo: 'V-ALT' })]
    const map: UncheckedDispositionMap = {
      'V-DEV': { mode: 'treated_as_deviation' },
      'V-ALT': { mode: 'alternative_performed', note: 'x' },
    }
    const out = applyUncheckedDisposition(samples, map)
    expect(out.map(v => v.checkResult)).toEqual(['N', 'Y'])
    // 视同偏差按 100% 污染率写入账面金额；替代程序不写金额
    expect(out[0].actualMisstatement).toBe('1000.00')
    expect(out[1].actualMisstatement).toBeUndefined()
  })

  it('未选处置方式的样本一律不改写（由结论门控阻断，不得悄悄参与推断）', () => {
    const out = applyUncheckedDisposition([sample({ voucherNo: 'V-PEND' })], {})
    expect(out[0].checkResult).toBe('')
  })

  // 🔴 反向自检：用 Task 19 浏览器实测那组真实数字钉死「旧行为把推断错报放大」
  it('反向自检：只做视同偏差改写会把替代程序样本挤出分母、放大推断错报', () => {
    const samples: SampledVoucher[] = [
      // 已检查 + 手工录入错报
      sample({ voucherNo: '2124', debitAmount: null, creditAmount: '13832.00', checkResult: '异常', actualMisstatement: '5000' }),
      // 视同偏差（账面 195.60 全额计入）
      sample({ voucherNo: '4846', debitAmount: '195.60' }),
      // 已实施替代程序（账面 37340.20，未发现错报）
      sample({ voucherNo: '1382', debitAmount: '37340.20' }),
      // 视同偏差（账面 15655.09 全额计入）
      sample({ voucherNo: '3251', debitAmount: '15655.09' }),
    ]
    const map: UncheckedDispositionMap = {
      '4846': { mode: 'treated_as_deviation' },
      '3251': { mode: 'treated_as_deviation' },
      '1382': { mode: 'alternative_performed', note: '已检查合同与收款记录' },
    }
    const population = '4857866.37'
    const infer = (list: SampledVoucher[]) =>
      projectMisstatement(list.filter(v => v.checkResult !== ''), 'random', '0', population, 0.95)

    // 旧行为：只改写视同偏差 → 分母 29,682.69（1382 被排除）
    const old = infer(applyDeviationTreatment(samples, map))
    expect(old.projected).toBe('3412422.05')

    // 修复后：替代程序样本进入分母（错报 0）→ 分母 67,022.89
    // 两个期望值均由独立 Decimal 复算核对（20850.69/29682.69 与 20850.69/67022.89 × 总体），
    // 且 3412422.05 与真实库那次实测写入的 `projected` 逐位相同 = 旧行为取证。
    const now = infer(applyUncheckedDisposition(samples, map))
    expect(now.projected).toBe('1511272.73')

    // 方向必须是「旧口径虚高」而非相反
    expect(Number(old.projected)).toBeGreaterThan(Number(now.projected))
  })

  it('自检：fnBody 跳过内联返回类型注解（否则下一条断言会在类型文本上空转）', () => {
    const fixture = [
      'function demo(a: number): {',
      '  result: string',
      '} {',
      '  const x = a',
      '  return String(x)',
      '}',
    ].join('\n')
    const body = fnBody(fixture, 'function demo')
    expect(body).toContain('const x = a')
    expect(body).not.toContain('result: string')
  })

  it('推断调用点必须走统一入口（防回退成只处置视同偏差）', () => {
    const src = fs.readFileSync(
      path.join(repoRoot(), 'audit-platform/frontend/src/components/workpaper/composables/useVoucherSampling.ts'),
      'utf-8',
    ).replace(/\r\n/g, '\n')
    const body = fnBody(src, 'function inferMisstatement')
    expect(body).toMatch(/applyUncheckedDisposition\s*\(/)
    expect(body).not.toMatch(/applyDeviationTreatment\s*\(/)
    // 反向自检：截函数体确实生效（未把整份文件当函数体）
    expect(body.length).toBeLessThan(src.length / 4)
    expect(body).toContain('checkResult')
  })
})
