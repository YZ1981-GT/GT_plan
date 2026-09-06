// d4FourTableWiring.spec.ts — D4 营业收入源码级守卫
//
// Properties asserted (after stripComments on source):
// - 无写死科目码: d4/ 下 .vue + composables/d4*.ts + composables/useD4*.ts 不含
//   字面 '6001'/'6051'/'6401'/'6402' 作科目码参数（应导入自 d4AccountScope.ts）
// - 无自调度: syncToDisclosureNotes 函数体不含 scheduleAutoSync(syncToDisclosureNotes)
// - 金额控件归零: 两个披露 Tab 剩余 el-input type="number" 用于金额的计数为 0
// - AI 四处齐备: 每个前端 AI target 有后端 _SECTION_PROMPTS 条目
// - Builder 零入参: buildD4TwoPeriodColumns / buildD4TransposeColumns / buildD4ObligationColumns
//   可零入参调用且返回有效列集
// - D4 不引入账龄档位 (Property 28): D4 源文件不 import disclosureAgingLabels / useAgingConfig
//
// 🔴 先 stripComments() 再扫描（Req 9.9: 守卫注释里通常含被禁字样反例）
// + 反向自检（assert stripComments 确实剥掉了什么）
//
// Validates: Requirements 9.5, 9.6, 9.8, 9.9
//
// spec: .kiro/specs/d4-four-table-extraction-and-disclosure-alignment/ Task 7.4
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve, join } from 'node:path'

import {
  buildD4TwoPeriodColumns,
  buildD4TransposeColumns,
  buildD4ObligationColumns,
} from '../d4DisclosureModel'
import {
  D4_LISTED_AI_TARGETS,
  D4_SOE_AI_TARGETS,
} from '../useD4DisclosureAi'

// ─── helpers ─────────────────────────────────────────────────────────────────

const ROOT = resolve(__dirname, '../..')
const COMPOSABLES = resolve(ROOT, 'composables')
const D4_DIR = resolve(ROOT, 'd4')

function read(rel: string): string {
  return readFileSync(resolve(ROOT, rel), 'utf-8')
}

/** 去掉注释后再做「源码不得出现 xxx」类断言（Req 9.9 踩坑铁律） */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/** 递归收集目录下所有 .vue / .ts 文件路径（相对 ROOT） */
function collectFiles(dir: string, exts: string[]): string[] {
  const result: string[] = []
  function walk(d: string) {
    for (const entry of readdirSync(d, { withFileTypes: true })) {
      const full = join(d, entry.name)
      if (entry.isDirectory()) {
        if (entry.name === '__tests__' || entry.name === 'node_modules') continue
        walk(full)
      } else if (exts.some(e => entry.name.endsWith(e))) {
        // Convert to relative from ROOT using '/'
        const rel = full.slice(ROOT.length + 1).replace(/\\/g, '/')
        result.push(rel)
      }
    }
  }
  walk(dir)
  return result
}

// D4 前端文件集合（d4/**/*.vue + composables/d4*.ts + composables/useD4*.ts）
// 🔴 排除 d4AccountScope.ts —— 它是常量的单一真源，里面声明兜底码是合法的
const D4_FRONTEND_FILES: string[] = [
  ...collectFiles(D4_DIR, ['.vue']),
  ...collectFiles(COMPOSABLES, ['.ts']).filter(
    f => /composables\/(d4|useD4)[^/]*\.ts$/.test(f)
      && !f.includes('__tests__')
      && !f.includes('d4AccountScope.ts'),
  ),
]

// ─── 反向自检：stripComments 确实工作 ──────────────────────────────────────────

describe('stripComments 反向自检', () => {
  it('stripComments 能剥掉行注释和块注释', () => {
    const withComments = `
      // 这行是注释，里面有 '6001' 字面量作反例
      const x = 1 /* 块注释 '6401' */
    `
    const stripped = stripComments(withComments)
    expect(stripped).not.toContain("// 这行是注释")
    expect(stripped).not.toContain("块注释")
    // 原始源码确实含被禁字样
    expect(withComments).toContain("'6001'")
    expect(withComments).toContain("'6401'")
    // 剥掉后不含
    expect(stripped).not.toContain("'6001'")
    expect(stripped).not.toContain("'6401'")
  })

  it('D4 至少有 1 个源文件的原始内容含注释（防空扫）', () => {
    let hasComments = false
    for (const rel of D4_FRONTEND_FILES.slice(0, 10)) {
      const raw = read(rel)
      if (raw !== stripComments(raw)) {
        hasComments = true
        break
      }
    }
    expect(hasComments).toBe(true)
  })

  it('D4 前端文件集合非空（防 glob 失效空转）', () => {
    expect(D4_FRONTEND_FILES.length).toBeGreaterThan(5)
  })
})

// ─── Property: 无写死科目码 ────────────────────────────────────────────────────

describe('D4 前端源码不含写死科目码（Property 24 / Req 9.9）', () => {
  // 被禁的字面量 —— 作为科目码参数/赋值/常量/字符串比对出现
  const FORBIDDEN_ACCOUNT_PATTERNS = [
    /['"]6001['"]/,
    /['"]6051['"]/,
    /['"]6401['"]/,
    /['"]6402['"]/,
  ]

  it.each(D4_FRONTEND_FILES)(
    '%s 不含写死科目码 6001/6051/6401/6402',
    (rel) => {
      const raw = read(rel)
      const body = stripComments(raw)
      // 文件确实能读到（防路径错导致断言空转）
      expect(body.length).toBeGreaterThan(50)
      for (const pattern of FORBIDDEN_ACCOUNT_PATTERNS) {
        expect(body).not.toMatch(pattern)
      }
    },
  )
})

// ─── Property: 无自调度 ────────────────────────────────────────────────────────

describe('syncToDisclosureNotes 无自调度（Property 26 / Req 8.6）', () => {
  const DISCLOSURE_TABS = [
    'd4/core/D4TabDisclosureListed.vue',
    'd4/core/D4TabDisclosureSoe.vue',
  ]

  it.each(DISCLOSURE_TABS)(
    '%s 的 syncToDisclosureNotes 函数体内不出现 scheduleAutoSync(syncToDisclosureNotes)',
    (rel) => {
      const raw = read(rel)
      const body = stripComments(raw)
      expect(body.length).toBeGreaterThan(500)

      // 提取 syncToDisclosureNotes 函数体（从函数声明到下一个顶层函数/结束）
      const fnStart = body.indexOf('async function syncToDisclosureNotes')
      expect(fnStart).toBeGreaterThan(0) // 反向自检：确实找到了函数

      // 从函数开始位置向后找花括号配对截取函数体
      const afterStart = body.indexOf('{', fnStart)
      let depth = 0
      let fnEnd = afterStart
      for (let i = afterStart; i < body.length; i++) {
        if (body[i] === '{') depth++
        if (body[i] === '}') depth--
        if (depth === 0) { fnEnd = i; break }
      }
      const fnBody = body.slice(afterStart, fnEnd + 1)

      // 核心断言：函数体内不得调度自己
      expect(fnBody).not.toMatch(/scheduleAutoSync\s*\(\s*syncToDisclosureNotes\s*\)/)
    },
  )
})

// ─── Property: 金额控件归零 ──────────────────────────────────────────────────

describe('D4 披露 Tab 金额控件归零（Property 24 / Req 8.1, 8.2）', () => {
  const DISCLOSURE_TABS = [
    'd4/core/D4TabDisclosureListed.vue',
    'd4/core/D4TabDisclosureSoe.vue',
  ]

  it.each(DISCLOSURE_TABS)(
    '%s 无裸 el-input type="number" 用于金额 & 无自造 toLocaleString',
    (rel) => {
      const raw = read(rel)
      const body = stripComments(raw)
      expect(body.length).toBeGreaterThan(500)

      // 计数 el-input type="number"
      const elInputNumberMatches = body.match(/el-input[^>]*type\s*=\s*["']number["']/g)
      expect(
        elInputNumberMatches?.length ?? 0,
        `${rel} 仍有 ${elInputNumberMatches?.length} 个裸 el-input type="number"，应全部改为 WpAmountInput`,
      ).toBe(0)

      // 禁 toLocaleString（应走 displayPrefs.fmtAmount）
      expect(body).not.toMatch(/toLocaleString/)
    },
  )
})

// ─── Property: AI 四处齐备 ──────────────────────────────────────────────────

describe('AI 四处齐备（Property 25 / Req 8.3, 8.4）', () => {
  // 后端 _SECTION_PROMPTS 文件
  const BACKEND_AI_FILE = resolve(
    ROOT, '../../../../../../backend/app/routers/wp_render_strategies/_d4_ai_generate.py',
  )

  it('每个 D4_LISTED_AI_TARGETS 条目在后端 _SECTION_PROMPTS 有对应', () => {
    let backendSrc: string
    try {
      backendSrc = readFileSync(BACKEND_AI_FILE, 'utf-8')
    } catch {
      // 如果路径调整导致找不到，跳过（CI 上后端在同级目录）
      const altPath = resolve(ROOT, '../../../../../backend/app/routers/wp_render_strategies/_d4_ai_generate.py')
      backendSrc = readFileSync(altPath, 'utf-8')
    }

    // 反向自检：文件确实含 _SECTION_PROMPTS
    expect(backendSrc).toContain('_SECTION_PROMPTS')

    // 前端 targets 非空
    expect(D4_LISTED_AI_TARGETS.length).toBe(8)
    expect(D4_SOE_AI_TARGETS.length).toBe(7)

    // 检查后端 _SUPPORTED_SECTIONS 包含全部前端 target 的 section id
    // _SUPPORTED_SECTIONS 通常以 list 或 set 声明全部合法 section
    for (const target of D4_LISTED_AI_TARGETS) {
      // target 形如 'd4-disc-note-1'，后端 section id 可能是相同字符串或映射
      // 只验证后端文件提及了该 section 标识（字面量或等价常量）
      const noteNumber = target.replace('d4-disc-note-', '')
      // 后端至少要有对应的条目（精确形式由实现决定）
      expect(
        backendSrc.includes(target) || backendSrc.includes(`note-${noteNumber}`) || backendSrc.includes(`"${target}"`),
        `后端缺少 ${target} 对应的 prompt/section 登记`,
      ).toBe(true)
    }
  })

  it('国企 SOE 版是上市版去掉 note-8（试运行销售收入仅上市）', () => {
    expect(D4_SOE_AI_TARGETS).not.toContain('d4-disc-note-8')
    // SOE = Listed 的前 7 条
    for (const t of D4_SOE_AI_TARGETS) {
      expect(D4_LISTED_AI_TARGETS).toContain(t)
    }
  })
})

// ─── Property: builder 零入参可调 ──────────────────────────────────────────────

describe('buildD4*Columns 零入参可调（Property 27 / Req 9.5, 9.6）', () => {
  // 🔴 2026-09-06：表态判据由**按列**改为**按表**。
  // `flat` 是表级语义（后端 `_extract_column_groups`：任一列带 flat 即整表
  // `return []` 禁分组），按列要求每列都有 group 或 flat 会逼两级表头表在标签列
  // 补 flat，从而整表 group 全部失效、两级表头渲染不出来。
  it('buildD4TwoPeriodColumns() 零参返回有效列集且整表表态', () => {
    const cols = buildD4TwoPeriodColumns()
    expect(cols.length).toBeGreaterThan(2)
    for (const col of cols) expect(col.key).toBeTruthy()
    const hasGroup = cols.some(c => !!c.group)
    const hasFlat = cols.some(c => c.flat === true)
    expect(hasGroup || hasFlat).toBe(true)
    expect(hasGroup && hasFlat, 'flat 与 group 同表并存 → flat 会整表抑制分组').toBe(false)
  })

  it('buildD4TransposeColumns() 零参返回有效列集且整表表态', () => {
    const cols = buildD4TransposeColumns()
    expect(cols.length).toBeGreaterThan(2)
    for (const col of cols) expect(col.key).toBeTruthy()
    const hasGroup = cols.some(c => !!c.group)
    const hasFlat = cols.some(c => c.flat === true)
    expect(hasGroup || hasFlat).toBe(true)
    expect(hasGroup && hasFlat).toBe(false)
  })

  it('buildD4ObligationColumns() 零参返回有效列集', () => {
    const cols = buildD4ObligationColumns()
    expect(cols.length).toBeGreaterThan(2)
    for (const col of cols) {
      expect(col.key).toBeTruthy()
      // 年度列与合计列可以是 flat
      expect(col.group || col.flat).toBeTruthy()
    }
  })
})

// ─── Property 28: D4 不引入账龄档位 ────────────────────────────────────────────

describe('D4 不引入账龄档位（Property 28 / Design §账龄枚举说明）', () => {
  it.each(D4_FRONTEND_FILES)(
    '%s 不 import disclosureAgingLabels / useAgingConfig',
    (rel) => {
      const raw = read(rel)
      const body = stripComments(raw)
      expect(body.length).toBeGreaterThan(10)
      expect(body).not.toMatch(/disclosureAgingLabels/)
      expect(body).not.toMatch(/useAgingConfig/)
    },
  )
})
