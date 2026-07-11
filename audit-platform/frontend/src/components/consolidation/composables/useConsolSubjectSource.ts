/**
 * useConsolSubjectSource — 合并模块科目名称真源 (Req 19.1 / 19.4 / 19.5 / 19.7)
 *
 * 背景（第四轮复盘实证）：`EliminationSheet.subjectTree` 原为硬编码五级科目中文名树，
 * 科目坐标名称脱离真源，容易与账户名称注册表漂移。
 *
 * 本 composable 把「科目名称的来源」收敛到 ACNR-backed 地址 store 的 `tbAddresses`
 * （Req 16，TB 域），产出与原硬编码 `subjectTree` **同构** 的 el-tree-select 数据：
 *   - 保留原有 disabled 父节点分组骨架（资产/负债/权益/损益/现金流及其子分组）
 *   - 叶子节点 value === 科目中文名字符串（契约不变，供 buildAutoEntries / Excel 复用）
 *
 * 设计要点（Req 19.5 降级 / Req 19.7 逻辑不变）：
 *   - TB 域为空/不可用 → 直接返回硬编码 `HARDCODED_SUBJECT_TREE`（无空白 picker、无回归）
 *   - TB 域可用 → 以硬编码分组结构为骨架，对每个叶子科目名 **按名称在 TB 注册表中确认/取 canonical 名**；
 *     注册表命中则采用其 canonical 名称（真源），未命中则 **保留硬编码字面量兜底**（逐叶子降级，绝不丢叶子）。
 *   - 无论命中与否，叶子 value === label === 科目名字符串，`subject` 值契约保持字节级不变，
 *     因此 `buildAutoEntries` + Excel 导入导出逻辑无需任何改动（Req 19.7）。
 *
 * 复用：其余合并 worksheet（InternalTradeSheet / InternalArApSheet / CapitalReserveSheet /
 * NetAssetSheet 等）可增量复用本 helper（Req 19.4），EliminationSheet 为试点。
 */
import { computed, type ComputedRef } from 'vue'
import { storeToRefs } from 'pinia'
import { useAddressRegistry } from '@/stores/addressRegistry'

// el-tree-select 节点结构（与原 EliminationSheet subjectTree 同构）
export interface SubjectTreeNode {
  label: string
  value: string
  disabled?: boolean
  children?: SubjectTreeNode[]
}

/**
 * 硬编码科目树（真源不可用时的降级骨架，Req 19.5）。
 * 父节点 disabled 仅作分类标题；叶子 value === 科目中文名。
 * 结构从 EliminationSheet.vue 原地迁移而来，保持完全一致。
 */
export const HARDCODED_SUBJECT_TREE: SubjectTreeNode[] = [
  { label: '资产', value: '_asset', disabled: true, children: [
    { label: '流动资产', value: '_current_asset', disabled: true, children: [
      { label: '货币资金', value: '货币资金' },
      { label: '应收票据', value: '应收票据' },
      { label: '应收账款', value: '应收账款' },
      { label: '预付账款', value: '预付账款' },
      { label: '其他应收款', value: '其他应收款' },
      { label: '存货', value: '存货' },
      { label: '合同资产', value: '合同资产' },
    ] },
    { label: '非流动资产', value: '_noncurrent_asset', disabled: true, children: [
      { label: '长期股权投资', value: '长期股权投资' },
      { label: '固定资产', value: '固定资产' },
      { label: '在建工程', value: '在建工程' },
      { label: '无形资产', value: '无形资产' },
      { label: '商誉', value: '商誉' },
      { label: '长期待摊费用', value: '长期待摊费用' },
      { label: '递延所得税资产', value: '递延所得税资产' },
    ] },
    { label: '减值准备', value: '_impairment', disabled: true, children: [
      { label: '坏账准备', value: '坏账准备' },
      { label: '存货跌价准备', value: '存货跌价准备' },
      { label: '固定资产减值准备', value: '固定资产减值准备' },
      { label: '长期股权投资减值准备', value: '长期股权投资减值准备' },
    ] },
  ] },
  { label: '负债', value: '_liability', disabled: true, children: [
    { label: '流动负债', value: '_current_liability', disabled: true, children: [
      { label: '应付票据', value: '应付票据' },
      { label: '应付账款', value: '应付账款' },
      { label: '预收账款', value: '预收账款' },
      { label: '合同负债', value: '合同负债' },
      { label: '其他应付款', value: '其他应付款' },
      { label: '应付职工薪酬', value: '应付职工薪酬' },
      { label: '应交税费', value: '应交税费' },
    ] },
    { label: '非流动负债', value: '_noncurrent_liability', disabled: true, children: [
      { label: '长期借款', value: '长期借款' },
      { label: '递延所得税负债', value: '递延所得税负债' },
      { label: '递延收益', value: '递延收益' },
    ] },
  ] },
  { label: '权益', value: '_equity', disabled: true, children: [
    { label: '实收资本（或股本）', value: '实收资本（或股本）' },
    { label: '其他权益工具', value: '其他权益工具' },
    { label: '资本公积', value: '资本公积' },
    { label: '减：库存股', value: '减：库存股' },
    { label: '其他综合收益', value: '其他综合收益' },
    { label: '专项储备', value: '专项储备' },
    { label: '盈余公积', value: '盈余公积' },
    { label: '△一般风险准备', value: '△一般风险准备' },
    { label: '未分配利润', value: '未分配利润' },
    { label: '少数股东权益', value: '少数股东权益' },
  ] },
  { label: '损益', value: '_income', disabled: true, children: [
    { label: '收入', value: '_revenue', disabled: true, children: [
      { label: '营业收入', value: '营业收入' },
      { label: '投资收益', value: '投资收益' },
      { label: '公允价值变动收益', value: '公允价值变动收益' },
      { label: '资产处置收益', value: '资产处置收益' },
      { label: '其他收益', value: '其他收益' },
    ] },
    { label: '成本费用', value: '_expense', disabled: true, children: [
      { label: '营业成本', value: '营业成本' },
      { label: '管理费用', value: '管理费用' },
      { label: '销售费用', value: '销售费用' },
      { label: '财务费用', value: '财务费用' },
      { label: '研发费用', value: '研发费用' },
      { label: '信用减值损失', value: '信用减值损失' },
      { label: '资产减值损失', value: '资产减值损失' },
    ] },
    { label: '利润分配', value: '_profit_dist', disabled: true, children: [
      { label: '年初未分配利润', value: '年初未分配利润' },
      { label: '少数股权损益', value: '少数股权损益' },
      { label: '提取盈余公积', value: '提取盈余公积' },
      { label: '对所有者的分配', value: '对所有者的分配' },
    ] },
  ] },
  { label: '现金流', value: '_cashflow', disabled: true, children: [
    { label: '销售商品收到的现金', value: '销售商品收到的现金' },
    { label: '购买商品支付的现金', value: '购买商品支付的现金' },
    { label: '收回投资收到的现金', value: '收回投资收到的现金' },
    { label: '投资支付的现金', value: '投资支付的现金' },
    { label: '分配股利支付的现金', value: '分配股利支付的现金' },
  ] },
]

/** 名称归一化：去首尾空白，供 TB 注册表名称匹配。 */
function normalizeName(name: string): string {
  return (name || '').trim()
}

/** 判断节点是否为叶子科目（无 children 且非 disabled 分类标题）。 */
function isLeaf(node: SubjectTreeNode): boolean {
  return !node.disabled && (!node.children || node.children.length === 0)
}

/**
 * 以硬编码分组骨架为基，对叶子科目名按 TB 注册表 canonical 名称库 **确认/取真源**。
 * - 命中：采用注册表 canonical 名（真源，Req 19.1）——value === label 契约保持
 * - 未命中：保留硬编码字面量（逐叶子降级，绝不丢叶子，Req 19.7）
 */
function mapTreeWithRegistry(
  nodes: SubjectTreeNode[],
  canonicalByName: Map<string, string>,
): SubjectTreeNode[] {
  return nodes.map((node) => {
    if (node.children && node.children.length > 0) {
      // 分类父节点：保留 disabled 骨架，递归子节点
      return {
        label: node.label,
        value: node.value,
        disabled: node.disabled,
        children: mapTreeWithRegistry(node.children, canonicalByName),
      }
    }
    if (isLeaf(node)) {
      const canonical = canonicalByName.get(normalizeName(node.value))
      // 命中注册表 → 用 canonical 名称（真源）；未命中 → 硬编码兜底
      const name = canonical ?? node.value
      return { label: name, value: name }
    }
    // 无子节点的 disabled 节点（理论上不存在）原样返回
    return { label: node.label, value: node.value, disabled: node.disabled }
  })
}

export interface ConsolSubjectSource {
  /** 响应式科目树（真源可用则确认自 TB 注册表，否则硬编码降级）。 */
  subjectTree: ComputedRef<SubjectTreeNode[]>
  /** 当前是否由 ACNR-backed TB 注册表支撑（false = 走硬编码降级）。 */
  isRegistryBacked: ComputedRef<boolean>
  /** TB 注册表 canonical 科目名集合（供契约测试/其他 worksheet 复用）。 */
  registrySubjectNames: ComputedRef<Set<string>>
  /** 硬编码降级树（供测试断言与直接引用）。 */
  hardcodedSubjectTree: SubjectTreeNode[]
}

/**
 * 合并模块科目名称真源 composable。
 *
 * 读取全局 `useAddressRegistry` store 的 `tbAddresses`（ACNR-backed，Req 16）。
 * store 由应用其他部分在切项目/年度时 `refresh()` 填充；本 helper 仅响应式读取，
 * 未填充时自然走硬编码降级（Req 19.5 无回归）。
 */
export function useConsolSubjectSource(): ConsolSubjectSource {
  const store = useAddressRegistry()
  const { tbAddresses } = storeToRefs(store)

  // TB 域 canonical 科目名映射：normalize(名称) → 原始 canonical 名称
  const canonicalByName = computed<Map<string, string>>(() => {
    const map = new Map<string, string>()
    for (const a of tbAddresses.value) {
      const label = a?.label
      if (label) {
        const key = normalizeName(label)
        if (key && !map.has(key)) map.set(key, label)
      }
    }
    return map
  })

  const registrySubjectNames = computed<Set<string>>(
    () => new Set(canonicalByName.value.keys()),
  )

  const isRegistryBacked = computed(() => canonicalByName.value.size > 0)

  const subjectTree = computed<SubjectTreeNode[]>(() => {
    if (!isRegistryBacked.value) {
      // Req 19.5：TB 注册表为空/不可用 → 硬编码降级，picker 不空白
      if (import.meta.env?.DEV) {
        console.warn('[useConsolSubjectSource] TB 地址注册表为空，回退硬编码科目树')
      }
      return HARDCODED_SUBJECT_TREE
    }
    return mapTreeWithRegistry(HARDCODED_SUBJECT_TREE, canonicalByName.value)
  })

  return {
    subjectTree,
    isRegistryBacked,
    registrySubjectNames,
    hardcodedSubjectTree: HARDCODED_SUBJECT_TREE,
  }
}
