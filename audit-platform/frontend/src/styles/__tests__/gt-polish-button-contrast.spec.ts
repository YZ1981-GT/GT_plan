/**
 * 按钮文字对比度防御 — gt-polish.css 内容验证
 *
 * 背景（D4-1 营业收入审定表实际暴露）：
 *   gt-polish.css 的 `.el-button--primary` / `.el-button--success` 用 !important
 *   强制深色渐变背景，且**未排除 .is-plain**，导致 plain 按钮也是深紫/深绿实心底；
 *   而 Element Plus 给 plain 变体的文字色是主题色本身 ⇒ 紫底紫字 / 绿底绿字不可读。
 *
 * 这里把"实心底必须白字"钉成断言，防止后续改动把白字兜底规则删掉而复发。
 *
 * 直接读 CSS 源码做存在性断言（CSS only，无 JS 行为可单测）。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const css = readFileSync(resolve(__dirname, '../gt-polish.css'), 'utf-8')

describe('gt-polish.css 按钮文字对比度', () => {
  it('primary / success 的实心+plain 变体统一白字（排除 text/link）', () => {
    // 形如：
    // .el-button--primary:not(.is-text):not(.is-link),
    // .el-button--success:not(.is-text):not(.is-link) { color: #fff !important; }
    expect(css).toMatch(
      /\.el-button--primary:not\(\.is-text\):not\(\.is-link\)\s*,\s*\.el-button--success:not\(\.is-text\):not\(\.is-link\)\s*\{[^}]*color:\s*#fff\s*!important/,
    )
  })

  it('白字规则排除 text/link 变体，避免白字白底', () => {
    const idx = css.search(/\.el-button--primary:not\(\.is-text\):not\(\.is-link\)/)
    expect(idx).toBeGreaterThan(-1)
    // 白字规则块内不得出现未排除 text/link 的裸选择器
    const block = css.slice(idx, css.indexOf('}', idx) + 1)
    expect(block).not.toMatch(/\.el-button--(primary|success)\s*[,{]/)
  })

  it('primary / success / danger 的 text/link 变体均恢复透明背景', () => {
    for (const variant of ['primary', 'success', 'danger']) {
      const re = new RegExp(
        `\\.el-button--${variant}\\.is-text\\s*,\\s*\\.el-button--${variant}\\.is-link\\s*\\{[^}]*background:\\s*transparent\\s*!important`,
      )
      expect(css, `${variant} 的 text/link 应无背景`).toMatch(re)
    }
  })

  it('success 的 text/link 显式给主题色文字（跟随明暗模式 token）', () => {
    expect(css).toMatch(
      /\.el-button--success\.is-text\s*,\s*\.el-button--success\.is-link\s*\{[^}]*color:\s*var\(--el-color-success\)\s*!important/,
    )
  })

  it('禁用态实心按钮保留透明度线索（背景渐变被 !important 接管）', () => {
    expect(css).toMatch(/\.el-button--primary\.is-disabled:not\(\.is-text\):not\(\.is-link\)/)
    expect(css).toMatch(/\.el-button--success\.is-disabled:not\(\.is-text\):not\(\.is-link\)/)
    expect(css).toMatch(/opacity:\s*0\.55\s*!important/)
  })

  it('danger 的实心变体仍显式白字（既有正确写法未被破坏）', () => {
    expect(css).toMatch(
      /\.el-button--danger:not\(\.is-text\):not\(\.is-link\):not\(\.is-plain\)\s*\{[^}]*color:\s*#fff\s*!important/,
    )
  })
})
