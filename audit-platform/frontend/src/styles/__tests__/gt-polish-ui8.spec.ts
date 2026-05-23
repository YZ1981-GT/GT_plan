/**
 * UI-8 微交互增强 — gt-polish.css 内容验证
 *
 * 验证 task 5.5（UI-8）增加的三类 CSS 规则与 prefers-reduced-motion 降级：
 *  1) 按钮 :active 缩放 0.95
 *  2) 拖拽元素浮起阴影 + translateY(-2px)
 *  3) 状态标签 flip 动画（rotateY 0/90/0）
 *  4) prefers-reduced-motion: reduce 时禁用上述动画
 *
 * 直接读 CSS 源码做存在性断言（CSS only，无 JS 行为可单测）。
 * Validates: requirements §三 · UI-8 微交互增强
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const cssPath = resolve(__dirname, '../gt-polish.css')
const css = readFileSync(cssPath, 'utf-8')

describe('UI-8 gt-polish.css 微交互增强', () => {
  it('按钮 active 缩放规则存在（scale 0.95 + transition）', () => {
    expect(css).toMatch(/\.el-button:active\s*,\s*\.gt-btn:active\s*\{[^}]*transform:\s*scale\(0\.95\)/)
    expect(css).toMatch(/\.el-button:active\s*,\s*\.gt-btn:active\s*\{[^}]*transition:\s*transform\s+0\.1s/)
  })

  it('拖拽元素浮起阴影规则存在（box-shadow + translateY -2px）', () => {
    // [draggable="true"]:hover 选择器
    expect(css).toMatch(/\[draggable="true"\]:hover/)
    // .is-dragging 选择器
    expect(css).toMatch(/\.is-dragging/)
    // box-shadow 0 8px 16px
    expect(css).toMatch(/box-shadow:\s*0\s+8px\s+16px\s+rgba\(0,\s*0,\s*0,\s*0\.2\)/)
    // translateY(-2px)
    expect(css).toMatch(/transform:\s*translateY\(-2px\)/)
  })

  it('状态标签 flip keyframe 动画存在（rotateY 0 / 90 / 0）', () => {
    expect(css).toMatch(/@keyframes\s+gt-tag-flip/)
    expect(css).toMatch(/0%\s*\{\s*transform:\s*rotateY\(0deg\)/)
    expect(css).toMatch(/50%\s*\{\s*transform:\s*rotateY\(90deg\)/)
    expect(css).toMatch(/100%\s*\{\s*transform:\s*rotateY\(0deg\)/)
    // 触发器（gt-tag-flip / is-flipping）
    expect(css).toMatch(/\.gt-tag-flip/)
    expect(css).toMatch(/\.el-tag\.is-flipping/)
    // animation 引用
    expect(css).toMatch(/animation:\s*gt-tag-flip\s+0\.4s/)
  })

  it('prefers-reduced-motion: reduce 时禁用三类动画', () => {
    expect(css).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/)
    // 提取 reduced-motion 媒体查询块（粗略截取至文件结尾）
    const idx = css.indexOf('@media (prefers-reduced-motion: reduce)')
    expect(idx).toBeGreaterThan(-1)
    const reducedBlock = css.slice(idx)
    // 三类动画各自有 transform: none / animation: none / transition: none
    expect(reducedBlock).toMatch(/\.el-button:active[\s\S]*?transform:\s*none/)
    expect(reducedBlock).toMatch(/\[draggable="true"\]:hover[\s\S]*?transform:\s*none/)
    expect(reducedBlock).toMatch(/\.gt-tag-flip[\s\S]*?animation:\s*none/)
  })

  it('未破坏现有动画（progress shine + stale pulse 仍然保留）', () => {
    expect(css).toMatch(/@keyframes\s+gt-progress-shine/)
    expect(css).toMatch(/@keyframes\s+gt-stale-pulse/)
  })
})
