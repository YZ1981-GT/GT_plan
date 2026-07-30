/**
 * f2NoteSectionMap + sync payload 单测
 */
import { describe, it, expect } from 'vitest'
import {
  F2_NOTE_SECTION,
  isF2DisclosureApplicable,
  resolveF2CurrentStandard,
  resolveF2NoteSectionTarget,
} from '../composables/f2NoteSectionMap'
import {
  buildF2ListedColumns,
  buildF2ListedSubTableData,
  buildF2SoeColumns,
  buildF2SoeSubTableData,
  buildF2SyncPayload,
} from '../composables/f2DisclosureSyncPayload'

describe('f2NoteSectionMap', () => {
  it('listed → 五、9 / soe → 八、10', () => {
    expect(F2_NOTE_SECTION.listed).toBe('五、9')
    expect(F2_NOTE_SECTION.soe).toBe('八、10')
  })

  it('空准则时两侧均适用', () => {
    expect(isF2DisclosureApplicable('listed', [])).toBe(true)
    expect(isF2DisclosureApplicable('soe', [])).toBe(true)
  })

  it('一般企业等非上市/国企标签时两侧仍适用', () => {
    expect(isF2DisclosureApplicable('listed', ['general'])).toBe(true)
    expect(isF2DisclosureApplicable('soe', ['一般企业'])).toBe(true)
  })

  it('上市准则不适用国企页，反之亦然', () => {
    expect(isF2DisclosureApplicable('listed', ['listed_standalone'])).toBe(true)
    expect(isF2DisclosureApplicable('soe', ['listed_standalone'])).toBe(false)
    expect(isF2DisclosureApplicable('soe', ['soe_standalone'])).toBe(true)
    expect(isF2DisclosureApplicable('listed', ['soe_standalone'])).toBe(false)
  })

  it('resolveF2NoteSectionTarget 按变体分流且不交叉', () => {
    const listed = resolveF2NoteSectionTarget('listed', ['listed_standalone'])!
    const soe = resolveF2NoteSectionTarget('soe', ['soe_standalone'])!
    expect(listed.sectionId).toBe('五、9')
    expect(listed.chipValue).toBe('Note:五、9')
    // sheetName = 源 xlsx 真实 tab 名（平台统一约定，见 N1/K1~K13/J1/I3~I6 同款映射）
    expect(listed.sheetName).toBe('附注披露信息（上市公司）')
    expect(soe.sectionId).toBe('八、10')
    expect(soe.chipValue).toBe('Note:八、10')
    expect(soe.sheetName).toBe('附注披露信息（国企）')
    expect(listed.sectionId).not.toBe(soe.sectionId)
  })

  it('不适用时返回 null', () => {
    expect(resolveF2NoteSectionTarget('listed', ['soe_standalone'])).toBeNull()
    expect(resolveF2NoteSectionTarget('soe', ['listed_consolidated'])).toBeNull()
  })

  it('current_standard 解析 consolidated / standalone', () => {
    expect(resolveF2CurrentStandard('listed', [])).toBe('listed_standalone')
    expect(resolveF2CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveF2CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
  })
})

describe('f2DisclosureSyncPayload', () => {
  const listedSnap = {
    section1Rows: [{
      rowKey: 'raw-materials',
      label: '原材料',
      endGross: 100,
      endImpairment: 10,
      endNet: 90,
      priorGross: 80,
      priorImpairment: 5,
      priorNet: 75,
    }],
    section1Total: {
      label: '合计',
      endGross: 100,
      endImpairment: 10,
      endNet: 90,
      priorGross: 80,
      priorImpairment: 5,
      priorNet: 75,
    },
    section2Rows: [{
      rowKey: 'raw-materials',
      label: '原材料',
      opening: 5,
      incProvision: 5,
      incOther: 0,
      decReversal: 0,
      decOther: 0,
      ending: 10,
    }],
    section2Total: {
      label: '合计',
      opening: 5,
      incProvision: 5,
      incOther: 0,
      decReversal: 0,
      decOther: 0,
      ending: 10,
    },
    section2QualRows: [{
      rowKey: 'raw-materials',
      label: '原材料',
      nrvBasis: '市价',
      reversalReason: '',
    }],
    s3EndRows: [],
    s3PriorRows: [],
    s4BorrowText: '借款资本化说明',
    s4AmortText: '合同履约成本摊销说明',
    s5Rows: [],
    s6Rows: [],
    s7Rows: [],
    s8DataResourceRows: [
      { label: '一、账面原值', purchased: 0, self_processed: 0, other: 0, total: 0 },
      { label: '1.期初余额', purchased: 100, self_processed: 0, other: 0, total: 100 },
    ],
    noteCategory: '分类说明',
    noteNrv: 'NRV',
    noteProvision: '计提依据',
    noteRe: '房企说明',
  }

  it('上市 sub_table_data 含同名子表与 note texts', () => {
    const sub = buildF2ListedSubTableData(listedSnap)
    expect(sub['存货分类']).toHaveLength(2)
    expect(sub['存货分类'][0].label).toBe('原材料')
    expect(sub['存货分类'][0].end_gross).toBe(100)
    expect(sub['存货跌价准备及合同履约成本减值准备'][0].ending).toBe(10)
    expect(sub['_note_texts'].some((r) => r.section === 'listed-note-category')).toBe(true)
  })

  it('上市 sync payload 只指向 五、9', () => {
    const payload = buildF2SyncPayload(
      'listed',
      'wp-1',
      ['listed_standalone'],
      buildF2ListedSubTableData(listedSnap),
    )!
    expect(payload.section_id).toBe('五、9')
    expect(payload.sheet_name).toBe('附注披露信息（上市公司）')
    expect(payload.current_standard).toBe('listed_standalone')
    expect(payload.wp_id).toBe('wp-1')
    expect(payload.section_id).not.toBe('八、10')
    // disclosure-table-sync-convergence Task 7: 载荷携带源对齐 _columns
    expect(payload.columns).toBeDefined()
    const lc = payload.columns!['存货分类']
    expect(lc).toBeDefined()
    expect(lc[0]).toMatchObject({ key: 'label', label: '项目', is_label: true })
    // 两级表头：子列名 + group 父表头（后端 _extract_column_groups 据此产出 _column_groups）
    expect(lc.find((c) => c.key === 'end_gross')).toMatchObject({
      label: '账面余额',
      group: '期末余额',
    })
    expect(lc.find((c) => c.key === 'prior_net')).toMatchObject({
      label: '账面价值',
      group: '上年年末余额',
    })
    // 每个 sub_table_data 键都有对应列头
    for (const k of Object.keys(payload.sub_table_data)) {
      if (k.startsWith('_')) continue
      expect(payload.columns![k], `缺列头: ${k}`).toBeDefined()
    }
  })

  it('国企 sync payload 只指向 八、10', () => {
    const soeSnap = {
      section1Rows: [{
        rowKey: 'raw-combined',
        label: '原材料',
        kind: 'normal',
        endGross: 50,
        endImpairment: 0,
        endNet: 50,
        priorGross: 40,
        priorImpairment: 0,
        priorNet: 40,
      }],
      section1Total: {
        label: '合计',
        endGross: 50,
        endImpairment: 0,
        endNet: 50,
        priorGross: 40,
        priorImpairment: 0,
        priorNet: 40,
      },
      section2Rows: [{
        rowKey: 'raw-combined',
        label: '原材料',
        opening: 0,
        incProvision: 0,
        incOther: 0,
        decReversal: 0,
        decWriteOff: 0,
        decOther: 0,
        ending: 0,
      }],
      section2Total: {
        label: '合计',
        opening: 0,
        incProvision: 0,
        incOther: 0,
        decReversal: 0,
        decWriteOff: 0,
        decOther: 0,
        ending: 0,
      },
      s5DataResourceRows: [
        { label: '一、账面原值', purchased: 0, self_processed: 0, other: 0, total: 0 },
        { label: '1.期初余额', purchased: 20, self_processed: 30, other: 0, total: 50 },
      ],
      noteCategory: '国企分类',
      s3BorrowText: '借款',
      s4AmortText: '摊销',
      noteText: '其他',
    }
    const payload = buildF2SyncPayload(
      'soe',
      'wp-2',
      ['soe_standalone'],
      buildF2SoeSubTableData(soeSnap),
    )!
    expect(payload.section_id).toBe('八、10')
    expect(payload.sheet_name).toBe('附注披露信息（国企）')
    expect(payload.current_standard).toBe('soe_standalone')
    expect(payload.sub_table_data['存货分类'][0].end_gross).toBe(50)
    expect(payload.section_id).not.toBe('五、9')
    // Task 7: 国企版 _columns 源对齐（含转销列）
    expect(payload.columns).toBeDefined()
    const sc = payload.columns!['存货分类']
    expect(sc[0]).toMatchObject({ key: 'label', label: '项目', is_label: true })
    const s2 = payload.columns!['存货跌价准备及合同履约成本减值准备']
    // 国企本期减少三列（转回/转销/其他）走两级表头：子列名 + group 父表头
    expect(s2.find((c) => c.key === 'decrease_writeoff')).toMatchObject({
      label: '转销',
      group: '本期减少',
    })
    expect(s2.find((c) => c.key === 'decrease_reversal')).toMatchObject({
      label: '转回',
      group: '本期减少',
    })
    expect(s2.find((c) => c.key === 'increase_provision')).toMatchObject({
      label: '计提',
      group: '本期增加',
    })
  })

  it('单级表头子表标 flat，抑制后端前缀推断出凭空父表头', () => {
    const listedCols = buildF2ListedColumns()
    // 源模板单行表头的表：房企 3 表 + 数据资源
    for (const key of ['开发成本', '开发产品', '周转房', '确认为存货的数据资源']) {
      const cols = listedCols[key]
      expect(cols, `缺子表列头: ${key}`).toBeDefined()
      expect(cols.some((c) => c.flat), `${key} 未标 flat`).toBe(true)
      expect(cols.every((c) => !c.group), `${key} 不应有 group`).toBe(true)
    }
    // 两级表头的表不得标 flat
    for (const key of ['存货分类', '存货跌价准备及合同履约成本减值准备', '按组合计提存货跌价准备']) {
      expect(listedCols[key].some((c) => c.flat), `${key} 误标 flat`).toBe(false)
      expect(listedCols[key].some((c) => c.group), `${key} 缺 group`).toBe(true)
    }
    // 国企数据资源同样单级
    expect(buildF2SoeColumns()['确认为存货的数据资源'].some((c) => c.flat)).toBe(true)
  })

  it('每张子表都必须在 flat / group 之间明确表态（否则后端回退前缀推断）', () => {
    for (const [variant, cols] of [
      ['listed', buildF2ListedColumns()],
      ['soe', buildF2SoeColumns()],
    ] as const) {
      for (const [name, defs] of Object.entries(cols)) {
        const hasFlat = defs.some((c) => c.flat)
        const hasGroup = defs.some((c) => c.group)
        expect(
          hasFlat || hasGroup,
          `${variant}/${name} 既无 flat 也无 group → 后端 _extract_column_groups 返回 null，会凭空造父表头`,
        ).toBe(true)
        expect(hasFlat && hasGroup, `${variant}/${name} 同时声明 flat 与 group（语义冲突）`).toBe(false)
      }
    }
  })

  it('同步载荷的列标签为纯文本（不得含 md 表格搬来的 <br/>）', () => {
    for (const cols of [buildF2ListedColumns(), buildF2SoeColumns()]) {
      for (const [name, defs] of Object.entries(cols)) {
        for (const d of defs) {
          expect(/<[^>]+>/.test(d.label ?? ''), `${name} 列标签含 HTML: ${d.label}`).toBe(false)
          expect(/<[^>]+>/.test(d.group ?? ''), `${name} 分组名含 HTML: ${d.group}`).toBe(false)
        }
      }
    }
  })

  it('不适用准则时 buildF2SyncPayload 返回 null', () => {
    expect(buildF2SyncPayload('listed', 'wp', ['soe_standalone'], {})).toBeNull()
    expect(buildF2SyncPayload('soe', 'wp', ['listed_standalone'], {})).toBeNull()
  })
})

describe('disclosure:note-text-updated 约定', () => {
  it('detail 含 wpCode/section/text', () => {
    const received: unknown[] = []
    const handler = (e: Event) => received.push((e as CustomEvent).detail)
    window.addEventListener('disclosure:note-text-updated', handler)
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: { wpCode: 'F2', section: 'soe-note-borrow', text: '借款说明' },
    }))
    window.removeEventListener('disclosure:note-text-updated', handler)
    expect(received).toEqual([{ wpCode: 'F2', section: 'soe-note-borrow', text: '借款说明' }])
  })
})
