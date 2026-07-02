<script setup lang="ts">
/**
 * E1TabDigitalCurrency.vue — E1-4 数字货币明细表
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.4
 *
 * 渲染：
 * - el-table 动态行：序号 | 开户银行 | 币种 | 汇率 | 期初 | 增加 | 减少 |
 *   期末原币 | 本位币 | 账项调整 | 审定原币 | 审定人民币 | 查询余额 | 差异 | 索引号 | 备注
 * - 底部合计行 + 审计说明/审计结论 textarea
 * - 动态行增删
 * - el-skeleton加载占位
 *
 * Requirements: 14.1-14.4
 */
import { ref, inject, toRef, computed, onMounted, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { UseE1BaseOptions, ChecklistItem, ChecklistResponse } from '../composables/useE1Adjudication'
import { parseNum, calcCashBalance, calcFxConvert, sumField } from '../composables/useE1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

interface DigitalRow {
  id: string
  seq: number
  bankName: string
  currency: string
  fxRate: number
  opening: number
  increase: number
  decrease: number
  endingFc: number       // readonly: opening+increase-decrease
  endingRmb: number      // readonly: endingFc×fxRate
  adjustment: number     // 账项调整(原币)
  auditedFc: number      // readonly: endingFc+adjustment
  auditedRmb: number     // readonly: auditedFc×fxRate
  queryBalance: number   // 查询余额
  diff: number           // readonly: queryBalance-auditedFc
  indexNo: string
  note: string
}

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'E1-digital-rows'
const CROSS_KEY_OPENING = 'E1-digital-opening-unaudited'
const CROSS_KEY_ENDING = 'E1-digital-total-unaudited'
const NOTE_KEY = 'E1-digital-audit-note'
const CONCLUSION_KEY = 'E1-digital-audit-conclusion'

const USER_FIELDS = ['id', 'seq', 'bankName', 'currency', 'fxRate', 'opening', 'increase', 'decrease', 'adjustment', 'queryBalance', 'indexNo', 'note']

// ─── State ───────────────────────────────────────────────────────────────────

const rows = ref<DigitalRow[]>([])
const isLoading = ref(false)
const auditNote = ref('')
const auditConclusion = ref('')

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateId(): string {
  return `digi-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function recalcRow(row: DigitalRow): DigitalRow {
  const endingFc = calcCashBalance(row.opening, row.increase, row.decrease)
  const endingRmb = calcFxConvert(endingFc, row.fxRate)
  const auditedFc = endingFc + row.adjustment
  const auditedRmb = calcFxConvert(auditedFc, row.fxRate)
  const diff = row.queryBalance - auditedFc
  return { ...row, endingFc, endingRmb, auditedFc, auditedRmb, diff }
}

function createEmptyRow(seq: number): DigitalRow {
  return recalcRow({
    id: generateId(), seq, bankName: '', currency: '人民币', fxRate: 1,
    opening: 0, increase: 0, decrease: 0, endingFc: 0, endingRmb: 0,
    adjustment: 0, auditedFc: 0, auditedRmb: 0, queryBalance: 0, diff: 0,
    indexNo: '', note: '',
  })
}

// ─── Load/Save ───────────────────────────────────────────────────────────────

function loadFromResponses(): void {
  const raw = props.allResponses.get(STORAGE_KEY)?.remark
  if (!raw) { rows.value = [createEmptyRow(1)]; return }
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || !parsed.length) { rows.value = [createEmptyRow(1)]; return }
    rows.value = parsed.map((r: any, i: number) => recalcRow({
      id: String(r.id || generateId()), seq: i + 1, bankName: String(r.bankName || ''),
      currency: String(r.currency || ''), fxRate: parseNum(r.fxRate) || 1,
      opening: parseNum(r.opening), increase: parseNum(r.increase), decrease: parseNum(r.decrease),
      endingFc: 0, endingRmb: 0, adjustment: parseNum(r.adjustment),
      auditedFc: 0, auditedRmb: 0, queryBalance: parseNum(r.queryBalance), diff: 0,
      indexNo: String(r.indexNo || ''), note: String(r.note || ''),
    }))
  } catch { rows.value = [createEmptyRow(1)] }

  auditNote.value = props.allResponses.get(NOTE_KEY)?.remark || ''
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
}

loadFromResponses()

function serializeRows(): string {
  return JSON.stringify(rows.value.map(row => {
    const obj: Record<string, unknown> = {}
    for (const f of USER_FIELDS) obj[f] = (row as any)[f]
    return obj
  }))
}

let saveTimer: ReturnType<typeof setTimeout> | null = null

function scheduleSave(): void {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { saveTimer = null; persistToResponses() }, 2000)
}

function persistToResponses(): void {
  const serialized = serializeRows()
  const items: ChecklistItem[] = [{ item_id: STORAGE_KEY, conclusion: null, remark: serialized }]
  props.allResponses.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: serialized })

  // Cross-sheet totals for E1-1
  const openingTotal = String(totalRow.value.opening)
  const endingTotal = String(totalRow.value.auditedRmb)
  props.allResponses.set(CROSS_KEY_OPENING, { item_id: CROSS_KEY_OPENING, conclusion: null, remark: openingTotal })
  props.allResponses.set(CROSS_KEY_ENDING, { item_id: CROSS_KEY_ENDING, conclusion: null, remark: endingTotal })
  items.push({ item_id: CROSS_KEY_OPENING, conclusion: null, remark: openingTotal })
  items.push({ item_id: CROSS_KEY_ENDING, conclusion: null, remark: endingTotal })

  // Audit note/conclusion
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value })
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value })
  items.push({ item_id: NOTE_KEY, conclusion: null, remark: auditNote.value })
  items.push({ item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value })

  props.saveImmediate(items).catch(() => {})
}

onBeforeUnmount(() => { if (saveTimer) { clearTimeout(saveTimer); persistToResponses() } })

// ─── Computed Total ──────────────────────────────────────────────────────────

const totalRow = computed(() => {
  const r = rows.value as unknown as Array<Record<string, unknown>>
  return {
    opening: sumField(r, 'opening'),
    increase: sumField(r, 'increase'),
    decrease: sumField(r, 'decrease'),
    endingFc: sumField(r, 'endingFc'),
    endingRmb: sumField(r, 'endingRmb'),
    adjustment: sumField(r, 'adjustment'),
    auditedFc: sumField(r, 'auditedFc'),
    auditedRmb: sumField(r, 'auditedRmb'),
    queryBalance: sumField(r, 'queryBalance'),
    diff: sumField(r, 'diff'),
  }
})

// ─── Row CRUD ────────────────────────────────────────────────────────────────

function addRow(): void {
  if (props.isReadonly) return
  rows.value = [...rows.value, createEmptyRow(rows.value.length + 1)]
  scheduleSave()
}

function removeRow(rowId: string): void {
  if (props.isReadonly) return
  rows.value = rows.value.filter(r => r.id !== rowId).map((r, i) => ({ ...r, seq: i + 1 }))
  scheduleSave()
}

function updateCell(rowId: string, field: string, value: number | string): void {
  if (props.isReadonly) return
  const idx = rows.value.findIndex(r => r.id === rowId)
  if (idx === -1) return
  const row = { ...rows.value[idx] }
  const numericFields = ['fxRate', 'opening', 'increase', 'decrease', 'adjustment', 'queryBalance']
  if (numericFields.includes(field)) (row as any)[field] = parseNum(value)
  else (row as any)[field] = String(value)
  const newRows = [...rows.value]
  newRows[idx] = recalcRow(row)
  rows.value = newRows
  scheduleSave()
}

function onNoteChange(val: string): void {
  auditNote.value = val; scheduleSave()
}
function onConclusionChange(val: string): void {
  auditConclusion.value = val; scheduleSave()
}
</script>

<template>
  <div class="e1-tab-digital-currency">
    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <!-- Toolbar -->
        <div class="toolbar" v-if="!isReadonly">
          <el-button type="primary" size="small" @click="addRow">+ 新增行</el-button>
        </div>

        <el-table :data="rows" border stripe size="small" style="width: 100%" max-height="500">
          <el-table-column label="序号" width="60" align="center">
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>
          <el-table-column label="开户银行" width="130">
            <template #default="{ row }">
              <el-input :model-value="row.bankName" :disabled="isReadonly" size="small" @change="(v: string) => updateCell(row.id, 'bankName', v)" />
            </template>
          </el-table-column>
          <el-table-column label="币种" width="90">
            <template #default="{ row }">
              <el-input :model-value="row.currency" :disabled="isReadonly" size="small" @change="(v: string) => updateCell(row.id, 'currency', v)" />
            </template>
          </el-table-column>
          <el-table-column label="汇率" width="80" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.fxRate" :disabled="isReadonly" :controls="false" :precision="4" size="small" @change="(v: number | undefined) => updateCell(row.id, 'fxRate', v ?? 1)" />
            </template>
          </el-table-column>
          <el-table-column label="期初" width="110" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.opening" :disabled="isReadonly" :controls="false" size="small" @change="(v: number | undefined) => updateCell(row.id, 'opening', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="增加" width="110" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.increase" :disabled="isReadonly" :controls="false" size="small" @change="(v: number | undefined) => updateCell(row.id, 'increase', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="减少" width="110" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.decrease" :disabled="isReadonly" :controls="false" size="small" @change="(v: number | undefined) => updateCell(row.id, 'decrease', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="期末原币" width="110" align="right">
            <template #default="{ row }"><span class="readonly-val">{{ displayPrefs.fmtAmount(row.endingFc) }}</span></template>
          </el-table-column>
          <el-table-column label="本位币" width="110" align="right">
            <template #default="{ row }"><span class="readonly-val">{{ displayPrefs.fmtAmount(row.endingRmb) }}</span></template>
          </el-table-column>
          <el-table-column label="账项调整" width="110" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.adjustment" :disabled="isReadonly" :controls="false" size="small" @change="(v: number | undefined) => updateCell(row.id, 'adjustment', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="审定原币" width="110" align="right">
            <template #default="{ row }"><span class="readonly-val">{{ displayPrefs.fmtAmount(row.auditedFc) }}</span></template>
          </el-table-column>
          <el-table-column label="审定人民币" width="120" align="right">
            <template #default="{ row }"><span class="readonly-val">{{ displayPrefs.fmtAmount(row.auditedRmb) }}</span></template>
          </el-table-column>
          <el-table-column label="查询余额" width="110" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.queryBalance" :disabled="isReadonly" :controls="false" size="small" @change="(v: number | undefined) => updateCell(row.id, 'queryBalance', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="差异" width="110" align="right">
            <template #default="{ row }">
              <span :class="{ 'red-text': Math.abs(row.diff) > 0.005 }">{{ displayPrefs.fmtAmount(row.diff) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="索引号" width="100">
            <template #default="{ row }">
              <el-input :model-value="row.indexNo" :disabled="isReadonly" size="small" @change="(v: string) => updateCell(row.id, 'indexNo', v)" />
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="120">
            <template #default="{ row }">
              <el-input :model-value="row.note" :disabled="isReadonly" size="small" @change="(v: string) => updateCell(row.id, 'note', v)" />
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="70" fixed="right" align="center">
            <template #default="{ row }">
              <el-button type="danger" text size="small" @click="removeRow(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- Total Row -->
        <div class="total-row">
          <span class="total-label">合计</span>
          <span>期初: {{ displayPrefs.fmtAmount(totalRow.opening) }}</span>
          <span>期末原币: {{ displayPrefs.fmtAmount(totalRow.endingFc) }}</span>
          <span>本位币: {{ displayPrefs.fmtAmount(totalRow.endingRmb) }}</span>
          <span>审定人民币: {{ displayPrefs.fmtAmount(totalRow.auditedRmb) }}</span>
        </div>

        <!-- 审计说明 + 审计结论 -->
        <div class="audit-notes-section">
          <div class="note-block">
            <label class="note-label">审计说明</label>
            <el-input
              type="textarea"
              :model-value="auditNote"
              :disabled="isReadonly"
              :autosize="{ minRows: 2, maxRows: 6 }"
              placeholder="填写审计说明"
              @change="onNoteChange"
            />
          </div>
          <div class="note-block">
            <label class="note-label">审计结论</label>
            <el-input
              type="textarea"
              :model-value="auditConclusion"
              :disabled="isReadonly"
              :autosize="{ minRows: 2, maxRows: 6 }"
              placeholder="填写审计结论"
              @change="onConclusionChange"
            />
          </div>
        </div>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-digital-currency { padding: 12px 0; }
.toolbar { margin-bottom: 12px; }
.readonly-val { color: #909399; background: #f5f7fa; padding: 2px 6px; border-radius: 2px; }
.red-text { color: #f56c6c; font-weight: 600; }
.total-row {
  display: flex; gap: 16px; padding: 10px 12px; margin-top: 8px;
  background: #f5f7fa; border: 1px solid #ebeef5; border-radius: 4px;
  font-weight: 700; font-size: 13px; flex-wrap: wrap;
}
.total-label { color: #303133; min-width: 40px; }
.audit-notes-section { margin-top: 16px; display: flex; flex-direction: column; gap: 12px; }
.note-block { display: flex; flex-direction: column; gap: 4px; }
.note-label { font-weight: 600; font-size: 13px; color: #303133; }
</style>
