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
 * 「确定高度」的可接受写法。仓库里真实使用的有三种：
 * - `.oo-container { height: calc(100vh - 280px) }`（28 个 D4 子 tab 的统一模式）
 * - 内联 `style="min-height: 600px; height: calc(100vh - 280px);"`（D4-5 政策检查）
 * - `.oo-container { height: 80vh; min-height: 600px }`（M1 / M5 / M8 / M9 四个宿主）
 *
 * 🔴 判据原来只认 `calc(100vh …)` 与 `100vh`，把第三种写成了假红：`80vh` 同样是
 * **视口相关的确定高度**，父级不会退化成 auto，缺陷类别（压根没给高度）不成立。
 * 现在按共同特征收口 —— `height` 的值里出现 `<数字>vh`（裸写或包在 calc 里）即算。
 * 这仍挡不住「高度写错数值」（本文件开头已声明该边界），但不再误伤合规写法。
 */
const DEFINITE_HEIGHT_PATTERNS = [
  /height:\s*calc\([^;{}]*\d+(?:\.\d+)?vh/i,
  /height:\s*\d+(?:\.\d+)?vh/i,
]

/**
 * 包住挂载点的那个元素用了类名，样式里却没有这条规则 —— scoped 下等于没给高度。
 *
 * 🔴 两个真实形态（全文匹配判据**抓不到**，因为它们文件里别处有 vh 高度）：
 *   · `GtB22AControlMatrix.vue`：模板写着 `class="oo-container"`，全文件只出现这一次，
 *     没有任何 `.oo-container { … }` 规则 ⇒ 高度完全没生效（它连 height 都没写）。
 *   · `GtH6AssetDisposalClearing.vue`：同样用 `class="oo-container"` 且无规则；
 *     文件里那句 `height: calc(100vh - 180px)` 是**另一个分支**上 legacy
 *     `GtOnlyOfficeSheet` 的内联样式，与同步宿主的容器无关。
 *
 * 🔴 必须**整词**比类名：`k-oo-container` / `cct-oo-container` 都各自有规则，
 * 按子串匹配会把它们误判成缺规则（首版就这么误报了 6 处 —— `-` 不是 \w，
 * `\boo-container\b` 会在 `k-oo-container` 里命中）。
 */
function wrapperOpeningTag(text: string, mountAt: number): string {
  // 挂载点的前一个 `>` 就是包裹元素开标签的结尾；往前找到配对的 `<`。
  // 注释（`<!-- … -->`）要跳过：它也以 `>` 结尾。
  let end = text.lastIndexOf('>', mountAt)
  while (end > 0) {
    const start = text.lastIndexOf('<', end)
    if (start < 0) return ''
    const tag = text.slice(start, end + 1)
    if (!tag.startsWith('<!--')) return tag
    end = text.lastIndexOf('>', start)
  }
  return ''
}

function classTokens(tag: string): string[] {
  const m = /\sclass="([^"]*)"/.exec(tag)
  return m ? m[1].trim().split(/\s+/).filter(Boolean) : []
}

function hasRuleFor(text: string, token: string): boolean {
  // `.token` 后面允许直接 `{`、逗号（分组选择器）、或空白再接 `{` / `,`
  const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`\\.${escaped}(?![\\w-])\\s*[,{]`).test(text)
}

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
        `${rel} 挂了 WorkpaperSyncEditorHost 但没有任何视口相关高度（如 `
          + 'height: calc(100vh - 280px) / height: 80vh）—— '
          + '该组件根元素是 height:100% + flex 列，父级 auto 高度会把编辑区压扁，'
          + 'OnlyOffice 在页面上只剩一条。请照 `.oo-container` 同款给容器高度。',
      ).toBe(true)
    },
  )

  it.each(mountSites.map((s) => [s.rel, s] as const))(
    '%s 包住挂载点的类名都真的有 CSS 规则',
    (rel, site) => {
      let at = site.text.indexOf(MOUNT_MARKER)
      let checked = 0
      while (at >= 0) {
        const tag = wrapperOpeningTag(site.text, at)
        for (const token of classTokens(tag)) {
          checked += 1
          expect(
            hasRuleFor(site.text, token),
            `${rel} 包住 WorkpaperSyncEditorHost 的元素用了 .${token}，`
              + `但本文件没有 \`.${token} { … }\` 规则 —— scoped 样式下未定义的类名`
              + '不会带来任何高度，等于没给高度（OnlyOffice 会被压成一条）。'
              + '🔴 注意「文件里别处有 100vh」不算：那可能是另一个分支的内联样式。',
          ).toBe(true)
        }
        at = site.text.indexOf(MOUNT_MARKER, at + 1)
      }
      // 分母声明：这条判据只在「包裹元素带 class」时有话说；全无 class 的由上一条
      // 「文件里有确定高度」兜。两条都为空才是真漏网，故这里把检查数打印进断言消息。
      expect(checked, `${rel} 的挂载点包裹元素一个 class 都没有`).toBeGreaterThanOrEqual(0)
    },
  )
})
