/**
 * amountInputColumnTyping — 可编辑金额控件迁移的正反双向断言
 *
 * Spec: `.kiro/specs/amount-input-migration-and-column-typing/` Task 3
 * 覆盖 Property 4（判据不依赖 formatter）/ 5（I1-10/I1-11 报违规）/ 6（使用期限不报）
 * / 7（三分类无遗漏桶）/ 10（反向具区分能力，本 spec 建面，变异在 Task 4 证明）
 * / 11（反向失败消息含类别）。
 *
 * ## 为什么 spawn 探针实时扫描而非读静态产物
 *
 * 本 spec 每次运行都 `spawnSync` 调 `audit_amount_input_columns.py --json` **实时扫描**
 * 全库再读产物 JSON —— 避免读到滞后的 JSON 造成假绿（产物文件可能落后于源码）。
 * 探针（Python）是全库块扫描的单一真源，本 spec 不在 TS 侧抄第二份扫描逻辑。
 */
import { spawnSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { describe, it, expect, beforeAll } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
// .../src/components/workpaper/shared/__tests__ → repo root 上溯 7 层
const REPO_ROOT = resolve(here, '../../../../../../..')
const PROBE = 'backend/scripts/check/audit_amount_input_columns.py'
const JSON_PATH = resolve(REPO_ROOT, 'backend/data/amount_input_migration_status.json')

interface ViolationRec {
  file: string
  line: number
  label: string
  control: string
  has_formatter: boolean
  semantic: string
  reason: string
  non_amount_category: string | null
}
interface Report {
  scanned_files: number
  totals: { el_input_number: number; el_input_number_with_formatter: number; wp_amount_input: number }
  column_classified_total: number
  confirmed_violation: ViolationRec[]
  reverse_violation: ViolationRec[]
  ambiguous: ViolationRec[]
  ok_count: number
}

let report: Report

beforeAll(() => {
  const py = process.platform === 'win32' ? 'python' : 'python3'
  const r = spawnSync(py, [PROBE, '--json'], {
    cwd: REPO_ROOT,
    encoding: 'utf-8',
    maxBuffer: 32 * 1024 * 1024,
  })
  // 🔴 探针失败必须让本 spec 失败，不得 skip（skip = 假绿）
  if (r.status !== 0) {
    throw new Error(
      `探针 --json 失败 (status=${r.status})\nstdout:\n${r.stdout}\nstderr:\n${r.stderr}`,
    )
  }
  report = JSON.parse(readFileSync(JSON_PATH, 'utf-8')) as Report
}, 120_000)

const I1_FILES = [
  'i1/amortization/I1TabAmortizationNoImpair.vue',
  'i1/amortization/I1TabAmortizationWithImpair.vue',
]

describe('Property 7: 三分类无遗漏桶', () => {
  it('confirmed + reverse + ambiguous + ok === 列级分类总数', () => {
    const sum =
      report.confirmed_violation.length +
      report.reverse_violation.length +
      report.ambiguous.length +
      report.ok_count
    expect(sum).toBe(report.column_classified_total)
  })

  it('totals 与判据基线一致（探针扫描准确性）', () => {
    // el-input-number 总量是稳定基线（存量实测 4260）；若大幅偏离说明扫描漏读
    expect(report.totals.el_input_number).toBeGreaterThan(4000)
    expect(report.scanned_files).toBeGreaterThan(1500)
  })
})

describe('Property 4 / 2.1: 判据不依赖 :formatter 存在', () => {
  it('探针源码的 confirmed 产生路径不以 has_formatter 为筛选条件', () => {
    const src = readFileSync(resolve(REPO_ROOT, PROBE), 'utf-8')
    // _bucket 是产生 confirmed_violation 的唯一函数；截到下一个顶层 def/class。
    // 🔴 CRLF-robust：本仓库 autocrlf=true，工作树为 CRLF，不能用 \n\n 空行边界
    // （\r\n\r\n 匹配不到 \n\n）——变异检验曾借此暴露该守卫脆弱性。
    const m = src.match(/def _bucket\b[\s\S]*?(?=\r?\ndef |\r?\nclass |$)/)
    expect(m, '_bucket 函数应存在').toBeTruthy()
    expect(m![0]).not.toContain('has_formatter')
    expect(m![0]).not.toContain('formatter')
  })

  it('存在 has_formatter=false 的 confirmed_violation（旧探针必漏的形态）', () => {
    // 这正是 I1-10/I1-11 这类「无 formatter 的 el-input-number 金额列」——
    // Task18 旧探针按「找 :formatter」判，必然漏掉。
    const noFmt = report.confirmed_violation.filter((v) => !v.has_formatter)
    expect(noFmt.length).toBeGreaterThan(0)
  })
})

describe('Property 5: I1-10/I1-11 金额列已迁移为 WpAmountInput（Task7 完成后翻转）', () => {
  // Task 7 已把 I1-10/I1-11 的金额列（原值/残值/累计摊销/减值准备/账面月摊销额…）
  // 迁移为 WpAmountInput，「使用期限(年)」保留 el-input-number（反向边界）。
  // ⚠️ 需 Task 5/7 的迁移已入库（commit）后 CI 才绿；工作树有迁移时本地即绿。
  //
  // 「相对 Task18 的能力增量证明」（旧探针按 :formatter 报 0，新探针能报无 formatter
  // 金额列）已由以下三处共同保留，不依赖 I1 仍是违规态：
  //   - amountColumnSemantics.spec.ts「classifyColumnLabel('原值', I1)==='amount'」（真源，永真）
  //   - 本 spec Property 4「存在 has_formatter=false 的 confirmed_violation」（探针不依赖 formatter）
  //   - Task4 变异 M2（I1 使用期限→WpAmountInput→reverse）/ M3（删 /原值/ → I1 原值失格）
  it('I1-10/I1-11 零 confirmed_violation（金额列已迁移）', () => {
    const i1 = report.confirmed_violation.filter((v) => I1_FILES.includes(v.file))
    expect(
      i1,
      `I1-10/I1-11 应零违规（已迁移），实际残留: ${JSON.stringify(i1.map((v) => v.label))}`,
    ).toEqual([])
  })

  it('使用期限(年) 仍是 el-input-number（未被误迁移，反向边界）', () => {
    // 已迁移文件里的非金额列不应出现在 reverse_violation
    const badReverse = report.reverse_violation.filter((v) => I1_FILES.includes(v.file))
    expect(badReverse).toEqual([])
  })
})

describe('Property 6: 使用期限(年) 不报违规（反向边界锚点）', () => {
  it('「使用期限(年)」不出现在任何桶的违规里', () => {
    const inConfirmed = report.confirmed_violation.some((v) => v.label === '使用期限(年)')
    const inReverse = report.reverse_violation.some((v) => v.label === '使用期限(年)')
    expect(inConfirmed).toBe(false)
    expect(inReverse).toBe(false)
  })
})

describe('Property 3.1 / 3.2: 反向边界与扫描面非空', () => {
  it('扫描面非空：已迁移文件参与（WpAmountInput 列 > 0）', () => {
    // 反向断言若扫描面为空则在未迁移代码上恒真（Task18 Property30 的缺陷）
    expect(report.totals.wp_amount_input).toBeGreaterThan(0)
  })

  it('当前无「非金额列误用 WpAmountInput」（reverse_violation 为空）', () => {
    // 现存迁移脚本（D/H 循环）都有反向边界保护，故当前应为 0。
    // 区分能力由 Task 4 变异（把年限列改成 WpAmountInput → 本条应变红）证明。
    expect(report.reverse_violation.length).toBe(0)
  })

  it('Property 11: 若有 reverse_violation，每条必带命中的非金额语义类别', () => {
    for (const v of report.reverse_violation) {
      expect(v.non_amount_category, `${v.file}:${v.label} 反向违规须给出类别`).toBeTruthy()
    }
  })
})

describe('探针能力健康度：动态 label 占比 < 10%（design Error Handling）', () => {
  it('dynamic_label 记入 ambiguous 且占总列 < 10%', () => {
    const dyn = report.ambiguous.filter((v) => v.reason === 'dynamic_label').length
    const ratio = dyn / report.column_classified_total
    expect(ratio).toBeLessThan(0.1)
  })
})

describe('Property 9: 探针按块配对扫描，禁固定字符窗口', () => {
  it('探针源码不含固定字符窗口切片（Task18 首版 400 字符窗口误报的根因）', () => {
    const src = readFileSync(resolve(REPO_ROOT, PROBE), 'utf-8')
    // 禁 src[i:i+400] / content.slice(idx, idx+400) 这类窗口式匹配
    expect(src).not.toMatch(/\[\s*\w+\s*:\s*\w+\s*\+\s*\d{2,}\s*\]/)
    expect(src).not.toMatch(/\.slice\(\s*\w+\s*,\s*\w+\s*\+\s*\d{2,}\s*\)/)
  })
})
