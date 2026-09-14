/**
 * useICycleAdjudicationSeeding — I 类六循环审定表「从四表库带入未审数」的交互装配。
 *
 * 把 `iCycleAdjudicationSeed`（纯映射）+ `shared/adjudicationPrefillPlan`（纯计划）
 * 与 UI 三件事（按钮禁用态 / 冲突确认框 / 逐格写入）粘起来，让六个审定表各接 ~6 行即可，
 * **不必各抄一份 70 行的 plan→confirm→apply 流程**（G 循环 8 处各抄一份的教训）。
 *
 * ## 循环差异由调用方吸收，本 composable 无 per-cycle 分支
 *
 * - 行标签字段不同（`projectName` / `category` / `类别`）→ 调用方传 `rows` 时已归一为
 *   `{ rowId, label }`（用 `iCycleSeedSpec(wp).labelField` 取）。
 * - 写入签名不同（🔴 I1 是 `updateCell(block, rowId, field, value)` **四参**，
 *   其余是 `updateCell(rowId, field, value)` 三参）→ 调用方实现 `applyCell`，
 *   本 composable 把 `blockOf[segment]` 一并交给它。
 *
 * ## 三条口径原样透传（不在这一层做判断）
 *
 * 1. 手工优先：冲突格进确认框，默认「仅补空值」。
 * 2. 幂等：值已相同的格不写入（由 `planAdjudicationPrefill` 判定）。
 * 3. 「本项目无此科目 ≠ 为 0」：`absentSlots` 进提示文案，**不写 0**。
 * 4. 未命中不兜底：`unclassified` 进提示，交审计师显式归入。
 *
 * spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/ Task 17
 *       Requirements 9.2, 9.3, 9.4
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  buildICycleSeedCells,
  extractICyclePrefill,
  iCycleSeedSpec,
  type ICycleSeedResult,
  type ISeedExistingRow,
} from './iCycleAdjudicationSeed'
import {
  describeAdjPrefillConflicts,
  describeAdjPrefillPlan,
  planAdjudicationPrefill,
  planHasWork,
  resolveAdjPrefillWrites,
  type AdjPrefillCell,
  type AdjPrefillMode,
} from './shared/adjudicationPrefillPlan'
import { iCycleSpec } from './iCycleAccountScope'

export interface UseICycleSeedingOptions {
  /** 循环编码 I1~I6 */
  wpCode: string
  /** render 下发的 `html_data`（含 `adjudication_prefill`） */
  htmlData: ComputedRef<Record<string, unknown> | null | undefined>
  /** 审定表现有行，已归一为 `{ rowId, label }`（label 取自该循环的 `labelField`） */
  rows: ComputedRef<ISeedExistingRow[]> | Ref<ISeedExistingRow[]>
  /** 只读态 */
  isReadonly: ComputedRef<boolean> | Ref<boolean>
  /**
   * 读某格当前值。返回 `null` / `''` 视为未填。
   *
   * 🔴 **`0` 该不该算「未填」由调用方决定**：多数 I 循环的行初始化为 `0`（而非空），
   * 此时必须把 `0` 当未填、否则「带入」对新建行完全无效（G9 就是这么处理的）。
   */
  readCell: (cell: AdjPrefillCell) => number | string | null | undefined
  /**
   * 写入一格。`block` 仅 I1 非空（`'cost' | 'amort' | 'impairment'`）。
   *
   * 🔴 I1 必须用 `block` 调 `updateCell(block, rowId, field, value)`，
   * 漏传则三段全落到同一 block（后两段静默覆盖前一段）。
   */
  applyCell: (cell: AdjPrefillCell, block: string | undefined) => void
}

export function useICycleAdjudicationSeeding(opts: UseICycleSeedingOptions) {
  const seeding = ref(false)

  const accountName = computed(
    () => iCycleSpec(opts.wpCode)?.accountName || opts.wpCode,
  )

  /** render 下发的载荷（形态非法一律 null） */
  const prefill = computed(() => extractICyclePrefill(opts.htmlData.value))

  const seedResult = computed<ICycleSeedResult>(() =>
    buildICycleSeedCells(prefill.value, opts.wpCode, opts.rows.value),
  )

  /** 有可带入的格才启用按钮（无口径时禁用而非点了没反应） */
  const hasPrefill = computed(() => seedResult.value.cells.length > 0)

  /** 按钮 tooltip：三态文案（有数据 / 无此科目 / 未导入余额表） */
  const hint = computed(() => {
    const res = seedResult.value
    if (res.cells.length) {
      const parts = [`把四表库（${accountName.value}叶子余额）按科目名带入对应行的未审数，已录入的格不覆盖`]
      if (res.absentSlots.length) {
        parts.push(`${res.absentSlots.map((s) => s.label).join('、')} 本项目无此科目（不填 0）`)
      }
      if (res.unclassified.length) {
        parts.push(`${res.unclassified.length} 个科目在审定表里找不到同名行，需先建行或手工归入`)
      }
      return parts.join('；')
    }
    if (!prefill.value) {
      return `render 未下发四表取数结果 —— 可能本项目无「${accountName.value}」科目，或余额表尚未导入`
    }
    if (res.unclassified.length) {
      return `四表库有 ${res.unclassified.length} 个科目，但审定表里没有同名行 —— 请先新增对应行（不自动兜底到「其他」）`
    }
    return `四表库暂无${accountName.value}科目数据可带入`
  })

  async function pullFromFourTable(): Promise<void> {
    if (opts.isReadonly.value) return
    const { cells, unclassified, absentSlots, blockOf } = seedResult.value
    if (!cells.length) {
      ElMessage.info(hint.value)
      return
    }
    const plan = planAdjudicationPrefill(cells, opts.readCell, { unclassified, absentSlots })
    if (!planHasWork(plan)) {
      ElMessage.info(describeAdjPrefillPlan(plan))
      return
    }

    let mode: AdjPrefillMode = 'fill-blank'
    if (plan.conflicts.length) {
      try {
        const action = await ElMessageBox.confirm(
          `以下 ${plan.conflicts.length} 格已有录入且与四表不一致：\n`
          + `${describeAdjPrefillConflicts(plan)}\n\n`
          + '「覆盖」以四表数据替换；「仅补空值」保留已录入数据、只填空白格。',
          '从四表库带入未审数',
          {
            confirmButtonText: '覆盖',
            cancelButtonText: '仅补空值',
            distinguishCancelAndClose: true,
            type: 'warning',
          },
        )
        if (action === 'confirm') mode = 'overwrite'
      } catch (e) {
        if (e === 'close') return // 右上角关闭 = 放弃整个操作
        mode = 'fill-blank'
      }
    }

    seeding.value = true
    try {
      const slots = iCycleSeedSpec(opts.wpCode)?.slots || []
      for (const w of resolveAdjPrefillWrites(plan, mode)) {
        // 段键由 periodLabel 前缀反查（`buildICycleSeedCells` 产的是 `{段名}·{列名}`）。
        // 🔴 I1 三段的 rowKey+field 完全相同，只有段能区分 —— 反查不到就必须传
        //    undefined 让调用方按「无 block」处理，绝不能瞎猜一个 block。
        const seg = slots.find((s) => w.periodLabel.startsWith(`${s.segmentLabel}·`))?.segment
        opts.applyCell(w, seg ? blockOf[seg] : undefined)
      }
      ElMessage.success(describeAdjPrefillPlan(plan))
    } finally {
      seeding.value = false
    }
  }

  return { seeding, prefill, seedResult, hasPrefill, hint, pullFromFourTable }
}
