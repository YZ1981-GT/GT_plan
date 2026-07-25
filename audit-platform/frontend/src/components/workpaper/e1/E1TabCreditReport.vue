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
import { ref, computed, inject, toRef, watch, onMounted, onBeforeUnmount } from 'vue'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { amountFormatter, amountParser } from '../composables/wpAmountInput'

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

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

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

// ─── 审计说明 / 审计结论 ─────────────────────────────────────────────────────

const NOTE_KEY = computed(() => `E1-credit-audit-note-${variant.value}`)
const CONCLUSION_KEY = computed(() => `E1-credit-audit-conclusion-${variant.value}`)
const auditNote = ref('')
const auditConclusion = ref('')

function loadAuditText(): void {
  const noteResp = props.allResponses.get(NOTE_KEY.value)
  auditNote.value = noteResp?.remark || ''
  const concResp = props.allResponses.get(CONCLUSION_KEY.value)
  auditConclusion.value = concResp?.remark || ''
}

onMounted(loadAuditText)
watch(variant, loadAuditText)

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY.value, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY.value, item)
  void props.saveImmediate([item])
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY.value, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY.value, item)
  void props.saveImmediate([item])
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
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 通过中国人民银行征信系统查询企业信用报告，取得贷款卡编码及查询授权。</p>
        <p>2. 核对征信报告披露的银行账户、贷款卡与账面记录（E1-10 账户核对）的一致性。</p>
        <p>3. 关注征信报告中的未入账借款、对外担保、票据承兑等或有事项。</p>
        <p>4. 核对差异应查明原因并评估对财务报表（负债完整性）的影响。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：通过征信报告核查银行账户与借款的完整性，识别未入账负债与或有事项。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" :type="variant === 'check' ? 'warning' : 'success'">
          {{ variant === 'check' ? '征信核对 (E1-19)' : '征信查询 (E1-18)' }}
        </el-tag>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-10" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

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
        <el-table-column label="操作" width="70" align="center" fixed="right">
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
              :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small"
              @change="(val: number) => updateCheckCell(row.id, 'creditAmount', val ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="账面金额" width="150" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="(row as CheckRow).bookAmount" :disabled="isReadonly"
              :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small"
              @change="(val: number) => updateCheckCell(row.id, 'bookAmount', val ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="差异" width="130" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="auto-calc-value">{{ displayPrefs.fmtAmount((row as CheckRow).diff) }}</span>
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
        <el-table-column label="操作" width="70" align="center" fixed="right">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" type="danger" text size="small" @click="removeRow(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计说明</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        :placeholder="variant === 'check'
          ? '填写审计说明：可概述（1）征信报告借款、担保、票据承兑等信息与账面（短期借款L1、长期借款L3）核对情况；（2）核对差异及不一致原因；（3）是否存在未入账借款、对外担保等或有事项。'
          : '填写审计说明：可概述（1）征信报告查询的方式、时间与操作过程（现场查询/被审计单位下载并观察）；（2）取得的贷款卡编码及查询授权情况；（3）征信报告披露的账户与借款概况。'"
        @change="(val: string) => saveAuditNote(val)"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        :placeholder="variant === 'check'
          ? '填写审计结论：A、征信报告信息与账面记录核对一致，未见未入账负债或或有事项。B、除上述差异事项外，核对相符。C、由于存在以下重大不一致（或资料受限），需进一步核查。'
          : '填写审计结论：A、已取得并核查企业信用报告，账户及借款信息完整。B、征信查询程序已执行完毕，具体核对见E1-19。C、因资料受限无法完整查询，需补充程序。'"
        @change="(val: string) => saveAuditConclusion(val)"
      />
    </el-card>
  </div>
</template>

<style scoped>
.e1-tab-credit-report {
  padding: 12px 0;
}
.e1-tab-credit-report :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-credit-report :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
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
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc-value {
  color: #606266;
}
.audit-note-card {
  margin-top: 16px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
</style>
