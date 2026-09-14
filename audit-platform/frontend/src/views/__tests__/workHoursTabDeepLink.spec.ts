/**
 * `/work-hours?tab=approve` 深链守卫
 *
 * ## 背景
 *
 * `ManagerDashboard.goToWorkHoursApprove()` 原本 `router.push('/work-hours/approve')`，
 * 而该路由**从未声明**（审批是 `WorkHoursPage` 里 `name="approve"` 的 tab，
 * 不是独立页面）⇒ 点击落 404。由 `FrontendReferenceIntegrity` 守卫的
 * 「路由孤儿」判据抓出。
 *
 * 修法是把它改成 `{ path: '/work-hours', query: { tab: 'approve' } }`，
 * 并给 `WorkHoursPage` 加 query 深链支持。本文件锁住**那段新增逻辑的行为** ——
 * 否则就是「改了行为但没有判据」，跳转能到页面却停在默认 tab，
 * 用户看不出区别，而所有既有测试都不会红。
 *
 * ## 为什么测纯函数投影而不是 mount 整页
 *
 * `WorkHoursPage` 挂着 WeeklyTimesheet / WorkHourApprovalTab / BudgetCompareChart
 * 等重组件（含图表），mount 成本高且失败面与本判据无关。
 * 这里把「query → 初始 tab」这条规则按同一算法独立断言，
 * 并用源码级判据锁住页面真的走了这条规则（防实现被换掉而本文件仍绿）。
 *
 * Feature: dsh-agent-panel-integration / P0 收口（路由孤儿连带修复）
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { stripJsComments, stripHtmlComments } from '../../__tests__/_helpers/frontendSourceScan'

const PAGE = resolve(__dirname, '../WorkHoursPage.vue')
const DASHBOARD = resolve(__dirname, '../ManagerDashboard.vue')

/**
 * 源码级判据**必须先剥注释**。
 *
 * 🔴 这条不是理论洁癖：本文件首版直接对原始源码断言
 * `not.toContain("'/work-hours/approve'")`，结果被**修复时写的说明注释**打红 ——
 * 那条注释正文里就引用了旧路径。反过来同样成立：正向 `toContain` 判据
 * 会被注释里的字面量喂成假绿。
 */
function codeOf(path: string): string {
  return stripJsComments(stripHtmlComments(readFileSync(path, 'utf-8')))
}

/** 与 `WorkHoursPage.initialTab()` 同一规则（白名单 + approve 需权限）。 */
const TAB_NAMES = ['mine', 'approve', 'stats', 'budget'] as const
function resolveInitialTab(
  queryTab: unknown,
  canApprove: boolean,
): (typeof TAB_NAMES)[number] {
  if (typeof queryTab !== 'string') return 'mine'
  if (!TAB_NAMES.includes(queryTab as (typeof TAB_NAMES)[number])) return 'mine'
  if (queryTab === 'approve' && !canApprove) return 'mine'
  return queryTab as (typeof TAB_NAMES)[number]
}

describe('/work-hours?tab= 深链规则', () => {
  it('有权用户 tab=approve 落到审批页', () => {
    expect(resolveInitialTab('approve', true)).toBe('approve')
  })

  it('无权用户即使手敲 tab=approve 也退回默认页', () => {
    // 门控不能只靠 UI 隐藏 —— tab 值是用户可控输入
    expect(resolveInitialTab('approve', false)).toBe('mine')
  })

  it('白名单外的值一律退回默认页', () => {
    for (const bad of ['../../etc', '<script>', 'ADMIN', '', 'approve ']) {
      expect(resolveInitialTab(bad, true)).toBe('mine')
    }
  })

  it('无 query / 非字符串一律退回默认页', () => {
    expect(resolveInitialTab(undefined, true)).toBe('mine')
    expect(resolveInitialTab(['approve'], true)).toBe('mine') // Vue Router 重复参数给数组
    expect(resolveInitialTab(42, true)).toBe('mine')
  })

  it('其余合法 tab 正常放行', () => {
    expect(resolveInitialTab('stats', false)).toBe('stats')
    expect(resolveInitialTab('budget', false)).toBe('budget')
    expect(resolveInitialTab('mine', false)).toBe('mine')
  })
})

describe('接线判据（防实现被换掉而本文件仍绿）', () => {
  const pageSrc = codeOf(PAGE)
  const dashSrc = codeOf(DASHBOARD)

  it('判据自检：剥注释确实生效', () => {
    // 没有这条，`codeOf` 一旦退化成原样返回，下面所有断言的强度都会悄悄改变
    // （正向断言变假绿、反向断言变假红）。
    const raw = readFileSync(DASHBOARD, 'utf-8')
    expect(raw).toContain("原写法 '/work-hours/approve'") // 注释原文在
    expect(dashSrc).not.toContain('原写法') // 剥掉后不在
  })

  it('WorkHoursPage 真的从 route.query 取初始 tab', () => {
    expect(pageSrc).toContain('useRoute')
    expect(pageSrc).toContain('route.query.tab')
    // activeTab 必须由 initialTab() 初始化，而不是硬编码 'mine'
    expect(pageSrc).toMatch(/const activeTab = ref\(initialTab\(\)\)/)
  })

  it('WorkHoursPage 的 approve tab 仍受权限门控', () => {
    expect(pageSrc).toMatch(/requested === 'approve'[\s\S]{0,80}approve_workhours/)
  })

  it('ManagerDashboard 不再跳不存在的 /work-hours/approve', () => {
    expect(pageSrc.length).toBeGreaterThan(0)
    expect(dashSrc).not.toContain("'/work-hours/approve'")
    expect(dashSrc).toMatch(/path:\s*'\/work-hours'[\s\S]{0,60}tab:\s*'approve'/)
  })

  it('判据自检：白名单与页面源码里的一致', () => {
    // 防两边漂移 —— 本文件的 TAB_NAMES 是页面规则的复刻，必须同源
    for (const name of TAB_NAMES) {
      expect(pageSrc).toContain(`'${name}'`)
    }
  })
})
