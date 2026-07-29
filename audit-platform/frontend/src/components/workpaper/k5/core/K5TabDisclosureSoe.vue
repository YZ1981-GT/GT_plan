<template>
  <div class="k5-tab-disclosure-soe">
    <!-- Section标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">附注披露信息（国企）</h3>
      <div class="head-actions">
        <el-button size="small" type="success" :disabled="isReadonly" @click="syncToDisclosureNotes">同步到附注</el-button>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="openReview('K5-disclosure-soe')">💬复核</el-button>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>国企版附注：CAS13或有负债披露要求+国资委附加披露（诉讼/担保/环保义务明细+风险等级判断）。31行×14列结构，含分类统计与风险等级。</p>
    </div>

    <!-- Section 1: 预计负债变动表 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>一、预计负债变动情况</span>
          <el-tag v-if="hasAutoData" type="primary" size="small" effect="light">跨sheet自动取数</el-tag>
        </div>
      </template>

      <el-table :data="provisionTable" border size="small" style="width: 100%" max-height="400">
        <el-table-column prop="category" label="项目" width="140" fixed />
        <el-table-column label="期初余额" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期计提" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期转销/冲回" width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right">
          <template #default="{ row }">
            <strong :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.endBalance) }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="确认依据" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal"
              :model-value="row.basis"
              :disabled="isReadonly"
              size="small"
              placeholder="确认依据"
              @blur="(e: FocusEvent) => handleFieldChange(row.id, 'basis', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="100">
          <template #default="{ row }">
            <el-select
              v-if="!row.isTotal"
              :model-value="row.riskLevel"
              :disabled="isReadonly"
              size="small"
              placeholder="—"
              @change="(v: string) => handleFieldChange(row.id, 'riskLevel', v)"
            >
              <el-option label="高" value="high" />
              <el-option label="中" value="medium" />
              <el-option label="低" value="low" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Section 2: 或有负债+担保披露 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>二、或有负债及担保情况</span>
          <el-tag v-if="contingentItems.length > 0" type="warning" size="small">{{ contingentItems.length }} 项</el-tag>
        </div>
      </template>

      <el-empty v-if="contingentItems.length === 0" description="暂无需披露的或有负债/担保（K5-2明细中“可能”事项将自动出现）" />

      <el-table v-else :data="contingentItems" border size="small" style="width: 100%">
        <el-table-column type="index" label="序" width="48" align="center" />
        <el-table-column prop="item" label="或有事项" min-width="120" />
        <el-table-column prop="nature" label="性质/类型" width="100" />
        <el-table-column label="涉及金额" width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.financialImpact) }}</template>
        </el-table-column>
        <el-table-column label="可能性" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.likelihood === 'possible'" type="warning" size="small">可能</el-tag>
            <span v-else>{{ row.likelihood }}</span>
          </template>
        </el-table-column>
        <el-table-column label="披露说明" min-width="200">
          <template #default="{ row }">
            <el-input
              :model-value="row.disclosure"
              :disabled="isReadonly"
              size="small"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="披露说明"
              @blur="(e: FocusEvent) => handleContingentField(row.id, 'disclosure', (e.target as HTMLTextAreaElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Section 2.1: 诉讼明细（自动从K5-6筛选） -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>（1）未决诉讼/仲裁明细</span>
          <el-tag v-if="litigationDisclosureItems.length > 0" type="danger" size="small">{{ litigationDisclosureItems.length }} 项</el-tag>
        </div>
      </template>
      <el-empty v-if="litigationDisclosureItems.length === 0" description="暂无（K5-6中诉讼事项将自动出现）" />
      <el-table v-else :data="litigationDisclosureItems" border size="small" style="width: 100%">
        <el-table-column type="index" label="序" width="42" align="center" />
        <el-table-column prop="caseName" label="案件名称" min-width="120" />
        <el-table-column label="涉案金额" width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.amount) }}</template>
        </el-table-column>
        <el-table-column prop="stage" label="阶段" width="80" />
        <el-table-column label="败诉可能性" width="100">
          <template #default="{ row }">
            <el-tag :type="row.likelihood === 'very_likely' ? 'danger' : 'warning'" size="small">{{ row.likelihood === 'very_likely' ? '很可能' : '可能' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="确认/预计金额" width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.estimatedLoss) }}</template>
        </el-table-column>
        <el-table-column label="风险等级" width="90">
          <template #default="{ row }">
            <el-select :model-value="row.riskLevel || ''" :disabled="isReadonly" size="small" placeholder="—" @change="(v: string) => handleLitigationRisk(row.id, v)">
              <el-option label="高" value="high" /><el-option label="中" value="medium" /><el-option label="低" value="low" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Section 2.2: 环保/弃置义务明细（自动从K5-5筛选） -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>（2）环保/弃置义务明细</span>
          <el-tag v-if="decommissionDisclosureItems.length > 0" type="success" size="small">{{ decommissionDisclosureItems.length }} 项</el-tag>
        </div>
      </template>
      <el-empty v-if="decommissionDisclosureItems.length === 0" description="暂无（K5-5中弃置费用数据将自动出现）" />
      <el-table v-else :data="decommissionDisclosureItems" border size="small" style="width: 100%">
        <el-table-column type="index" label="序" width="42" align="center" />
        <el-table-column prop="assetName" label="资产名称" min-width="130" />
        <el-table-column label="预计弃置支出" width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.futureExpense) }}</template>
        </el-table-column>
        <el-table-column label="折现率" width="80" align="right">
          <template #default="{ row }">{{ row.discountRate ? (row.discountRate * 100).toFixed(2) + '%' : '-' }}</template>
        </el-table-column>
        <el-table-column label="期末现值" width="110" align="right">
          <template #default="{ row }"><strong>{{ fmtAmt(row.endBalance) }}</strong></template>
        </el-table-column>
        <el-table-column label="风险等级" width="90">
          <template #default="{ row }">
            <el-select :model-value="row.riskLevel || ''" :disabled="isReadonly" size="small" placeholder="—" @change="(v: string) => handleDecommissionRisk(row.id, v)">
              <el-option label="高" value="high" /><el-option label="中" value="medium" /><el-option label="低" value="low" />
            </el-select>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Section 3: 叙述式结论 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>三、补充说明</span>
          <el-button size="small" type="primary" plain @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="narrativeText"
        :disabled="isReadonly"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        placeholder="国企附注补充说明文字（可AI辅助生成）"
        @blur="handleNarrativeSave"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国企附注格式（约31行×14列），含风险等级列（高/中/低）</li>
        <li>监听 substantive:adjudicated(2701) 自动同步审定数据（浅蓝色=跨sheet自动取数）</li>
        <li>与上市公司版区别：含风险等级/确认依据列；使用中文编号（一、二...）</li>
        <li>或有负债+担保从K5-2明细和K5-6诉讼自动筛选"可能"级别事项</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabDisclosureSoe.vue — 附注披露信息（国企版）
 *
 * - Section ① 预计负债变动表（含风险等级列）
 * - Section ② 或有负债+担保情况
 * - Section ③ 补充说明
 *
 * EventBus: subscribe 'substantive:adjudicated' → auto-refresh
 *           subscribe 'adjustment:created' → auto-refresh
 *           publish 'disclosure:note-text-updated' on text change
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 6.1
 * Requirements: 9.1, 2.7
 */
import { ref, onMounted, onBeforeUnmount, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'

const K5_ACCOUNT_CODE = '2701'

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

// ─── State ───────────────────────────────────────────────────────────────────

interface ProvisionRow {
  id: string
  category: string
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  basis: string
  riskLevel: string
  isTotal: boolean
  isAutoFill: boolean
}

interface ContingentItem {
  id: string
  item: string
  nature: string
  financialImpact: number
  likelihood: string
  disclosure: string
}

const provisionTable = ref<ProvisionRow[]>([])
const contingentItems = ref<ContingentItem[]>([])
const narrativeText = ref('')
const hasAutoData = ref(false)

// ─── Load ────────────────────────────────────────────────────────────────────

function loadSavedData(): void {
  const saved = props.allResponses.get('K5-disclosure-soe-provision-table')
  if (saved?.remark) {
    try { provisionTable.value = JSON.parse(saved.remark) }
    catch { initDefaultTable() }
  } else {
    initDefaultTable()
  }

  const savedContingent = props.allResponses.get('K5-disclosure-soe-contingent')
  if (savedContingent?.remark) {
    try { contingentItems.value = JSON.parse(savedContingent.remark) }
    catch { contingentItems.value = [] }
  }

  const savedNarrative = props.allResponses.get('K5-disclosure-soe-narrative')
  if (savedNarrative?.remark) {
    narrativeText.value = savedNarrative.remark
  }
}

function initDefaultTable(): void {
  const categories = ['产品质量保证', '未决诉讼', '亏损合同', '重组义务', '弃置义务', '担保', '环保义务', '其他']
  provisionTable.value = [
    ...categories.map((cat, idx) => ({
      id: `row-${idx}`,
      category: cat,
      beginBalance: 0,
      increase: 0,
      decrease: 0,
      endBalance: 0,
      basis: '',
      riskLevel: '',
      isTotal: false,
      isAutoFill: false,
    })),
    {
      id: 'row-total',
      category: '合计',
      beginBalance: 0,
      increase: 0,
      decrease: 0,
      endBalance: 0,
      basis: '',
      riskLevel: '',
      isTotal: true,
      isAutoFill: false,
    },
  ]
}

function applyAutoFill(): void {
  const adjTotal = props.allResponses.get('K5-1-audited-total')
  if (adjTotal?.remark) {
    hasAutoData.value = true
    try {
      const data = JSON.parse(adjTotal.remark)
      if (data && typeof data === 'object') {
        for (const row of provisionTable.value) {
          if (!row.isTotal && data[row.category]) {
            const d = data[row.category]
            row.beginBalance = Number(d.beginBalance ?? 0)
            row.increase = Number(d.increase ?? 0)
            row.decrease = Number(d.decrease ?? 0)
            row.endBalance = Number(d.endBalance ?? 0)
            row.isAutoFill = true
          }
        }
        const totalRow = provisionTable.value.find(r => r.isTotal)
        if (totalRow) {
          const dataRows = provisionTable.value.filter(r => !r.isTotal)
          totalRow.beginBalance = dataRows.reduce((s, r) => s + r.beginBalance, 0)
          totalRow.increase = dataRows.reduce((s, r) => s + r.increase, 0)
          totalRow.decrease = dataRows.reduce((s, r) => s + r.decrease, 0)
          totalRow.endBalance = dataRows.reduce((s, r) => s + r.endBalance, 0)
        }
      }
    } catch { /* silent */ }
  }

  // 从 K5-2 明细表筛选或有负债披露项
  const detailData = props.allResponses.get('K5-2-detail-rows')
  if (detailData?.remark) {
    try {
      const rows: any[] = JSON.parse(detailData.remark)
      contingentItems.value = rows
        .filter(r => r.lossLikelihood === 'possible' || r.recognition === 'disclose')
        .map((r, idx) => ({
          id: `contingent-${idx}`,
          item: r.caseName || r.item || r.project || `事项${idx + 1}`,
          nature: r.nature || r.type || '待补充',
          financialImpact: Number(r.amount || r.estimatedLoss || 0),
          likelihood: 'possible',
          disclosure: r.disclosure || '',
        }))
    } catch { /* silent */ }
  }
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleFieldChange(rowId: string, field: string, value: string): void {
  const row = provisionTable.value.find(r => r.id === rowId)
  if (row) {
    ;(row as any)[field] = value
    persistTable()
  }
}

function handleContingentField(id: string, field: string, value: string): void {
  const item = contingentItems.value.find(r => r.id === id)
  if (item) {
    ;(item as any)[field] = value
    persistContingent()
  }
}

function handleNarrativeSave(): void {
  emit('save', 'K5-disclosure-soe-narrative', { remark: narrativeText.value })
  eventBus.emit('disclosure:note-text-updated' as any, {
    wpCode: 'K5',
    variant: 'soe',
    text: narrativeText.value,
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleAiGenerate(): void {
  emit('save', 'K5-disclosure-soe-ai-trigger', { remark: 'contingency-disclosure' })
}

function persistTable(): void {
  emit('save', 'K5-disclosure-soe-provision-table', { remark: JSON.stringify(provisionTable.value) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function persistContingent(): void {
  emit('save', 'K5-disclosure-soe-contingent', { remark: JSON.stringify(contingentItems.value) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  const rows = provisionTable.value.filter(r => !r.isTotal).map(r => ({ project: r.category, endAmount: r.endBalance ?? 0, priorAmount: r.beginBalance ?? 0 }))
  const narrative = narrativeText.value
  const payload = {
    wp_id: props.wpId,
    sheet_name: 'K5-note-soe',
    section_id: '八、55',
    current_standard: 'soe_standalone',
    sub_table_data: { rows },
    _note_texts: narrative ? [{ section: 'main', title: '说明', text: narrative }] : [],
  }
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K5', variant: 'soe', accountCode: '2701',
      projectId: props.projectId, sectionIds: ['八、55'],
    })
    ElMessage.success('已同步到附注')
  } catch { /* silent */ }
}

// ─── 分项明细（诉讼/弃置，自动从K5-6/K5-5筛选） ─────────────────────────────

interface LitigationDisclosureItem {
  id: string
  caseName: string
  amount: number
  stage: string
  likelihood: string
  estimatedLoss: number
  riskLevel: string
}

interface DecommissionDisclosureItem {
  id: string
  assetName: string
  futureExpense: number
  discountRate: number
  endBalance: number
  riskLevel: string
}

const litigationDisclosureItems = ref<LitigationDisclosureItem[]>([])
const decommissionDisclosureItems = ref<DecommissionDisclosureItem[]>([])

function loadSubCategoryItems(): void {
  // 从 K5-6 诉讼表筛选
  const litigationData = props.allResponses.get('K5-6-litigation-rows')
  if (litigationData?.remark) {
    try {
      const rows: any[] = JSON.parse(litigationData.remark)
      litigationDisclosureItems.value = rows
        .filter(r => r.lossLikelihood === 'very_likely' || r.lossLikelihood === 'possible')
        .map((r, idx) => ({
          id: `lit-${idx}`,
          caseName: r.caseName || `案件${idx + 1}`,
          amount: Number(r.amount || 0),
          stage: r.stage || '',
          likelihood: r.lossLikelihood || 'possible',
          estimatedLoss: Number(r.estimatedLoss || r.bookProvision || 0),
          riskLevel: r.riskLevel || '',
        }))
    } catch { litigationDisclosureItems.value = [] }
  }

  // 从 K5-5 弃置表筛选
  const decommissionData = props.allResponses.get('K5-5-decommission-rows')
  if (decommissionData?.remark) {
    try {
      const rows: any[] = JSON.parse(decommissionData.remark)
      decommissionDisclosureItems.value = rows
        .filter(r => Number(r.endBalance || 0) > 0)
        .map((r, idx) => ({
          id: `dec-${idx}`,
          assetName: r.assetName || `资产${idx + 1}`,
          futureExpense: Number(r.futureExpense || 0),
          discountRate: Number(r.discountRate || 0),
          endBalance: Number(r.endBalance || 0),
          riskLevel: r.riskLevel || '',
        }))
    } catch { decommissionDisclosureItems.value = [] }
  }
}

function handleLitigationRisk(id: string, value: string): void {
  const item = litigationDisclosureItems.value.find(r => r.id === id)
  if (item) { item.riskLevel = value }
  emit('save', 'K5-disclosure-soe-litigation-risk', { remark: JSON.stringify(litigationDisclosureItems.value) })
}

function handleDecommissionRisk(id: string, value: string): void {
  const item = decommissionDisclosureItems.value.find(r => r.id === id)
  if (item) { item.riskLevel = value }
  emit('save', 'K5-disclosure-soe-decommission-risk', { remark: JSON.stringify(decommissionDisclosureItems.value) })
}

// ─── EventBus: subscribe 'substantive:adjudicated' + 'adjustment:created' ═══

function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === K5_ACCOUNT_CODE || payload.wpCode === 'K5') {
    applyAutoFill()
  }
}

function handleAdjustmentCreated(payload: any): void {
  if (!payload || payload.accountCode === K5_ACCOUNT_CODE || payload.wpCode === 'K5') {
    applyAutoFill()
  }
}

onMounted(() => {
  eventBus.on('substantive:adjudicated', handleAdjudicated)
  eventBus.on('adjustment:created', handleAdjustmentCreated)
  loadSavedData()
  applyAutoFill()
  loadSubCategoryItems()
})

onBeforeUnmount(() => {
  autoSync.cancelPending()
  eventBus.off('substantive:adjudicated', handleAdjudicated)
  eventBus.off('adjustment:created', handleAdjustmentCreated)
})

// ─── Formatting ──────────────────────────────────────────────────────────────

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k5-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.head-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.disclosure-section { margin-bottom: 14px; }
.section-card-header { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.auto-data { color: #409eff; font-style: italic; }
:deep(.el-card__header) { padding: 10px 16px; background: #fafafa; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
