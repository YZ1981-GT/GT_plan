/**
 * 挂载点 id 唯一性守卫（2026-11-06，spec trim-generation-plan-followup-optimizations R5.5 顺带修）。
 *
 * 真实缺陷：`index.html` 有 `<div id="app">`、`main.ts` 挂的就是它，而 `App.vue` 的模板根元素
 * 又写了一遍 `id="app"`。Vue 只替换挂载点的**内容**，所以运行期 DOM 里会有两个 `id="app"`
 * （外层带 `data-v-app`、内层是根组件）。后果：
 *   · 重复 id 是非法 HTML；
 *   · 任何按 `#app` 取节点的工具拿到歧义结果 —— 真实项目只读走查在 Playwright strict mode 上
 *     直接失败（`locator('#app') resolved to 2 elements`），而这一条断言本来是用来确认「页面渲染了」的，
 *     等于把一条有效判据变成了恒红。
 *
 * 判据按**源码文本**查，不靠挂载：挂载 `App.vue` 会连带拉起 router / pinia / Element Plus，
 * 判据会随无关依赖变红；而这里要守的恰好是「模板里不要写这个 id」这件事本身。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const FRONTEND_ROOT = resolve(__dirname, '..', '..')
const SRC_ROOT = join(FRONTEND_ROOT, 'src')
const INDEX_HTML = join(FRONTEND_ROOT, 'index.html')

/**
 * `id="app"` / `id='app'` / `:id="'app'"` 都算（后者是动态绑定写法，同样进 DOM）。
 *
 * 前面必须是 `(?<![-\w])`：`\b` 在 `-` 之后也成立，会把 `data-id="app"` 误命中
 * （本文件判据自检第一版就被它打红）。
 */
const APP_ID = /(?<![-\w])(?::id\s*=\s*(?:"'app'"|'"app"')|id\s*=\s*(?:"app"|'app'))/g

/**
 * 剥掉注释再判。注释里的 `id="app"` 进不了 DOM，不是缺陷 —— 而本文件自己的说明注释就写了这个
 * 字面量，第一版因此把 `App.vue` 误报成「2 处」（注释骗过文本扫描器的反向形态）。
 * 只剥注释、不剥字符串：JS 里拼出来的 markup 仍该被看见。
 */
function stripComments(text: string): string {
  return text
    .replace(/<!--[\s\S]*?-->/g, '') // 模板注释
    .replace(/\/\*[\s\S]*?\*\//g, '') // 脚本 / 样式块注释
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1') // 行注释（`[^:]` 避开 http:// 这类）
}

function listVueFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) {
      if (name === 'node_modules' || name === 'dist') continue
      listVueFiles(full, out)
      continue
    }
    if (name.endsWith('.vue')) out.push(full)
  }
  return out
}

describe('挂载点 id 唯一性', () => {
  const vueFiles = listVueFiles(SRC_ROOT)

  it('扫描面非空（否则下面的断言是恒绿的）', () => {
    expect(vueFiles.length).toBeGreaterThan(500)
  })

  it('index.html 恰好声明一个 id="app" 作为唯一挂载点', () => {
    const html = stripComments(readFileSync(INDEX_HTML, 'utf-8'))
    expect(html.match(APP_ID) ?? []).toHaveLength(1)
  })

  it('src 下任何 .vue 都不得再声明 id="app"', () => {
    const offenders = vueFiles
      .map((file) => ({ file, hits: (stripComments(readFileSync(file, 'utf-8')).match(APP_ID) ?? []).length }))
      .filter((entry) => entry.hits > 0)
      .map((entry) => `${relative(FRONTEND_ROOT, entry.file)}（${entry.hits} 处）`)

    expect(
      offenders,
      '挂载点 id 只能由 index.html 声明。组件模板里再写 id="app" 会在 DOM 里留下两个同 id 的元素，'
        + '让按 #app 取节点的工具（Playwright strict mode、document.querySelector 的调用方）拿到歧义结果',
    ).toEqual([])
  })

  it('判据自检：正则认出四种写法，且不误命中别的 id', () => {
    const matched = (text: string) => (text.match(APP_ID) ?? []).length
    expect(matched('<div id="app">')).toBe(1)
    expect(matched("<div id='app'>")).toBe(1)
    expect(matched('<div :id="\'app\'">')).toBe(1)
    expect(matched('<div :id=\'"app"\'>')).toBe(1)
    // 不该命中的：别的 id、以 app 开头 / 结尾的 id、模板插值
    expect(matched('<div id="application">')).toBe(0)
    expect(matched('<div id="my-app">')).toBe(0)
    expect(matched('<div :id="appId">')).toBe(0)
    expect(matched('<div data-id="app">')).toBe(0)
  })

  it('判据自检（双向）：注释里的字面量不算，同一段 markup 放出注释就必须被抓到', () => {
    const inMarkup = '<template>\n  <div id="app">x</div>\n</template>'
    const inComment = `<template>\n  <!-- 不要再写 id="app" -->\n  <div>x</div>\n</template>`
    const count = (text: string) => (stripComments(text).match(APP_ID) ?? []).length

    // 反向：注释里写了也不报（否则本文件自己的说明注释就会把 App.vue 打红）
    expect(count(inComment)).toBe(0)
    // 正向：同一个字面量落在 markup 上必须报 —— 否则「剥注释」就成了放行后门
    expect(count(inMarkup)).toBe(1)
    // 脚本注释同样不算，脚本里真拼 markup 仍要被看见
    expect(count('<script>// id="app"\nconst a = 1</script>')).toBe(0)
    expect(count('<script>el.innerHTML = \'<div id="app"></div>\'</script>')).toBe(1)
  })
})
