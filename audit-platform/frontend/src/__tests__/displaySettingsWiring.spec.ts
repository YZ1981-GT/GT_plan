/**
 * spec: platform-global-display-settings-closure 任务 5 / AC-07
 *
 * 这些断言守的是「接线」，不是「文件存在」。当前 HEAD 已完成路由、布局运行时和面板复用，
 * 本守卫继续钉住其单一入口，并覆盖阶段 A 新补的密度指标与虚拟表接线。
 *
 * 所以判据一律按「源码里是否真的引用了」而不是「文件是否在磁盘上」；
 * 正向断言与反向断言同时存在，避免删掉旧实现后测试因分母为空而假绿。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const SRC = resolve(__dirname, '..')

function read(rel: string): string {
  return readFileSync(resolve(SRC, rel), 'utf-8')
}

describe('显示设置接线（AC-07）', () => {
  it('router 域声明 /display-settings，且不设 admin 门控', () => {
    const system = read('router/domains/system.ts')
    // 正向：路由存在且指向 DisplaySettingsView
    expect(system).toContain("path: 'display-settings'")
    expect(system).toContain('DisplaySettingsView.vue')
    expect(system).toContain("name: 'DisplaySettings'")

    // 反向：这一块**不能**带 meta.permission —— 带了普通用户就被踢回首页。
    // 取 path 到下一处 `},` 之间的片段判断。
    const start = system.indexOf("path: 'display-settings'")
    expect(start).toBeGreaterThan(-1)
    const block = system.slice(start, system.indexOf('},', start))
    expect(block).not.toContain('permission')

    // `/settings` 仍必须是 admin 门（系统配置不开放给普通用户）
    const settingsStart = system.indexOf("path: 'settings',")
    expect(settingsStart).toBeGreaterThan(-1)
    const settingsBlock = system.slice(settingsStart, system.indexOf('},', settingsStart))
    expect(settingsBlock).toContain("permission: 'admin'")
  })

  it('DefaultLayout 真的调用了两个运行时 composable', () => {
    const layout = read('layouts/DefaultLayout.vue')
    // 正向：import 与调用都在
    expect(layout).toContain('useDisplayPreferencesRuntime')
    expect(layout).toContain('useGlobalTableLayout')
    // 反向自检：不是只在 import 语句里出现一次，setup 里必须真调用
    const calls = layout.match(/^\s*useDisplayPreferencesRuntime\(\)/m)
    expect(calls, 'DefaultLayout 必须调用 useDisplayPreferencesRuntime()').not.toBeNull()
    const runtimeCalls = layout.match(/^\s*useDisplayPreferencesRuntime\(\)/gm) ?? []
    const layoutCalls = layout.match(/^\s*useGlobalTableLayout\(\)/gm) ?? []
    expect(runtimeCalls, 'DefaultLayout 只能安装一个显示偏好运行时').toHaveLength(1)
    expect(layoutCalls, 'DefaultLayout 只能安装一个全局表格布局监听器').toHaveLength(1)

    // 面板只消费 store，不另起 GET；避免同页多个入口把首屏请求放大。
    const panel = read('components/settings/DisplayPreferencesPanel.vue')
    expect(panel).not.toContain('loadForUser(')
    expect(panel).not.toContain('getDisplayPreferences(')

    //    `toContain("'/display-settings'")` 判整个文件，而注释里也写了这个路径
    //    ⇒ 把数组元素删掉后注释仍能满足断言，变异存活（实测坐实）。
    const prefixesLine = layout
      .split(/\r?\n/)
      .find((l) => l.includes('const FULLWIDTH_PREFIXES'))
    expect(prefixesLine, 'DefaultLayout 必须有 FULLWIDTH_PREFIXES 定义').toBeTruthy()
    expect(prefixesLine).toContain("'/display-settings'")
    // 方向性：只加在注释里不算接线
    expect(prefixesLine!.trim().startsWith('//')).toBe(false)
  })

  it('两个运行时 composable 都有真实实现（不是空壳）', () => {
    const runtime = read('composables/useDisplayPreferencesRuntime.ts')
    // 必须写根变量：字号与密度各至少一处 setProperty
    expect(runtime).toContain('--gt-display-font-size')
    expect(runtime).toContain('--gt-table-row-height')
    expect(runtime).toContain('setProperty')

    const layout = read('composables/useGlobalTableLayout.ts')
    // 必须真调 doLayout（否则字号变化后列宽不会重算）
    expect(layout).toContain('doLayout')
    expect(layout).toContain('nextTick')
    expect(layout).toContain('displayPrefs.density')

    const density = read('composables/useTableDensityMetrics.ts')
    expect(density).toContain('useDisplayPrefsStore')
    expect(density).toContain('estimatedRowHeight')
    expect(density).toContain('remountKey')

    const ledger = read('views/LedgerPenetration.vue')
    expect(ledger).toContain('useTableDensityMetrics')
    // 🔴 densityMetrics 是普通对象包 ComputedRef，模板不自动解包，必须显式 .value
    // （漏写 .value 时 el-table-v2 拿到对象，虚拟列表渲染 0 行整表空白，2026-11-26 实测）
    expect(ledger).toContain(':estimated-row-height="densityMetrics.estimatedRowHeight.value"')
    expect(ledger).toContain(':header-height="densityMetrics.headerHeight.value"')
    // 反向：禁止回退到漏 .value 的缺陷写法（该写法曾让序时账 >1000 行时整表空白）
    expect(ledger).not.toContain(':estimated-row-height="densityMetrics.estimatedRowHeight"')
    expect(ledger).not.toContain(':header-height="densityMetrics.headerHeight"')
    expect(ledger).not.toContain(':estimated-row-height="50"')
  })

  it('ThreeColumnLayout 的 Aa 面板复用 DisplayPreferencesPanel，不再手写面板', () => {
    const tcl = read('layouts/ThreeColumnLayout.vue')
    // 正向：挂载同一组件
    expect(tcl).toContain('DisplayPreferencesPanel')
    expect(tcl).toContain('<DisplayPreferencesPanel compact')

    // 反向：手写面板的特征类必须已消失（这些类只服务那份 14 处 el-radio-group 的旧实现）
    expect(tcl).not.toContain('gt-dp-label')
    expect(tcl).not.toContain('gt-dp-hint')
    expect(tcl).not.toContain('gridEditModeHint')
  })

  it('Dashboard 快捷入口也按角色分流到普通用户显示设置', () => {
    const dashboard = read('views/Dashboard.vue')
    expect(dashboard).toContain("'/display-settings'")
    expect(dashboard).toContain("authStore.user?.role === 'admin'")
    expect(dashboard).not.toContain("{ label: '系统设置',   path: '/settings'")
  })

})
describe('显示设置：样式与复用（AC-07 剩余两条）', () => {
  it('gt-polish.css 的数据区字号读根变量而非固定 12px', () => {
    const css = read('styles/gt-polish.css')
    // 正向：表格表头 / 单元格 / 表内编辑控件都读 --gt-display-font-size
    const fontLines = css
      .split(/\r?\n/)
      .filter((l) => l.includes('font-size:') && l.includes('--gt-display-font-size'))
    expect(
      fontLines.length,
      'gt-polish.css 至少要有多处字号读 --gt-display-font-size（表头/单元格/cell/再入控件）',
    ).toBeGreaterThanOrEqual(4)

    // 反向：数据区选择器里不得再有固定 12px 覆盖。
    // 用「选择器块」切分判断，避免被别的组件里的 12px 误伤。
    const blocks = css.split(/}\s*\n/)
    const offenders = blocks.filter(
      (b) =>
        (b.includes('.el-table') || b.includes('.el-table-v2') || b.includes('.el-descriptions__label')) &&
        /font-size:\s*12px/.test(b),
    )
    expect(offenders, '数据区选择器不得用固定 12px 覆盖显示字号').toHaveLength(0)

    const global = read('styles/global.css')
    expect(global).toContain('--el-font-size-base: var(--gt-display-font-size')
    expect(global).toContain('font-size: var(--gt-display-font-size, var(--gt-font-size-sm))')

    const table = read('styles/gt-table.css')
    expect(table).toContain('font-size: var(--gt-display-font-size, 12px) !important;')
  })

  it('SystemSettings 复用同一面板（管理页 Tab），且不重复实现', () => {
    const sys = read('views/SystemSettings.vue')
    // 🔴 必须断言**真实挂载标签**，不能只断言文件名 —— 注释里也写着
    //    `DisplayPreferencesPanel`（实测：把挂载换成占位 div 后旧判据存活）。
    expect(sys).toContain('<DisplayPreferencesPanel')
    expect(sys).toContain('name="display"')
    // 反向：管理页不该自己再写一套金额单位 / 表格字号单选组
    expect(sys).not.toContain('unitOptions')
    expect(sys).not.toContain('fontOptions')
    expect(sys).not.toContain('gt-dp-label')
  })
})
describe('正式导出与个人偏好解耦（AC-20 前端侧）', () => {
  it('PDF 导出面板不再有「报表语言」选择器（评审 NIT：不做双语 PDF）', () => {
    const panel = read('views/PDFExportPanel.vue')
    // 正向：面板本身还在（不是把文件删了糊弄）
    expect(panel).toContain('导出选项')

    // 🔴 按**真实表单形态**断言，不断言裸词 —— 源码注释里会解释「为什么删掉」，
    //    用 `not.toContain('报表语言')` 会被自己的注释打红（本轮实测）。
    expect(panel).not.toMatch(/<el-form-item[^>]*label="[^"]*语言/)
    expect(panel).not.toMatch(/v-model="exportLanguage"/)
    // 也不该留语言选项（`<el-option ... value="en-US"`）
    expect(panel).not.toMatch(/<el-option[^>]*value="en-US"/)
  })
})