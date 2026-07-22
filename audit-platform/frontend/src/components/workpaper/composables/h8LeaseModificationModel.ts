/**
 * h8LeaseModificationModel — H8-7 纯函数：校验、H8-2 映射、回写草稿
 */
import { isSeparateLease, type H8YesNo } from './useH8CAS21Engine'

export interface H8ModValidationIssue {
  level: 'error' | 'warning' | 'info'
  code: string
  message: string
}

/** 校验所需的最小行形状（避免与 composable 循环依赖） */
export interface H8ModValidationInput {
  contractNo: string
  modificationDate: string
  modificationType: string
  expandsScope: H8YesNo
  standalonePrice: H8YesNo
  scopeReduction: H8YesNo
  carryingLiability: number
  carryingROU: number
  newLiabilityPV: number
  remainingPeriods: number
  reductionRatio: number
  rouAmortYears: number
}

/** 从 H8-2 明细行抽取可带入字段 */
export interface H82ContractSeed {
  contractNo: string
  assetName: string
  startDate: string
  endDate: string
  netValue: number
  h9InitialAmount: number
  initialAmount: number
  modificationAmount: number
}

export function mapH82ToSeeds(rawRows: any[]): H82ContractSeed[] {
  if (!Array.isArray(rawRows)) return []
  return rawRows
    .filter(r => String(r?.contractNo ?? '').trim())
    .map(r => {
      const h9 = Number(r.h9InitialAmount) || 0
      const dc = Number(r.directCost) || 0
      const inc = Number(r.incentive) || 0
      const cas21 = h9 + dc - inc
      const initialAmount =
        Number(r.initialAmount)
        || Number(r.costEndAud)
        || cas21
      const accDepEnd =
        Number(r.accDepEnd)
        || Number(r.depEndAud)
        || ((Number(r.accDepBegin) || Number(r.depBeginUnadj) || 0)
          + (Number(r.depCurrentPeriod) || Number(r.depProvUnadj) || 0))
      const netValue =
        Number(r.netValue)
        || Number(r.netEndAud)
        || (initialAmount - accDepEnd - (Number(r.impairEndAud) || 0))
      return {
        contractNo: String(r.contractNo).trim(),
        assetName: String(r.assetName ?? ''),
        startDate: String(r.startDate ?? ''),
        endDate: String(r.endDate ?? ''),
        netValue,
        h9InitialAmount: h9,
        initialAmount,
        modificationAmount: Number(r.modificationAmount) || 0,
      }
    })
}

/** 估算起租日至变更日已过年数 */
export function yearsBetween(startDate: string, modificationDate: string): number {
  if (!startDate || !modificationDate) return 0
  const a = Date.parse(startDate)
  const b = Date.parse(modificationDate)
  if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return 0
  return (b - a) / (365.25 * 24 * 3600 * 1000)
}

export function validateModificationRow(
  row: H8ModValidationInput,
  h82EndDate?: string,
): H8ModValidationIssue[] {
  const issues: H8ModValidationIssue[] = []

  if (!row.contractNo?.trim()) {
    issues.push({ level: 'warning', code: 'no-contract', message: '未填写合同号' })
  }
  if (!row.modificationDate) {
    issues.push({ level: 'warning', code: 'no-mod-date', message: '未填写变更日期' })
  }
  if (!row.modificationType) {
    issues.push({ level: 'info', code: 'no-type', message: '请完成判定树以确定变更类型' })
  }

  if (isSeparateLease(row.expandsScope, row.standalonePrice) && row.scopeReduction === '是') {
    issues.push({
      level: 'error',
      code: 'mutex',
      message: '1.1 单独租赁与 1.2 范围减少不可同时适用',
    })
  }

  if (row.modificationType === '其他变更') {
    if (!(row.carryingLiability > 0) && !(row.carryingROU > 0)) {
      issues.push({
        level: 'warning',
        code: 'no-carrying',
        message: '其他变更建议录入变更日账面负债/ROU（可从 H8-2/H8-6 带入）',
      })
    }
    if (!(row.newLiabilityPV > 0) && !(row.remainingPeriods > 0)) {
      issues.push({
        level: 'warning',
        code: 'no-new-pv',
        message: '其他变更需录入变更后负债现值，或填写剩余付款测算',
      })
    }
  }

  if (row.modificationType === '范围减少') {
    if (!(row.reductionRatio > 0 && row.reductionRatio <= 1)) {
      issues.push({
        level: 'warning',
        code: 'no-ratio',
        message: '范围减少请填写终止比例（0–100%）',
      })
    }
  }

  if (row.remainingPeriods > 0 && row.rouAmortYears > 0
    && Math.abs(row.remainingPeriods - row.rouAmortYears) >= 2) {
    issues.push({
      level: 'info',
      code: 'amort-mismatch',
      message: `剩余付款期(${row.remainingPeriods})与ROU摊销期(${row.rouAmortYears})差异较大，请核对`,
    })
  }

  if (row.modificationDate && h82EndDate) {
    const mod = Date.parse(row.modificationDate)
    const end = Date.parse(h82EndDate)
    if (Number.isFinite(mod) && Number.isFinite(end) && mod > end) {
      issues.push({
        level: 'info',
        code: 'after-end',
        message: '变更日晚于 H8-2 原合同到期日，请确认是否为续租/展期类变更',
      })
    }
  }

  return issues
}

/** 生成回写 H8-2 的 modificationAmount 补丁 */
export function buildH82ModificationPatch(
  modRows: Array<{ contractNo: string; adjustmentAmount: number; modificationType: string; modificationDate: string }>,
  h82Rows: any[],
): { contractNo: string; modificationAmount: number; remarkAppend: string }[] {
  if (!Array.isArray(h82Rows)) return []
  const byContract = new Map<string, { adjustmentAmount: number; modificationType: string; modificationDate: string }>()
  for (const r of modRows) {
    const k = r.contractNo?.trim()
    if (!k) continue
    const prev = byContract.get(k)
    if (!prev) {
      byContract.set(k, {
        adjustmentAmount: r.adjustmentAmount || 0,
        modificationType: r.modificationType,
        modificationDate: r.modificationDate,
      })
    } else {
      byContract.set(k, {
        ...prev,
        adjustmentAmount: (prev.adjustmentAmount || 0) + (r.adjustmentAmount || 0),
      })
    }
  }
  const patches: { contractNo: string; modificationAmount: number; remarkAppend: string }[] = []
  for (const [contractNo, mod] of byContract) {
    if (!h82Rows.some(r => String(r.contractNo ?? '').trim() === contractNo)) continue
    patches.push({
      contractNo,
      modificationAmount: mod.adjustmentAmount || 0,
      remarkAppend: `H8-7变更(${mod.modificationType || '未分类型'}) ${mod.modificationDate || ''}`.trim(),
    })
  }
  return patches
}

/** 单独租赁 → 拟新增 H8-2 行草稿 */
export function buildSeparateLeaseH82Draft(row: {
  modificationType: string
  contractNo: string
  assetName: string
  modificationDate: string
  newLiabilityPV: number
  modificationDesc: string
  newTerms: string
}): Record<string, any> | null {
  if (row.modificationType !== '单独租赁') return null
  const base = row.contractNo?.trim() || 'NEW'
  return {
    contractNo: `${base}-SEP`,
    assetName: row.assetName || '',
    startDate: row.modificationDate || '',
    endDate: '',
    h9InitialAmount: row.newLiabilityPV || 0,
    directCost: 0,
    incentive: 0,
    modificationAmount: 0,
    remark: `来源:H8-7单独租赁/${row.contractNo || ''} ${row.modificationDesc || row.newTerms || ''}`.trim(),
  }
}

export function appendRemark(existing: string, append: string): string {
  const a = (append || '').trim()
  if (!a) return existing || ''
  const e = (existing || '').trim()
  if (!e) return a
  if (e.includes(a)) return e
  return `${e}；${a}`
}
