/**
 * e1RestrictedScope — E1「受限制的货币资金明细」②表 的动态取数与人工归类
 *
 * **为什么必须动态**
 *
 * 受限资金没有独立标准科目 —— 它是货币资金（1001/1002/1012）里「用途受限」的
 * 那一部分，客户各自用二级/三级子科目承载，命名千差万别（活体项目 `df5b8403` 的
 * `1012` 叶子全是支付渠道名：金华支付宝 / 微信小程序 / 聚合收款 / AFO / 小桔有车）。
 *
 * 取数链路（后端 `four_table/e1_restricted_buckets.py` + render `restricted_prefill`）：
 *
 *   BS-002 报表行解析 → account_mapping 反解项目原始码 → select_leaves 取叶子
 *   → 逐叶子按**科目名**分类 → 命中落 buckets / 未命中落 unclassified
 *
 * 本模块负责前端侧：合并「人工归类」与「自动分类」，产出 ②表行。
 *
 * **🔴 中文标签只有后端一份** —— 桶的 label 从 render 下发的 `bucketDefs` 取
 * （`bucket_defs_payload()`）。本文件**不得**再抄一份桶中文名，否则后端改了前端不跟。
 * 拿不到 `bucketDefs` 时退化显示 key（宁可难看也不双真源）。
 *
 * **人工归类优先**：审计师在「待归类科目」面板把某叶子归入某类 / 标记不受限后，
 * 结果持久化到 `E1-disclosure-{variant}-restricted-map`（`原始科目码 → bucketKey |
 * '__unrestricted__'`）；下次刷新取数时人工归类**优先于**自动分类，四表新增的
 * 科目自动出现在 unclassified 而不改动已有类别行金额。
 *
 * spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/
 *       Requirements 6.2, 6.4, 11.5~11.10 / Property 17
 */

/** 「标记为不受限」哨兵值（与后端 `e1_restricted_buckets.UNRESTRICTED` 一致）。 */
export const E1_UNRESTRICTED = '__unrestricted__'

// ─── render 下发的载荷 ────────────────────────────────────────────────────────

export interface E1RestrictedBucketDef {
  key: string
  /** 中文标签 —— **唯一来源是后端**，前端不抄第二份 */
  label: string
  /** 源模板无对应行的平台补充桶（如「其他受限资金」） */
  isPlatformExtra: boolean
  /**
   * 附注**展示序**（越小越靠前）—— 与数组下标（= 匹配优先级）**不同**。
   *
   * 🔴 后端 `E1_RESTRICTED_BUCKETS` 的声明序被「包含关系必须先声明」绑住
   * （`信用证保证金` 含「保证金」须先于兜底桶；`境外冻结存款` 同含「冻结」与「境外」
   * 须境外优先），产出 `信用证→银行承兑→履约→境外→质押`；而源 docx 行序是
   * `银行承兑→信用证→履约→质押→境外→法定准备金`（**1↔2、4↔5 互换**）。
   * 用数组下标排序会让附注行序与 docx 不符（既存缺陷，E-cycle spec R6.7）。
   *
   * 缺字段时退化为数组下标（向后兼容旧 render 载荷）。
   */
  displayOrder?: number
}

/**
 * 货币资金三族的一个叶子科目。
 *
 * 🔴 后端下发的是**扁平叶子清单**而不是预聚合的桶 —— 预聚合是有损表示：
 * 审计师把某叶子改归到别的类别后，就无法重算被改动桶的余额。
 */
export interface E1RestrictedLeaf {
  code: string
  name: string
  opening: number
  closing: number
  /** 所属语义槽（cash / bank / other） */
  slot: string
  /** 按科目名自动分类的结果；`null` = 判不出来，须人工归类 */
  autoBucket: string | null
}

export interface E1RestrictedPrefill {
  leaves: E1RestrictedLeaf[]
  bucketDefs: E1RestrictedBucketDef[]
  source: { report_row_code?: string; chart_available?: boolean }
}

const num = (v: unknown): number =>
  typeof v === 'number' && Number.isFinite(v) ? v : Number(v) || 0

/** 归一 render 载荷（缺字段按空处理，不抛）。 */
export function normalizeRestrictedPrefill(raw: unknown): E1RestrictedPrefill {
  const p = (raw ?? {}) as Record<string, unknown>
  return {
    leaves: Array.isArray(p.leaves)
      ? (p.leaves as unknown[]).map((x) => {
          const r = (x ?? {}) as Record<string, unknown>
          const auto = r.autoBucket
          return {
            code: String(r.code ?? ''),
            name: String(r.name ?? ''),
            opening: num(r.opening),
            closing: num(r.closing),
            slot: String(r.slot ?? ''),
            autoBucket: auto == null || auto === '' ? null : String(auto),
          }
        })
      : [],
    bucketDefs: Array.isArray(p.bucketDefs)
      ? (p.bucketDefs as unknown[]).map((x) => {
          const r = (x ?? {}) as Record<string, unknown>
          const rawOrder = Number(r.displayOrder)
          return {
            key: String(r.key ?? ''),
            label: String(r.label ?? ''),
            isPlatformExtra: !!r.isPlatformExtra,
            // 缺字段/非数值时留 undefined，由排序侧退化为数组下标（向后兼容）
            ...(Number.isFinite(rawOrder) ? { displayOrder: rawOrder } : {}),
          }
        })
      : [],
    source: (p.source ?? {}) as E1RestrictedPrefill['source'],
  }
}

// ─── 人工归类 map ─────────────────────────────────────────────────────────────

/** `原始科目码 → bucketKey | E1_UNRESTRICTED`。 */
export type E1RestrictedManualMap = Record<string, string>

export function parseManualMap(raw: unknown): E1RestrictedManualMap {
  if (typeof raw !== 'string' || !raw.trim()) return {}
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const out: E1RestrictedManualMap = {}
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      const code = String(k).trim()
      const target = String(v ?? '').trim()
      if (code && target) out[code] = target
    }
    return out
  } catch {
    return {}
  }
}

export function serializeManualMap(map: E1RestrictedManualMap): string {
  return JSON.stringify(map ?? {})
}

/** 人工归类持久化键（按变体分开，上市/国企各自归类互不干扰）。 */
export function e1RestrictedMapKey(variant: 'listed' | 'soe'): string {
  return `E1-disclosure-${variant}-restricted-map`
}

// ─── ②表行 ────────────────────────────────────────────────────────────────────

export interface E1RestrictedRow {
  /** 稳定 key（`restricted_{bucketKey|custom}_{seq}`，**禁用 label 作 key**） */
  id: string
  /** 桶 key；自定义类别为 `custom:{名称}` */
  bucketKey: string
  /** 展示名（桶来自后端 bucketDefs；自定义类别用审计师输入的名称） */
  label: string
  openingAmount: number
  endingAmount: number
  /** 受限原因（审计师录入的真实披露内容） */
  reason: string
  /** 归集到本行的原始科目码（溯源展示） */
  codes: string[]
  /** 是否由四表自动分类得来（false = 纯手工行 / 人工归类行） */
  fromFourTable: boolean
}

const CUSTOM_PREFIX = 'custom:'

export function isCustomBucketKey(key: string): boolean {
  return String(key ?? '').startsWith(CUSTOM_PREFIX)
}

export function customBucketKey(label: string): string {
  return `${CUSTOM_PREFIX}${String(label ?? '').trim()}`
}

/** 自定义类别的展示名 = key 去前缀（自定义类别的中文名本就由审计师输入）。 */
export function customBucketLabel(key: string): string {
  return isCustomBucketKey(key) ? key.slice(CUSTOM_PREFIX.length) : key
}

export function e1RestrictedRowId(bucketKey: string, seq: number): string {
  const slug = isCustomBucketKey(bucketKey)
    ? `custom_${customBucketLabel(bucketKey).replace(/\s+/g, '').slice(0, 12)}`
    : bucketKey
  return `restricted_${slug || 'bucket'}_${seq}`
}

/**
 * 桶 key → 展示名。**只从后端 bucketDefs 取**；未下发时退化显示 key。
 *
 * 🔴 不在前端硬编码桶中文名 —— 平台铁律「分类桶一份声明式真源，前端不抄第二份」。
 */
/**
 * 桶 key → **附注展示序**（②表行序）。
 *
 * 🔴 **不能用数组下标** —— `bucketDefs` 的数组顺序是后端的**声明序 = 匹配优先级**，
 * 与源 docx 的行序 1↔2、4↔5 互换（`信用证`↔`银行承兑`、`境外`↔`质押`）。
 * 用下标排序会让附注②表行序与 docx 不符（既存缺陷，E-cycle spec R6.7 / Property 36）。
 *
 * 真源 = 后端 `bucket_defs_payload()` 下发的 `displayOrder`（由
 * `E1_RESTRICTED_DOCX_ROW_ORDER` 派生）。旧 render 载荷缺该字段时退化为数组下标
 * （向后兼容：行序仍与改造前一致，不会因为字段缺失而乱序）。
 */
export function bucketDisplayOrderMap(
  bucketDefs: readonly E1RestrictedBucketDef[],
): Map<string, number> {
  return new Map(
    bucketDefs.map((d, i) => [d.key, Number.isFinite(d.displayOrder) ? (d.displayOrder as number) : i]),
  )
}

export function resolveBucketLabel(
  bucketKey: string,
  bucketDefs: readonly E1RestrictedBucketDef[],
): string {
  if (isCustomBucketKey(bucketKey)) return customBucketLabel(bucketKey)
  return bucketDefs.find((d) => d.key === bucketKey)?.label || bucketKey
}

export interface ResolveRestrictedOptions {
  prefill: E1RestrictedPrefill
  manualMap: E1RestrictedManualMap
  /** 已持久化的行（保留审计师录入的 reason 与手工金额） */
  existingRows?: readonly E1RestrictedRow[]
}

/** 某叶子的最终归属：人工归类优先于自动分类；`null` = 仍待归类。 */
export function effectiveBucketOf(
  leaf: E1RestrictedLeaf,
  manualMap: E1RestrictedManualMap,
): string | null {
  const manual = manualMap[leaf.code]
  if (manual) return manual === E1_UNRESTRICTED ? null : manual
  return leaf.autoBucket
}

/**
 * 合并「人工归类」与「自动分类」→ ②表行。**纯函数。**
 *
 * 优先级：人工归类 > 自动分类 > 仍待归类（不进表）。
 * 被标 `E1_UNRESTRICTED` 的叶子不进任何类别行（其金额由勾稽面板计入差额侧）。
 *
 * 因后端下发的是**逐叶子**明细，这里可以自由重算 —— 审计师把叶子改归到别的类别时，
 * 原类别与新类别的余额都能精确重算（预聚合表示做不到这点）。
 *
 * 已有行的 `reason` 保留；纯手工行（不由四表叶子构成）原样保留金额。
 */
export function resolveRestrictedRows(opts: ResolveRestrictedOptions): E1RestrictedRow[] {
  const { prefill, manualMap } = opts
  const existing = opts.existingRows ?? []
  const reasonByBucket = new Map<string, string>()
  for (const r of existing) {
    if (r.reason) reasonByBucket.set(r.bucketKey, r.reason)
  }

  const agg = new Map<string, { opening: number; closing: number; codes: string[] }>()
  const bump = (key: string, opening: number, closing: number, code: string) => {
    const cur = agg.get(key) ?? { opening: 0, closing: 0, codes: [] }
    cur.opening += opening
    cur.closing += closing
    if (code) cur.codes.push(code)
    agg.set(key, cur)
  }

  // ① 逐叶子按最终归属聚合（人工归类优先）
  for (const leaf of prefill.leaves) {
    const bucket = effectiveBucketOf(leaf, manualMap)
    if (!bucket) continue
    bump(bucket, leaf.opening, leaf.closing, leaf.code)
  }

  // ② 纯手工行（审计师直接加的类别，不由四表叶子构成）
  for (const r of existing) {
    if (agg.has(r.bucketKey)) continue
    if (r.fromFourTable) continue
    agg.set(r.bucketKey, {
      opening: r.openingAmount,
      closing: r.endingAmount,
      codes: [...r.codes],
    })
  }

  const defs = prefill.bucketDefs
  const order = bucketDisplayOrderMap(defs)
  // 🔴 已持久化行的 id **原样保留**，不按下标重算（Property 28 的端到端环节）。
  //    `addRestrictedRow` 用 `nextRestrictedSeq` 算出的稳定序号写进 `existingRows`，
  //    若这里再用数组下标 `i` 生成 id，就把那个序号**覆盖**掉 ——
  //    删掉 custom_甲_2 再新增 custom_乙 时，乙 落库又是 `_2`（复用已删序号），
  //    按 row id 索引的历史 reason/金额于是串到新类别上。
  //    真实库实测（soe 2aa00f57）：计数器已正确涨到 3，落库 id 仍是 `_2` ⇒ 缺陷在此处。
  //    下标只能用于**新桶**（四表新归集出来、还没有 id 的行）。
  const idByBucket = new Map<string, string>()
  for (const r of existing) {
    const id = String(r.id ?? '')
    if (id) idByBucket.set(r.bucketKey, id)
  }
  return [...agg.entries()]
    .sort((a, b) => (order.get(a[0]) ?? 999) - (order.get(b[0]) ?? 999))
    .map(([bucketKey, amt], i) => ({
      id: idByBucket.get(bucketKey) ?? e1RestrictedRowId(bucketKey, i),
      bucketKey,
      label: resolveBucketLabel(bucketKey, defs),
      openingAmount: amt.opening,
      endingAmount: amt.closing,
      reason: reasonByBucket.get(bucketKey) ?? '',
      codes: amt.codes,
      fromFourTable: amt.codes.length > 0,
    }))
}

/**
 * 仍待归类的叶子（自动分类判不出来、且审计师还没处理的）。
 *
 * 这是「各项目科目命名不同」的兜底通道：四表新增科目自动出现在这里，
 * **既不静默丢弃也不臆造归属**。
 */
export function pendingUnclassified(
  prefill: E1RestrictedPrefill,
  manualMap: E1RestrictedManualMap,
): E1RestrictedLeaf[] {
  return prefill.leaves.filter((u) => u.autoBucket === null && !(u.code in manualMap))
}

/** 被标「不受限」的叶子（金额计入 F1-5/F1-6 勾稽的差额侧，不隐藏）。 */
export function unrestrictedLeaves(
  prefill: E1RestrictedPrefill,
  manualMap: E1RestrictedManualMap,
): E1RestrictedLeaf[] {
  return prefill.leaves.filter((u) => manualMap[u.code] === E1_UNRESTRICTED)
}

/**
 * 货币资金叶子合计（供 F1-5/F1-6 勾稽：②表合计 = 货币资金 − 现金及现金等价物）。
 *
 * 恒等式：受限合计 + 不受限合计 + 待归类合计 == 本函数返回值。
 */
export function allLeavesTotal(prefill: E1RestrictedPrefill): {
  opening: number
  ending: number
} {
  return {
    opening: prefill.leaves.reduce((s, r) => s + (Number(r.opening) || 0), 0),
    ending: prefill.leaves.reduce((s, r) => s + (Number(r.closing) || 0), 0),
  }
}

/** E1-3 明细行的持久化键（真源在 `useE1BankDetail.STORAGE_KEY`）。 */
export const E1_BANK_DETAIL_ROWS_KEY = 'E1-bank-detail-rows'

/** ②表合计（源 xlsx R23「合  计」；校验预设 F1-4 要求合计 = 明细之和）。 */
export function restrictedTotals(rows: readonly E1RestrictedRow[]): {
  opening: number
  ending: number
} {
  return {
    opening: rows.reduce((s, r) => s + (Number(r.openingAmount) || 0), 0),
    ending: rows.reduce((s, r) => s + (Number(r.endingAmount) || 0), 0),
  }
}

// ─── L2：E1-3 逐户受限归集（源模板 SUMIF 口径）──────────────────────────────

/**
 * ## 两条受限资金链路并存（E-cycle spec R8.1~R8.3 / Property 26）
 *
 * | 链路 | 数据源 | 口径 |
 * |------|--------|------|
 * | **L1**（上方 `resolveRestrictedRows`）| 四表叶子 `restricted_prefill.leaves` | 按**科目名**自动分类 + 人工归类 |
 * | **L2**（本节）| E1-3 持久化行 `E1-bank-detail-rows` | 按**账户性质·主要用途**（D 列）逐户归集 |
 *
 * L2 的源模板依据 = soe 受限表原始公式：
 *
 * ```
 * SUMIF(E1-3!$D$23:$D$28, A17, E1-3!$AB$23:$AB$28)
 *   + SUMIF(E1-3!$D$38:$D$40, A17, E1-3!$AB$38:$AB$40)
 * ```
 *
 * 即「按 D 列（账户性质·主要用途）匹配 ②表 A 列的受限类别名，取 AB 列期末审定人民币」。
 * 平台侧 E1-3 的对应字段是 `accountType`（D 列）与 **`restrictedAmount`（AJ 列）**
 * —— AJ 是审计师专门填的「受限金额」，比 AB 列（该账户全额）更贴合披露口径
 * （一个账户可能只有部分余额受限）。
 *
 * ## 🔴 两条链路不得互相覆盖
 *
 * 代码中**不存在**「取其一覆盖另一」的分支：L2 产出独立行集，只供
 * ①「与 L1 对照勾稽」②「受限原因文本归集」两个用途。哪条是披露主口径由审计师
 * 看勾稽结果后判断（不等时给 `warn` 而非 `error` —— 两个口径本就可能因
 * 「部分受限」「非银行受限项」而不等，那是审计判断不是错报）。
 *
 * ## 🔴 受限原因不进 ②表列（Property 38）
 *
 * ②表列 key 恒为 `['label','end_amount','prior_amount']`（3 列，源模板即 3 列，
 * 既有契约 `e1NoteSubtableContract.spec.ts` 已钉死）。L2 归集出的 `reason` 文本
 * **去重后并入 `_note_texts` 的文字说明段**，加第 4 列会打红既有断言。
 *
 * ## 🔴 数据源不是账户级取数
 *
 * `tb_aux_balance` **没有受限金额字段**（只有余额与维度），故 L2 读的是审计师
 * 在 E1-3 手填的 `restrictedAmount` / `restrictedReason` / `accountType`。
 * ⇒ 本节**不依赖** Task 7 的账户级取数（R8.8）；Task 7 只是让 E1-3 有账户行可填（UX 前提）。
 */

/** E1-3 行的最小形状（只取 L2 需要的字段，与 `useE1BankDetail.BankDetailRow` 子集对齐）。 */
export interface E1BankDetailRowLike {
  /** D 列：账户性质·主要用途 */
  accountType?: string
  /** AJ 列：受限金额（审计师填） */
  restrictedAmount?: number
  /** AK 列：受限原因（审计师填） */
  restrictedReason?: string
  /** 期初（供②表期初列对照；E1-3 的 `opening`） */
  opening?: number
  /** 账号（溯源展示） */
  accountNo?: string
  /** 开户银行（溯源展示） */
  bankName?: string
}

/** L2 归集出的一行（形状与 `E1RestrictedRow` 兼容，另带逐户溯源）。 */
export interface E1RestrictedL2Row {
  bucketKey: string
  label: string
  openingAmount: number
  endingAmount: number
  /** 去重后的受限原因（**不进②表列**，供 `_note_texts` 使用） */
  reasons: string[]
  /** 归集到本行的账户（账号或开户银行，溯源展示） */
  accounts: string[]
}

/** 文本归一：去空白 + 去全/半角括号内容以外的常见噪声，供匹配用。 */
function normalizeNatureText(s: unknown): string {
  return String(s ?? '')
    .replace(/\s+/g, '')
    .replace(/[（）()]/g, '')
    .trim()
}

/**
 * 把 E1-3 的「账户性质·主要用途」文本匹配到受限桶。
 *
 * 🔴 **只用后端 `bucketDefs` 的 label 做双向包含匹配**，前端不抄第二份桶中文名
 * （平台铁律；本文件头已声明）。匹配不上返 `null` —— 由调用方落「未匹配」清单，
 * **既不静默丢弃也不臆造归属**（同 L1 的 `pendingUnclassified` 范式）。
 *
 * 平台补充桶（`isPlatformExtra`，如「其他受限资金」）**不参与自动匹配** ——
 * 它是兜底桶，label 过于宽泛（「其他」会命中大量文本）。
 */
export function matchNatureToBucket(
  natureText: string,
  bucketDefs: readonly E1RestrictedBucketDef[],
): string | null {
  const nature = normalizeNatureText(natureText)
  if (!nature) return null
  // 🔴 按**数组顺序**（= 后端声明序 = 匹配优先级）遍历，不按 displayOrder（展示序）——
  //    两序已分离（Property 36），匹配必须沿用优先级序，否则「信用证保证金」会被
  //    宽标签抢走（同 L1 的 classify_e1_restricted_leaf 口径）。
  for (const d of bucketDefs) {
    if (d.isPlatformExtra || !d.label) continue
    const label = normalizeNatureText(d.label)
    if (!label) continue
    if (nature.includes(label) || label.includes(nature)) return d.key
  }
  return null
}

export interface ResolveRestrictedFromAccountsOptions {
  /** E1-3 持久化行（`E1-bank-detail-rows`） */
  rows: readonly E1BankDetailRowLike[]
  /** render 下发的桶定义（label 唯一真源） */
  bucketDefs: readonly E1RestrictedBucketDef[]
}

export interface RestrictedL2Result {
  rows: E1RestrictedL2Row[]
  /** 有受限金额但性质文本匹配不上任何桶的行（交审计师判断，不臆造归属） */
  unmatched: Array<{ nature: string; amount: number; account: string }>
  totals: { opening: number; ending: number }
}

/**
 * 由 E1-3 逐户行归集出 L2 ②表行。**纯函数。**
 *
 * 判据三条：
 * - **只收 `restrictedAmount !== 0` 的行** —— 未填受限金额的账户不属受限资金
 * - 性质文本匹配不上 → 进 `unmatched`（**不落兜底桶**，与 L1 的待归类同款）
 * - 期初列取 E1-3 的 `opening`**按同一比例**无法推导 ⇒ 如实留 0 并由勾稽提示
 *   （E1-3 没有「期初受限金额」列，源模板亦无该口径）
 */
export function resolveRestrictedFromAccounts(
  opts: ResolveRestrictedFromAccountsOptions,
): RestrictedL2Result {
  const { rows, bucketDefs } = opts
  const agg = new Map<
    string,
    { opening: number; ending: number; reasons: Set<string>; accounts: Set<string> }
  >()
  const unmatched: RestrictedL2Result['unmatched'] = []

  for (const r of rows) {
    const amount = Number(r.restrictedAmount) || 0
    if (amount === 0) continue
    const nature = String(r.accountType ?? '')
    const account = String(r.accountNo || r.bankName || '').trim()
    const bucketKey = matchNatureToBucket(nature, bucketDefs)
    if (!bucketKey) {
      unmatched.push({ nature: normalizeNatureText(nature), amount, account })
      continue
    }
    const cur =
      agg.get(bucketKey) ??
      { opening: 0, ending: 0, reasons: new Set<string>(), accounts: new Set<string>() }
    cur.ending += amount
    const reason = String(r.restrictedReason ?? '').trim()
    if (reason) cur.reasons.add(reason)
    if (account) cur.accounts.add(account)
    agg.set(bucketKey, cur)
  }

  const order = bucketDisplayOrderMap(bucketDefs)
  const out: E1RestrictedL2Row[] = [...agg.entries()]
    .sort((a, b) => (order.get(a[0]) ?? 999) - (order.get(b[0]) ?? 999))
    .map(([bucketKey, v]) => ({
      bucketKey,
      label: resolveBucketLabel(bucketKey, bucketDefs),
      openingAmount: v.opening,
      endingAmount: v.ending,
      reasons: [...v.reasons],
      accounts: [...v.accounts],
    }))

  return {
    rows: out,
    unmatched,
    totals: {
      opening: out.reduce((s, r) => s + r.openingAmount, 0),
      ending: out.reduce((s, r) => s + r.endingAmount, 0),
    },
  }
}

/**
 * 把 L2 归集出的受限原因拼成披露文字段（去重 + 带类别前缀）。
 *
 * 🔴 落点是 `_note_texts` **不是②表第 4 列**（Property 38）。
 * 无原因时返 `''`（调用方据此不追加文字，避免产出「类别：」空壳句）。
 */
export function buildRestrictedReasonText(rows: readonly E1RestrictedL2Row[]): string {
  const parts: string[] = []
  for (const r of rows) {
    if (!r.reasons.length) continue
    parts.push(`${r.label}：${r.reasons.join('；')}`)
  }
  return parts.join('\n')
}

/**
 * 解析 `E1-bank-detail-rows` 的 remark JSON → L2 最小行形状。
 *
 * 容错：非 JSON / 非数组 / 缺字段一律按空处理（不抛）—— 披露表不该因为
 * E1-3 还没编制就崩掉。
 */
export function parseBankDetailRowsForL2(raw: unknown): E1BankDetailRowLike[] {
  if (typeof raw !== 'string' || !raw.trim()) return []
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return []
  }
  if (!Array.isArray(parsed)) return []
  return parsed.map((x) => {
    const r = (x ?? {}) as Record<string, unknown>
    return {
      accountType: String(r.accountType ?? ''),
      restrictedAmount: Number(r.restrictedAmount) || 0,
      restrictedReason: String(r.restrictedReason ?? ''),
      opening: Number(r.opening) || 0,
      accountNo: String(r.accountNo ?? ''),
      bankName: String(r.bankName ?? ''),
    }
  })
}

/**
 * L2 汇总（组件层唯一入口）。
 *
 * 🔴 **无受限行时 `ending` 返 `null` 不是 0** —— 「审计师还没在 E1-3 填 AJ 列」
 * 与「逐户口径确实为 0」必须可区分：前者应让勾稽 `skip`（不误报），
 * 后者才是真实的 0。同款判据见 `e1MainRowPrefill` 的「不写 0」。
 */
export function summarizeRestrictedFromAccounts(
  rows: readonly E1BankDetailRowLike[],
  bucketDefs: readonly E1RestrictedBucketDef[] = [],
): {
  rows: E1RestrictedL2Row[]
  unmatched: RestrictedL2Result['unmatched']
  ending: number | null
  opening: number | null
  reasonText: string
} {
  const res = resolveRestrictedFromAccounts({ rows, bucketDefs })
  const hasAny = res.rows.length > 0 || res.unmatched.length > 0
  // 未匹配行的金额也计入 L2 合计 —— 它们确实是审计师标了受限金额的账户，
  // 只是性质文本归不到桶；不计入会让 L1/L2 对照凭空少一块（假一致）。
  const unmatchedSum = res.unmatched.reduce((s, u) => s + u.amount, 0)
  return {
    rows: res.rows,
    unmatched: res.unmatched,
    ending: hasAny ? res.totals.ending + unmatchedSum : null,
    opening: hasAny ? res.totals.opening : null,
    reasonText: buildRestrictedReasonText(res.rows),
  }
}

// ─── 自定义类别的稳定序号（单调递增，禁复用已删序号）────────────────────────

/**
 * 自定义受限类别的**单调计数器**持久化键。
 *
 * 🔴 为什么需要它（Property 28）：`e1RestrictedRowId(bucketKey, seq)` 的 `seq` 若取
 * 「现有行数」或「现有最大 seq + 1」，删掉 `custom_保证金_3` 再新增又会拿到 `_3`
 * ⇒ 历史 cell/备注（按 row id 索引）串到新类别上，显示别的类别的金额。
 *
 * 与平台既有范式一致（H7 动态列 `{slot}_{seq}` / K2 动态行），差别是那两处踩过
 * 「max+1 会复用」的坑后才补的计数器 —— 这里直接按补强后的口径实现。
 */
export function e1RestrictedSeqKey(variant: 'listed' | 'soe'): string {
  return `E1-disclosure-${variant}-restricted-seq`
}

/**
 * 读回已持久化的单调计数器。**纯函数。**
 *
 * 落库形态是 `checklist_responses.remark`（字符串），故取值必须容忍全部脏形态：
 * `undefined` / `null` / `''` / 非数值 / 负数 / 小数 / 带空格 —— 一律归 `0`
 * （= 「还没有计数器」），由 `nextRestrictedSeq` 退回「现有最大 + 1」。
 *
 * 🔴 **不得抛异常也不得返回 NaN** —— 本函数在 `loadRestricted()` 里被调用，
 * 抛错会让整个②表读回失败（受限行 + 人工归类 map 一起丢）；返回 `NaN` 会让
 * `Math.max(maxSeq, NaN)` 变 `NaN` ⇒ 新增行的 id 变 `restricted_xxx_NaN`，
 * 与历史 id 不同形且后续 `/_(\d+)$/` 再也匹配不到 ⇒ 计数器永久失效。
 *
 * 🔴 负数按 0 处理而不是取绝对值 —— 负计数器只可能来自数据损坏，
 * 取绝对值会凭空造出一个「看起来合法」的高序号。
 *
 * @param storedSeq `e1RestrictedSeqKey` 对应的 remark 原值
 * @returns 非负整数（脏值一律 0）
 */
export function parseRestrictedSeq(storedSeq: unknown): number {
  const n = Number(String(storedSeq ?? '').trim())
  if (!Number.isFinite(n) || n <= 0) return 0
  return Math.floor(n)
}

/**
 * 下一个自定义类别序号 = `max(现有行里的最大 seq, 已存计数器) + 1`。**纯函数。**
 *
 * 两个入参都要看：
 * - `existingRows`：防「计数器还没落库就新增两次」时撞号
 * - `storedSeq`：防「删掉高序号行后 max 回落」时复用（这是本函数存在的理由）
 *
 * 🔴 朴素实现 `max(现有) + 1` 必被守卫打红（守卫用替身复现该形态）。
 *
 * @param existingRows 当前②表行（含四表命中行与自定义行）
 * @param storedSeq 已持久化的计数器（`e1RestrictedSeqKey` 的 remark；非数值按 0）
 */
export function nextRestrictedSeq(
  existingRows: readonly E1RestrictedRow[],
  storedSeq: unknown,
): number {
  let maxSeq = 0
  for (const r of existingRows) {
    // id 形如 `restricted_{slug}_{seq}`；只取尾部数字段
    const m = /_(\d+)$/.exec(String(r.id ?? ''))
    if (!m) continue
    const n = Number(m[1])
    if (Number.isFinite(n) && n > maxSeq) maxSeq = n
  }
  // 🔴 脏值归一走 `parseRestrictedSeq` 单一真源 —— 两处各写一份归一逻辑时，
  //    「读回时判 NaN」与「新增时判 NaN」会漂移（改一处另一处不红）。
  const storedNum = parseRestrictedSeq(storedSeq)
  return Math.max(maxSeq, storedNum) + 1
}

// ─── 待归类面板分区（R8.4）──────────────────────────────────────────────────

/**
 * 「无子科目明细的父科目行」判定。
 *
 * 背景：`restricted_prefill.leaves` 是后端 `select_leaves` 取的**叶子**，但客户科目树
 * 参差 —— 有的项目 `1002` 不分户（叶子就是一级科目本身，如 `1002 银行存款`），
 * 这类行出现在「待归类」面板里语义与真明细行完全不同：
 *
 * | 类型 | 形态 | 审计师该怎么处理 |
 * |------|------|------------------|
 * | 父科目行 | 码为 4 位一级码（无点号/横杠分隔） | 该科目未分户 ⇒ 通常整体判「不受限」或按 E1-3 逐户口径（L2）处理 |
 * | 真明细行 | 码带 `.` 或 `-` 分隔（如 `1002.03`）| 逐个归类到受限类别 |
 *
 * 🔴 判据只看**码的形态**不看金额大小 —— 金额大的父科目与金额小的明细行在语义上
 * 没有可比性，按金额分区会把「小额分户」误判成父科目。
 *
 * 🔴 **不做「父子包含关系」推断** —— 后端已保证下发的是叶子，若同时出现 `1002`
 * 与 `1002.01` 那是数据问题（父子双算），应由 `parent_check` 暴露而不是在这里猜。
 */
export function isParentLikeLeaf(leaf: Pick<E1RestrictedLeaf, 'code'>): boolean {
  const code = String(leaf.code ?? '').trim()
  if (!code) return false
  return !/[.\-]/.test(code)
}

/**
 * 待归类叶子分区（父科目行 / 真明细行）。**纯函数。**
 *
 * 两区都要展示（不隐藏任何一侧）—— 隐藏父科目行会让「该科目未分户」这一事实
 * 消失，审计师看不到就不会去 E1-3 逐户填（L2 链路的入口）。
 */
export function partitionUnclassified(leaves: readonly E1RestrictedLeaf[]): {
  parents: E1RestrictedLeaf[]
  details: E1RestrictedLeaf[]
} {
  const parents: E1RestrictedLeaf[] = []
  const details: E1RestrictedLeaf[] = []
  for (const l of leaves) {
    if (isParentLikeLeaf(l)) parents.push(l)
    else details.push(l)
  }
  return { parents, details }
}
