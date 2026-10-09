/**
 * 结构判据：每个挂载 `WorkpaperSyncEditorHost` 的宿主都必须给它**确定高度**的容器。
 *
 * 🔴 2026-09-22 真栈缺陷：`GtD4OperatingRevenue.vue` 把 `<WorkpaperSyncEditorHost>`
 * **裸渲染**（没有任何高度容器），而该组件根元素是 `height: 100%` + flex 列。父级高度为
 * `auto` 时 `height:100%` 解析成 auto，编辑区（`flex:1; min-height:0`）随之退化，
 * OnlyOffice 被压成一条，用户「根本看不清」（截图实证）。
 *
 * 同目录 28 个 D4 子 tab 全都有 `.oo-container { min-height:600px; height:calc(100vh - 280px) }`，
 * 只有这一处漏了 —— 典型的「同一模式 29 个落点、漏一个没人发现」。单测层面没有任何判据
 * 覆盖布局，所以它一路绿到用户手上。本文件补的就是这条。
 *
 * 判据形态说明：不解析 CSS 级联（jsdom 里 `WorkpaperSyncEditorHost` 的 scoped 样式与
 * 宿主样式都不真实生效，量不到像素），改为**源码级结构判据** —— 凡挂载该组件的 .vue
 * 文件，必须自己声明一处视口相关的确定高度。这挡不住「高度写错数值」，但挡得住
 * 「压根没给高度」这个真实发生过的类别。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

import { describe, expect, it } from 'vitest'

const COMPONENTS_ROOT = join(process.cwd(), 'src', 'components')

/** 挂载标记：模板里出现 `<WorkpaperSyncEditorHost` 即算一个落点。 */
const MOUNT_MARKER = '<WorkpaperSyncEditorHost'

/**
 * 「确定高度」的可接受写法。两种都在仓库里真实使用：
 * - `.oo-container` 类（28 个子 tab 的统一模式）
 * - 内联 `style="min-height: 600px; height: calc(100vh - 280px);"`（D4-5 政策检查）
 *
 * 共同特征是**视口相关的 height**，故判据落在 `height: calc(100vh` 上（容忍空格差异）。
 */
const DEFINITE_HEIGHT_PATTERNS = [/height:\s*calc\(\s*100vh/i, /height:\s*100vh/i]

function walkVueFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) {
      if (name === '__tests__' || name === 'node_modules') continue
      walkVueFiles(full, out)
    } else if (name.endsWith('.vue')) {
      out.push(full)
    }
  }
  return out
}

const mountSites = walkVueFiles(COMPONENTS_ROOT)
  .map((path) => ({ path, text: readFileSync(path, 'utf8') }))
  .filter((f) => f.text.includes(MOUNT_MARKER))
  .map((f) => ({ ...f, rel: relative(process.cwd(), f.path).replace(/\\/g, '/') }))

describe('WorkpaperSyncEditorHost 的每个挂载点都要给确定高度', () => {
  it('落点非空 —— 否则本文件是空分母重言式', () => {
    expect(mountSites.length).toBeGreaterThan(20)
  })

  it.each(mountSites.map((s) => [s.rel, s] as const))(
    '%s 声明了视口相关的确定高度',
    (rel, site) => {
      const hasHeight = DEFINITE_HEIGHT_PATTERNS.some((re) => re.test(site.text))
      expect(
        hasHeight,
        `${rel} 挂了 WorkpaperSyncEditorHost 但没有任何 height: calc(100vh …) 容器 —— `
          + '该组件根元素是 height:100% + flex 列，父级 auto 高度会把编辑区压扁，'
          + 'OnlyOffice 在页面上只剩一条。请照 `.oo-container` 同款给容器高度。',
      ).toBe(true)
    },
  )
})
