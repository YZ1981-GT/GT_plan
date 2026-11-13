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
/**
 * HTML↔OO 模式值字面量（排除纯业务分段器，如附注树筛选、调整分录来源筛选）。
 *
 * 🔴 第一版只认小写枚举 `'onlyoffice' | 'online-edit' | 'structured' | 'docx'`，
 *    **漏掉了 10 个 S 循环宿主**（`GtS3PolicyChange` / S4 / S5 / S6 / S12 / S13 / S14 /
 *    S15 / S20 / S21）—— 它们的选项值直接写成**英文标签** `'HTML'` / `'OnlyOffice'`，
 *    一个小写枚举都不出现 ⇒ 这 10 条债从来没进过分母，棘轮也就从来没提醒过。
 *    这与本 spec 反复抓到的「把标签当值」（A 轮 AC-41：17 条把中文标签直接当 mode 值）
 *    是同一形态，只是这次是英文。加上 `'HTML'` / `'OnlyOffice'` / `'oo'` 三个值。
 *    `'oo'` 来自 `J2TabAdjudication.vue` 的内联选项 `[{label:'OnlyOffice',value:'oo'}]`。
 */
const MODE_VALUE =
  /['"](?:onlyoffice|online-edit|structured|docx|OnlyOffice)['"]|value:\s*['"](?:oo|HTML|excel)['"]/
const HTML_MODE_VALUE = /value:\s*['"]html['"]|=== ?['"]html['"]/
/**
 * 🔴 2026-11-03 第二次补漏：中文标签直接当 mode 值。
 *
 * 上一轮补了英文标签（S 循环的 `'HTML'` / `'OnlyOffice'`），却没补中文 —— 而 A 轮 AC-41
 * 早就点名「17 条把中文标签直接当 mode 值」。现算（注释剥掉后）**48 个**宿主的模式开关
 * 选项是 `'结构化视图' / '在线编辑'` 这类中文标签，或由组合式（`useD4SyncMode` 的
 * `D4_ONLINE_EDIT_LABEL`、K 循环的 `kModeOptions`）给出，一个英文枚举都不出现 ⇒ 棘轮
 * 只认出 1 个（`D4TabContract.vue`，还是因为注释里恰好写了 `'onlyoffice'`），据此宣称的
 * 「全域零宿主自行决定」是假绿。补两条识别：
 *   ① 中文「在线编辑」作选项（允许 emoji 前缀，如 J1 的 `'📊 在线编辑'`）或经 D4 常量引用；
 *   ② 选项来自组合式、文件里看不到任何选项字面量时：挂了 OO 编辑载体，且某个分段器的
 *      模型绑定名以 `Mode` 结尾（`mode` / `editorMode` / `kEditorMode` …）。业务分段器
 *      （`activeA175Sub`、`activeType`）即使与载体同文件也不会被纳入。
 */
const ZH_ONLINE_EDIT = /['"][^'"\n]{0,8}在线编辑['"]|\bD4_ONLINE_EDIT_LABEL\b/
const OO_CARRIER = /<(?:WorkpaperSyncEditorHost|GtOnlyOfficeSheet|WorkpaperWordEditor)\b/
const SINGLE_SOURCE = /useEntrySyncReadiness|entrySyncPresentation/

/** 剥注释：注释里的模式值不是模式开关（`D4TabContract.vue` 曾只因注释被认出来）。 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

/** 引号感知地截出 `<el-segmented ...>` 开标签（属性值里的 `>` 不得当成标签结束）。 */
function segmentedOpenTags(text: string): string[] {
  const out: string[] = []
  let i = 0
  for (;;) {
    i = text.indexOf('<el-segmented', i)
    if (i < 0) return out
    let j = i + '<el-segmented'.length
    let quote: string | null = null
    while (j < text.length) {
      const ch = text[j]
      if (quote) {
        if (ch === quote) quote = null
      } else if (ch === '"' || ch === "'") {
        quote = ch
      } else if (ch === '>') {
        j += 1
        break
      }
      j += 1
    }
    out.push(text.slice(i, j))
    i = j
  }
}

/** 某个分段器的模型绑定名以 `Mode` 结尾（`dual.currentMode.value` 取最后一段）。 */
function hasModeBoundSegmented(text: string): boolean {
  return segmentedOpenTags(text).some((tag) => {
    const bound = /(?:^|\s)(?:v-model|:model-value)="([^"]+)"/.exec(tag)?.[1]
    if (!bound) return false
    const last = bound.replace(/\.value$/, '').split('.').pop() ?? ''
    return /^mode$|Mode$/.test(last)
  })
}

/** 文件级判定：画了分段器、没接单源、且分段器里有一个是 HTML ↔ OnlyOffice 模式开关。 */
function isHostLocalModeSwitch(raw: string): boolean {
  const text = stripComments(raw)
  if (!SEGMENTED.test(text) || SINGLE_SOURCE.test(text)) return false
  if (MODE_VALUE.test(text) || HTML_MODE_VALUE.test(text) || ZH_ONLINE_EDIT.test(text)) return true
  return OO_CARRIER.test(text) && hasModeBoundSegmented(text)
}

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
    .filter((rel) => isHostLocalModeSwitch(read(rel)))
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
    // 🔴 label-as-value 形态必须认得出（10 个 S 循环宿主正是这样写的，第一版全漏）
    expect(
      MODE_VALUE.test(`const modeOptions = [{ label: 'HTML', value: 'HTML' }, { label: '在线编辑', value: 'OnlyOffice' }]`),
      "把英文标签直接当 mode 值（'HTML' / 'OnlyOffice'）的宿主必须进分母",
    ).toBe(true)
    expect(
      MODE_VALUE.test(`[{ label: 'HTML', value: 'html' }, { label: 'OnlyOffice', value: 'oo' }]`),
      "内联 `value: 'oo'` 形态必须进分母",
    ).toBe(true)
    // 反例：业务控件里出现「HTML」字样（如导出格式）不得仅因此进分母
    expect(
      MODE_VALUE.test(`<el-segmented v-model="exportFmt" :options="['PDF', 'Word']" />`),
      '业务分段器不得被误纳',
    ).toBe(false)
  })

  it('中文标签当值、组合式给选项两种形态都必须进分母，业务分段器与注释不得误纳', () => {
    // ① 中文「在线编辑」直接当选项（A3 / B14 / I1 一类）
    expect(
      isHostLocalModeSwitch(
        `<el-segmented v-model="mode" :options="modeOptions" />\nconst modeOptions = ref(['结构化视图', '在线编辑'])`,
      ),
    ).toBe(true)
    // ①' 带 emoji 前缀的中文标签（J1 的 `'📊 在线编辑'`）
    expect(
      isHostLocalModeSwitch(`<el-segmented v-model="viewMode" :options="o" />\nconst o = [{ label: '📊 在线编辑', value: 'excel' }]`),
    ).toBe(true)
    // ② 选项由组合式给出，文件里没有任何选项字面量（D4 子 Tab / K 表 / B1 一类）
    expect(
      isHostLocalModeSwitch(
        `<el-segmented v-model="kEditorMode" :options="kModeOptions" />\n<WorkpaperSyncEditorHost :descriptor="d" />`,
      ),
    ).toBe(true)
    // 反例：载体同文件的业务分段器（A17 的子检查表切换、N1 的类型切换）
    expect(
      isHostLocalModeSwitch(
        `<el-segmented v-model="activeA175Sub" :options="subOptions" />\n<WorkpaperSyncEditorHost :descriptor="d" />`,
      ),
      '业务分段器因与载体同文件被误纳 ⇒ 分母虚高',
    ).toBe(false)
    // 反例：模式值只出现在注释里（D4TabContract 曾经只因为这个被认出）
    expect(
      isHostLocalModeSwitch(
        `<el-segmented v-model="bondBranch" :options="branchOptions" />\n// 原值 'structured'/'onlyoffice'，已改中文`,
      ),
      '注释里的模式值被当成模式开关',
    ).toBe(false)
    // 反例：接了单源的宿主即使写着中文标签也不进分母
    expect(
      isHostLocalModeSwitch(
        `<el-segmented v-if="x.presentation.value.showModeSwitch" v-model="mode" :options="['结构化视图','在线编辑']" />\nuseEntrySyncReadiness({})`,
      ),
    ).toBe(false)
  })

  it('没有新的「宿主自行决定模式开关」', () => {
    expect(actual.filter((rel) => !BASELINE.includes(rel))).toEqual([])
  })

  it('基线里没有已接单源 / 已删除的失效条目（表只许变短）', () => {
    expect(BASELINE.filter((rel) => !actual.includes(rel))).toEqual([])
  })
})
