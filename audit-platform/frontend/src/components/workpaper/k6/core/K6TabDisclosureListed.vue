<template>
  <div class="k6-tab-disclosure-listed">
    <!-- Section标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">附注披露信息（上市公司）</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="openReview('K6-disclosure-listed')">💬复核</el-button>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS42第29-30条：持有待售的非流动资产或处置组应在附注中披露：(1)非流动资产或处置组的描述；(2)预计处置方式和时间安排；(3)已确认的减值损失及其金额；(4)报告期间处置组所产生的营业利润或亏损。上市公司按证监会格式披露。</p>
    </div>

    <!-- Section 1: 持有待售资产变动表 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>一、持有待售资产</span>
          <el-tag v-if="hasAutoData" type="primary" size="small" effect="light">跨sheet自动取数</el-tag>
        </div>
      </template>

      <el-table :data="assetTable" border size="small" style="width: 100%" max-height="350">
        <el-table-column prop="category" label="项目" width="140" fixed />
        <el-table-column label="账面原值" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计折旧" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.accumulatedDep) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.impairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面价值" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允价值" width="110" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmt(row.fairValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="出售费用" width="100" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmt(row.sellingCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允净额" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.fairValueNet) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.openingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right">
          <template #default="{ row }">
            <strong :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.closingBalance) }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal"
              :model-value="row.remark"
              :disabled="isReadonly"
              size="small"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="变动原因"
              @blur="(e: FocusEvent) => handleFieldChange(row.id, 'remark', (e.target as HTMLTextAreaElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Section 2: 持有待售负债 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>二、持有待售负债</span>
        </div>
      </template>

      <el-table :data="liabilityTable" border size="small" style="width: 100%" max-height="300">
        <el-table-column prop="category" label="项目" width="140" fixed />
        <el-table-column label="期初余额" width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.openingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
          <template #default="{ row }">
            <strong :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.closingBalance) }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal"
              :model-value="row.remark"
              :disabled="isReadonly"
              size="small"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="负债项说明"
              @blur="(e: FocusEvent) => handleLiabFieldChange(row.id, 'remark', (e.target as HTMLTextAreaElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Section 3: 处置安排及损益 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>三、处置安排与已确认损益</span>
          <el-button size="small" type="primary" plain @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="disposalNarrative"
        :disabled="isReadonly"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="描述处置方式/时间安排/已确认损益金额（可AI辅助生成）"
        @blur="handleNarrativeSave"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="k6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司格式（约79行×11列），分持有待售资产/负债/处置安排三大部分</li>
        <li>监听 substantive:adjudicated 自动同步K6-1审定数据（浅蓝色=跨sheet自动取数）</li>
        <li>公允价值净额=公允价值-预计出售费用（虚线公式列）</li>
        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
        <li>金额单位默认"元"，千分位分隔</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabDisclosureListed.vue — 附注披露（上市公司）
 * Spec: .kiro/specs/k6-held-for-sale/ Task 4.6
 * Requirements: 8.1
 *
 * 功能：
 * - 上市公司版附注披露 (79行×11列)
 * - subscribe 'substantive:adjudicated' 刷新
 * - AI辅助生成 (section='overall-opinion')
 * - autosize textarea for notes
 * - 审计说明 + 结论 el-card
 */
import { ref, computed, onMounted, onBeforeUnmount, inject } from 'vue'
import { eventBus } from '@/utils/eventBus'

const K6_ACCOUNT_CODE = '1481'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

const openReview = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── Data Models ─────────────────────────────────────────────────────────────

interface AssetDisclosureRow {
  id: string
  category: string
  originalCost: number
  accumulatedDep: number
  impairment: number
  bookValue: number       // 公式：原值 - 折旧 - 减值
  fairValue: number
  sellingCost: number
  fairValueNet: number    // 公式：公允 - 出售费用
  openingBalance: number
  closingBalance: number
  remark: string
  isTotal: boolean
  isAutoFill: boolean
}

interface LiabilityDisclosureRow {
  id: string
  category: string
  openingBalance: number
  increase: number
  decrease: number
  closingBalance: number
  remark: string
  isTotal: boolean
  isAutoFill: boolean
}

// ─── State ───────────────────────────────────────────────────────────────────

const assetTable = ref<AssetDisclosureRow[]>([])
const liabilityTable = ref<LiabilityDisclosureRow[]>([])
const disposalNarrative = ref('')
const hasAutoData = ref(false)

// ─── Init ────────────────────────────────────────────────────────────────────

function initDefaultAssetTable(): void {
  const categories = ['固定资产', '在建工程', '无形资产', '长期股权投资', '投资性房地产', '其他非流动资产']
  assetTable.value = [
    ...categories.map((cat, idx) => ({
      id: `asset-${idx}`,
      category: cat,
      originalCost: 0,
      accumulatedDep: 0,
      impairment: 0,
      bookValue: 0,
      fairValue: 0,
      sellingCost: 0,
      fairValueNet: 0,
      openingBalance: 0,
      closingBalance: 0,
      remark: '',
      isTotal: false,
      isAutoFill: false,
    })),
    {
      id: 'asset-total',
      category: '合计',
      originalCost: 0,
      accumulatedDep: 0,
      impairment: 0,
      bookValue: 0,
      fairValue: 0,
      sellingCost: 0,
      fairValueNet: 0,
      openingBalance: 0,
      closingBalance: 0,
      remark: '',
      isTotal: true,
      isAutoFill: false,
    },
  ]
}

function initDefaultLiabTable(): void {
  const categories = ['应付账款', '其他应付款', '预收款项', '应付职工薪酬', '其他']
  liabilityTable.value = [
    ...categories.map((cat, idx) => ({
      id: `liab-${idx}`,
      category: cat,
      openingBalance: 0,
      increase: 0,
      decrease: 0,
      closingBalance: 0,
      remark: '',
      isTotal: false,
      isAutoFill: false,
    })),
    {
      id: 'liab-total',
      category: '合计',
      openingBalance: 0,
      increase: 0,
      decrease: 0,
      closingBalance: 0,
      remark: '',
      isTotal: true,
      isAutoFill: false,
    },
  ]
}

// ─── Load ────────────────────────────────────────────────────────────────────

function loadSavedData(): void {
  const savedAssets = props.allResponses.get('K6-disclosure-listed-asset-table')
  if (savedAssets?.remark) {
    try { assetTable.value = JSON.parse(savedAssets.remark) }
    catch { initDefaultAssetTable() }
  } else {
    initDefaultAssetTable()
  }

  const savedLiab = props.allResponses.get('K6-disclosure-listed-liab-table')
  if (savedLiab?.remark) {
    try { liabilityTable.value = JSON.parse(savedLiab.remark) }
    catch { initDefaultLiabTable() }
  } else {
    initDefaultLiabTable()
  }

  const savedNarrative = props.allResponses.get('K6-disclosure-listed-narrative')
  if (savedNarrative?.remark) disposalNarrative.value = savedNarrative.remark

  const savedConclusion = props.allResponses.get('K6-disclosure-listed-conclusion')
}

function applyAutoFill(): void {
  // 从K6-1审定数据自动填充
  const adjTotal = props.allResponses.get('K6-1-audited-total')
  if (adjTotal?.remark) {
    hasAutoData.value = true
    try {
      const data = JSON.parse(adjTotal.remark)
      if (data && typeof data === 'object') {
        // Apply asset data
        for (const row of assetTable.value) {
          if (!row.isTotal && data.assets?.[row.category]) {
            const d = data.assets[row.category]
            row.originalCost = Number(d.originalCost ?? 0)
            row.accumulatedDep = Number(d.accumulatedDep ?? 0)
            row.impairment = Number(d.impairment ?? 0)
            row.bookValue = row.originalCost - row.accumulatedDep - row.impairment
            row.openingBalance = Number(d.openingBalance ?? 0)
            row.closingBalance = Number(d.closingBalance ?? 0)
            row.isAutoFill = true
          }
        }
        recalcAssetTotals()
      }
    } catch { /* silent */ }
  }
}

function recalcAssetTotals(): void {
  const totalRow = assetTable.value.find(r => r.isTotal)
  if (totalRow) {
    const dataRows = assetTable.value.filter(r => !r.isTotal)
    totalRow.originalCost = dataRows.reduce((s, r) => s + r.originalCost, 0)
    totalRow.accumulatedDep = dataRows.reduce((s, r) => s + r.accumulatedDep, 0)
    totalRow.impairment = dataRows.reduce((s, r) => s + r.impairment, 0)
    totalRow.bookValue = dataRows.reduce((s, r) => s + r.bookValue, 0)
    totalRow.fairValue = dataRows.reduce((s, r) => s + r.fairValue, 0)
    totalRow.sellingCost = dataRows.reduce((s, r) => s + r.sellingCost, 0)
    totalRow.fairValueNet = dataRows.reduce((s, r) => s + r.fairValueNet, 0)
    totalRow.openingBalance = dataRows.reduce((s, r) => s + r.openingBalance, 0)
    totalRow.closingBalance = dataRows.reduce((s, r) => s + r.closingBalance, 0)
  }
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleFieldChange(rowId: string, field: string, value: string): void {
  const row = assetTable.value.find(r => r.id === rowId)
  if (row) {
    ;(row as any)[field] = value
    persistAssetTable()
  }
}

function handleLiabFieldChange(rowId: string, field: string, value: string): void {
  const row = liabilityTable.value.find(r => r.id === rowId)
  if (row) {
    ;(row as any)[field] = value
    persistLiabTable()
  }
}

function handleNarrativeSave(): void {
  emit('save', 'K6-disclosure-listed-narrative', { remark: disposalNarrative.value })
  eventBus.emit('disclosure:note-text-updated' as any, {
    wpCode: 'K6',
    variant: 'listed',
    text: disposalNarrative.value,
  })
}

function handleConclusionSave(): void {
}

function handleAiGenerate(): void {
  emit('save', 'K6-disclosure-listed-ai-trigger', { remark: 'overall-opinion' })
}

// ─── Persist ─────────────────────────────────────────────────────────────────

function persistAssetTable(): void {
  emit('save', 'K6-disclosure-listed-asset-table', { remark: JSON.stringify(assetTable.value) })
}

function persistLiabTable(): void {
  emit('save', 'K6-disclosure-listed-liab-table', { remark: JSON.stringify(liabilityTable.value) })
}

// ─── EventBus: subscribe 'substantive:adjudicated' ───────────────────────────

function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === K6_ACCOUNT_CODE || payload.wpCode === 'K6') {
    applyAutoFill()
  }
}

function handleAdjustmentCreated(payload: any): void {
  if (!payload || payload.wpCode === 'K6') {
    // 调整分录变化时刷新附注数据
    applyAutoFill()
  }
}

onMounted(() => {
  loadSavedData()
  applyAutoFill()
  eventBus.on('substantive:adjudicated', handleAdjudicated)
  eventBus.on('adjustment:created', handleAdjustmentCreated)
})

onBeforeUnmount(() => {
  eventBus.off('substantive:adjudicated', handleAdjudicated)
  eventBus.off('adjustment:created', handleAdjustmentCreated)
})

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k6-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; }

.methodology-context {
  border-left: 3px solid #f0a500; background: #fef9e7; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #7d6608; line-height: 1.6;
}
.methodology-context p { margin: 0; }

.disclosure-section { margin-bottom: 12px; }
.conclusion-card { margin-bottom: 12px; }
.section-card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }

.formula-col :deep(.cell) { border-bottom: 1px dashed #409eff; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.auto-data { color: #409eff; }

.k6-details-tip { margin-top: 16px; font-size: 12px; color: #666; }
.k6-details-tip summary { cursor: pointer; color: #409eff; font-weight: 500; }
.k6-details-tip ul { margin: 8px 0 0 16px; line-height: 1.8; }
</style>
