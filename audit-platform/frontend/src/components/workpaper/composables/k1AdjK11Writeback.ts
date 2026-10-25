/**
 * k1AdjK11Writeback — K1-4 调整净额 → K1-1 组合行 AJE/RJE 分摊回写
 *
 * 可被 K1-4 保存自动触发，也可由 K1-1 手动/分块回写调用。
 */
import { readK14AdjustmentNets, type K14AdjustmentNets } from './useK1Adjustment'
import { calcSubtotal } from './useK1FormulaEngine'
import { K1_PORTFOLIO_COUNT } from './k1AdjudicationModel'

export type K14WritebackScope = 'all' | 'receivable' | 'baddebt'

export interface K14WritebackOptions {
  scope?: K14WritebackScope
  nets?: Partial<K14AdjustmentNets>
}

export interface K14WritebackResult {
  applied: boolean
  message: string
}

function num(map: Map<string, any>, itemId: string): number {
  const raw = map.get(itemId)?.remark
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
}

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

function allocateScalar(
  specs: { rowKey: string; weight: number }[],
  net: number,
): Map<string, number> {
  const out = new Map<string, number>()
  if (!specs.length) return out
  if (Math.abs(net) < 0.005) {
    for (const s of specs) out.set(s.rowKey, 0)
    return out
  }
  const weights = specs.map((s) => Math.abs(s.weight) || 0)
  const weightSum = calcSubtotal(weights)
  if (weightSum < 0.005) {
    const each = round2(net / specs.length)
    let allocated = 0
    specs.forEach((s, i) => {
      if (i === specs.length - 1) out.set(s.rowKey, round2(net - allocated))
      else {
        out.set(s.rowKey, each)
        allocated = round2(allocated + each)
      }
    })
    return out
  }
  let allocated = 0
  specs.forEach((s, i) => {
    if (i === specs.length - 1) {
      out.set(s.rowKey, round2(net - allocated))
    } else {
      const share = round2((net * weights[i]) / weightSum)
      out.set(s.rowKey, share)
      allocated = round2(allocated + share)
    }
  })
  return out
}

function writeField(
  map: Map<string, any>,
  onSave: ((itemId: string, value: any) => void) | undefined,
  block: 'receivable' | 'baddebt',
  rowKey: string,
  field: 'aje' | 'rje',
  amount: number,
): void {
  const itemId = `K1-1-${block}-${rowKey}-${field}`
  const val = String(round2(amount))
  map.set(itemId, { item_id: itemId, conclusion: null, remark: val })
  onSave?.(itemId, { remark: val })
}

function portfolioRowSpecs(
  map: Map<string, any>,
  block: 'receivable' | 'baddebt',
): { rowKey: string; weight: number }[] {
  const count = num(map, `K1-1-${block}-count`) || K1_PORTFOLIO_COUNT
  const specs: { rowKey: string; weight: number }[] = []
  for (let i = 0; i < count; i++) {
    specs.push({
      rowKey: `r${i}`,
      weight: num(map, `K1-1-${block}-r${i}-unadj`),
    })
  }
  return specs
}

function applyBlock(
  map: Map<string, any>,
  onSave: ((itemId: string, value: any) => void) | undefined,
  block: 'receivable' | 'baddebt',
  ajeNet: number,
  rjeNet: number,
): boolean {
  const specs = portfolioRowSpecs(map, block)
  if (!specs.length) return false
  const ajeMap = allocateScalar(specs, ajeNet)
  const rjeMap = allocateScalar(specs, rjeNet)
  for (const s of specs) {
    writeField(map, onSave, block, s.rowKey, 'aje', ajeMap.get(s.rowKey) ?? 0)
    writeField(map, onSave, block, s.rowKey, 'rje', rjeMap.get(s.rowKey) ?? 0)
  }
  return Math.abs(ajeNet) >= 0.005 || Math.abs(rjeNet) >= 0.005
}

/**
 * 将 K1-4 1221/1231 净额按未审数权重分摊至 K1-1 组合行 AJE/RJE。
 */
export function applyK14NetsToK11(
  allResponses: Map<string, any>,
  onSave?: (itemId: string, value: any) => void,
  options?: K14WritebackOptions,
): K14WritebackResult {
  const scope = options?.scope ?? 'all'
  const read = readK14AdjustmentNets(allResponses)
  const nets: K14AdjustmentNets = { ...read, ...options?.nets }

  const doRec = scope === 'all' || scope === 'receivable'
  const doBd = scope === 'all' || scope === 'baddebt'

  const hasRec = doRec && (Math.abs(nets.receivableAjeNet) >= 0.005 || Math.abs(nets.receivableRjeNet) >= 0.005)
  const hasBd = doBd && (Math.abs(nets.badDebtAjeNet) >= 0.005 || Math.abs(nets.badDebtRjeNet) >= 0.005)

  if (!hasRec && !hasBd) {
    const scopeLabel = scope === 'receivable' ? '1221' : scope === 'baddebt' ? '1231' : '1221/1231'
    return { applied: false, message: `K1-4 暂无 ${scopeLabel} 调整净额` }
  }

  let appliedRec = false
  let appliedBd = false
  if (hasRec) {
    appliedRec = applyBlock(
      allResponses,
      onSave,
      'receivable',
      nets.receivableAjeNet,
      nets.receivableRjeNet,
    )
  }
  if (hasBd) {
    appliedBd = applyBlock(
      allResponses,
      onSave,
      'baddebt',
      nets.badDebtAjeNet,
      nets.badDebtRjeNet,
    )
  }

  const fmt = (n: number) => n.toLocaleString('zh-CN')
  const parts: string[] = []
  if (appliedRec) {
    parts.push(`1221 AJE ${fmt(nets.receivableAjeNet)} / RJE ${fmt(nets.receivableRjeNet)}`)
  }
  if (appliedBd) {
    parts.push(`1231 AJE ${fmt(nets.badDebtAjeNet)} / RJE ${fmt(nets.badDebtRjeNet)}`)
  }

  return {
    applied: appliedRec || appliedBd,
    message: parts.length ? `已从 K1-4 回写：${parts.join('；')}` : 'K1-4 暂无可回写净额',
  }
}
