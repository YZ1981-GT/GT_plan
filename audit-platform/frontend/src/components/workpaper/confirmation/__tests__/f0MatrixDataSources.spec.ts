/**
 * f0MatrixDataSources.spec.ts — F0 矩阵取数编排守卫
 *
 * 🔴 本文件的核心价值 = Task 23.4「防再次退化成空壳」
 * 上一版把 bookAmounts/altTotals 全传 undefined 并留 TODO 注释，
 * 167 个单测全绿却让 4 个百分比行恒 `-`。故必须有源码级断言。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname_ = dirname(fileURLToPath(import.meta.url))
// __tests__ → confirmation → workpaper → components → src → frontend → audit-platform → repo
// 🔴 需回退 7 级（memory 铁律：`composables/__tests__` 下比 `workpaper/__tests__` 多一级，
//    照抄别处的 6 级会 ENOENT；本文件在 `confirmation/__tests__` 下同样是 7 级）
const REPO_ROOT = resolve(__dirname_, '../../../../../../..')

function readSource(rel: string): string {
  return readFileSync(resolve(REPO_ROOT, rel), 'utf-8')
}

/** 去注释（防说明文字被数成真实代码） */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

const SUMMARY_VUE = 'audit-platform/frontend/src/components/workpaper/confirmation/GtConfirmationSummary.vue'
const SOURCES_TS = 'audit-platform/frontend/src/components/workpaper/confirmation/composables/f0MatrixDataSources.ts'
const AGG_TS = 'audit-platform/frontend/src/components/workpaper/confirmation/composables/f0SummaryAggregation.ts'

// ─── Property: 矩阵入参不得全为 undefined（防空壳退化） ──────────────────────

describe('Property 23.4: 矩阵入参必须接真实数据源', () => {
  const src = stripComments(readSource(SUMMARY_VUE))

  it('反向自检：能读到源码且含 buildF0SummaryMatrix 调用', () => {
    expect(src.length).toBeGreaterThan(1000)
    expect(src).toContain('buildF0SummaryMatrix')
  })

  it('bookAmounts 不得传 undefined', () => {
    expect(src).not.toMatch(/bookAmounts:\s*undefined/)
  })

  it('manualOverrides 不得传 undefined', () => {
    expect(src).not.toMatch(/manualOverrides:\s*undefined/)
  })

  it('矩阵入参必须引用取数结果（f0Sources）与手工覆盖（f0ManualOverrides）', () => {
    const callMatch = src.match(/buildF0SummaryMatrix\(\{[\s\S]{0,600}?\}\)/)
    expect(callMatch).not.toBeNull()
    const call = callMatch![0]
    expect(call).toContain('f0Sources')
    expect(call).toContain('f0ManualOverrides')
  })

  it('🔴 Task 28：矩阵入参不得含 altF05Totals/altF06Totals（源模板 R36 取上区 Y 列）', () => {
    const callMatch = src.match(/buildF0SummaryMatrix\(\{[\s\S]{0,600}?\}\)/)
    expect(callMatch).not.toBeNull()
    const call = callMatch![0]
    expect(call).not.toContain('altF05Totals')
    expect(call).not.toContain('altF06Totals')
  })

  it('🔴 Task 28：F0-5/F0-6 合计必须接到勾稽（checkAltConsistency）而非丢弃', () => {
    expect(src).toContain('checkAltConsistency')
    const callMatch = src.match(/checkAltConsistency\(\{[\s\S]{0,400}?\}\)/)
    expect(callMatch).not.toBeNull()
    expect(callMatch![0]).toContain('altF05Totals')
    expect(callMatch![0]).toContain('altF06Totals')
  })

  it('🔴 Task 28：R37 双算风险行必须接线（detectAltOverlapRows）', () => {
    expect(src).toContain('detectAltOverlapRows')
    expect(src).toMatch(/f0AltOverlapCount/)
  })

  it('必须调用 loadF0MatrixSources 拉取数据源', () => {
    expect(src).toContain('loadF0MatrixSources')
  })

  it('必须在 onMounted 触发取数（否则数据源永不加载）', () => {
    expect(src).toMatch(/onMounted\([\s\S]{0,200}loadF0Sources/)
  })

  it('禁止残留 TODO 注释形态的未接线标记（在矩阵调用附近）', () => {
    // 原始源码（未去注释）中矩阵调用块内不得有 TODO
    const raw = readSource(SUMMARY_VUE)
    const callMatch = raw.match(/buildF0SummaryMatrix\(\{[\s\S]{0,800}?\}\)/)
    if (callMatch) {
      expect(callMatch[0]).not.toMatch(/TODO/i)
    }
  })
})

// ─── Property: 取数模块的 import 路径正确（防 Vite 500） ─────────────────────

describe('Property: 取数模块 HTTP 客户端与响应形态实证', () => {
  const src = readSource(SOURCES_TS)
  const code = stripComments(src)

  it('必须导出三个核心函数', () => {
    expect(src).toContain('export async function loadF0MatrixSources')
    expect(src).toContain('export function matrixOverrideItemId')
    expect(src).toContain('export function parseManualOverrides')
  })

  // 🔴 2026-08-03 浏览器实测 P0：客户端与响应形态必须配对，否则静默取不到数
  //    `http.get()` → AxiosResponse（要 `.data`）；`api.get()` → 业务数据本身。
  //    上一版用 `@/utils/http` 却按 apiProxy 形态读 `(idRes as any)?.wp_id` → 恒 undefined。
  it('HTTP 客户端走 @/services/apiProxy（与平台 20+ 处 wp-id-by-code 调用一致）', () => {
    expect(code).toContain("import { api } from '@/services/apiProxy'")
  })

  it('禁止 default-import @/utils/http（返回 AxiosResponse，形态与本模块读法不符）', () => {
    expect(code).not.toMatch(/import\s+api\s+from\s+'@\/utils\/http'/)
    expect(code).not.toContain("from '@/utils/api'") // 该模块不存在，曾致 Vite 500
  })

  it('wp-id-by-code 响应按业务数据读（idRes?.wp_id），不得再套一层 .data', () => {
    expect(code).toMatch(/idRes\?\.wp_id/)
    expect(code).not.toMatch(/idRes[^\n]*\.data\b/)
  })

  it('反向自检：源码确实含 wp-id-by-code 与 render-config 两次取数', () => {
    expect(code).toContain('/api/custom-query/wp-id-by-code')
    expect(code).toContain('/render-config')
  })

  // 🔴 2026-08-03 实测 P0：`utils/http` 去重键 = `method:url:JSON.stringify(params)`
  //    → 并行请求同一 URL 会被 `pendingMap.get(key)!.abort()` 打掉先发的那个
  //    （症状：diagnostics.errors 出现 `F0-5: canceled`）
  it('F0-5/F0-6 必须一次 render-config 取两张表，不得并行发同 URL 请求', () => {
    expect(code).toContain('async function fetchAltCompaniesBoth')
    expect(code).not.toContain('fetchAltCompanies(wpId,')
    // 不得出现「并行两次同一 render-config」的形态
    const parallel = code.match(/Promise\.allSettled\(\[[\s\S]{0,300}?\]\)/g) ?? []
    for (const block of parallel) {
      const hits = (block.match(/render-config|fetchAltCompanies/g) ?? []).length
      expect(hits).toBe(0)
    }
  })

  it('账面金额取值必须走每品种声明的 pick（三循环键名不同）', () => {
    expect(code).toMatch(/pick:\s*\(htmlData: any\)\s*=>\s*unknown/)
    expect(code).toMatch(/Number\(pick\(hd\)\)/)
    // 不得再统一假设 project_context.tb_amount
    expect(code).not.toMatch(/hd\?\.project_context\?\.tb_amount/)
  })

  it('取数错误必须被 UI 渲染（不能只收集不显示）', () => {
    const summary = stripComments(readSource(SUMMARY_VUE))
    expect(summary).toContain('f0SourceErrors')
    expect(summary).toMatch(/diagnostics\.errors/)
    // 模板里要有消费点，不能只有一个没人用的 computed
    expect(summary).toMatch(/v-if="f0SourceErrors\.length"/)
  })
})

// ─── Property: 替代程序取数口径实证（不用猜测键名） ──────────────────────────

describe('Property: 替代程序合计取数口径', () => {
  const aggSrc = stripComments(readSource(AGG_TS))

  it('已删除上一版猜测键名的 extractAltTotalsFromResponses', () => {
    expect(aggSrc).not.toContain('extractAltTotalsFromResponses')
  })

  it('改用从 companies[] 计算的 computeAltTotalsFromCompanies', () => {
    expect(aggSrc).toContain('export function computeAltTotalsFromCompanies')
  })

  it('凭证金额字段名为 voucher_amount（对齐后端 _VOUCHER_COLS）', () => {
    expect(aggSrc).toContain("F0_ALT_VOUCHER_FIELD = 'voucher_amount'")
  })

  it('遍历 block1_rows ~ block4_rows 四个区块', () => {
    for (const b of ['block1_rows', 'block2_rows', 'block3_rows', 'block4_rows']) {
      expect(aggSrc).toContain(b)
    }
  })
})

// ─── Property: 矩阵取值口径逐行对齐源模板公式（Task 28） ─────────────────────

describe('Property: 矩阵取值必须按源模板 SUMIF 口径，禁编造分摊', () => {
  const aggSrc = stripComments(readSource(AGG_TS))

  it('已删除无源模板依据的 distributeAltAmounts（F0-5 全归预付 / F0-6 平分）', () => {
    expect(aggSrc).not.toContain('distributeAltAmounts')
  })

  it('已删除旧口径 sumConfirmedByCategory（源模板 SUMIF(U) 无相符过滤）', () => {
    expect(aggSrc).not.toContain('sumConfirmedByCategory')
  })

  it('R33 取 confirmed_amount 列（U 可确认金额）', () => {
    expect(aggSrc).toMatch(/sumByCategory\(\s*rows\s*,\s*category\s*,\s*'confirmed_amount'\s*\)/)
  })

  it('R36 取 alt_confirmed 列（Y 替代后可确认金额）', () => {
    expect(aggSrc).toMatch(/sumByCategory\(\s*rows\s*,\s*category\s*,\s*'alt_confirmed'\s*\)/)
  })

  it('F0MatrixInput 不再声明 altF05Totals/altF06Totals', () => {
    const ifaceMatch = aggSrc.match(/export interface F0MatrixInput \{[\s\S]*?\n\}/)
    expect(ifaceMatch).not.toBeNull()
    expect(ifaceMatch![0]).not.toContain('altF05Totals')
    expect(ifaceMatch![0]).not.toContain('altF06Totals')
  })

  it('反向自检：源码里确实存在「编造分摊」这段被删掉的语义关键词的替代物', () => {
    // 删掉编造逻辑后必须有勾稽兜底，否则 F0-5/F0-6 取数就成了纯浪费
    expect(aggSrc).toContain('export function checkAltConsistency')
    expect(aggSrc).toContain('export function detectAltOverlapRows')
  })
})

// ─── 运行时行为：computeAltTotalsFromCompanies ───────────────────────────────

describe('computeAltTotalsFromCompanies 运行时', () => {
  it('空/null/undefined → total 0', async () => {
    const { computeAltTotalsFromCompanies } = await import('../composables/f0SummaryAggregation')
    expect(computeAltTotalsFromCompanies(null).total).toBe(0)
    expect(computeAltTotalsFromCompanies(undefined).total).toBe(0)
    expect(computeAltTotalsFromCompanies([]).total).toBe(0)
  })

  it('四区块金额累加', async () => {
    const { computeAltTotalsFromCompanies } = await import('../composables/f0SummaryAggregation')
    const companies = [{
      block1_rows: [{ voucher_amount: 100 }, { voucher_amount: 200 }],
      block2_rows: [{ voucher_amount: 300 }],
      block3_rows: [{ voucher_amount: 400 }],
      block4_rows: [{ voucher_amount: 500 }],
    }]
    expect(computeAltTotalsFromCompanies(companies).total).toBe(1500)
  })

  it('多公司累加', async () => {
    const { computeAltTotalsFromCompanies } = await import('../composables/f0SummaryAggregation')
    const companies = [
      { block1_rows: [{ voucher_amount: 1000 }] },
      { block1_rows: [{ voucher_amount: 2000 }] },
    ]
    expect(computeAltTotalsFromCompanies(companies).total).toBe(3000)
  })

  it('NaN/非数值/缺字段跳过不产出 NaN', async () => {
    const { computeAltTotalsFromCompanies } = await import('../composables/f0SummaryAggregation')
    const companies = [{
      block1_rows: [
        { voucher_amount: 100 },
        { voucher_amount: NaN },
        { voucher_amount: 'abc' },
        {},
        { voucher_amount: Infinity },
      ],
    }]
    const result = computeAltTotalsFromCompanies(companies as any)
    expect(result.total).toBe(100)
    expect(Number.isFinite(result.total)).toBe(true)
  })

  it('浮点精度归一到两位小数', async () => {
    const { computeAltTotalsFromCompanies } = await import('../composables/f0SummaryAggregation')
    const companies = [{
      block1_rows: [{ voucher_amount: 0.1 }, { voucher_amount: 0.2 }],
    }]
    expect(computeAltTotalsFromCompanies(companies).total).toBe(0.3)
  })

  it('非数组 block 字段安全跳过', async () => {
    const { computeAltTotalsFromCompanies } = await import('../composables/f0SummaryAggregation')
    const companies = [{ block1_rows: 'not-array' as any, block2_rows: [{ voucher_amount: 50 }] }]
    expect(computeAltTotalsFromCompanies(companies).total).toBe(50)
  })
})

// ─── matrixOverrideItemId / parseManualOverrides ─────────────────────────────

describe('手工覆盖持久化键', () => {
  it('matrixOverrideItemId 形态为 F0-1-matrix-{品种}-{指标}', async () => {
    const { matrixOverrideItemId } = await import('../composables/f0MatrixDataSources')
    expect(matrixOverrideItemId('预付账款', '本期（期末）账面金额'))
      .toBe('F0-1-matrix-预付账款-本期（期末）账面金额')
  })

  it('parseManualOverrides 从 Map 读取', async () => {
    const { parseManualOverrides } = await import('../composables/f0MatrixDataSources')
    const map = new Map<string, any>([
      ['F0-1-matrix-预付账款-本期（期末）账面金额', { value: '12345.67' }],
    ])
    const result = parseManualOverrides(map)
    expect(result['预付账款::本期（期末）账面金额']).toBe(12345.67)
  })

  it('parseManualOverrides 从对象读取', async () => {
    const { parseManualOverrides } = await import('../composables/f0MatrixDataSources')
    const obj = {
      'F0-1-matrix-应付账款-本期（期末）账面金额': { value: 999 },
    }
    expect(parseManualOverrides(obj)['应付账款::本期（期末）账面金额']).toBe(999)
  })

  it('空值/非数值不进结果（撤销覆盖语义）', async () => {
    const { parseManualOverrides } = await import('../composables/f0MatrixDataSources')
    const map = new Map<string, any>([
      ['F0-1-matrix-预付账款-本期（期末）账面金额', { value: '' }],
      ['F0-1-matrix-应付票据-本期（期末）账面金额', { value: 'abc' }],
    ])
    expect(Object.keys(parseManualOverrides(map))).toHaveLength(0)
  })

  it('null/undefined 输入返回空对象', async () => {
    const { parseManualOverrides } = await import('../composables/f0MatrixDataSources')
    expect(parseManualOverrides(null)).toEqual({})
    expect(parseManualOverrides(undefined)).toEqual({})
  })
})
