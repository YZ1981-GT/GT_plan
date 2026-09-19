/**
 * k0MatrixSpec.spec.ts — K0 品种矩阵声明守卫（Wave 2）
 *
 * spec: k0-confirmation-source-alignment · Task 7
 *   Property 8（row_code 精确匹配 + 「无科目」≠「为 0」）
 *   Requirement 4.1 / 4.2 / 4.3 / 4.5 / 4.6
 *
 * 判据：**读对侧源码**（后端源模板事实守卫 + K1/K3 render 声明），不拿自己写的 fixture 自证。
 * 每条断言配反向自检，防正则失效导致断言空转。
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  CONVERGENCE_TARGET,
  K0_BOOK_AMOUNT_WP_CODES,
  K0_CATEGORY_NAMES,
  K0_LOWER_ZONE_SHEET,
  K0_MATRIX_CATEGORIES,
  K0_MATRIX_EDITABLE_METRIC_INDEX,
  K0_MATRIX_METRIC_ANCHORS,
  K0_MATRIX_METRIC_LABELS,
  K0_SOURCE_REF_PREFIX,
  getK0Category,
  k0BookAmountHint,
  k0MatrixOverrideItemId,
} from '../k0MatrixSpec'

// ─── 仓库根定位：哨兵**文件**向上查找，不写死回退级数 ─────────────────────────
// 🔴 本目录深度为 src/components/workpaper/confirmation/k0-confirmation/__tests__/
//    （比 g0-confirmation/__tests__/ 深一级）。写死 `../..` 级数极易差一级 →
//    解析到 audit-platform 后 readFileSync ENOENT，表现为**文件级失败**而非断言失败，
//    很容易被当噪声跳过（平台已踩过两次）。
const SENTINEL = 'backend/wp_templates/K/K0 管理循环函证.xlsx'

function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    if (existsSync(resolve(dir, SENTINEL))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未找到仓库根（哨兵 ${SENTINEL} 不存在于 ${__dirname} 的任一祖先）`)
}

const REPO_ROOT = findRepoRoot()
const BACKEND_FACTS = resolve(REPO_ROOT, 'backend/tests/test_k0_source_template_facts.py')
const K1_RENDER = resolve(REPO_ROOT, 'backend/app/routers/wp_render_strategies/_k1_other_receivables.py')
const K_CYCLE_SPECS = resolve(REPO_ROOT, 'backend/app/services/four_table/k_cycle_specs.py')
const MATRIX_SPEC_TS = resolve(__dirname, '../k0MatrixSpec.ts')

const factsSrc = readFileSync(BACKEND_FACTS, 'utf-8')

/**
 * 从 `k_cycle_specs.py` 取某循环声明的 row_code（listed / soe）。
 *
 * 🔴 用**花括号/圆括号配对**截 `KCycleSpec(...)` 块，不用固定字符窗口 —— 块长度会随
 * 注释增删漂移，写死 `slice(at, at+600)` 会在注释变长后截断、把断言变成空转。
 */
function backendRowCode(wp: string): { listed: string; soe: string } {
  const src = readFileSync(K_CYCLE_SPECS, 'utf-8')
  const at = src.indexOf(`"${wp}": KCycleSpec(`)
  expect(at, `后端 K_CYCLE_SPECS 未找到 ${wp}`).toBeGreaterThan(-1)
  const start = src.indexOf('(', src.indexOf('KCycleSpec', at))
  let depth = 0
  let end = -1
  for (let i = start; i < src.length; i += 1) {
    if (src[i] === '(') depth += 1
    else if (src[i] === ')') {
      depth -= 1
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  expect(end, `${wp} 的 KCycleSpec(...) 括号未配对`).toBeGreaterThan(start)
  const block = src.slice(start, end)
  const listed = block.match(/row_code_listed="([^"]+)"/)?.[1]
  const soe = block.match(/row_code_soe="([^"]+)"/)?.[1]
  expect(listed, `${wp} 未声明 row_code_listed`).toBeTruthy()
  expect(soe, `${wp} 未声明 row_code_soe`).toBeTruthy()
  return { listed: listed!, soe: soe! }
}

/** 从 python 源码里按「常量名 = [ ... ]」取块（括号配对），再抽双引号字符串 */
function pyListStrings(src: string, constName: string): string[] {
  const at = src.indexOf(`${constName} = [`)
  expect(at, `后端未找到常量 ${constName}`).toBeGreaterThan(-1)
  const start = src.indexOf('[', at)
  let depth = 0
  let end = -1
  for (let i = start; i < src.length; i += 1) {
    if (src[i] === '[') depth += 1
    else if (src[i] === ']') {
      depth -= 1
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  expect(end, `${constName} 括号未配对`).toBeGreaterThan(start)
  return [...src.slice(start, end + 1).matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((m) => m[1])
}

describe('helper 自检（防解析失效导致断言空转）', () => {
  it('pyListStrings 能从真实后端文件取到非空结果', () => {
    const cats = pyListStrings(factsSrc, 'MATRIX_CATEGORIES')
    expect(cats.length).toBeGreaterThan(0)
  })

  it('pyListStrings 对不存在的常量会失败而不是静默返回空数组', () => {
    expect(() => pyListStrings(factsSrc, 'THIS_CONST_DOES_NOT_EXIST')).toThrow()
  })
})

// ─── Requirement 4.1：品种清单与源模板锚点 ───────────────────────────────────

describe('Requirement 4.1: 2 品种 + sourceRef 逐字锚定源模板', () => {
  it('恰 2 个品种，顺序与源模板 E28→F28 一致', () => {
    expect(K0_CATEGORY_NAMES).toEqual(['其他应收款', '其他应付款'])
    expect(K0_MATRIX_CATEGORIES).toHaveLength(2)
  })

  it('品种名与后端源模板事实守卫的 MATRIX_CATEGORIES 逐字一致（交叉锁死）', () => {
    // 后端常量形如 [("E28", "其他应收款"), ("F28", "其他应付款")]
    const flat = pyListStrings(factsSrc, 'MATRIX_CATEGORIES')
    expect(flat).toEqual(['E28', '其他应收款', 'F28', '其他应付款'])
    for (const cat of K0_MATRIX_CATEGORIES) {
      expect(flat).toContain(cat.category)
      expect(flat).toContain(cat.anchor)
    }
  })

  it('sourceRef == 前缀 + anchor（防两字段各自漂移）', () => {
    for (const cat of K0_MATRIX_CATEGORIES) {
      expect(cat.sourceRef).toBe(`${K0_SOURCE_REF_PREFIX}${cat.anchor}`)
    }
    expect(K0_SOURCE_REF_PREFIX).toBe('K0-1!')
  })

  it('下区 sheet 名是源模板真实 tab，不是 `审定表K0-1`', () => {
    expect(K0_LOWER_ZONE_SHEET).toBe('函证结果汇总表K0-1')
    expect(K0_LOWER_ZONE_SHEET).not.toContain('审定表')
  })

  it('K0 品种**没有** `……` 可扩位（与 G0/H0 不同，不做动态品种）', () => {
    expect(K0_CATEGORY_NAMES).not.toContain('……')
    // 源模板 G28 为空的事实已由后端 `test_matrix_categories_are_exactly_two` 钉住
    expect(factsSrc).toContain('G28')
  })
})

// ─── Property 8：row_code 精确匹配 ───────────────────────────────────────────

describe('Property 8: row_code 精确匹配（BS-009 / BS-050，非 BS-075）', () => {
  it('两品种 reportRowCode 为 BS-009 / BS-050', () => {
    expect(K0_MATRIX_CATEGORIES.map((c) => c.reportRowCode)).toEqual(['BS-009', 'BS-050'])
  })

  it('绝不使用 BS-075（同名 NULL 行；listed 侧 row_name 竟是「股本」）', () => {
    const src = readFileSync(MATRIX_SPEC_TS, 'utf-8')
    for (const cat of K0_MATRIX_CATEGORIES) {
      expect(cat.reportRowCode).not.toBe('BS-075')
    }
    // 允许在注释里提到 BS-075（作为坑的留证），但不得出现在 reportRowCode 字段值上
    expect(src).toMatch(/reportRowCode:\s*'BS-009'/)
    expect(src).toMatch(/reportRowCode:\s*'BS-050'/)
    expect(src).not.toMatch(/reportRowCode:\s*'BS-075'/)
  })

  it('BS-075 的坑必须在文件里留证（否则下个会话会重踩）', () => {
    const src = readFileSync(MATRIX_SPEC_TS, 'utf-8')
    expect(src).toContain('BS-075')
    expect(src).toMatch(/row_code/)
  })

  it('声明中不含任何按 row_name 匹配的路径', () => {
    const src = readFileSync(MATRIX_SPEC_TS, 'utf-8')
    expect(src).not.toMatch(/rowName|row_name\s*[:=]/)
  })

  it('BS-009 声明为净额口径（含备抵扣减），BS-050 不是', () => {
    expect(getK0Category('其他应收款')!.netOfProvision).toBe(true)
    expect(getK0Category('其他应付款')!.netOfProvision).toBe(false)
    // 净额口径三个码齐备：原值 + 减项 + 加项
    expect(getK0Category('其他应收款')!.fallbackAccountCodes).toEqual(['1221', '1231-03', '1131'])
  })
})

// ─── Requirement 4.6：与后端声明双向锁死 ─────────────────────────────────────

describe('Requirement 4.6: 与后端 K 循环声明双向锁死', () => {
  /**
   * 🔴 K1 render 的 `K1_REPORT_ROW_CODE` 已收敛为 `_K1_SPEC.row_code_soe`（不再是字面量），
   * 故此处必须解一层：render 侧只断言「取自 spec」，真值到 `k_cycle_specs.py` 取。
   * 若哪天 render 又写回字面量，第一条断言会打红。
   */
  it('其他应收款的 row_code 与 K1 后端声明一致（render 侧不得写字面量）', () => {
    const k1 = readFileSync(K1_RENDER, 'utf-8')
    expect(
      k1,
      'K1 render 的 K1_REPORT_ROW_CODE 不再取自 _K1_SPEC —— 单一真源被绕开',
    ).toMatch(/K1_REPORT_ROW_CODE\s*=\s*_K1_SPEC\.row_code_(soe|listed)\b/)
    expect(k1, 'K1 render 不得把 row_code 写成字面量').not.toMatch(
      /K1_REPORT_ROW_CODE\s*=\s*["']/,
    )

    const row = backendRowCode('K1')
    expect(getK0Category('其他应收款')!.reportRowCode).toBe(row.listed)
    expect(row.listed, 'K1 两准则应同码').toBe(row.soe)
  })

  it('账面金额来源底稿 = K1 / K3（相邻循环，不新建通路）', () => {
    expect(K0_MATRIX_CATEGORIES.map((c) => c.bookAmountFrom)).toEqual(['K1', 'K3'])
    expect([...K0_BOOK_AMOUNT_WP_CODES].sort()).toEqual(['K1', 'K3'])
  })

  it('后端 K3 声明的科目名确实是「其他应付款」（语义锚点）', () => {
    const src = readFileSync(K_CYCLE_SPECS, 'utf-8')
    const at = src.indexOf('"K3": KCycleSpec(')
    expect(at).toBeGreaterThan(-1)
    const block = src.slice(at, at + 600)
    expect(block).toMatch(/account_name="其他应付款"/)
  })

  /**
   * ✅ 分歧已收敛（`k-cycle-extraction-formula-and-disclosure-closure` Task 7）：
   * 后端 K3 原声明 `row_code_listed="BS-053"` / `row_code_soe="BS-075"` 均为错码 ——
   * BS-053 实为**其他流动负债**（K4 的行，与 K4 跨循环撞码）、BS-075 在 soe 侧名对但
   * formula 为 NULL、在 listed 侧竟是「股本」。有公式的其他应付款行是 **BS-050**
   * （`TB('2241') + TB('2231')`，应付利息已并入其他应付款列报）。
   *
   * 后端已改为 BS-050 + `extra_standard_codes=("2231",)`，K0 侧本就是 BS-050 →
   * 此处从「记录分歧」翻转为**双向锁死**：任一侧再漂移即打红。
   */
  it('K3 row_code 与 K0 双向锁死在 BS-050（含 2231 并表口径）', () => {
    const row = backendRowCode('K3')
    expect(row.listed, 'K3 listed 侧 row_code 漂移').toBe('BS-050')
    expect(row.soe, 'K3 soe 侧 row_code 漂移').toBe('BS-050')
    expect(getK0Category('其他应付款')!.reportRowCode, 'K0 侧与后端脱钩').toBe(row.listed)

    // BS-050 公式含 2231（应付利息并入）→ 后端必须声明为附加码，否则取数漏一段
    const src = readFileSync(K_CYCLE_SPECS, 'utf-8')
    const at = src.indexOf('"K3": KCycleSpec(')
    expect(at).toBeGreaterThan(-1)
    const k3block = src.slice(at, at + 900)
    expect(k3block, 'K3 未声明 extra_standard_codes=("2231",)').toMatch(
      /extra_standard_codes=\(\s*"2231",?\s*\)/,
    )

    // 旧错码不得再作为 K3 的取值出现
    expect(k3block).not.toMatch(/row_code_(listed|soe)="BS-(053|075)"/)
  })

  it('反向自检：backendRowCode 抽不到时必须抛错（不得静默返回 undefined）', () => {
    expect(() => backendRowCode('K99')).toThrow()
    // 已存在的循环必须抽得到，否则上面几条断言全是空转
    for (const wp of ['K1', 'K3']) {
      const row = backendRowCode(wp)
      expect(row.listed, `${wp} listed 抽空`).toMatch(/^(BS|IS|IMP)-\d+$/)
      expect(row.soe, `${wp} soe 抽空`).toMatch(/^(BS|IS|IMP)-\d+$/)
    }
  })
})

// ─── 指标 ────────────────────────────────────────────────────────────────────

describe('指标 8 条与源模板逐字一致', () => {
  it('8 条标签 + 8 个锚点一一对应', () => {
    expect(K0_MATRIX_METRIC_LABELS).toHaveLength(8)
    expect(K0_MATRIX_METRIC_ANCHORS).toEqual(['C29', 'C30', 'C31', 'C32', 'C33', 'C34', 'C35', 'C36'])
    expect(K0_MATRIX_METRIC_ANCHORS).toHaveLength(K0_MATRIX_METRIC_LABELS.length)
  })

  it('每条标签 + 「：」 都能在后端源模板事实常量里找到（交叉锁死）', () => {
    const flat = pyListStrings(factsSrc, 'MATRIX_METRIC_CELLS')
    for (const [i, label] of K0_MATRIX_METRIC_LABELS.entries()) {
      expect(flat).toContain(`${label}：`)
      expect(flat).toContain(K0_MATRIX_METRIC_ANCHORS[i])
    }
  })

  it('只有第 0 条（账面金额）可手填 —— 源模板 R29 无公式', () => {
    expect(K0_MATRIX_EDITABLE_METRIC_INDEX).toBe(0)
    expect(K0_MATRIX_METRIC_LABELS[0]).toBe('本期（期末）账面金额')
  })

  it('三个比例指标的文字含 (%) 且为半角括号（源模板如此）', () => {
    const ratios = K0_MATRIX_METRIC_LABELS.filter((l) => l.includes('比例'))
    expect(ratios).toHaveLength(4)
    for (const r of ratios) expect(r).toContain('(%)')
  })
})

// ─── 手工覆盖键 ──────────────────────────────────────────────────────────────

describe('手工覆盖键用指标 key 不用中文 label', () => {
  it('形态 = K0-1-matrix-{品种}-{指标key}', () => {
    expect(k0MatrixOverrideItemId('其他应收款', 'book_amount')).toBe(
      'K0-1-matrix-其他应收款-book_amount',
    )
  })

  it('与公式预设的 cell_ref 逐字一致（后端已落盘）', () => {
    const mapping = JSON.parse(
      readFileSync(resolve(REPO_ROOT, 'backend/data/prefill_formula_mapping.json'), 'utf-8'),
    ) as { mappings: Array<{ wp_code?: string; cells?: Array<{ cell_ref?: string }> }> }
    const blk = mapping.mappings.find((m) => m.wp_code === 'K0')
    expect(blk, '后端无 K0 预设块').toBeTruthy()
    const refs = (blk!.cells ?? []).map((c) => c.cell_ref)
    for (const cat of K0_CATEGORY_NAMES) {
      expect(refs).toContain(k0MatrixOverrideItemId(cat, 'book_amount'))
    }
  })

  it('键里不含中文指标 label（改文案不会让已录入值失联）', () => {
    const id = k0MatrixOverrideItemId('其他应收款', 'book_amount')
    for (const label of K0_MATRIX_METRIC_LABELS) {
      expect(id).not.toContain(label)
    }
  })
})

// ─── 溯源提示 / 收敛锚点 ─────────────────────────────────────────────────────

describe('溯源提示与收敛锚点', () => {
  it('两品种 amountHint 都写明报表行；其他应付款侧留 BS-075 警示', () => {
    expect(k0BookAmountHint('其他应收款')).toContain('BS-009')
    expect(k0BookAmountHint('其他应付款')).toContain('BS-050')
    expect(k0BookAmountHint('其他应付款')).toContain('BS-075')
  })

  it('未知品种返回「无此科目」提示而不是 0 或空串（宁缺勿造）', () => {
    const hint = k0BookAmountHint('不存在的品种')
    expect(hint).toContain('本项目无此科目')
    expect(getK0Category('不存在的品种')).toBeUndefined()
  })

  it('CONVERGENCE_TARGET 与 F0/E0/H0/G0 副本用同一标识（收敛 spec 靠它 grep）', () => {
    expect(CONVERGENCE_TARGET).toBe('confirmation-summary-matrix-convergence')
  })

  it('科目码只出现在 fallbackAccountCodes / hint 文案里，不进请求参数形态', () => {
    const src = readFileSync(MATRIX_SPEC_TS, 'utf-8')
    // 不得出现把科目码拼进 URL / params 的形态
    expect(src).not.toMatch(/account_code=/)
    expect(src).not.toMatch(/params\s*:/)
  })
})
