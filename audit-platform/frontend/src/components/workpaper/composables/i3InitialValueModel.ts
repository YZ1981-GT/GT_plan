/**
 * i3InitialValueModel — I3-4 入账价值测算纯函数（CAS20）
 */
import { calcInitialGoodwill } from './useI3FormulaEngine'

export interface I3InitialValueRow {
  rowId: string
  projectName: string
  bookedAmount: number
  sameControl: '' | '是' | '否'
  acquisitionDate: string
  dateCompliant: '' | '是' | '否' | '待确认'
  mergerCost: number
  netAssetFV: number
  /** 股权比例，界面用百分数 0–100 */
  equityRatio: number
  goodwillCompliant: '' | '是' | '否' | '不适用' | '待确认'
  remark: string
}

export function newI34RowId(): string {
  return `i34-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function emptyI3InitialValueRow(partial?: Partial<I3InitialValueRow>): I3InitialValueRow {
  return {
    rowId: partial?.rowId || newI34RowId(),
    projectName: partial?.projectName || '',
    bookedAmount: partial?.bookedAmount ?? 0,
    sameControl: partial?.sameControl ?? '否',
    acquisitionDate: partial?.acquisitionDate || '',
    dateCompliant: partial?.dateCompliant || '',
    mergerCost: partial?.mergerCost ?? 0,
    netAssetFV: partial?.netAssetFV ?? 0,
    equityRatio: partial?.equityRatio ?? 100,
    goodwillCompliant: partial?.goodwillCompliant || '',
    remark: partial?.remark || '',
  }
}

export function calcI34Share(row: I3InitialValueRow): number {
  if (row.sameControl === '是') return 0
  return (Number(row.netAssetFV) || 0) * ((Number(row.equityRatio) || 0) / 100)
}

export function calcI34Goodwill(row: I3InitialValueRow): number {
  if (row.sameControl === '是') return 0
  return calcInitialGoodwill(Number(row.mergerCost) || 0, calcI34Share(row))
}

export function normalizeI3InitialValueRow(raw: any): I3InitialValueRow {
  const ratioRaw = Number(raw?.equityRatio)
  let equityRatio = 100
  if (Number.isFinite(ratioRaw) && ratioRaw > 0) {
    equityRatio = ratioRaw <= 1 ? ratioRaw * 100 : ratioRaw
  }
  return emptyI3InitialValueRow({
    rowId: String(raw?.rowId || newI34RowId()),
    projectName: String(raw?.projectName || raw?.investee || ''),
    bookedAmount: Number(raw?.bookedAmount ?? raw?.goodwillAmount) || 0,
    sameControl: (raw?.sameControl === '是' || raw?.sameControl === '否') ? raw.sameControl : '否',
    acquisitionDate: String(raw?.acquisitionDate || ''),
    dateCompliant: raw?.dateCompliant || '',
    mergerCost: Number(raw?.mergerCost) || 0,
    netAssetFV: Number(raw?.netAssetFV ?? raw?.netAssetFairValue) || 0,
    equityRatio,
    goodwillCompliant: raw?.goodwillCompliant || '',
    remark: String(raw?.remark || ''),
  })
}

export function buildI34GateWarnings(rows: I3InitialValueRow[]): string[] {
  const list: string[] = []
  for (const r of rows) {
    const name = r.projectName || '未命名项目'
    if (r.sameControl === '是' && (Number(r.bookedAmount) || 0) !== 0) {
      list.push(`「${name}」属同一控制，入账金额应为 0（不应确认商誉）。`)
    }
    if (r.sameControl === '否' || r.sameControl === '') {
      const gw = calcI34Goodwill(r)
      if (gw < -0.005) {
        list.push(`「${name}」⑤商誉为负（负商誉），应计入当期损益并复核评估公允性。`)
      }
      const booked = Number(r.bookedAmount) || 0
      if (Math.abs(booked - gw) >= 0.01 && (booked !== 0 || gw !== 0)) {
        list.push(`「${name}」入账金额(${booked})与⑤商誉(${gw})不一致。`)
      }
      if (r.dateCompliant === '否') {
        list.push(`「${name}」购买日判定为不符合规定，须跟进。`)
      }
      if (r.goodwillCompliant === '否') {
        list.push(`「${name}」商誉确定判定为不符合规定，须跟进。`)
      }
    }
  }
  return list
}

/** 跨表 I3-4-rows / I3-2 入账联动载荷 */
export function toI34CrossSheetPayload(rows: I3InitialValueRow[]) {
  return rows.map((r) => ({
    rowId: r.rowId,
    investee: r.projectName,
    projectName: r.projectName,
    bookedAmount: Number(r.bookedAmount) || 0,
    sameControl: r.sameControl,
    acquisitionDate: r.acquisitionDate,
    dateCompliant: r.dateCompliant,
    mergerCost: Number(r.mergerCost) || 0,
    netAssetFairValue: calcI34Share(r),
    netAssetFV: Number(r.netAssetFV) || 0,
    equityRatio: Number(r.equityRatio) || 0,
    goodwillAmount: calcI34Goodwill(r),
    goodwillCompliant: r.goodwillCompliant,
    remark: r.remark,
  }))
}

export function summarizeI34(rows: I3InitialValueRow[]) {
  let bookedAmount = 0
  let mergerCost = 0
  let netAssetFV = 0
  let share = 0
  let goodwill = 0
  for (const r of rows) {
    bookedAmount += Number(r.bookedAmount) || 0
    if (r.sameControl !== '是') {
      mergerCost += Number(r.mergerCost) || 0
      netAssetFV += Number(r.netAssetFV) || 0
      share += calcI34Share(r)
      goodwill += calcI34Goodwill(r)
    }
  }
  return { bookedAmount, mergerCost, netAssetFV, share, goodwill }
}
