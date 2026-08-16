<template>
  <div class="m6-tab-disclosure-soe">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（国有企业）</h3>
        <el-tag type="success" size="small">国企</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" :loading="aiLoading === 'disclosure-soe'" :disabled="isReadonly" @click="handleAI('disclosure-soe')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>国有企业未分配利润附注披露（19×18）：</strong>
        按上年末/期初调整/本期年初/增加/减少/期末格式列示未分配利润变动。
        国企格式重点关注一般风险准备、转增资本等特有项目。
        数据自动从审定表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
      </div>
    </div>

    <!-- ═══ Section 1: 未分配利润变动表（国企格式） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>未分配利润变动明细（国企格式）</span>
          <el-button size="small" :loading="aiLoading === 'section-movement'" :disabled="isReadonly" @click="handleAI('section-movement')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="movementRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="220" fixed>
          <template #default="{ row }">
            <span :class="{ 'formula-row': row.isFormula, 'subtotal-row': row.isSubtotal }">
              {{ row.item }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="上年末" min-width="130" align="right">
          <template #default="{ row, $index }">
            <span v-if="row.isFormula" class="formula-cell" :title="row.formulaDesc">
              {{ fmtAmount(row.priorYearEnd) }}
            </span>
            <WpAmountInput
              v-else-if="!isReadonly"
              :model-value="row.priorYearEnd"
              @update:model-value="(val: number) => updateRow($index, 'priorYearEnd', val)"
            />
            <span v-else>{{ fmtAmount(row.priorYearEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初调整" min-width="130" align="right">
          <template #default="{ row, $index }">
            <span v-if="row.isFormula" class="formula-cell" :title="row.formulaDesc">
              {{ fmtAmount(row.beginAdj) }}
            </span>
            <WpAmountInput
              v-else-if="!isReadonly"
              :model-value="row.beginAdj"
              @update:model-value="(val: number) => updateRow($index, 'beginAdj', val)"
            />
            <span v-else>{{ fmtAmount(row.beginAdj) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期年初" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :title="'= 上年末 + 期初调整'">
              {{ fmtAmount(row.beginBalance) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" min-width="130" align="right">
          <template #default="{ row, $index }">
            <span v-if="row.isFormula" class="formula-cell" :title="row.formulaDesc">
              {{ fmtAmount(row.increase) }}
            </span>
            <WpAmountInput
              v-else-if="!isReadonly"
              :model-value="row.increase"
              @update:model-value="(val: number) => updateRow($index, 'increase', val)"
            />
            <span v-else>{{ fmtAmount(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" min-width="130" align="right">
          <template #default="{ row, $index }">
            <span v-if="row.isFormula" class="formula-cell" :title="row.formulaDesc">
              {{ fmtAmount(row.decrease) }}
            </span>
            <WpAmountInput
              v-else-if="!isReadonly"
              :model-value="row.decrease"
              @update:model-value="(val: number) => updateRow($index, 'decrease', val)"
            />
            <span v-else>{{ fmtAmount(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :title="'= 本期年初 + 增加 - 减少'">
              {{ fmtAmount(row.endBalance) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 一般风险准备/转增资本说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>一般风险准备及转增资本说明</span>
          <el-button size="small" :loading="aiLoading === 'section-risk-reserve'" :disabled="isReadonly" @click="handleAI('section-risk-reserve')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="riskReserveNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明一般风险准备计提依据、转增资本情况及审批程序..."
        @change="handleRiskReserveNoteChange"
      />
    </el-card>

    <!-- ═══ Section 3: 国有资本经营收益分配说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>国有资本经营收益分配说明</span>
          <el-button size="small" :loading="aiLoading === 'section-soe-distribution'" :disabled="isReadonly" @click="handleAI('section-soe-distribution')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="soeDistributionNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明国有资本经营收益上缴比例、分配方案及国资委审批情况..."
        @change="handleSoeDistributionNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国企格式按"上年末/期初调整/本期年初/增加/减少/期末"六列列示</li>
        <li>本期年初=上年末+期初调整（只读公式列）</li>
        <li>期末=本期年初+增加-减少（只读公式列）</li>
        <li>国企特有：一般风险准备（金融行业）、转增资本</li>
        <li>数据从审定表和明细表自动拉取，订阅审定事件刷新</li>
        <li>格式：19行×18列</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M6TabDisclosureSoe — 附注披露信息（国有企业）19×18
 *
 * Spec: .kiro/specs/m6-retained-earnings/
 * Task: 4.5
 * Requirements: 5.4, 5.5
 *
 * 功能：
 * - 未分配利润变动表（国企格式）：项目 | 上年末 | 期初调整 | 本期年初 | 增加 | 减少 | 期末
 * - 公式列 read-only（本期年初=上年末+期初调整, 期末=本期年初+增加-减少）
 * - Subscribe 'substantive:adjudicated' to refresh
 * - 国企特定字段：一般风险准备/转增资本
 * - inject openReviewDialog
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useM6FormData } from '../../composables/useM6FormData'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import WpAmountInput from '../../shared/WpAmountInput.vue'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── 同步链路 ───────────────────────────────────────────────────────────────

import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildM6SyncPayload, type M6DisclosureRow } from '../../composables/m6NoteSectionMap'
import http from '@/utils/http'

async function syncToDisclosureNotes(): Promise<void> {
  const rows: M6DisclosureRow[] = movementRows.value
    .filter((r) => !r.isFormula || r.key === 'end-retained')
    .map((r) => ({
      label: r.item.trim(),
      current: r.currentPeriod,
      prior: r.priorPeriod,
    }))
  const noteText = riskReserveNote.value || ''
  const payload = buildM6SyncPayload(props.wpId, 'soe', rows, noteText)
  if (!payload) return
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
  } catch { /* fail-open */ }
}

const { scheduleAutoSync } = useDisclosureAutoSync(syncToDisclosureNotes)

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useM6FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Movement Table Rows (国企格式) ──────────────────────────────────────────

interface SoeMovementRow {
  item: string
  priorYearEnd: number
  beginAdj: number
  beginBalance: number   // 公式: 上年末 + 期初调整
  increase: number
  decrease: number
  endBalance: number     // 公式: 本期年初 + 增加 - 减少
  isFormula: boolean
  isSubtotal: boolean
  formulaDesc?: string
  key: string
}

const movementRows = ref<SoeMovementRow[]>([
  { item: '一、期初未分配利润', priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isFormula: false, isSubtotal: true, key: 'begin-retained' },
  { item: '  加：会计政策变更影响', priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isFormula: false, isSubtotal: false, key: 'policy-change' },
  { item: '  加：前期差错更正影响', priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isFormula: false, isSubtotal: false, key: 'error-correction' },
  { item: '二、本期增加', priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isFormula: true, isSubtotal: true, formulaDesc: '= 本期净利润 + 其他', key: 'total-increase' },
  { item: '  其中：本期净利润', priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isFormula: false, isSubtotal: false, key: 'net-profit' },
  { item: '  其中：其他转入', priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isFormula: false, isSubtotal: false, key: 'other-transfer-in' },
  { item: '三、本期减少', priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isFormula: true, isSubtotal: true, formulaDesc: '= 盈余公积 + 股利 + 风险准备 + 转增资本 + 其他', key: 'total-decrease' },
  { item: '  其中：提取法定盈余公积', priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isFormula: false, isSubtotal: false, key: 'statutory-surplus' },
  { item: '  其中：提取任意盈余公积', priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isFormula: false, isSubtotal: false, key: 'discretionary-surplus' },
  { item: '  其中：应付股利（利润）', priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isFormula: false, isSubtotal: false, key: 'dividend' },
  { item: '  其中：提取一般风险准备', priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isFormula: false, isSubtotal: false, key: 'general-risk-reserve' },
  { item: '  其中：转增资本', priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isFormula: false, isSubtotal: false, key: 'capital-conversion' },
  { item: '  其中：其他', priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isFormula: false, isSubtotal: false, key: 'other-decrease' },
  { item: '四、期末未分配利润', priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, isFormula: true, isSubtotal: true, formulaDesc: '= 期初 + 增加合计 - 减少合计', key: 'end-retained' },
])

// ─── Text Notes ──────────────────────────────────────────────────────────────

const riskReserveNote = ref('')
const soeDistributionNote = ref('')

// ─── Formula Calculations ────────────────────────────────────────────────────

function recalcFormulas() {
  const rows = movementRows.value

  // 计算每行的 beginBalance = priorYearEnd + beginAdj
  for (const row of rows) {
    row.beginBalance = row.priorYearEnd + row.beginAdj
  }

  // 二、本期增加合计 = 净利润 + 其他转入
  const totalIncrease = rows.find(r => r.key === 'total-increase')
  const netProfit = rows.find(r => r.key === 'net-profit')
  const otherIn = rows.find(r => r.key === 'other-transfer-in')
  if (totalIncrease && netProfit && otherIn) {
    totalIncrease.increase = netProfit.increase + otherIn.increase
    totalIncrease.decrease = 0
  }

  // 三、本期减少合计 = 法定盈余 + 任意盈余 + 股利 + 风险准备 + 转增资本 + 其他
  const totalDecrease = rows.find(r => r.key === 'total-decrease')
  const decreaseKeys = ['statutory-surplus', 'discretionary-surplus', 'dividend', 'general-risk-reserve', 'capital-conversion', 'other-decrease']
  if (totalDecrease) {
    totalDecrease.decrease = decreaseKeys.reduce((sum, key) => {
      const row = rows.find(r => r.key === key)
      return sum + (row ? row.decrease : 0)
    }, 0)
    totalDecrease.increase = 0
  }

  // 四、期末未分配利润 = 期初 + 增加合计 - 减少合计
  const endRetained = rows.find(r => r.key === 'end-retained')
  const beginRetained = rows.find(r => r.key === 'begin-retained')
  if (endRetained && beginRetained && totalIncrease && totalDecrease) {
    endRetained.endBalance = beginRetained.beginBalance + totalIncrease.increase - totalDecrease.decrease
  }

  // 计算非公式行的 endBalance = beginBalance + increase - decrease
  for (const row of rows) {
    if (!row.isFormula) {
      row.endBalance = row.beginBalance + row.increase - row.decrease
    }
  }
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateRow(index: number, field: 'priorYearEnd' | 'beginAdj' | 'increase' | 'decrease', val: number) {
  if (index >= 0 && index < movementRows.value.length) {
    movementRows.value[index][field] = val
    recalcFormulas()
    formData.debouncedSave(`M6-disclosure-soe-${movementRows.value[index].key}-${field}`, { remark: String(val) })
    scheduleAutoSync()
  }
}

function handleRiskReserveNoteChange() {
  formData.debouncedSave('M6-disclosure-soe-risk-reserve', { remark: riskReserveNote.value || null })
  scheduleAutoSync()
}

function handleSoeDistributionNoteChange() {
  formData.debouncedSave('M6-disclosure-soe-distribution', { remark: soeDistributionNote.value || null })
  scheduleAutoSync()
}

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const endRow = movementRows.value.find(r => r.key === 'end-retained')
    const context: Record<string, string> = {
      科目: '4104 利润分配-未分配利润 / 附注披露（国有企业）',
      期末未分配利润: fmtAmount(endRow?.endBalance ?? 0),
    }
    if (section === 'section-risk-reserve') {
      const text = await generateAiText({ section: 'm6-disclosure-soe-risk-reserve', context, existingContent: riskReserveNote.value })
      if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
      riskReserveNote.value = text
      handleRiskReserveNoteChange()
      return
    }
    if (section === 'section-soe-distribution') {
      const text = await generateAiText({ section: 'm6-disclosure-soe-distribution', context, existingContent: soeDistributionNote.value })
      if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
      soeDistributionNote.value = text
      handleSoeDistributionNoteChange()
      return
    }
    // 无对应文本区（整体披露/变动表说明）→ 弹窗展示建议
    const text = await generateAiText({ section: `m6-disclosure-soe-${section}`, context, existingContent: '' })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '知道了' }).catch(() => {})
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}

function handleReview() {
  openReviewDialog?.('M6-disclosure-soe', '附注披露（国有企业）')
}

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Restore from saved data ─────────────────────────────────────────────────

function restoreData(): void {
  const responses = formData.allResponses.value
  const editableFields: Array<'priorYearEnd' | 'beginAdj' | 'increase' | 'decrease'> = ['priorYearEnd', 'beginAdj', 'increase', 'decrease']

  for (const row of movementRows.value) {
    if (row.isFormula) continue
    for (const field of editableFields) {
      const resp = responses.get(`M6-disclosure-soe-${row.key}-${field}`)
      if (resp?.remark) row[field] = Number(resp.remark) || 0
    }
  }
  recalcFormulas()

  const riskResp = responses.get('M6-disclosure-soe-risk-reserve')
  if (riskResp?.remark) riskReserveNote.value = riskResp.remark

  const distResp = responses.get('M6-disclosure-soe-distribution')
  if (distResp?.remark) soeDistributionNote.value = distResp.remark
}

// ─── EventBus subscribe: 审定变化刷新 ───────────────────────────────────────

function onAdjudicatedRefresh() {
  formData.loadData().then(() => restoreData())
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})
</script>

<style scoped>
.m6-tab-disclosure-soe {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.section-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}

.methodology-text {
  font-size: var(--wp-font-size, 13px);
  color: #6b5900;
  line-height: 1.6;
}

.disclosure-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.formula-row {
  font-weight: 600;
  color: #303133;
}

.subtotal-row {
  font-weight: 700;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-weight: 500;
  color: #303133;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

.m6-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m6-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.m6-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
