/**
 * H3 溯源面板接线守卫（spec `h-cycle-extraction-formula-and-disclosure-completion` Task 10）
 *
 * 钉死四项接线事实，防被回退：
 *
 * 1. `H3TabAdjudicationCost.vue` / `H3TabAdjudicationFair.vue` 各含 1 处
 *    `<WpFourTableSourcePanel>`（H3 是四槽循环，面板是它唯一的取数口径追溯出口）
 * 2. 两个 Tab 传给面板的**每个属性**都存在于面板 `defineProps<{...}>` 的键集里
 *    —— 🔴 Vue 对「传不存在的 prop」不报错（落到根元素当 HTML 属性），
 *    `get_diagnostics` / vitest / Vite transform **四层全绿**，只有浏览器能发现。
 *    平台已踩过两次：G5 审定表溯源面板从未渲染过（传的 4 个属性全不是 prop 名 +
 *    漏传 `source-codes` ⇒ 面板内部 `visible` 恒 false）；G6 写 `report-row`/`hint`
 *    而真实 prop 是 `fallback-row-code`/`hints`（复数、数组）。
 * 3. 必填 prop（`defineProps` 里不带 `?` 的）必须已传；`sourceCodes` 虽可选但
 *    面板 `visible = hasTbSourceCodes(props.sourceCodes) || hasExtraSlotCodes`
 *    ⇒ 不传等于面板不渲染，故按必传处理
 * 4. 宿主 `GtH3InvestmentProperty.vue` 的 `H3-1` 那一支必须是
 *    `<template v-else-if="currentSheet === 'H3-1'">` 且其后仍有 `v-else-if`
 *    —— 裸 `v-if` 插进 sheet 分发链中间会让后续 `v-else-if` **全成死分支**
 *    （H 类已踩过 11 个宿主 / 140 个分支，见 `__tests__/hostSheetDispatchChain.spec.ts`）
 *
 * 另钉住面板自身的两条 R5.3/R5.4 行为（**不在 H3 侧另写一份判定** ——
 * 面板是 K1/K2/F1/E1/G5/G6 等的共享件，双真源必漂移）：
 * - 「本项目无此科目」三态：`found=false` 的槽显示该文案而非 0
 * - `conflicts` 以中文完整句展示，不得渲染裸科目码数组
 *
 * 🔴 标签存在性断言必须带**标签名边界** —— `toContain('<Foo')` 会被
 * `<FooREMOVED` 骗过（= 组件根本没渲染，最核心的变异静默逃逸）。
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

// 本文件位于 .../components/workpaper/h3/__tests__/ → 回仓库根需 7 级
const REPO_ROOT = path.resolve(__dirname, '../../../../../../..')
const WP_DIR = path.join(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper')

const PANEL_REL = 'shared/WpFourTableSourcePanel.vue'
const HOST_REL = 'GtH3InvestmentProperty.vue'
const TAB_RELS = ['h3/core/H3TabAdjudicationCost.vue', 'h3/core/H3TabAdjudicationFair.vue'] as const

const PANEL_TAG = 'WpFourTableSourcePanel'

function readWp(rel: string): string {
  const p = path.join(WP_DIR, rel)
  // 路径写错时表现为「文件级失败」而非断言失败，极易当噪声跳过 → 显式抛
  if (!fs.existsSync(p)) throw new Error(`守卫路径失效（REPO_ROOT 回退级数错？）: ${p}`)
  return fs.readFileSync(p, 'utf-8')
}

/** 剥 HTML 注释 + JS 行/块注释（注释里会写反例，不剥必误判） */
export function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/** 标签存在性：带名字边界，`<FooREMOVED` 不算命中 */
export function countTag(src: string, tag: string): number {
  return (src.match(new RegExp(`<${tag}(?=[\\s/>])`, 'g')) || []).length
}

/** camelCase → kebab-case */
export function toKebab(s: string): string {
  return s.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase()
}

/** 括号/尖括号配对取 `defineProps<{ ... }>` 的类型字面量体 */
export function definePropsBody(src: string): string {
  const at = src.indexOf('defineProps<')
  if (at < 0) throw new Error('未找到 defineProps<（正则失效或组件改用运行时声明）')
  const open = src.indexOf('{', at)
  if (open < 0) throw new Error('defineProps< 之后未找到 {')
  let depth = 0
  for (let i = open; i < src.length; i++) {
    if (src[i] === '{') depth++
    else if (src[i] === '}') {
      depth--
      if (depth === 0) return src.slice(open + 1, i)
    }
  }
  throw new Error('defineProps 类型字面量花括号未配对')
}

/**
 * 抽 prop 名与是否可选。
 * 只认「行首标识符 + 可选 `?` + `:`」，注释与嵌套类型体天然不匹配。
 */
export function parseProps(body: string): { name: string; optional: boolean }[] {
  const out: { name: string; optional: boolean }[] = []
  for (const line of stripComments(body).split('\n')) {
    const m = line.match(/^\s{2,6}([A-Za-z_$][\w$]*)(\?)?\s*:/)
    if (m) out.push({ name: m[1], optional: Boolean(m[2]) })
  }
  return out
}

/** 抽某个标签调用点上的属性名（去掉 `:` / `@` / `v-` 前缀形态） */
export function tagAttrs(src: string, tag: string): string[] {
  const re = new RegExp(`<${tag}(?=[\\s/>])([\\s\\S]*?)/?>`, 'g')
  const attrs: string[] = []
  let m: RegExpExecArray | null
  while ((m = re.exec(src))) {
    for (const a of m[1].matchAll(/(?:^|\s)(:?[A-Za-z][\w.-]*)\s*=/g)) {
      attrs.push(a[1].replace(/^:/, ''))
    }
  }
  return attrs
}

const PANEL_SRC = stripComments(readWp(PANEL_REL))
const PANEL_PROPS = parseProps(definePropsBody(PANEL_SRC))
const PANEL_PROP_KEBAB = new Set(PANEL_PROPS.map((p) => toKebab(p.name)))

/** Vue 对所有组件都放行的通用属性（不算未知 prop） */
const UNIVERSAL_ATTRS = new Set(['key', 'ref', 'class', 'style', 'id'])

describe('H3 溯源面板接线（Task 10 / Property 16）', () => {
  it('解析器自检：面板 prop 集合非空且含已知键（防正则失效导致全部断言空转）', () => {
    expect(PANEL_PROPS.length).toBeGreaterThanOrEqual(6)
    for (const known of ['sourceCodes', 'grossLabel', 'extraSlotKeys', 'hints', 'fallbackRowCode']) {
      expect(PANEL_PROPS.map((p) => p.name)).toContain(known)
    }
  })

  it.each(TAB_RELS)('%s 渲染溯源面板（标签带名字边界）', (rel) => {
    const src = stripComments(readWp(rel))
    expect(countTag(src, PANEL_TAG)).toBe(1)
  })

  it.each(TAB_RELS)('%s 的 htmlData 在 defineProps 内（缺它面板恒不渲染）', (rel) => {
    const src = stripComments(readWp(rel))
    const names = parseProps(definePropsBody(src)).map((p) => p.name)
    expect(names).toContain('htmlData')
  })

  it.each(TAB_RELS)('%s 传给面板的每个属性都是面板真实 prop', (rel) => {
    const src = stripComments(readWp(rel))
    const attrs = tagAttrs(src, PANEL_TAG).filter((a) => !UNIVERSAL_ATTRS.has(a))
    expect(attrs.length).toBeGreaterThan(0)
    const unknown = attrs.filter((a) => !PANEL_PROP_KEBAB.has(a))
    expect(unknown, `未知属性会静默落到根元素当 HTML 属性：${unknown.join(', ')}`).toEqual([])
  })

  it.each(TAB_RELS)('%s 已传面板必填 prop 与 source-codes', (rel) => {
    const src = stripComments(readWp(rel))
    const attrs = new Set(tagAttrs(src, PANEL_TAG))
    for (const p of PANEL_PROPS.filter((x) => !x.optional)) {
      expect(attrs, `缺必填 prop ${toKebab(p.name)}`).toContain(toKebab(p.name))
    }
    // sourceCodes 可选，但面板 visible 完全由它（或 extraSlotKeys 命中）决定
    expect(attrs).toContain('source-codes')
  })

  it.each(TAB_RELS)('%s 声明 extra-slot-keys（H3 四槽，扁平投影只覆盖 gross/provision）', (rel) => {
    const src = stripComments(readWp(rel))
    expect(new Set(tagAttrs(src, PANEL_TAG))).toContain('extra-slot-keys')
  })

  it('H3 两个审定表 Tab 的 tbSourceCodes 兼容顶层与 project_context 两处落点', () => {
    // 平台两套并存：6 个 D render 写 html_data 顶层，D4/F1/E1/G1 写 project_context
    for (const rel of TAB_RELS) {
      const src = stripComments(readWp(rel))
      expect(src).toMatch(/hd\?\.tb_source_codes/)
      expect(src).toMatch(/hd\?\.project_context\?\.tb_source_codes/)
    }
  })
})

describe('H3 宿主分发链未被打断（Task 10）', () => {
  const HOST = stripComments(readWp(HOST_REL))
  const LINES = HOST.split('\n')

  it("H3-1 那一支是 <template v-else-if> 且其后仍有 v-else-if", () => {
    const idx = LINES.findIndex((l) => /v-else-if\s*=\s*"currentSheet === 'H3-1'"/.test(l))
    expect(idx, "未找到 currentSheet === 'H3-1' 分支").toBeGreaterThan(-1)
    expect(LINES[idx], 'H3-1 分支必须用 <template> 包住「面板 + 该 sheet 内容」').toMatch(
      /<template\s+v-else-if/,
    )
    const after = LINES.slice(idx + 1).filter((l) => /v-else-if\s*=\s*"currentSheet ===/.test(l))
    expect(after.length, 'H3-1 之后应仍有按 sheet 分发的 v-else-if').toBeGreaterThan(5)
  })

  it('宿主向两个审定表 Tab 传 :html-data', () => {
    for (const tag of ['H3TabAdjudicationCost', 'H3TabAdjudicationFair']) {
      expect(countTag(HOST, tag), `${tag} 未在宿主渲染`).toBe(1)
      expect(tagAttrs(HOST, tag), `${tag} 漏传 :html-data ⇒ 面板与预填双双静默失效`).toContain(
        'html-data',
      )
    }
  })
})

describe('面板共享行为：无此科目三态与 conflicts 中文化（R5.3 / R5.4）', () => {
  it('槽未命中显示「本项目无…科目」而非 0', () => {
    // 🔴 实际文案是插值形态 `本项目无「{{ absentSlotLabels.join('、') }}」科目`
    //    ⇒ 断言不能写连续字面量「本项目无此科目」（那样恒红且看起来像实现缺陷）
    expect(PANEL_SRC).toMatch(/本项目无[「{][\s\S]{0,80}科目/)
    // 判据源 = `found === false`（不是「金额为 0」）；宁缺勿造用 info 不用 danger
    expect(PANEL_SRC, '三态判据必须是 found === false').toMatch(/found\s*===\s*false/)
    expect(PANEL_SRC).toMatch(/absentSlotLabels/)
    expect(PANEL_SRC, '「无此科目」是正确行为，不得用 danger 告警').toMatch(
      /absentSlotLabels\.length"\s+size="small"\s+type="info"/,
    )
  })

  it('conflicts 以中文句子展示，不渲染裸三元组数组', () => {
    // 变量名是 `conflictTexts` / `tbConflictTexts`（无小写复数 `conflicts`）
    expect(PANEL_SRC).toMatch(/conflictTexts/)
    expect(PANEL_SRC, '必须消费 render 下发的 conflicts').toMatch(/tbConflictTexts\(/)
    // 三元组 = [槽键, 报表公式给的码, 按名定位到的实际码] → 必须翻成完整句
    expect(PANEL_SRC, 'conflicts 必须翻成中文完整句').toMatch(/报表公式[\s\S]{0,40}科目表/)
    expect(PANEL_SRC, '禁 .map(String) 直接渲染裸码数组').not.toMatch(
      /conflict[\w]*[^\n]*\.map\(String\)/,
    )
  })
})

describe('反向自检（证明上面的断言不是空转）', () => {
  it('把标签名改成 <XxxREMOVED 后标签断言必红', () => {
    const mutated = readWp(TAB_RELS[0]).replace(
      new RegExp(`<${PANEL_TAG}(?=[\\s/>])`),
      `<${PANEL_TAG}REMOVED`,
    )
    expect(countTag(mutated, PANEL_TAG)).toBe(0)
    // 弱判据对照：`toContain('<Foo')` 会被骗过（这正是要避免的写法）
    expect(mutated).toContain(`<${PANEL_TAG}`)
  })

  it('传不存在的 prop 时未知属性检测必红', () => {
    const fake = `<${PANEL_TAG} :source-codes="x" gross-label="y" :report-row="z" />`
    const unknown = tagAttrs(fake, PANEL_TAG).filter(
      (a) => !PANEL_PROP_KEBAB.has(a) && !UNIVERSAL_ATTRS.has(a),
    )
    expect(unknown).toEqual(['report-row'])
  })

  it('漏传必填 prop 时必红', () => {
    const fake = `<${PANEL_TAG} :source-codes="x" />`
    const attrs = new Set(tagAttrs(fake, PANEL_TAG))
    const missing = PANEL_PROPS.filter((p) => !p.optional && !attrs.has(toKebab(p.name)))
    expect(missing.map((p) => p.name)).toContain('grossLabel')
  })

  it('裸 v-if 插进分发链中间时链断裂检测必红', () => {
    const good = [
      `    <XTabIndex v-if="currentSheet === 'H3'" />`,
      `    <template v-else-if="currentSheet === 'H3-1'">`,
      `    <XTabDetail v-else-if="currentSheet === 'H3-2'" />`,
    ]
    const bad = [
      `    <XTabIndex v-if="currentSheet === 'H3'" />`,
      `    <${PANEL_TAG} v-if="props.htmlData?.enabled" />`,
      `    <XTabDetail v-else-if="currentSheet === 'H3-2'" />`,
    ]
    const isTemplateElseIf = (ls: string[]) =>
      ls.some((l) => /<template\s+v-else-if\s*=\s*"currentSheet ===/.test(l))
    expect(isTemplateElseIf(good)).toBe(true)
    expect(isTemplateElseIf(bad)).toBe(false)
  })

  it('stripComments 自检：注释里的反例不参与判定', () => {
    const withComment = `<!-- 反例：<${PANEL_TAG} :report-row="x" /> -->\n<div/>`
    expect(countTag(stripComments(withComment), PANEL_TAG)).toBe(0)
    expect(countTag(withComment, PANEL_TAG)).toBe(1)
  })
})
