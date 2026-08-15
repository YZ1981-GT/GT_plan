import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { buildI4ListedSyncPayloads, buildI4SoeSyncPayloads } from '../i4DisclosureSyncPayload'
import { buildI5ListedSyncPayloads, buildI5SoeSyncPayloads } from '../i5DisclosureSyncPayload'
import { buildI6ListedSyncPayloads, buildI6SoeSyncPayloads } from '../i6DisclosureSyncPayload'
import { buildI1ListedColumns, buildI1ListedSyncPayloads } from '../i1DisclosureSyncPayload'
import { buildI2ListedSyncPayloads, buildI2SoeSyncPayloads } from '../i2DisclosureSyncPayload'
import { buildI3ListedSyncPayloads, buildI3SoeSyncPayloads } from '../i3DisclosureSyncPayload'
import { I4_LISTED_SUBTABLE, I4_SOE_SUBTABLE } from '../i4NoteSectionMap'
import { I5_LISTED_SUBTABLE, I5_SOE_SUBTABLE } from '../i5NoteSectionMap'
import { I6_LISTED_SUBTABLE, I6_SOE_SUBTABLE } from '../i6NoteSectionMap'
import { I1_LISTED_SUBTABLE } from '../i1NoteSectionMap'
import {
  I1_LISTED_DEFAULT_CATEGORIES,
  I1_LISTED_MOVEMENT_ROWS,
} from '../i1ListedDisclosureModel'
import { I1_STANDARD_TO_LEGACY } from '../i1CategoryScope'
import { I2_LISTED_SUBTABLE, I2_SOE_SUBTABLE } from '../i2NoteSectionMap'
import { I3_LISTED_SUBTABLE, I3_SOE_SUBTABLE } from '../i3NoteSectionMap'

// disclosure-table-sync-convergence：I4/I5/I6 披露同步载荷携带源对齐列头
describe('I 循环披露 _columns 覆盖', () => {
  it('I4 长期待摊费用 listed/soe 附带源对齐变动表列头', () => {
    const [listed] = buildI4ListedSyncPayloads('wp-i4', null, { rows: [] })
    const lc = listed.columns![I4_LISTED_SUBTABLE.movement]
    expect(lc[0].is_label).toBe(true)
    expect(lc.map((c) => c.label)).toEqual(['项  目', '期初数', '本期增加', '本期摊销', '其他减少', '期末数'])
    expect(lc[3].group).toBe('本期减少')
    expect(lc[4].group).toBe('本期减少')

    const [soe] = buildI4SoeSyncPayloads('wp-i4', null, { rows: [] })
    const sc = soe.columns![I4_SOE_SUBTABLE.movement]
    expect(sc.map((c) => c.label)).toEqual([
      '项  目', '期初余额', '本期增加额', '本期摊销额', '其他减少额', '期末余额', '其他减少的原因',
    ])
    expect(sc.every((c) => c.flat)).toBe(true)
  })

  it('I5 其他非流动资产 listed=两级 7 列，soe=期末/年初 flat', () => {
    const [listed] = buildI5ListedSyncPayloads('wp-i5', null, { rows: [] })
    expect(listed.columns![I5_LISTED_SUBTABLE.main].map((c) => c.label)).toEqual([
      '项  目', '账面余额', '减值准备', '账面价值', '账面余额', '减值准备', '账面价值',
    ])
    expect(listed.columns![I5_LISTED_SUBTABLE.main][1].group).toBe('期末数')
    expect(listed.columns![I5_LISTED_SUBTABLE.main][4].group).toBe('上年年末数')

    const [soe] = buildI5SoeSyncPayloads('wp-i5', null, { rows: [] })
    expect(soe.columns![I5_SOE_SUBTABLE.main].map((c) => c.label)).toEqual([
      '项  目', '期末余额', '年初余额',
    ])
    expect(soe.columns![I5_SOE_SUBTABLE.main].every((c) => c.flat)).toBe(true)
  })

  it('I6 研发费用按性质表 listed/soe 同构（项目/本期发生额/上期发生额）', () => {
    const [listed] = buildI6ListedSyncPayloads('wp-i6', null, { rows: [] })
    expect(listed.columns![I6_LISTED_SUBTABLE.expenseByNature].map((c) => c.label)).toEqual([
      '项目', '本期发生额', '上期发生额',
    ])
    const [soe] = buildI6SoeSyncPayloads('wp-i6', null, { rows: [] })
    expect(soe.columns![I6_SOE_SUBTABLE.expenseByNature][0].is_label).toBe(true)
    expect(soe.columns![I6_SOE_SUBTABLE.expenseByNature].map((c) => c.label)).toEqual([
      '项目', '本期发生额', '上期发生额',
    ])
  })

  it('I1 无形资产 listed 变动表列头随类别动态（项目 + 类别 + 合计）', () => {
    const cols = buildI1ListedColumns({
      categories: [{ key: 'patent', label: '专利权' }, { key: 'software', label: '软件' }],
    } as any)
    const mv = cols[I1_LISTED_SUBTABLE.movement]
    expect(mv[0].is_label).toBe(true)
    expect(mv.map((c) => c.label)).toEqual(['项目', '专利权', '软件', '合计'])
    // 附属子表源对齐
    expect(cols['本期摊销费用归属'].map((c) => c.label)).toEqual([
      '项目', '生产成本', '制造费用', '销售费用', '管理费用', '研发费用', '其他', '合计',
    ])
  })

  // Task 12 / Property 20：类别列 key 稳定 `{slot}_{seq}`，禁用中文 label 作 key（会撞键）
  it('I1 listed 类别列 key = 稳定 {key}_{seq}，非中文 label', () => {
    const cols = buildI1ListedColumns({
      categories: [{ key: 'patent', label: '专利权' }, { key: 'software', label: '软件' }],
    } as any)
    const mv = cols[I1_LISTED_SUBTABLE.movement]
    // 类别列（去掉首列 label 与末列合计）
    const catKeys = mv.slice(1, -1).map((c) => c.key)
    expect(catKeys).toEqual(['patent_1', 'software_2'])
    // 任何类别列 key 不得等于其中文 label（防回退到 label 作 key）
    for (const c of mv.slice(1, -1)) {
      expect(c.key).not.toBe(c.label)
      expect(c.key).toMatch(/^[a-z0-9_]+_\d+$/)
    }
  })

  // Task 12：列 key 必须逐字等于 sub_table_data 行字段名（投影器 r.get(col.key) 对齐前提）
  it('I1 listed 列 key ≡ 行字段名（防投影器取空整表空白）', () => {
    const state = {
      categories: [
        { key: 'land', label: '土地使用权' },
        { key: 'patent', label: '专利权' },
        { key: 'other', label: '其他' },
      ],
      movement: { land: { cost_begin: 100 }, patent: { cost_begin: 50 } },
    } as any
    const [payload] = buildI1ListedSyncPayloads('wp-i1', null, state)
    const colKeys = payload.columns![I1_LISTED_SUBTABLE.movement].map((c) => c.key)
    const rows = payload.sub_table_data[I1_LISTED_SUBTABLE.movement] as Record<string, unknown>[]
    // 每个数据行（非 section）的字段键集合必须 ⊇ 列 key 集合（label/合计 亦在两侧）
    const dataRow = rows.find((r) => !r.is_section && r.label === '1.期初余额')!
    for (const k of colKeys) {
      expect(k in dataRow).toBe(true)
    }
    // 稳定 key 形态：土地使用权 → land_1（不是「土地使用权」）
    expect(colKeys).toContain('land_1')
    expect(colKeys).toContain('patent_2')
    expect(colKeys).not.toContain('土地使用权')
  })

  it('I2 开发支出 listed/soe 变动表列头两级 group', () => {
    const [listed] = buildI2ListedSyncPayloads('wp-i2', null, {
      natureRows: [], movementRows: [], importantRows: [], impairmentRows: [],
      noteText: '', noteCap: '', noteImpairTest: '', notePurchased: '',
    })
    // Task 14：研发支出表源模板是两级表头（B7:C7「本期发生额」/ D7:E7「上期发生额」，
    // 各含「费用化金额」「资本化金额」）⇒ 必须 group 形态。
    // 🔴 此前基线锁的是被压扁的 flat + 改写 label（'本期费用化'…），属「把错值当基线」：
    //    任一列 flat=True 会让 _extract_column_groups 整表返 []，push 路径两级表头静默压扁。
    const nature = listed.columns![I2_LISTED_SUBTABLE.nature]
    expect(nature.map((c) => c.label)).toEqual([
      '项  目', '费用化金额', '资本化金额', '费用化金额', '资本化金额',
    ])
    expect(nature.map((c) => c.group)).toEqual([
      undefined, '本期发生额', '本期发生额', '上期发生额', '上期发生额',
    ])
    // 禁止任何列带 flat（否则整表分组被丢弃）
    expect(nature.some((c) => c.flat), '研发支出表是两级表头，不得声明 flat').toBe(false)

    expect(listed.columns![I2_LISTED_SUBTABLE.movement].map((c) => c.label)).toEqual([
      '项  目', '期初数', '内部开发支出', '其他增加',
      '确认为无形资产', '计入当期损益', '期末数',
      '资本化开始时点', '资本化依据', '研发进度',
    ])
    expect(listed.columns![I2_LISTED_SUBTABLE.movement][2].group).toBe('本期增加')
    expect(listed.columns![I2_LISTED_SUBTABLE.movement][4].group).toBe('本期减少')

    const [soe] = buildI2SoeSyncPayloads('wp-i2', null, { movementRows: [], noteText: '' })
    expect(soe.columns![I2_SOE_SUBTABLE.movement].map((c) => c.label)).toContain('其他减少')
    expect(soe.columns![I2_SOE_SUBTABLE.movement][2].group).toBe('本期增加')
    expect(soe.columns![I2_SOE_SUBTABLE.movement][4].group).toBe('本期减少')
  })

  it('I3 商誉 listed 两级表头（本期增加/本期减少含子列）+ soe flat 5 列', () => {
    const [listed] = buildI3ListedSyncPayloads('wp-i3', null, {
      bookValueRows: [], impairmentRows: [],
    })
    const bv = listed.columns![I3_LISTED_SUBTABLE.bookValue]
    expect(bv[0].label).toBe('被投资单位名称或形成商誉的事项')
    expect(bv.map((c) => c.label)).toEqual([
      '被投资单位名称或形成商誉的事项', '期初余额',
      '企业合并形成', '取得构成业务的共同经营的利益份额形成', '其他',
      '处置', '其他',
      '期末余额',
    ])
    expect(bv[2].group).toBe('本期增加')
    expect(bv[5].group).toBe('本期减少')

    // 减值表 7 列两级
    const imp = listed.columns![I3_LISTED_SUBTABLE.impairment]
    expect(imp.length).toBe(7)
    expect(imp[2].group).toBe('本期增加')
    expect(imp[4].group).toBe('本期减少')

    // 假设参数表（动态结构，不标 flat/group — 模板侧 headers[0] 为示例数据）
    expect(listed.columns![I3_LISTED_SUBTABLE.assumptions].map((c) => c.label)).toEqual([
      '资产组/业务', '毛利率', '增长率', '折现率',
    ])

    // SOE flat 5 列
    const [soe] = buildI3SoeSyncPayloads('wp-i3', null, { bookValueRows: [], impairmentRows: [] })
    expect(soe.columns![I3_SOE_SUBTABLE.impairment][0].label).toBe('被投资单位名称或形成商誉的事项')
    expect(soe.columns![I3_SOE_SUBTABLE.bookValue].every((c) => c.flat)).toBe(true)
    expect(soe.columns![I3_SOE_SUBTABLE.bookValue].length).toBe(5)
  })
})

// ═══════════════════════════════════════════════════════════════════
// Task 18 / Property 30：I 循环金额控件与展示格式收口
// ═══════════════════════════════════════════════════════════════════

describe('Property 30 — I 循环金额控件与只读金额格式单一真源', () => {
  const REPO = (() => {
    let dir = __dirname
    for (let i = 0; i < 12; i += 1) {
      if (existsSync(join(dir, 'backend')) && existsSync(join(dir, 'audit-platform'))) return dir
      dir = dirname(dir)
    }
    throw new Error('未找到仓库根')
  })()
  const WP = join(REPO, 'audit-platform', 'frontend', 'src', 'components', 'workpaper')

  function walkVue(dir: string, out: string[] = []): string[] {
    let entries: string[]
    try {
      entries = readdirSync(dir)
    } catch {
      return out
    }
    for (const name of entries) {
      const p = join(dir, name)
      if (statSync(p).isDirectory()) walkVue(p, out)
      else if (name.endsWith('.vue')) out.push(p)
    }
    return out
  }

  const I_SFCS = [1, 2, 3, 4, 5, 6].flatMap((n) => walkVue(join(WP, `i${n}`)))

  function sfcParts(p: string): { tpl: string; scr: string } {
    const raw = readFileSync(p, 'utf-8')
    const t = raw.match(/<template>([\s\S]*)<\/template>/)
    const s = raw.match(/<script[^>]*>([\s\S]*?)<\/script>/)
    const strip = (x: string) =>
      x.replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/(?<![:'"\w])\/\/[^\n]*/g, '')
    return { tpl: strip(t ? t[1] : ''), scr: strip(s ? s[1] : '') }
  }

  it('反向自检：扫到足量 I 循环 SFC（扫不到 = 判据空转）', () => {
    expect(I_SFCS.length, `只扫到 ${I_SFCS.length} 个 ⇒ 目录结构变了`).toBeGreaterThanOrEqual(70)
  })

  it('🔴 禁用 el-input-number :formatter —— EP 2.13.6 无此 prop，千分符从未生效', () => {
    const bad: string[] = []
    for (const p of I_SFCS) {
      const { tpl } = sfcParts(p)
      for (const m of tpl.matchAll(/<el-input-number\b([\s\S]{0,900}?)\/?>/g)) {
        if (/:?formatter\s*=/.test(m[1])) bad.push(p.split(/[\\/]/).pop()!)
      }
    }
    expect(
      [...new Set(bad)],
      '`:formatter` 是空操作（浏览器实测无千分符）—— 可编辑金额请换 WpAmountInput',
    ).toEqual([])
  })

  it('🔴 只读金额一律走 displayPrefs.fmtAmount（禁本地 toLocaleString 造第二套格式）', () => {
    const bad: string[] = []
    for (const p of I_SFCS) {
      const { scr } = sfcParts(p)
      // 只看名为 fmtAmount / fmtAmt 的本地实现：不得自己 toLocaleString
      const m = scr.match(/function\s+fmtAmoun?t?\w*\s*\([^)]*\)[^{]*\{([\s\S]{0,400}?)\n\}/)
      if (m && /toLocaleString/.test(m[1])) bad.push(p.split(/[\\/]/).pop()!)
    }
    expect(
      bad,
      '本地 toLocaleString 硬编码「2 位小数 + 千分符」，取不到用户的单位（元/万元）'
        + '与 showZero 偏好，且各文件零值返 `-`/`—` 不一致',
    ).toEqual([])
  })

  it('用了 displayPrefs 的 SFC 必须 setup 顶层 inject ?? store（写进函数体静默失效）', () => {
    const bad: string[] = []
    for (const p of I_SFCS) {
      const { scr } = sfcParts(p)
      if (!scr.includes('displayPrefs.fmtAmount')) continue
      if (!scr.includes('inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()')) {
        bad.push(`${p.split(/[\\/]/).pop()}: 缺 inject ?? store 范式`)
      }
    }
    expect(bad).toEqual([])
  })

  it('🔴 DisplayPrefs_Key 只能从 composables/displayPrefsKey 引入（从 store 引会让整页崩）', () => {
    const bad: string[] = []
    for (const p of I_SFCS) {
      const { scr } = sfcParts(p)
      if (!scr.includes('DisplayPrefs_Key')) continue
      for (const m of scr.matchAll(/import\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/g)) {
        if (/\bDisplayPrefs_Key\b/.test(m[1]) && !m[2].includes('displayPrefsKey')) {
          bad.push(`${p.split(/[\\/]/).pop()}: from ${m[2]}`)
        }
      }
    }
    expect(bad, 'stores/displayPrefs 没有 DisplayPrefs_Key 导出 ⇒ 浏览器白屏').toEqual([])
  })

  it('反向自检：确有若干 SFC 真的用了 displayPrefs.fmtAmount（否则上两条在空转）', () => {
    const users = I_SFCS.filter((p) => sfcParts(p).scr.includes('displayPrefs.fmtAmount'))
    expect(users.length, '零个消费方 ⇒ 收敛没落地或判据写错').toBeGreaterThanOrEqual(20)
  })

  it('反向边界：比率/年限/月份/占比等非金额列不得用 WpAmountInput', () => {
    const NON_AMOUNT = ['比率', '利率', '汇率', '占比', '年限', '月份', '笔数', '折现率', '增长率', '毛利率']
    const bad: string[] = []
    for (const p of I_SFCS) {
      const { tpl } = sfcParts(p)
      for (const m of tpl.matchAll(/<WpAmountInput\b[^>]*>/g)) {
        const hit = NON_AMOUNT.filter((k) => m[0].includes(k))
        if (hit.length) bad.push(`${p.split(/[\\/]/).pop()}: ${hit}`)
      }
    }
    expect(bad, '非金额列应保持 el-input-number（金额语义控件不适用于比率/期限）').toEqual([])
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 44 / 45：I1 上市披露主表的**行骨架**与**类别默认值**必须锁到真源
//
// 🔴🔴 补这两条的实证依据（2026-08-15）：本文件既有判据都是拿**合成 categories**
// 调 `buildI1ListedColumns({ categories: [{key:'patent',...}] })` 测函数行为，
// **从不断言生产默认值**。于是两处真错长期全绿：
//
//   ① `I1_LISTED_MOVEMENT_ROWS` 的减值准备减少段丢了「（2）失效且终止确认的部分」、
//      末尾凭空多一个 `……` 扩位 ⇒ 源模板 3 处扩位被实现成 4 处，
//      第 33 行披露标签渲染成「（2）其他减少」（源模板是「（3）其他减少」）。
//   ② `I1_LISTED_DEFAULT_CATEGORIES` 是**第二份类别真源**且 3 个 label 与源模板不符
//      （`房屋使用权`/`特许权`/`探矿权/采矿权` vs 源 `住房使用权`/`特许经营权`/`矿产权`）。
//      label 直接进 `buildI1ListedColumns` 的列头 ⇒ 推给附注的列头与模板不同构。
//
// 期望值一律取自**真源**（附注模板 JSON / 后端 `i1_asset_categories.py`），
// 不在本文件抄第二份字面量 —— 抄一份就等于把当时的值当基线锁死。
// ═══════════════════════════════════════════════════════════════════════════════

function findRepoRootForI1(start: string): string {
  let cur = start
  for (let i = 0; i < 12; i++) {
    if (existsSync(join(cur, 'backend')) && existsSync(join(cur, 'audit-platform'))) return cur
    const parent = dirname(cur)
    if (parent === cur) break
    cur = parent
  }
  throw new Error('找不到仓库根（缺 backend/ + audit-platform/ 双哨兵）')
}
const I1_REPO_ROOT = findRepoRootForI1(__dirname)

/** 去掉全部空白（源模板与模板 JSON 的行标签缩进不一致） */
const i1Norm = (s: unknown) => String(s ?? '').replace(/\s+/g, '')

/** 附注模板「五、26 / 无形资产情况」（seed 侧真源，由 fix_note_i_cycle_structure.py 对齐源 xlsx） */
function noteListedIntangibleTable(): { rows: Array<Record<string, unknown>> } {
  const raw = readFileSync(join(I1_REPO_ROOT, 'backend/data/note_template_listed.json'), 'utf-8')
  const doc = JSON.parse(raw) as { sections: Array<Record<string, any>> }
  const sec = doc.sections.find((s) => String(s.section_number) === '五、26')
  expect(sec, '附注模板缺章节「五、26」⇒ 判据锚点失效').toBeTruthy()
  const tbl = (sec!.tables as Array<Record<string, any>>).find((t) => t.name === '无形资产情况')
  expect(tbl, '「五、26」缺表「无形资产情况」⇒ 判据锚点失效').toBeTruthy()
  return tbl as { rows: Array<Record<string, unknown>> }
}

/** 后端类别真源 `i1_asset_categories.I1_ASSET_CATEGORIES`：按 seq 返回 `(key, label)` */
function beI1Categories(): Array<{ key: string; label: string; seq: number }> {
  const src = readFileSync(
    join(I1_REPO_ROOT, 'backend/app/services/four_table/i1_asset_categories.py'),
    'utf-8',
  )
  const anchor = 'I1_ASSET_CATEGORIES'
  const at = src.indexOf(anchor + ':')
  expect(at, `后端锚点 ${anchor} 未命中 ⇒ 守卫失效（可能已改名）`).toBeGreaterThan(-1)
  // 先跳过类型注解再找赋值号后的 `(`/`[`（类型注解里的括号会骗到第一个开括号）
  const eq = src.indexOf('=', at)
  const open = src.search(new RegExp('[\\(\\[]', 'g')) // placeholder，下面重新算
  void open
  let start = -1
  for (let i = eq; i < src.length; i++) {
    if (src[i] === '(' || src[i] === '[') { start = i; break }
  }
  expect(start, '未找到 I1_ASSET_CATEGORIES 的开括号').toBeGreaterThan(-1)
  const openCh = src[start]
  const closeCh = openCh === '(' ? ')' : ']'
  let depth = 0
  let end = -1
  for (let i = start; i < src.length; i++) {
    if (src[i] === openCh) depth++
    else if (src[i] === closeCh) {
      depth--
      if (depth === 0) { end = i; break }
    }
  }
  expect(end, '括号未配对 ⇒ 守卫解析失败').toBeGreaterThan(-1)
  const body = src.slice(start, end + 1)

  // 🔴 `key=` 有两种形态：字面量 `key="software"` 与常量引用 `key=CATEGORY_OTHER`。
  // 只认字面量会静默漏掉「其他」（首版就漏了，被反向自检「应为 11 个」打红）。
  // 故先把模块级字符串常量收成表，用于解析标识符形态。
  const consts = new Map<string, string>()
  for (const m of src.matchAll(/^([A-Z_][A-Z0-9_]*)\s*(?::[^=\n]+)?=\s*"([^"]*)"/gm)) {
    consts.set(m[1], m[2])
  }

  const out: Array<{ key: string; label: string; seq: number }> = []
  // 逐个 `I1Category(` 用**圆括号配对**截块（不用固定缩进/字符窗口）
  for (let i = 0; i < body.length; ) {
    const at = body.indexOf('I1Category(', i)
    if (at < 0) break
    const bOpen = at + 'I1Category('.length - 1
    let d = 0
    let bEnd = -1
    for (let j = bOpen; j < body.length; j++) {
      if (body[j] === '(') d++
      else if (body[j] === ')') {
        d--
        if (d === 0) { bEnd = j; break }
      }
    }
    expect(bEnd, 'I1Category(...) 括号未配对 ⇒ 抽取器失效').toBeGreaterThan(-1)
    const blk = body.slice(bOpen + 1, bEnd)
    const rawKey = /key=\s*(?:"([^"]+)"|([A-Za-z_][A-Za-z0-9_]*))/.exec(blk)
    const key = rawKey?.[1] ?? (rawKey?.[2] ? consts.get(rawKey[2]) : undefined)
    const label = /label=\s*"([^"]+)"/.exec(blk)?.[1]
    const seq = /seq=\s*(\d+)/.exec(blk)?.[1]
    expect(
      key && label && seq,
      `I1Category 块解析失败（key/label/seq 缺一）⇒ 抽取器失效：${blk.slice(0, 80)}`,
    ).toBeTruthy()
    out.push({ key: key!, label: label!, seq: Number(seq) })
    i = bEnd + 1
  }
  expect(out.length, '后端类别块解析结果为空 ⇒ 抽取器失效（不是「后端没有类别」）')
    .toBeGreaterThan(0)
  const seqs = out.map((c) => c.seq).sort((a, b) => a - b)
  expect(seqs, 'seq 必须是 1..N 连续无空洞（否则抽取器漏块了）').toEqual(
    Array.from({ length: out.length }, (_, i) => i + 1),
  )
  return out.sort((a, b) => a.seq - b.seq)
}

describe('Property 44：I1 上市变动行骨架锁到附注模板（= 源 xlsx A11:A48）', () => {
  it('I1_LISTED_MOVEMENT_ROWS 的 label 序列逐行等于模板 rows', () => {
    const tmpl = noteListedIntangibleTable()
    const want = tmpl.rows.map((r) => i1Norm(r.label))
    const got = I1_LISTED_MOVEMENT_ROWS.map((r) => i1Norm(r.label))
    expect(got.length, '前端行数与附注模板行数不一致 ⇒ 推送必产出错位行').toBe(want.length)
    const bad = want
      .map((w, i) => (w === got[i] ? null : `第 ${i} 行：前端「${got[i]}」≠ 模板「${w}」`))
      .filter(Boolean)
    expect(bad, '前端行标签与附注模板不符（label 是附注行的匹配键）').toEqual([])
  })

  it('`kind === "ellipsis"` 的行数等于模板 expandable 行数（源模板 3 处扩位）', () => {
    const tmpl = noteListedIntangibleTable()
    const wantN = tmpl.rows.filter((r) => String(r.row_type ?? '') === 'expandable').length
    const gotN = I1_LISTED_MOVEMENT_ROWS.filter((r) => r.kind === 'ellipsis').length
    expect(wantN, '模板 expandable 数为 0 ⇒ 判据在空转（应为源模板的 3 处）').toBe(3)
    expect(gotN, '前端扩位数 ≠ 模板扩位数 ⇒ 要么凭空多了扩位、要么真实扩位被抹掉').toBe(wantN)
  })

  it('三层减少段结构一致：处置 / 失效且终止确认的部分 / 其他减少，且其后直接是期末余额', () => {
    const labels = I1_LISTED_MOVEMENT_ROWS.map((r) => i1Norm(r.label))
    const starts = labels.map((l, i) => (l === '3.本期减少金额' ? i : -1)).filter((i) => i >= 0)
    expect(starts.length, '应有三层「3.本期减少金额」').toBe(3)
    for (const at of starts) {
      expect(labels.slice(at + 1, at + 4)).toEqual([
        '（1）处置', '（2）失效且终止确认的部分', '（3）其他减少',
      ])
      expect(labels[at + 4], '减少段后应直接是「4.期末余额」（无扩位）').toBe('4.期末余额')
    }
  })

  it('小计行 sumOf 必须覆盖其后全部明细行（防漏加新增的明细）', () => {
    const byKey = new Map(I1_LISTED_MOVEMENT_ROWS.map((r) => [r.key, r]))
    for (const row of I1_LISTED_MOVEMENT_ROWS) {
      if (row.kind !== 'subtotal') continue
      const at = I1_LISTED_MOVEMENT_ROWS.indexOf(row)
      const children: string[] = []
      for (let i = at + 1; i < I1_LISTED_MOVEMENT_ROWS.length; i++) {
        const r = I1_LISTED_MOVEMENT_ROWS[i]
        if (r.indent <= row.indent) break
        children.push(r.key)
      }
      expect(row.sumOf ?? [], `小计行 ${row.key} 的 sumOf 与其下明细不一致`).toEqual(children)
      for (const k of row.sumOf ?? []) {
        expect(byKey.has(k), `小计行 ${row.key} 引用了不存在的行 ${k}`).toBe(true)
      }
    }
  })
})

describe('Property 45：I1 上市类别默认值锁到后端类别真源（消除第二份类别声明）', () => {
  it('label 序列逐字等于后端 i1_asset_categories 按 seq 的 label', () => {
    const be = beI1Categories()
    expect(I1_LISTED_DEFAULT_CATEGORIES.map((c) => c.label)).toEqual(be.map((c) => c.label))
  })

  it('key 序列等于后端标准 key 经 I1_STANDARD_TO_LEGACY 的映射（历史短 key 不得改）', () => {
    const be = beI1Categories()
    expect(I1_LISTED_DEFAULT_CATEGORIES.map((c) => c.key)).toEqual(
      be.map((c) => I1_STANDARD_TO_LEGACY[c.key] ?? c.key),
    )
  })

  it('i1ListedDisclosureModel.ts 内不得再出现类别 label 字面量（防又抄一份）', () => {
    const src = readFileSync(
      join(
        I1_REPO_ROOT,
        'audit-platform/frontend/src/components/workpaper/composables/i1ListedDisclosureModel.ts',
      ),
      'utf-8',
    )
    // 只看代码区：剥掉块注释与行注释（注释里为解释历史错值会提到这些词）
    const code = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
    const offenders = beI1Categories()
      .map((c) => c.label)
      .filter((label) => code.includes(`'${label}'`) || code.includes(`"${label}"`))
    expect(offenders, '类别 label 只能由 i1CategoryScope 派生，本文件不得写死').toEqual([])
  })

  it('反向自检：抽取器真的读到了 11 个类别且含本轮修正的三个 label', () => {
    const be = beI1Categories()
    expect(be.length, '后端类别数应为 11（底稿目录!A9:A19）').toBe(11)
    expect(be.map((c) => c.label)).toContain('住房使用权')
    expect(be.map((c) => c.label)).toContain('特许经营权')
    expect(be.map((c) => c.label)).toContain('矿产权')
    // 旧错 label 必须已不存在于真源（否则本组判据会把错值当期望）
    for (const wrong of ['房屋使用权', '特许权', '探矿权/采矿权']) {
      expect(be.map((c) => c.label)).not.toContain(wrong)
    }
  })

  it('列头 label 由类别默认值驱动：buildI1ListedColumns 产出与真源同序同名', () => {
    const be = beI1Categories()
    const cols = buildI1ListedColumns({
      categories: I1_LISTED_DEFAULT_CATEGORIES.map((c) => ({ key: c.key, label: c.label })),
      cells: {},
    } as never)
    const movement = cols[I1_LISTED_SUBTABLE.movement]
    expect(movement[0].is_label).toBe(true)
    expect(movement.slice(1, -1).map((c) => c.label)).toEqual(be.map((c) => c.label))
    expect(movement[movement.length - 1].label).toBe('合计')
  })
})
