/**
 * I 类通用溯源配置（六循环共用）。
 *
 * 提供各循环的 `grossLabel` / `provisionLabel` / `hints` / `fallbackRowCode`
 * 供 `WpFourTableSourcePanel` 使用。
 *
 * spec: .kiro/specs/i-cycle-four-table-extraction-and-disclosure-alignment/ Wave 3.3
 */
import type { TbSourceCodes } from './shared/tbSourceCodes'

interface ICycleSourceConfig {
  grossLabel: string
  provisionLabel: string // 空串 = 不显示备抵行
  fallbackRowCode: string
  hints: string[]
}

const CONFIGS: Record<string, ICycleSourceConfig> = {
  I1: {
    grossLabel: '无形资产原值（1701）',
    provisionLabel: '累计摊销（1702）+ 减值准备（1703）',
    fallbackRowCode: 'BS-033',
    hints: [
      '三段结构：原值(1701) − 累计摊销(1702) − 减值准备(1703) = 账面价值',
      '报表公式：<code>TB(\'1701\') − TB(\'1702\')</code>（未减 1703，减值段走段兜底码）',
    ],
  },
  I2: {
    grossLabel: '开发支出（1704）',
    provisionLabel: '',
    fallbackRowCode: 'BS-035',
    hints: ['科目码 1704（account_chart 实证）；report_config 写 1703 有误，已走兜底码'],
  },
  I3: {
    grossLabel: '商誉（1711）',
    provisionLabel: '',
    fallbackRowCode: 'BS-037',
    hints: ['商誉减值准备在 account_chart 中无标准科目，该段留空'],
  },
  I4: {
    grossLabel: '长期待摊费用（1801）',
    provisionLabel: '',
    fallbackRowCode: 'BS-038',
    hints: [],
  },
  I5: {
    grossLabel: '其他非流动资产',
    provisionLabel: '',
    fallbackRowCode: 'BS-040',
    hints: [
      '本项目无标准科目映射（report_config formula 为 None），需手工编制',
      '溯源面板显示的码来自项目级自定义（若有）',
    ],
  },
  I6: {
    grossLabel: '研发费用（6604）',
    provisionLabel: '',
    fallbackRowCode: 'IS-006',
    hints: [
      '损益类：取本期发生额（trial_balance 优先，tb_balance 借方回退）',
      '禁用 debit−credit —— 含年末结转损益时恒为 0',
    ],
  },
}

export function getICycleSourceConfig(wpCode: string): ICycleSourceConfig {
  return CONFIGS[wpCode.toUpperCase()] || CONFIGS.I4
}

export function extractTbSourceCodes(htmlData?: Record<string, unknown> | null): TbSourceCodes | null {
  if (!htmlData) return null
  const src = (htmlData as any).tb_source_codes
  return src && typeof src === 'object' ? src as TbSourceCodes : null
}
