/**
 * useN1DisclosureTables — N1 披露表（上市 / 国企共用）编制模型
 *
 * 把两张披露 sheet 的**源模板结构**收敛到一处：行骨架、列序、分段小计公式、
 * N1-2/N1-5 预填、持久化键、勾稽入参、同步载荷组装。两个 Tab 组件只负责渲染。
 *
 * 源模板权威 = `backend/wp_templates/N/N1 递延所得税资产.xlsx`
 * （`附注披露信息（上市公司）` A1:K54 / `附注披露信息（国企）` A1:IV74），
 * 结论固化在 spec `n1-deferred-tax-disclosure-template-alignment` design.md §1。
 *
 * 🔴 不得在此之外另造披露小节：现有实现曾自造「余额变动表」「与 N3 对应关系」
 * 两张源模板没有的表，且把 N1-2 的审计过程列（账面价值/计税基础/确认依据）
 * 搬进披露表 —— 披露表只放交付物内容，审计过程留在 N1-2 / N1-4。
 */
import { computed, ref, type Ref } from 'vue'
import {
  N1_GROUP_LABELS,
  N1_SUBTOTAL_LABEL,
  N1_TOTAL_LABEL,
  N1_UNOFFSET_GROUPS,
  buildN1SyncPayload,
  n1UnoffsetSubOrder,
  type N1DisclosureSnapshot,
  type N1DisclosureVariant,
  type N1NetOffsetItemRow,
  type N1UnoffsetItemRow,
  type NullableAmount,
} from './n1NoteSectionMap'
import {
  runN1DisclosureChecks,
  type N1CheckResult,
  type N1CheckSegment,
} from './n1DisclosureConsistency'
import { deriveDisclosureDetailRows, deriveUnrecognizedLossPayload } from './useN1DisclosureSource'
import type { N1SegColumn, N1Segment } from './shared/disclosureSegmentTypes'

// ─── 源模板行骨架 ────────────────────────────────────────────────────────────

/** 表 1 资产段 7 项（上市 R13~R19；国企 R13~R19 公式引用上市同列） */
export const N1_ASSET_ITEMS = [
  '资产减值准备',
  '可抵扣亏损',
  '内部交易未实现利润',
  '公允价值变动',
  '租赁负债',
  '购入摊销年限小于税法规定的资产',
  '其他',
] as const

/**
 * 表 1 负债段 5 项（上市 R23~R27 / 国企 R23~R27）。
 * 🔴 第 4 项两版不同：上市 `使用权资产`，国企 `租赁形成`。
 */
export const N1_LIABILITY_ITEMS: Record<N1DisclosureVariant, readonly string[]> = {
  listed: [
    '购入摊销年限大于税法规定的资产',
    '可供出售金融资产公允价值变动',
    '投资性房地产公允价值变动',
    '使用权资产',
    '其他',
  ],
  soe: [
    '购入摊销年限大于税法规定的资产',
    '可供出售金融资产公允价值变动',
    '投资性房地产公允价值变动',
    '租赁形成',
    '其他',
  ],
}

/** 未确认明细两行（上市 R39/R40 / 国企 R61/R62） */
export const N1_UNRECOGNIZED_ITEMS = ['可抵扣暂时性差异', '可抵扣亏损'] as const

/** 表 2（上市）两行（R35/R36） */
export const N1_NET_OFFSET_ROWS_LISTED = ['递延所得税资产', '递延所得税负债'] as const

/** 可抵扣亏损结转期限（税法一般 5 年；高新 / 科技型中小企业 10 年，用增行处理） */
const LOSS_CARRY_FORWARD_YEARS = 5

// ─── 行模型 ──────────────────────────────────────────────────────────────────

export interface UnoffsetRowModel extends N1UnoffsetItemRow {
  /** true = 用户动态新增（行名可编辑 + 可删除） */
  _editableLabel?: boolean
}

export interface NetOffsetRowModel extends N1NetOffsetItemRow {
  _editableLabel?: boolean
}

export interface NetOffsetListedRowModel {
  item: string
  offsetEnd: NullableAmount
  netEnd: NullableAmount
  offsetPrior: NullableAmount
  netPrior: NullableAmount
}

export interface OffsetDetailRowModel {
  item: string
  amount: NullableAmount
  _editableLabel?: boolean
}

export interface UnrecognizedRowModel {
  item: string
  end: NullableAmount
  prior: NullableAmount
}

export interface LossExpiryRowModel {
  item: string
  end: NullableAmount
  prior: NullableAmount
  remark: string
  _editableLabel?: boolean
}

// ─── 持久化键 ────────────────────────────────────────────────────────────────

export function n1DisclosureItemIds(variant: N1DisclosureVariant) {
  const p = `N1-disclosure-${variant}`
  return {
    unoffset: `${p}-unoffset`,
    netOffset: `${p}-netoffset`,
    offsetDetail: `${p}-offsetdetail`,
    unrecognized: `${p}-unrecognized`,
    lossExpiry: `${p}-lossexpiry`,
    rollbackNote: `${p}-rollback-note`,
    conclusion: `${p}-conclusion`,
    syncedTables: `${p}-synced-tables`,
  } as const
}

// ─── 列定义（供 N1DisclosureSegmentTable） ───────────────────────────────────

const AMT = 'amount' as const

/** 表 1：两级表头，子列序由 `n1UnoffsetSubOrder` 单一真源给出 */
export function n1UnoffsetSegColumns(variant: N1DisclosureVariant): N1SegColumn[] {
  const g = N1_UNOFFSET_GROUPS[variant]
  const order = n1UnoffsetSubOrder(variant)
  return [
    ...order.map(([k, label]) => ({
      key: k === 'diff' ? 'endDiff' : 'endTax',
      label,
      group: g.end,
      format: AMT,
      minWidth: 170,
    })),
    ...order.map(([k, label]) => ({
      key: k === 'diff' ? 'priorDiff' : 'priorTax',
      label,
      group: g.prior,
      format: AMT,
      minWidth: 170,
    })),
  ]
}

/** 表 2（上市）：互抵金额 + 抵销后余额（源模板 R34） */
export function n1NetOffsetSegColumnsListed(): N1SegColumn[] {
  return [
    { key: 'offsetEnd', label: '递延所得税资产和负债期末互抵金额', format: AMT, minWidth: 200 },
    { key: 'netEnd', label: '抵销后递延所得税资产或负债期末余额', format: AMT, minWidth: 200 },
    { key: 'offsetPrior', label: '递延所得税资产和负债期初互抵金额', format: AMT, minWidth: 200 },
    { key: 'netPrior', label: '抵销后递延所得税资产或负债期初余额', format: AMT, minWidth: 200 },
  ]
}

/** 表 2（国企）：互抵后资产/负债 + 互抵后暂时性差异（源模板 R34） */
export function n1NetOffsetSegColumnsSoe(): N1SegColumn[] {
  return [
    { key: 'netEnd', label: '报告期末互抵后的递延所得税资产或负债', format: AMT, minWidth: 200 },
    { key: 'diffEnd', label: '报告期末互抵后的可抵扣或应纳税暂时性差异', format: AMT, minWidth: 210 },
    { key: 'netPrior', label: '报告年初互抵后的递延所得税资产或负债', format: AMT, minWidth: 200 },
    { key: 'diffPrior', label: '报告年初互抵后的可抵扣或应纳税暂时性差异', format: AMT, minWidth: 210 },
  ]
}

/** 表 3（国企）互抵明细（源模板（2）B，R55） */
export function n1OffsetDetailSegColumns(): N1SegColumn[] {
  return [{ key: 'amount', label: '本期互抵金额', format: AMT, minWidth: 180 }]
}

/** 未确认明细（上市 R38 / 国企 R60） */
export function n1UnrecognizedSegColumns(variant: N1DisclosureVariant): N1SegColumn[] {
  return [
    { key: 'end', label: '期末余额', format: AMT, minWidth: 170 },
    {
      key: 'prior',
      label: variant === 'listed' ? '上年年末余额' : '年初余额',
      format: AMT,
      minWidth: 170,
    },
  ]
}

/** 亏损到期（上市 R45 / 国企 R65） */
export function n1LossExpirySegColumns(variant: N1DisclosureVariant): N1SegColumn[] {
  return [
    { key: 'end', label: '期末余额', format: AMT, minWidth: 160 },
    {
      key: 'prior',
      label: variant === 'listed' ? '上年年末余额' : '年初余额',
      format: AMT,
      minWidth: 160,
    },
    { key: 'remark', label: '备注', format: 'text', minWidth: 180, placeholder: '如：——' },
  ]
}

// ─── 工具 ────────────────────────────────────────────────────────────────────

const nz = (v: unknown): NullableAmount =>
  typeof v === 'number' && Number.isFinite(v) ? v : null

function sumNullable(vals: readonly NullableAmount[]): NullableAmount {
  let has = false
  let total = 0
  for (const v of vals) {
    if (v === null || v === undefined) continue
    has = true
    total += v
  }
  return has ? Math.round(total * 100) / 100 : null
}

function parseJsonArray<T>(raw: unknown): T[] | null {
  if (typeof raw !== 'string' || !raw) return null
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as T[]) : null
  } catch {
    return null
  }
}

function parseJsonObject<T>(raw: unknown): T | null {
  if (typeof raw !== 'string' || !raw) return null
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as T) : null
  } catch {
    return null
  }
}

// ─── 骨架构造 ────────────────────────────────────────────────────────────────

function blankUnoffsetRow(item: string, editable = false): UnoffsetRowModel {
  return {
    item,
    endDiff: null,
    endTax: null,
    priorDiff: null,
    priorTax: null,
    ...(editable ? { _editableLabel: true } : {}),
  }
}

function blankNetOffsetRow(item: string, editable = false): NetOffsetRowModel {
  return {
    item,
    netEnd: null,
    diffEnd: null,
    netPrior: null,
    diffPrior: null,
    ...(editable ? { _editableLabel: true } : {}),
  }
}

/** 亏损到期默认年度骨架：审计年度后 5 年（税法一般结转期限） */
export function defaultLossExpiryRows(auditYear: number): LossExpiryRowModel[] {
  return Array.from({ length: LOSS_CARRY_FORWARD_YEARS }, (_, i) => ({
    item: `${auditYear + i + 1}年`,
    end: null,
    prior: null,
    remark: '',
  }))
}

// ─── 主 composable ───────────────────────────────────────────────────────────

export interface UseN1DisclosureTablesOptions {
  variant: N1DisclosureVariant
  allResponses: Ref<Map<string, { conclusion?: string | null; remark?: string | null }>>
  auditYear: Ref<number>
}

export function useN1DisclosureTables(opts: UseN1DisclosureTablesOptions) {
  const { variant, allResponses, auditYear } = opts
  const ID = n1DisclosureItemIds(variant)
  const G = N1_GROUP_LABELS[variant]

  // ── 表 1 ──────────────────────────────────────────────────────────────────
  const assetRows = ref<UnoffsetRowModel[]>([])
  const liabilityRows = ref<UnoffsetRowModel[]>([])

  // ── 表 2 ──────────────────────────────────────────────────────────────────
  const netOffsetListed = ref<NetOffsetListedRowModel[]>([])
  const netOffsetAssetRows = ref<NetOffsetRowModel[]>([])
  const netOffsetLiabilityRows = ref<NetOffsetRowModel[]>([])

  // ── 表 3（国企） ──────────────────────────────────────────────────────────
  const offsetDetailRows = ref<OffsetDetailRowModel[]>([])

  // ── 表 4 / 5 ──────────────────────────────────────────────────────────────
  const unrecognizedRows = ref<UnrecognizedRowModel[]>([])
  const lossExpiryRows = ref<LossExpiryRowModel[]>([])

  // ── 文本 ──────────────────────────────────────────────────────────────────
  const rollbackNote = ref('')
  const conclusionNote = ref('')
  const syncedTables = ref<string[]>([])

  /**
   * N1-2 明细按「类别」聚合，用于表 1 资产段预填。
   *
   * 🔴 宁缺勿造：N1-2 的类别枚举只有 {资产减值准备, 可抵扣亏损, 公允价值变动, 其他}，
   * 与披露 7 项**不是全映射** —— 只对**逐字同名**的披露行预填，
   * 其余 3 项（内部交易未实现利润 / 租赁负债 / 购入摊销年限小于税法规定的资产）留人工。
   */
  const detailByCategory = computed(() => {
    const map = new Map<string, { endDiff: number; endTax: number; priorDiff: number; priorTax: number }>()
    for (const r of deriveDisclosureDetailRows(allResponses.value)) {
      const key = String(r.category || '').trim()
      if (!key) continue
      const slot = map.get(key) || { endDiff: 0, endTax: 0, priorDiff: 0, priorTax: 0 }
      slot.endDiff += r.deductibleDiff
      slot.endTax += r.endBalance
      slot.priorDiff += r.beginDiff
      slot.priorTax += r.beginBalance
      map.set(key, slot)
    }
    return map
  })

  /** N1-5 未确认亏损供数（Req 4.1，新模型键无行时 hasData=false） */
  const lossPayload = computed(() => deriveUnrecognizedLossPayload(allResponses.value))

  // ── 加载 ──────────────────────────────────────────────────────────────────

  function restore(): void {
    const unoffset = parseJsonObject<{ asset?: UnoffsetRowModel[]; liability?: UnoffsetRowModel[] }>(
      allResponses.value.get(ID.unoffset)?.conclusion,
    )
    assetRows.value = unoffset?.asset?.length
      ? unoffset.asset
      : N1_ASSET_ITEMS.map((n) => blankUnoffsetRow(n))
    liabilityRows.value = unoffset?.liability?.length
      ? unoffset.liability
      : N1_LIABILITY_ITEMS[variant].map((n) => blankUnoffsetRow(n))

    // 未持久化的行按 N1-2 类别预填（已编辑过的不覆盖）
    if (!unoffset?.asset?.length) applyDetailPrefill()

    if (variant === 'listed') {
      const saved = parseJsonArray<NetOffsetListedRowModel>(
        allResponses.value.get(ID.netOffset)?.conclusion,
      )
      netOffsetListed.value = saved?.length
        ? saved
        : N1_NET_OFFSET_ROWS_LISTED.map((item) => ({
            item,
            offsetEnd: null,
            netEnd: null,
            offsetPrior: null,
            netPrior: null,
          }))
    } else {
      const saved = parseJsonObject<{
        asset?: NetOffsetRowModel[]
        liability?: NetOffsetRowModel[]
      }>(allResponses.value.get(ID.netOffset)?.conclusion)
      netOffsetAssetRows.value = saved?.asset?.length
        ? saved.asset
        : N1_ASSET_ITEMS.map((n) => blankNetOffsetRow(n))
      netOffsetLiabilityRows.value = saved?.liability?.length
        ? saved.liability
        : N1_LIABILITY_ITEMS.soe.map((n) => blankNetOffsetRow(n))

      offsetDetailRows.value =
        parseJsonArray<OffsetDetailRowModel>(allResponses.value.get(ID.offsetDetail)?.conclusion) ?? []
    }

    const savedUnrec = parseJsonArray<UnrecognizedRowModel>(
      allResponses.value.get(ID.unrecognized)?.conclusion,
    )
    unrecognizedRows.value = savedUnrec?.length
      ? savedUnrec
      : N1_UNRECOGNIZED_ITEMS.map((item) => ({ item, end: null, prior: null }))

    const savedLoss = parseJsonArray<LossExpiryRowModel>(
      allResponses.value.get(ID.lossExpiry)?.conclusion,
    )
    lossExpiryRows.value = savedLoss?.length ? savedLoss : defaultLossExpiryRows(auditYear.value)
    applyLossPrefill()

    rollbackNote.value = allResponses.value.get(ID.rollbackNote)?.remark || ''
    conclusionNote.value = allResponses.value.get(ID.conclusion)?.remark || ''
    syncedTables.value =
      parseJsonArray<string>(allResponses.value.get(ID.syncedTables)?.conclusion) ?? []
  }

  /** 表 1 资产段按 N1-2 类别预填（只填逐字同名行，且只在该行四值全空时） */
  function applyDetailPrefill(): void {
    const byCat = detailByCategory.value
    if (byCat.size === 0) return
    assetRows.value = assetRows.value.map((r) => {
      const src = byCat.get(r.item)
      const untouched =
        r.endDiff === null && r.endTax === null && r.priorDiff === null && r.priorTax === null
      if (!src || !untouched) return r
      return {
        ...r,
        endDiff: src.endDiff || null,
        endTax: src.endTax || null,
        priorDiff: src.priorDiff || null,
        priorTax: src.priorTax || null,
      }
    })
  }

  /**
   * 亏损到期表按 N1-5 不确认口径预填。
   *
   * N1-5 有数据时按到期年度覆盖对应行金额（不新增行则追加缺失年度），
   * 无数据时保持骨架（`hasData=false` 时不写 0，见 spec R5.5）。
   */
  function applyLossPrefill(): void {
    const payload = lossPayload.value
    if (!payload.hasData || payload.rows.length === 0) return
    const rows = [...lossExpiryRows.value]
    for (const src of payload.rows) {
      const label = /年$/.test(src.expiryYear) ? src.expiryYear : `${src.expiryYear}年`
      const idx = rows.findIndex((r) => r.item === label)
      const patch = {
        end: nz(src.unrecognized),
        prior: nz(src.priorUnrecognized),
        remark: src.reason || '',
      }
      if (idx >= 0) rows[idx] = { ...rows[idx], ...patch }
      else rows.push({ item: label, _editableLabel: true, ...patch })
    }
    rows.sort((a, b) => String(a.item).localeCompare(String(b.item), 'zh-CN'))
    lossExpiryRows.value = rows

    // 未确认明细「可抵扣亏损」行同源（源模板 B40=B52 勾稽的左侧）
    const idx = unrecognizedRows.value.findIndex((r) => r.item.includes('可抵扣亏损'))
    if (idx >= 0) {
      unrecognizedRows.value[idx] = {
        ...unrecognizedRows.value[idx],
        end: nz(payload.totalUnrecognized),
        prior: nz(payload.totalPriorUnrecognized),
      }
    }
  }

  // ── 小计 / 合计（源模板公式） ─────────────────────────────────────────────

  function unoffsetSubtotal(rows: readonly UnoffsetRowModel[]): Record<string, number | null> {
    return {
      endDiff: sumNullable(rows.map((r) => nz(r.endDiff))),
      endTax: sumNullable(rows.map((r) => nz(r.endTax))),
      priorDiff: sumNullable(rows.map((r) => nz(r.priorDiff))),
      priorTax: sumNullable(rows.map((r) => nz(r.priorTax))),
    }
  }

  function netOffsetSubtotal(rows: readonly NetOffsetRowModel[]): Record<string, number | null> {
    return {
      netEnd: sumNullable(rows.map((r) => nz(r.netEnd))),
      diffEnd: sumNullable(rows.map((r) => nz(r.diffEnd))),
      netPrior: sumNullable(rows.map((r) => nz(r.netPrior))),
      diffPrior: sumNullable(rows.map((r) => nz(r.diffPrior))),
    }
  }

  const assetSubtotal = computed(() => unoffsetSubtotal(assetRows.value))
  const liabilitySubtotal = computed(() => unoffsetSubtotal(liabilityRows.value))
  const netOffsetAssetSubtotal = computed(() => netOffsetSubtotal(netOffsetAssetRows.value))
  const netOffsetLiabilitySubtotal = computed(() => netOffsetSubtotal(netOffsetLiabilityRows.value))

  /** 未确认明细合计（源模板 =B39+B40） */
  const unrecognizedTotal = computed(() => ({
    end: sumNullable(unrecognizedRows.value.map((r) => nz(r.end))),
    prior: sumNullable(unrecognizedRows.value.map((r) => nz(r.prior))),
  }))

  /** 亏损到期合计（源模板 =SUM(B46:B51)） */
  const lossExpiryTotal = computed(() => ({
    end: sumNullable(lossExpiryRows.value.map((r) => nz(r.end))),
    prior: sumNullable(lossExpiryRows.value.map((r) => nz(r.prior))),
  }))

  // ── 勾稽 ──────────────────────────────────────────────────────────────────

  /** 表 1 校验取「递延所得税资产/负债」期末列（源模板小计公式所在列） */
  function seg(rows: readonly UnoffsetRowModel[], subtotal: Record<string, number | null>): N1CheckSegment {
    return { details: rows.map((r) => nz(r.endTax)), subtotal: subtotal.endTax ?? null }
  }

  const checks = computed<N1CheckResult[]>(() => {
    const u = unrecognizedRows.value
    const diffRow = u.find((r) => r.item.includes('暂时性差异'))
    const lossRow = u.find((r) => r.item.includes('可抵扣亏损'))
    return runN1DisclosureChecks(variant, {
      unoffsetAsset: seg(assetRows.value, assetSubtotal.value),
      unoffsetLiability: seg(liabilityRows.value, liabilitySubtotal.value),
      ...(variant === 'soe'
        ? {
            netOffsetAsset: {
              details: netOffsetAssetRows.value.map((r) => nz(r.netEnd)),
              subtotal: netOffsetAssetSubtotal.value.netEnd ?? null,
            },
            netOffsetLiability: {
              details: netOffsetLiabilityRows.value.map((r) => nz(r.netEnd)),
              subtotal: netOffsetLiabilitySubtotal.value.netEnd ?? null,
            },
          }
        : {}),
      unrecognized: {
        temporaryDiff: nz(diffRow?.end),
        deductibleLoss: nz(lossRow?.end),
        total: unrecognizedTotal.value.end,
        priorTemporaryDiff: nz(diffRow?.prior),
        priorDeductibleLoss: nz(lossRow?.prior),
        priorTotal: unrecognizedTotal.value.prior,
      },
      lossExpiry: {
        yearAmounts: lossExpiryRows.value.map((r) => nz(r.end)),
        total: lossExpiryTotal.value.end,
        priorYearAmounts: lossExpiryRows.value.map((r) => nz(r.prior)),
        priorTotal: lossExpiryTotal.value.prior,
      },
    })
  })

  // ── 段（供 N1DisclosureSegmentTable 渲染） ────────────────────────────────

  /** 行模型 → 渲染契约（`N1SegRow` 的索引签名比具体模型宽，故显式收窄） */
  const asSegRows = (rows: readonly object[]): N1Segment['rows'] =>
    rows as unknown as N1Segment['rows']

  const unoffsetSegments = computed<N1Segment[]>(() => [
    {
      key: 'asset',
      label: G.asset,
      rows: asSegRows(assetRows.value),
      subtotal: assetSubtotal.value,
      subtotalLabel: N1_SUBTOTAL_LABEL,
    },
    {
      key: 'liability',
      label: G.liability,
      rows: asSegRows(liabilityRows.value),
      subtotal: liabilitySubtotal.value,
      subtotalLabel: N1_SUBTOTAL_LABEL,
    },
  ])

  const netOffsetSegmentsSoe = computed<N1Segment[]>(() => [
    {
      key: 'asset',
      label: G.asset,
      rows: asSegRows(netOffsetAssetRows.value),
      subtotal: netOffsetAssetSubtotal.value,
      subtotalLabel: N1_SUBTOTAL_LABEL,
    },
    {
      key: 'liability',
      label: G.liability,
      rows: asSegRows(netOffsetLiabilityRows.value),
      subtotal: netOffsetLiabilitySubtotal.value,
      subtotalLabel: N1_SUBTOTAL_LABEL,
    },
  ])

  const netOffsetSegmentsListed = computed<N1Segment[]>(() => [
    { key: 'main', label: '', rows: asSegRows(netOffsetListed.value), subtotal: null },
  ])

  const offsetDetailSegments = computed<N1Segment[]>(() => [
    { key: 'main', label: '', rows: asSegRows(offsetDetailRows.value), subtotal: null },
  ])

  const unrecognizedSegments = computed<N1Segment[]>(() => [
    {
      key: 'main',
      label: '',
      rows: asSegRows(unrecognizedRows.value),
      subtotal: unrecognizedTotal.value,
      subtotalLabel: N1_TOTAL_LABEL,
    },
  ])

  const lossExpirySegments = computed<N1Segment[]>(() => [
    {
      key: 'main',
      label: '',
      rows: asSegRows(lossExpiryRows.value),
      // 合计行的「备注」列无值（源模板 D52 空）
      subtotal: { end: lossExpiryTotal.value.end, prior: lossExpiryTotal.value.prior },
      subtotalLabel: N1_TOTAL_LABEL,
    },
  ])

  // ── 载荷 ──────────────────────────────────────────────────────────────────

  function buildSnapshot(): N1DisclosureSnapshot {
    const strip = <T extends { _editableLabel?: boolean }>(r: T): Omit<T, '_editableLabel'> => {
      const { _editableLabel, ...rest } = r
      return rest
    }
    return {
      assetRows: assetRows.value.map(strip) as N1UnoffsetItemRow[],
      liabilityRows: liabilityRows.value.map(strip) as N1UnoffsetItemRow[],
      ...(variant === 'listed'
        ? {
            netOffset: {
              assetOffsetEnd: nz(netOffsetListed.value[0]?.offsetEnd),
              assetNetEnd: nz(netOffsetListed.value[0]?.netEnd),
              assetOffsetPrior: nz(netOffsetListed.value[0]?.offsetPrior),
              assetNetPrior: nz(netOffsetListed.value[0]?.netPrior),
              liabOffsetEnd: nz(netOffsetListed.value[1]?.offsetEnd),
              liabNetEnd: nz(netOffsetListed.value[1]?.netEnd),
              liabOffsetPrior: nz(netOffsetListed.value[1]?.offsetPrior),
              liabNetPrior: nz(netOffsetListed.value[1]?.netPrior),
            },
          }
        : {
            netOffsetAssetRows: netOffsetAssetRows.value.map(strip) as N1NetOffsetItemRow[],
            netOffsetLiabilityRows: netOffsetLiabilityRows.value.map(strip) as N1NetOffsetItemRow[],
            offsetDetailRows: offsetDetailRows.value.map((r) => ({ item: r.item, amount: nz(r.amount) })),
          }),
      unrecognizedRows: unrecognizedRows.value.map((r) => ({
        item: r.item,
        amount: nz(r.end),
        priorAmount: nz(r.prior),
      })),
      lossExpiryRows: lossExpiryRows.value.map((r) => ({
        expiryYear: r.item,
        unrecovered: nz(r.end),
        priorUnrecovered: nz(r.prior),
        remark: r.remark || '',
      })),
      notes: {
        ...(rollbackNote.value.trim() ? { rollback: rollbackNote.value } : {}),
        ...(conclusionNote.value.trim() ? { conclusion: conclusionNote.value } : {}),
      },
      previouslySyncedTables: syncedTables.value,
    }
  }

  function buildPayload(ctx: { wpId: string; year: number }) {
    return buildN1SyncPayload(variant, buildSnapshot(), ctx)
  }

  // ── 行增删 ────────────────────────────────────────────────────────────────

  function addUnoffsetRow(segKey: string): void {
    const target = segKey === 'asset' ? assetRows : liabilityRows
    target.value = [...target.value, blankUnoffsetRow('', true)]
  }

  function addNetOffsetRow(segKey: string): void {
    const target = segKey === 'asset' ? netOffsetAssetRows : netOffsetLiabilityRows
    target.value = [...target.value, blankNetOffsetRow('', true)]
  }

  function addOffsetDetailRow(): void {
    offsetDetailRows.value = [
      ...offsetDetailRows.value,
      { item: '', amount: null, _editableLabel: true },
    ]
  }

  function addLossExpiryRow(): void {
    lossExpiryRows.value = [
      ...lossExpiryRows.value,
      { item: '', end: null, prior: null, remark: '', _editableLabel: true },
    ]
  }

  return {
    // 模型
    assetRows,
    liabilityRows,
    netOffsetListed,
    netOffsetAssetRows,
    netOffsetLiabilityRows,
    offsetDetailRows,
    unrecognizedRows,
    lossExpiryRows,
    rollbackNote,
    conclusionNote,
    syncedTables,
    // 公式
    assetSubtotal,
    liabilitySubtotal,
    netOffsetAssetSubtotal,
    netOffsetLiabilitySubtotal,
    unrecognizedTotal,
    lossExpiryTotal,
    // 渲染段
    unoffsetSegments,
    netOffsetSegmentsListed,
    netOffsetSegmentsSoe,
    offsetDetailSegments,
    unrecognizedSegments,
    lossExpirySegments,
    // 勾稽
    checks,
    // 行操作
    addUnoffsetRow,
    addNetOffsetRow,
    addOffsetDetailRow,
    addLossExpiryRow,
    // 生命周期 / 载荷
    restore,
    applyDetailPrefill,
    applyLossPrefill,
    buildSnapshot,
    buildPayload,
    itemIds: ID,
    lossPayload,
  }
}
