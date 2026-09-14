/**
 * 平台级守卫：宿主的 **sheet 分发链**不得被「非 sheet 条件」的裸 `v-if` 打断。
 *
 * **抓到的真实事故（2026-08-03 浏览器实测）**
 *
 * 11 个宿主（H5/H6/H8/H9/H10 / I1~I6）把 `HiFourTableSourcePanel` 写成::
 *
 *     <XTabIndex           v-if="currentSheet === 'X'" />
 *     <CycleTabProcedure   v-else-if="currentSheet === 'XA'" />
 *     <HiFourTableSourcePanel v-if="props.htmlData?.hi_extraction_enabled" />  ← 断链
 *     <XTabAdjudication    v-else-if="currentSheet === 'X-1'" />
 *     <XTabDetail          v-else-if="currentSheet === 'X-2'" />
 *     ...
 *
 * `v-if` 开启**新链** → `hi_extraction_enabled` 为真时面板胜出，
 * 它之后按 `currentSheet` 分发的**全部 `v-else-if` 成为死分支**（实测 140 个）
 * → 审定表 / 两个披露 Tab / 各明细表一律渲染不出来。
 *
 * `HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 于 2026-08-02 翻 True 后全量生效。
 *
 * 🔴 四层验证全部查不出：Vue 编译器对「v-if 打断 v-else-if 链」不报错
 * （语法完全合法）、`get_diagnostics` 零诊断、Vite transform 200、
 * vitest 不覆盖模板分发。**只有浏览器打开对应 Tab 才暴露。**
 *
 * **判据（刻意收窄，避免误报）**：只看条件里提到 `currentSheet` 的分发链 ——
 * 某个 `v-else-if="currentSheet === ..."` 的**紧前同级兄弟**若是
 * 「条件不含 `currentSheet` 的 `v-if`」，即为断链。
 * 表格列内部的 `v-if/v-else-if`（条件是 `row.xxx` 之类）天然不参与判定。
 *
 * 正解 = 用 `<template v-else-if="currentSheet === ...">` 包住
 * 「附加面板 + 该 sheet 内容」（`GtH7BiologicalAssets.vue` 是范式，它一直是对的）。
 * 批量修复脚本 `backend/scripts/fix/fix_hi_source_panel_vif_chain.py`。
 *
 * spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

// 本文件位于 .../components/workpaper/__tests__/ → 回仓库根需 6 级
const REPO_ROOT = path.resolve(__dirname, '../../../../../..')
const WP_DIR = path.join(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper')

/** 分发变量名（各宿主统一用它做 sheet 分发） */
const DISPATCH_VAR = 'currentSheet'

interface DirectiveTag {
  tag: string
  line: number
  indent: number
  kind: 'if' | 'else-if' | 'else'
  cond: string
}

/** 剥 HTML 注释（注释里会写反例片段，不剥必误判） */
function stripHtmlComments(src: string): string {
  return src.replace(/<!--[\s\S]*?-->/g, '')
}

/** 取 `<template>` 段（`<script>` 里的字符串不参与判定） */
function templateSection(src: string): string {
  const m = src.match(/^<template>([\s\S]*?)\n<\/template>/m)
  return m ? m[1] : src
}

/** 收集所有带 v-if / v-else-if / v-else 的标签起始行 */
export function collectDirectiveTags(tpl: string): DirectiveTag[] {
  const lines = tpl.split('\n')
  const out: DirectiveTag[] = []
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^(\s*)<([A-Za-z][\w.-]*)/)
    if (!m) continue
    // 取该标签的属性块（到 `/>` 或 `>` 结束）
    const block: string[] = []
    for (let j = i; j < Math.min(i + 40, lines.length); j++) {
      block.push(lines[j])
      const s = lines[j].trimEnd()
      if (s.endsWith('/>') || s.endsWith('>')) break
    }
    const btxt = block.join('\n')
    const elseIf = btxt.match(/v-else-if\s*=\s*"([^"]*)"/)
    if (elseIf) {
      out.push({ tag: m[2], line: i + 1, indent: m[1].length, kind: 'else-if', cond: elseIf[1] })
      continue
    }
    if (/\bv-else(?![\w-])/.test(btxt)) {
      out.push({ tag: m[2], line: i + 1, indent: m[1].length, kind: 'else', cond: '' })
      continue
    }
    const vIf = btxt.match(/v-if\s*=\s*"([^"]*)"/)
    if (vIf) {
      out.push({ tag: m[2], line: i + 1, indent: m[1].length, kind: 'if', cond: vIf[1] })
    }
  }
  return out
}

export interface ChainBreak {
  tag: string
  line: number
  cond: string
  /** 被打死的 `currentSheet` 分支数 */
  dead: number
}

/**
 * 找出「非 sheet 条件的裸 v-if 打断 currentSheet 分发链」的位置。
 *
 * 只在同缩进层级判定，且要求断链前后都存在 `currentSheet` 分支
 * （前有链、后有被打死的分支）。
 */
export function findSheetChainBreaks(tpl: string): ChainBreak[] {
  const tags = collectDirectiveTags(tpl)
  const breaks: ChainBreak[] = []

  for (let i = 0; i < tags.length; i++) {
    const cur = tags[i]
    if (cur.kind !== 'if') continue
    if (cur.cond.includes(DISPATCH_VAR)) continue // 自己就是 sheet 条件 → 是合法新链首

    // 紧前同级兄弟必须是 **v-else-if 形态的 sheet 分发分支** —— 只有 `else-if`
    // 才能证明「链已经在这里了」。若前一个是 `v-if`，它可能只是个独立条件块
    // （如工具栏 `<div v-if="isHtmlSheet && currentSheet !== 'N4'">`），
    // 此时当前 `v-if` 是**合法链首**（OnlyOffice 双模式短路即此形态），不得误报。
    let prev: DirectiveTag | null = null
    for (let k = i - 1; k >= 0; k--) {
      if (tags[k].indent === cur.indent) {
        prev = tags[k]
        break
      }
    }
    if (!prev || prev.kind !== 'else-if') continue
    if (!prev.cond.includes(DISPATCH_VAR)) continue

    // 其后同级还有 sheet 分发的 v-else-if → 那些全部成死分支
    let dead = 0
    for (let k = i + 1; k < tags.length; k++) {
      const t = tags[k]
      if (t.indent !== cur.indent) continue
      if (t.kind === 'if') break // 新链开始，后面不再受本次断链影响
      if (t.kind === 'else-if' && t.cond.includes(DISPATCH_VAR)) dead++
    }
    if (dead > 0) breaks.push({ tag: cur.tag, line: cur.line, cond: cur.cond, dead })
  }
  return breaks
}

function hostFiles(): string[] {
  return fs
    .readdirSync(WP_DIR)
    .filter((n) => n.startsWith('Gt') && n.endsWith('.vue'))
    .map((n) => path.join(WP_DIR, n))
}

function analyze(file: string): ChainBreak[] {
  return findSheetChainBreaks(templateSection(stripHtmlComments(fs.readFileSync(file, 'utf-8'))))
}

// ──────────────────────────────────────────────────────────────────────────────
// 反向自检（用合成样本，不依赖真实文件的现状）
// ──────────────────────────────────────────────────────────────────────────────

describe('自检：检测器有效', () => {
  it('扫到足量宿主文件', () => {
    expect(hostFiles().length).toBeGreaterThan(50)
  })

  it('对事故样本必须报出，且死分支数正确', () => {
    const bad = `
        <TabA v-if="currentSheet === 'A'" />
        <TabB v-else-if="currentSheet === 'B'" />
        <Panel
          v-if="props.htmlData?.hi_extraction_enabled"
          :x="1"
        />
        <TabC v-else-if="currentSheet === 'C'" />
        <TabD v-else-if="currentSheet === 'D'" />
`
    const breaks = findSheetChainBreaks(bad)
    expect(breaks).toHaveLength(1)
    expect(breaks[0].tag).toBe('Panel')
    expect(breaks[0].dead).toBe(2)
  })

  it('<template v-else-if> 包裹后不得再报（即修好的形态）', () => {
    const good = `
        <TabA v-if="currentSheet === 'A'" />
        <TabB v-else-if="currentSheet === 'B'" />
        <template v-else-if="currentSheet === 'C'">
          <Panel
            v-if="props.htmlData?.hi_extraction_enabled"
            :x="1"
          />
          <TabC :y="2" />
        </template>
        <TabD v-else-if="currentSheet === 'D'" />
`
    expect(findSheetChainBreaks(good)).toEqual([])
  })

  it('链首的 v-if 不算断链（前面无 sheet 链）', () => {
    const ok = `
        <Panel v-if="flag" />
        <TabA v-else-if="currentSheet === 'A'" />
`
    expect(findSheetChainBreaks(ok)).toEqual([])
  })

  it('表格列内部的 row 级 v-if/v-else-if 不参与判定（防误报）', () => {
    const tableCol = `
        <el-table-column>
          <template #default="scope">
            <el-input v-if="isEditable(scope.row)" />
            <span v-else-if="!scope.row.isSection" />
          </template>
        </el-table-column>
`
    expect(findSheetChainBreaks(tableCol)).toEqual([])
  })

  it('OnlyOffice 双模式短路是合法链首（前一个是独立 v-if 工具栏，不得误报）', () => {
    // 真实形态：GtN4TaxesAndSurcharges.vue / G8~G14 / N2~N5
    const dualMode = `
      <div v-if="isHtmlSheet && currentSheet !== 'N4' && currentSheet !== '底稿目录'" class="toolbar">
        <el-segmented :model-value="m" />
      </div>

      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
      />
      <GtCycleAProgramRouter v-else-if="currentSheet === 'N4A'" />
      <N4TabIndex v-else-if="currentSheet === 'N4'" />
`
    expect(findSheetChainBreaks(dualMode)).toEqual([])
  })

  it('断链后另起的合法新 sheet 链不计入死分支', () => {
    const mixed = `
        <TabA v-if="currentSheet === 'A'" />
        <Panel v-if="flag" />
        <TabB v-if="currentSheet === 'B'" />
        <TabC v-else-if="currentSheet === 'C'" />
`
    // Panel 之后紧接的是 v-if（新链首）→ 无死分支
    expect(findSheetChainBreaks(mixed)).toEqual([])
  })

  it('注释里的反例片段被剥掉（不剥会误报）', () => {
    const withComment = `
        <!--
          反例：
          <Panel v-if="flag" />
          <TabC v-else-if="currentSheet === 'C'" />
        -->
        <TabA v-if="currentSheet === 'A'" />
`
    expect(findSheetChainBreaks(templateSection(stripHtmlComments(withComment)))).toEqual([])
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// 主断言
// ──────────────────────────────────────────────────────────────────────────────

describe('宿主 sheet 分发链完整性', () => {
  it('任何宿主都不得用非 sheet 条件的裸 v-if 打断 currentSheet 分发链', () => {
    const violations: string[] = []
    for (const f of hostFiles()) {
      for (const b of analyze(f)) {
        violations.push(
          `${path.basename(f)}:${b.line} <${b.tag}> v-if="${b.cond}" 打断了 ` +
            `currentSheet 分发链 → 后续 ${b.dead} 个 sheet 分支成死分支（永不渲染）`,
        )
      }
    }
    expect(
      violations,
      '修法：用 `<template v-else-if="currentSheet === ...">` 包住' +
        '「附加面板 + 该 sheet 内容」（范式 GtH7BiologicalAssets.vue）；' +
        '批量修复 backend/scripts/fix/fix_hi_source_panel_vif_chain.py --apply',
    ).toEqual([])
  })

  it('检测器在真实宿主上确实跑过 currentSheet 链（否则主断言空转）', () => {
    let hostsWithChain = 0
    for (const f of hostFiles()) {
      const tpl = templateSection(stripHtmlComments(fs.readFileSync(f, 'utf-8')))
      const sheetBranches = collectDirectiveTags(tpl).filter(
        (t) => t.kind === 'else-if' && t.cond.includes(DISPATCH_VAR),
      )
      if (sheetBranches.length >= 3) hostsWithChain++
    }
    expect(hostsWithChain, '未扫到任何 currentSheet 分发链，正则或路径失效').toBeGreaterThan(20)
  })
})

// ──────────────────────────────────────────────────────────────────────────────
// H/I 溯源面板：回归钉死
// ──────────────────────────────────────────────────────────────────────────────

const HI_PANEL_HOSTS = [
  'GtH5OilGasAssets.vue',
  'GtH6AssetDisposalClearing.vue',
  'GtH7BiologicalAssets.vue',
  'GtH8RightOfUseAssets.vue',
  'GtH9LeaseLiabilities.vue',
  'GtH10AssetDisposalIncome.vue',
  'GtI1IntangibleAssets.vue',
  'GtI2DevelopmentExpenditure.vue',
  'GtI3Goodwill.vue',
  'GtI4LongTermPrepaid.vue',
  'GtI5OtherNoncurrentAssets.vue',
  'GtI6ResearchDevelopmentExpense.vue',
]

describe('HiFourTableSourcePanel 放置形态', () => {
  it('12 个 H/I 宿主的溯源面板全部包在 <template> 分支里', () => {
    const problems: string[] = []
    for (const h of HI_PANEL_HOSTS) {
      const p = path.join(WP_DIR, h)
      if (!fs.existsSync(p)) {
        problems.push(`${h}（文件不存在，清单已过时）`)
        continue
      }
      const src = fs.readFileSync(p, 'utf-8')
      const idx = src.indexOf('<HiFourTableSourcePanel')
      if (idx < 0) {
        problems.push(`${h}（未使用溯源面板，清单已过时）`)
        continue
      }
      const before = src.slice(Math.max(0, idx - 300), idx)
      if (!/<template v-(?:else-)?if=/.test(before)) {
        problems.push(`${h}（面板未被 <template v-else-if> 包裹 → 会打断 sheet 分发链）`)
      }
    }
    expect(problems).toEqual([])
  })

  it('包裹条件必须是 sheet 分发条件（不是把 hi_extraction_enabled 提到 template 上）', () => {
    const problems: string[] = []
    for (const h of HI_PANEL_HOSTS) {
      const p = path.join(WP_DIR, h)
      if (!fs.existsSync(p)) continue
      const src = fs.readFileSync(p, 'utf-8')
      const idx = src.indexOf('<HiFourTableSourcePanel')
      if (idx < 0) continue
      const before = src.slice(Math.max(0, idx - 300), idx)
      const m = [...before.matchAll(/<template v-(?:else-)?if="([^"]*)"/g)].pop()
      if (!m || !m[1].includes(DISPATCH_VAR)) {
        problems.push(`${h}（包裹条件 "${m?.[1] ?? '无'}" 未按 ${DISPATCH_VAR} 分发）`)
      }
    }
    expect(problems).toEqual([])
  })
})
