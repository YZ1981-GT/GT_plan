/**
 * G 循环（投资与金融工具）科目定位 —— **前端单一真源**，与后端
 * `app/services/four_table/g_cycle_specs.py` 逐字对称。
 *
 * 改一侧必改另一侧；守卫 `__tests__/gCycleAccountScope.spec.ts` 交叉锁死两侧
 * 的槽键、报表行号与兜底码。
 *
 * 🔴 **科目码不是权威真源**，运行态一律取 render 下发的 `tb_source_codes`。
 * 这里的兜底码只在「render 未下发」时兜住界面 —— 因为标准码在项目间并不一致：
 * `account_mapping` 实证同一原始码 `1525` 在 1 个项目映射到 `1521`（并入母科目）、
 * 在 4 个项目映射到 `1525`（独立）；平台标准科目表本身 10 个项目分三档
 * （4 个有 `1519` / 2 个只到 `1507` / 4 个完全没有这一族）。
 *
 * 🔴 **`report_config` 有 4 行错码**（`account_chart` + `trial_balance.account_name` 双证）：
 * `BS-022`→`1505`(债权投资减值准备) / `BS-025`→`1506`(其他债权投资) /
 * `BS-026`→`1507`(其他权益工具投资) 连续偏移一位；`IS-016` 与 `IS-017` 整整互换
 * （铁证：同库 `CFSS-003 = TB('6701')` / `CFSS-004 = TB('6702')` 是对的）。
 * 故这里的兜底码取**实证真值**（1506 / 1507 / 1519 / 6702），与报表公式不一致时
 * 后端会在 `tb_source_codes.conflicts` 暴露，溯源面板渲染橙色告警。
 *
 * spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/ Requirements 3
 */
import {
  type CycleAccountScope,
  type CycleAccountScopeSpec,
  createCycleAccountScope,
} from './shared/cycleAccountScope'

/** 损益类 G 循环 —— 取数口径是**本期发生额**，不是期初 / 期末余额 */
export const G_PL_CYCLES: ReadonlySet<string> = new Set(['G11', 'G12', 'G13', 'G14'])

const SPECS: readonly CycleAccountScopeSpec[] = [
  {
    cycle: 'G1',
    reportRowCode: 'BS-003',
    slots: [
      { key: 'gross', label: '交易性金融资产', fallback: '1101' },
      // 🔴 无兜底码：`1102 衍生金融资产` 实证任何项目科目表都没有
      { key: 'derivative', label: '衍生金融资产' },
    ],
  },
  {
    // 🔴 `report_config` 无独立报表行：`BS-015` 是「流动资产合计」（ROW 派生行），
    //    `BS-009 其他应收款` 的公式含 `1131` 应收股利但**不含** `1132` 应收利息。
    cycle: 'G2',
    reportRowCode: null,
    slots: [{ key: 'gross', label: '应收利息', fallback: '1132' }],
  },
  {
    // soe 侧 `BS-016` 是「其中：应收股利」但 formula 为 None；listed 侧该行是
    // 「一年内到期的非流动资产」→ 同样不认领。
    cycle: 'G3',
    reportRowCode: null,
    slots: [{ key: 'gross', label: '应收股利', fallback: '1131' }],
  },
  {
    cycle: 'G4',
    reportRowCode: 'BS-021',
    slots: [
      { key: 'gross', label: '债权投资', fallback: '1504' },
      {
        key: 'provision',
        label: '债权投资减值准备',
        fallback: '1505',
        isProvision: true,
      },
    ],
  },
  {
    cycle: 'G5',
    reportRowCode: 'BS-023',
    slots: [{ key: 'gross', label: '长期应收款', fallback: '1531' }],
  },
  {
    // 真值 1506（report_config 的 BS-022 写 1505 = 债权投资减值准备）。
    // 无备抵槽：CAS22 FVOCI-Debt 减值在 OCI 确认，不冲减账面价值。
    cycle: 'G6',
    reportRowCode: 'BS-022',
    slots: [{ key: 'gross', label: '其他债权投资', fallback: '1506' }],
  },
  {
    cycle: 'G7',
    reportRowCode: 'BS-024',
    slots: [
      { key: 'gross', label: '长期股权投资', fallback: '1511' },
      {
        key: 'provision',
        label: '长期股权投资减值准备',
        fallback: '1512',
        isProvision: true,
      },
    ],
  },
  {
    // 真值 1507（BS-025 写 1506 = 其他债权投资）
    cycle: 'G8',
    reportRowCode: 'BS-025',
    slots: [{ key: 'gross', label: '其他权益工具投资', fallback: '1507' }],
  },
  {
    // 真值 1519（BS-026 写 1507 = 其他权益工具投资）；`1519` 只在 4 个项目科目表里
    cycle: 'G9',
    reportRowCode: 'BS-026',
    slots: [{ key: 'gross', label: '其他非流动金融资产', fallback: '1519' }],
  },
  {
    cycle: 'G10',
    reportRowCode: 'BS-042',
    slots: [
      { key: 'gross', label: '交易性金融负债', fallback: '2101' },
      // 🔴 无兜底码：实证无「衍生金融负债」科目（`2102` 是短期应付债券）
      { key: 'derivative', label: '衍生金融负债' },
    ],
  },
  {
    cycle: 'G11',
    reportRowCode: 'IS-011',
    slots: [{ key: 'gross', label: '投资收益', fallback: '6111' }],
  },
  {
    // `IS-014` formula 为 None → 走名称 / 兜底。公式预设曾错写 `6115`（资产处置损益）
    cycle: 'G12',
    reportRowCode: 'IS-014',
    slots: [{ key: 'gross', label: '净敞口套期收益', fallback: '6103' }],
  },
  {
    cycle: 'G13',
    reportRowCode: 'IS-015',
    slots: [{ key: 'gross', label: '公允价值变动损益', fallback: '6101' }],
  },
  {
    // 真值 6702（IS-016 写 6701 = 资产减值损失，与 IS-017 互换）
    cycle: 'G14',
    reportRowCode: 'IS-016',
    slots: [{ key: 'gross', label: '信用减值损失', fallback: '6702' }],
  },
]

/** wp_code → 科目视图 */
export const G_CYCLE_SCOPES: Readonly<Record<string, CycleAccountScope>> =
  Object.freeze(
    SPECS.reduce<Record<string, CycleAccountScope>>((acc, spec) => {
      acc[spec.cycle] = createCycleAccountScope(spec)
      return acc
    }, {}),
  )

/** 按 wp_code 取科目视图（大小写不敏感；未登记返 `null`） */
export function gCycleScope(wpCode: string): CycleAccountScope | null {
  return G_CYCLE_SCOPES[String(wpCode || '').trim().toUpperCase()] || null
}

/** 该循环取数口径是否为本期发生额（损益类） */
export function isGPlCycle(wpCode: string): boolean {
  return G_PL_CYCLES.has(String(wpCode || '').trim().toUpperCase())
}

/** 取数口径中文名（溯源面板展示） */
export function gCycleBasisLabel(wpCode: string): string {
  return isGPlCycle(wpCode) ? '本期发生额' : '期末余额'
}
