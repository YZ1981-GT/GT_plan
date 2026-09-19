/**
 * H2 CIP 桥接 + H4 上市附注 sync payload
 */
import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import {
  H2_CIP_CACHE_PREFIX,
  buildH2CipSnapshot,
  cacheH2CipSnapshot,
  isH2CipAdjudicatedEvent,
  parseH2CipFromAdjudicatedEvent,
  readH2CipSnapshot,
} from '../h2CipBridge'
import {
  buildH4ListedMaterialsSubTable,
  buildH4ListedSyncPayloads,
  patchListedSummaryMaterialsRow,
} from '../h4DisclosureSyncPayload'
import { createDefaultH4ListedMaterials } from '../h4ListedDisclosureModel'
import { H2_LISTED_SUBTABLE, H2_NOTE_SECTION } from '../h2NoteSectionMap'

describe('h2CipBridge', () => {
  const pid = 'proj-h2-cip-test'

  beforeEach(() => {
    sessionStorage.removeItem(`${H2_CIP_CACHE_PREFIX}${pid}`)
  })

  afterEach(() => {
    sessionStorage.removeItem(`${H2_CIP_CACHE_PREFIX}${pid}`)
  })

  it('识别 H2 / 1604 审定事件', () => {
    expect(isH2CipAdjudicatedEvent({ wpCode: 'H2', accountCode: '1604' })).toBe(true)
    expect(isH2CipAdjudicatedEvent({ wp_code: 'H2', account_codes: ['1604'] })).toBe(true)
    expect(isH2CipAdjudicatedEvent({ wpCode: 'H4', accountCode: '1605' })).toBe(false)
  })

  it('从 cip 嵌套对象解析三栏', () => {
    const snap = parseH2CipFromAdjudicatedEvent({
      wpCode: 'H2',
      cip: { endBook: 200, endImpairment: 20, beginBook: 150, beginImpairment: 10 },
    })
    expect(snap?.endBook).toBe(200)
    expect(snap?.endNet).toBe(180)
    expect(snap?.beginNet).toBe(140)
  })

  it('从 snake_case 扁平字段解析', () => {
    const snap = parseH2CipFromAdjudicatedEvent({
      wp_code: 'H2',
      account_codes: ['1604'],
      end_audited: 100,
      begin_audited: 80,
      impair_audited: 5,
      begin_impair_audited: 2,
    })
    expect(snap?.endBook).toBe(100)
    expect(snap?.endImpairment).toBe(5)
    expect(snap?.beginImpairment).toBe(2)
  })

  it('仅有净值 auditedAmount、无 end_audited 时不解析（避免误作账面余额）', () => {
    expect(parseH2CipFromAdjudicatedEvent({
      wpCode: 'H2',
      accountCode: '1604',
      auditedAmount: 99,
    })).toBeNull()
  })

  it('sessionStorage 缓存读写', () => {
    const snap = buildH2CipSnapshot({
      endBook: 50,
      endImpairment: 5,
      beginBook: 40,
      beginImpairment: 4,
      projectId: pid,
    })
    cacheH2CipSnapshot(pid, snap)
    const read = readH2CipSnapshot(pid)
    expect(read?.endBook).toBe(50)
    expect(read?.beginNet).toBe(36)
  })
})

describe('h4DisclosureSyncPayload', () => {
  it('构建工程物资子表含小计与合计', () => {
    const mats = createDefaultH4ListedMaterials()
    mats[0].endBalance = 100
    mats[1].endBalance = 50
    mats[2].endBalance = 30
    mats[3].endBalance = 20
    const rows = buildH4ListedMaterialsSubTable(mats)
    expect(rows.some((r) => r.is_subtotal)).toBe(true)
    expect(rows[rows.length - 1]).toMatchObject({ label: '合计', end_balance: 160, is_total: true })
    const impair = rows.find((r) => r.label === '工程物资减值准备')
    expect(impair?.end_balance).toBe(-20)
  })

  it('sync payload 指向五、23 且含工程物资 key', () => {
    const mats = createDefaultH4ListedMaterials()
    mats[0].endBalance = 10
    const payloads = buildH4ListedSyncPayloads('wp-1', [], {
      materials: mats,
      noteText: '分类已核对',
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(H2_NOTE_SECTION.listed)
    expect(payloads[0].sub_table_data[H2_LISTED_SUBTABLE.materials]).toBeDefined()
    expect(payloads[0].sub_table_data._note_texts?.[0]).toMatchObject({
      section: 'h4-listed-materials',
    })
  })

  it('patch 汇总表工程物资行净值', () => {
    const mats = createDefaultH4ListedMaterials()
    mats[0].endBalance = 80
    mats[3].endBalance = 10
    const existing = {
      [H2_LISTED_SUBTABLE.summary]: [
        { label: '在建工程', end_balance: 200, prior_balance: 180 },
        { label: '工程物资', end_balance: 0, prior_balance: 0 },
        { label: '合计', end_balance: 200, prior_balance: 180, is_total: true },
      ],
    }
    const patched = patchListedSummaryMaterialsRow(existing, mats)
    const matRow = (patched[H2_LISTED_SUBTABLE.summary] as any[]).find((r) => r.label === '工程物资')
    expect(matRow.end_balance).toBe(70)
  })
})
