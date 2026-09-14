/**
 * H5 上市披露「本版不适用」守卫（spec `h-cycle-extraction-formula-and-disclosure-completion` Task 11）
 *
 * 钉死五项，防被回退成「补回披露表」：
 *
 * 1. 组件零同步链路（`useDisclosureAutoSync` / `scheduleAutoSync` / `sync-from-workpaper`）
 * 2. **源码不得出现 `?? '五、…'` 形态的章节号兜底** —— 改造前写的是
 *    `noteSectionId: H5_NOTE_SECTION.listed ?? '五、油气资产'`，而 `H5_NOTE_SECTION`
 *    连 `listed` 键都没有（`?? ` 恒取右值）⇒ 向 AI／复核链路下发 listed 模板里
 *    **不存在**的虚构章节号。这是 Task 11 修的真缺陷。
 * 3. `H5_NOTE_SECTION` 无 `listed` 键（判据真源侧）
 * 4. 判据文案必须如实说「源 sheet 有表格但附注无落点」，**不得**照抄 N4 国企侧的
 *    「源模板内容为无」—— openpyxl 直读实证 H5 的 `附注披露信息（上市公司）` 是
 *    visible 且有完整 38 行四层表（`A7:G7` 表头 + 行 8~38），N4 的 soe sheet 才是
 *    逐字 `附注披露信息：` / `无`。照抄即事实错误。
 * 5. `buildH5SyncPayload` 类型层不接受 `'listed'`（恒发 soe 口径）
 *
 * 🔴 标签／字符串存在性断言一律带边界，`toContain('<Foo')` 会被 `<FooREMOVED` 骗过。
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

// 本文件位于 .../components/workpaper/h5/__tests__/ → 回仓库根需 7 级
const REPO_ROOT = path.resolve(__dirname, '../../../../../../..')
const WP_DIR = path.join(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper')

const LISTED_REL = 'h5/core/H5TabDisclosureListed.vue'
const SOE_REL = 'h5/core/H5TabDisclosureSoe.vue'
const MAP_REL = 'composables/h5NoteSectionMap.ts'
const HOST_REL = 'GtH5OilGasAssets.vue'

function readWp(rel: string): string {
  const p = path.join(WP_DIR, rel)
  // 路径写错时表现为「文件级失败」而非断言失败 → 显式抛，防守卫静默空转
  if (!fs.existsSync(p)) throw new Error(`守卫路径失效（REPO_ROOT 回退级数错？）: ${p}`)
  return fs.readFileSync(p, 'utf-8')
}

/** 剥 HTML 注释 + JS 行/块注释（注释里写着反例，不剥必误判） */
export function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/** 按花括号配对取 `export const NAME = { ... }` 的对象体 */
export function constObjectBody(src: string, name: string): string {
  const m = new RegExp(`export const ${name}\\s*(?::[^=]*)?=\\s*\\{`).exec(src)
  if (!m) throw new Error(`未找到 export const ${name} = {`)
  const open = src.indexOf('{', m.index)
  let depth = 0
  for (let i = open; i < src.length; i++) {
    if (src[i] === '{') depth++
    else if (src[i] === '}') {
      depth--
      if (depth === 0) return src.slice(open + 1, i)
    }
  }
  throw new Error(`${name} 花括号未配对`)
}

const LISTED_RAW = readWp(LISTED_REL)
const LISTED = stripComments(LISTED_RAW)
const MAP_RAW = readWp(MAP_REL)
const MAP = stripComments(MAP_RAW)

describe('H5 上市披露改「本版不适用」（Task 11 / R12.1~R12.6）', () => {
  it('解析器自检：文件非空且已剥注释（防断言空转）', () => {
    expect(LISTED.length).toBeGreaterThan(500)
    // 注释里刻意保留了改造前的反例形态，剥注释后不应残留
    expect(LISTED_RAW).toContain('五、油气资产')
    expect(LISTED, '注释里的反例不得参与判定').not.toContain('五、油气资产')
  })

  it('R12.1：零同步链路（不推送、不新建附注章节）', () => {
    for (const forbidden of [
      'useDisclosureAutoSync',
      'scheduleAutoSync',
      'sync-from-workpaper',
      'syncToDisclosureNotes',
    ]) {
      expect(LISTED, `不适用页不应含 ${forbidden}`).not.toContain(forbidden)
    }
  })

  it('R12.5：禁章节号兜底字面量（原缺陷 = 下发虚构章节号）', () => {
    expect(LISTED, "禁 `?? '五、…'` 形态").not.toMatch(/\?\?\s*['"][一二三四五六七八九十]+、/)
    // 连带：不再接 AI／自造附注表
    for (const forbidden of [
      'useHCycleDisclosureAi',
      'WpNoteTextArea',
      'costNoteRows',
      'depletionNoteRows',
      'H5-disc-listed-text',
    ]) {
      expect(LISTED, `不适用页不应含 ${forbidden}`).not.toContain(forbidden)
    }
  })

  it('R12.2：H5_NOTE_SECTION 无 listed 键（判据真源侧）', () => {
    const body = constObjectBody(MAP, 'H5_NOTE_SECTION')
    expect(body).toMatch(/\bsoe\s*:/)
    expect(body, 'listed 侧无附注落点，不得新增该键').not.toMatch(/\blisted\s*:/)
  })

  it('R12.3：判据文案如实说「源 sheet 有表格但无落点」，不得照抄 N4「内容为无」', () => {
    const body = constObjectBody(MAP_RAW, 'H5_LISTED_NOT_APPLICABLE_REASON')
    // 必须点名源 sheet。允许经常量引用（`sourceSheet: H5_DISCLOSURE_SHEET_LISTED`
    // 与模板串 `${H5_DISCLOSURE_SHEET_LISTED}`）—— 那是单一真源的正确写法，
    // 故这里断言「引用了该常量」，常量本身的字面量由下一条断言钉死。
    expect(body, '判据必须点名源 sheet（直接字面量或引用 H5_DISCLOSURE_SHEET_LISTED）').toMatch(
      /附注披露信息（上市公司）|H5_DISCLOSURE_SHEET_LISTED/,
    )
    expect(MAP, 'H5_DISCLOSURE_SHEET_LISTED 必须逐字等于源 xlsx 的 tab 名').toMatch(
      /H5_DISCLOSURE_SHEET_LISTED\s*=\s*'附注披露信息（上市公司）'/,
    )
    expect(body, '必须承认源 sheet 有表格（openpyxl 实证 38 行四层表）').toMatch(/有表格|四层/)
    // 三条落点侧判据
    expect(body).toMatch(/listed_standalone/)
    expect(body).toMatch(/note_template_listed\.json/)
    // 🔴 反向：不得出现 N4 那套「内容为无」措辞（对 H5 是事实错误）
    expect(body, 'H5 源 sheet 不是「无内容」，禁照抄 N4 措辞').not.toMatch(
      /内容为「?无」?|sheet\s*内容.*无表格|全\s*sheet\s*无表格/,
    )
  })

  it('组件展示判据文案（不是把常量渲染成 [object Object]）', () => {
    expect(LISTED).toContain('H5_LISTED_NOT_APPLICABLE_REASON')
    // 对象常量必须逐字段渲染：summary + evidence 列表
    expect(LISTED, '缺 summary 渲染').toMatch(/H5_LISTED_NOT_APPLICABLE_REASON\.summary/)
    expect(LISTED, 'evidence 应逐条渲染成列表').toMatch(
      /v-for[^>]*H5_LISTED_NOT_APPLICABLE_REASON\.evidence/,
    )
  })

  it('R12.4：保留返回目录 / 跳国企版 / 复核入口', () => {
    expect(LISTED).toMatch(/emit\(\s*'navigate'/)
    expect(LISTED, '应提供跳国企版披露表的入口').toContain('H5_DISCLOSURE_SHEET_SOE')
    expect(LISTED, '缺复核入口').toMatch(/<GtReviewTrigger(?=[\s/>])/)
  })

  it('R12.6：buildH5SyncPayload 恒发 soe 口径，类型层不接受 listed', () => {
    expect(MAP).toMatch(/current_standard:\s*'soe_standalone'/)
    // 入参没有 variant 维度 ⇒ 结构上无法发 listed
    const opts = MAP.slice(MAP.indexOf('interface H5SyncPayloadOptions'))
    const body = opts.slice(opts.indexOf('{'), opts.indexOf('}') + 1)
    expect(body, '入参不得引入 variant/standard 维度（否则可发 listed）').not.toMatch(
      /variant|listed/,
    )
  })

  it('宿主仍按 sheet 分发到该 Tab（不适用页也要能打开）', () => {
    const host = stripComments(readWp(HOST_REL))
    expect(host).toMatch(/<H5TabDisclosureListed(?=[\s/>])/)
    expect(host).toMatch(/v-else-if="currentSheet === '附注上市'"/)
  })

  it('国企版不受影响（仍有披露表与持久化）', () => {
    const soe = stripComments(readWp(SOE_REL))
    expect(soe).toContain('H5-disc-soe-text')
    expect(soe).toContain('buildH5SyncPayload')
  })
})

describe('反向自检（证明上面的断言不是空转）', () => {
  it('注入章节号兜底后该断言必红', () => {
    const mutated = `${LISTED}\n  noteSectionId: H5_NOTE_SECTION.listed ?? '五、油气资产',\n`
    expect(mutated).toMatch(/\?\?\s*['"][一二三四五六七八九十]+、/)
  })

  it('注入 useDisclosureAutoSync 后同步链路断言必红', () => {
    const mutated = `${LISTED}\nimport { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'\n`
    expect(mutated).toContain('useDisclosureAutoSync')
  })

  it('把文案改成 N4 的「内容为无」措辞后必红', () => {
    const fake = `evidence: ['源模板 sheet 内容是 附注披露信息： / 无，全 sheet 无表格。']`
    expect(fake).toMatch(/全\s*sheet\s*无表格/)
  })

  it('给 H5_NOTE_SECTION 加 listed 键后必红', () => {
    const fake = `export const H5_NOTE_SECTION = { soe: '八、25', listed: '五、油气资产' } as const`
    const body = constObjectBody(fake, 'H5_NOTE_SECTION')
    expect(body).toMatch(/\blisted\s*:/)
  })

  it('stripComments 自检：注释里的禁用符号不参与判定', () => {
    const withComment = `<!-- 反例：useDisclosureAutoSync -->\nconst a = 1`
    expect(stripComments(withComment)).not.toContain('useDisclosureAutoSync')
    expect(withComment).toContain('useDisclosureAutoSync')
  })
})
