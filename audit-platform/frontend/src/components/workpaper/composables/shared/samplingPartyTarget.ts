/**
 * samplingPartyTarget — 抽凭样本「往来单位名称」的落列裁决（单一真源）
 *
 * ## 为什么需要这一层
 *
 * 后端 `enrich_items_with_aux_party` 只提供**中性事实**：
 * `party_name`（辅助明细账里的往来单位名）+ `party_aux_type`（它来自哪个维度）。
 * 它**不知道**目标底稿那一列叫什么、语义是什么 —— 这是宿主侧的知识。
 *
 * 而抽凭底稿的这一列语义并不统一（实测 24 个宿主）：
 *
 * | 语义 | 宿主举例 | 行字段 |
 * |---|---|---|
 * | 客户名称 | D3 / D6 / D7 | `customerName` |
 * | 供应商名称 | F1 / F2 / H2 / H4 / I2 | `supplier` / `supplierName` |
 * | 债务人 / 债权人 | K1 / K3 / K9 | `debtorName` |
 * | 被投资单位 | G8 / I3 | `investeeName` |
 * | 对方单位 | K5 / K8 | `debtorName` |
 * | **没有这一列** | H10（合规检查项行）/ F2 计价测试 | — |
 *
 * 所以「无条件把 party_name 写进 customerName」是错的：会把供应商名填进
 * 「客户名称」列，也会往根本没有这列的行里塞字段。
 *
 * ## 🔴 判据的数据基础（真实库实证，2026-08-04）
 *
 * `tb_aux_ledger` 全库 8 个项目只有 **「客户」与「职员」** 两种往来单位类维度，
 * **没有「供应商」「往来单位」**。而 `aux_type='客户'` 的行同时挂在：
 *
 * - 应收侧 `1122`（123 万行 / 8287 个名字）、`1123`、`1221`、`2203`（预收）
 * - **应付侧 `2202`（48 万行 / 5878 个名字）、`2241`、`2201`**
 * - 损益侧 `6001`（收入）、`6401`（成本）、`6601`~`6603`（费用）
 *
 * ⇒ 该账套的「客户」维度实际承载的是**「往来单位」**（应付科目下那批就是供应商）。
 * 故**不能按 `aux_type` 反推目标列语义** —— 必须按「本次抽的是哪个科目 + 宿主
 * 那一列是什么」来判定，`aux_type` 只作溯源展示（让审计师知道值取自哪个维度）。
 *
 * ## 设计取向
 *
 * - **宿主显式声明目标列语义**，共享件不猜（声明式，与 `HOST_ROW_MODEL_KIND` 同范式）
 * - 没有该列的宿主**不声明** ⇒ 不落列（宁缺勿造）
 * - 歧义（一键多名）**不写值**，只透出候选让审计师点选 —— 与「重复抽凭必须弹窗
 *   人工确认」同一原则：系统能算但涉及审计判断的，交给人
 * - 手工已填的值**永不覆盖**
 */

/** 目标列语义（宿主声明用） */
export type PartyColumnSemantic =
  | 'customer'   // 客户名称（应收/预收/收入侧）
  | 'supplier'   // 供应商名称（应付/预付/成本侧）
  | 'debtor'     // 债务人（其他应收）
  | 'creditor'   // 债权人（其他应付）
  | 'investee'   // 被投资单位
  | 'counterpart' // 对方单位（不区分方向）

/** 各语义的中文展示名（提示文案与守卫共用，禁在组件里另写一份） */
export const PARTY_SEMANTIC_LABELS: Readonly<Record<PartyColumnSemantic, string>> =
  Object.freeze({
    customer: '客户名称',
    supplier: '供应商名称',
    debtor: '债务人',
    creditor: '债权人',
    investee: '被投资单位',
    counterpart: '对方单位',
  })

/**
 * 宿主对「往来单位名称列」的声明。
 *
 * `rowField` 是行模型里的字段名；`semantic` 决定提示文案与守卫判定。
 * 不声明 ⇒ 该宿主没有这一列 ⇒ 不落列。
 */
export interface PartyFillTarget {
  rowField: string
  semantic: PartyColumnSemantic
}

/** 样本侧的往来单位信息（后端 enrich 的三个字段，camelCase 与 snake_case 双兼容） */
export interface SampledPartyInfo {
  /** 唯一命中的往来单位名；未命中 / 歧义时为 null */
  partyName: string | null
  /** 该名字来自哪个辅助维度（如「客户」）；仅作溯源展示，不用于反推列语义 */
  partyAuxType: string | null
  /** 一键多名 ⇒ 系统不猜，交审计师判断 */
  partyAmbiguous: boolean
}

function str(v: unknown): string {
  return v === null || v === undefined ? '' : String(v).trim()
}

/**
 * 从样本对象读出往来单位信息（纯函数）。
 *
 * 兼容抽凭引擎的 camelCase 与后端 items 的 snake_case；非对象输入返回全空
 * （不抛错，一条脏样本不该打掉整批回填）。
 */
export function readSampledParty(v: unknown): SampledPartyInfo {
  const src = (v && typeof v === 'object' ? v : {}) as Record<string, unknown>
  const name = str(src.partyName ?? src.party_name)
  const auxType = str(src.partyAuxType ?? src.party_aux_type)
  const ambiguous = Boolean(src.partyAmbiguous ?? src.party_ambiguous)
  return {
    partyName: name === '' ? null : name,
    partyAuxType: auxType === '' ? null : auxType,
    partyAmbiguous: ambiguous,
  }
}

/**
 * 可作为「交易对手方名称」的辅助维度类型白名单。
 *
 * 🔴 实测（真实库 8 个项目）`tb_aux_ledger` 只有「客户」与「职员」两种往来单位类
 * 维度。其中：
 * - **「客户」= 往来单位**（同时挂应收 1122 与应付 2202，后者就是供应商）→ 采纳
 * - **「职员」= 内部员工**（备用金/差旅报销的领用人）→ **不采纳**：员工不是交易
 *   对手方，把「张三」填进「客户名称/供应商名称」列是错的
 *
 * 「成本中心」「业态」「税率」「区域」等分摊/分类维度天然不在此列 —— 它们由
 * 后端 `AUX_PARTY_TYPES` 先挡一道，此处是第二道（防后端白名单被放宽后前端失守）。
 */
export const PARTY_ELIGIBLE_AUX_TYPES: readonly string[] = Object.freeze([
  '客户',
  '供应商',
  '往来单位',
])

/**
 * 该维度类型能否作为交易对手方名称。
 *
 * 🔴 `aux_type` 缺失时判**不适格**（不填）。理由：后端 `enrich_items_with_aux_party`
 * 命中时必然同时写 `party_name` 与 `party_aux_type`（同一行 SQL 取出），二者只会
 * 同时有值。故「有名字但没维度」意味着数据来源不明 —— 可能是别处塞进来的、也可能
 * 是格式变更后的半成品，此时按「不确定就不填」处理。
 *
 * 早期实现在这里返回 true（「不因缺元数据而丢弃已匹配到的名称」），但那让
 * 「维度不适格」这道门可以被"不带维度"绕过 —— 守卫已用替身样本打红。
 */
export function isEligiblePartyAuxType(auxType: string | null | undefined): boolean {
  const t = str(auxType)
  if (t === '') return false
  return PARTY_ELIGIBLE_AUX_TYPES.includes(t)
}

/**
 * 判定某个样本该不该往目标列写值、写什么。
 *
 * 返回 `null` 表示**不写**，四种情形：
 * 1. 宿主没声明该列（这张底稿没有往来单位名称列）
 * 2. 未命中（该凭证行在辅助明细账里没有往来单位）
 * 3. 歧义（一键多名 → 交审计师判断）
 * 4. **维度类型不适格**（如「职员」→ 不是交易对手方）
 *
 * 调用方拿到 null 时应保留该单元格原值（含空值），不得写空串覆盖手工输入。
 */
export function resolvePartyFill(
  target: PartyFillTarget | null | undefined,
  sample: unknown,
): { rowField: string; value: string } | null {
  if (!target || !target.rowField) return null
  const info = readSampledParty(sample)
  if (info.partyAmbiguous) return null
  if (!info.partyName) return null
  if (!isEligiblePartyAuxType(info.partyAuxType)) return null
  return { rowField: target.rowField, value: info.partyName }
}

/**
 * 便捷包装：直接取「该写进目标列的字符串」，不写时返回空串。
 *
 * 给 `mapSampledToXxxRow` 这类「必须给字段一个初值」的映射函数用 ——
 * 它们要的是 `string` 而不是 `{rowField, value} | null`。
 *
 * 🔴 返回空串的语义是**「本次不自动填」**，不是「清空」：映射函数是在
 * 构造**新行**，新行该列本来就是空的。**不得**拿它去覆盖既有行的手工值
 * （那属于 merge 场景，必须先判 `resolvePartyFill` 是否为 null）。
 *
 * @param semantic 目标列语义；宿主自己知道自己那一列是什么
 */
export function partyNameForColumn(
  sample: unknown,
  semantic: PartyColumnSemantic,
): string {
  const fill = resolvePartyFill({ rowField: '_', semantic }, sample)
  return fill ? fill.value : ''
}

/**
 * 歧义提示文案：告诉审计师「系统查到多个候选、故意没填」。
 *
 * 与「留空」区分开 —— 留空可能是本来没有这个维度，歧义是**有值但需要人判断**。
 */
export function buildPartyAmbiguousHint(
  semantic: PartyColumnSemantic,
  auxType?: string | null,
): string {
  const label = PARTY_SEMANTIC_LABELS[semantic] ?? '往来单位'
  const dim = str(auxType)
  const from = dim ? `辅助维度「${dim}」下` : '辅助明细账中'
  return (
    `${from}该凭证行对应多个往来单位，系统未自动填写${label}，` +
    `请核对原始凭证后手工填写（填错往来单位比留空更严重）`
  )
}

/** 溯源文案：说明这个值是自动带出来的、来自哪里（审计追溯要求） */
export function buildPartySourceHint(
  semantic: PartyColumnSemantic,
  auxType?: string | null,
): string {
  const label = PARTY_SEMANTIC_LABELS[semantic] ?? '往来单位'
  const dim = str(auxType)
  return dim
    ? `${label}自动取自辅助明细账（维度：${dim}），可手工修改`
    : `${label}自动取自辅助明细账，可手工修改`
}
