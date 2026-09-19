/**
 * K1 目录页 — 跨表勾稽汇总
 */
import type { Ref } from 'vue'
import { computed } from 'vue'
import { useK1CrossSheet } from './useK1CrossSheet'
import { computeK11ComboCrossCheck } from './k1AdjudicationCross'
import { K1_PORTFOLIO_ROW_DEFS } from './k1AdjudicationModel'

export interface K1CrossAlertItem {
  id: string
  severity: 'error' | 'warning' | 'info'
  title: string
  detail: string
  targetSheet: string
}

function num(map: Map<string, any>, key: string): number {
  const raw = map.get(key)?.remark ?? map.get(key)?.conclusion
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
}

export function useK1IndexCrossCheck(allResponses: Ref<Map<string, any>>) {
  const {
    adjudicationVsDetail,
    badDebtVsCalc,
    agingVsBalance,
    adjudicationVsK14,
  } = useK1CrossSheet(allResponses)

  const alerts = computed((): K1CrossAlertItem[] => {
    const map = allResponses.value
    const items: K1CrossAlertItem[] = []

    const vsDetail = adjudicationVsDetail.value
    if (!vsDetail.isMatch && (num(map, 'K1-1-audited-receivable') || num(map, 'K1-2-end-subtotal'))) {
      items.push({
        id: 'adj-vs-detail',
        severity: 'warning',
        title: 'K1-1 与 K1-2 未勾稽',
        detail: `审定原值与明细小计差异 ${vsDetail.diff.toLocaleString('zh-CN')}`,
        targetSheet: '审定表K1-1',
      })
    }

    const vsK14 = adjudicationVsK14.value
    if (!vsK14.isMatch && num(map, 'K1-4-adj-entries')) {
      items.push({
        id: 'adj-vs-k14',
        severity: 'warning',
        title: 'K1-1 与 K1-4 调整未勾稽',
        detail: `1221 AJE 差 ${vsK14.receivableAjeDiff.toLocaleString('zh-CN')}；1231 AJE 差 ${vsK14.badDebtAjeDiff.toLocaleString('zh-CN')}`,
        targetSheet: '审定表K1-1',
      })
    }

    const vsCalc = badDebtVsCalc.value
    if (!vsCalc.isMatch && (num(map, 'K1-3-bad-debt-end') || num(map, 'K1-8-calc-provision-total'))) {
      items.push({
        id: 'k13-vs-k18',
        severity: 'warning',
        title: 'K1-3 与 K1-8 坏账未勾稽',
        detail: `K1-3 期末 vs K1-8 应计提差异 ${vsCalc.diff.toLocaleString('zh-CN')}`,
        targetSheet: '坏账准备明细表K1-3',
      })
    }

    const vsAging = agingVsBalance.value
    if (!vsAging.isMatch && num(map, 'K1-2-end-subtotal')) {
      items.push({
        id: 'k12-aging',
        severity: 'info',
        title: 'K1-2 账龄与期末不一致',
        detail: `账龄合计与期末余额差异 ${vsAging.diff.toLocaleString('zh-CN')}`,
        targetSheet: '明细表K1-2',
      })
    }

    const labels = K1_PORTFOLIO_ROW_DEFS.map((d) => d.label)
    const combo = computeK11ComboCrossCheck(map, labels)
    if (combo.hasK18Data && !combo.isConsistent) {
      const parts: string[] = []
      if (combo.onlyInK16.length) parts.push(`仅 K1-6：${combo.onlyInK16.join('、')}`)
      if (combo.onlyInK18.length) parts.push(`仅 K1-8：${combo.onlyInK18.join('、')}`)
      items.push({
        id: 'combo-names',
        severity: 'warning',
        title: 'K1-6/K1-8 组合名称不一致',
        detail: parts.join('；') || '组合划分名称不匹配',
        targetSheet: '信用减值损失会计政策检查K1-6',
      })
    }

    const fsTotal = num(map, 'K1-1-fs-other-total')
    const k11Net = num(map, 'K1-1-audited-net')
    if (fsTotal > 0 && Math.abs(k11Net - fsTotal) >= 0.01) {
      items.push({
        id: 'fs-reconcile',
        severity: 'warning',
        title: 'K1-1 报表核对差异',
        detail: `其他应收款合计 ${fsTotal.toLocaleString('zh-CN')} vs 净值审定 ${k11Net.toLocaleString('zh-CN')}`,
        targetSheet: '审定表K1-1',
      })
    }

    const revTotal = num(map, 'K1-9-reversal-total')
    const woTotal = num(map, 'K1-9-writeoff-total')
    const k13Rev = num(map, 'K1-3-reversal-total')
    const k13Wo = num(map, 'K1-3-writeoff-total')
    if ((revTotal || k13Rev) && Math.abs(revTotal - k13Rev) >= 0.01) {
      items.push({
        id: 'k19-reversal',
        severity: 'warning',
        title: 'K1-9 转回与 K1-3 不一致',
        detail: `K1-9 转回合计 ${revTotal.toLocaleString('zh-CN')} vs K1-3 ${k13Rev.toLocaleString('zh-CN')}`,
        targetSheet: '坏账准备转回(收回)核销检查表K1-9',
      })
    }
    if ((woTotal || k13Wo) && Math.abs(woTotal - k13Wo) >= 0.01) {
      items.push({
        id: 'k19-writeoff',
        severity: 'warning',
        title: 'K1-9 核销与 K1-3 不一致',
        detail: `K1-9 核销合计 ${woTotal.toLocaleString('zh-CN')} vs K1-3 ${k13Wo.toLocaleString('zh-CN')}`,
        targetSheet: '坏账准备转回(收回)核销检查表K1-9',
      })
    }

    return items
  })

  const openCount = computed(() => alerts.value.filter((a) => a.severity !== 'info').length)

  return { alerts, openCount }
}
