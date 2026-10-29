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
import { computed, inject, onBeforeUnmount, onMounted, onUnmounted, ref } from 'vue'
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
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── 同步链路 ───────────────────────────────────────────────────────────────

import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import {
  createM6SoeRows,
  m6NoteText,
  m6WireRows,
  recalcM6SoeRows,
  restoreM6SoeRows,
  type M6SoeRow,
} from '../../composables/m6DisclosureForm'
import { buildM6SyncPayload } from '../../composables/m6NoteSectionMap'
import http from '@/utils/http'

async function syncToDisclosureNotes(): Promise<void> {
  const payload = buildM6SyncPayload(
    props.wpId,
    'soe',
    m6WireRows('soe', movementRows.value),
    m6NoteText(formData.allResponses.value, 'soe'),
  )
  if (!payload || props.isReadonly) return
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
  } catch { /* fail-open */ }
}

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useM6FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Movement Table Rows (国企格式) ──────────────────────────────────────────

const movementRows = ref<M6SoeRow[]>(createM6SoeRows())

// ─── Text Notes ──────────────────────────────────────────────────────────────

const riskReserveNote = ref('')
const soeDistributionNote = ref('')

// ─── Formula Calculations ────────────────────────────────────────────────────

function recalcFormulas() {
  movementRows.value = recalcM6SoeRows(movementRows.value)
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateRow(index: number, field: 'priorYearEnd' | 'beginAdj' | 'increase' | 'decrease', val: number) {
  if (index >= 0 && index < movementRows.value.length) {
    movementRows.value[index][field] = val
    recalcFormulas()
    formData.debouncedSave(`M6-disclosure-soe-${movementRows.value[index].key}-${field}`, { remark: String(val) })
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  }
}

function handleRiskReserveNoteChange() {
  formData.debouncedSave('M6-disclosure-soe-risk-reserve', { remark: riskReserveNote.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleSoeDistributionNoteChange() {
  formData.debouncedSave('M6-disclosure-soe-distribution', { remark: soeDistributionNote.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
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
  movementRows.value = restoreM6SoeRows(responses)
  riskReserveNote.value = responses.get('M6-disclosure-soe-risk-reserve')?.remark || ''
  soeDistributionNote.value = responses.get('M6-disclosure-soe-distribution')?.remark || ''
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

onBeforeUnmount(() => autoSync.cancelPending())
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
