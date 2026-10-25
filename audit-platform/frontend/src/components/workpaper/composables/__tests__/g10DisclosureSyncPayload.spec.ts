import { describe, expect, it } from 'vitest'
import {
  G10_NOTE_ITEM_LABEL,
  G10_NOTE_TOTAL_LABEL,
  buildG10ListedSyncPayloads,
  buildG10SoeSyncPayloads,
} from '../g10DisclosureSyncPayload'
import { defaultG10ListedDiscStore, defaultG10SoeDiscStore } from '../g10DisclosureFromAdj'
import {
  G10_DERIVATIVE_SUBTABLE,
  G10_DISCLOSURE_SHEET_NAME,
  G10_NOTE_SECTION,
  G10_SUBTABLE,
} from '../g10NoteSectionMap'
import { G10_LISTED_MOVEMENT_ROWS, G10_SOE_BALANCE_ROWS } from '../g10SchemaRows'

const fvName = (y: number | string) =>
  `对于指定为以公允价值计量且其变动计入当期损益的金融负债，${y}年公允价值的变动情况如下表所示：`

function listedPayloads(auditYear: number | null, mutate?: (s: ReturnType<typeof defaultG10ListedDiscStore>) => void) {
  const store = defaultG10ListedDiscStore()
  mutate?.(store)
  return buildG10ListedSyncPayloads('wp-g10', [], { store, auditNote: '审计说明', auditYear })
}

function soePayloads(auditYear: number | null, mutate?: (s: ReturnType<typeof defaultG10SoeDiscStore>) => void) {
  const store = defaultG10SoeDiscStore()
  mutate?.(store)
  return buildG10SoeSyncPayloads('wp-g10', ['soe_standalone'], { store, auditNote: '国企说明', auditYear })
}

const tableNames = (data: Record<string, unknown>) => Object.keys(data).filter((k) => !k.startsWith('_'))

describe('g10DisclosureSyncPayload', () => {
  it('上市写五、34，sheet_name 为源 xlsx 真实 tab 名', () => {
    const payloads = listedPayloads(2025)
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(G10_NOTE_SECTION.listed.trading)
    // sheet_name = 源 xlsx 真实 tab 名（非 `附注上市` 短名，否则附注反向跳转匹配不上）
    expect(payloads[0].sheet_name).toBe(G10_DISCLOSURE_SHEET_NAME.listed)
  })

  it.each([2023, 2025, 2026, null])('表名是模板常量、不随审计年度拼（auditYear=%s）', (year) => {
    expect(tableNames(listedPayloads(year)[0].sub_table_data)).toEqual(Object.values(G10_SUBTABLE.listed))
    expect(tableNames(soePayloads(year)[0].sub_table_data)).toEqual(Object.values(G10_SUBTABLE.soe))
  })

  it('旧载荷按审计年度拼的公允价值变动表名随 _removed_table_keys 清掉（与现名相同的不发）', () => {
    expect(soePayloads(2024)[0].sub_table_data._removed_table_keys).toContain(fvName(2024))
    const listed = listedPayloads(2024)[0].sub_table_data._removed_table_keys as string[]
    expect(listed).toContain(fvName(2024))
    expect(listed).not.toContain(G10_SUBTABLE.listed.fvCredit)
  })

  it('上市主表按底稿行序带父行：父行 = 其下各行之和，合计 = 末级行之和（父行不重复计）', () => {
    const [payload] = listedPayloads(2025, (s) => {
      s.movement.mv_trading_bond = { openingAmount: 100, increaseAmount: 20, decreaseAmount: 10, closingAmount: 110 }
      s.movement.mv_other = { openingAmount: 5, increaseAmount: 0, decreaseAmount: 0, closingAmount: 5 }
      s.movement.mv_designated_bond = { openingAmount: 30, increaseAmount: 0, decreaseAmount: 30, closingAmount: 0 }
    })
    const rows = payload.sub_table_data[G10_SUBTABLE.listed.trading] as Record<string, unknown>[]
    expect(rows.map((r) => r.label)).toEqual([...G10_LISTED_MOVEMENT_ROWS.map((d) => d.label.trim()), G10_NOTE_TOTAL_LABEL])
    const byKey = Object.fromEntries(rows.map((r) => [r.row_key, r]))
    expect(byKey.mv_trading).toMatchObject({ begin_balance: 105, end_balance: 115 })
    expect(byKey.mv_designated).toMatchObject({ begin_balance: 30, current_decrease: 30, end_balance: 0 })
    expect(rows.at(-1)).toMatchObject({ label: '合计', begin_balance: 135, end_balance: 115, is_total: true })
  })

  it('国企主表同样带父行；列键 = 模板 end_fv / begin_fv', () => {
    const [payload] = soePayloads(2025, (s) => {
      s.balance.soe_trading_bond = { currentAmount: 200, priorAmount: 180 }
      s.balance.soe_designated_other = { currentAmount: 7, priorAmount: 3 }
    })
    const rows = payload.sub_table_data[G10_SUBTABLE.soe.trading] as Record<string, unknown>[]
    expect(rows.map((r) => r.label)).toEqual([...G10_SOE_BALANCE_ROWS.map((d) => d.label.trim()), G10_NOTE_TOTAL_LABEL])
    const byKey = Object.fromEntries(rows.map((r) => [r.row_key, r]))
    expect(byKey.soe_trading).toMatchObject({ end_fv: 200, begin_fv: 180 })
    expect(byKey.soe_designated).toMatchObject({ end_fv: 7, begin_fv: 3 })
    expect(rows.at(-1)).toMatchObject({ end_fv: 207, begin_fv: 183, is_total: true })
  })

  it('标签列头用模板字面量「项目」并显式 flat', () => {
    for (const payload of [...listedPayloads(2025), ...soePayloads(2025)]) {
      for (const cols of Object.values(payload.columns ?? {})) {
        expect(cols[0]).toMatchObject({ key: 'label', label: G10_NOTE_ITEM_LABEL, is_label: true, flat: true })
      }
    }
  })

  it('衍生负债写入五、35：表名 = 章节名「衍生金融负债」（不是表前的 15 号文提示段），无旧表可清', () => {
    const payloads = listedPayloads(2025, (s) => {
      s.derivativeRows = [{ rowKey: 'd1', label: '利率互换', currentAmount: 50, priorAmount: 40 }]
    })
    expect(payloads).toHaveLength(2)
    expect(payloads[1].section_id).toBe(G10_NOTE_SECTION.listed.derivative)
    const data = payloads[1].sub_table_data
    expect(G10_DERIVATIVE_SUBTABLE.listed).toBe('衍生金融负债')
    expect(tableNames(data)).toEqual([G10_DERIVATIVE_SUBTABLE.listed])
    expect(data).not.toHaveProperty('_removed_table_keys')
    expect((data[G10_DERIVATIVE_SUBTABLE.listed] as Record<string, unknown>[]).at(-1)).toMatchObject({
      end_balance: 50, prior_balance: 40, is_total: true,
    })
  })

  it('国企写八、34', () => {
    const payloads = soePayloads(2025)
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(G10_NOTE_SECTION.soe.trading)
    expect(payloads[0].sheet_name).toBe(G10_DISCLOSURE_SHEET_NAME.soe)
  })
})
