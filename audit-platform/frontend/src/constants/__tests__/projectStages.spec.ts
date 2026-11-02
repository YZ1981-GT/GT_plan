/**
 * projectStages.spec.ts — 项目侧栏环节清单的契约守卫。
 *
 * 钉住三件在界面上「静默坏掉、看不出来」的事：
 *  1. 每个可点条目的 `routeName` 必须是 router 里真实存在的具名路由
 *     —— 写错就是点了白屏/404，而菜单看起来完全正常。
 *  2. `pending` 与「没有 routeName」严格等价
 *     —— 只标 pending 却留着 routeName 会让它看着灰、点了却能跳；
 *        反之没页面又不标 pending，点了白屏。
 *  3. pending 条目必须有 `pendingReason`（tooltip 要讲清缺什么）。
 *
 * 另外钉住 CSS 注释不含右花括号：CSS 注释不能嵌套，注释里的 '}' 会提前闭合注释，
 * 余下文字漏成非法 CSS 并**静默吃掉紧随其后的整条规则**（本轮实测踩过：
 * 选中态与 pending 灰字全部失效，控制台无任何报错）。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import { PROJECT_STAGES, PROJECT_STAGE_GROUPS, projectStageFlowText } from '../projectStages'

const SRC = path.resolve(__dirname, '../..')

/** 从 router/domains/*.ts 现扫全部具名路由（不写死清单，加路由不用改本文件） */
function declaredRouteNames(): Set<string> {
  const dir = path.join(SRC, 'router/domains')
  const names = new Set<string>()
  for (const f of fs.readdirSync(dir)) {
    if (!f.endsWith('.ts')) continue
    const text = fs.readFileSync(path.join(dir, f), 'utf-8')
    for (const m of text.matchAll(/name:\s*'([^']+)'/g)) names.add(m[1])
  }
  return names
}

describe('PROJECT_STAGES — 路由与 pending 契约', () => {
  it('分组非空，且拍平结果与分组逐项一致', () => {
    expect(PROJECT_STAGE_GROUPS.length).toBeGreaterThan(0)
    const flat = PROJECT_STAGE_GROUPS.flatMap(g => g.items)
    expect(PROJECT_STAGES).toEqual(flat)
    // 每组都要有条目 —— 空组会在侧栏留下一个孤立标题
    for (const g of PROJECT_STAGE_GROUPS) expect(g.items.length).toBeGreaterThan(0)
  })

  it('key 全局唯一（高亮按 key 匹配，撞 key 会多处同时高亮）', () => {
    const keys = PROJECT_STAGES.map(s => s.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('每个 routeName 都是 router 中真实存在的具名路由', () => {
    const declared = declaredRouteNames()
    // 先证明扫描本身有效（否则空集合会让下面的断言恒绿）
    expect(declared.size).toBeGreaterThan(50)
    expect(declared.has('TrialBalance')).toBe(true)

    const missing = PROJECT_STAGES
      .filter(s => s.routeName && !declared.has(s.routeName))
      .map(s => `${s.label}(${s.routeName})`)
    expect(missing).toEqual([])
  })

  it('pending 与「无 routeName」严格等价，且 pending 必须给出原因', () => {
    for (const s of PROJECT_STAGES) {
      expect(
        !!s.pending,
        `「${s.label}」: pending=${!!s.pending} 但 routeName=${s.routeName ?? '(无)'}；` +
          '两者必须同时成立 —— 有页面就别标 pending，没页面必须标',
      ).toBe(!s.routeName)
      if (s.pending) {
        expect(s.pendingReason, `「${s.label}」缺 pendingReason`).toBeTruthy()
      }
    }
  })

  it('带 query.tab 的条目：tab 必须是 ReportView 真实存在的页签', () => {
    // 🔴 写错页签名时 ReportView 的白名单会静默回落到资产负债表 —— 菜单看着能点、点了却不是「报表分析」。
    const src = fs.readFileSync(path.join(SRC, 'views/ReportView.vue'), 'utf-8')
    const panes = new Set([...src.matchAll(/<el-tab-pane[^>]*\bname="([^"]+)"/g)].map(m => m[1]))
    expect(panes.size).toBeGreaterThan(5) // 防空转：扫描本身得扫到东西
    expect(panes.has('report_analysis')).toBe(true)

    const withTab = PROJECT_STAGES.filter(s => s.query?.tab)
    expect(withTab.length).toBeGreaterThan(0)
    for (const s of withTab) {
      expect(s.routeName, `「${s.label}」带 tab 却不指向 Reports`).toBe('Reports')
      expect(panes.has(s.query!.tab), `「${s.label}」的 tab=${s.query!.tab} 不是 ReportView 的页签`).toBe(true)
    }
  })

  it('ReportView 的页签白名单与模板里的 <el-tab-pane name> 逐个一致', () => {
    // 白名单少一个 ⇒ 该页签无法从 URL 直达；多一个 ⇒ URL 能把 el-tabs 停在不存在的 pane 上（整页空白）
    const src = fs.readFileSync(path.join(SRC, 'views/ReportView.vue'), 'utf-8')
    const panes = [...src.matchAll(/<el-tab-pane[^>]*\bname="([^"]+)"/g)].map(m => m[1]).sort()
    const block = src.match(/const REPORT_TAB_NAMES = \[([\s\S]*?)\] as const/)
    expect(block, '找不到 REPORT_TAB_NAMES 白名单').toBeTruthy()
    const allow = [...block![1].matchAll(/'([^']+)'/g)].map(m => m[1]).sort()
    expect(allow).toEqual(panes)
  })

  it('至少有一个可点条目（全 pending 等于侧栏全灰）', () => {
    expect(PROJECT_STAGES.some(s => s.routeName)).toBe(true)
  })

  it('流程文案由分组标题拼成，不含 pending 条目的标签', () => {
    const text = projectStageFlowText()
    for (const g of PROJECT_STAGE_GROUPS) expect(text).toContain(g.title)
    for (const s of PROJECT_STAGES) {
      if (s.pending) expect(text).not.toContain(s.label)
    }
  })
})

describe('布局 CSS 注释不得含右花括号', () => {
  const files = [
    'layouts/ThreeColumnLayout.vue',
    'components/layout/ProjectEntryBar.vue',
    'views/ProjectEntryHome.vue',
    'views/TaxReturnPage.vue',
    'views/TaxAuditReportPage.vue',
    'views/TaxWorkpaperPage.vue',
    'components/layout/TaxWorkpaperSubnav.vue',
    'components/workpaper/TaxWorkpaperGrid.vue',
  ]

  it.each(files)('%s 的 <style> 注释内无花括号', (rel) => {
    const text = fs.readFileSync(path.join(SRC, rel), 'utf-8')
    const styles = [...text.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m => m[1])
    expect(styles.length).toBeGreaterThan(0)

    const offenders: string[] = []
    for (const block of styles) {
      for (const m of block.matchAll(/\/\*[\s\S]*?\*\//g)) {
        if (m[0].includes('{') || m[0].includes('}')) offenders.push(m[0].slice(0, 70))
      }
    }
    expect(offenders).toEqual([])
  })
})
