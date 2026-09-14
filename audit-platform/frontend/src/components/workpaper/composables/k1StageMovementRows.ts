/**
 * K1 三阶段变动表行集 —— 单一真源（坏账准备 K1-3 + 国企附注账面余额变动）.
 *
 * 源模板两处三阶段滚动表行集与既有底稿实现存在实质差异：
 *
 * ① 坏账准备三阶段变动（源 xlsx 上市 `A93:E104` / 国企 `A64:E75`）12 行：
 *    上年年末余额(soe:期初余额) / 上年年末余额在本期(soe:期初余额在本期) /
 *    --转入第二阶段 / --转入第三阶段 / --转回第二阶段 / --转回第一阶段 /
 *    本期计提 / 本期转回 / 本期转销 / 本期核销 / 其他变动 / 期末余额。
 *    既有 `defaultStageMovements()` 是 13 行内部叫法（`第一阶段→第二阶段`/
 *    `本年计提`/`汇兑差异` 等），且**缺「本期转销」**（F8-8 勾稽算不出）。
 *
 * ② 国企附注「账面余额三阶段变动」（源 xlsx `A78:E87`）10 行：
 *    期初余额 / 期初余额在本期 / --转入第二阶段 / --转入第三阶段 /
 *    --转回第二阶段 / --转回第一阶段 / 本期新增 / 本期终止确认 / 其他变动 / 期末余额。
 *    既有 `defaultBalanceStageMovements()` 是 11 行且**两对重复标签**
 *    （`—转入第三阶段`×2、`—转回第一阶段`×2）。
 *
 * 本模块提供两套**源模板口径**行集构造器 + 历史数据迁移（按 key 对齐，金额不丢），
 * `useK1BadDebt.defaultStageMovements` 与 `k1DisclosureModel.defaultBalanceStageMovements`
 * 改为委托本模块（保留导出名，既有引用零改动）。
 *
 * spec: .kiro/specs/k1-extraction-chain-and-note-alignment/
 * Requirements 5.1~5.6, 6.5 / Properties 4, 5
 */
import type { K1StageMovementRow } from './useK1BadDebt'

export type K1MovementVariant = 'listed' | 'soe'

/** 迁移用旧 key 序列（按语义分组，供求和折叠） */
type LegacyKey =
  | 'opening' | 's1-s2' | 's1-s3' | 's2-s3' | 's2-s1' | 's3-s1' | 's3-s2'
  | 'provision' | 'reversal' | 'writeoff' | 'fx' | 'other' | 'collection' | 'closing'

/** 新 key（两套三阶段变动表共用的语义键） */
export type K1MovementKey =
  | 'opening' | 'openingInPeriod' | 'to2' | 'to3' | 'back2' | 'back1'
  | 'provision' | 'reversal' | 'writeOffTransfer' | 'writeOff'
  | 'addition' | 'derecognition' | 'other' | 'closing'

function row(key: K1MovementKey, label: string, editable: boolean): K1StageMovementRow {
  return { key, label, stage1: 0, stage2: 0, stage3: 0, editable }
}

/**
 * 坏账准备三阶段变动（源模板 12 行）。
 *
 * `variant` 只影响首两行标签口径：上市「上年年末余额」/「上年年末余额在本期」
 * （源 xlsx `A93`/`A94`），国企「期初余额」/「期初余额在本期」（源 xlsx `A64`/`A65`）。
 * 国企侧迁移箭头用全角破折号 `—`（源 xlsx 国企实证），上市侧用双短横 `--`
 * （源 xlsx 上市实证），与既有底稿 UI 展示一致，不额外统一。
 */
export function buildK1ProvisionMovementRows(variant: K1MovementVariant): K1StageMovementRow[] {
  const dash = variant === 'soe' ? '—' : '--'
  const openingLabel = variant === 'soe' ? '期初余额' : '上年年末余额'
  const openingInPeriodLabel = variant === 'soe' ? '期初余额在本期' : '上年年末余额在本期'
  return [
    row('opening', openingLabel, true),
    row('openingInPeriod', openingInPeriodLabel, false),
    row('to2', `${dash}转入第二阶段`, true),
    row('to3', `${dash}转入第三阶段`, true),
    row('back2', `${dash}转回第二阶段`, true),
    row('back1', `${dash}转回第一阶段`, true),
    row('provision', '本期计提', true),
    row('reversal', '本期转回', true),
    row('writeOffTransfer', '本期转销', true),
    row('writeOff', '本期核销', true),
    row('other', '其他变动', true),
    row('closing', '期末余额', false),
  ]
}

/**
 * 国企附注「账面余额三阶段变动」（源模板 10 行，固定用全角破折号）。
 */
export function buildK1BalanceMovementRows(): K1StageMovementRow[] {
  return [
    row('opening', '期初余额', false),
    row('openingInPeriod', '期初余额在本期', false),
    row('to2', '—转入第二阶段', false),
    row('to3', '—转入第三阶段', false),
    row('back2', '—转回第二阶段', false),
    row('back1', '—转回第一阶段', false),
    row('addition', '本期新增', true),
    row('derecognition', '本期终止确认', true),
    row('other', '其他变动', true),
    row('closing', '期末余额', false),
  ]
}

/** 旧 → 新 key 折叠表（同组多个旧行的金额求和归入一个新行） */
const LEGACY_TO_NEW: Record<LegacyKey, K1MovementKey> = {
  opening: 'opening',
  's1-s2': 'to2',
  's1-s3': 'to3',
  's2-s3': 'to3',
  's2-s1': 'back1',
  's3-s1': 'back1',
  's3-s2': 'back2',
  provision: 'provision',
  reversal: 'reversal',
  writeoff: 'writeOff',
  fx: 'other',
  other: 'other',
  collection: 'derecognition',
  closing: 'closing',
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 历史数据迁移：旧行集（13 行 provision 形态 / 11 行 balance 形态，也兼容已是
 * 新行集的情形）→ 新行集，按 key 对齐、金额求和折叠、不丢失。
 *
 * `kind='provision'` 用 `buildK1ProvisionMovementRows(variant)` 作模板；
 * `kind='balance'` 用 `buildK1BalanceMovementRows()`（`variant` 参数被忽略）。
 */
export function migrateK1MovementRows(
  raw: unknown,
  kind: 'provision' | 'balance',
  variant: K1MovementVariant = 'listed',
): K1StageMovementRow[] {
  const template = kind === 'provision'
    ? buildK1ProvisionMovementRows(variant)
    : buildK1BalanceMovementRows()

  if (!Array.isArray(raw) || raw.length === 0) return template

  const sums: Record<string, { stage1: number; stage2: number; stage3: number }> = {}
  for (const t of template) sums[t.key] = { stage1: 0, stage2: 0, stage3: 0 }

  for (const r of raw) {
    if (!r || typeof r !== 'object') continue
    const oldKey = String((r as any).key ?? '')
    const newKey = (LEGACY_TO_NEW as Record<string, K1MovementKey>)[oldKey] ?? oldKey
    const bucket = sums[newKey]
    if (!bucket) continue // 未知 key：按 Property 5 的口径丢弃前已在 other 兜住，此处防御
    bucket.stage1 += num((r as any).stage1)
    bucket.stage2 += num((r as any).stage2)
    bucket.stage3 += num((r as any).stage3)
  }

  return template.map((t) => ({
    ...t,
    stage1: Math.round(sums[t.key].stage1 * 100) / 100,
    stage2: Math.round(sums[t.key].stage2 * 100) / 100,
    stage3: Math.round(sums[t.key].stage3 * 100) / 100,
  }))
}
