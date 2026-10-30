/**
 * 编辑器深链 ?cell=：HTML 路径交给 GtWpRenderer 的 initial-cell，编辑器只在 Univer 分支发定位事件
 * （spec wp-deeplink-cell-locate-closure 需求 1.1 / 1.3 / 1.4）。
 *
 * 编辑器组件依赖面太大，不在这里整页挂载；按源码结构判定（行为由 useRendererCellLocate 与浏览器实测覆盖）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parse } from '@vue/compiler-sfc'

const SRC = readFileSync(resolve(__dirname, '../../WorkpaperEditor.vue'), 'utf-8')
const { descriptor } = parse(SRC)
const template = descriptor.template?.content ?? ''
const script = descriptor.scriptSetup?.content ?? ''

function gtWpRendererTag(): string {
  const start = template.indexOf('<GtWpRenderer')
  expect(start).toBeGreaterThanOrEqual(0)
  return template.slice(start, template.indexOf('/>', start) + 2)
}

describe('WorkpaperEditor 深链 ?cell=', () => {
  it('GtWpRenderer 同时收到 initial-sheet 与 initial-cell', () => {
    const tag = gtWpRendererTag()
    expect(tag).toMatch(/:initial-sheet="initialSheetFromQuery"/)
    expect(tag).toMatch(/:initial-cell="[^"]*route\.query\.cell[^"]*"/)
  })

  it('深链定位事件只在 onMounted 异步块的 Univer 分支发（HTML 分支 return 之后）', () => {
    const emits = [...script.matchAll(/eventBus\.emit\('workpaper:locate-cell'/g)].map((m) => m.index!)
    const mounted = script.indexOf('onMounted(() => {')
    const htmlReturn = script.indexOf('if (useHtmlRenderer.value) {', mounted)
    const iifeEnd = script.indexOf('})()', mounted)
    expect(mounted).toBeGreaterThan(0)
    expect(htmlReturn).toBeGreaterThan(mounted)
    const deepLinkEmits = emits.filter((i) => i > mounted && script.slice(i - 400, i).includes('route.query.cell'))
    expect(deepLinkEmits).toHaveLength(1)
    expect(deepLinkEmits[0]).toBeGreaterThan(htmlReturn)
    expect(deepLinkEmits[0]).toBeLessThan(iifeEnd)
  })

  it('不再用「nextTick + 300ms 后发事件」等渲染器挂载', () => {
    expect(script).not.toMatch(/nextTick\(\(\) => \{\s*setTimeout\(\(\) => \{\s*eventBus\.emit\('workpaper:locate-cell'/)
  })
})
