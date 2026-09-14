/**
 * H8 使用权资产披露内部勾稽校验（纯函数，国企五层派生；上市为列转置暂不做层间校验）
 *
 * 源模板国企五层结构（`h8SoeDisclosureModel.H8_SOE_LAYER_META`）：
 * 一、账面原值 → 二、累计折旧 → 三、账面净值（= 原值 − 折旧，`movementNa` 层）
 * → 四、减值准备 → 五、账面价值（= 净值 − 减值，`movementNa` 层）。
 * `recomputeDerivedLayers` 已在组件内做同款推导，此处只是把「推导值 == 组件展示值」
 * 显式列成勾稽项，便于审计追溯 UI 呈现。
 *
 * spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R5
 */
import { eqCheck, type WpCheckResult } from './shared/disclosureConsistency'
import { layerTotal, type H8SoeLayerBlock } from './h8SoeDisclosureModel'

export function buildH8SoeChecks(layers: readonly H8SoeLayerBlock[]): WpCheckResult[] {
  const byLayer = new Map(layers.map((l) => [l.layer, l]))
  const cost = byLayer.get('cost')
  const dep = byLayer.get('dep')
  const net = byLayer.get('net')
  const impair = byLayer.get('impair')
  const carrying = byLayer.get('carrying')
  if (!cost || !dep || !net || !impair || !carrying) return []

  const costTot = layerTotal(cost)
  const depTot = layerTotal(dep)
  const netTot = layerTotal(net)
  const impairTot = layerTotal(impair)
  const carryingTot = layerTotal(carrying)

  return [
    eqCheck(
      '三、使用权资产账面净值合计（期末）',
      '账面净值 = 账面原值 − 累计折旧（源模板层间派生，movementNa 层）',
      netTot.end,
      Math.round((costTot.end - depTot.end) * 100) / 100,
      ['Note:八、26'],
    ),
    eqCheck(
      '五、使用权资产账面价值合计（期末）',
      '账面价值 = 账面净值 − 减值准备（源模板层间派生，movementNa 层）',
      carryingTot.end,
      Math.round((netTot.end - impairTot.end) * 100) / 100,
      ['Note:八、26'],
    ),
    eqCheck(
      '一、账面原值合计 期末结转',
      '期末余额 = 期初余额 + 本期增加 − 本期减少',
      costTot.end,
      Math.round((costTot.begin + costTot.increase - costTot.decrease) * 100) / 100,
      ['wp:H8-2'],
    ),
    eqCheck(
      '二、累计折旧合计 期末结转',
      '期末余额 = 期初余额 + 本期增加 − 本期减少',
      depTot.end,
      Math.round((depTot.begin + depTot.increase - depTot.decrease) * 100) / 100,
      ['wp:H8-2'],
    ),
    eqCheck(
      '四、减值准备合计 期末结转',
      '期末余额 = 期初余额 + 本期增加 − 本期减少',
      impairTot.end,
      Math.round((impairTot.begin + impairTot.increase - impairTot.decrease) * 100) / 100,
      ['wp:H8-10'],
    ),
  ]
}
