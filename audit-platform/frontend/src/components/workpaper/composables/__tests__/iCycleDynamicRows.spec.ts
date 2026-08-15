/**
 * I 循环动态可扩类别行守卫（Task 13, Property 21/22/23）
 *
 * 源模板动态标记数（`test_note_i_cycle_structure._SRC_DYNAMIC_MARK_COUNT` openpyxl 实测冻结）：
 * I1 上市 3 / I1 国企 4 / I2 上市 2 / I2 国企 1 / I5 两版各 1；I3/I4/I6 各 0。
 *
 * 本守卫覆盖：
 *  - Property 21：I1 国企四层可扩类别（Task 13 真缺口）—— 新增/删除在四层同步
 *  - Property 22：撞名拒绝（默认类别 + 已有自定义类别）
 *  - Property 23：自定义 key 单调**不复用已删序号**（持久化计数器 seqFloor）
 *  - Property 20：I1 上市列转置类别列稳定 key `{slot.key}_{seq}`（Task 12 已接线）
 *
 * Spec: i-cycle-extraction-formula-and-disclosure-closure Task 12/13
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import {
  createDefaultI1SoeLayers,
  resolveI1SoeCategories,
  nextI1SoeCustomKey,
  maxI1SoeCustomSeq,
  addI1SoeCategory,
  removeI1SoeCategory,
  i1SoeCategoryLabel,
  flattenI1SoeMovement,
  recomputeI1SoeDerivedLayers,
  I1_SOE_CATEGORIES,
} from '../i1SoeDisclosureModel'
import {
  I1_DEFAULT_CATEGORIES,
  addI1Category,
  removeI1Category,
  renameI1Category,
  i1CategoryColumnKey,
} from '../i1CategoryScope'
import {
  I2_NATURE_DEFAULT_NAMES,
  addI2NatureRow,
  removeI2NatureRow,
  isI2NatureDefaultRow,
  defaultNatureRows,
} from '../i2DisclosureModel'
import { buildI2ListedNatureSubTable, buildI2ListedSyncPayloads } from '../i2DisclosureSyncPayload'
import { I2_LISTED_SUBTABLE } from '../i2NoteSectionMap'

/** 四层键（与 I1_SOE_LAYER_META 同序） */
const LAYERS = ['cost', 'amort', 'impair', 'carrying'] as const

// ═══════════════════════════════════════════════════════════════════
// Property 21：I1 国企四层可扩类别
// ═══════════════════════════════════════════════════════════════════

describe('Property 21 — I1 国企动态可扩类别（四层同步）', () => {
  it('默认类别 = 源模板固定 12 类，且四层齐备', () => {
    const layers = createDefaultI1SoeLayers()
    expect(layers.map((l) => l.layer)).toEqual([...LAYERS])
    const cats = resolveI1SoeCategories(layers)
    expect(cats).toHaveLength(I1_SOE_CATEGORIES.length)
    expect(cats).toHaveLength(12)
    // 默认类别全部不带 soe_custom_ 前缀（稳定常量键）
    expect(cats.every((c) => !/^soe_custom_/.test(c.key))).toBe(true)
    // other 不可删，其余可删
    expect(cats.find((c) => c.key === 'other')!.removable).toBe(false)
  })

  it('新增自定义类别 → 四层（原价/累计摊销/减值/账面价值）同时出现', () => {
    const layers = createDefaultI1SoeLayers()
    const res = addI1SoeCategory(layers, '碳排放权')
    expect(res).not.toBeNull()
    expect(res!.key).toBe('soe_custom_1')
    expect(res!.seq).toBe(1)

    // 🔴 四层每层都必须多出该类别 —— 只加一层会让账面价值层算不出该类别
    for (const block of res!.layers) {
      const found = block.categories.find((c) => c.key === 'soe_custom_1')
      expect(found, `层 ${block.layer} 缺自定义类别`).toBeTruthy()
      expect(found!.label).toBe('碳排放权')
    }
    expect(res!.layers).toHaveLength(4)

    // 派生类别序列把它排在默认 12 类之后
    const cats = resolveI1SoeCategories(res!.layers)
    expect(cats).toHaveLength(13)
    expect(cats[12]).toMatchObject({ key: 'soe_custom_1', label: '碳排放权', removable: true })
  })

  it('自定义类别进入 flatten（推附注）与账面价值联动', () => {
    let layers = createDefaultI1SoeLayers()
    layers = addI1SoeCategory(layers, '碳排放权')!.layers
    // 原价 100 / 摊销 30 / 减值 10 → 账面价值 60
    const setCell = (layer: string, field: 'begin', v: number) => {
      layers = layers.map((b) =>
        b.layer !== layer
          ? b
          : { ...b, categories: b.categories.map((c) => (c.key === 'soe_custom_1' ? { ...c, [field]: v } : c)) },
      )
    }
    setCell('cost', 'begin', 100)
    setCell('amort', 'begin', 30)
    setCell('impair', 'begin', 10)
    layers = recomputeI1SoeDerivedLayers(layers)

    const carrying = layers.find((l) => l.layer === 'carrying')!
    const cc = carrying.categories.find((c) => c.key === 'soe_custom_1')!
    expect(cc.begin).toBe(60)

    // flatten 必须把自定义类别推出去（否则附注侧看不到该行）
    const flat = flattenI1SoeMovement(layers)
    const rows = flat.filter((r) => r.label === '碳排放权')
    expect(rows, '自定义类别未进 flatten → 附注缺行').toHaveLength(4) // 四层各一行
  })

  it('默认类别不可删；自定义类别可删且四层同步删除', () => {
    const layers = createDefaultI1SoeLayers()
    expect(removeI1SoeCategory(layers, 'patent'), '默认类别竟可删').toBeNull()
    expect(removeI1SoeCategory(layers, 'other')).toBeNull()
    expect(removeI1SoeCategory(layers, '不存在的键')).toBeNull()

    const added = addI1SoeCategory(layers, '碳排放权')!.layers
    const removed = removeI1SoeCategory(added, 'soe_custom_1')
    expect(removed).not.toBeNull()
    for (const block of removed!) {
      expect(block.categories.find((c) => c.key === 'soe_custom_1')).toBeFalsy()
    }
    expect(resolveI1SoeCategories(removed!)).toHaveLength(12)
  })

  it('i1SoeCategoryLabel：默认类别取常量，自定义取数据里的 label', () => {
    const layers = addI1SoeCategory(createDefaultI1SoeLayers(), '碳排放权')!.layers
    expect(i1SoeCategoryLabel('patent', layers)).toBe('专利权')
    expect(i1SoeCategoryLabel('soe_custom_1', layers)).toBe('碳排放权')
    expect(i1SoeCategoryLabel('未知键', layers)).toBe('未知键') // 不编造
  })
})

// ═══════════════════════════════════════════════════════════════════
// Property 22：撞名拒绝
// ═══════════════════════════════════════════════════════════════════

describe('Property 22 — 撞名拒绝（新增须先命名且不得重名）', () => {
  it('与默认类别同名 → 拒绝', () => {
    const layers = createDefaultI1SoeLayers()
    for (const c of I1_SOE_CATEGORIES) {
      expect(addI1SoeCategory(layers, c.label), `${c.label} 竟可重名新增`).toBeNull()
    }
  })

  it('空名 / 纯空白 → 拒绝（不产生无名行）', () => {
    const layers = createDefaultI1SoeLayers()
    expect(addI1SoeCategory(layers, '')).toBeNull()
    expect(addI1SoeCategory(layers, '   ')).toBeNull()
    expect(addI1SoeCategory(layers, '\t\n')).toBeNull()
  })

  it('与已有自定义类别同名 → 拒绝（含前后空白归一后比较）', () => {
    const once = addI1SoeCategory(createDefaultI1SoeLayers(), '碳排放权')!.layers
    expect(addI1SoeCategory(once, '碳排放权')).toBeNull()
    expect(addI1SoeCategory(once, '  碳排放权  ')).toBeNull()
    // 不同名可加
    expect(addI1SoeCategory(once, '域名')).not.toBeNull()
  })
})

// ═══════════════════════════════════════════════════════════════════
// Property 23：key 单调不复用已删序号
// ═══════════════════════════════════════════════════════════════════

describe('Property 23 — 自定义类别 key 单调不复用已删序号', () => {
  it('连续新增 seq 递增', () => {
    let layers = createDefaultI1SoeLayers()
    const a = addI1SoeCategory(layers, 'A')!
    expect(a.key).toBe('soe_custom_1')
    const b = addI1SoeCategory(a.layers, 'B', a.seq)!
    expect(b.key).toBe('soe_custom_2')
    const c = addI1SoeCategory(b.layers, 'C', b.seq)!
    expect(c.key).toBe('soe_custom_3')
  })

  it('🔴 删掉最大号后再增，seq 不复用（靠持久化计数器 seqFloor）', () => {
    let layers = createDefaultI1SoeLayers()
    const a = addI1SoeCategory(layers, 'A')!          // soe_custom_1
    const b = addI1SoeCategory(a.layers, 'B', a.seq)! // soe_custom_2
    let counter = b.seq                                // 持久化计数器 = 2

    // 删掉最大号 soe_custom_2 → 数据里 max 回退到 1
    const afterRemove = removeI1SoeCategory(b.layers, 'soe_custom_2')!
    expect(maxI1SoeCustomSeq(afterRemove)).toBe(1)

    // 不传 seqFloor 会复用已删的 2（这正是要防的形态）
    expect(nextI1SoeCustomKey(afterRemove)).toBe('soe_custom_2')

    // 传持久化计数器后不再复用
    expect(nextI1SoeCustomKey(afterRemove, counter)).toBe('soe_custom_3')
    const c = addI1SoeCategory(afterRemove, 'C', counter)!
    expect(c.key, '复用了已删序号 → 旧持久化数据会串台').toBe('soe_custom_3')
  })

  it('maxI1SoeCustomSeq 只认 soe_custom_ 前缀，默认类别不干扰', () => {
    const base = createDefaultI1SoeLayers()
    expect(maxI1SoeCustomSeq(base)).toBe(0)
    const one = addI1SoeCategory(base, 'X')!.layers
    expect(maxI1SoeCustomSeq(one)).toBe(1)
  })
})

// ═══════════════════════════════════════════════════════════════════
// Property 20：I1 上市列转置类别列稳定 key（Task 12）
// ═══════════════════════════════════════════════════════════════════

describe('Property 20 — I1 上市类别列稳定 key {slot.key}_{seq}', () => {
  it('i1CategoryColumnKey 生成 {key}_{seq}，不含中文', () => {
    expect(i1CategoryColumnKey({ key: 'land_use_right', label: '土地使用权', seq: 1, removable: true }))
      .toBe('land_use_right_1')
    expect(i1CategoryColumnKey({ key: 'other', label: '其他', seq: 11, removable: false }))
      .toBe('other_11')
    // 反向自检：生成结果不得含中文（否则撞键防护失效）
    const k = i1CategoryColumnKey({ key: 'patent', label: '专利权', seq: 3, removable: true })
    expect(/[\u4e00-\u9fa5]/.test(k), 'key 含中文 → 改名即撞键').toBe(false)
  })

  it('addI1Category 撞名拒绝 + seq 单调', () => {
    const base = [...I1_DEFAULT_CATEGORIES]
    expect(addI1Category(base, '土地使用权')).toBeNull()
    expect(addI1Category(base, '  ')).toBeNull()
    const added = addI1Category(base, '碳排放权')
    expect(added).not.toBeNull()
    expect(added!).toHaveLength(base.length + 1)
    const last = added![added!.length - 1]
    expect(last.label).toBe('碳排放权')
    expect(last.seq).toBeGreaterThan(Math.max(...base.map((c) => c.seq)) - 1)
  })

  it('renameI1Category 撞名拒绝', () => {
    const base = [...I1_DEFAULT_CATEGORIES]
    expect(renameI1Category(base, 'patent', '土地使用权')).toBeNull()
    const ok = renameI1Category(base, 'patent', '发明专利')
    expect(ok).not.toBeNull()
    expect(ok!.find((c) => c.key === 'patent')!.label).toBe('发明专利')
    // 🔴 改名后 key 不变 → 列 key 稳定，已推送数据不失落点
    expect(ok!.find((c) => c.key === 'patent')!.key).toBe('patent')
  })

  it('other 不可删，其他可删', () => {
    const base = [...I1_DEFAULT_CATEGORIES]
    expect(removeI1Category(base, 'other')).toBeNull()
    expect(removeI1Category(base, 'patent')).not.toBeNull()
  })
})

// ═══════════════════════════════════════════════════════════════════
// Property 24：I2 上市「研发支出」按费用性质可扩行（Task 14）
//
// 源模板 `backend/wp_templates/I/I2 开发支出.xlsx!附注披露（上市公司）`：
//   A9:A14 = 6 个固定费用性质（人工费/材料费/水电燃气费/折旧费/无形资产摊销/外购在研项目）
//   A15    = `……`（唯一可扩位）
//   A16    = 合  计
// ⇒ 固定 6 类不可删、可扩位需先命名、撞名拒绝。
// ═══════════════════════════════════════════════════════════════════

describe('Property 24 — I2 上市研发支出按费用性质可扩行', () => {
  it('默认行 = 源模板固定 6 类（A9:A14 逐字同序）', () => {
    expect(I2_NATURE_DEFAULT_NAMES).toEqual([
      '人工费', '材料费', '水电燃气费', '折旧费', '无形资产摊销', '外购在研项目',
    ])
    const rows = defaultNatureRows()
    expect(rows).toHaveLength(6)
    expect(rows.map((r) => r.name)).toEqual([...I2_NATURE_DEFAULT_NAMES])
    // 六个默认行全部被判为「固定类别」⇒ 不可删
    expect(rows.every(isI2NatureDefaultRow), '默认行竟可删').toBe(true)
  })

  it('新增自定义费用性质 → 追加在末尾且金额归零', () => {
    const base = defaultNatureRows()
    const next = addI2NatureRow(base, '委外研发费')
    expect(next, '合法命名竟被拒').not.toBeNull()
    expect(next!).toHaveLength(base.length + 1)
    expect(base, '入参被就地修改（非纯函数）').toHaveLength(6)
    const added = next![next!.length - 1]
    expect(added.name).toBe('委外研发费')
    expect(added.currentExpensed).toBe(0)
    expect(added.currentCapitalized).toBe(0)
    expect(added.priorExpensed).toBe(0)
    expect(added.priorCapitalized).toBe(0)
    // 自定义行不是固定类别 ⇒ 可删
    expect(isI2NatureDefaultRow(added)).toBe(false)
  })

  it('撞名拒绝：与 6 个固定类别同名 / 与已有自定义行同名 / 空名', () => {
    const base = defaultNatureRows()
    for (const n of I2_NATURE_DEFAULT_NAMES) {
      expect(addI2NatureRow(base, n), `${n} 竟可重名新增`).toBeNull()
    }
    expect(addI2NatureRow(base, '')).toBeNull()
    expect(addI2NatureRow(base, '   ')).toBeNull()
    // 归一后比较：内部空白与首尾空白都不能绕过撞名
    expect(addI2NatureRow(base, ' 人工费 ')).toBeNull()
    expect(addI2NatureRow(base, '人 工 费')).toBeNull()
    const once = addI2NatureRow(base, '委外研发费')!
    expect(addI2NatureRow(once, '委外研发费')).toBeNull()
    expect(addI2NatureRow(once, ' 委外研发费 ')).toBeNull()
  })

  it('固定 6 类不可删；自定义行可删', () => {
    const base = defaultNatureRows()
    for (const r of base) {
      expect(removeI2NatureRow(base, r.rowId), `${r.name} 竟可删`).toBeNull()
    }
    const withCustom = addI2NatureRow(base, '委外研发费')!
    const customId = withCustom[withCustom.length - 1].rowId
    const removed = removeI2NatureRow(withCustom, customId)
    expect(removed).not.toBeNull()
    expect(removed!).toHaveLength(base.length)
    expect(removed!.some((r) => r.rowId === customId)).toBe(false)
    // 不存在的 rowId → null（不静默改数据）
    expect(removeI2NatureRow(withCustom, 'no-such-id')).toBeNull()
  })

  it('自定义行进入推送载荷（可扩行能推附注）且计入合计', () => {
    const rows = addI2NatureRow(defaultNatureRows(), '委外研发费')!
      .map((r) => (r.name === '委外研发费'
        ? { ...r, currentExpensed: 30, currentCapitalized: 70 }
        : { ...r, currentExpensed: 10, currentCapitalized: 20 }))
    const sub = buildI2ListedNatureSubTable(rows)
    const labels = sub.map((r) => r['项目'])
    expect(labels, '自定义行未进载荷 ⇒ 增行是死操作').toContain('委外研发费')
    const total = sub.find((r) => r.is_total)!
    // 6 固定 × 10 + 自定义 30 = 90；6 × 20 + 70 = 190
    expect(total['cur_expense']).toBe(90)
    expect(total['cur_capitalize']).toBe(190)
  })
})

// ═══════════════════════════════════════════════════════════════════
// Property 25：I2 上市按性质表列结构与附注模板同构（Task 14 压扁修复）
//
// 🔴 原缺陷：`I2_NATURE_COLUMNS` 全列 `flat: true` 且 label 被改写成
// 「本期费用化」⇒ 投影器 `_extract_column_groups` 命中「任一列 flat ⇒ 整表返 []」，
// push 路径两级表头被静默压扁（同 D2 把 6 列压成 2 列的老坑）。
// 判据一律与模板 JSON **实读交叉锁死**，不在此处抄第二份字面量。
// ═══════════════════════════════════════════════════════════════════

const TPL_LISTED = JSON.parse(
  readFileSync(resolve(__dirname, '../../../../../../../backend/data/note_template_listed.json'), 'utf-8'),
) as { sections?: Array<{ section_number?: string; tables?: Array<{ name?: string; headers?: string[]; columns?: any[] }> }> }

function tplTable(sectionNumber: string, tableName: string) {
  const sec = (TPL_LISTED.sections ?? []).find((s) => String(s.section_number ?? '').trim() === sectionNumber)
  return (sec?.tables ?? []).find((t) => t.name === tableName)
}

describe('Property 25 — I2 上市按性质表列结构与附注模板同构', () => {
  const [payload] = buildI2ListedSyncPayloads('wp-i2', null, {
    natureRows: [], movementRows: [], importantRows: [], impairmentRows: [],
    noteText: '', noteCap: '', noteImpairTest: '', notePurchased: '',
  })
  const cols = payload.columns![I2_LISTED_SUBTABLE.nature]

  it('模板 §五、27「研发支出」确实存在且已声明 group（守卫锚点有效）', () => {
    const t = tplTable('五、27', I2_LISTED_SUBTABLE.nature)
    expect(t, '模板缺表 ⇒ 本 Property 的比对基准失效（ANCHOR-MISS）').toBeDefined()
    expect((t!.columns ?? []).length, '模板列为空 ⇒ 无法交叉锁死').toBeGreaterThan(0)
    expect(
      (t!.columns ?? []).some((c: any) => c.group),
      '模板侧未声明 group ⇒ 应先修模板再对齐载荷',
    ).toBe(true)
  })

  it('🔴 载荷不得声明 flat（否则投影器整表返 [] → 两级表头被压扁）', () => {
    const flatted = cols.filter((c) => c.flat).map((c) => c.key)
    expect(
      flatted,
      '任一列 flat=true 会让 _extract_column_groups 返 []，push 路径两级表头静默压扁',
    ).toEqual([])
    // 正向：必须真的有 group 列，不能靠"两边都不表态"骗过上一条
    expect(cols.some((c) => c.group), '既无 flat 又无 group ⇒ 会走前缀推断造凭空父表头').toBe(true)
  })

  it('列 key / label / group / format 逐项等于模板（交叉锁死，不抄第二份字面量）', () => {
    const tpl = tplTable('五、27', I2_LISTED_SUBTABLE.nature)!.columns!
    expect(cols.map((c) => c.key)).toEqual(tpl.map((c: any) => c.key))
    expect(cols.map((c) => c.label)).toEqual(tpl.map((c: any) => c.label))
    expect(cols.map((c) => c.group ?? null)).toEqual(tpl.map((c: any) => c.group ?? null))
    expect(cols.map((c) => c.format ?? null)).toEqual(tpl.map((c: any) => c.format ?? null))
  })

  it('标签列头等于模板 headers[0]，group 覆盖本期/上期各 2 子列', () => {
    const t = tplTable('五、27', I2_LISTED_SUBTABLE.nature)!
    const labelDef = cols.find((c) => c.is_label) ?? cols[0]
    expect(labelDef.label).toBe(t.headers![0])
    const groups = cols.filter((c) => c.group).map((c) => c.group)
    expect(groups).toEqual(['本期发生额', '本期发生额', '上期发生额', '上期发生额'])
  })

  it('列 key ≡ 行字段名（投影器 r.get(col.key) 对齐前提，防整表空白）', () => {
    const rows = buildI2ListedNatureSubTable([
      {
        rowId: 'r1', name: '人工费',
        currentExpensed: 1, currentCapitalized: 2, priorExpensed: 3, priorCapitalized: 4,
      },
    ])
    const dataRow = rows[0]
    for (const c of cols) {
      expect(c.key in dataRow, `列 key「${c.key}」在行里取不到 ⇒ 该列整列空白`).toBe(true)
    }
    // 值按源模板列序对位（本期费用化/本期资本化/上期费用化/上期资本化）
    expect(cols.filter((c) => !c.is_label).map((c) => dataRow[c.key])).toEqual([1, 2, 3, 4])
  })
})
