<script setup lang="ts">
/**
 * E1TabInterestAnalysis.vue — E1-15 利息分析
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.12
 *
 * - Uses useE1InterestCalc with variant='monthly'
 * - 12 rows (months): 月份 | 月均余额 | 月利率 | 测算利息(readonly)
 * - Summary: 测算合计 | 账面利息(editable) | 差异(readonly, orange if material)
 *
 * Requirements: 9.4-9.6
 */
import { ref, inject, toRef, onMounted, type Ref } from 'vue'
import {
  useE1InterestCalc,
  type MonthlyInterestRow,
} from '../composables/useE1InterestCalc'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

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

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions & { variant: 'monthly' } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  variant: 'monthly',
}

const {
  rows,
  monthlySummary,
  totalCalculated,
  isLoading,
  updateCell,
  updateSummary,
} = useE1InterestCalc(options)

// ─── Helpers ─────────────────────────────────────────────────────────────────

function asMonthly(row: any): MonthlyInterestRow { return row }

function isMaterial(): boolean {
  return Math.abs(monthlySummary.value.diff) > 0.005
}

// ─── 审计说明 / 审计结论 ─────────────────────────────────────────────────────

const NOTE_KEY = 'E1-interest-audit-note'
const CONCLUSION_KEY = 'E1-interest-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

onMounted(() => {
  const noteResp = props.allResponses.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  const concResp = props.allResponses.get(CONCLUSION_KEY)
  if (concResp?.remark) auditConclusion.value = concResp.remark
})

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY, item)
  void props.saveImmediate([item])
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  void props.saveImmediate([item])
}
</script>

<template>
  <div class="e1-tab-interest-analysis">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表按月测算存款利息，验证账面利息收入的合理性：测算利息 = 月均余额 × 月利率。</p>
        <p>2. 灰色底纹列（测算利息）为自动计算，不可手工录入；月均余额与月利率可手工录入。</p>
        <p>3. 测算合计与账面利息的差异橙色高亮时，须核对利率与计息基础，查明差异原因。</p>
        <p>4. 关注利息收入与银行存款规模、协定存款利率是否匹配，识别账外资金或体外循环迹象。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：通过利息测算复核存款利息收入的完整与准确，评价利率合理性，识别未入账利息及资金异常占用。"
      class="objective-alert"
    />

    <el-skeleton :loading="isLoading" :rows="14" animated>
      <template #default>
        <!-- 工具栏 -->
        <div class="tab-toolbar">
          <div class="toolbar-left"></div>
          <div class="toolbar-right">
            <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
            <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
          </div>
        </div>

        <el-table :data="rows" border stripe size="small" style="width: 100%">
          <el-table-column label="月份" width="80" align="center">
            <template #default="{ row }">
              {{ asMonthly(row).month }}月
            </template>
          </el-table-column>

          <el-table-column label="月均余额" width="180" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="asMonthly(row).monthlyAvgBalance"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number) => updateCell(row.id, 'monthlyAvgBalance', val ?? 0)"
              />
            </template>
          </el-table-column>

          <el-table-column label="月利率" width="140" align="center">
            <template #default="{ row }">
              <el-input-number
                :model-value="asMonthly(row).monthlyRate"
                :disabled="isReadonly"
                :controls="false"
                :precision="6"
                size="small"
                @change="(val: number) => updateCell(row.id, 'monthlyRate', val ?? 0)"
              />
            </template>
          </el-table-column>

          <el-table-column label="测算利息" width="180" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="computed-cell">{{ displayPrefs.fmtAmount(asMonthly(row).calculatedInterest) }}</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- Summary Card -->
        <el-card class="summary-card" shadow="never">
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="测算合计">
              <span class="computed-cell">{{ displayPrefs.fmtAmount(totalCalculated) }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="账面利息">
              <el-input-number
                :model-value="monthlySummary.bookInterest"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number) => updateSummary('bookInterest', val ?? 0)"
              />
            </el-descriptions-item>
            <el-descriptions-item label="差异">
              <span :class="['computed-cell', { 'orange-text': isMaterial() }]">
                {{ displayPrefs.fmtAmount(monthlySummary.diff) }}
              </span>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

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
            placeholder="填写审计说明：可概述（1）利息收入月度测算的方法与利率来源；（2）测算合计与账面利息收入的差异及成因分析；（3）利息收入与存款规模的匹配性；（4）是否存在高息资金拆借、体外资金循环等异常迹象。"
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
            placeholder="填写审计结论：A、利息收入测算数与账面记录基本相符，未见异常。B、除上述差异事项外，利息收入合理、完整。C、由于存在以下重大未解释差异（或资料受限无法测算），需进一步核查。"
            @change="(val: string) => saveAuditConclusion(val)"
          />
        </el-card>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-interest-analysis {
  padding: 12px 0;
}
.e1-tab-interest-analysis :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-interest-analysis :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
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
.computed-cell {
  color: #606266;
  font-style: italic;
}
.orange-text {
  color: #e6a23c;
  font-weight: 600;
}
.summary-card {
  margin-top: 16px;
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
