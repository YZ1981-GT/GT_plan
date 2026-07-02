<script setup lang="ts">
/**
 * E1TabCreditReport.vue — E1-18/19 征信 (variant: query/check)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.13
 *
 * - Props include variant detected from sheetName (E1-18→'query', E1-19→'check')
 * - Simple dynamic table (no composable, implement inline like E1-11)
 * - Query mode: 借款人 | 征信代码 | 贷款卡编码 | 查询日期 | 查询结果
 * - Check mode: 征信项目 | 征信金额 | 账面金额 | 差异(readonly) | 核对结果
 * - Storage: 'E1-credit-query-rows' / 'E1-credit-check-rows'
 *
 * Requirements: 10.1-10.2
 */
import { ref, computed, inject, toRef, watch, onBeforeUnmount } from 'vue'

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

// ─── Variant ─────────────────────────────────────────────────────────────────

type CreditVariant = 'query' | 'check'

const variant = computed<CreditVariant>(() => {
  const name = props.sheetName || ''
  if (name.includes('E1-19') || name.includes('核对')) return 'check'
  return 'query'
})

const storageKey = computed(() =>
  variant.value === 'query' ? 'E1-credit-query-rows' : 'E1-credit-check-rows'
)

// ─── Types ───────────────────────────────────────────────────────────────────

interface QueryRow {
  id: string
  borrower: string
  creditCode: string
  loanCardCode: string
  queryDate: string
  queryResult: string
}

interface CheckRow {
  id: string
  creditItem: string
  creditAmount: number
  bookAmount: number
  diff: number
  checkResult: string
}

type CreditRow = QueryRow | CheckRow

// ─── State ───────────────────────────────────────────────────────────────────

const rows = ref<CreditRow[]>([])

function generateId(): string {
  return `cr-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createEmptyRow(): CreditRow {
  if (variant.value === 'query') {
    return { id: generateId(), borrower: '', creditCode: '', loanCardCode: '', queryDate: '', queryResult: '' }
  }
  return { id: generateId(), creditItem: '', creditAmount: 0, bookAmount: 0, diff: 0, checkResult: '' }
}

// ─── Load ────────────────────────────────────────────────────────────────────

function loadFromResponses(): void {
  const resp = props.allResponses.get(storageKey.value)
  if (!resp?.remark) {
    rows.value = [createEmptyRow()]
    return
  }
  try {
    const parsed = JSON.parse(resp.remark)
    if (!Array.isArray(parsed) || parsed.length === 0) {
      rows.value = [createEmptyRow()]
      return
    }
    if (variant.value === 'query') {
      rows.value = parsed.map((r: any) => ({
        id: r.id || generateId(),
        borrower: String(r.borrower || ''),
        creditCode: String(r.creditCode || ''),
        loanCardCode: String(r.loanCardCode || ''),
        queryDate: String(r.queryDate || ''),
        queryResult: String(r.queryResult || ''),
      }))
    } else {
      rows.value = parsed.map((r: any) => {
        const creditAmount = Number(r.creditAmount) || 0
        const bookAmount = Number(r.bookAmount) || 0
        return {
          id: r.id || generateId(),
          creditItem: String(r.creditItem || ''),
          creditAmount,
          bookAmount,
          diff: creditAmount - bookAmount,
          checkResult: String(r.checkResult || ''),
        }
      })
    }
  } catch {
    rows.value = [createEmptyRow()]
  }
}

loadFromResponses()

// ─── Serialize & Save ────────────────────────────────────────────────────────

function serializeRows(): string {
  return JSON.stringify(rows.value.map(r => {
    const { ...data } = r as any
    if (variant.value === 'check') {
      const { diff, ...rest } = data
      return rest
    }
    return data
  }))
}

let saveTimer: ReturnType<typeof setTimeout> | null = null

function scheduleSave(): void {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    persistToResponses()
  }, 2000)
}

function persistToResponses(): void {
  const serialized = serializeRows()
  const key = storageKey.value
  const items = [{ item_id: key, conclusion: null, remark: serialized }]
  props.allResponses.set(key, items[0])
  props.saveImmediate(items).catch(() => {})
}

// ─── CRUD ────────────────────────────────────────────────────────────────────

function addRow(): void {
  if (props.isReadonly) return
  rows.value = [...rows.value, createEmptyRow()]
  scheduleSave()
}

function removeRow(id: string): void {
  if (props.isReadonly) return
  rows.value = rows.value.filter(r => r.id !== id)
  scheduleSave()
}

function updateQueryCell(id: string, field: string, value: string): void {
  if (props.isReadonly) return
  const idx = rows.value.findIndex(r => r.id === id)
  if (idx === -1) return
  const row = { ...rows.value[idx] } as any
  row[field] = value
  rows.value = [...rows.value.slice(0, idx), row, ...rows.value.slice(idx + 1)]
  scheduleSave()
}

function updateCheckCell(id: string, field: string, value: number | string): void {
  if (props.isReadonly) return
  const idx = rows.value.findIndex(r => r.id === id)
  if (idx === -1) return
  const row = { ...rows.value[idx] } as any
  if (field === 'creditAmount' || field === 'bookAmount') {
    row[field] = Number(value) || 0
    row.diff = (row.creditAmount || 0) - (row.bookAmount || 0)
  } else {
    row[field] = String(value)
  }
  rows.value = [...rows.value.slice(0, idx), row, ...rows.value.slice(idx + 1)]
  scheduleSave()
}

// ─── Cleanup ─────────────────────────────────────────────────────────────────

onBeforeUnmount(() => {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
    persistToResponses()
  }
})
</script>

<template>
  <div class="e1-tab-credit-report">
    <!-- Query Mode (E1-18) -->
    <template v-if="variant === 'query'">
      <el-table :data="rows" border stripe size="small" max-height="500" style="width: 100%">
        <el-table-column label="借款人" width="140">
          <template #default="{ row }">
            <el-input :model-value="(row as QueryRow).borrower" :disabled="isReadonly" size="small"
              @change="(val: string) => updateQueryCell(row.id, 'borrower', val)" />
          </template>
        </el-table-column>
        <el-table-column label="征信代码" width="130">
          <template #default="{ row }">
            <el-input :model-value="(row as QueryRow).creditCode" :disabled="isReadonly" size="small"
              @change="(val: string) => updateQueryCell(row.id, 'creditCode', val)" />
          </template>
        </el-table-column>
        <el-table-column label="贷款卡编码" width="150">
          <template #default="{ row }">
            <el-input :model-value="(row as QueryRow).loanCardCode" :disabled="isReadonly" size="small"
              @change="(val: string) => updateQueryCell(row.id, 'loanCardCode', val)" />
          </template>
        </el-table-column>
        <el-table-column label="查询日期" width="140">
          <template #default="{ row }">
            <el-date-picker :model-value="(row as QueryRow).queryDate" :disabled="isReadonly" type="date"
              value-format="YYYY-MM-DD" size="small" style="width: 100%"
              @update:model-value="(val: string) => updateQueryCell(row.id, 'queryDate', val || '')" />
          </template>
        </el-table-column>
        <el-table-column label="查询结果" min-width="150">
          <template #default="{ row }">
            <el-input :model-value="(row as QueryRow).queryResult" :disabled="isReadonly" size="small"
              @change="(val: string) => updateQueryCell(row.id, 'queryResult', val)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" type="danger" text size="small" @click="removeRow(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- Check Mode (E1-19) -->
    <template v-else>
      <el-table :data="rows" border stripe size="small" max-height="500" style="width: 100%">
        <el-table-column label="征信项目" width="150">
          <template #default="{ row }">
            <el-input :model-value="(row as CheckRow).creditItem" :disabled="isReadonly" size="small"
              @change="(val: string) => updateCheckCell(row.id, 'creditItem', val)" />
          </template>
        </el-table-column>
        <el-table-column label="征信金额" width="150" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="(row as CheckRow).creditAmount" :disabled="isReadonly"
              :controls="false" size="small"
              @change="(val: number) => updateCheckCell(row.id, 'creditAmount', val ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="账面金额" width="150" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="(row as CheckRow).bookAmount" :disabled="isReadonly"
              :controls="false" size="small"
              @change="(val: number) => updateCheckCell(row.id, 'bookAmount', val ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="差异" width="130" align="right">
          <template #default="{ row }">
            <span class="computed-cell">{{ displayPrefs.fmtAmount((row as CheckRow).diff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对结果" min-width="120">
          <template #default="{ row }">
            <el-select :model-value="(row as CheckRow).checkResult" :disabled="isReadonly" size="small" placeholder="选择"
              @change="(val: string) => updateCheckCell(row.id, 'checkResult', val)">
              <el-option label="一致" value="一致" />
              <el-option label="不一致" value="不一致" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" type="danger" text size="small" @click="removeRow(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <el-button v-if="!isReadonly" size="small" class="add-btn" @click="addRow">+ 添加行</el-button>
  </div>
</template>

<style scoped>
.e1-tab-credit-report {
  padding: 12px 0;
}
.computed-cell {
  color: #606266;
  font-style: italic;
}
.add-btn {
  margin-top: 8px;
}
</style>
