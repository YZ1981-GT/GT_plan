/**
 * 宿主自行决定「HTML ↔ OnlyOffice 模式开关」表现 —— 全前端棘轮。
 *
 * spec workpaper-html-onlyoffice-bidirectional-writeback-closure（AC 1.4 / 12.8）：
 * 「能不能双向」是 entry 级事实（静态裁决 + 运行时 readiness + 真实验收三层），不是宿主
 * 的局部判断。宿主自己画 `el-segmented`、自己拼模式选项时，开关的可见性与可用性就与真实
 * 能力脱钩 —— 这正是「仅能打开 OO 却呈现成双向」的来源。
 *
 * 单源 = `useEntrySyncReadiness()` 的 `presentation`（`deriveEntrySyncPresentation`）。
 * 样板宿主：`GtM7SpecialReserve.vue`（已终裁 bidirectional，开关可见性改由单源决定，本地
 * `ooAvailable` 只保留为「这张 sheet 的 OO 侧能否拉起」的附加禁用条件）。
 *
 * 规模：现算 126 条宿主仍自行决定（其中 101 条已挂能力披露 notice，但开关仍是本地判断）。
 * 逐条改线要按宿主实测（各域 mode 值体系不同：`'onlyoffice'` / `'structured'` /
 * `'online-edit'` / `'docx'` / 中文标签当值），超出单轮能力 ⇒ 冻结成只许变短的棘轮：
 *
 *   * 新出现的「宿主自行决定」⇒ 红（要么接单源，要么证明它不是模式开关并进豁免）；
 *   * 表里的宿主接上单源后 ⇒ 红（必须从表里删掉，表不许留失效条目）。
 *
 * 🔴 判据**不按常量名**匹配：实测样板宿主的本地常量叫 `modeToggleOptions`，按
 *    `modeOptions` 一类名字的正则认不出它 —— 那样数出来的分母（85）比真值（126）少 41 条。
 *    改按「画了 segmented + 出现 HTML↔OO 模式值字面量 + 没导入单源」三条合取。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import BASELINE from './entrySyncModePresentationRatchet.baseline.json'

const SRC = resolve(__dirname, '../../../..')
const SEGMENTED = /<el-segmented\b/
/** HTML↔OO 模式值字面量（排除纯业务分段器，如附注树筛选、调整分录来源筛选）。 */
const MODE_VALUE = /['"](?:onlyoffice|online-edit|structured|docx)['"]/
const HTML_MODE_VALUE = /value:\s*['"]html['"]|=== ?['"]html['"]/
const SINGLE_SOURCE = /useEntrySyncReadiness|entrySyncPresentation/

/** 样板宿主：接单源后必须从基线里消失（本文件据此自证扫描器没失锚）。 */
const WIRED_REFERENCE = 'components/workpaper/GtM7SpecialReserve.vue'

function walk(dir: string, out: string[]): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (name === '__tests__' || name === 'node_modules') continue
    if (statSync(full).isDirectory()) walk(full, out)
    else if (name.endsWith('.vue')) out.push(full)
  }
  return out
}

function read(rel: string): string {
  return readFileSync(join(SRC, rel), 'utf-8')
}

function hostLocalModePresentation(): string[] {
  return walk(SRC, [])
    .map((file) => relative(SRC, file).split('\\').join('/'))
    .filter((rel) => {
      const text = read(rel)
      if (!SEGMENTED.test(text)) return false
      if (SINGLE_SOURCE.test(text)) return false
      return MODE_VALUE.test(text) || HTML_MODE_VALUE.test(text)
    })
    .sort()
}

describe('模式开关表现单源棘轮', () => {
  const actual = hostLocalModePresentation()

  it('扫描器分母没失锚（样板宿主确实画了 segmented，且确实接了单源）', () => {
    const text = read(WIRED_REFERENCE)
    expect(SEGMENTED.test(text), '样板宿主已不画 segmented ⇒ 扫描器失锚').toBe(true)
    expect(SINGLE_SOURCE.test(text), '样板宿主已不消费单源 ⇒ 改线被回退').toBe(true)
    expect(actual).not.toContain(WIRED_REFERENCE)
  })

  it('分母不为空（否则本棘轮在空集上恒绿）', () => {
    expect(BASELINE.length).toBeGreaterThan(50)
  })

  it('没有新的「宿主自行决定模式开关」', () => {
    expect(actual.filter((rel) => !BASELINE.includes(rel))).toEqual([])
  })

  it('基线里没有已接单源 / 已删除的失效条目（表只许变短）', () => {
    expect(BASELINE.filter((rel) => !actual.includes(rel))).toEqual([])
  })
})
