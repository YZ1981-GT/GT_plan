/**
 * GtWpRenderer.overlay.spec.ts — overlay not_applicable 三态测试
 *
 * Feature: s-cycle-linkage-trimming-and-component-wiring, D1.2
 *
 * GtWpRenderer 依赖链过深不适合浅挂载测试 overlay 逻辑。
 * 本测试直接验证 overlay 的计算契约和源码守卫：
 * 1. isWpNotApplicable 的 computed 逻辑（纯函数等价）
 * 2. 模板中的条件链顺序（redirect → not_applicable → 正常渲染）
 * 3. 中文文案正确性
 *
 * 浏览器级 overlay 验收由 F3 Playwright 覆盖。
 */
import * as fs from 'node:fs'
import * as path from 'node:path'
import { describe, expect, it } from 'vitest'

// ─── 纯函数：等价于 GtWpRenderer.vue L520-522 的 computed 逻辑 ───
function isWpNotApplicable(renderConfig: Record<string, any> | null | undefined): boolean {
  return renderConfig?.not_applicable === true
}

// ─── 源码守卫：直接读 .vue 文件确认模板结构 ───
const VUE_FILE = path.resolve(
  __dirname,
  '..',
  'GtWpRenderer.vue',
)
const vueSource = fs.readFileSync(VUE_FILE, 'utf-8')

describe('D1.2 GtWpRenderer overlay — not_applicable 三态', () => {
  // ---- 计算逻辑 ----
  it('not_applicable=true → 返回 true', () => {
    expect(isWpNotApplicable({ not_applicable: true })).toBe(true)
  })

  it('not_applicable=false → 返回 false', () => {
    expect(isWpNotApplicable({ not_applicable: false })).toBe(false)
  })

  it('not_applicable 缺失 → 返回 false', () => {
    expect(isWpNotApplicable({})).toBe(false)
    expect(isWpNotApplicable(null)).toBe(false)
    expect(isWpNotApplicable(undefined)).toBe(false)
  })

  it('not_applicable="true"（字符串）→ 返回 false（严格 === true）', () => {
    expect(isWpNotApplicable({ not_applicable: 'true' })).toBe(false)
  })

  // ---- 源码守卫：确认 .vue 文件中的关键结构 ----
  it('源码中 isWpNotApplicable 只消费 renderConfig.not_applicable', () => {
    // 确认 computed 定义存在且只读 not_applicable
    expect(vueSource).toContain('renderConfig.value?.not_applicable === true')
    // 不读 project_context
    const notApplicableBlock = vueSource.slice(
      vueSource.indexOf('isWpNotApplicable'),
      vueSource.indexOf('isWpNotApplicable') + 200,
    )
    expect(notApplicableBlock).not.toContain('project_context')
  })

  it('模板条件链：redirect 在 not_applicable 之前', () => {
    const redirectPos = vueSource.indexOf('v-if="renderConfig.redirect"')
    const notApplicablePos = vueSource.indexOf('v-else-if="isWpNotApplicable"')
    expect(redirectPos).toBeGreaterThan(-1)
    expect(notApplicablePos).toBeGreaterThan(-1)
    expect(redirectPos).toBeLessThan(notApplicablePos)
  })

  it('覆盖层中文文案为"不适用"', () => {
    expect(vueSource).toContain('title="不适用"')
    expect(vueSource).toContain('当前项目类型不适用此底稿')
  })

  it('覆盖层使用 gt-wp-renderer__not-applicable CSS 类', () => {
    expect(vueSource).toContain('gt-wp-renderer__not-applicable')
  })
})
