<template>
  <div class="k6-tab-disclosure-soe">
    <!-- Section标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">附注披露信息（国企）</h3>
      <div class="head-actions">
        <el-button size="small" type="success" :disabled="isReadonly" @click="syncToDisclosureNotes">同步到附注</el-button>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="openReview('K6-disclosure-soe')">💬复核</el-button>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS42第29-30条：持有待售的非流动资产或处置组应在附注中披露描述/预计处置方式和时间安排/减值损失金额/处置组营业利润或亏损。国有企业按国资委格式披露，侧重资产保值增值和处置合规性。</p>
    </div>

    <!-- Section 1: 持有待售资产一览 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>一、持有待售资产明细</span>
          <el-tag v-if="hasAutoData" type="primary" size="small" effect="light">跨sheet自动取数</el-tag>
        </div>
      </template>

      <el-table :data="assetSummary" border size="small" style="width: 100%" max-height="300">
        <el-table-column prop="category" label="项目" width="140" fixed />
        <el-table-column label="账面价值" width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="110" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmt(row.impairment) }}</span>
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
        <el-table-column label="处置进展" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal"
              :model-value="row.disposalProgress"
              :disabled="isReadonly"
              size="small"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="处置进展说明"
              @blur="(e: FocusEvent) => handleAssetField(row.id, 'disposalProgress', (e.target as HTMLTextAreaElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="审批情况" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal"
              :model-value="row.approvalStatus"
              :disabled="isReadonly"
              size="small"
              placeholder="审批文号"
              @blur="(e: FocusEvent) => handleAssetField(row.id, 'approvalStatus', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Section 2: 处置组负债 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>二、处置组相关负债</span>
        </div>
      </template>

      <el-table :data="liabilitySummary" border size="small" style="width: 100%" max-height="250">
        <el-table-column prop="category" label="项目" width="140" fixed />
        <el-table-column label="期初余额" width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.openingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期变动" width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmt(row.periodChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
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
              :autosize="{ minRows: 1, maxRows: 2 }"
              placeholder="说明"
              @blur="(e: FocusEvent) => handleLiabField(row.id, 'remark', (e.target as HTMLTextAreaElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Section 3: CAS42(3)(4) 减值损失 + 处置组损益 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>三、已确认减值损失及处置组损益（CAS42第30条）</span>
          <el-tag v-if="impairmentAutoFilled" type="primary" size="small" effect="light">减值自动取数</el-tag>
        </div>
      </template>
      <div class="cas42-fields">
        <div class="cas42-field">
          <span class="cas42-label">(3) 本期已确认减值损失金额</span>
          <el-input-number
            v-model="impairmentLoss"
            :controls="false"
            :precision="2"
            :disabled="isReadonly"
            size="small"
            class="cas42-input"
            @change="persistCas42"
          />
          <span class="cas42-hint">（来自K6-5减值测试/K6-1减值合计）</span>
        </div>
        <div class="cas42-field">
          <span class="cas42-label">(4) 报告期间处置组营业利润/亏损</span>
          <el-input-number
            v-model="disposalGroupProfit"
            :controls="false"
            :precision="2"
            :disabled="isReadonly"
            size="small"
            class="cas42-input"
            @change="persistCas42"
          />
          <span class="cas42-hint">（正=利润，负=亏损）</span>
        </div>
      </div>
    </el-card>

    <!-- Section 4: 处置合规性与补充说明 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>四、处置合规性、保值增值与处置安排</span>
          <el-button size="small" type="primary" plain :loading="aiLoading" @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="narrativeText"
        :disabled="isReadonly"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="国资处置合规性说明、保值增值分析、处置方式和时间安排（可AI辅助生成）"
        @blur="handleNarrativeSave"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="k6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国企版格式（约61行×8列），侧重资产保值增值与处置合规性</li>
        <li>监听 substantive:adjudicated 自动同步K6-1审定数据</li>
        <li>国资监管要求：处置前需经评估、审批、公开挂牌等程序</li>
        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
        <li>金额单位默认"元"</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabDisclosureSoe.vue — 附注披露（国企）
 * Spec: .kiro/specs/k6-held-for-sale/ Task 4.6
 * Requirements: 8.1
 *
 * 功能：
 * - 国企版附注披露 (61行×8列)
 * - subscribe 'substantive:adjudicated' 刷新
 * - AI辅助
 * - Same pattern as Listed but different dimensions
 */
import { ref, onMounted, onBeforeUnmount, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'

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
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

// ─── Data Models ─────────────────────────────────────────────────────────────

interface AssetSoeRow {
  id: string
  category: string
  bookValue: number
  impairment: number
  fairValueNet: number
  openingBalance: number
  closingBalance: number
  disposalProgress: string
  approvalStatus: string
  isTotal: boolean
  isAutoFill: boolean
}

interface LiabSoeRow {
  id: string
  category: string
  openingBalance: number
  periodChange: number
  closingBalance: number
  remark: string
  isTotal: boolean
  isAutoFill: boolean
}

// ─── State ───────────────────────────────────────────────────────────────────

const assetSummary = ref<AssetSoeRow[]>([])
const liabilitySummary = ref<LiabSoeRow[]>([])
const narrativeText = ref('')
const hasAutoData = ref(false)

// CAS42 第30条(3)(4)
const impairmentLoss = ref(0)
const disposalGroupProfit = ref(0)
const impairmentAutoFilled = ref(false)
const aiLoading = ref(false)

// ─── Init ────────────────────────────────────────────────────────────────────

function initDefaultAssetTable(): void {
  const categories = ['固定资产', '在建工程', '无形资产', '长期股权投资', '其他']
  assetSummary.value = [
    ...categories.map((cat, idx) => ({
      id: `soe-asset-${idx}`,
      category: cat,
      bookValue: 0,
      impairment: 0,
      fairValueNet: 0,
      openingBalance: 0,
      closingBalance: 0,
      disposalProgress: '',
      approvalStatus: '',
      isTotal: false,
      isAutoFill: false,
    })),
    {
      id: 'soe-asset-total',
      category: '合计',
      bookValue: 0,
      impairment: 0,
      fairValueNet: 0,
      openingBalance: 0,
      closingBalance: 0,
      disposalProgress: '',
      approvalStatus: '',
      isTotal: true,
      isAutoFill: false,
    },
  ]
}

function initDefaultLiabTable(): void {
  const categories = ['应付账款', '其他应付款', '应付职工薪酬', '其他']
  liabilitySummary.value = [
    ...categories.map((cat, idx) => ({
      id: `soe-liab-${idx}`,
      category: cat,
      openingBalance: 0,
      periodChange: 0,
      closingBalance: 0,
      remark: '',
      isTotal: false,
      isAutoFill: false,
    })),
    {
      id: 'soe-liab-total',
      category: '合计',
      openingBalance: 0,
      periodChange: 0,
      closingBalance: 0,
      remark: '',
      isTotal: true,
      isAutoFill: false,
    },
  ]
}

// ─── Load ────────────────────────────────────────────────────────────────────

function loadSavedData(): void {
  const savedAssets = props.allResponses.get('K6-disclosure-soe-asset-table')
  if (savedAssets?.remark) {
    try { assetSummary.value = JSON.parse(savedAssets.remark) }
    catch { initDefaultAssetTable() }
  } else {
    initDefaultAssetTable()
  }

  const savedLiab = props.allResponses.get('K6-disclosure-soe-liab-table')
  if (savedLiab?.remark) {
    try { liabilitySummary.value = JSON.parse(savedLiab.remark) }
    catch { initDefaultLiabTable() }
  } else {
    initDefaultLiabTable()
  }

  const savedNarrative = props.allResponses.get('K6-disclosure-soe-narrative')
  if (savedNarrative?.remark) narrativeText.value = savedNarrative.remark

  _loadCas42()
}

function applyAutoFill(): void {
  // 从K6-2明细表按类别聚合（K6-2 持久化键为 K6-2-rows）
  const k6_2 = props.allResponses.get('K6-2-rows')
  const raw = k6_2?.remark ?? (typeof k6_2 === 'string' ? k6_2 : null)
  if (raw) {
    try {
      const rows = JSON.parse(raw)
      if (Array.isArray(rows) && rows.length > 0) {
        hasAutoData.value = true
        for (const row of assetSummary.value) {
          if (row.isTotal) continue
          row.bookValue = 0; row.impairment = 0; row.fairValueNet = 0; row.closingBalance = 0; row.isAutoFill = false
        }
        for (const r of rows) {
          const cat = r.category || '其他'
          let target = assetSummary.value.find(x => !x.isTotal && x.category === cat)
          if (!target) target = assetSummary.value.find(x => !x.isTotal && x.category === '其他')
          if (!target) continue
          target.bookValue += Number(r.bookValue) || 0
          target.impairment += Number(r.impairmentProvision) || 0
          target.fairValueNet += Number(r.fairValueNet) || 0
          target.closingBalance += Number(r.bookValue) || 0
          target.isAutoFill = true
        }
        recalcAssetTotals()
      }
    } catch { /* silent */ }
  }

  // 减值损失从K6-1/K6-5带入（仅未手工录入时）
  if (impairmentLoss.value === 0) {
    const k6_1_imp = props.allResponses.get('K6-1-impairment-total')
    const k6_5_imp = props.allResponses.get('K6-5-impairment-total')
    const impVal = Number(k6_1_imp?.remark ?? 0) || Number(k6_5_imp?.remark ?? 0) || 0
    if (impVal > 0) {
      impairmentLoss.value = impVal
      impairmentAutoFilled.value = true
    }
  }
}

function recalcAssetTotals(): void {
  const totalRow = assetSummary.value.find(r => r.isTotal)
  if (totalRow) {
    const dataRows = assetSummary.value.filter(r => !r.isTotal)
    totalRow.bookValue = dataRows.reduce((s, r) => s + r.bookValue, 0)
    totalRow.impairment = dataRows.reduce((s, r) => s + r.impairment, 0)
    totalRow.fairValueNet = dataRows.reduce((s, r) => s + r.fairValueNet, 0)
    totalRow.openingBalance = dataRows.reduce((s, r) => s + r.openingBalance, 0)
    totalRow.closingBalance = dataRows.reduce((s, r) => s + r.closingBalance, 0)
  }
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAssetField(rowId: string, field: string, value: string): void {
  const row = assetSummary.value.find(r => r.id === rowId)
  if (row) {
    ;(row as any)[field] = value
    persistAssetTable()
  }
}

function handleLiabField(rowId: string, field: string, value: string): void {
  const row = liabilitySummary.value.find(r => r.id === rowId)
  if (row) {
    ;(row as any)[field] = value
    persistLiabTable()
  }
}

function handleNarrativeSave(): void {
  emit('save', 'K6-disclosure-soe-narrative', { remark: narrativeText.value })
  eventBus.emit('disclosure:note-text-updated' as any, {
    wpCode: 'K6',
    variant: 'soe',
    text: narrativeText.value,
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── CAS42(3)(4) 持久化 ──────────────────────────────────────────────────────

function persistCas42(): void {
  impairmentAutoFilled.value = false
  emit('save', 'K6-disclosure-soe-cas42', {
    remark: JSON.stringify({
      impairmentLoss: impairmentLoss.value,
      disposalGroupProfit: disposalGroupProfit.value,
    }),
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function _loadCas42(): void {
  const saved = props.allResponses.get('K6-disclosure-soe-cas42')
  if (saved?.remark) {
    try {
      const d = JSON.parse(saved.remark)
      impairmentLoss.value = Number(d.impairmentLoss) || 0
      disposalGroupProfit.value = Number(d.disposalGroupProfit) || 0
    } catch { /* ignore */ }
  }
}

// ─── AI辅助（真实接入/ai/generate-text） ─────────────────────────────────────

async function handleAiGenerate(): Promise<void> {
  if (props.isReadonly || aiLoading.value) return
  aiLoading.value = true
  try {
    const totalRow = assetSummary.value.find(r => r.isTotal)
    const context: Record<string, string> = {
      '持有待售资产账面合计': String(totalRow?.bookValue ?? 0),
      '公允净额合计': String(totalRow?.fairValueNet ?? 0),
      '本期已确认减值损失': String(impairmentLoss.value),
      '处置组营业利润/亏损': String(disposalGroupProfit.value),
    }
    const resp = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'k6-disclosure-soe',
      context,
      prompt: '根据持有待售资产/负债披露数据，生成国有企业附注披露说明（侧重处置合规性、资产保值增值、评估审批公开挂牌程序、CAS42第30条减值损失及处置组损益）',
      existingContent: narrativeText.value,
    })
    const text = resp?.data?.content || resp?.data?.text || resp?.content || ''
    if (text) {
      narrativeText.value = text
      handleNarrativeSave()
      ElMessage.success('AI披露说明已生成')
    }
  } catch (e: any) {
    ElMessage.error('AI生成失败: ' + (e?.message || '未知错误'))
  } finally {
    aiLoading.value = false
  }
}

// ─── Persist ─────────────────────────────────────────────────────────────────

function persistAssetTable(): void {
  emit('save', 'K6-disclosure-soe-asset-table', { remark: JSON.stringify(assetSummary.value) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function persistLiabTable(): void {
  emit('save', 'K6-disclosure-soe-liab-table', { remark: JSON.stringify(liabilitySummary.value) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  const rows = assetSummary.value.filter(r => !r.isTotal).map(r => ({ project: r.category, endAmount: r.closingBalance ?? 0, priorAmount: r.openingBalance ?? 0 }))
  const narrative = narrativeText.value
  const payload = {
    wp_id: props.wpId,
    sheet_name: 'K6-note-soe',
    section_id: '八、12',
    current_standard: 'soe_standalone',
    sub_table_data: { rows },
    _note_texts: narrative ? [{ section: 'main', title: '说明', text: narrative }] : [],
  }
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K6', variant: 'soe', accountCode: '1481',
      projectId: props.projectId, sectionIds: ['八、12'],
    })
    ElMessage.success('已同步到附注')
  } catch { /* silent */ }
}

// ─── EventBus: subscribe 'substantive:adjudicated' ───────────────────────────

function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === K6_ACCOUNT_CODE || payload.wpCode === 'K6') {
    applyAutoFill()
  }
}

function handleAdjustmentCreated(payload: any): void {
  if (!payload || payload.wpCode === 'K6') {
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
  autoSync.cancelPending()
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
.k6-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
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

/* CAS42(3)(4) 字段 */
.cas42-fields { display: flex; flex-direction: column; gap: 12px; }
.cas42-field { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.cas42-label { min-width: 220px; font-size: var(--wp-font-size, 13px); color: #303133; }
.cas42-input { width: 180px; }
.cas42-input :deep(.el-input__inner) { text-align: right; }
.cas42-hint { font-size: 12px; color: #909399; }

.k6-details-tip { margin-top: 16px; font-size: 12px; color: #666; }
.k6-details-tip summary { cursor: pointer; color: #409eff; font-weight: 500; }
.k6-details-tip ul { margin: 8px 0 0 16px; line-height: 1.8; }
</style>
