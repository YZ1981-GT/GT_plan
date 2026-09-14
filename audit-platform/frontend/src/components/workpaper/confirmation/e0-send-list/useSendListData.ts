/**
 * useSendListData.ts — E0 发函清单共享引擎
 *
 * 行 CRUD / 载荷构建 / legacy 兼容 / 列显隐。
 * 由三个专属组件 (E03/E04/E05) 消费；E06 的 wealthList 可在内部复用。
 *
 * @module e0-send-list-dedicated-components / Wave 3 Task 6
 */

import { computed, ref, type Ref } from 'vue'
import type { SendListColumn, SendListSpec } from './sendListSpec'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface SendListRow {
  _row_id: string
  [field: string]: any
}

export interface SendListConclusion {
  audit_explanation: string
  overall_conclusion: string
  remarks: string
}

export interface SendListPayload {
  _format: string
  rows: SendListRow[]
  conclusion: SendListConclusion
}

// ─── Row ID 生成 ──────────────────────────────────────────────────────────────

function generateRowId(): string {
  const ts = Date.now()
  const rnd = Math.random().toString(36).slice(2, 8)
  return `row-${ts}-${rnd}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useSendListData(spec: SendListSpec, opts: {
  htmlData: Ref<any>
  isReadonly: Ref<boolean>
}) {
  // ─── 初始化 ─────────────────────────────────────────────────────────────────

  const _rawData = computed<any>(() => {
    const hd = opts.htmlData.value
    if (!hd || typeof hd !== 'object') return null
    return hd
  })

  // ─── Rows ───────────────────────────────────────────────────────────────────

  const rows = ref<SendListRow[]>([]) as Ref<SendListRow[]>
  const conclusion = ref<SendListConclusion>({
    audit_explanation: '',
    overall_conclusion: '',
    remarks: '',
  })

  /** 从 html_data 加载（render-config 下发） */
  function loadFromHtmlData(data: any) {
    if (!data || typeof data !== 'object') {
      rows.value = []
      conclusion.value = { audit_explanation: '', overall_conclusion: '', remarks: '' }
      return
    }

    // 行数据
    if (Array.isArray(data.rows)) {
      rows.value = data.rows.map((r: any) => ({
        ...r,
        _row_id: r._row_id || generateRowId(),
      }))
    } else {
      rows.value = []
    }

    // 结论
    if (data.conclusion && typeof data.conclusion === 'object') {
      conclusion.value = {
        audit_explanation: data.conclusion.audit_explanation || '',
        overall_conclusion: data.conclusion.overall_conclusion || '',
        remarks: data.conclusion.remarks || '',
      }
    }
  }

  // ─── 行 CRUD ────────────────────────────────────────────────────────────────

  function addRow(): SendListRow {
    const row: SendListRow = { _row_id: generateRowId() }
    rows.value.push(row)
    return row
  }

  function removeRow(rowId: string) {
    const idx = rows.value.findIndex(r => r._row_id === rowId)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
    }
  }

  function moveRow(rowId: string, direction: 'up' | 'down') {
    const idx = rows.value.findIndex(r => r._row_id === rowId)
    if (idx < 0) return
    const targetIdx = direction === 'up' ? idx - 1 : idx + 1
    if (targetIdx < 0 || targetIdx >= rows.value.length) return
    const [row] = rows.value.splice(idx, 1)
    rows.value.splice(targetIdx, 0, row)
  }

  // ─── 列显隐 ──────────────────────────────────────────────────────────────────

  const hiddenFields = ref<Set<string>>(new Set())

  const visibleColumns = computed<SendListColumn[]>(() => {
    return spec.columns.filter(c => !hiddenFields.value.has(c.field))
  })

  function toggleColumn(field: string) {
    if (hiddenFields.value.has(field)) {
      hiddenFields.value.delete(field)
    } else {
      hiddenFields.value.add(field)
    }
  }

  // ─── 载荷构建 ──────────────────────────────────────────────────────────────

  /** 构建保存载荷。🔴 不得含 _prefill 键（Property 6） */
  function buildPayload(): SendListPayload {
    return {
      _format: spec.formatVersion,
      rows: rows.value.map(r => {
        // 只保留 _row_id + spec 声明的 field + _unmapped_cells
        const cleaned: SendListRow = { _row_id: r._row_id }
        for (const col of spec.columns) {
          if (r[col.field] !== undefined && r[col.field] !== null && r[col.field] !== '') {
            cleaned[col.field] = r[col.field]
          }
        }
        if (r._unmapped_cells) {
          cleaned._unmapped_cells = r._unmapped_cells
        }
        return cleaned
      }),
      conclusion: { ...conclusion.value },
    }
  }

  // ─── 未映射单元格检测 ──────────────────────────────────────────────────────

  const hasUnmappedCells = computed<boolean>(() => {
    return rows.value.some(r => r._unmapped_cells && Object.keys(r._unmapped_cells).length > 0)
  })

  return {
    rows,
    conclusion,
    visibleColumns,
    hiddenFields,
    hasUnmappedCells,
    addRow,
    removeRow,
    moveRow,
    toggleColumn,
    buildPayload,
    loadFromHtmlData,
  }
}
