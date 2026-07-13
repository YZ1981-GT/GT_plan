<script setup lang="ts">
/**
 * E1TabAnalysis.vue — E1-14 分析表
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.11
 *
 * - Uses useE1Analysis composable
 * - Fixed rows: 项目 | 期末金额(from E1-1) | 期初金额 | 变动额 | 变动率 | 变动原因(textarea+AI)
 * - Red highlight when |changeRate|>30%
 * - AI button per row (disabled placeholder)
 *
 * Requirements: 9.1-9.3
 */
import { ref, inject, toRef, computed, onMounted, type Ref } from 'vue'
import { useE1Analysis, type AnalysisRow } from '../composables/useE1Analysis'
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

const options: UseE1BaseOptions = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
}

const {
  rows,
  isLoading,
  isRateExceeding,
  updateCell,
} = useE1Analysis(options)

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtRate(rate: number | ''): string {
  if (rate === '' || rate === 0) return '-'
  return (rate * 100).toFixed(2) + '%'
}

function getRowClass({ row }: { row: AnalysisRow }): string {
  if (isRateExceeding(row)) return 'e1-analysis-red-row'
  return ''
}

// ─── 结构比（各项目期末金额 ÷ 货币资金合计，仅展示派生）─────────────────────

const totalEnding = computed(() =>
  rows.value.reduce((sum, r) => sum + (r.endingAmount || 0), 0),
)

/** 期末结构比：库存现金/银行存款/其他货币资金占货币资金合计的比重 */
function structureRatio(row: AnalysisRow): string {
  const total = totalEnding.value
  if (!total) return '-'
  return ((row.endingAmount / total) * 100).toFixed(2) + '%'
}

// ─── 存贷双高预警（展示派生：银行存款占比高即提示核查贷款匹配性）───────────

/** 银行存款期末金额占货币资金合计比重 */
const bankRatio = computed(() => {
  const total = totalEnding.value
  if (!total) return 0
  const bank = rows.value.find(r => r.itemKey === 'bank')
  return bank ? bank.endingAmount / total : 0
})

/** 货币资金合计（期末）是否处于较高水平且以银行存款为主，触发存贷双高关注 */
const showDualHighWarning = computed(
  () => totalEnding.value > 0 && bankRatio.value >= 0.6,
)

// ─── 审计说明 / 审计结论（源模板"审计说明""审计结论"，无AI→纯textarea）──────

const NOTE_KEY = 'E1-analysis-audit-note'
const CONCLUSION_KEY = 'E1-analysis-audit-conclusion'
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
  <div class="e1-tab-analysis">
    <!-- 编制提示（源模板 E1-14 分析程序要点）-->
    <details class="guidance-details">
      <summary>📋 编制提示（分析程序要点）</summary>
      <div class="guidance-content">
        <p>1. <strong>构成结构比及变动分析</strong>：分析货币资金（库存现金/银行存款/其他货币资金）及其他货币资金各明细项目的结构比（各项目÷货币资金合计）及本期、上期变动情况。</p>
        <p>2. <strong>比例分析</strong>：计算并关注①银行存款÷资产总额、②定期存款÷银行存款、③受限货币资金÷货币资金 等比例；若定期存款占比偏高，须了解其商业理由并取得支持文件。</p>
        <p>3. <strong>"存贷双高"异常识别</strong>：计算货币资金÷贷款总额、定期存款÷贷款总额 等比例；当货币资金余额持续较高、同时负债（借款）比例亦偏高（"存贷双高"）时，应向管理层询问商业理由并评估合理性，警惕资金占用、受限未披露及舞弊风险。</p>
        <p>4. <strong>取数与计算</strong>：期末金额取自 E1-1 审定表（跨sheet自动取数）；灰色底纹列（期末金额/结构比/变动额）为自动计算不可手工录入；期初金额可手工录入；变动率 = 变动额 ÷ 期初金额，绝对值超过30%时红色高亮，须在"变动原因"列分析说明。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：通过分析性程序评价货币资金构成、结构比及变动的合理性，计算银行存款/定期存款相关比例，识别'存贷双高'等异常波动，为进一步实质性程序提供方向。"
      class="objective-alert"
    />

    <el-skeleton :loading="isLoading" :rows="6" animated>
      <template #default>
        <!-- 工具栏 -->
        <div class="tab-toolbar">
          <div class="toolbar-left"></div>
          <div class="toolbar-right">
            <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
            <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
          </div>
        </div>

        <el-table
          :data="rows"
          border
          stripe
          size="small"
          :row-class-name="getRowClass"
          style="width: 100%"
        >
          <el-table-column prop="itemName" label="项目" width="150" fixed="left">
            <template #default="{ row }">
              <span class="font-bold">{{ row.itemName }}</span>
            </template>
          </el-table-column>

          <el-table-column label="本期金额" width="140" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="computed-cell">{{ displayPrefs.fmtAmount(row.endingAmount) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="结构比" width="100" align="center" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="computed-cell">{{ structureRatio(row) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="上期金额" width="140" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.openingAmount"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number) => updateCell(row.itemKey, 'openingAmount', val ?? 0)"
              />
            </template>
          </el-table-column>

          <el-table-column label="变动额" width="150" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="computed-cell">{{ displayPrefs.fmtAmount(row.changeAmount) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="变动率" width="100" align="center">
            <template #default="{ row }">
              <span :class="{ 'red-text': isRateExceeding(row) }">
                {{ fmtRate(row.changeRate) }}
              </span>
            </template>
          </el-table-column>

          <el-table-column label="变动原因" min-width="250">
            <template #default="{ row }">
              <div class="note-cell">
                <el-input
                  type="textarea"
                  :model-value="row.varianceNote"
                  :disabled="isReadonly"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  placeholder="填写变动原因分析"
                  @change="(val: string) => updateCell(row.itemKey, 'varianceNote', val)"
                />
                <el-button
                  size="small"
                  type="primary"
                  text
                  disabled
                  class="ai-btn"
                  title="AI生成(待接入)"
                >🤖</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <!-- 存贷双高预警 -->
        <el-alert
          v-if="showDualHighWarning"
          type="warning"
          :closable="false"
          show-icon
          class="dual-high-alert"
          title="存贷双高关注提示"
        >
          <template #default>
            期末银行存款占货币资金合计比重达 {{ (bankRatio * 100).toFixed(2) }}%，货币资金余额较高。请结合借款（短期借款/长期借款）余额核查是否存在"存贷双高"异常：计算货币资金÷贷款总额、定期存款÷贷款总额，若同时存在高额存款与高额借款，须向管理层询问定期存款/大额资金的商业理由，评估其合理性，并关注资金是否受限、是否存在资金占用或舞弊风险。
          </template>
        </el-alert>

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
            placeholder="填写审计说明：说明货币资金构成、结构比及变动分析结果，银行存款/定期存款相关比例，以及'存贷双高'等异常情况的了解与评估..."
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
            placeholder="填写审计结论：分析程序执行结果是否支持货币资金余额及变动的合理性，是否发现需进一步实施实质性程序的异常..."
            @change="(val: string) => saveAuditConclusion(val)"
          />
        </el-card>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-analysis {
  padding: 12px 0;
}
.e1-tab-analysis :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-analysis :deep(.el-table .cell) {
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
.red-text {
  color: #f56c6c;
  font-weight: 600;
}
.font-bold {
  font-weight: 700;
}
.note-cell {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}
.note-cell .el-textarea {
  flex: 1;
}
.ai-btn {
  flex-shrink: 0;
  margin-top: 2px;
}
:deep(.e1-analysis-red-row) {
  background-color: #fef0f0 !important;
}
:deep(.e1-analysis-red-row td) {
  color: #f56c6c;
}
.dual-high-alert {
  margin-top: 16px;
  line-height: 1.6;
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
