/**
 * hCycleAdjudicationSeed — H 类审定表「从四表库带入未审数」的声明与归类（per-cycle 薄壳）。
 *
 * **要解决的缺陷**
 *
 * 后端 `four_table/h_cycle_adjudication_prefill.py` 产出的
 * `html_data.adjudication_segment_prefill` 在改造前是**全平台零消费方的 dead output**
 * —— H5~H10 六个循环的 render 都在产它（每次 render 花若干条 DB 查询），
 * 而 `HiFourTableSourcePanel` 读的是静态 registry + 锚点值，**根本不读这个键**；
 * H1~H4 更是连产出都因调用签名不匹配而静默失败（见该 py 的 docstring）。
 *
 * 本模块补上消费侧：把「逐叶子明细」按**科目名称**归类到各循环审定表的行，
 * 再交平台共享件 `shared/adjudicationPrefillPlan` 做 plan → resolve → describe。
 *
 * **三条口径（每条都对应一个已实测的缺陷形态）**
 *
 * 1. **按名称归类，不按编码** —— 客户子科目编码语义在项目间冲突（memory 已记
 *    存货 14xx / 6403 税种 / 1123 性质三例），只有科目名是稳定判据。
 * 2. **顺序即优先级 + 否决词** —— `其他` 一类宽兜底规则必须排在最后；
 *    `投资性房地产累计折旧` 含「投资性房地产」，故具体规则要能否决泛化规则。
 * 3. **未命中不兜底** —— `defaults` 恒为空数组，未命中的叶子进 `unclassified`
 *    面板由审计师显式归入（G11 已确立范式：自动路径不兜底，显式归入是独立处理器 + 确认框）。
 *
 * 本模块是**纯函数、零 Vue 依赖**，便于单测与跨文件交叉锁死。
 *
 * spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
 *       Requirements 4.1~4.6 / Property 7~8
 */
import type {
  AdjPrefillCell,
  AdjPrefillUnclassified,
} from './shared/adjudicationPrefillPlan'

// ═══════════════════════════════════════════════════════════════════════════
// 后端载荷契约（`adjudication_segment_prefill`）
// ═══════════════════════════════════════════════════════════════════════════

/** 后端 `build_d_adjudication_prefill(mode='balance')` 的一行 */
export interface HPrefillBalanceItem {
  code: string
  name: string
  opening_balance: number
  closing_balance: number
}

/** 后端 `build_d_adjudication_prefill(mode='occurrence')` 的一行 */
export interface HPrefillOccurrenceItem {
  code: string
  name: string
  debit_amount: number
  credit_amount: number
}

export type HPrefillItem = HPrefillBalanceItem | HPrefillOccurrenceItem

/** 一个语义槽的一段（后端逐槽逐码产出） */
export interface HPrefillSegment {
  segment: string
  account_prefix: string
  mode: 'balance' | 'occurrence'
  items: HPrefillItem[]
}

/** `html_data.adjudication_segment_prefill` 整体 */
export interface HSegmentPrefill {
  segments: HPrefillSegment[]
  enabled: boolean
}

// ═══════════════════════════════════════════════════════════════════════════
// 归类声明
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 一条归类规则：把「科目名命中关键词」的叶子归到某个审定表行。
 *
 * 🔴 `RULES` 数组**顺序即优先级**，第一条命中即停。
 */
export interface HRowRule {
  /** 审定表行键（与该循环 composable 的 `rowId` 对齐） */
  rowKey: string
  /** 行中文名（提示文案 / 冲突清单 / 待归类面板用） */
  label: string
  /** 命中关键词（任一命中即算候选） */
  keywords: readonly string[]
  /** 否决词（命中任一即**不**归入本行，用于让具体规则压过泛化规则） */
  excludeKeywords?: readonly string[]
}

/** 一个槽对应的目标列字段（期初 / 期末各一格） */
export interface HSlotFieldMap {
  /** 后端 segment 名（= `H{n}_SLOT_KEY_PREFIX` 的键） */
  slotKey: string
  /** 槽中文名（`absentSlots` 提示用） */
  slotLabel: string
  /** 期初列字段名；不声明则不产出期初格 */
  openingField?: string
  /** 期末列字段名 */
  closingField: string
  /** 期初列中文名 */
  openingLabel?: string
  /** 期末列中文名 */
  closingLabel: string
}

/** 一个循环的完整声明 */
export interface HSeedSpec {
  cycle: 'H1' | 'H2' | 'H3' | 'H4' | 'H5' | 'H6' | 'H7' | 'H8' | 'H9' | 'H10'
  /** 行归类规则（顺序即优先级） */
  rules: readonly HRowRule[]
  /** 槽 → 列字段映射 */
  slots: readonly HSlotFieldMap[]
  /**
   * 未命中时的默认落点。
   *
   * 🔴 **恒为空数组**：H 类不做自动兜底（R4.3「宁缺勿造」）。
   * 保留该字段是为了让守卫能正向断言「它确实是空的」，
   * 而不是靠「源码里没有这个字段」这种弱判据。
   */
  defaults: readonly never[]
}

// ─── H2 在建工程（1604）───────────────────────────────────────────────────
// 源模板 H2-1 按**工程项目**分行（动态行），四表叶子名即工程名 ⇒ 规则表为空，
// 全部叶子进 unclassified 由审计师逐个建行归入（动态行需命名，
// 平台铁律：ElMessageBox.prompt 输入名称再创建）。
const H2_SPEC: HSeedSpec = {
  cycle: 'H2',
  rules: [],
  slots: [
    {
      slotKey: 'gross',
      slotLabel: '在建工程原值',
      openingField: 'beginUnadjusted',
      closingField: 'endUnadjusted',
      openingLabel: '期初未审',
      closingLabel: '期末未审',
    },
  ],
  defaults: [],
}

// ─── H3 投资性房地产（1521 / 1525 / 1526 / 1527）─────────────────────────
// 源模板 H3-1（成本模式）按**房地产类别**分行；三个备抵槽各自成表。
const H3_CATEGORY_RULES: readonly HRowRule[] = [
  {
    rowKey: 'building',
    label: '房屋、建筑物',
    keywords: ['房屋', '建筑物', '厂房', '楼'],
  },
  {
    rowKey: 'land',
    label: '土地使用权',
    keywords: ['土地'],
  },
  // 宽兜底放最后
  {
    rowKey: 'other',
    label: '其他',
    keywords: ['其他'],
  },
]

const H3_SPEC: HSeedSpec = {
  cycle: 'H3',
  rules: H3_CATEGORY_RULES,
  slots: [
    {
      slotKey: 'gross',
      slotLabel: '投资性房地产原值',
      openingField: 'beginBalance',
      closingField: 'unadjusted',
      openingLabel: '期初余额',
      closingLabel: '未审数',
    },
    {
      slotKey: 'accum_dep',
      slotLabel: '累计折旧',
      openingField: 'beginBalance',
      closingField: 'unadjusted',
      openingLabel: '期初余额',
      closingLabel: '未审数',
    },
    {
      slotKey: 'accum_amort',
      slotLabel: '累计摊销',
      openingField: 'beginBalance',
      closingField: 'unadjusted',
      openingLabel: '期初余额',
      closingLabel: '未审数',
    },
    {
      slotKey: 'impairment',
      slotLabel: '减值准备',
      openingField: 'beginBalance',
      closingField: 'unadjusted',
      openingLabel: '期初余额',
      closingLabel: '未审数',
    },
  ],
  defaults: [],
}

// ─── H4 工程物资（1605）─────────────────────────────────────────────────
// 源模板 H4-1 固定四类（`DEFAULT_H4_CATEGORIES`）。
const H4_SPEC: HSeedSpec = {
  cycle: 'H4',
  rules: [
    {
      rowKey: '专用材料',
      label: '专用材料',
      keywords: ['专用材料', '材料'],
      // 「专用设备」含「专用」但不该落材料行
      excludeKeywords: ['设备', '工器具'],
    },
    {
      rowKey: '专用设备',
      label: '专用设备',
      keywords: ['专用设备', '设备'],
      excludeKeywords: ['工器具'],
    },
    {
      rowKey: '工器具',
      label: '工器具',
      keywords: ['工器具', '工具', '器具'],
    },
    {
      rowKey: '其他',
      label: '其他',
      keywords: ['其他'],
    },
  ],
  slots: [
    // 🔴 槽键必须与后端 `h4_account_scope.H4_SLOT_KEY_PREFIX` 逐字一致 =
    // `gross`（1605 工程物资，H4 自己的科目）/ `cip`（1604 在建工程）。
    // 首版按语义猜成 `eng_mat` → 跨文件交叉锁死守卫打红（后端实测 ['gross','cip']）。
    {
      slotKey: 'gross',
      slotLabel: '工程物资',
      openingField: 'beginUnadjusted',
      closingField: 'endUnadjusted',
      openingLabel: '期初未审',
      closingLabel: '期末未审',
    },
    // `cip`（1604）在 H4-1 里只作「报表核对·在建工程」用，不参与分类行预填
    // （它是 H2 的科目，落进 H4 分类行会双算）→ 有意不声明。
  ],
  defaults: [],
}

/** 各循环声明注册表 */
const _SPECS: Partial<Record<HSeedSpec['cycle'], HSeedSpec>> = {
  H2: H2_SPEC,
  H3: H3_SPEC,
  H4: H4_SPEC,
}

export function getHSeedSpec(cycle: string): HSeedSpec | null {
  return _SPECS[cycle as HSeedSpec['cycle']] ?? null
}

/**
 * 行定位/建行适配器 —— 由各审定表 Tab 注入。
 *
 * 各循环行模型不同构（H2 按工程项目名 / H4 按物资分类 / H3 按房地产类别），
 * 但「按 rowKey 找到行；找不到就建一行；往某列写值」这三件事一样。
 * 把它做成注入而非共享件内部实现，是因为**持久化动作**必须由宿主提供
 * （平台既有三种形态：`saveImmediate(itemId, data)` / `saveImmediate(items[])` /
 * `window.dispatchEvent('xx:save-items')`，硬写任一种会让另两种无法接入）。
 */
export interface HSeedRowAdapter {
  /** 按 rowKey（行标签）找现有行 id；找不到返回 null */
  findRowId: (rowKey: string) => string | null
  /** 建一行并返回其 id（H2 = `addProjectRow` / H4 = `addRow`） */
  createRow: (rowKey: string) => string | null
  /** 往某行某列写值 */
  writeCell: (rowId: string, field: string, amount: number) => void
}

export interface HSeedApplyResult {
  written: number
  created: number
  /** 无法定位且建行失败的格（如实回报，不静默丢弃） */
  failed: AdjPrefillCell[]
}

/**
 * 把「计划」落到行模型。
 *
 * 🔴 只写 `cells` 里给出的格 —— 调用方须先经
 * :func:`resolveAdjPrefillWrites` 决定 `fill-blank` 还是 `overwrite`，
 * 本函数不再做手工优先判定（避免两处各判一次导致语义分叉）。
 */
export function applyHSeedCells(
  cells: readonly AdjPrefillCell[],
  adapter: HSeedRowAdapter,
): HSeedApplyResult {
  const result: HSeedApplyResult = { written: 0, created: 0, failed: [] }
  for (const cell of cells ?? []) {
    let rowId = adapter.findRowId(cell.rowKey)
    if (!rowId) {
      rowId = adapter.createRow(cell.rowKey)
      if (rowId) result.created += 1
    }
    if (!rowId) {
      result.failed.push(cell)
      continue
    }
    adapter.writeCell(rowId, cell.field, cell.amount)
    result.written += 1
  }
  return result
}

/** 已声明的循环（守卫用；H1 走自己的 `adjudication_category_prefill` 链路） */
export const H_SEED_DECLARED_CYCLES: readonly string[] = Object.keys(_SPECS)

// ═══════════════════════════════════════════════════════════════════════════
// 归类与计划构造
// ═══════════════════════════════════════════════════════════════════════════

/** 名称归一：去空白 + 全角括号转半角（客户科目名空格位置很随意） */
export function normalizeAccountName(name: string): string {
  return String(name ?? '')
    .replace(/\s+/g, '')
    .replace(/（/g, '(')
    .replace(/）/g, ')')
}

/**
 * 按科目名把一个叶子归类到审定表行。
 *
 * @returns 命中的规则；未命中返回 `null`（**不兜底**）
 */
export function classifyHLeaf(
  name: string,
  rules: readonly HRowRule[],
): HRowRule | null {
  const s = normalizeAccountName(name)
  if (!s) return null
  for (const rule of rules) {
    if (rule.excludeKeywords?.some((k) => s.includes(k))) continue
    if (rule.keywords.some((k) => s.includes(k))) return rule
  }
  return null
}

function itemAmounts(
  item: HPrefillItem,
  mode: 'balance' | 'occurrence',
): { opening: number; closing: number } {
  if (mode === 'occurrence') {
    const it = item as HPrefillOccurrenceItem
    // 损益类无期初；发生额取借贷净额（借方为正）
    return {
      opening: 0,
      closing: Number(it.debit_amount || 0) - Number(it.credit_amount || 0),
    }
  }
  const it = item as HPrefillBalanceItem
  return {
    opening: Number(it.opening_balance || 0),
    closing: Number(it.closing_balance || 0),
  }
}

export interface HSeedBuildResult {
  /** 待写入格（交 `planAdjudicationPrefill`） */
  cells: AdjPrefillCell[]
  /** 未能归类的叶子（交审计师分配，**不兜底**） */
  unclassified: AdjPrefillUnclassified[]
  /** 本项目无该科目的槽 */
  absentSlots: Array<{ slotKey: string; label: string }>
}

/**
 * 把后端 `adjudication_segment_prefill` 转成待写入格 + 待归类清单。
 *
 * 同一行同一列可能由多个叶子累加（如「房屋」下有多个具体楼栋）⇒ 按
 * `rowKey|field` 聚合，`sourceCodes` 累积全部来源码供溯源。
 */
export function buildHSeedCells(
  spec: HSeedSpec,
  prefill: HSegmentPrefill | null | undefined,
): HSeedBuildResult {
  const result: HSeedBuildResult = { cells: [], unclassified: [], absentSlots: [] }
  const segments = prefill?.segments ?? []

  // 槽缺失如实登记（「本项目无此科目」≠「该科目为 0」）
  const presentSlots = new Set(segments.map((s) => s.segment))
  for (const slot of spec.slots) {
    if (!presentSlots.has(slot.slotKey)) {
      result.absentSlots.push({ slotKey: slot.slotKey, label: slot.slotLabel })
    }
  }

  /** `rowKey|field` → 聚合中的格 */
  const acc = new Map<string, AdjPrefillCell>()

  for (const seg of segments) {
    const slot = spec.slots.find((s) => s.slotKey === seg.segment)
    if (!slot) continue // 声明里没有这个槽 → 忽略（不凭空造列）

    for (const item of seg.items ?? []) {
      const { opening, closing } = itemAmounts(item, seg.mode)
      const rule = classifyHLeaf(item.name, spec.rules)

      if (!rule) {
        result.unclassified.push({
          code: item.code,
          name: item.name,
          amount: closing,
          opening,
        })
        continue
      }

      const targets: Array<{ field: string; label: string; amount: number }> = [
        { field: slot.closingField, label: slot.closingLabel, amount: closing },
      ]
      if (slot.openingField && slot.openingLabel) {
        targets.unshift({
          field: slot.openingField,
          label: slot.openingLabel,
          amount: opening,
        })
      }

      for (const t of targets) {
        const key = `${rule.rowKey}|${t.field}`
        const existing = acc.get(key)
        if (existing) {
          existing.amount += t.amount
          if (!existing.sourceCodes?.includes(item.code)) {
            existing.sourceCodes = [...(existing.sourceCodes ?? []), item.code]
          }
        } else {
          acc.set(key, {
            rowKey: rule.rowKey,
            field: t.field,
            amount: t.amount,
            label: rule.label,
            periodLabel: t.label,
            sourceCodes: [item.code],
          })
        }
      }
    }
  }

  result.cells = [...acc.values()]
  return result
}

/**
 * 从 render 下发的 `html_data` 里取分段预填。
 *
 * 🔴 平台有两套落点约定（memory 已记 D 类实证）：多数循环写 `html_data` 顶层，
 * 少数写 `project_context`。此处**两层都读**（顶层优先），
 * 避免「后端产了、前端读不到」这类 dead output。
 */
export function readHSegmentPrefill(
  htmlData: unknown,
): HSegmentPrefill | null {
  const hd = htmlData as Record<string, any> | null | undefined
  const raw =
    hd?.adjudication_segment_prefill ??
    hd?.project_context?.adjudication_segment_prefill
  if (!raw || !Array.isArray(raw.segments)) return null
  return raw as HSegmentPrefill
}
