/**
 * 交付件能力门控守卫 — deliverable-lineage-wiring-and-writeback-closure Task 9.1
 *
 * Property 11：能力矩阵前后端一致 —— 前端**只消费**后端下发的布尔，
 *   禁止自己再写一份 doc_type 白名单（双真源一旦分叉，改一处另一处不红）。
 * Property 12：章节状态为空时显示「无锚点」提示且不渲染空下拉。
 *
 * 手法为**源码级**断言：门控写在模板 `v-if` 上，挂载测试要拉起 OnlyOffice
 * iframe 与整条 API 链（既有 OnlyOfficeEditor.spec.ts 已因此有 2 例预存在失败），
 * 源码断言更稳且能直接钉住「有没有在前端重写白名单」这类结构性问题。
 */
import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'

// ── 仓库根定位：哨兵**文件**向上查找（禁写死回退级数；哨兵不能用目录，
// audit-platform/backend/app/routers 是历史遗留空目录会提前停下）
function repoRoot(): string {
  let dir = resolve(__dirname)
  for (let i = 0; i < 12; i += 1) {
    if (existsSync(join(dir, 'backend', 'app', 'services', 'deliverable_capabilities.py'))) {
      return dir
    }
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error('未能定位仓库根（哨兵 backend/app/services/deliverable_capabilities.py 未找到）')
}

const ROOT = repoRoot()

function readSrc(rel: string): string {
  const p = join(ROOT, rel)
  const text = readFileSync(p, 'utf-8')
  expect(text.length, `${rel} 读取为空`).toBeGreaterThan(0)
  return text
}

const CAPABILITIES_PY = readSrc('backend/app/services/deliverable_capabilities.py')
const EDITOR = readSrc('audit-platform/frontend/src/components/deliverable/OnlyOfficeEditor.vue')
const CENTER = readSrc('audit-platform/frontend/src/views/DeliverableCenter.vue')
const PANEL = readSrc('audit-platform/frontend/src/components/deliverable/LineagePanel.vue')
const API = readSrc('audit-platform/frontend/src/services/deliverableApi.ts')

/** 从 python frozenset 字面量抽取字符串成员（按 ASCII 括号配对，不用行尾正则）。 */
function pyFrozenSetMembers(src: string, name: string): string[] {
  const declIdx = src.indexOf(`${name}: Final[frozenset[str]] = frozenset(`)
  expect(declIdx, `后端未找到常量 ${name}`).toBeGreaterThan(-1)
  const open = src.indexOf('(', declIdx + name.length)
  let depth = 0
  let end = -1
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === '(') depth += 1
    else if (src[i] === ')') {
      depth -= 1
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  expect(end, `${name} 括号未配对`).toBeGreaterThan(open)
  const body = src.slice(open + 1, end)
  return [...body.matchAll(/"([^"]+)"/g)].map((m) => m[1])
}

/** 剥 JS/TS 注释（守卫注释里会写反例，不剥会把说明文字数成真实代码）。 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

describe('Property 11: 能力矩阵前后端一致（单一真源在后端）', () => {
  it('后端能力集合 = 附注 + 报告正文（仅回填），且显式禁止 financial_report*', () => {
    const writeback = pyFrozenSetMembers(CAPABILITIES_PY, 'WRITEBACK_SUPPORTED_DOC_TYPES')
    const refresh = pyFrozenSetMembers(CAPABILITIES_PY, 'SECTION_REFRESH_SUPPORTED_DOC_TYPES')
    const forbidden = pyFrozenSetMembers(CAPABILITIES_PY, 'WRITEBACK_FORBIDDEN_DOC_TYPES')

    // Wave 3（Task 18）把 audit_report 加入**回填**能力：报告正文段落可回填到
    // `report_body_json`。但**不加**章节刷新 —— 报告正文内容来自 Word 模板占位符
    // 填充，按上游重算等于重新生成整份，不存在"刷新单个章节"的语义。
    expect([...writeback].sort()).toEqual(['audit_report', 'disclosure_notes'])
    expect(refresh).toEqual(['disclosure_notes'])
    expect(forbidden).toContain('financial_report')
    // 交集必须为空：报表数字只能由试算表 + 调整分录派生
    expect(writeback.filter((t) => forbidden.includes(t))).toEqual([])
    expect(refresh.filter((t) => forbidden.includes(t))).toEqual([])
  })

  it('DTO 两个能力字段已在前端 API 类型中声明', () => {
    expect(API).toMatch(/supports_writeback\?*:\s*boolean/)
    expect(API).toMatch(/supports_section_refresh\?*:\s*boolean/)
  })

  it('DeliverableCenter 把后端能力布尔透传给编辑器（不是自己算）', () => {
    const src = stripComments(CENTER)
    expect(src).toContain(':supports-writeback="editorItem.supports_writeback === true"')
    expect(src).toContain(
      ':supports-section-refresh="editorItem.supports_section_refresh === true"',
    )
  })

  it('OnlyOfficeEditor 的回填面板按 supportsWriteback 门控，刷新能力向下透传', () => {
    const src = stripComments(EDITOR)
    expect(src).toMatch(/<WritebackResultPanel[\s\S]{0,200}?v-if="supportsWriteback"/)
    expect(src).toContain(':supports-section-refresh="supportsSectionRefresh"')
  })

  it('前端不得重写 doc_type 能力白名单（只允许在展示文案里判断类型）', () => {
    // 允许：writebackUnsupportedTitle 里按 docType 定制**文案**
    // 禁止：用 docType 决定「是否渲染回填入口」
    const src = stripComments(EDITOR)
    const gateLines = src
      .split('\n')
      .filter((l) => /v-if=|v-show=/.test(l))
      .filter((l) => /docType|doc_type|disclosure_notes|financial_report/.test(l))
    expect(
      gateLines,
      `门控条件里出现 doc_type 判断 = 前端重写了能力白名单（双真源）:\n${gateLines.join('\n')}`,
    ).toEqual([])
  })

  it('反向自检：把 financial_report 加进后端集合则前端门控失去意义', () => {
    // 复现「后来者顺手把报表加进白名单」的旧行为 —— 断言 FORBIDDEN 是真实屏障，
    // 不是注释里的君子协定（它被 backend/tests/test_deliverable_capabilities_matrix.py 消费）
    expect(CAPABILITIES_PY).toContain('WRITEBACK_FORBIDDEN_DOC_TYPES')
    expect(CAPABILITIES_PY).toMatch(/financial_report/)
  })
})

describe('Property 12: 无章节状态时给出明确提示', () => {
  it('OnlyOfficeEditor 由 section-states 结果驱动 hasNoAnchors（非死 prop）', () => {
    const src = stripComments(EDITOR)
    expect(src).toContain('fetchSectionStates')
    // 必须有真实赋值语句，而非只声明 ref(false)
    expect(src).toMatch(/hasNoAnchors\.value\s*=\s*states\.length === 0/)
    expect(src).toContain(':has-no-anchors="hasNoAnchors"')
  })

  it('LineagePanel 无锚点时渲染中文提示，且提示与「未选章节」提示互斥', () => {
    const src = stripComments(PANEL)
    expect(src).toMatch(/v-if="noAnchorAvailable"/)
    expect(src).toContain('该出品物版本不支持溯源，请重新生成')
    // 「未选中章节」分支必须是 v-else-if，否则两条提示会同时出现
    expect(src).toMatch(/v-else-if="!currentSectionCode && !noAnchorAvailable"/)
  })

  it('章节下拉为空时不凭空造选项（fail-open 到空数组）', () => {
    const src = stripComments(PANEL)
    expect(src).toMatch(/sectionOptions\.value\s*=\s*\[\]/)
    expect(src).toMatch(/data\?\.sections \|\| \[\]/)
  })

  it('反向自检：hasNoAnchors 若只有 ref(false) 声明则本组守卫必须打红', () => {
    const src = stripComments(EDITOR)
    const declOnly = /const hasNoAnchors = ref\(false\)/.test(src)
    const assigned = /hasNoAnchors\.value\s*=/.test(src)
    expect(declOnly && !assigned, '历史缺陷：hasNoAnchors 声明后从不赋值 = 死 prop').toBe(false)
  })
})
