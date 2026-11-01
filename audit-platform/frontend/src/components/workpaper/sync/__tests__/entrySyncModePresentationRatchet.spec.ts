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

  // 🔴 原判据是 `expect(BASELINE.length).toBeGreaterThan(50)`，注释写的是「分母不为空，
  //    否则本棘轮在空集上恒绿」。但它把「写下它时还剩 126 条债」这个**过渡量**写成了永久
  //    不变量：棘轮每接走一批宿主，基线就更接近 50，减到 50 以下必红 —— 也就是**惩罚进展**，
  //    而唯一的「修法」会是把已接单源的宿主塞回基线。这与棘轮本身的方向正好相反
  //    （task 3.5 分批迁移到第六批时基线降到 32，这条就红了）。
  //
  //    它真正要防的事是「扫描器瞎了」：`walk` / `read` 一出问题，`actual` 变空集，
  //    下面两条差集判据就都恒绿。那件事与「还剩多少债」无关，应当直接断言**扫描面**非空
  //    与**识别正则可伪证**。基线自身的大小不需要另设下限 —— 下面两条差集判据合起来已经
  //    把 `BASELINE` 钉成与现实**逐条相等**的集合（双向差集都必须为空）。
  it('扫描面非空且识别正则可伪证（防本棘轮在空集 / 失锚上恒绿）', () => {
    const drawsSegmented = walk(SRC, [])
      .map((file) => relative(SRC, file).split('\\').join('/'))
      .filter((rel) => SEGMENTED.test(read(rel)))
    expect(drawsSegmented.length, '全前端一个 el-segmented 都扫不到 ⇒ 扫描器失锚').toBeGreaterThan(50)

    // 识别正则必须对已知正例命中、对已知反例不命中（否则 `actual` 可能恒空）
    expect(MODE_VALUE.test(`<el-segmented :options="[{value:'onlyoffice'}]" />`)).toBe(true)
    expect(HTML_MODE_VALUE.test(`currentMode === 'html'`)).toBe(true)
    expect(
      MODE_VALUE.test(`<el-segmented v-model="bondBranch" :options="branchOptions" />`),
      '纯业务分段器被当成模式开关 ⇒ 分母虚高',
    ).toBe(false)
  })

  it('没有新的「宿主自行决定模式开关」', () => {
    expect(actual.filter((rel) => !BASELINE.includes(rel))).toEqual([])
  })

  it('基线里没有已接单源 / 已删除的失效条目（表只许变短）', () => {
    expect(BASELINE.filter((rel) => !actual.includes(rel))).toEqual([])
  })
})
