/**
 * H1-17 title-check helpers — import / expiry / disclosure merge
 */
import { describe, expect, it } from 'vitest'
import {
  isTransportCategory,
  isInspectionExpiredBeforePeriodEnd,
  mapDetailSeedToVehicleRow,
  mapMortgagedVehiclesToDisclosureRows,
  mergeRestrictedDisclosureRows,
  getTransportDetailSeeds,
  type VehicleRow,
} from '../useH1TitleCheck'

function veh(partial: Partial<VehicleRow>): VehicleRow {
  return {
    rowId: partial.rowId ?? 'v1',
    seq: partial.seq ?? 1,
    assetCode: partial.assetCode ?? '',
    name: partial.name ?? '',
    plateNo: partial.plateNo ?? '',
    vinNo: partial.vinNo ?? '',
    engineNo: '',
    drivingLicenseNo: '',
    regCertNo: '',
    regDate: '',
    regRemarks: '',
    owner: '',
    isOwnerEntity: 'Y',
    useNature: '',
    isMortgaged: partial.isMortgaged ?? 'N',
    mortgageAmount: partial.mortgageAmount ?? 0,
    mortgageNature: partial.mortgageNature ?? '',
    bookValue: partial.bookValue ?? 0,
    regValue: 0,
    difference: 0,
    inspectionExpiry: partial.inspectionExpiry ?? '',
    inspectionStatus: partial.inspectionStatus ?? '',
    checkConclusion: '',
    conclusion: '',
    remark: partial.remark ?? '',
  }
}

describe('isTransportCategory', () => {
  it('matches 运输设备 variants', () => {
    expect(isTransportCategory('运输设备')).toBe(true)
    expect(isTransportCategory('交通运输设备')).toBe(true)
    expect(isTransportCategory('车辆')).toBe(true)
    expect(isTransportCategory('房屋及建筑物')).toBe(false)
    expect(isTransportCategory('')).toBe(false)
  })
})

describe('isInspectionExpiredBeforePeriodEnd', () => {
  it('marks expiry strictly before period end', () => {
    expect(isInspectionExpiredBeforePeriodEnd('2025-12-30', '2025-12-31')).toBe(true)
    expect(isInspectionExpiredBeforePeriodEnd('2025-12-31', '2025-12-31')).toBe(false)
    expect(isInspectionExpiredBeforePeriodEnd('2026-01-01', '2025-12-31')).toBe(false)
    expect(isInspectionExpiredBeforePeriodEnd('', '2025-12-31')).toBe(false)
    expect(isInspectionExpiredBeforePeriodEnd('2025-06-01', '')).toBe(false)
  })
})

describe('mapDetailSeedToVehicleRow', () => {
  it('maps H1-2 cost end to bookValue and tags source', () => {
    const row = mapDetailSeedToVehicleRow(
      { rowId: 'd1', assetNo: 'TR-01', name: '货车A', originalCostEnd: 120000, category: '运输设备' },
      1,
    )
    expect(row.assetCode).toBe('TR-01')
    expect(row.name).toBe('货车A')
    expect(row.bookValue).toBe(120000)
    expect(row.remark).toBe('来源:H1-2')
  })
})

describe('getTransportDetailSeeds', () => {
  it('filters only transport categories from H1-2-rows', () => {
    const map = new Map<string, any>([
      ['H1-2-rows', {
        remark: JSON.stringify([
          { category: '房屋及建筑物', name: '厂房', assetNo: 'B1' },
          { category: '运输设备', name: '轿车', assetNo: 'T1', originalCostEnd: 80000 },
          { category: '机器设备', name: '机床', assetNo: 'M1' },
        ]),
      }],
    ])
    const seeds = getTransportDetailSeeds(map)
    expect(seeds).toHaveLength(1)
    expect(seeds[0].assetNo).toBe('T1')
  })
})

describe('disclosure mortgage merge', () => {
  it('maps mortgaged vehicles and merges without dropping other sources', () => {
    const from = mapMortgagedVehiclesToDisclosureRows([
      veh({ rowId: 'a', name: '货车', isMortgaged: 'Y', mortgageAmount: 50000, plateNo: '粤A123' }),
      veh({ rowId: 'b', name: '自用车', isMortgaged: 'N', bookValue: 10000 }),
    ])
    expect(from).toHaveLength(1)
    expect(from[0].remark).toBe('来源:H1-17')
    expect(from[0].amount).toBe(50000)

    const merged = mergeRestrictedDisclosureRows(
      [
        { rowId: 'old-h16', name: '厂房抵押', amount: 1e6, remark: '来源:H1-16' },
        { rowId: 'old-h117', name: '旧车', amount: 1, remark: '来源:H1-17' },
      ],
      from,
      '来源:H1-17',
    )
    expect(merged.map((r) => r.rowId)).toEqual(['old-h16', 'disc-h117-a'])
  })
})
