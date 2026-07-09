<template>
  <div class="k7-tab-disclosure-soe">
    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>附注披露信息（国有企业）</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="openReview?.('K7-disclosure-soe')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>国企版附注按CAS16政府补助准则，分"与资产相关"和"与收益相关"两类披露递延收益变动。列结构比上市公司版少1列（无"形成原因详细说明"），共18行×10列。数据从K7-1审定表自动获取。</p>
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
        <el-table-column prop="project" label="项目" min-width="160" />
        <el-table-column prop="beginBalance" label="期初余额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.beginBalance" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateAssetField(row.id, 'beginBalance', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.increase" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateAssetField(row.id, 'increase', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.decrease" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateAssetField(row.id, 'decrease', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :title="`期末 = 期初 + 增加 - 减少`">{{ fmtAmt(row.beginBalance + row.increase - row.decrease) }}</span>
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
        <el-table-column prop="project" label="项目" min-width="160" />
        <el-table-column prop="beginBalance" label="期初余额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.beginBalance" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateIncomeField(row.id, 'beginBalance', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.increase" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateIncomeField(row.id, 'increase', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.decrease" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateIncomeField(row.id, 'decrease', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :title="`期末 = 期初 + 增加 - 减少`">{{ fmtAmt(row.beginBalance + row.increase - row.decrease) }}</span>
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
        <li>国企版附注规格：18行×10列（比上市版少"形成原因详细说明"列）</li>
        <li>按相关类型分组披露：与资产相关 / 与收益相关</li>
        <li>期末余额为公式列（期末=期初+增加-减少），负债类方向</li>
        <li>数据来源：K7-1审定表审定数据，subscribe EventBus自动刷新</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K7TabDisclosureSoe.vue — 附注披露信息（国有企业）18行×10列
 *
 * Spec: .kiro/specs/k7-deferred-income/ | Task: 4.6
 * Requirements: 6.1
 *
 * 功能：
 * - 按相关类型（与资产相关/与收益相关）披露（比上市版少形成原因详细说明列）
 * - Columns: 项目/期初余额/本期增加/本期减少/期末余额
 * - Auto data fetch from K7-1 审定表 (subscribe substantive:adjudicated EventBus)
 * - AI assisted (section: overall-opinion)
 */
import { ref, onMounted, onUnmounted, inject, type Ref } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'

const K7_ACCOUNT_CODE = '2401'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Ref<Map<string, any>>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReview = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── 数据模型 ────────────────────────────────────────────────────────────────

interface DisclosureRow {
  id: string
  project: string
  beginBalance: number
  increase: number
  decrease: number
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
  }))

  incomeRelatedRows.value = incomeDefaults.map((name, idx) => ({
    id: `income-${idx}`,
    project: name,
    beginBalance: 0,
    increase: 0,
    decrease: 0,
  }))
}

// ─── 加载已保存数据 ──────────────────────────────────────────────────────────

function loadSavedData(): void {
  const savedAsset = props.allResponses.value.get('K7-disclosure-soe-asset-rows')
  if (savedAsset?.remark) {
    try {
      assetRelatedRows.value = JSON.parse(savedAsset.remark)
    } catch { initDefaultRows() }
  } else {
    initDefaultRows()
  }

  const savedIncome = props.allResponses.value.get('K7-disclosure-soe-income-rows')
  if (savedIncome?.remark) {
    try {
      incomeRelatedRows.value = JSON.parse(savedIncome.remark)
    } catch { /* keep default */ }
  }

  const savedNarrative = props.allResponses.value.get('K7-disclosure-soe-narrative')
  if (savedNarrative?.remark) {
    narrativeText.value = savedNarrative.remark
  }
}

// ─── 自动取数（从K7-1审定表） ────────────────────────────────────────────────

function applyAutoFill(): void {
  const adjData = props.allResponses.value.get('K7-1-audited-by-type')
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
  emit('save', 'K7-disclosure-soe-asset-rows', { remark: JSON.stringify(assetRelatedRows.value) })
}

function persistIncomeRows(): void {
  emit('save', 'K7-disclosure-soe-income-rows', { remark: JSON.stringify(incomeRelatedRows.value) })
}

function handleNarrativeSave(): void {
  emit('save', 'K7-disclosure-soe-narrative', { remark: narrativeText.value })
  // Publish disclosure:note-text-updated
  eventBus.emit('disclosure:note-text-updated' as any, {
    wpCode: 'K7',
    variant: 'soe',
    text: narrativeText.value,
  })
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
  emit('save', 'K7-disclosure-soe-ai-trigger', { remark: 'overall-opinion' })
}

function handleAiNarrative(): void {
  emit('save', 'K7-disclosure-soe-ai-narrative', { remark: 'narrative-generate' })
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
.k7-tab-disclosure-soe { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 13px; color: #78350f; line-height: 1.6; }
.disclosure-card { margin-bottom: 14px; }
.disclosure-card :deep(.el-card__header) { padding: 10px 16px; }
.card-head { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.formula-cell { text-decoration: underline dashed; cursor: help; color: #409eff; }
:deep(.el-table) { font-size: 13px; }
:deep(.el-table__footer-wrapper td) { font-weight: 600; }
.k7-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.k7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
