<template>
  <div class="h4-tab-recoverable">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H4-8可收回金额测试：通过DCF折现现金流法测试工程物资资产组的可收回金额。预计未来5年现金流+永续期价值，按加权平均资本成本（WACC）折现。58行28列12公式，复杂DCF计算以OnlyOffice渲染为主。</p>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：通过 DCF 折现现金流法测试工程物资资产组的可收回金额，验证关键假设（折现率/预测期/永续增长率）的合理性，为减值计提提供依据。" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H4-8" :context-project-id="props.projectId" /></span>
    </div>

    <!-- Section Title -->
    <div class="section-header">
      <span>可收回金额测试表 H4-8</span>
      <div class="section-header-actions">
        <el-segmented v-model="dualMode.currentMode.value" :options="dualMode.modeOptions"
          size="small" @change="dualMode.onModeChange" />
        <el-button size="small" circle @click="openReview('H4-8-recoverable')">💬</el-button>
      </div>
    </div>

    <!-- OnlyOffice 模式 -->
    <GtOnlyOfficeSheet
      v-if="dualMode.currentMode.value === 'onlyoffice'"
      :wp-id="props.wpId"
      :sheet-name="props.sheetName"
      :project-id="props.projectId"
      class="recoverable-oo"
    />

    <!-- HTML 简化摘要视图 -->
    <div v-else class="recoverable-summary">
      <el-card shadow="never">
        <template #header>
          <span style="font-weight: 600">可收回金额测试关键参数摘要</span>
        </template>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="折现率(WACC)">
            <span class="param-val">{{ summaryData.discountRate ? summaryData.discountRate + '%' : '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="预测期(年)">
            <span class="param-val">{{ summaryData.forecastYears || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="预计现金流现值">
            <span class="amt-cell">{{ fmtAmt(summaryData.dcfValue) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="永续价值现值">
            <span class="amt-cell">{{ fmtAmt(summaryData.terminalValue) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="可收回金额合计">
            <span class="amt-cell highlight">{{ fmtAmt(summaryData.totalRecoverable) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="账面价值">
            <span class="amt-cell">{{ fmtAmt(summaryData.bookValue) }}</span>
          </el-descriptions-item>
        </el-descriptions>
        <div class="summary-note">
          <el-alert v-if="summaryData.totalRecoverable > 0 && summaryData.bookValue > summaryData.totalRecoverable"
            type="warning" :closable="false" show-icon>
            可收回金额（{{ fmtAmt(summaryData.totalRecoverable) }}）低于账面价值（{{ fmtAmt(summaryData.bookValue) }}），应计提减值。
          </el-alert>
          <el-alert v-else-if="summaryData.totalRecoverable > 0" type="success" :closable="false" show-icon>
            可收回金额高于账面价值，无需计提减值。
          </el-alert>
          <el-alert v-else type="info" :closable="false" show-icon>
            请切换到在线编辑模式完成DCF计算。
          </el-alert>
        </div>
      </el-card>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0"><span>审计说明</span></div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }"
        placeholder="请填写可收回金额测试的审计说明..." :disabled="props.isReadonly"
        @blur="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0"><span>审计结论</span></div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写审计结论..." :disabled="props.isReadonly"
        @blur="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>折现率通常使用WACC（加权平均资本成本）</li>
        <li>预测期通常5年，永续期假设稳定增长率（不超过GDP增速）</li>
        <li>现金流预测应基于管理层批准的最近财务预算/预测</li>
        <li>关键假设（增长率/折现率/永续增长率）需做敏感性分析</li>
        <li>本表58行28列12公式，建议使用在线编辑模式进行详细计算</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabRecoverable.vue — H4-8 可收回金额测试表（OnlyOffice为主 + HTML摘要视图）
 *
 * 58行28列12公式，DCF资产组测试。复杂矩阵计算保留OnlyOffice为主渲染。
 * HTML模式显示关键参数摘要卡片（折现率/预测期/DCF现值/永续价值/可收回合计）。
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 4.8
 * Requirements: 7.4-7.6
 */
import { ref, computed, defineAsyncComponent, inject, toRef, onMounted } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH4DualMode } from '../../composables/useH4DualMode'
import GtIndexChip from '../../GtIndexChip.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('../../GtOnlyOfficeSheet.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  sheetName: string
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Dual Mode ───────────────────────────────────────────────────────────────
const dualMode = useH4DualMode({
  wpId: toRef(props, 'wpId'),
  sheetName: toRef(props, 'sheetName'),
})

// ─── Summary Data (from allResponses) ────────────────────────────────────────
const summaryData = computed(() => {
  const map = props.allResponses
  const getNum = (key: string) => {
    const resp = map.get(key)
    const n = Number(resp?.remark)
    return Number.isFinite(n) ? n : 0
  }
  return {
    discountRate: getNum('H4-8-discount-rate'),
    forecastYears: getNum('H4-8-forecast-years'),
    dcfValue: getNum('H4-8-dcf-value'),
    terminalValue: getNum('H4-8-terminal-value'),
    totalRecoverable: getNum('H4-8-total-recoverable'),
    bookValue: getNum('H4-8-book-value'),
  }
})

// ─── 审计说明 / 审计结论（inject saveResponse 落库 + onMounted 恢复） ──────────
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', () => {})
const auditNote = ref('')
const auditConclusion = ref('')
function saveAuditNote() {
  props.allResponses.set('H4-8-note', { item_id: 'H4-8-note', remark: auditNote.value, conclusion: null })
  saveResponse('H4-8-note', auditNote.value)
}
function saveAuditConclusion() {
  props.allResponses.set('H4-8-conclusion', { item_id: 'H4-8-conclusion', remark: auditConclusion.value, conclusion: null })
  saveResponse('H4-8-conclusion', auditConclusion.value)
}
onMounted(() => {
  const n = props.allResponses.get('H4-8-note'); if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get('H4-8-conclusion'); if (c?.remark) auditConclusion.value = c.remark
})

// ─── Actions ─────────────────────────────────────────────────────────────────

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────
function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h4-tab-recoverable { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 12px; }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.6;
}

.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600; margin-bottom: 12px;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.recoverable-oo { min-height: 500px; margin-bottom: 12px; }

.recoverable-summary { margin-bottom: 12px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.param-val { font-weight: 500; color: var(--el-text-color-primary); }
.highlight { color: #409eff; font-weight: 600; }
.summary-note { margin-top: 12px; }

.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
