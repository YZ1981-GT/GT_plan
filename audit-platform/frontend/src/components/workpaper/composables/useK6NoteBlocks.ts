/**
 * K6 持有待售 —— 附注要求的 4 个录入区块（两变体共用）
 *
 * 背景（`k-cycle-disclosure-alignment` 批 3 Task 13）：改造前两个披露 Tab **只喂主表**，
 * 附注要求的另外 3~4 张表（减值准备变动 / 持有待售非流动资产 / 处置组 / 持有待售负债）
 * 在底稿里**完全没有录入位置** —— 模板补了 `columns`/`guidance` 也只有 seed 路径能看到，
 * 同步路径永远推不出这些表。
 *
 * 章节归属（源 xlsx + `note_template_variant_matrix.json` 实证）：
 *   · 上市 §五、11 一节含全部 5 表（负债也在里面，列口径是「期末余额/上年年末余额」两列）
 *   · 国企 §八、12 含资产 4 表，**§八、43 单独承载持有待售负债**（5 列公允价值口径）
 *
 * 派生列一律**读时推导不持久化**（平台铁律）：减值准备表期末 = 期初 + 本期增加
 * − 本期转回 − 本期出售，纯函数 `impairmentEndAmount()` 落在 `k6NoteSectionMap`，
 * 组件与同步载荷同源。
 */
import { computed, ref, type Ref } from 'vue'
import {
  impairmentEndAmount,
  type K6DisclosureVariant,
  type K6FairValueRow,
  type K6ImpairmentRow,
} from './k6NoteSectionMap'

/** 带行 id 的减值准备变动行（`id` 只用于表格 track / 编辑定位，不进载荷） */
export interface K6ImpairmentUiRow extends K6ImpairmentRow {
  id: string
}

/** 带行 id 的公允价值明细行 */
export interface K6FairValueUiRow extends K6FairValueRow {
  id: string
}

/** 上市侧持有待售负债是「期末余额 / 上年年末余额」两列口径（与国企 5 列不同） */
export interface K6ListedLiabilityUiRow {
  id: string
  project: string
  endAmount: number
  priorAmount: number
}

export type K6BlockKey = 'impairment' | 'nonCurrent' | 'disposalGroup' | 'liabilities'

/** checklist item_id 命名：`K6-disclosure-{variant}-{block}-rows` */
export function k6BlockItemId(variant: K6DisclosureVariant, block: K6BlockKey): string {
  return `K6-disclosure-${variant}-${block}-rows`
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function nextId(prefix: string, len: number): string {
  return `${prefix}-${Date.now()}-${len}`
}

/**
 * 「本次会话内改动过的区块」标记 —— **模块级**，按 `{variant}:{wpId}` 归集。
 *
 * 🔴 不能放在 composable 实例里（2026-07-31 浏览器实测踩中）：宿主在 checklist 保存后
 * 会重建 `allResponses` 并可能重挂 Tab 组件 → setup 重跑 → 实例级 Set 归零 →
 * 「填过再清空」被误判成「从未填过」→ 清理载荷不发 → 附注永久残留过时明细。
 * 模块级标记跨重挂存活；跨页面刷新则由 `responses().has(itemId)` 兜住
 * （整页加载时宿主会从服务端取回该 checklist item）。
 */
const TOUCHED_BLOCKS = new Map<string, Set<K6BlockKey>>()

function touchKey(variant: K6DisclosureVariant, wpId: string): string {
  return `${variant}:${wpId}`
}

function normImpairment(raw: any, idx: number): K6ImpairmentUiRow {
  return {
    id: String(raw?.id || `imp-${idx}`),
    project: String(raw?.project ?? ''),
    priorAmount: num(raw?.priorAmount),
    increase: num(raw?.increase),
    reverse: num(raw?.reverse),
    disposal: num(raw?.disposal),
  }
}

function normFairValue(raw: any, idx: number, prefix: string): K6FairValueUiRow {
  return {
    id: String(raw?.id || `${prefix}-${idx}`),
    project: String(raw?.project ?? ''),
    endBook: num(raw?.endBook),
    endFairValue: num(raw?.endFairValue),
    disposalFee: num(raw?.disposalFee),
    timetable: String(raw?.timetable ?? ''),
  }
}

function normListedLiability(raw: any, idx: number): K6ListedLiabilityUiRow {
  return {
    id: String(raw?.id || `liab-${idx}`),
    project: String(raw?.project ?? ''),
    endAmount: num(raw?.endAmount),
    priorAmount: num(raw?.priorAmount),
  }
}

export interface UseK6NoteBlocksOptions {
  variant: K6DisclosureVariant
  /** 底稿 id —— 「改动过」标记按底稿归集，跨组件重挂存活 */
  wpId: () => string
  /** 读 checklist 快照（父组件的 `props.allResponses`） */
  responses: () => Map<string, any>
  /** 持久化一个区块（父组件 `emit('save', itemId, { remark })`） */
  save: (itemId: string, remark: string) => void
  /** 任一区块变更后回调（父组件用来 `scheduleAutoSync`） */
  onChanged: () => void
}

export interface K6NoteBlocks {
  impairment: Ref<K6ImpairmentUiRow[]>
  nonCurrent: Ref<K6FairValueUiRow[]>
  disposalGroup: Ref<K6FairValueUiRow[]>
  /** 国企：5 列公允价值口径（推 §八、43） */
  liabilities: Ref<K6FairValueUiRow[]>
  /** 上市：2 列余额口径（并入 §五、11） */
  listedLiabilities: Ref<K6ListedLiabilityUiRow[]>
  load: () => void
  addRow: (block: K6BlockKey) => void
  removeRow: (block: K6BlockKey, id: string) => void
  updateField: (block: K6BlockKey, id: string, field: string, value: unknown) => void
  /**
   * 该区块是否**曾被填写过**（checklist item 存在 或 本会话保存过）。
   *
   * 用途：区分「从未填过」与「填过再清空」—— 后者必须给附注发清理载荷
   * （`_removed_table_keys`），否则附注永久残留上次推送的过时明细；前者整节不发请求，
   * 否则会把该节标成 `_source=workpaper`、模板骨架反而不再渲染。
   */
  wasTouched: (block: K6BlockKey) => boolean
  /** 减值准备表期末余额（读时推导） */
  endOf: (row: K6ImpairmentUiRow) => number
  /** 各区块合计（供表尾与勾稽面板） */
  impairmentTotalEnd: Ref<number>
  nonCurrentTotalBook: Ref<number>
}

export function useK6NoteBlocks(opts: UseK6NoteBlocksOptions): K6NoteBlocks {
  const { variant, responses, save, onChanged } = opts
  const wpId = opts.wpId ?? (() => '')

  const impairment = ref<K6ImpairmentUiRow[]>([])
  const nonCurrent = ref<K6FairValueUiRow[]>([])
  const disposalGroup = ref<K6FairValueUiRow[]>([])
  const liabilities = ref<K6FairValueUiRow[]>([])
  const listedLiabilities = ref<K6ListedLiabilityUiRow[]>([])

  function markTouched(block: K6BlockKey): void {
    const key = touchKey(variant, wpId())
    let set = TOUCHED_BLOCKS.get(key)
    if (!set) {
      set = new Set<K6BlockKey>()
      TOUCHED_BLOCKS.set(key, set)
    }
    set.add(block)
  }

  function readBlock(block: K6BlockKey): any[] {
    const saved = responses().get(k6BlockItemId(variant, block))
    const raw = saved?.remark ?? saved?.conclusion ?? null
    if (!raw) return []
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }

  function load(): void {
    impairment.value = readBlock('impairment').map(normImpairment)
    nonCurrent.value = readBlock('nonCurrent').map((r, i) => normFairValue(r, i, 'nc'))
    disposalGroup.value = readBlock('disposalGroup').map((r, i) => normFairValue(r, i, 'dg'))
    const liabRaw = readBlock('liabilities')
    if (variant === 'soe') {
      liabilities.value = liabRaw.map((r, i) => normFairValue(r, i, 'liab'))
    } else {
      listedLiabilities.value = liabRaw.map(normListedLiability)
    }
  }

  function persist(block: K6BlockKey): void {
    const payload = block === 'impairment'
      ? impairment.value
      : block === 'nonCurrent'
        ? nonCurrent.value
        : block === 'disposalGroup'
          ? disposalGroup.value
          : variant === 'soe' ? liabilities.value : listedLiabilities.value
    markTouched(block)
    save(k6BlockItemId(variant, block), JSON.stringify(payload))
    onChanged()
  }

  function wasTouched(block: K6BlockKey): boolean {
    if (TOUCHED_BLOCKS.get(touchKey(variant, wpId()))?.has(block)) return true
    try {
      return Boolean(responses()?.has(k6BlockItemId(variant, block)))
    } catch {
      return false
    }
  }

  function addRow(block: K6BlockKey): void {
    if (block === 'impairment') {
      impairment.value.push({
        id: nextId('imp', impairment.value.length),
        project: '', priorAmount: 0, increase: 0, reverse: 0, disposal: 0,
      })
    } else if (block === 'nonCurrent') {
      nonCurrent.value.push({
        id: nextId('nc', nonCurrent.value.length),
        project: '', endBook: 0, endFairValue: 0, disposalFee: 0, timetable: '',
      })
    } else if (block === 'disposalGroup') {
      disposalGroup.value.push({
        id: nextId('dg', disposalGroup.value.length),
        project: '', endBook: 0, endFairValue: 0, disposalFee: 0, timetable: '',
      })
    } else if (variant === 'soe') {
      liabilities.value.push({
        id: nextId('liab', liabilities.value.length),
        project: '', endBook: 0, endFairValue: 0, disposalFee: 0, timetable: '',
      })
    } else {
      listedLiabilities.value.push({
        id: nextId('liab', listedLiabilities.value.length),
        project: '', endAmount: 0, priorAmount: 0,
      })
    }
    persist(block)
  }

  function rowsOf(block: K6BlockKey): Array<{ id: string }> {
    if (block === 'impairment') return impairment.value
    if (block === 'nonCurrent') return nonCurrent.value
    if (block === 'disposalGroup') return disposalGroup.value
    return variant === 'soe' ? liabilities.value : listedLiabilities.value
  }

  function removeRow(block: K6BlockKey, id: string): void {
    if (block === 'impairment') {
      impairment.value = impairment.value.filter(r => r.id !== id)
    } else if (block === 'nonCurrent') {
      nonCurrent.value = nonCurrent.value.filter(r => r.id !== id)
    } else if (block === 'disposalGroup') {
      disposalGroup.value = disposalGroup.value.filter(r => r.id !== id)
    } else if (variant === 'soe') {
      liabilities.value = liabilities.value.filter(r => r.id !== id)
    } else {
      listedLiabilities.value = listedLiabilities.value.filter(r => r.id !== id)
    }
    persist(block)
  }

  function updateField(block: K6BlockKey, id: string, field: string, value: unknown): void {
    const row = rowsOf(block).find(r => r.id === id)
    if (!row) return
    ;(row as any)[field] = value
    persist(block)
  }

  const impairmentTotalEnd = computed(
    () => impairment.value.reduce((s, r) => s + impairmentEndAmount(r), 0),
  )
  const nonCurrentTotalBook = computed(
    () => nonCurrent.value.reduce((s, r) => s + num(r.endBook), 0),
  )

  return {
    impairment,
    nonCurrent,
    disposalGroup,
    liabilities,
    listedLiabilities,
    load,
    addRow,
    removeRow,
    updateField,
    wasTouched,
    endOf: impairmentEndAmount,
    impairmentTotalEnd,
    nonCurrentTotalBook,
  }
}
