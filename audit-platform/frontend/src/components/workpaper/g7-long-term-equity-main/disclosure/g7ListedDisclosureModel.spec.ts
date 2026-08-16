import { describe, expect, it } from 'vitest'
import {
  G7_LISTED_DISCLOSURE_SECTIONS,
  buildG7ListedColumns,
  buildG7ListedSyncData,
  buildG7ListedSyncPayloads,
  createG7ListedDisclosureState,
  markG7ListedSynced,
  resolveG7ListedTableColumns,
} from './g7ListedDisclosureModel'

describe('G7 listed disclosure source model', () => {
  it('keeps the real Excel hierarchy instead of the legacy five-section placeholder', () => {
    expect(G7_LISTED_DISCLOSURE_SECTIONS.map(section => section.id)).toEqual([
      'investment-movement',
      'subsidiary-interests',
      'joint-associate-interests',
      'joint-operations',
    ])

    const tables = G7_LISTED_DISCLOSURE_SECTIONS.flatMap(section => section.tables ?? [])
    const narratives = G7_LISTED_DISCLOSURE_SECTIONS.flatMap(section => section.narratives ?? [])
    expect(tables).toHaveLength(15)
    expect(narratives).toHaveLength(11)
    expect(tables.find(table => table.id === 'investment-movement')?.sourceRows).toBe('A8:M23')
    expect(tables.find(table => table.id === 'joint-operations')?.sourceRows).toBe('A235:F240')
  })

  it('assigns each section to its target note chapter (五、18 vs 七、1)', () => {
    // R8.1：主表所在区段归 五、18；子公司/合营联营/共同经营三区块归 七、1
    // （旧实现把 15 张表全推 五、18，其中 14 张在该章节是孤儿表）。
    const byId = new Map(G7_LISTED_DISCLOSURE_SECTIONS.map(s => [s.id, s]))
    expect(byId.get('investment-movement')?.noteSectionId).toBe('五、18')
    for (const id of ['subsidiary-interests', 'joint-associate-interests', 'joint-operations']) {
      expect(byId.get(id)?.noteSectionId).toBe('七、1')
    }
  })

  it('template table keys align with note_template_listed.json 七、1 table names', () => {
    const tables = G7_LISTED_DISCLOSURE_SECTIONS.flatMap(section => section.tables ?? [])
    const keys = tables.map(t => t.templateTableKey ?? t.title)
    expect(keys).toEqual([
      '长期股权投资',
      '企业集团的构成',
      '重要的非全资子公司',
      '重要非全资子公司主要财务信息—期末数',
      '续（1）',
      '续（2）',
      '未丧失控制权的所有者权益份额变动影响',
      '重要的合营企业或联营企业',
      '重要合营企业主要财务信息',
      '续：重要合营企业本期及上期经营成果',
      '重要联营企业主要财务信息',
      '续：重要联营企业本期及上期经营成果',
      '其他不重要合营企业和联营企业的汇总财务信息',
      '对合营企业或联营企业发生超额亏损的分担额',
      '重要的共同经营',
    ])
  })

  it('preserves source-workpaper lineage and separates note text during sync', () => {
    const state = createG7ListedDisclosureState()
    const composition = state.tables['subsidiary-composition']
    expect(composition[0].source).toContain('被投资单位基本信息G7-4')

    state.texts['impairment-method'] = '按预计未来现金流量现值确定可收回金额。'
    const syncData = buildG7ListedSyncData(state)
    // 同步键 = templateTableKey（对齐 note_template_listed.json 的 tables[].name），
    // 非 UI 展示用的 table.title（Task 5.1 修正孤儿表名）。
    // 🔴 Task 5.6：骨架行数不写死，初始态只给 1 行（Requirement 11.7）。
    expect(syncData['企业集团的构成']).toHaveLength(1)
    expect(syncData['长期股权投资']).toBeTruthy()
    expect(syncData._note_texts).toEqual([
      {
        section: 'impairment-method',
        title: '长期资产减值测试说明',
        text: '按预计未来现金流量现值确定可收回金额。',
      },
    ])
  })

  it('main table has ①合营企业/②联营企业 group label rows (Task 5.3)', () => {
    const state = createG7ListedDisclosureState()
    const rows = state.tables['investment-movement']
    // 🔴 Task 5.6：骨架行数不写死，初始态每组只给 1 行空行（Requirement 11.7）。
    expect(rows.map(r => r.label)).toEqual([
      '①合营企业', '', '小  计',
      '②联营企业', '', '小  计',
      '合  计',
    ])
    expect(rows[0].kind).toBe('group')
    expect(rows[3].kind).toBe('group')
  })

  it('main table subtotal sumRows track the actually generated blank-row ids (Task 5.6)', () => {
    const state = createG7ListedDisclosureState()
    const rows = state.tables['investment-movement']
    const jvSubtotal = rows.find(r => r.id === 'joint-venture-subtotal')!
    const assocSubtotal = rows.find(r => r.id === 'associate-subtotal')!
    expect(jvSubtotal.sumRows).toEqual(['joint-venture-1'])
    expect(assocSubtotal.sumRows).toEqual(['associate-1'])
  })

  it('important-associate-balance has 17 rows without 现金和现金等价物 (Property 12)', () => {
    const state = createG7ListedDisclosureState()
    const jvRows = state.tables['important-jv-balance'].map(r => r.label)
    const assocRows = state.tables['important-associate-balance'].map(r => r.label)
    expect(jvRows).toHaveLength(18)
    expect(jvRows).toContain('其中：现金和现金等价物')
    expect(assocRows).toHaveLength(17)
    expect(assocRows).not.toContain('其中：现金和现金等价物')
  })

  it('aligns unimportant aggregate and excess losses to grouped Excel structure', () => {
    const state = createG7ListedDisclosureState()
    const aggregate = state.tables['unimportant-aggregate']
    expect(aggregate.some(row => row.id === 'ua-jv-group')).toBe(true)
    expect(aggregate.some(row => row.id === 'ua-assoc-comprehensive')).toBe(true)

    const excess = state.tables['excess-losses']
    expect(excess.find(row => row.id === 'el-assoc-1')?.source).toContain('第17行')
    expect(excess.find(row => row.id === 'el-total')?.sumRows).toEqual(['el-jv-subtotal', 'el-assoc-subtotal'])

    state.tables['investment-movement'].find(row => row.id === 'joint-venture-1')!.values.closingBook = 10
    state.tables['investment-movement'].find(row => row.id === 'associate-1')!.values.closingBook = 30
    const syncData = buildG7ListedSyncData(state)
    const total = syncData['长期股权投资'].find((row: any) => row._row_id === 'investment-total')
    expect(total?.closingBook).toBe(40)
  })

  describe('buildG7ListedSyncPayloads (Task 5.1/5.4/5.5 — multi-chapter payload + removed-table diff)', () => {
    it('groups tables into 五、18 and 七、1 payloads with matching sheet name', () => {
      const state = createG7ListedDisclosureState()
      const payloads = buildG7ListedSyncPayloads(state)
      const byNote = new Map(payloads.map(p => [p.noteSectionId, p]))

      expect(payloads).toHaveLength(2)
      expect(byNote.get('五、18')?.sheetName).toBe('附注披露信息（上市公司）')
      expect(byNote.get('七、1')?.sheetName).toBe('附注披露信息（上市公司）')

      // 五、18 只承载主表；其余 14 张表全归 七、1（不再是孤儿表）。
      const mainKeys = Object.keys(byNote.get('五、18')!.subTableData).filter(k => !k.startsWith('_'))
      expect(mainKeys).toEqual(['长期股权投资'])
      const otherKeys = Object.keys(byNote.get('七、1')!.subTableData).filter(k => !k.startsWith('_'))
      expect(otherKeys).toHaveLength(14)
    })

    it('routes _note_texts into the payload matching each narrative section', () => {
      const state = createG7ListedDisclosureState()
      // 主表区（五、18）唯一的说明
      state.texts['impairment-method'] = '按预计未来现金流量现值确定可收回金额。'
      // 七、1 区的说明
      state.texts['subsidiary-control-judgement'] = '本公司持股 60%，同时持有过半数表决权。'

      const payloads = buildG7ListedSyncPayloads(state)
      const byNote = new Map(payloads.map(p => [p.noteSectionId, p]))

      const mainTexts = byNote.get('五、18')!.subTableData._note_texts as any[]
      expect(mainTexts).toEqual([
        { section: 'impairment-method', title: '长期资产减值测试说明', text: '按预计未来现金流量现值确定可收回金额。' },
      ])

      const otherTexts = byNote.get('七、1')!.subTableData._note_texts as any[]
      expect(otherTexts.map(t => t.section)).toContain('subsidiary-control-judgement')
      // 空文本不进 _note_texts
      expect(otherTexts.every((t: any) => t.text.trim().length > 0)).toBe(true)
    })

    it('emits no _removed_table_keys on first sync (previouslySyncedTables empty)', () => {
      const state = createG7ListedDisclosureState()
      const payloads = buildG7ListedSyncPayloads(state)
      for (const payload of payloads) {
        expect(payload.subTableData._removed_table_keys).toBeUndefined()
      }
    })

    it('computes _removed_table_keys as (previously synced − pushed), never removing pushed keys', () => {
      const state = createG7ListedDisclosureState()
      // 模拟历史推送过一个已改名/已删除的表，且历史清单里混入本次仍会推送的表（不应被删）。
      state.previouslySyncedTables = {
        '七、1': ['企业集团的构成', '已废弃的历史表名'],
        '五、18': ['长期股权投资'],
      }
      const payloads = buildG7ListedSyncPayloads(state)
      const byNote = new Map(payloads.map(p => [p.noteSectionId, p]))

      const otherRemoved = byNote.get('七、1')!.subTableData._removed_table_keys as string[]
      expect(otherRemoved).toEqual(['已废弃的历史表名'])
      expect(otherRemoved).not.toContain('企业集团的构成')

      // 五、18 本次推送集合与历史推送集合完全一致 → 无需删除
      expect(byNote.get('五、18')!.subTableData._removed_table_keys).toBeUndefined()
    })

    it('markG7ListedSynced records this sync as the new baseline for the next diff', () => {
      const state = createG7ListedDisclosureState()
      const payloads = buildG7ListedSyncPayloads(state)
      const next = markG7ListedSynced(state, payloads)

      expect(next['五、18']).toEqual(['长期股权投资'])
      expect(next['七、1']).toHaveLength(14)

      // 应用新基线后立即再构建一次 payload：无历史遗留差异 → 无 _removed_table_keys
      state.previouslySyncedTables = next
      const secondPayloads = buildG7ListedSyncPayloads(state)
      for (const payload of secondPayloads) {
        expect(payload.subTableData._removed_table_keys).toBeUndefined()
      }
    })
  })

  describe('dynamic slot columns (Task 5.6, Property 18 — column count driven by data)', () => {
    it('buildG7ListedColumns is callable with zero args and returns non-empty columns (coverage sweep)', () => {
      const columns = buildG7ListedColumns()
      const ownershipCols = columns['未丧失控制权的所有者权益份额变动影响']
      const assocCols = columns['重要联营企业主要财务信息']
      expect(ownershipCols.length).toBeGreaterThan(1)
      expect(assocCols.length).toBeGreaterThan(1)
      // 缺省 3 家联营企业 × 2 子列 + 标签列
      expect(assocCols).toHaveLength(1 + 3 * 2)
    })

    it('column count grows/shrinks with entitySlots names (single-column slot)', () => {
      const table = G7_LISTED_DISCLOSURE_SECTIONS
        .flatMap(s => s.tables ?? [])
        .find(t => t.id === 'ownership-change-impact')!

      const three = resolveG7ListedTableColumns(table, { 'ownership-change-company': ['甲公司', '乙公司', '丙公司'] })
      expect(three.map(c => c.key)).toEqual([
        'ownership-change-company_1',
        'ownership-change-company_2',
        'ownership-change-company_3',
      ])
      expect(three.map(c => c.label)).toEqual(['甲公司', '乙公司', '丙公司'])
      expect(three.every(c => c.flat)).toBe(true)

      const one = resolveG7ListedTableColumns(table, { 'ownership-change-company': ['甲公司'] })
      expect(one).toHaveLength(1)
    })

    it('renaming an entity changes label but keeps key stable (no data loss on rename)', () => {
      const table = G7_LISTED_DISCLOSURE_SECTIONS
        .flatMap(s => s.tables ?? [])
        .find(t => t.id === 'ownership-change-impact')!

      const before = resolveG7ListedTableColumns(table, { 'ownership-change-company': ['甲公司', '乙公司'] })
      const afterRename = resolveG7ListedTableColumns(table, { 'ownership-change-company': ['甲公司改名', '乙公司'] })
      expect(afterRename.map(c => c.key)).toEqual(before.map(c => c.key))
      expect(afterRename[0].label).toBe('甲公司改名')
    })

    it('two-sub-column slot (important-associate) groups by entity name with stable keys', () => {
      const table = G7_LISTED_DISCLOSURE_SECTIONS
        .flatMap(s => s.tables ?? [])
        .find(t => t.id === 'important-associate-balance')!

      const cols = resolveG7ListedTableColumns(table, { 'important-associate': ['联营企业A', '联营企业B'] })
      expect(cols).toHaveLength(4)
      expect(cols.map(c => c.key)).toEqual([
        'important-associate_1_current',
        'important-associate_1_prior',
        'important-associate_2_current',
        'important-associate_2_prior',
      ])
      expect(cols.map(c => c.group)).toEqual(['联营企业A', '联营企业A', '联营企业B', '联营企业B'])
      // 🔴 子列 label 逐字取源 xlsx（`g7-column-alignment-…` spec Task 7 的 D 类裁决）：
      // 联营 FS 表源 A165:G187 的子列是「期末数 / 期初数」，**不是**此前写死的
      // 「期末/本期 / 期初/上期」（那是把 FS 表与 PL 表两套子列混成一套的产物）。
      // 本断言原先锁着旧值 ⇒ Task 7 改了 `IMPORTANT_ASSOCIATE_FS_SUB` 后本用例即转红，
      // 但该任务当时未跑本 spec、仍被标记完成（假绿）。现按源原文更正。
      expect(cols.map(c => c.label)).toEqual(['期末数', '期初数', '期末数', '期初数'])
    })

    it('sync data reflects the current entitySlots column set (not the static default)', () => {
      const state = createG7ListedDisclosureState()
      state.entitySlots!['ownership-change-company'] = ['独家投资方', '第二投资方']
      const syncData = buildG7ListedSyncData(state)
      const rows = syncData['未丧失控制权的所有者权益份额变动影响']
      expect(rows.length).toBeGreaterThan(0)
      // 缺省 6 家（company_1..6），改成 2 家后 columns 元数据随之收缩为 2 列，
      // 且 buildG7ListedColumns 输出的列头须与 entitySlots 一致（不是静态默认 6 家）。
      const columns = buildG7ListedColumns(state.entitySlots)
      const ownershipCols = columns['未丧失控制权的所有者权益份额变动影响']
      // 🔴 标签列头是「项  目」（**双空格**）—— 源 xlsx A96 原文如此，seed 的
      // `headers[0]` 也一直是双空格。Task 12 把运行时 `labelHeader` 从归一化的
      // 「项目」改回源原文以消除契约 P5 偏差（R4.1/R4.4：禁「统一成好看的那种」）。
      expect(ownershipCols.map(c => c.label)).toEqual(['项  目', '独家投资方', '第二投资方'])
    })

    it('static (non-slot) tables are unaffected by resolveG7ListedTableColumns', () => {
      const table = G7_LISTED_DISCLOSURE_SECTIONS
        .flatMap(s => s.tables ?? [])
        .find(t => t.id === 'subsidiary-composition')!
      expect(resolveG7ListedTableColumns(table, {})).toBe(table.columns)
    })
  })
})
