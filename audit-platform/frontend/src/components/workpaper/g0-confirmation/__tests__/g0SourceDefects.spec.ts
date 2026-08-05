/**
 * g0SourceDefects.spec.ts — G0 源模板缺陷「双向」守卫
 *
 * spec: g0-confirmation-source-alignment，Task 20
 * Property 24（源模板缺陷双向断言：源侧存在 × 平台侧已按 handling 处置，缺一即红）
 * Property 27（差异表证券侧 M 列方向按意图统一为 账面 − 回函）
 * Property 13（新建件有真实消费方）
 *
 * ─── 裁决者链条（本文件**不连库、不读 xlsx**）────────────────────────────────
 *   源模板 xlsx ──openpyxl──▶ backend/tests/test_g0_source_template_facts.py
 *                             （`TestSourceDefectsExist` 7 个用例 = 缺陷存在性）
 *                                      │ 交叉锁死（本文件按 id ↔ 用例名比对）
 *                                      ▼
 *                             g0SourceDefects.ts（登记表 7 条）
 *                                      │ 交叉锁死（platformEvidence 逐条查符号）
 *                                      ▼
 *                    平台实现（公式引擎 / 下区声明 / sheet 注册 / 共享列注册表）
 *
 * 后端那份守卫本身是 openpyxl 直读源 xlsx 的 → 它等价于离线 fixture，且它一变本守卫
 * 跟着红，两侧不可能各自漂移。
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  G0_DIFF_DIRECTION_HINT,
  G0_DIFF_DIRECTION_LABEL,
  G0_SOURCE_DEFECTS,
  G0_SOURCE_DEFECT_COUNT,
  g0DefectUiNote,
  g0SourceDefect,
  type G0DefectHandling,
} from '../g0SourceDefects'
import { G0_AUDIT_NOTE_DEFS } from '../g0SummaryLowerZone'
import { G0_SHEET_REGISTRY } from '../g0SheetRegistry'
import {
  calcFairValueDiff,
  calcMarketValueDiff,
  calcQuantityDiff,
} from '../composables/useG0FormulaEngine'

// ─── REPO_ROOT：哨兵**文件**向上查找（禁写死回退级数） ───────────────────────
//
// 🔴 哨兵必须是具体文件不能是目录 —— `audit-platform/backend/app/routers` 是历史遗留
//    空目录，用目录做哨兵会在 `audit-platform` 层提前停下。
const SENTINELS = [
  join('backend', 'tests', 'test_g0_source_template_facts.py'),
  join('backend', 'app', 'data', 'wp_code_overrides.json'),
] as const

function findRepoRoot(start: string): string {
  let dir = resolve(start)
  for (let i = 0; i < 20; i += 1) {
    if (SENTINELS.every((s) => existsSync(join(dir, s)))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未能从 ${start} 向上找到含哨兵文件的仓库根：${SENTINELS.join(' + ')}`)
}

const REPO_ROOT = findRepoRoot(__dirname)
const BACKEND_FACTS = join(REPO_ROOT, 'backend', 'tests', 'test_g0_source_template_facts.py')
const G0_DIR = join(
  REPO_ROOT,
  'audit-platform',
  'frontend',
  'src',
  'components',
  'workpaper',
  'g0-confirmation',
)

/** 去注释（块 + 行 + HTML）—— 登记表与被验证源码的注释里都写着反例字样，不剥必假绿 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

function readG0(rel: string): string {
  const p = join(G0_DIR, rel)
  if (!existsSync(p)) throw new Error(`平台实现文件不存在：${rel}`)
  return readFileSync(p, 'utf-8')
}

const BACKEND_SRC = readFileSync(BACKEND_FACTS, 'utf-8')

/**
 * 缺陷 id ↔ 后端存在性用例名（**声明式**交叉锁）。
 *
 * 这张表是「双向守卫」的连接键：登记表少一条、后端少一个用例、或两侧对不上，都会红。
 */
const BACKEND_TEST_BY_ID: Readonly<Record<string, string>> = Object.freeze({
  'directory-serial': 'test_defect_directory_serial_hardcoded',
  'matrix-sumif-range': 'test_defect_matrix_sumif_row_overflow',
  'xref-reliability': 'test_defect_xref_reliability_points_to_g0_6',
  'xref-followup-self': 'test_defect_entity_verify_self_reference',
  'securities-mv-diff-direction': 'test_defect_securities_market_value_diff_direction',
  'reply-amount-group-header-shift': 'test_defect_reply_amount_group_header_shifted',
  'alt-total-sums-index-column': 'test_defect_alt_total_sums_index_column',
  'alt-abnormal-dv-offset': 'test_defect_alt_abnormal_dv_offset',
  'tab-index-typos': 'test_defect_tab_index_typos_count',
})

/** 取后端 `TestSourceDefectsExist` 类体（花括号/缩进配对，不用固定字符窗口） */
function backendDefectClassBody(): string {
  const i = BACKEND_SRC.indexOf('class TestSourceDefectsExist')
  expect(i).toBeGreaterThan(0)
  // 下一个顶层 `class ` 即为边界
  const j = BACKEND_SRC.indexOf('\nclass ', i + 1)
  return BACKEND_SRC.slice(i, j > 0 ? j : BACKEND_SRC.length)
}

// ════════════════════════════════════════════════════════════════════════════
describe('Property 24 — 登记表结构与两侧连接键', () => {
  it('恰 7 条、id 唯一、数量常量与实际一致', () => {
    expect(G0_SOURCE_DEFECTS).toHaveLength(G0_SOURCE_DEFECT_COUNT)
    expect(G0_SOURCE_DEFECT_COUNT).toBe(9)
    const ids = G0_SOURCE_DEFECTS.map((d) => d.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('每条都有非空 anchor / defect / intent / intentEvidence / uiNote（禁占位登记）', () => {
    for (const d of G0_SOURCE_DEFECTS) {
      expect(d.anchor.trim().length).toBeGreaterThan(0)
      // 🔴 长度闸：H0 那轮出现过「理由 2 字」的占位登记 → 此处设下限使占位必红
      expect(d.defect.trim().length, `${d.id} 的 defect 描述过短`).toBeGreaterThanOrEqual(20)
      expect(d.intent.trim().length, `${d.id} 的 intent 过短`).toBeGreaterThanOrEqual(8)
      expect(
        d.intentEvidence.trim().length,
        `${d.id} 缺少「判定这是缺陷而非有意」的旁证`,
      ).toBeGreaterThanOrEqual(20)
      expect(d.uiNote.trim().length, `${d.id} 的 uiNote 过短`).toBeGreaterThanOrEqual(10)
    }
  })

  it('handling 取值域恰为三态，且每态都有条目（三态都在用，非死枚举）', () => {
    const allowed: G0DefectHandling[] = [
      'implement-intent',
      'display-as-is',
      'index-label-correction',
    ]
    const used = new Set(G0_SOURCE_DEFECTS.map((d) => d.handling))
    for (const h of used) expect(allowed).toContain(h)
    for (const h of allowed) {
      expect(used.has(h), `handling '${h}' 无任何条目 = 死枚举`).toBe(true)
    }
  })

  it('(a) 源侧：每条 id 在后端存在性守卫里都有对应用例，且两侧数量相等', () => {
    const body = backendDefectClassBody()
    const backendTests = [...body.matchAll(/def (test_defect_\w+)\(/g)].map((m) => m[1])
    // 抽取非空自检（防正则失效导致断言空转）
    expect(backendTests.length).toBeGreaterThan(0)
    expect(backendTests).toHaveLength(G0_SOURCE_DEFECT_COUNT)

    for (const d of G0_SOURCE_DEFECTS) {
      const expected = BACKEND_TEST_BY_ID[d.id]
      expect(expected, `缺陷 ${d.id} 未在 BACKEND_TEST_BY_ID 登记连接键`).toBeTruthy()
      expect(backendTests, `后端缺少 ${d.id} 的存在性用例`).toContain(expected)
    }
    // 反向：后端不得有本表未登记的缺陷用例（孤儿断言）
    expect(new Set(Object.values(BACKEND_TEST_BY_ID))).toEqual(new Set(backendTests))
  })

  it('(b) 平台侧：每条 platformEvidence 指向的文件存在且含该符号', () => {
    for (const d of G0_SOURCE_DEFECTS) {
      expect(d.platformEvidence.length, `${d.id} 未给出平台处置证据`).toBeGreaterThan(0)
      for (const ev of d.platformEvidence) {
        const [rel, symbol] = ev.split('#')
        expect(symbol, `platformEvidence 格式应为 '文件#符号'：${ev}`).toBeTruthy()
        const src = stripComments(readG0(rel))
        expect(src, `${d.id}：${rel} 中找不到符号 ${symbol}`).toContain(symbol)
      }
    }
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 24 — display-as-is：原文逐字保留 + 加标注', () => {
  const displayAsIs = G0_SOURCE_DEFECTS.filter((d) => d.handling === 'display-as-is')

  it('display-as-is 条目必须给 sourceText（守卫据此比对平台展示）', () => {
    expect(displayAsIs.length).toBeGreaterThan(0)
    for (const d of displayAsIs) {
      expect(d.sourceText, `${d.id} 缺 sourceText`).toBeTruthy()
      expect(d.sourceText!.trim().length).toBeGreaterThan(0)
    }
  })

  it('xref-reliability：审计说明第 3 项标题与源原文逐字相等（含「（G0-6）」笔误）', () => {
    const d = g0SourceDefect('xref-reliability')
    const reliability = G0_AUDIT_NOTE_DEFS.find((x) => x.key === 'reliability')
    expect(reliability).toBeTruthy()
    // 平台展示 == 源原文（禁「顺手修正」为 G0-7）
    expect(reliability!.title).toBe(d.sourceText)
    expect(reliability!.title).toContain('（G0-6）')
    expect(reliability!.titleAnchor).toBe('S24')
    // 标注存在且指出正确去向
    expect(d.uiNote).toContain('G0-7')
    expect(d.uiNote).toContain('笔误')
  })

  it('xref-reliability / xref-followup-self 的 sourceText 与后端断言的字面逐字一致', () => {
    // 后端：`assert "（G0-6）" in text` + `assert "可靠性" in text`
    const rel = g0SourceDefect('xref-reliability').sourceText!
    expect(rel).toContain('（G0-6）')
    expect(rel).toContain('可靠性')

    // 后端：`assert text == "跟函函证控制过程（G0-2）"` —— 从 py 源码抽字面比对
    const m = BACKEND_SRC.match(/text\s*==\s*"(跟函函证控制过程（G0-2）)"/)
    expect(m, '未能在后端守卫里定位 G0-2!AA6 的字面断言').toBeTruthy()
    expect(g0SourceDefect('xref-followup-self').sourceText).toBe(m![1])
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 24 — index-label-correction：定位/展示分离', () => {
  it('三处 tab 名笔误在 sheet 注册表里都有 indexTypoNote，展示值为 G0-4/G0-5/G0-8', () => {
    const withTypo = Object.values(G0_SHEET_REGISTRY).filter((r) => r?.indexTypoNote)
    expect(withTypo).toHaveLength(3)
    expect(withTypo.map((r) => r!.indexLabel).sort()).toEqual(['G0-4', 'G0-5', 'G0-8'])
    for (const r of withTypo) {
      // 定位值仍是源 tab 名（不含修正后的索引号）
      expect(r!.sheetName).not.toContain(r!.indexLabel)
      expect(r!.indexTypoNote!.trim().length).toBeGreaterThan(0)
    }
  })

  it('登记表的 tab-index-typos 条目与注册表条数一致（两侧不可各自漂移）', () => {
    const d = g0SourceDefect('tab-index-typos')
    expect(d.handling).toBe('index-label-correction')
    const withTypo = Object.values(G0_SHEET_REGISTRY).filter((r) => r?.indexTypoNote)
    for (const r of withTypo) {
      expect(d.anchor, `注册表里的 ${r!.sheetName} 未出现在缺陷 anchor 里`).toContain(r!.sheetName)
    }
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 27 — 证券差异 M 列方向按意图统一为「账面 − 回函」', () => {
  it('源侧缺陷仍在：后端断言 M7 = `=J7-G7`，而同组 K7/L7 为账面 − 回函', () => {
    // 缺陷存在性是本 Property 的前提；一旦源模板被改动（缺陷消失），本断言打红提醒复核 spec
    expect(BACKEND_SRC).toContain('"M7") == "=J7-G7"')
    expect(BACKEND_SRC).toContain('"K7") == "=E7-H7"')
    expect(BACKEND_SRC).toContain('"L7") == "=F7-I7"')
  })

  it('平台侧三个差异函数同向且方向为「账面 − 回函」', () => {
    // 账面 > 回函 → 正差异
    expect(calcQuantityDiff(10_000, 9_800)).toBe(200)
    expect(calcFairValueDiff(12.5, 12.0)).toBeCloseTo(0.5, 6)
    expect(calcMarketValueDiff(125_000, 117_600)).toBeCloseTo(7_400, 6)
    // 同向性：同一对 (2,1) 三者符号一致
    expect([
      Math.sign(calcQuantityDiff(2, 1)),
      Math.sign(calcFairValueDiff(2, 1)),
      Math.sign(calcMarketValueDiff(2, 1)),
    ]).toEqual([1, 1, 1])
  })

  it('反向自检：若任一函数回退为「回函 − 账面」，本断言必红', () => {
    // 旧方向下 calcMarketValueDiff(125000, 117600) 会是 -7400
    expect(calcMarketValueDiff(125_000, 117_600)).toBeGreaterThan(0)
    expect(calcQuantityDiff(9_800, 10_000)).toBeLessThan(0)
  })

  it('方向文案单一真源：组件不各写一份「账面 − 回函」字面', () => {
    expect(G0_DIFF_DIRECTION_LABEL).toBe('账面 − 回函')
    expect(G0_DIFF_DIRECTION_HINT).toContain(G0_DIFF_DIRECTION_LABEL)
    expect(G0_DIFF_DIRECTION_HINT).toContain('③=①−②')

    const vue = stripComments(
      readG0(join('diffSecurities', 'GtConfirmationDiffSecurities.vue')),
    )
    // 引用共享常量而非硬写字面
    expect(vue).toContain('G0_DIFF_DIRECTION_HINT')
    // 旧方向文案不得复活
    expect(vue).not.toContain('回函数量 − 账面数量')
    expect(vue).not.toContain('回函公允价值 − 账面余额')
  })

  it('公式引擎的形参命名已改为账面在前（防调用方颠倒实参）', () => {
    const engine = stripComments(readG0(join('composables', 'useG0FormulaEngine.ts')))
    expect(engine).toContain('bookedQty')
    expect(engine).toContain('replyQty')
    expect(engine).not.toContain('confirmed - booked')
  })

  /**
   * 🔴 Task 23 浏览器实测补强（2026-08-04）：Task 20 改了三个派生函数的方向，
   * 但证券差异表的**组表头字面**遗留旧方向 `差异（②−①）` → 界面上「表头说 ②−①、
   * 数值却按 ①−② 算」自相矛盾，而 `get_diagnostics` / vitest / Vite 全绿，
   * 只有浏览器打开该 sheet 才看得见。故把表头方向也纳入守卫。
   */
  it('证券差异表的组表头方向与派生方向一致（①−②，不得残留 ②−①）', () => {
    const vue = stripComments(
      readG0(join('diffSecurities', 'GtConfirmationDiffSecurities.vue')),
    )
    // 三段组表头方向标注：账面①、回函②、差异①−②
    expect(vue).toContain('label="账面数（①）"')
    expect(vue).toContain('label="回函数（②）"')
    expect(vue).toContain('label="差异（①−②）"')
    // 旧方向字面不得复活（半角/全角减号两种写法都拦）
    expect(vue).not.toContain('差异（②−①）')
    expect(vue).not.toContain('差异（②-①）')
  })

  it('反向自检：组表头方向断言不是恒真（对内联 fixture 复现旧字面必判红）', () => {
    const legacyFixture = '<el-table-column label="差异（②−①）" align="center">'
    // 复现改造前的字面 → 与上一条用的同一判据必须判否
    expect(legacyFixture.includes('差异（①−②）')).toBe(false)
    expect(legacyFixture.includes('差异（②−①）')).toBe(true)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 13 — 登记表有真实消费方（零消费方即未交付）', () => {
  it('下区组件集中展示 7 条缺陷', () => {
    const vue = stripComments(readG0('G0SummaryLowerZone.vue'))
    expect(vue).toContain('g0SourceDefects')
    expect(vue).toContain('SOURCE_DEFECTS')
    // 集中展示区确实遍历了登记表
    expect(vue).toMatch(/v-for="d in SOURCE_DEFECTS"/)
    // 审计说明第 3 项挂了笔误标注
    expect(vue).toContain('defectNoteOf')
  })

  it('证券差异表消费了缺陷说明（M 列方向 tooltip）', () => {
    const vue = stripComments(readG0(join('diffSecurities', 'GtConfirmationDiffSecurities.vue')))
    expect(vue).toContain('g0DefectUiNote')
    expect(vue).toContain('securities-mv-diff-direction')
  })

  it('g0DefectUiNote 对已登记 id 返回文案、对未登记 id 返回空串（UI 不崩）', () => {
    expect(g0DefectUiNote('securities-mv-diff-direction').length).toBeGreaterThan(0)
    expect(g0DefectUiNote('not-registered-at-all')).toBe('')
    // 严格取用则抛错（供内部逻辑用）
    expect(() => g0SourceDefect('not-registered-at-all')).toThrow(/未登记的缺陷 id/)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('反向自检（防断言空转）', () => {
  it('stripComments 确实剥掉注释里的反例字样（内联 fixture，不依赖真实文件）', () => {
    const fixture = [
      '// 旧方向：回函数量 − 账面数量',
      '/* 旧实现 confirmed - booked */',
      '<!-- 回函公允价值 − 账面余额 -->',
      'const keep = "账面 − 回函"',
    ].join('\n')
    const out = stripComments(fixture)
    expect(out).not.toContain('回函数量 − 账面数量')
    expect(out).not.toContain('confirmed - booked')
    expect(out).not.toContain('回函公允价值 − 账面余额')
    expect(out).toContain('账面 − 回函')
    // 不得把 URL 里的 `//` 当行注释
    expect(stripComments('const u = "https://x.test/a"')).toContain('https://x.test/a')
  })

  it('两个源码文件确实被读到（非空且含预期锚点）', () => {
    expect(BACKEND_SRC.length).toBeGreaterThan(1000)
    expect(BACKEND_SRC).toContain('class TestSourceDefectsExist')
    expect(readG0('g0SourceDefects.ts').length).toBeGreaterThan(1000)
  })

  it('后端类体切分未越界到下一个 class', () => {
    const body = backendDefectClassBody()
    expect(body).toContain('test_defect_directory_serial_hardcoded')
    // 下一个类的用例不得混进来
    expect(body).not.toContain('test_selfcheck_leaf_column_count_is_asserted')
  })
})
