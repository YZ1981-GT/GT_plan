/**
 * spec: platform-global-display-settings-closure 任务 5 / AC-07
 *
 * 这些断言守的是「接线」，不是「文件存在」。该 spec 的复核记录（2026-11-14）
 * 抓到整整六条「文件在但链路断」：
 *   ① DisplaySettingsView.vue 在，但 router 里没有 /display-settings ⇒ 普通用户进不去；
 *   ② useDisplayPreferencesRuntime / useGlobalTableLayout 各有定义与单测，但**零生产调用方**
 *      ⇒ 改字号 / 改密度对真实页面毫无作用；
 *   ③ useTableDensityMetrics 根本不存在；
 *   ④ gt-polish.css 仍靠固定 12px 覆盖字号；
 *   ⑤ SystemSettings / ThreeColumnLayout 都没挂 DisplayPreferencesPanel（各写一份手写面板）。
 *
 * 所以判据一律按「源码里是否真的引用了」而不是「文件是否在磁盘上」。
 * 🔴 每条判据都配了正向断言（引用必须出现）与反向断言（旧写法必须消失），
 *    只做单向断言的话，「删掉旧面板」这类改动可以让两侧同时变绿而功能其实断了。
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
    const calls2 = layout.match(/^\s*useGlobalTableLayout\(\)/m)
    expect(calls2, 'DefaultLayout 必须调用 useGlobalTableLayout()').not.toBeNull()

    // 🔴 判据必须落在 FULLWIDTH_PREFIXES 的**赋值行**上：上一版只用
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

  it('顶栏系统设置入口按角色分流，非管理员不直推 /settings', () => {
    const tcl = read('layouts/ThreeColumnLayout.vue')
    // 正向：分流函数存在
    expect(tcl).toContain('openSettingsEntry')
    expect(tcl).toContain("'/display-settings'")
    // 反向：不能再是无条件 router.push('/settings')
    expect(tcl).not.toContain("router.push('/settings')")
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