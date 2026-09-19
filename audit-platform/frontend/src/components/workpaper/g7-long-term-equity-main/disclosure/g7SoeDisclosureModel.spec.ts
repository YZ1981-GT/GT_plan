import { describe, expect, it } from 'vitest'
import {
  G7_SOE_DISCLOSURE_SECTIONS,
  buildG7SoeSyncPayloads,
  createG7SoeDisclosureState,
  g7SoeChapterSections,
} from './g7SoeDisclosureModel'

describe('G7 SOE disclosure source model', () => {
  it('splits the sheet into consolidation-scope and long-term-equity chapters', () => {
    const chapterIds = [...new Set(G7_SOE_DISCLOSURE_SECTIONS.map(section => section.chapter))]
    expect(chapterIds).toEqual(['consolidation-scope', 'long-term-equity'])

    const consolidation = g7SoeChapterSections('consolidation-scope')
    const longTerm = g7SoeChapterSections('long-term-equity')
    expect(consolidation.map(section => section.id)).toContain('subsidiary-basic')
    expect(consolidation.map(section => section.id)).toContain('common-control-combination')
    expect(consolidation.map(section => section.id)).toContain('ownership-interest-changes')
    expect(longTerm.map(section => section.id)).toEqual(['long-term-equity-investment'])
  })

  it('keeps heterogeneous tables instead of a uniform 17-column placeholder', () => {
    const tables = G7_SOE_DISCLOSURE_SECTIONS.flatMap(section => section.tables ?? [])
    const narratives = G7_SOE_DISCLOSURE_SECTIONS.flatMap(section => section.narratives ?? [])
    expect(tables.length).toBeGreaterThanOrEqual(20)
    expect(narratives.length).toBeGreaterThanOrEqual(15)

    const subsidiary = tables.find(table => table.id === 'subsidiary-basic')
    expect(subsidiary?.sourceRows).toBe('A9:M19')
    expect(subsidiary?.columns.map(column => column.key)).toContain('level')
    expect(subsidiary?.columns.map(column => column.key)).toContain('acquisitionMethod')

    const classification = tables.find(table => table.id === 'lte-classification')
    expect(classification?.sourceRows).toBe('A201:F208')
    expect(classification?.columns).toHaveLength(4)
  })

  it('routes sync payloads to multiple note sections, not only long-term equity', () => {
    const state = createG7SoeDisclosureState()
    state.texts['holding-voting-diff'] = '持股比例与表决权比例差异说明。'
    state.texts['lte-holding-voting-diff'] = '索引至附注十一、3。'
    state.tables['subsidiary-basic'][0].label = '甲子公司'

    const payloads = buildG7SoeSyncPayloads(state)
    const sectionIds = payloads.map(payload => payload.noteSectionId)
    expect(sectionIds).toContain('七、本期纳入合并报表')
    expect(sectionIds).toContain('七、本期发生的同一控')
    expect(sectionIds).toContain('八、18')
    expect(sectionIds).not.toContain('五、18')

    const consolidationPayload = payloads.find(payload => payload.noteSectionId === '七、本期纳入合并报表')
    // 🔴 标签键为平台惯例 `label`（不是中文字面量 `项目`）。改造依据见
    // `buildG7SoeColumns()` 的注释：平台 266 个标签列定义里 241 个用 `'label'`，
    // 中文字面量当 key 违反禁硬编码。行对象标签键必须与标签列 `key` 逐字一致，
    // 否则投影器 `_project_row` 取 `r.get(label_key)` 拿不到值 ⇒ 整表行名变空。
    const consolidationRow0 = consolidationPayload?.subTableData['本期纳入合并报表范围的子公司基本情况'][0] as Record<string, unknown>
    expect(consolidationRow0.label).toBe('甲子公司')
    // 反向锚定：旧中文键不得复活（复活即与标签列 key 分叉 ⇒ 行名丢失）
    expect(Object.keys(consolidationRow0)).not.toContain('项目')
    expect(consolidationPayload?.subTableData._note_texts).toEqual([
      {
        section: 'holding-voting-diff',
        title: '持股比例与表决权比例差异说明',
        text: '持股比例与表决权比例差异说明。',
      },
    ])

    const mismatch = payloads.find(payload => payload.noteSectionId === '七')
    expect(mismatch).toBeTruthy()

    const ltePayload = payloads.find(payload => payload.noteSectionId === '八、18')
    expect(ltePayload?.subTableData['长期股权投资分类']).toBeTruthy()
    expect(ltePayload?.subTableData['长期股权投资明细']).toBeTruthy()
    expect(ltePayload?.subTableData._note_texts?.some((item: any) => item.section === 'lte-holding-voting-diff')).toBe(true)
  })

  it('materializes computed totals and keeps G7-16 associate lineage starting at row 17', () => {
    const state = createG7SoeDisclosureState()
    state.tables['lte-classification'].find(row => row.id === 'lte-sub')!.values.closing = 100
    state.tables['lte-classification'].find(row => row.id === 'lte-jv')!.values.closing = 40
    state.tables['lte-classification'].find(row => row.id === 'lte-assoc')!.values.closing = 20
    state.tables['lte-classification'].find(row => row.id === 'lte-impairment')!.values.closing = 15

    const payloads = buildG7SoeSyncPayloads(state)
    const ltePayload = payloads.find(payload => payload.noteSectionId === '八、18')
    const classification = ltePayload?.subTableData['长期股权投资分类'] ?? []
    const total = classification.find((row: any) => row._row_id === 'lte-total')
    expect(total?.closing).toBe(145)

    // 🔴 骨架行数由 `dynamicRowCount(seedRowCount)` 派生（平台铁律：动态区禁写死
    // 3/5/10 行）—— 无 seed 数据时两段各 1 行，故不得断言 `ul-assoc-3` 存在。
    // 该测试的真实意图 = 「联营段血缘起点是 G7-16 第 17 行，与合营段第 12 行不同」，
    // 对应源模板 `附注披露信息（国企）` r303→G7-16!B12 / r308→G7-16!B17。
    const ul = state.tables['unrecognized-losses']
    const jvFirst = ul.find(row => row.id === 'ul-jv-1')
    const assocFirst = ul.find(row => row.id === 'ul-assoc-1')
    expect(jvFirst?.source).toContain('第12行')
    expect(assocFirst?.source).toContain('第17行')
    // 反向自检：两段起点必须不同（防被写成同一偏移，届时联营血缘会指向合营行）
    expect(assocFirst?.source).not.toEqual(jvFirst?.source)
    // 骨架行数与 dynamicRowCount(1)=1 一致：无 seed 时每段恰 1 行**数据行**。
    // 🔴 判据必须锚定 `-\d+$`：裸 `startsWith('ul-assoc-')` 会把
    // `ul-assoc-group` / `ul-assoc-subtotal` 也数进去（实测得 3，与旧断言的
    // 「3 行数据」巧合重合 → 会掩盖行数回退）。
    const dataRows = (prefix: string) =>
      ul.filter(row => new RegExp(`^${prefix}-\\d+$`).test(row.id))
    expect(dataRows('ul-assoc').length).toBe(1)
    expect(dataRows('ul-jv').length).toBe(1)
    // 结构行仍在（小计/合计靠它们求和），只是不算数据行
    expect(ul.some(row => row.id === 'ul-assoc-subtotal')).toBe(true)
    expect(ul.some(row => row.id === 'ul-jv-subtotal')).toBe(true)
  })

  it('preserves source-workpaper lineage on formula-driven rows', () => {
    const state = createG7SoeDisclosureState()
    expect(state.tables['subsidiary-basic'][0].source).toContain('被投资单位基本信息G7-4')
    expect(state.tables['former-subsidiary-basic'][0].source).toContain('处置子公司测试表G7-11')
    expect(state.tables['lte-classification'].find(row => row.id === 'lte-jv')?.source).toContain('G7-1')
    expect(state.tables['important-jv-fs'][0].source).toContain('G7-5')
    expect(state.tables['unrecognized-losses'].find(row => row.id === 'ul-jv-1')?.source).toContain('G7-16')
  })
})


// ═════════════════════════════════════════════════════════════════════════════
// `_removed_table_keys` 逐章节差集（Task 13）
//
// ## 改造前的实际状态（本组守卫要防的就是它回来）
//
// soe 侧这条链**整条是死的**：`dataTableNames` / `buildRemovedTableKeys` 在
// `g7SoeDisclosureModel.ts` 里的调用数都是 **0**（死导入），`markG7SoeSynced` 不存在，
// `previouslySyncedTables` 只在 `createG7SoeDisclosureState()` 里被初始化成 `{}`
// 并由 `G7TabDisclosureSOE.vue` 持久化时原样透传 —— **无写入方、也无消费方**。
//
// 后果：披露同步按 key **浅合并**，删除必须显式上报 `_removed_table_keys`；
// soe 侧既然从不上报，删表/改名后附注侧 `sub_table_data` 与 `_sub_table_columns`
// 就**永久残留**过时明细（附注多出永不消失的空 TAB / 旧数据）。
// 而 listed 侧同一能力早已接通 ⇒ 两个变体行为长期不一致。
//
// ## 🔴 判据为什么必须是「行为级 + 端到端」
//
// 这类断链在四层验证里全绿：`get_diagnostics` 只看类型、vitest 若手动塞
// `previouslySyncedTables` 就能把 `buildRemovedTableKeys` 测绿、HEAD-swap 看不出、
// 浏览器不点「删表再同步」也看不出。所以本组不断言「符号存在」，而是断言
// **「不喂基线 ⇒ 无 removed；喂了基线 ⇒ 恰好删掉过时键且绝不碰本次推送键」**，
// 并额外钉住宿主三处接线（回写 / 落库 / 载入恢复）缺一即断链。
// ═════════════════════════════════════════════════════════════════════════════

describe('G7 SOE `_removed_table_keys` 逐章节差集', () => {
  it('首次同步（基线为空）不上报 removed —— 无基线时删任何键都是越权', () => {
    const state = createG7SoeDisclosureState()
    const payloads = buildG7SoeSyncPayloads(state)
    expect(payloads.length).toBeGreaterThanOrEqual(11)
    for (const payload of payloads) {
      expect(
        payload.subTableData._removed_table_keys,
        `${payload.noteSectionId} 在无基线时上报了 removed（越权删）`,
      ).toBeUndefined()
    }
  })

  it('有基线时按章节求「上次推送 − 本次推送」，且本次推送键绝不进 removed', () => {
    const state = createG7SoeDisclosureState()
    const first = buildG7SoeSyncPayloads(state)

    // 取一个真实章节，在其基线里混入「一个已废弃表名」+「本次仍会推送的表名」
    const target = first.find(p => p.noteSectionId === '八、18')
    expect(target, 'soe 应有 八、18 章节载荷').toBeDefined()
    const pushedNames = Object.keys(target!.subTableData).filter(k => !k.startsWith('_'))
    expect(pushedNames.length).toBeGreaterThan(0)

    state.previouslySyncedTables = {
      '八、18': [...pushedNames, '已废弃的历史表名'],
    }
    const second = buildG7SoeSyncPayloads(state)
    const removed = second.find(p => p.noteSectionId === '八、18')!
      .subTableData._removed_table_keys as unknown as string[] | undefined

    expect(removed, '基线里的过时表名应被上报').toEqual(['已废弃的历史表名'])
    // 推送优先：本次推送的键一个都不能出现在 removed 里
    for (const name of pushedNames) {
      expect(removed).not.toContain(name)
    }
  })

  it('removed 键与本次推送键无交集（逐章节校验，不只抽样）', () => {
    const state = createG7SoeDisclosureState()
    // 给每个章节都造一个「基线 = 本次推送 ∪ 一个废弃名」的场景
    const base = buildG7SoeSyncPayloads(state)
    const seeded: Record<string, string[]> = {}
    for (const p of base) {
      const pushed = Object.keys(p.subTableData).filter(k => !k.startsWith('_'))
      // 🔴 注入名**不得以 `_` 开头**：`buildRemovedTableKeys` 会剔除元数据键
      //    （`isMetaKey`），用 `__废弃__…` 当替身会被静默过滤 ⇒ 断言看似「守卫没抓到」
      //    实为**替身缺陷**。这条注释就是为了别再踩（本轮已踩过一次）。
      seeded[p.noteSectionId] = [...pushed, `已废弃-${p.noteSectionId}`]
    }
    state.previouslySyncedTables = seeded

    const payloads = buildG7SoeSyncPayloads(state)
    let checked = 0
    for (const p of payloads) {
      const pushed = new Set(Object.keys(p.subTableData).filter(k => !k.startsWith('_')))
      const removed = (p.subTableData._removed_table_keys as unknown as string[] | undefined) ?? []
      // 每个有表的章节都应恰好报出那一个废弃名
      if (pushed.size > 0) {
        expect(removed, `${p.noteSectionId} 应报出注入的废弃名`).toContain(
          `已废弃-${p.noteSectionId}`,
        )
        checked += 1
      }
      for (const r of removed) {
        expect(pushed.has(r), `${p.noteSectionId}: removed 键 ${r} 同时在本次推送里`).toBe(false)
      }
    }
    // 防空转：必须真的逐章节检查过（不是 payloads 为空导致的假绿）
    expect(checked, '参与差集校验的章节数').toBeGreaterThanOrEqual(11)
  })

  it('无录入区块的章节不进载荷 ⇒ 既不推表也不上报 removed（不越权删别人的表）', () => {
    const state = createG7SoeDisclosureState()
    // 纯文字披露章节（`tables` 为空）实测 3 个，它们不该出现在载荷里带表的那批中
    const withTables = G7_SOE_DISCLOSURE_SECTIONS.filter(s => (s.tables ?? []).length > 0)
    const withoutTables = G7_SOE_DISCLOSURE_SECTIONS.filter(s => (s.tables ?? []).length === 0)
    expect(withoutTables.length, '实测应有纯文字披露章节').toBe(3)

    // 即使给纯文字章节喂基线，也不能凭空产生一个只含 removed 的载荷去删表
    state.previouslySyncedTables = Object.fromEntries(
      withoutTables.map(s => [s.noteSectionId, ['别的底稿推的表']]),
    )
    const payloads = buildG7SoeSyncPayloads(state)
    for (const p of payloads) {
      const pushed = Object.keys(p.subTableData).filter(k => !k.startsWith('_'))
      const removed = (p.subTableData._removed_table_keys as unknown as string[] | undefined) ?? []
      if (pushed.length === 0) {
        expect(removed, `${p.noteSectionId} 无推送表却上报 removed ⇒ 越权删`).toEqual([])
      }
    }
    // 反面锚定：有表章节数与 38 张表的章节分布自洽
    expect(withTables.length).toBe(11)
  })

  it('markG7SoeSynced 把本次推送记为下次基线（连跑两轮后 removed 归零）', async () => {
    const { markG7SoeSynced } = await import('./g7SoeDisclosureModel')
    const state = createG7SoeDisclosureState()
    const payloads = buildG7SoeSyncPayloads(state)

    const next = markG7SoeSynced(state, payloads)
    // 🔴 只有**有录入区块**的章节记入基线；纯文字披露章节（只推 narratives）不建基线
    //    —— 与 `buildG7SoeSyncPayloads` 的差集门控必须同一判据，否则基线里凭空多出
    //    一批永不参与清理的章节键。
    const withTables = new Set(
      G7_SOE_DISCLOSURE_SECTIONS.filter(s => (s.tables ?? []).length > 0).map(s => s.noteSectionId),
    )
    let recorded = 0
    for (const p of payloads) {
      const pushed = Object.keys(p.subTableData).filter(k => !k.startsWith('_'))
      if (withTables.has(p.noteSectionId)) {
        expect(next[p.noteSectionId], `${p.noteSectionId} 未记入基线`).toEqual(pushed)
        recorded += 1
      } else {
        expect(
          next[p.noteSectionId],
          `${p.noteSectionId} 是纯文字章节，不该记入基线`,
        ).toBeUndefined()
      }
    }
    expect(recorded, '记入基线的章节数（防空转）').toBe(11)
    // 应用基线后再构建：无历史差异 ⇒ 不上报 removed
    state.previouslySyncedTables = next
    for (const p of buildG7SoeSyncPayloads(state)) {
      expect(p.subTableData._removed_table_keys).toBeUndefined()
    }
  })

  it('宿主三处接线齐全（回写基线 / 落库 / 载入恢复）—— 缺一即整条链空转', async () => {
    const { readFileSync, existsSync } = await import('node:fs')
    const { dirname, resolve } = await import('node:path')

    // 仓库根定位：双哨兵具体文件（禁写死回退级数）
    const SENTINELS = ['backend/data/note_template_soe.json', '.kiro/steering/memory.md']
    let dir = __dirname
    let root = ''
    for (let i = 0; i < 14; i += 1) {
      if (SENTINELS.every(s => existsSync(resolve(dir, s)))) {
        root = dir
        break
      }
      const parent = dirname(dir)
      if (parent === dir) break
      dir = parent
    }
    expect(root, '仓库根定位失败').not.toBe('')

    const host = readFileSync(
      resolve(
        root,
        'audit-platform/frontend/src/components/workpaper/g7-long-term-equity-main/disclosure/G7TabDisclosureSOE.vue',
      ),
      'utf-8',
    ).replace(/\r\n/g, '\n')

    // ① 同步成功后回写基线（必须在 api.post 之后，失败时不更新基线）
    expect(
      /state\.previouslySyncedTables\s*=\s*markG7SoeSynced\(/.test(host),
      '宿主未在同步成功后调用 markG7SoeSynced ⇒ 基线恒为 {} ⇒ 差集恒空',
    ).toBe(true)
    // ② 回写后必须落库（否则刷新即丢）
    const afterMark = host.slice(host.indexOf('markG7SoeSynced('))
    expect(
      /await persist\(\)/.test(afterMark.slice(0, 600)),
      'markG7SoeSynced 之后未 persist ⇒ 基线不落库',
    ).toBe(true)
    // ③ 载入时恢复（listed 有、改造前 soe 没有 ⇒ 每次打开都退回 {}）
    //
    // 🔴 判据必须匹配**条件表达式形态**，不能只查 `saved.previouslySyncedTables` 字样：
    //    该字样在恢复分支的赋值语句里也出现，把守卫门 `if (…)` 改成 `if (false)`
    //    后字样仍在 ⇒ 只查字样的守卫**仍然绿**（本轮变异检验已实测踩到这个 GREEN）。
    const restoreCond =
      /if\s*\(\s*saved\.previouslySyncedTables\s*&&\s*typeof\s+saved\.previouslySyncedTables\s*===\s*['"]object['"]\s*\)/
    expect(
      restoreCond.test(host),
      '宿主载入时未恢复 previouslySyncedTables（或恢复条件被改坏）⇒ 基线每次打开都归零',
    ).toBe(true)

    // 反向自检：三条判据都要能区分「有」与「被改坏」两种形态
    expect(/state\.previouslySyncedTables\s*=\s*markG7SoeSynced\(/.test('// nothing')).toBe(false)
    expect(restoreCond.test('// nothing')).toBe(false)
    expect(
      restoreCond.test('if (false) {\n  x = Object.entries(saved.previouslySyncedTables)\n}'),
      '判据被 `if (false)` 骗过 ⇒ 退化成 grep 式守卫',
    ).toBe(false)
    expect(
      restoreCond.test(
        "if (saved.previouslySyncedTables && typeof saved.previouslySyncedTables === 'object') {",
      ),
      '判据对正确形态应命中',
    ).toBe(true)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 同步失败提示的 fail-open 收口（2026-08-12 浏览器实测）
//
// 🔴 实测形态：点一次「同步到附注模块」，页面上同时出现
//      `已同步 128 行到 14 个附注章节（含合并范围变化与八、18）`
//      `同步附注失败，请检查国企附注章节映射后重试`
//    而 postgres 实况是 13 个章节全部写入、`八、18` 落 10 张子表 ⇒ 失败提示是**误报**。
//
// 根因：两个 Tab 的 `syncToDisclosureNotes()` 用**一个 try 包住整条链**
//   （persist → 构载荷 → api.post → 回写同步基线 → persist → 派发事件 → success）
//   + 裸 `catch {}` 一律报「同步失败，请检查附注章节映射」。于是 `api.post` 之后的
//   任何异常都被说成「同步失败」，且真实异常被吞掉、排查方向指向根本没问题的章节映射，
//   还诱使审计师重复写库。
//
// 收口：拆成 ①真同步 / ②成功后收尾 两段各自 try；②失败只说「已同步…；但基线回写失败」；
//   两段都 `console.error` 原始异常；提示带真实原因（`describeSyncError`）。
// ─────────────────────────────────────────────────────────────────────────────

import { readFileSync } from 'node:fs'
import { dirname, resolve as resolvePath } from 'node:path'
import { describeSyncError, describeSyncTailFailure } from './g7DisclosureSyncFeedback'

/** 本目录（两个 Tab 与本 spec 同目录），用相对定位避免依赖仓库根查找。 */
const DISCLOSURE_DIR = dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))

function readTab(name: 'G7TabDisclosureSOE.vue' | 'G7TabDisclosureListed.vue'): string {
  return readFileSync(resolvePath(DISCLOSURE_DIR, name), 'utf8')
}

/** 剥注释再做源码形态判据 —— 否则本次改造写下的解释性注释会把反面断言骗成假红。 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
}

/** 抽出 `syncToDisclosureNotes` 函数体（花括号配对，跳过参数列表）。 */
function syncBody(src: string): string {
  const at = src.indexOf('async function syncToDisclosureNotes')
  if (at < 0) return ''
  // 🔴 先跳过参数列表与返回类型注解再找函数体的 `{` ——
  //    直接找「第一个 {」会被 `(): Promise<void> {` 之前的任何 `{` 骗到。
  const bodyStart = src.indexOf('{', src.indexOf(')', at))
  let depth = 0
  for (let i = bodyStart; i < src.length; i += 1) {
    if (src[i] === '{') depth += 1
    else if (src[i] === '}') {
      depth -= 1
      if (depth === 0) return src.slice(bodyStart, i + 1)
    }
  }
  return ''
}

const TABS = ['G7TabDisclosureSOE.vue', 'G7TabDisclosureListed.vue'] as const

describe('G7 披露同步：失败提示不得 fail-open（两个 Tab 同款收口）', () => {
  it('两个 Tab 都不再用裸 catch 把整条链的异常说成「同步失败」', () => {
    for (const tab of TABS) {
      const body = syncBody(stripComments(readTab(tab)))
      expect(body, `${tab}: 未取到 syncToDisclosureNotes 函数体`).not.toBe('')
      // 裸 catch（无绑定变量）在本函数体内必须绝迹 —— 它是吞异常的形态本身
      expect(
        /catch\s*\{/.test(body),
        `${tab}: syncToDisclosureNotes 里仍有裸 catch {（吞掉真实异常）`,
      ).toBe(false)
      // 原来的误导性文案必须消失
      expect(
        /同步附注失败，请检查.*章节映射后重试/.test(body),
        `${tab}: 仍在用「请检查附注章节映射」这条与实况不符的提示`,
      ).toBe(false)
    }
  })

  it('两个 Tab 都把「真同步」与「成功后收尾」分成两段 try，且收尾失败不说「同步失败」', () => {
    for (const tab of TABS) {
      const body = syncBody(stripComments(readTab(tab)))
      // 至少两个 try（外层 finally 用的那个 + 内层真同步段）
      expect(
        (body.match(/\btry\s*\{/g) || []).length,
        `${tab}: try 段少于 3 个 ⇒ 未按「真同步 / 收尾」分段`,
      ).toBeGreaterThanOrEqual(3)
      // 两段都必须捕获到变量并打 console.error（不吞异常）
      expect(
        (body.match(/catch\s*\(\s*err\s*:\s*unknown\s*\)/g) || []).length,
        `${tab}: 未用 catch (err: unknown) 捕获（两段各一处）`,
      ).toBeGreaterThanOrEqual(2)
      expect(
        (body.match(/console\.error\(/g) || []).length,
        `${tab}: console.error 少于 2 处 ⇒ 有分支仍在静默吞异常`,
      ).toBeGreaterThanOrEqual(2)
      // 收尾失败走共享文案（不得自拟「同步失败」）
      expect(
        body.includes('describeSyncTailFailure('),
        `${tab}: 收尾失败未走 describeSyncTailFailure ⇒ 可能又把「已落地」说成失败`,
      ).toBe(true)
      expect(
        body.includes('describeSyncError('),
        `${tab}: 真同步失败未带真实原因（describeSyncError）`,
      ).toBe(true)
      // 真同步失败必须 return —— 否则会继续走收尾并弹出 success（正是实测的矛盾提示）
      expect(
        /console\.error\([^)]*\)\s*;?\s*ElMessage\.error\([^;]*\)\s*;?\s*return/.test(
          body.replace(/\s+/g, ' '),
        ),
        `${tab}: 真同步失败分支缺 return ⇒ 会继续执行收尾并弹 success（成功与失败提示并存）`,
      ).toBe(true)
    }
  })

  it('反向自检：把任一 Tab 改回裸 catch 形态 → 判据必打红', () => {
    const flatLike = `{
      try {
        await persist()
        const r = await api.post(url, body)
        ElMessage.success('已同步')
      } catch {
        ElMessage.warning('同步附注失败，请检查国企附注章节映射后重试')
      } finally { isSyncing.value = false }
    }`
    expect(/catch\s*\{/.test(flatLike)).toBe(true)
    expect(/同步附注失败，请检查.*章节映射后重试/.test(flatLike)).toBe(true)
    expect((flatLike.match(/\btry\s*\{/g) || []).length).toBeLessThan(3)
    // 正确形态必须命中（否则判据恒假）
    for (const tab of TABS) {
      const body = syncBody(stripComments(readTab(tab)))
      expect(/catch\s*\{/.test(body)).toBe(false)
      expect((body.match(/\btry\s*\{/g) || []).length).toBeGreaterThanOrEqual(3)
    }
  })

  it('describeSyncError 按优先级提炼原因，且**绝不返回空串**', () => {
    expect(describeSyncError({ response: { data: { detail: '章节 八、18 不存在' } } }))
      .toBe('章节 八、18 不存在')
    expect(describeSyncError({ response: { data: { message: '后端信封 message' } } }))
      .toBe('后端信封 message')
    expect(describeSyncError({ response: { status: 500 } })).toBe('HTTP 500')
    expect(describeSyncError(new Error('Network Error'))).toBe('Network Error')
    // 空/无信息形态一律给可读兜底（空串会拼出「同步附注失败：」断尾提示）
    for (const empty of [undefined, null, {}, { response: {} }, { message: '   ' }]) {
      expect(describeSyncError(empty)).toBe('未知错误（详见浏览器控制台）')
    }
    // detail 优先于 status（后端给了具体原因就别只报状态码）
    expect(describeSyncError({ response: { status: 400, data: { detail: '载荷缺 section_id' } } }))
      .toBe('载荷缺 section_id')
  })

  it('describeSyncTailFailure 必须原样带上成功文案并明说「无需重试」', () => {
    const ok = '已同步 128 行到 14 个附注章节'
    const text = describeSyncTailFailure(ok, { response: { status: 409 } })
    expect(text.startsWith(ok)).toBe(true)
    expect(text).toContain('HTTP 409')
    expect(text).toContain('无需重试')
    // 不得出现「同步失败」字样 —— 那正是误导审计师重复写库的根源
    expect(text.includes('同步附注失败')).toBe(false)
  })
})
