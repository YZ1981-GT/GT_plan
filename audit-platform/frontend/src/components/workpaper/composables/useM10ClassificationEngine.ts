/**
 * useM10ClassificationEngine — M10 负债权益区分引擎（CAS37）
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 实现CAS37《金融工具列报》核心分类判定逻辑。
 *
 * ─── CAS37 负债权益区分铁律 ───
 * 永续债/优先股等金融工具需按CAS37判定分类：
 * - 发行方是否存在交付现金/其他金融资产的合同义务
 * - 无合同义务 → 权益工具（计入M10科目4003）
 * - 有合同义务 → 金融负债（计入负债科目）
 *
 * 复合金融工具可拆分为权益部分+负债部分，
 * 两者之和必须等于工具总额（金额守恒）。
 * ──────────────────────────────────────
 *
 * 判定维度（来自M10-4检查表64×8）：
 * - 本金相关：存续期限/回购赎回条件
 * - 股利/利息：强制付息事件/递延取消
 * - 或有结算：违约/应急/约束条款
 * - 转股特征：转股条件/价格/调整
 * - 清算偿付顺序
 * - 最终判定：权益工具 or 金融负债
 *
 * 本引擎覆盖：
 * - P3: CAS37分类判定（有合同义务→liability，无→equity）
 * - P4: 金额拆分（负债部分 = 总额 - 权益部分）
 * - P5: 分类金额守恒（权益 + 负债 === 总额）
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/ Task 2.2
 * Requirements: 4.2-4.3, 6.1-6.3
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P3: CAS37 分类判定 ─────────────────────────────────────

/**
 * 判定金融工具分类（Property P3）
 *
 * CAS37《金融工具列报》核心判定规则：
 * - 发行方存在交付现金/其他金融资产的合同义务 → 金融负债
 * - 发行方无上述合同义务 → 权益工具
 *
 * 典型场景：
 * - 永续债无到期日且可无条件递延利息 → 无合同义务 → equity
 * - 优先股有强制赎回条款 → 有合同义务 → liability
 * - 可转债权益成分（不含交付义务部分）→ equity
 *
 * @param hasContractualObligation - 是否存在交付现金/金融资产的合同义务
 * @returns 分类结论：'equity'（权益工具）或 'liability'（金融负债）
 */
export function classifyInstrument(hasContractualObligation: boolean): 'equity' | 'liability' {
  return hasContractualObligation ? 'liability' : 'equity'
}

// ─── P4: 金额拆分 ───────────────────────────────────────────

/**
 * 计算负债部分金额（Property P4）
 *
 * 复合金融工具拆分：
 * - 负债部分 = 工具总额 - 权益部分
 *
 * 来源：M10-4 负债与权益区分检查表
 * CAS37要求复合金融工具初始确认时将权益和负债成分分别确认。
 * 负债成分按公允价值确认，权益成分=总额-负债成分（或反之）。
 *
 * @param total - 工具总额（发行金额/面值）
 * @param equityPart - 权益部分金额
 * @returns 负债部分金额
 */
export function splitAmount(total: number, equityPart: number): number {
  return safe(total) - safe(equityPart)
}

// ─── P5: 分类金额守恒 ──────────────────────────────────────

/**
 * 校验分类金额守恒（Property P5）
 *
 * 复合金融工具拆分后：权益部分 + 负债部分 === 总额
 * 用于M10-4检查表底部校验行，防止拆分计算错误。
 *
 * 使用浮点安全比较（容差1e-10），避免因浮点精度问题
 * 导致理论上相等的金额被判为不一致。
 *
 * @param equity - 权益部分金额
 * @param liability - 负债部分金额
 * @param total - 工具总额
 * @returns 是否守恒（equity + liability === total）
 */
export function calcClassificationConsistency(equity: number, liability: number, total: number): boolean {
  const eq = safe(equity)
  const liab = safe(liability)
  const t = safe(total)
  return Math.abs(eq + liab - t) < 1e-10
}

// ─── composable wrapper ─────────────────────────────────────

/**
 * useM10ClassificationEngine composable 包装
 *
 * 提供CAS37分类判定纯函数的统一导出。
 * 核心函数直接 export 供 PBT 直接引用。
 */
export function useM10ClassificationEngine() {
  return {
    classifyInstrument,
    splitAmount,
    calcClassificationConsistency,
  }
}
