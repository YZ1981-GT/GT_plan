/**
 * 抽凭科目门 —— 科目码解析不出时显式降级，禁止以空/错科目发起抽样。
 *
 * spec: voucher-sampling-account-scope-and-attach-closure（Requirement 2，阶段 4）
 *
 * ## 为什么需要它
 *
 * 部分循环的科目真源以 `FALLBACK_STANDARD = ''` 表达「本循环无标准独立科目码」
 * （现算 3 例：`i5AccountScope` 其他非流动资产 / `k4AccountScope` 其他流动负债 /
 * `l7AccountScope` 其他非流动负债 —— 与 `L7_WRONG_LEGACY_ACCOUNTS` 一并记录了
 * 历史上被误填的码）。这叫**宁缺勿造**：臆造一个兜底码会让抽凭以错科目查库。
 *
 * 🔴 阶段 3 实证把适用面推得更广：修正科目码后，G1(`1101`/`1102`) / I2(`1704`) /
 * I6(`6604`) / H5(`1631`) 在当前 8 个真实项目的 active `tb_ledger` 里**全部 0 行**
 * （这些医药流通/租车企业确实没有衍生品、开发支出、研发支出、油气资产业务）。
 * 所以降级不能只给那 3 个"空兜底"循环打补丁，而应是**通用能力**：
 * 只要最终解析出的科目码集为空，就禁用抽凭入口并给出可操作提示。
 *
 * ## 与「加载中」「只读」的区别
 *
 * 三态必须可区分（Requirement 2.4）：
 * - `absent`   → 本项目无此科目（本 composable 负责）
 * - `loading`  → 科目解析中（调用方传入）
 * - `readonly` → 底稿只读（调用方传入）
 *
 * 前者的提示要给出下一步（手工录入 / 去报表配置映射），后两者不是错误态。
 */
import { computed, unref, type ComputedRef, type MaybeRefOrGetter } from 'vue'

export interface SamplingAccountGateOptions {
  /**
   * 已解析的科目码集。通常来自 `{x}QueryCodes(props.tbSourceCodes)`；
   * 允许含空串（会被过滤）。
   */
  codes: MaybeRefOrGetter<readonly string[] | string | null | undefined>
  /** 底稿显示名，用于提示文案（如「其他非流动资产」） */
  accountLabel: MaybeRefOrGetter<string>
  /** 底稿只读态（可选） */
  isReadonly?: MaybeRefOrGetter<boolean>
  /** 科目解析进行中（可选） */
  isLoading?: MaybeRefOrGetter<boolean>
}

export type SamplingGateState = 'ready' | 'absent' | 'loading' | 'readonly'

export interface SamplingAccountGate {
  /** 规范化后的科目码集（去空、去重、保序） */
  resolvedCodes: ComputedRef<string[]>
  /** 传给 `GtVoucherSamplingEngine` 的 `account-code`（逗号拼接；空态为 ''） */
  accountCode: ComputedRef<string>
  /** 当前门状态 */
  state: ComputedRef<SamplingGateState>
  /**
   * 抽凭入口是否禁用。
   * 🔴 `absent` / `loading` / `readonly` 三态都禁用，但 `disabledReason` 不同。
   */
  disabled: ComputedRef<boolean>
  /** 是否因「本项目无此科目」而禁用（区别于只读/加载中） */
  isAccountAbsent: ComputedRef<boolean>
  /** 禁用原因（tooltip 用；`ready` 时为空串） */
  disabledReason: ComputedRef<string>
  /**
   * 是否允许发起抽样请求。
   * 🔴 调用方**必须**在发请求前检查它 —— Requirement 2.2 要求空科目时
   * 不得调 `POST /voucher-extract`（否则会以空/错科目扫全库）。
   */
  canSample: ComputedRef<boolean>
}

function toList(v: readonly string[] | string | null | undefined): string[] {
  if (v == null) return []
  const arr = typeof v === 'string' ? v.split(',') : [...v]
  const out: string[] = []
  for (const x of arr) {
    const s = String(x ?? '').trim()
    if (s && !out.includes(s)) out.push(s)
  }
  return out
}

function read<T>(src: MaybeRefOrGetter<T>): T {
  return typeof src === 'function' ? (src as () => T)() : unref(src as never)
}

export function useSamplingAccountGate(
  options: SamplingAccountGateOptions,
): SamplingAccountGate {
  const resolvedCodes = computed(() => toList(read(options.codes)))

  const isAccountAbsent = computed(() => resolvedCodes.value.length === 0)

  const state = computed<SamplingGateState>(() => {
    // 顺序即优先级：只读是最强约束，其次加载中，再次无科目。
    if (options.isReadonly != null && read(options.isReadonly)) return 'readonly'
    if (options.isLoading != null && read(options.isLoading)) return 'loading'
    if (isAccountAbsent.value) return 'absent'
    return 'ready'
  })

  const accountCode = computed(() => resolvedCodes.value.join(','))

  const disabled = computed(() => state.value !== 'ready')

  const disabledReason = computed(() => {
    switch (state.value) {
      case 'absent':
        return (
          `本项目无「${read(options.accountLabel)}」对应科目，无法抽凭。` +
          '请手工录入检查明细，或先在报表配置中为该行映射科目。'
        )
      case 'loading':
        return '科目信息加载中，请稍候…'
      case 'readonly':
        return '底稿为只读状态，无法抽凭。'
      default:
        return ''
    }
  })

  // 🔴 与 disabled 同源但语义不同：canSample 用于**发请求前**的守门，
  //    即便 UI 被绕过（快捷键/程序化调用）也不应发出请求。
  const canSample = computed(() => state.value === 'ready')

  return {
    resolvedCodes,
    accountCode,
    state,
    disabled,
    isAccountAbsent,
    disabledReason,
    canSample,
  }
}
