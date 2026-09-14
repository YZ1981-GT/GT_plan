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
import {
  CONTROL_FREQUENCY_OPTIONS,
  CONTROL_PERFORMER_OPTIONS,
  CONTROL_RISK_OPTIONS,
  CONTROL_NATURE_OPTIONS,
} from './b22aReference'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 12 列控制矩阵行模型 */
export interface ControlPoint {
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

  function rowFieldId(n: number, field: keyof ControlPoint): string {
    return `B22B-row-${n}-${field}`
  }
  const COUNT_ID = 'B22B-row-count'

  // ─── Load ────────────────────────────────────────────────────────────────

  async function loadAll(): Promise<void> {
    if (!wpId.value) return
    loading.value = true
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const map = new Map<string, string>()
      let count = 0
      for (const r of responses) {
        const id: string = r.item_id ?? ''
        if (id === COUNT_ID) {
          const n = parseInt(r.remark || '0', 10)
          if (!isNaN(n)) count = n
        } else if (id.startsWith('B22B-row-')) {
          map.set(id, r.remark ?? '')
        }
      }
      const loaded: ControlPoint[] = []
      for (let n = 0; n < count; n++) {
        const row = emptyControlPoint()
        for (const field of CONTROL_POINT_FIELDS) {
          const v = map.get(rowFieldId(n, field))
          if (v != null) (row[field] as string) = v
        }
        loaded.push(row)
      }
      rows.value = loaded
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

  /** 构造整表全部 item（含 count）用于批量保存 */
  function buildAllItems(): { item_id: string; remark: string | null }[] {
    const items: { item_id: string; remark: string | null }[] = [
      { item_id: COUNT_ID, remark: String(rows.value.length) },
    ]
    rows.value.forEach((row, n) => {
      for (const field of CONTROL_POINT_FIELDS) {
        items.push({ item_id: rowFieldId(n, field), remark: (row[field] as string) || null })
      }
    })
    return items
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

  function removeRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    rows.value.splice(index, 1)
    // 行删除后 item_id 索引整体前移，最简单可靠：先清空旧尾行再全量重写
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
    // 收集所有 (tab, isIT, sub, index) 组合
    const reItem = /^B22A-T(\d+)-item-(\d+)-point$/
    const reIT = /^B22A-T(\d+)-IT-([^-]+)-(\d+)-point$/
    const result: ControlPoint[] = []

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

      const row = emptyControlPoint()
      row.element = tabToElement(tab, isIT)
      row.controlName = controlName
      row.description = description

      // 尝试读取控制属性（attrs JSON）
      const attrsRaw = map.get(`${attrsPrefix}-attrs`)
      if (attrsRaw) {
        try {
          const attrs = JSON.parse(attrsRaw)
          if (attrs && typeof attrs === 'object') {
            if (attrs.antiFraud != null) row.antiFraud = String(attrs.antiFraud)
            if (attrs.frequency != null) row.frequency = String(attrs.frequency)
            if (attrs.performer != null) row.performer = String(attrs.performer)
            if (attrs.competence != null) row.competence = String(attrs.competence)
            if (attrs.risk != null) row.relatedRisk = String(attrs.risk)
            if (attrs.relatedRisk != null) row.relatedRisk = String(attrs.relatedRisk)
            if (attrs.nature != null) row.nature = String(attrs.nature)
            if (attrs.itApp != null) row.itApp = String(attrs.itApp)
          }
        } catch {
          // 忽略非法 JSON
        }
      }
      result.push(row)
    }
    return result
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
