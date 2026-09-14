import { describe, it, expect } from 'vitest'
import { normalizeTraceRow } from '../h3AdditionCheckModel'
import { normalizeTitleRow } from '../h3TitleRowModel'
import {
  matchTraceToTitleRow,
  findTraceRowsForTitle,
  isTitleCertTraceSource,
} from '../h3AdditionTitleLink'

describe('h3AdditionTitleLink', () => {
  const titles = [
    normalizeTitleRow({ rowId: 't1', assetName: '浦东写字楼A', titleCertNo: '沪房地浦字(2024)第001号', bookValue: 5000000 }),
    normalizeTitleRow({ rowId: 't2', assetName: '虹桥仓储中心', titleCertNo: '沪(2023)不动产权第888号', bookValue: 3000000 }),
  ]

  it('matches trace to title by cert number', () => {
    const tr = normalizeTraceRow({
      sourceType: '产权证',
      sourceRef: '沪房地浦字(2024)第001号',
      bookAssetName: '其他名称',
    })
    const hit = matchTraceToTitleRow(tr, titles)
    expect(hit?.rowId).toBe('t1')
  })

  it('matches trace to title by asset name', () => {
    const tr = normalizeTraceRow({
      sourceType: '合同',
      bookAssetName: '虹桥仓储中心',
      bookAmount: 3000000,
    })
    const hit = matchTraceToTitleRow(tr, titles)
    expect(hit?.rowId).toBe('t2')
  })

  it('uses persisted linkedTitleRowId first', () => {
    const tr = normalizeTraceRow({
      linkedTitleRowId: 't2',
      bookAssetName: '不匹配的名称',
    })
    expect(matchTraceToTitleRow(tr, titles)?.rowId).toBe('t2')
  })

  it('finds trace rows for title (reverse)', () => {
    const traces = [
      normalizeTraceRow({ rowId: 'tr1', bookAssetName: '浦东写字楼A' }),
      normalizeTraceRow({ rowId: 'tr2', sourceType: '产权证', sourceRef: '沪(2023)不动产权第888号' }),
    ]
    const hits = findTraceRowsForTitle(titles[1], traces)
    expect(hits.map((h) => h.rowId)).toContain('tr2')
  })

  it('detects title cert trace sources', () => {
    expect(isTitleCertTraceSource({ sourceType: '产权证', sourceRef: '' })).toBe(true)
    expect(isTitleCertTraceSource({ sourceType: '发票', sourceRef: 'INV-001' })).toBe(false)
  })
})
