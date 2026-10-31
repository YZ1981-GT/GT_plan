/**
 * 编辑器深链 ?sheet= / ?cell=：HTML 路径交给 GtWpRenderer 的 initial-sheet / initial-cell，
 * Univer 路径交给 UniverEditorCore 的同名属性（就绪后定位），编辑器本身不再定时发定位事件
 * （spec wp-deeplink-cell-locate-closure 需求 1.1 / 1.3 / 1.4；spec wp-deeplink-locate-coverage-closure 需求 4）。
 *
 * 编辑器组件依赖面太大，不在这里整页挂载；按源码结构判定（行为由 useRendererCellLocate、
 * UniverEditorCore.locate.spec 与浏览器实测覆盖）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parse } from '@vue/compiler-sfc'

const SRC = readFileSync(resolve(__dirname, '../../WorkpaperEditor.vue'), 'utf-8')
const { descriptor } = parse(SRC)
const template = descriptor.template?.content ?? ''
const script = descriptor.scriptSetup?.content ?? ''

function componentTag(name: string): string {
  const start = template.indexOf(`<${name}`)
  expect(start, `模板里没有 <${name}>`).toBeGreaterThanOrEqual(0)
  return template.slice(start, template.indexOf('/>', start) + 2)
}

describe('WorkpaperEditor 深链 ?sheet= / ?cell=', () => {
  it('GtWpRenderer 同时收到 initial-sheet 与 initial-cell', () => {
    const tag = componentTag('GtWpRenderer')
    expect(tag).toMatch(/:initial-sheet="initialSheetFromQuery"/)
    expect(tag).toMatch(/:initial-cell="[^"]*route\.query\.cell[^"]*"/)
  })

  it('UniverEditorCore 同时收到 initial-sheet 与 initial-cell', () => {
    const tag = componentTag('UniverEditorCore')
    expect(tag).toMatch(/:initial-sheet="initialSheetFromQuery"/)
    expect(tag).toMatch(/:initial-cell="[^"]*route\.query\.cell[^"]*"/)
  })

  it('编辑器不再按 route.query.cell 自己发定位事件（两条分支都由子组件就绪后处理）', () => {
    const emits = [...script.matchAll(/eventBus\.emit\('workpaper:locate-cell'/g)].map((m) => m.index!)
    const deepLinkEmits = emits.filter((i) => script.slice(Math.max(0, i - 400), i).includes('route.query.cell'))
    expect(deepLinkEmits).toEqual([])
  })

  it('不再用定时器延后发定位事件', () => {
    expect(script).not.toMatch(/setTimeout\(\s*\(\)\s*=>\s*eventBus\.emit\('workpaper:locate-cell'/)
    expect(script).not.toMatch(/nextTick\(\(\) => \{\s*setTimeout\(\(\) => \{\s*eventBus\.emit\('workpaper:locate-cell'/)
  })
})
