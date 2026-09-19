/**
 * I 类通用溯源配置（六循环共用）。
 *
 * 提供各循环的 `grossLabel` / `provisionLabel` / `hints` / `fallbackRowCode`
 * 供 `WpFourTableSourcePanel` 使用。
 *
 * 🔴 **`fallbackRowCode` 不在本文件写字面量** —— 它由 `iCycleAccountScope.ts` 的
 * `iCycleRowCode()` 派生（该模块与后端 `i_cycle_accounts.I_CYCLE_ROW_CODES`
 * 由 `iCycleAccountScope.spec.ts` 逐项交叉锁死）。
 *
 * 改造前本文件写死了**第三份**行编码副本，且 6 个里 5 个是错位旧值
 * （I1 `BS-033` 实为 I2 的行 / I2 `BS-035` 实为 I4 / I3 `BS-037` 实为 I5 /
 * I4 `BS-038` 是非流动资产合计派生行 / I5 `BS-040` 是「流动负债：」节标题），
 * 而该值直接渲染进溯源面板的「报表行 X」tag（`src.row_code || fallbackRowCode`）
 * ⇒ render 未下发 row_code 时，审计人员看到的报表行溯源是错的。
 *
 * spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/ Task 17
 *       Requirements 1.1 / 9.1（原 i-cycle-four-table-extraction-and-disclosure-alignment Wave 3.3）
 */
import type { TbSourceCodes } from './shared/tbSourceCodes'
import { iCycleRowCode } from './iCycleAccountScope'

interface ICycleSourceConfig {
  grossLabel: string
  provisionLabel: string // 空串 = 不显示备抵行
  fallbackRowCode: string
  hints: string[]
}

/** 展示层文案（行编码不在此声明，见文件头注释） */
type ICycleSourceLabels = Omit<ICycleSourceConfig, 'fallbackRowCode'>

const CONFIGS: Record<string, ICycleSourceLabels> = {
  I1: {
    grossLabel: '无形资产原值（1701）',
    provisionLabel: '累计摊销（1702）+ 减值准备（1703）',
    hints: [
      '三段结构：原值(1701) − 累计摊销(1702) − 减值准备(1703) = 账面价值',
      '报表公式：<code>TB(\'1701\') − TB(\'1702\')</code>（未减 1703，减值段走段兜底码）',
    ],
  },
  I2: {
    grossLabel: '开发支出（1704）',
    provisionLabel: '',
    hints: ['科目码 1704（account_chart 实证）；report_config 写 1703 有误，已走兜底码'],
  },
  I3: {
    grossLabel: '商誉（1711）',
    provisionLabel: '',
    hints: ['商誉减值准备在 account_chart 中无标准科目，该段留空'],
  },
  I4: {
    grossLabel: '长期待摊费用（1801）',
    provisionLabel: '',
    hints: [],
  },
  I5: {
    grossLabel: '其他非流动资产',
    provisionLabel: '',
    hints: [
      '本项目无标准科目映射（report_config formula 为 None），需手工编制',
      '溯源面板显示的码来自项目级自定义（若有）',
    ],
  },
  I6: {
    grossLabel: '研发费用（6604）',
    provisionLabel: '',
    hints: [
      '损益类：取本期发生额（trial_balance 优先，tb_balance 借方回退）',
      '禁用 debit−credit —— 含年末结转损益时恒为 0',
    ],
  },
}

/**
 * 溯源面板配置。
 *
 * @param wpCode I1~I6；未知值退回 I4 文案（与改造前同行为）
 * @param standards 项目适用准则集。I 类四准则同码，故通常可省；保留该维度以免
 *   后续准则分化时又在消费方写死。
 */
export function getICycleSourceConfig(
  wpCode: string,
  standards?: readonly string[] | null,
): ICycleSourceConfig {
  const raw = String(wpCode || '').toUpperCase()
  // 🔴 文案与行编码必须由**同一个** effective key 派生，否则未知 wp_code 时会出现
  //    「I4 文案 + 别的循环行编码」这种自相矛盾的溯源展示。
  const key = raw in CONFIGS ? raw : 'I4'
  return { ...CONFIGS[key], fallbackRowCode: iCycleRowCode(key, standards) }
}

export function extractTbSourceCodes(htmlData?: Record<string, unknown> | null): TbSourceCodes | null {
  if (!htmlData) return null
  const src = (htmlData as any).tb_source_codes
  return src && typeof src === 'object' ? src as TbSourceCodes : null
}
