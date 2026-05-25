/**
 * useCycleType — 统一识别底稿所属审计循环（B/C/D/F/G/H/I/K/L/M/N）
 *
 * 锚定 spec workpaper-editor-refactor Phase 2 — 拆分前置工具
 *
 * 把 WorkpaperEditor 内 11 处重复的 `isXCycle = computed(...)` 集中到一个 composable，
 * 减少主文件行数 + 统一 wp_code 正则规则。
 *
 * @example
 * const { isDCycle, isFCycle } = useCycleType(wpDetail)
 * if (isDCycle.value) { ... }
 *
 * 循环代号约定（与 memory.md `审计循环代号` 章节一致）：
 *   A=报表/调整 / B=控制了解 / C=控制测试 / D=销售收入 / E=货币资金
 *   F=采购存货 / G=投资 / H=固定资产+在建+使用权资产+租赁负债
 *   I=无形资产+商誉+开发支出 / J=职工薪酬+股份支付 / K=管理 / L=筹资
 *   M=股东权益 / N=税费 / S=专项程序
 */
import { computed, type Ref, type ComputedRef } from 'vue'

export interface CycleTypeFlags {
  /** 当前 wp_code（大写归一化后） */
  code: ComputedRef<string>
  /** B 类底稿（控制了解/审计计划）：B1/B10/B22/B23/B30/B40/B50/B51/B52/B60 等 */
  isBCycle: ComputedRef<boolean>
  /** C 类底稿（控制测试）：C1~C26 */
  isCCycle: ComputedRef<boolean>
  /** D 销售收入循环：D0/D1/.../D7（含子表 D2-1, D4-22A 等） */
  isDCycle: ComputedRef<boolean>
  /** F 采购存货循环：F0/F1/.../F5（含子表 F2-1, F2-21A 等） */
  isFCycle: ComputedRef<boolean>
  /** G 投资循环：G0/G1/.../G14（含子表 G1-2, G7-3 等） */
  isGCycle: ComputedRef<boolean>
  /** H 固定资产循环：H0/H1/.../H10（含子表 H1-12, H8-8 等） */
  isHCycle: ComputedRef<boolean>
  /** I 无形资产循环：I0/I1/.../I6（含子表 I1-10, I4-7 等） */
  isICycle: ComputedRef<boolean>
  /** K 管理循环：K0/K1/.../K13（含子表 K8-2, K1-12 等） */
  isKCycle: ComputedRef<boolean>
  /** L 筹资循环：L0/L1/.../L8（含子表 L1-2, L8-2 等） */
  isLCycle: ComputedRef<boolean>
  /** M 权益循环：M1/M2/.../M10（含子表 M2-2, M6-2 等） */
  isMCycle: ComputedRef<boolean>
  /** N 税金循环：N1/N2/.../N5（含子表 N2-1, N5-4 等） */
  isNCycle: ComputedRef<boolean>
}

export function useCycleType(
  wpDetail: Ref<{ wp_code?: string | null } | null>,
): CycleTypeFlags {
  const code = computed(() => (wpDetail.value?.wp_code || '').toUpperCase())

  return {
    code,
    isBCycle: computed(() => /^B\d|^B[1-6]/i.test(code.value)),
    isCCycle: computed(() => /^C\d/i.test(code.value)),
    isDCycle: computed(() => /^D\d/.test(code.value)),
    isFCycle: computed(() => /^F\d/.test(code.value)),
    isGCycle: computed(() => /^G\d/.test(code.value)),
    isHCycle: computed(() => /^H\d/.test(code.value)),
    isICycle: computed(() => /^I\d/.test(code.value)),
    isKCycle: computed(() => /^K\d/.test(code.value)),
    isLCycle: computed(() => /^L\d/.test(code.value)),
    isMCycle: computed(() => /^M\d/.test(code.value)),
    isNCycle: computed(() => /^N\d/.test(code.value)),
  }
}
