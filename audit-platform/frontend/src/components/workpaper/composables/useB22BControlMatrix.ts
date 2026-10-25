/**
 * useB22BControlMatrix — B22B 企业层面控制矩阵登记册（致同源模板 B22B 真实结构）
 *
 * 方案 A：B22B 恢复为控制矩阵登记册（12 列），取代原缺陷评价表。
 *
 * 12 列（顺序严格，对齐致同源模板）：
 *   要素 / 子类别 / 编号 / 控制名称 / 详细控制描述 / 是否为反舞弊控制 /
 *   控制频率 / 执行人 / 执行内部控制的人员的知识经验技能 / 与控制相关的风险 /
 *   自动/人工 / IT应用名称
 *
 * 持久化：
 * - GET/PUT /api/workpapers/{wpId}/checklist-responses
 * - item_id：`B22B-row-{n}-{field}`（每字段一条，值存 remark，conclusion 恒 null）
 *   + `B22B-row-count`（行数）
 * - PUT 请求体绝不传 project_id（wpId 不是 project_id，传错触发 422 project_mismatch）
 *
 * 从 B22A 带入控制点：
 * - GET /api/projects/{projectId}/workpapers?wp_code=B22A → 拿 B22A wpId
 * - GET /api/workpapers/{b22aWpId}/checklist-responses → 解析各要素控制点
 * - 仅填空、按 controlName+description 去重，不覆盖已编辑行
 */
import { ref, computed, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { newRowIdentity } from './shared/rowIdentity'
import {
  CONTROL_FREQUENCY_OPTIONS,
  CONTROL_PERFORMER_OPTIONS,
  CONTROL_RISK_OPTIONS,
  CONTROL_NATURE_OPTIONS,
} from './b22aReference'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 12 列控制矩阵行模型 */
export interface ControlPoint {
  /**
   * 稳定行身份（BC-53 改造）。
   *
   * 🔴 改造前落库形态是 `B22B-row-{数组下标}-{field}`，行身份=位置：删中间行后
   *    所有后续行的 item_id 整体前移（`removeRow` 原注释自述「索引整体前移」），
   *    ① OO↔HTML roundtrip 按行身份配对 ⇒ 必错位；② 按 item_id 的外部引用
   *    （复核锚点）指向别人的行。现在身份随行对象走，与位置无关。
   */
  rowId: string
  element: string
  subCategory: string
  code: string
  controlName: string
  description: string
  antiFraud: string
  frequency: string
  performer: string
  competence: string
  relatedRisk: string
  nature: string
  itApp: string
}

/** 12 列字段键（顺序严格） */
export const CONTROL_POINT_FIELDS: (keyof ControlPoint)[] = [
  'element',
  'subCategory',
  'code',
  'controlName',
  'description',
  'antiFraud',
  'frequency',
  'performer',
  'competence',
  'relatedRisk',
  'nature',
  'itApp',
]

/** 文本字段（debounce 保存）；其余为枚举字段（即时保存） */
const TEXT_FIELDS = new Set<keyof ControlPoint>([
  'subCategory',
  'code',
  'controlName',
  'description',
  'competence',
  'itApp',
])

// ─── 枚举常量 ─────────────────────────────────────────────────────────────────

/** 要素枚举（企业层面控制五类） */
export const ELEMENT_OPTIONS = [
  '控制环境',
  '风险评估过程',
  '信息与沟通',
  '监督',
  'IT一般控制',
] as const

/** 反舞弊控制枚举 */
export const ANTI_FRAUD_OPTIONS = ['是', '否'] as const

// 复用 b22aReference 的控制矩阵属性枚举
export {
  CONTROL_FREQUENCY_OPTIONS,
  CONTROL_PERFORMER_OPTIONS,
  CONTROL_RISK_OPTIONS,
  CONTROL_NATURE_OPTIONS,
}

function emptyControlPoint(): ControlPoint {
  return {
    // 新行即铸稳定身份（委托平台共享出口，不自己实现唯一性逻辑）
    rowId: newRowIdentity('B22B-row'),
    element: '',
    subCategory: '',
    code: '',
    controlName: '',
    description: '',
    antiFraud: '',
    frequency: '',
    performer: '',
    competence: '',
    relatedRisk: '',
    nature: '',
    itApp: '',
  }
}

// ─── B22A tab → 要素映射 ──────────────────────────────────────────────────────

function tabToElement(tab: number, isIT: boolean): string {
  switch (tab) {
    case 1:
      return '控制环境'
    case 2:
      return '风险评估过程'
    case 3:
      return '信息与沟通'
    case 4:
      return isIT ? 'IT一般控制' : '信息与沟通'
    case 5:
      return '监督'
    default:
      return ''
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB22BControlMatrix(
  wpId: Ref<string>,
  projectId: Ref<string>,
) {
  const rows = ref<ControlPoint[]>([])
  const loading = ref(false)
  const saving = ref(false)

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  let pendingSave = false

  // ─── 持久化：item_id 构造 ────────────────────────────────────────────────

  /** legacy 按下标展开的字段键（仅迁移时回读）。 */
  function rowFieldId(n: number, field: keyof ControlPoint): string {
    return `B22B-row-${n}-${field}`
  }
  const COUNT_ID = 'B22B-row-count'
  /**
   * 行数组 item_id（BC-53 改造后的权威落点）。
   *
   * 整表一条记录、remark = 行对象 JSON 数组，每行带 `rowId`。形态与 D4 后端
   * `ROW_IDENTITY_STORE_KEY='rowId'` + `iter_store_rows` 一致，便于接真双向。
   */
  const ROWS_ID = 'B22B-rows'

  // ─── Load ────────────────────────────────────────────────────────────────

  async function loadAll(): Promise<void> {
    if (!wpId.value) return
    loading.value = true
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, string>()
      let count = 0
      let rowsJson: string | null = null
      for (const r of responses) {
        const id: string = r.item_id ?? ''
        if (id === ROWS_ID) {
          rowsJson = r.remark ?? null
        } else if (id === COUNT_ID) {
          const n = parseInt(r.remark || '0', 10)
          if (!isNaN(n)) count = n
        } else if (id.startsWith('B22B-row-')) {
          map.set(id, r.remark ?? '')
        }
      }

      // ═══ 形态① 行数组（权威）═══════════════════════════════════════════
      if (rowsJson) {
        rows.value = parseRowsJson(rowsJson)
        return
      }

      // ═══ 形态② legacy 下标键 → 迁移（只改键形状不改值，落库一次）═══════
      const loaded: ControlPoint[] = []
      for (let n = 0; n < count; n++) {
        const row = emptyControlPoint()
        for (const field of CONTROL_POINT_FIELDS) {
          const v = map.get(rowFieldId(n, field))
          if (v != null) (row[field] as string) = v
        }
        // 🔴 legacy 身份用确定性串（含原下标）：多会话并发迁移产出一致，
        //    避免随机铸造导致同一行在两处拿到两套身份。
        row.rowId = `B22B-row-legacy-${n}`
        loaded.push(row)
      }
      rows.value = loaded
      if (loaded.length > 0) {
        // 迁移结果立即固化（否则下次载入仍走 legacy 分支、身份反复重建）
        void doSave(buildAllItems())
      }
    } catch {
      ElMessage.warning('数据加载失败，可手动填写')
    } finally {
      loading.value = false
    }
  }

  // ─── Save ────────────────────────────────────────────────────────────────

  async function doSave(items: { item_id: string; remark: string | null }[]): Promise<void> {
    if (!wpId.value || items.length === 0) return
    saving.value = true
    try {
      // 注意：绝不传 project_id（wpId 不是 project_id，传错触发 422 project_mismatch）。
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        items: items.map((it) => ({
          item_id: it.item_id,
          conclusion: null,
          remark: it.remark ?? null,
          wp_ref: null,
        })),
      })
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败')
      }
    } finally {
      saving.value = false
    }
  }

  /** 解析行数组 JSON（非法/缺失 → 空数组，渲染侧 fail soft 不抛）。 */
  function parseRowsJson(remark: string | null): ControlPoint[] {
    if (!remark) return []
    let parsed: unknown
    try {
      parsed = JSON.parse(remark)
    } catch {
      return []
    }
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw, i) => {
      const obj = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
      const row = emptyControlPoint()
      for (const field of CONTROL_POINT_FIELDS) {
        const v = obj[field as string]
        if (typeof v === 'string') (row[field] as string) = v
      }
      const rid = obj.rowId
      // 缺身份才补（存量身份稳定，不重铸 —— 对齐平台 grandfather 口径）
      row.rowId =
        typeof rid === 'string' && rid.trim() ? rid : `B22B-row-legacy-${i}`
      return row
    })
  }

  /**
   * 构造落库 item：整表一条行数组记录。
   *
   * 🔴 改造前是「按数组下标展开 12×N 条单字段键 + count」，行身份=位置。
   *    现在只写一条 `B22B-rows`，行身份在行对象内。
   *    同时保留 count 键（值=实际行数）：真库既有查询/报表可能读它，
   *    但它已降级为**校验值**，不再是行数真源（BC-54）。
   */
  function buildAllItems(): { item_id: string; remark: string | null }[] {
    return [
      { item_id: ROWS_ID, remark: JSON.stringify(rows.value) },
      { item_id: COUNT_ID, remark: String(rows.value.length) },
    ]
  }

  async function saveImmediate(): Promise<void> {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    pendingSave = false
    await doSave(buildAllItems())
  }

  function saveDebounced(): void {
    pendingSave = true
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      pendingSave = false
      doSave(buildAllItems())
    }, 2000)
  }

  function flushPendingSave(): void {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    if (pendingSave) {
      pendingSave = false
      doSave(buildAllItems())
    }
  }

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRow(preset?: Partial<ControlPoint>): void {
    rows.value.push({ ...emptyControlPoint(), ...(preset || {}) })
    saveImmediate()
  }

  /**
   * 删行（BC-53 改造后）。
   *
   * 改造前落库键含数组下标，删行导致后续行 item_id 整体前移（行身份漂移）；
   * 现在只写一条行数组、身份在行对象内 ⇒ splice 后剩余行身份完全不变。
   */
  function removeRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    rows.value.splice(index, 1)
    saveImmediate()
  }

  function updateField(index: number, field: keyof ControlPoint, value: string): void {
    const row = rows.value[index]
    if (!row) return
    ;(row[field] as string) = value
    if (TEXT_FIELDS.has(field)) {
      saveDebounced()
    } else {
      saveImmediate()
    }
  }

  // ─── 从 B22A 带入 ───────────────────────────────────────────────────────────

  /** 从 B22A checklist-responses 解析控制点 → 控制矩阵行 */
  function parseB22AControlPoints(responses: any[]): ControlPoint[] {
    const map = new Map<string, string>()
    for (const r of responses) {
      if (r.item_id) map.set(r.item_id, r.remark ?? '')
    }
    const result: ControlPoint[] = []

    // ═══ 形态① 行数组（BC-53 改造后的 B22A 形态）═══════════════════════════
    //
    // 🔴 B22A 已把行存储从「每字段一条下标键」改为「整组行一条 JSON 数组」
    //    （`B22A-T{tab}-rows` / `B22A-T{tab}-IT-{sub}-rows`）。若只认下面的
    //    legacy 键，改造后本函数会读到 **0 个控制点** ⇒ 带入功能静默失效。
    //    故先解析行数组；legacy 键作为未迁移项目的兜底（见形态②）。
    const reRows = /^B22A-T(\d+)-rows$/
    const reRowsIT = /^B22A-T(\d+)-IT-([^-]+)-rows$/
    const seenFromRows = new Set<string>()

    for (const [id, remark] of map.entries()) {
      const mRows = id.match(reRows)
      const mRowsIT = id.match(reRowsIT)
      if (!mRows && !mRowsIT) continue

      const tab = parseInt((mRows ? mRows[1] : mRowsIT![1]), 10)
      const isIT = !!mRowsIT
      let rows: any[]
      try {
        const parsed = JSON.parse(remark || '[]')
        rows = Array.isArray(parsed) ? parsed : []
      } catch {
        continue
      }

      for (const raw of rows) {
        if (!raw || typeof raw !== 'object') continue
        const controlName = String(raw.point ?? '').trim()
        const description = String(raw.desc ?? '').trim()
        if (!controlName && !description) continue

        const row = emptyControlPoint()
        row.element = tabToElement(tab, isIT)
        row.controlName = controlName
        row.description = description
        applyB22AAttrs(row, raw.attrs)
        result.push(row)
        // 记下已由行数组提供的 (tab, name, desc)，避免 legacy 兜底重复带入
        seenFromRows.add(`${tab}|${isIT}|${controlName}|${description}`)
      }
    }

    // ═══ 形态② legacy 下标键（未迁移项目的兜底）═══════════════════════════
    const reItem = /^B22A-T(\d+)-item-(\d+)-point$/
    const reIT = /^B22A-T(\d+)-IT-([^-]+)-(\d+)-point$/

    for (const [id, point] of map.entries()) {
      let tab = 0
      let index = -1
      let isIT = false
      let attrsPrefix = ''
      let descId = ''

      const mItem = id.match(reItem)
      const mIT = id.match(reIT)
      if (mItem) {
        tab = parseInt(mItem[1], 10)
        index = parseInt(mItem[2], 10)
        isIT = false
        attrsPrefix = `B22A-T${tab}-item-${index}`
        descId = `B22A-T${tab}-item-${index}-desc`
      } else if (mIT) {
        tab = parseInt(mIT[1], 10)
        const sub = mIT[2]
        index = parseInt(mIT[3], 10)
        isIT = true
        attrsPrefix = `B22A-T${tab}-IT-${sub}-${index}`
        descId = `B22A-T${tab}-IT-${sub}-${index}-desc`
      } else {
        continue
      }

      const controlName = (point || '').trim()
      const description = (map.get(descId) || '').trim()
      if (!controlName && !description) continue

      // 同一控制点若已由行数组（形态①）提供，legacy 兜底不再重复带入
      if (seenFromRows.has(`${tab}|${isIT}|${controlName}|${description}`)) continue

      const row = emptyControlPoint()
      row.element = tabToElement(tab, isIT)
      row.controlName = controlName
      row.description = description

      const attrsRaw = map.get(`${attrsPrefix}-attrs`)
      if (attrsRaw) {
        try {
          applyB22AAttrs(row, JSON.parse(attrsRaw))
        } catch {
          // 忽略非法 JSON
        }
      }
      result.push(row)
    }
    return result
  }

  /** 把 B22A 的 attrs 对象映射到 B22B 控制矩阵行（两形态共用）。 */
  function applyB22AAttrs(row: ControlPoint, attrs: unknown): void {
    if (!attrs || typeof attrs !== 'object') return
    const a = attrs as Record<string, unknown>
    if (a.antiFraud != null) row.antiFraud = String(a.antiFraud)
    if (a.frequency != null) row.frequency = String(a.frequency)
    if (a.performer != null) row.performer = String(a.performer)
    if (a.competence != null) row.competence = String(a.competence)
    if (a.risk != null) row.relatedRisk = String(a.risk)
    if (a.relatedRisk != null) row.relatedRisk = String(a.relatedRisk)
    if (a.nature != null) row.nature = String(a.nature)
    if (a.itApp != null) row.itApp = String(a.itApp)
  }

  /** 去重键：controlName + description */
  function dedupKey(row: ControlPoint): string {
    return `${(row.controlName || '').trim()}|||${(row.description || '').trim()}`
  }

  /**
   * 从 B22A 带入控制点：仅填空、按 controlName+description 去重、不覆盖已编辑行。
   * @returns 新增行数
   */
  async function pullFromB22A(): Promise<number> {
    if (!projectId.value) {
      ElMessage.warning('缺少项目上下文，无法带入')
      return 0
    }
    try {
      const res = await api.get(`/api/projects/${projectId.value}/workpapers`, {
        params: { wp_code: 'B22A' },
      })
      const workpapers: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      if (workpapers.length === 0) {
        ElMessage.warning('未找到 B22A 底稿')
        return 0
      }
      const b22aWpId = workpapers[0].id || workpapers[0].wp_id
      if (!b22aWpId) {
        ElMessage.warning('未找到 B22A 底稿')
        return 0
      }
      const b22aRes = await api.get(`/api/workpapers/${b22aWpId}/checklist-responses`)
      const b22aResponses: any[] = Array.isArray(b22aRes) ? b22aRes : (b22aRes?.data ?? [])

      const parsed = parseB22AControlPoints(b22aResponses)
      if (parsed.length === 0) {
        ElMessage.info('B22A 暂无可带入的控制点')
        return 0
      }

      // 已存在去重键集合
      const existing = new Set(rows.value.map(dedupKey))
      let added = 0
      for (const p of parsed) {
        const key = dedupKey(p)
        if (existing.has(key)) continue
        existing.add(key)
        rows.value.push(p)
        added++
      }
      if (added > 0) {
        await saveImmediate()
        ElMessage.success(`已从 B22A 带入 ${added} 项控制`)
      } else {
        ElMessage.info('无新增控制（均已存在）')
      }
      return added
    } catch {
      ElMessage.warning('从 B22A 带入失败')
      return 0
    }
  }

  // ─── 导出登记册数据（供客户端 xlsx 导出）────────────────────────────────────

  const registerRows = computed(() => rows.value)

  // ─── Lifecycle ───────────────────────────────────────────────────────────

  onScopeDispose(() => {
    flushPendingSave()
  })

  return {
    rows,
    loading,
    saving,
    registerRows,
    // 方法
    loadAll,
    saveImmediate,
    flushPendingSave,
    addRow,
    removeRow,
    updateField,
    pullFromB22A,
  }
}

export default useB22BControlMatrix
