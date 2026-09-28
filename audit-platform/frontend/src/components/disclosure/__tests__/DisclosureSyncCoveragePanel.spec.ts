/**
 * 披露同步覆盖率面板 —— 组件行为测试
 *
 * spec: disclosure-payload-authority-source / Task 2.4 需求 3.4
 *
 * 修复记录（复盘 P0-3）：首版只创建了组件文件、**未接入任何页面也无测试**
 * ⇒ 是死代码，需求 3.4「覆盖率 SHALL 在前端可见」实质未达成。
 * 本文件锁死：① 共享章节去重显示 ② 汇总数展示 ③ 跳转事件 ④ 接入宿主页面。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// ── api mock ────────────────────────────────────────────────────────────

const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  default: { get: (...args: unknown[]) => mockGet(...args) },
}))

const mockPush = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mockPush }) }))

const mockResolveInstance = vi.fn()
vi.mock('@/services/acnr', () => ({
  useAcnr: () => ({ resolveInstance: mockResolveInstance }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), success: vi.fn(), error: vi.fn() },
}))

import DisclosureSyncCoveragePanel from '../DisclosureSyncCoveragePanel.vue'

const STUBS = {
  'el-button': { template: '<button><slot /></button>' },
  'el-icon': { template: '<i><slot /></i>' },
  'el-progress': { template: '<div class="el-progress" />', props: ['percentage'] },
  Refresh: { template: '<span />' },
}

function makeSummary(overrides: Record<string, unknown> = {}) {
  return {
    expected: 4,
    synced: 1,
    stale: 1,
    never_synced: 3,
    duty_rows: 5,
    items: [
      { wp_code: 'D1', variant: 'listed', note_section: '五、4', expected: true, synced: true, stale: true, never_synced: false },
      { wp_code: 'D2', variant: 'listed', note_section: '五、5', expected: true, synced: false, stale: false, never_synced: true },
      // 🔴 共享章节：G2 与 G3 同推「五、8」，只对应一个附注章节
      { wp_code: 'G2', variant: 'listed', note_section: '五、8', expected: true, synced: false, stale: false, never_synced: true },
      { wp_code: 'G3', variant: 'listed', note_section: '五、8', expected: true, synced: false, stale: false, never_synced: true },
      { wp_code: 'E1', variant: 'soe', note_section: '八、1', expected: true, synced: false, stale: false, never_synced: true },
    ],
    ...overrides,
  }
}

async function mountPanel(payload: unknown = makeSummary()) {
  mockGet.mockResolvedValue(payload)
  const wrapper = mount(DisclosureSyncCoveragePanel, {
    props: { projectId: 'p-1', year: 2025 },
    global: { stubs: STUBS },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  mockGet.mockReset()
  mockPush.mockReset()
  mockResolveInstance.mockReset()
})

describe('DisclosureSyncCoveragePanel', () => {
  it('调用覆盖率端点并带上 year 参数', async () => {
    await mountPanel()
    expect(mockGet).toHaveBeenCalledTimes(1)
    const [url, opts] = mockGet.mock.calls[0] as [string, { params: { year: number } }]
    expect(url).toContain('/api/projects/p-1/disclosure-sync-coverage')
    expect(opts.params.year).toBe(2025)
  })

  it('展示 已同步/应同步 汇总数', async () => {
    const wrapper = await mountPanel()
    const text = wrapper.text()
    expect(text).toContain('1')       // synced
    expect(text).toContain('4')       // expected
    expect(text).toContain('已同步')
  })

  it('🔴 共享章节在未同步列表里只出现一次（owner 合并展示）', async () => {
    const wrapper = await mountPanel()
    // 展开详情
    await wrapper.findAll('button').find((b) => b.text().includes('查看未同步章节'))?.trigger('click')
    await flushPromises()

    const rows = wrapper.findAll('.ds-detail-item')
    const sections = rows.map((r) => r.find('.ds-detail-section').text())
    // 「五、8」由 G2+G3 共推，但只能出现 1 行
    expect(sections.filter((s) => s === '五、8')).toHaveLength(1)
    // 3 个未同步章节（五、5 / 五、8 / 八、1），不是 4 条 item
    expect(rows).toHaveLength(3)
    // owner 合并为 G2/G3
    const sharedRow = rows.find((r) => r.find('.ds-detail-section').text() === '五、8')
    expect(sharedRow?.find('.ds-detail-code').text()).toBe('G2/G3')
  })

  it('变异对照：非共享章节的 owner 单独显示', async () => {
    const wrapper = await mountPanel()
    await wrapper.findAll('button').find((b) => b.text().includes('查看未同步章节'))?.trigger('click')
    await flushPromises()

    const rows = wrapper.findAll('.ds-detail-item')
    const d2Row = rows.find((r) => r.find('.ds-detail-section').text() === '五、5')
    expect(d2Row?.find('.ds-detail-code').text()).toBe('D2')
  })

  it('点击未同步章节触发跳转：经 ACNR 解析 wp_id 后 router.push', async () => {
    mockResolveInstance.mockResolvedValue({ found: true, wp_id: 'wp-42' })
    const wrapper = await mountPanel()
    await wrapper.findAll('button').find((b) => b.text().includes('查看未同步章节'))?.trigger('click')
    await flushPromises()

    const rows = wrapper.findAll('.ds-detail-item')
    const d2Row = rows.find((r) => r.find('.ds-detail-section').text() === '五、5')
    await d2Row?.trigger('click')
    await flushPromises()

    expect(mockResolveInstance).toHaveBeenCalledWith({
      project_id: 'p-1', parent: 'D2', sheet_code: 'D2',
    })
    expect(mockPush).toHaveBeenCalledWith('/projects/p-1/workpapers/wp-42/edit')
  })

  it('ACNR 解析不到底稿时不跳转（提示而非静默或崩）', async () => {
    mockResolveInstance.mockResolvedValue({ found: false })
    const wrapper = await mountPanel()
    await wrapper.findAll('button').find((b) => b.text().includes('查看未同步章节'))?.trigger('click')
    await flushPromises()
    await wrapper.findAll('.ds-detail-item')[0].trigger('click')
    await flushPromises()
    expect(mockPush).not.toHaveBeenCalled()
  })

  it('全部已同步时不渲染未同步入口', async () => {
    const wrapper = await mountPanel(makeSummary({
      expected: 1, synced: 1, stale: 0, never_synced: 0, duty_rows: 1,
      items: [{ wp_code: 'D1', variant: 'listed', note_section: '五、4', expected: true, synced: true, stale: false, never_synced: false }],
    }))
    expect(wrapper.text()).not.toContain('查看未同步章节')
  })

  it('端点失败时不抛异常且显示暂无数据（fail-soft）', async () => {
    mockGet.mockRejectedValue(new Error('boom'))
    const wrapper = mount(DisclosureSyncCoveragePanel, {
      props: { projectId: 'p-1', year: 2025 },
      global: { stubs: STUBS },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('暂无数据')
  })

  it('缺 projectId 或 year 时不发请求', async () => {
    mount(DisclosureSyncCoveragePanel, { props: {}, global: { stubs: STUBS } })
    await flushPromises()
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('UI 文本全中文（组件名/图标名等技术标识除外）', async () => {
    const src = readFileSync(resolve(__dirname, '..', 'DisclosureSyncCoveragePanel.vue'), 'utf-8')
    const template = src.match(/<template>([\s\S]*?)\n<\/template>/)?.[1] ?? ''
    expect(template).toContain('披露同步覆盖率')
    expect(template).toContain('已同步')
    expect(template).toContain('从未同步')

    // 🔴 只检查**用户可见文案**，须先剔除标签名与属性
    //    （`<Refresh />` 是 element-plus 图标组件名，不是 UI 文案；
    //      首版正则未剔标签 ⇒ 误报）
    const visibleText = template
      .replace(/<[^>]+>/g, '\n')                 // 去标签与属性
      .replace(/\{\{[^}]*\}\}/g, '')             // 去插值表达式
    expect(visibleText).not.toMatch(/\b(Loading|No data|Refresh|Synced|Total)\b/)
  })

  it('自检：中文化断言非恒绿（剔标签后仍能抓到英文文案）', () => {
    const sample = '<div>Loading...</div>'
    const visible = sample.replace(/<[^>]+>/g, '\n').replace(/\{\{[^}]*\}\}/g, '')
    expect(visible).toMatch(/\bLoading\b/)
    // 而标签名里的 Refresh 应被剔除
    const iconOnly = '<el-icon><Refresh /></el-icon>'
    const iconVisible = iconOnly.replace(/<[^>]+>/g, '\n').replace(/\{\{[^}]*\}\}/g, '')
    expect(iconVisible).not.toMatch(/\bRefresh\b/)
  })
})

// ══════════════════════════════════════════════════════════════════════════
// 🔴 接入守卫：需求 3.4「覆盖率 SHALL 在前端可见」
//    首版组件是死代码（未被任何页面 import）⇒ 本组锁死接入不被回退。
// ══════════════════════════════════════════════════════════════════════════

describe('覆盖率面板已接入宿主（需求 3.4）', () => {
  /**
   * 宿主 = `GtWpDisclosureSyncBar.vue`（设计 §四 指定的「既有展示位」）。
   *
   * 🔴 为什么不是附注侧 `DisclosureEditor.vue`：该宿主 3401 行，而
   * `check_file_size.py` 的 `HARD_CAPS` 给它登记了 ceiling **1800**
   * （既有瘦身欠账，非本轮造成）⇒ pre-commit 门禁对任何触碰硬拒绝，
   * 且 `HARD_CAPS` 优先级高于 whitelist，无法登记放行。
   * 本状态条已一处接入 `GtWpRenderer`、覆盖全部循环披露 sheet，是等效落点。
   * 附注侧入口留作遗留项（spec design.md §十三）。
   */
  const HOST = resolve(__dirname, '../../workpaper/GtWpDisclosureSyncBar.vue')
  const hostSrc = readFileSync(HOST, 'utf-8')

  /** 去注释，防注释里的组件名被数成真实接入（j1 守卫同款坑） */
  function stripComments(code: string): string {
    return code
      .replace(/<!--[\s\S]*?-->/g, '')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/(^|[^:])\/\/.*$/gm, '$1')
  }

  const clean = stripComments(hostSrc)

  it('宿主显式 import 了覆盖率面板', () => {
    expect(clean).toMatch(
      /import\s+DisclosureSyncCoveragePanel\s+from\s+['"][^'"]*DisclosureSyncCoveragePanel\.vue['"]/,
    )
  })

  it('模板里真的渲染了该组件（不是只 import）', () => {
    const template = clean.match(/<template>([\s\S]*?)\n<\/template>/)?.[1] ?? ''
    expect(template.length).toBeGreaterThan(200)
    expect(template).toContain('<DisclosureSyncCoveragePanel')
  })

  it('传入了 project-id 与 year（否则组件永不发请求）', () => {
    const tag = clean.match(/<DisclosureSyncCoveragePanel[\s\S]*?\/>/)?.[0] ?? ''
    expect(tag).toContain(':project-id=')
    expect(tag).toContain(':year=')
  })

  it('宿主不承担跳转逻辑（组件自持，宿主净增最小）', () => {
    // 跳转逻辑内收到面板自身（它已有 projectId，router/ACNR 可自取），
    // 宿主只负责放一个标签 ⇒ 便于换挂载点、也避免撑大宿主行数。
    expect(clean).not.toContain('onCoverageJumpToWorkpaper')
    const tag = clean.match(/<DisclosureSyncCoveragePanel[\s\S]*?\/>/)?.[0] ?? ''
    expect(tag).not.toContain('@jump-to-workpaper')
  })

  it('🔴 不得改回附注侧宿主（DisclosureEditor 受 HARD_CAPS 硬拒绝）', () => {
    const editor = readFileSync(
      resolve(__dirname, '../../../views/DisclosureEditor.vue'), 'utf-8',
    )
    expect(
      editor.includes('DisclosureSyncCoveragePanel'),
      'DisclosureEditor.vue 已 3401 行且 HARD_CAPS ceiling=1800，'
      + 'pre-commit 会硬拒绝。要挂附注侧须先完成该宿主瘦身（spec design.md §十三）',
    ).toBe(false)
  })

  it('自检：stripComments 不把真实代码剥掉', () => {
    expect(clean).toContain('DisclosureSyncCoveragePanel')
    // 注释里的引用应被剥掉：构造一个含注释的样本
    expect(stripComments('<!-- DisclosureSyncCoveragePanel -->\nconst a = 1'))
      .not.toContain('DisclosureSyncCoveragePanel')
  })
})
