<template>
  <div class="h4-tab-impairment">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H4-7减值测算：对存在减值迹象的工程物资，比较账面价值与可收回金额（资产组法/预计未来现金流量现值），确认减值损失。31行31列15公式，复杂矩阵计算以OnlyOffice渲染为主。</p>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：评估工程物资是否存在减值迹象，比较账面价值与可收回金额，核实减值损失计提的充分与恰当（CAS8 资产减值）。" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H4-7" :context-project-id="props.projectId" /></span>
    </div>

    <!-- Section Title -->
    <div class="section-header">
      <span>减值测算表 H4-7</span>
      <div class="section-header-actions">
        <el-segmented v-model="dualMode.currentMode.value" :options="dualMode.modeOptions"
          size="small" @change="dualMode.onModeChange" />
        <el-button size="small" circle @click="openReview('H4-7-impairment')">💬</el-button>
      </div>
    </div>

    <!-- OnlyOffice 模式 -->
    <GtOnlyOfficeSheet
      v-if="dualMode.currentMode.value === 'onlyoffice'"
      :wp-id="props.wpId"
      :sheet-name="props.sheetName"
      :project-id="props.projectId"
      class="impairment-oo"
    />

    <!-- HTML 简化摘要视图 -->
    <div v-else class="impairment-summary">
      <el-card shadow="never">
        <template #header>
          <span style="font-weight: 600">减值测算关键数据摘要</span>
        </template>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="工程物资账面价值">
            <span class="amt-cell">{{ fmtAmt(summaryData.bookValue) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="可收回金额">
            <span class="amt-cell">{{ fmtAmt(summaryData.recoverableAmount) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="减值损失">
            <span class="amt-cell" :class="{ 'diff-warn': summaryData.impairmentLoss > 0 }">
              {{ fmtAmt(summaryData.impairmentLoss) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="减值准备余额">
            <span class="amt-cell">{{ fmtAmt(summaryData.provisionBalance) }}</span>
          </el-descriptions-item>
        </el-descriptions>
        <div class="summary-note">
          <el-alert v-if="summaryData.impairmentLoss > 0" type="warning" :closable="false" show-icon>
            存在减值迹象，减值损失 {{ fmtAmt(summaryData.impairmentLoss) }} 元，请切换到在线编辑查看完整计算过程。
          </el-alert>
          <el-alert v-else type="success" :closable="false" show-icon>
            未发现需计提减值的工程物资。
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
        placeholder="请填写减值测算的审计说明..." :disabled="props.isReadonly"
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
        <li>减值测算使用资产组法或单项法，比较账面价值与可收回金额</li>
        <li>可收回金额=max(公允价值-处置费用, 预计未来现金流量现值)</li>
        <li>本表31行31列15公式，建议使用在线编辑模式进行详细计算</li>
        <li>减值损失一经确认不得转回（CAS8规定）</li>
        <li>如需详细查看DCF折现计算过程，请使用H4-8可收回金额测试表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabImpairment.vue — H4-7 减值测算表（OnlyOffice为主 + HTML摘要视图）
 *
 * 31行31列15公式，复杂矩阵计算保留OnlyOffice为主渲染。
 * HTML模式显示简化摘要卡片（关键数据：账面/可收回/减值损失/准备余额）。
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
  const bookValue = getNum('H4-7-book-value')
  const recoverableAmount = getNum('H4-7-recoverable-amount')
  const impairmentLoss = getNum('H4-7-impairment-loss')
  const provisionBalance = getNum('H4-7-provision-balance')
  return { bookValue, recoverableAmount, impairmentLoss, provisionBalance }
})

// ─── 审计说明 / 审计结论（inject saveResponse 落库 + onMounted 恢复） ──────────
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', () => {})
const auditNote = ref('')
const auditConclusion = ref('')
function saveAuditNote() {
  props.allResponses.set('H4-7-note', { item_id: 'H4-7-note', remark: auditNote.value, conclusion: null })
  saveResponse('H4-7-note', auditNote.value)
}
function saveAuditConclusion() {
  props.allResponses.set('H4-7-conclusion', { item_id: 'H4-7-conclusion', remark: auditConclusion.value, conclusion: null })
  saveResponse('H4-7-conclusion', auditConclusion.value)
}
onMounted(() => {
  const n = props.allResponses.get('H4-7-note'); if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get('H4-7-conclusion'); if (c?.remark) auditConclusion.value = c.remark
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
.h4-tab-impairment { padding: 16px; font-size: var(--wp-font-size, 13px); }

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

.impairment-oo { min-height: 500px; margin-bottom: 12px; }

.impairment-summary { margin-bottom: 12px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.summary-note { margin-top: 12px; }

.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
