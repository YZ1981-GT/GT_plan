<script setup lang="ts">
/**
 * E1TabDisclosure.vue — 附注 (variant: listed/soe)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.18
 *
 * - Props: variant detected from sheetName (includes('上市')→'listed', includes('国企')→'soe')
 * - Listed: project rows × 期末数/期初数, from E1-adj-total-* cross-sheet
 * - SOE: adds "受限制货币资金明细" dynamic table
 * - 提示折叠区 (<details> style)
 * - 说明 textarea (editable, bidirectional)
 * - Dual mode support (el-segmented structured/online-edit)
 * - Storage: 'E1-disclosure-{variant}-*'
 *
 * Requirements: 15.1-15.6
 */
import { ref, computed, inject, toRef, watch, onBeforeUnmount } from 'vue'
import GtIndexChip from '../GtIndexChip.vue'

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

// ─── Variant Detection ───────────────────────────────────────────────────────

type DisclosureVariant = 'listed' | 'soe'

const variant = computed<DisclosureVariant>(() => {
  const name = props.sheetName || ''
  if (name.includes('国企')) return 'soe'
  return 'listed'
})

const storagePrefix = computed(() => `E1-disclosure-${variant.value}`)

// ─── Dual Mode ───────────────────────────────────────────────────────────────

const activeMode = ref<'structured' | 'online-edit'>('structured')

// ─── Project Row Items (Listed) ──────────────────────────────────────────────

interface DisclosureRow {
  key: string
  label: string
  crossKey: string  // allResponses key for 期末
  endingAmount: number
  openingAmount: number
}

const LISTED_ITEMS = [
  { key: 'cash', label: '库存现金', crossKey: 'E1-adj-total-1001' },
  { key: 'bank', label: '银行存款', crossKey: 'E1-adj-total-1002' },
  { key: 'finance_co', label: '存放财务公司款项', crossKey: '' },
  { key: 'other_mf', label: '其他货币资金', crossKey: 'E1-adj-total-1012' },
  { key: 'accrued', label: '存款应计利息', crossKey: '' },
  { key: 'digital', label: '数字货币', crossKey: '' },
  { key: 'total', label: '合计', crossKey: '' },
  { key: 'overseas', label: '其中：存放境外', crossKey: '' },
]

// ─── Cross-Sheet + Opening Data ──────────────────────────────────────────────

const openingMap = ref<Record<string, number>>({})

function loadOpenings(): void {
  const key = `${storagePrefix.value}-openings`
  const resp = props.allResponses.get(key)
  if (resp?.remark) {
    try { openingMap.value = JSON.parse(resp.remark) } catch { openingMap.value = {} }
  }
}
loadOpenings()

const disclosureRows = computed<DisclosureRow[]>(() => {
  return LISTED_ITEMS.map(item => {
    let endingAmount = 0
    if (item.crossKey) {
      const resp = props.allResponses.get(item.crossKey)
      endingAmount = Number(resp?.remark) || 0
    }
    // Total row: sum of above items (excluding overseas)
    if (item.key === 'total') {
      endingAmount = LISTED_ITEMS
        .filter(i => !['total', 'overseas'].includes(i.key))
        .reduce((sum, i) => {
          if (!i.crossKey) return sum
          const r = props.allResponses.get(i.crossKey)
          return sum + (Number(r?.remark) || 0)
        }, 0)
    }
    return {
      key: item.key,
      label: item.label,
      crossKey: item.crossKey,
      endingAmount,
      openingAmount: openingMap.value[item.key] || 0,
    }
  })
})

// ─── SOE Restricted Table ────────────────────────────────────────────────────

interface RestrictedRow {
  id: string
  item: string
  amount: number
  reason: string
}

const restrictedRows = ref<RestrictedRow[]>([])

function loadRestricted(): void {
  const key = `${storagePrefix.value}-restricted`
  const resp = props.allResponses.get(key)
  if (resp?.remark) {
    try {
      const parsed = JSON.parse(resp.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        restrictedRows.value = parsed.map((r: any) => ({
          id: r.id || `restr-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          item: String(r.item || ''),
          amount: Number(r.amount) || 0,
          reason: String(r.reason || ''),
        }))
        return
      }
    } catch {}
  }
  restrictedRows.value = [{ id: `restr-${Date.now()}`, item: '', amount: 0, reason: '' }]
}
if (variant.value === 'soe') loadRestricted()

// ─── Note Text ───────────────────────────────────────────────────────────────

const noteText = ref('')

function loadNote(): void {
  const key = `${storagePrefix.value}-note`
  const resp = props.allResponses.get(key)
  noteText.value = resp?.remark || ''
}
loadNote()

// ─── Debounce Save ───────────────────────────────────────────────────────────

let saveTimer: ReturnType<typeof setTimeout> | null = null

function scheduleSave(): void {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { saveTimer = null; persistAll() }, 2000)
}

function persistAll(): void {
  const items: any[] = []
  // Openings
  const openingsKey = `${storagePrefix.value}-openings`
  const openingsJson = JSON.stringify(openingMap.value)
  items.push({ item_id: openingsKey, conclusion: null, remark: openingsJson })
  props.allResponses.set(openingsKey, items[items.length - 1])

  // Note
  const noteKey = `${storagePrefix.value}-note`
  items.push({ item_id: noteKey, conclusion: null, remark: noteText.value })
  props.allResponses.set(noteKey, items[items.length - 1])

  // SOE restricted
  if (variant.value === 'soe') {
    const rKey = `${storagePrefix.value}-restricted`
    const rJson = JSON.stringify(restrictedRows.value.map(r => ({ id: r.id, item: r.item, amount: r.amount, reason: r.reason })))
    items.push({ item_id: rKey, conclusion: null, remark: rJson })
    props.allResponses.set(rKey, items[items.length - 1])
  }

  props.saveImmediate(items).catch(() => {})
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateOpening(key: string, val: number): void {
  if (props.isReadonly) return
  openingMap.value = { ...openingMap.value, [key]: val }
  scheduleSave()
}

function updateNote(val: string): void {
  if (props.isReadonly) return
  noteText.value = val
  scheduleSave()
}

function addRestrictedRow(): void {
  if (props.isReadonly) return
  restrictedRows.value = [...restrictedRows.value, { id: `restr-${Date.now()}`, item: '', amount: 0, reason: '' }]
  scheduleSave()
}

function removeRestrictedRow(id: string): void {
  if (props.isReadonly) return
  restrictedRows.value = restrictedRows.value.filter(r => r.id !== id)
  scheduleSave()
}

function updateRestrictedCell(id: string, field: string, value: any): void {
  if (props.isReadonly) return
  const idx = restrictedRows.value.findIndex(r => r.id === id)
  if (idx === -1) return
  const row = { ...restrictedRows.value[idx] } as any
  row[field] = field === 'amount' ? (Number(value) || 0) : String(value)
  restrictedRows.value = [...restrictedRows.value.slice(0, idx), row, ...restrictedRows.value.slice(idx + 1)]
  scheduleSave()
}

// ─── Cleanup ─────────────────────────────────────────────────────────────────

onBeforeUnmount(() => {
  if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; persistAll() }
})
</script>

<template>
  <div class="e1-tab-disclosure">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 期末数取自 E1-1 审定表各科目审定数（跨sheet自动取数，灰色底纹列不可手工录入）。</p>
        <p>2. 上市公司版：列示库存现金/银行存款/存放财务公司/其他货币资金/应计利息/数字货币。</p>
        <p>3. 国企版：额外列示受限制货币资金明细（保证金/担保存款/境外受限）。</p>
        <p>4. 境外存款需说明汇率中间价参考来源；数字货币列报参照准则解释15号资金集中管理。</p>
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-segmented v-model="activeMode" :options="[
          { label: '结构化视图', value: 'structured' },
          { label: '在线编辑', value: 'online-edit' },
        ]" size="small" />
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
      </div>
    </div>

    <!-- Online Edit placeholder -->
    <div v-if="activeMode === 'online-edit'" class="online-edit-placeholder">
      <el-empty description="在线编辑模式(OnlyOffice)" :image-size="60" />
    </div>

    <!-- Structured View -->
    <template v-else>
      <!-- Disclosure Table -->
      <el-table :data="disclosureRows" border size="small" style="width: 100%; max-width: 700px">
        <el-table-column prop="label" label="项目" width="200">
          <template #default="{ row }">
            <span :class="{ 'font-bold': row.key === 'total' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末数" width="180" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="computed-cell">{{ displayPrefs.fmtAmount(row.endingAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初数" width="180" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.openingAmount"
              :disabled="isReadonly"
              :controls="false"
              size="small"
              @change="(val: number) => updateOpening(row.key, val ?? 0)"
            />
          </template>
        </el-table-column>
      </el-table>

      <!-- SOE: Restricted table -->
      <template v-if="variant === 'soe'">
        <h4 class="section-title">受限制货币资金明细</h4>
        <el-table :data="restrictedRows" border size="small" style="width: 100%; max-width: 700px">
          <el-table-column label="项目" width="200">
            <template #default="{ row }">
              <el-input :model-value="row.item" :disabled="isReadonly" size="small"
                @change="(val: string) => updateRestrictedCell(row.id, 'item', val)" />
            </template>
          </el-table-column>
          <el-table-column label="金额" width="180" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.amount" :disabled="isReadonly"
                :controls="false" size="small"
                @change="(val: number) => updateRestrictedCell(row.id, 'amount', val ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="受限原因" min-width="150">
            <template #default="{ row }">
              <el-input :model-value="row.reason" :disabled="isReadonly" size="small"
                @change="(val: string) => updateRestrictedCell(row.id, 'reason', val)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" align="center">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" type="danger" text size="small"
                @click="removeRestrictedRow(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button v-if="!isReadonly" size="small" class="add-btn" @click="addRestrictedRow">+ 添加行</el-button>
      </template>

      <!-- 附注说明（卡片式） -->
      <el-card class="opinion-card" shadow="never">
        <template #header>
          <div class="opinion-header">
            <span class="opinion-title">附注说明</span>
            <div class="opinion-chips">
              <GtIndexChip value="wp:E1-1" :context-project-id="projectId" />
            </div>
          </div>
        </template>
        <el-input
          :model-value="noteText"
          :disabled="isReadonly"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 14 }"
          placeholder="填写货币资金附注说明（受限/境外/回收风险等）"
          @change="updateNote"
        />
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.e1-tab-disclosure {
  padding: 12px 0;
}
.e1-tab-disclosure :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
}
.e1-tab-disclosure :deep(.el-table .cell) {
  font-size: 13px !important;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.online-edit-placeholder {
  padding: 40px 0;
}
.computed-cell {
  color: #606266;
  font-style: italic;
}
.font-bold {
  font-weight: 700;
}
.section-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.add-btn {
  margin-top: 8px;
}
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
  max-width: 700px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips {
  display: flex;
  gap: 6px;
}
</style>
