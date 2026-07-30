<template>
  <div class="k7-tab-disclosure-listed">
    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>附注披露信息（上市公司）</h3>
      <div class="header-actions">
        <el-button size="small" type="success" :disabled="isReadonly" @click="syncToDisclosureNotes">同步到附注</el-button>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="openReview?.('K7-disclosure-listed')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>按CAS16政府补助准则，递延收益应按相关类型（与资产相关/与收益相关）披露期初余额、本期增加、本期减少（分摊至损益）和期末余额。数据来自K7-1审定表，subscribe 'substantive:adjudicated' 事件自动刷新。</p>
    </div>

    <!-- ═══ 自动取数提示 ═══ -->
    <el-alert v-if="hasAutoData" type="success" :closable="true" style="margin-bottom:10px" show-icon>
      <template #title>已从K7-1审定表自动取数填充附注数据</template>
    </el-alert>

    <!-- ═══ 与资产相关递延收益 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-head">
          <span class="card-title">与资产相关的政府补助</span>
        </div>
      </template>
      <el-table :data="assetRelatedRows" border size="small" style="width:100%" show-summary :summary-method="assetSummary">
        <el-table-column prop="project" label="项目" min-width="150" />
        <el-table-column prop="beginBalance" label="期初余额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.beginBalance" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateAssetField(row.id, 'beginBalance', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.increase" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateAssetField(row.id, 'increase', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.decrease" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateAssetField(row.id, 'decrease', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :title="`期末 = 期初 + 增加 - 减少 = ${row.beginBalance} + ${row.increase} - ${row.decrease}`">{{ fmtAmt(row.beginBalance + row.increase - row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="形成原因" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && !row.isTotal" :model-value="row.reason" size="small" placeholder="形成原因" @change="(v: string) => updateAssetField(row.id, 'reason', v)" />
            <span v-else>{{ row.reason || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 与收益相关递延收益 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-head">
          <span class="card-title">与收益相关的政府补助</span>
        </div>
      </template>
      <el-table :data="incomeRelatedRows" border size="small" style="width:100%" show-summary :summary-method="incomeSummary">
        <el-table-column prop="project" label="项目" min-width="150" />
        <el-table-column prop="beginBalance" label="期初余额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.beginBalance" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateIncomeField(row.id, 'beginBalance', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.increase" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateIncomeField(row.id, 'increase', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.decrease" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateIncomeField(row.id, 'decrease', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :title="`期末 = 期初 + 增加 - 减少 = ${row.beginBalance} + ${row.increase} - ${row.decrease}`">{{ fmtAmt(row.beginBalance + row.increase - row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="形成原因" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && !row.isTotal" :model-value="row.reason" size="small" placeholder="形成原因" @change="(v: string) => updateIncomeField(row.id, 'reason', v)" />
            <span v-else>{{ row.reason || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 附注说明文本 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-head">
          <span class="card-title">附注说明</span>
          <el-button size="small" type="primary" plain @click="handleAiNarrative">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="narrativeText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="附注说明文本（可AI辅助生成）"
        @blur="handleNarrativeSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司附注按相关类型（与资产/与收益相关）分别披露递延收益变动情况</li>
        <li>表格规格：18行×11列（含合计行）</li>
        <li>期末余额为公式列（期末=期初+增加-减少）</li>
        <li>数据来源：K7-1审定表审定数据，subscribe EventBus自动刷新</li>
        <li>形成原因应说明政府补助项目名称及拨款依据</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K7TabDisclosureListed.vue — 附注披露信息（上市公司）18行×11列
 *
 * Spec: .kiro/specs/k7-deferred-income/ | Task: 4.6
 * Requirements: 6.1
 *
 * 功能：
 * - 按相关类型（与资产相关/与收益相关）披露
 * - Columns: 项目/期初余额/本期增加/本期减少/期末余额/形成原因
 * - Auto data fetch from K7-1 审定表 (subscribe substantive:adjudicated EventBus)
 * - AI assisted (section: overall-opinion)
 */
import { ref, computed, onMounted, onUnmounted, inject, toRef, type Ref } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildK7SyncPayload, K7_NOTE_SECTION } from '../../composables/k7NoteSectionMap'

const K7_ACCOUNT_CODE = '2401'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// 父组件模板绑定会自动解包顶层 ref → 子组件收到纯 Map；重新包成 ref 供内部逻辑使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const openReview = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

// ─── 数据模型 ────────────────────────────────────────────────────────────────

interface DisclosureRow {
  id: string
  project: string
  beginBalance: number
  increase: number
  decrease: number
  reason: string
  isTotal?: boolean
  isAutoFill?: boolean
}

const assetRelatedRows = ref<DisclosureRow[]>([])
const incomeRelatedRows = ref<DisclosureRow[]>([])
const narrativeText = ref('')
const hasAutoData = ref(false)

// ─── 默认行 ──────────────────────────────────────────────────────────────────

function initDefaultRows(): void {
  const assetDefaults = ['设备购置补助', '厂房建设补助', '技改项目补助', '环保设备补助', '其他与资产相关补助']
  const incomeDefaults = ['研发费用补助', '稳岗补贴', '产业扶持资金', '出口退税补贴', '其他与收益相关补助']

  assetRelatedRows.value = assetDefaults.map((name, idx) => ({
    id: `asset-${idx}`,
    project: name,
    beginBalance: 0,
    increase: 0,
    decrease: 0,
    reason: '',
  }))

  incomeRelatedRows.value = incomeDefaults.map((name, idx) => ({
    id: `income-${idx}`,
    project: name,
    beginBalance: 0,
    increase: 0,
    decrease: 0,
    reason: '',
  }))
}

// ─── 加载已保存数据 ──────────────────────────────────────────────────────────

function loadSavedData(): void {
  const savedAsset = allResponsesRef.value.get('K7-disclosure-listed-asset-rows')
  if (savedAsset?.remark) {
    try {
      assetRelatedRows.value = JSON.parse(savedAsset.remark)
    } catch { initDefaultRows() }
  } else {
    initDefaultRows()
  }

  const savedIncome = allResponsesRef.value.get('K7-disclosure-listed-income-rows')
  if (savedIncome?.remark) {
    try {
      incomeRelatedRows.value = JSON.parse(savedIncome.remark)
    } catch { /* keep default */ }
  }

  const savedNarrative = allResponsesRef.value.get('K7-disclosure-listed-narrative')
  if (savedNarrative?.remark) {
    narrativeText.value = savedNarrative.remark
  }
}

// ─── 自动取数（从K7-1审定表） ────────────────────────────────────────────────

function applyAutoFill(): void {
  const adjData = allResponsesRef.value.get('K7-1-audited-by-type')
  if (adjData?.remark) {
    hasAutoData.value = true
    try {
      const data = JSON.parse(adjData.remark)
      if (data?.assetRelated) {
        for (const row of assetRelatedRows.value) {
          const src = data.assetRelated[row.project]
          if (src) {
            row.beginBalance = Number(src.beginBalance ?? 0)
            row.increase = Number(src.increase ?? 0)
            row.decrease = Number(src.decrease ?? 0)
            row.isAutoFill = true
          }
        }
      }
      if (data?.incomeRelated) {
        for (const row of incomeRelatedRows.value) {
          const src = data.incomeRelated[row.project]
          if (src) {
            row.beginBalance = Number(src.beginBalance ?? 0)
            row.increase = Number(src.increase ?? 0)
            row.decrease = Number(src.decrease ?? 0)
            row.isAutoFill = true
          }
        }
      }
    } catch { /* silent */ }
  }
}

// ─── 字段更新 ────────────────────────────────────────────────────────────────

function updateAssetField(id: string, field: string, value: any): void {
  const row = assetRelatedRows.value.find(r => r.id === id)
  if (row) {
    ;(row as any)[field] = value
    persistAssetRows()
  }
}

function updateIncomeField(id: string, field: string, value: any): void {
  const row = incomeRelatedRows.value.find(r => r.id === id)
  if (row) {
    ;(row as any)[field] = value
    persistIncomeRows()
  }
}

// ─── 持久化 ──────────────────────────────────────────────────────────────────

function persistAssetRows(): void {
  emit('save', 'K7-disclosure-listed-asset-rows', { remark: JSON.stringify(assetRelatedRows.value) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function persistIncomeRows(): void {
  emit('save', 'K7-disclosure-listed-income-rows', { remark: JSON.stringify(incomeRelatedRows.value) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleNarrativeSave(): void {
  emit('save', 'K7-disclosure-listed-narrative', { remark: narrativeText.value })
  // Publish disclosure:note-text-updated
  eventBus.emit('disclosure:note-text-updated' as any, {
    wpCode: 'K7',
    variant: 'listed',
    text: narrativeText.value,
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 合计汇总方法 ────────────────────────────────────────────────────────────

function assetSummary({ columns, data }: { columns: any[]; data: DisclosureRow[] }): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (['beginBalance', 'increase', 'decrease'].includes(prop)) {
      const total = data.reduce((s, r) => s + (Number((r as any)[prop]) || 0), 0)
      return fmtAmt(total)
    }
    if (idx === 4) {
      // 期末余额合计
      const total = data.reduce((s, r) => s + r.beginBalance + r.increase - r.decrease, 0)
      return fmtAmt(total)
    }
    return ''
  })
}

function incomeSummary({ columns, data }: { columns: any[]; data: DisclosureRow[] }): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (['beginBalance', 'increase', 'decrease'].includes(prop)) {
      const total = data.reduce((s, r) => s + (Number((r as any)[prop]) || 0), 0)
      return fmtAmt(total)
    }
    if (idx === 4) {
      const total = data.reduce((s, r) => s + r.beginBalance + r.increase - r.decrease, 0)
      return fmtAmt(total)
    }
    return ''
  })
}

// ─── AI ──────────────────────────────────────────────────────────────────────

function handleAiGenerate(): void {
  emit('save', 'K7-disclosure-listed-ai-trigger', { remark: 'overall-opinion' })
}

function handleAiNarrative(): void {
  emit('save', 'K7-disclosure-listed-ai-narrative', { remark: 'narrative-generate' })
}

async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  // 附注 五、51 只有 1 张表 → 与资产相关 / 与收益相关 两张底稿表的行拼成一个列表。
  // 上市版 5 个值列（末列 形成原因），期末余额由 builder 按 F51-3 算（期初+增加−减少）。
  const rows = [...assetRelatedRows.value, ...incomeRelatedRows.value]
    .filter(r => !r.isTotal)
    .map(r => ({
      project: r.project,
      beginBalance: r.beginBalance ?? 0,
      increase: r.increase ?? 0,
      decrease: r.decrease ?? 0,
      reason: r.reason ?? '',
    }))
  const payload = buildK7SyncPayload('listed', props.wpId || '', rows, narrativeText.value)
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K7', variant: 'listed', accountCode: '2401',
      projectId: props.projectId, sectionIds: [K7_NOTE_SECTION.listed],
    })
    ElMessage.success('已同步到附注')
  } catch { /* silent */ }
}

// ─── EventBus ────────────────────────────────────────────────────────────────

function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === K7_ACCOUNT_CODE || payload.wpCode === 'K7') {
    applyAutoFill()
  }
}

function handleAdjustmentCreated(payload: any): void {
  if (!payload || payload.accountCode === K7_ACCOUNT_CODE || payload.wpCode === 'K7') {
    applyAutoFill()
  }
}

onMounted(() => {
  loadSavedData()
  applyAutoFill()
  eventBus.on('substantive:adjudicated', handleAdjudicated)
  eventBus.on('adjustment:created', handleAdjustmentCreated)
})

onUnmounted(() => {
  autoSync.cancelPending()
  eventBus.off('substantive:adjudicated', handleAdjudicated)
  eventBus.off('adjustment:created', handleAdjustmentCreated)
})

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  if (val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k7-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.disclosure-card { margin-bottom: 14px; }
.disclosure-card :deep(.el-card__header) { padding: 10px 16px; }
.card-head { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.formula-cell { text-decoration: underline dashed; cursor: help; color: #409eff; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table__footer-wrapper td) { font-weight: 600; }
.k7-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
