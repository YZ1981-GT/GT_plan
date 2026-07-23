<template>
  <div class="k9-tab-substantive-analysis">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性与准确性：</b>通过与上期/预算/收入的比率分析，评价管理费用整体合理性，识别异常波动；</li>
        <li><b>发生：</b>对超阈值波动查明原因，验证费用真实发生、无异常虚增。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <span class="section-title">K9-4 实质性分析程序</span>
      <div class="section-actions">
        <el-button size="small" type="primary" text :loading="aiLoading" @click="handleAiAssist"><el-icon><MagicStick /></el-icon> 生成波动分析</el-button>
        <el-button size="small" text @click="openReviewDialog?.('K9-4-substantive-analysis')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>对管理费用各明细项目执行实质性分析程序。<strong>同比变动率=(本期-上期)/|上期|</strong>，<strong>占营业收入比=费用/营业收入</strong>。当|同比变动率|>波动阈值时标记为异常（红色），异常项<strong>必须填写原因分析</strong>。默认阈值30%，可逐行调整。</p>
    </div>

    <!-- ═══ 数据来源 + 占收入比分母 ═══ -->
    <div class="analysis-toolbar">
      <el-button size="small" type="warning" plain :disabled="isReadonly" @click="pullFromDetail">从 K9-2 带入明细</el-button>
      <div class="rev-input">
        <span class="rev-label">营业收入</span>
        <el-input-number v-model="revenue" :controls="false" :precision="2" :disabled="isReadonly" size="small" style="width:170px" @change="saveRevenue" />
        <span class="rev-hint">用于计算「占营业收入比」（可从 D4 营业收入审定数录入）</span>
      </div>
    </div>

    <!-- ═══ 异常项汇总摘要 ═══ -->
    <el-alert v-if="summary.abnormalCount > 0" type="error" :closable="false" show-icon style="margin-bottom:10px">
      <template #title>⚠️ 发现 {{ summary.abnormalCount }} 项异常波动</template>
      <template #default>
        <span v-for="(name, idx) in summary.abnormalProjects" :key="idx" class="abnormal-tag">{{ name }}{{ idx < summary.abnormalProjects.length - 1 ? '、' : '' }}</span>
      </template>
    </el-alert>

    <!-- ═══ 统计卡片 ═══ -->
    <div class="stats-card">
      <div class="stat-item"><span class="stat-label">分析项目数</span><span class="stat-value">{{ summary.totalItems }}</span></div>
      <div class="stat-item"><span class="stat-label">异常项</span><span class="stat-value stat-danger">{{ summary.abnormalCount }}</span></div>
      <div class="stat-item"><span class="stat-label">正常项</span><span class="stat-value stat-success">{{ summary.normalCount }}</span></div>
      <div class="stat-item"><span class="stat-label">本期合计</span><span class="stat-value">{{ fmtAmt(summary.totalAmount) }}</span></div>
    </div>

    <!-- ═══ 实质性分析表格（48行虚拟滚动） ═══ -->
    <el-table
      :data="rows"
      border
      size="small"
      class="analysis-table"
      max-height="520"
      :row-class-name="rowClassName"
    >
      <el-table-column type="index" label="#" width="42" fixed align="center" />
      <el-table-column prop="projectName" label="费用项目" min-width="120" fixed>
        <template #default="{ row }">
          <span class="project-name">{{ row.projectName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="currentAmount" label="本期" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.currentAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowKey, 'currentAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.currentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="priorAmount" label="上期" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.priorAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowKey, 'priorAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="同比变动额" width="110" align="right">
        <template #default="{ row }">
          <span class="formula-cell" :title="`变动额 = 本期 - 上期 = ${row.currentAmount} - ${row.priorAmount}`">{{ fmtAmt(row.changeAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="同比变动率" width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" :class="{ 'abnormal-rate': row.isAbnormal }" :title="`变动率 = (本期-上期)/|上期| = ${fmtRate(row.changeRate)}`">{{ fmtRate(row.changeRate) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="占营业收入比" width="105" align="right">
        <template #default="{ row }">
          <span class="formula-cell" :title="`占收入比 = 本期/营业收入`">{{ fmtRate(row.ratioToRevenue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期占比" width="90" align="right">
        <template #default="{ row }">
          <span class="formula-cell">{{ fmtRate(row.priorRatioToRevenue) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="threshold" label="波动阈值" width="90" align="center">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.threshold * 100" size="small" :controls="false" :precision="0" :min="1" :max="100" style="width:60px" @change="(v: number | undefined) => updateCell(row.rowKey, 'threshold', (v ?? 30) / 100)">
            <template #suffix>%</template>
          </el-input-number>
          <span v-else>{{ (row.threshold * 100).toFixed(0) }}%</span>
        </template>
      </el-table-column>
      <el-table-column label="是否异常" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.isAbnormal ? 'danger' : 'success'" size="small">{{ row.isAbnormal ? '异常' : '正常' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="reasonAnalysis" label="原因分析" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reasonAnalysis"
            size="small"
            :placeholder="row.isAbnormal ? '异常项必填原因分析' : ''"
            :class="{ 'required-field': row.isAbnormal && !row.reasonAnalysis }"
            @change="(v: string) => updateCell(row.rowKey, 'reasonAnalysis', v)"
          />
          <span v-else :class="{ 'missing-reason': row.isAbnormal && !row.reasonAnalysis }">{{ row.reasonAnalysis || (row.isAbnormal ? '⚠️ 未填写' : '-') }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 总体结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-head">
          <span>实质性分析结论</span>
          <el-button size="small" type="primary" text :loading="aiLoading" @click="handleAiConclusion"><el-icon><MagicStick /></el-icon> AI生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="overallConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="请填写实质性分析总体结论..."
        @blur="(e: FocusEvent) => saveOverallConclusion((e.target as HTMLTextAreaElement)?.value ?? '')"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>同比变动率=(本期-上期)/|上期|，上期为0时显示"—"</li>
        <li>占营业收入比=本期费用/营业收入，收入为0时显示"—"</li>
        <li>异常判断：|同比变动率|>波动阈值（默认30%）</li>
        <li>异常项红色背景标记，必须填写原因分析</li>
        <li>48行虚拟滚动优化大数据量展示</li>
        <li>点「从 K9-2 带入明细」按项目导入审定数/上期数；录入「营业收入」后自动算占收入比</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K9TabSubstantiveAnalysis.vue — K9-4 实质性分析程序（16公式，48行）
 *
 * Spec: .kiro/specs/k9-admin-expenses/ | Task: 4.4
 * Requirements: 4.1-4.6
 *
 * 功能：
 * - 16公式列自动计算（同比/环比/占比/异常判断）
 * - 异常项红色背景标记，要求填写原因分析
 * - 48行虚拟滚动
 * - AI辅助生成波动分析
 * - 统计卡片（总项目/异常/正常/本期合计）
 */
import { toRef, inject, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK9Analysis } from '@/components/workpaper/composables/useK9Analysis'
import { generateK9AiText } from '@/components/workpaper/composables/useK9AiText'
import type { Ref } from 'vue'
import type { K9AnalysisRow } from '@/components/workpaper/composables/useK9Analysis'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ (e: 'save', itemId: string, value: any): void }>()
const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

// 营业收入（占收入比分母），手工录入并持久化 → 传入 composable 使占收入比可计算
const revenue = ref(0)

// ═══ Composable ═══
const {
  rows,
  summary,
  overallConclusion,
  updateCell,
  saveOverallConclusion,
  populateFromDetail,
} = useK9Analysis({
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  projectId: toRef(props, 'projectId'),
  wpId: toRef(props, 'wpId'),
  revenue,
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, typeof value === 'string' ? { remark: value } : { remark: JSON.stringify(value) }),
})

// ═══ 营业收入持久化（占收入比分母） ═══
function loadRevenue(): void {
  const item = props.allResponses.get('K9-4-revenue')
  const v = Number(item?.remark ?? item?.conclusion ?? 0)
  if (v > 0) revenue.value = v
}
function saveRevenue(): void {
  emit('save', 'K9-4-revenue', { remark: String(revenue.value ?? 0) })
}
onMounted(loadRevenue)

// ═══ 从 K9-2 明细表带入分析行（原「数据来源」仅文字提示，实际靠手填） ═══
function pullFromDetail(): void {
  if (props.isReadonly) return
  const item = props.allResponses.get('K9-2-detail-rows')
  const raw = item?.remark ?? item?.conclusion
  if (!raw) { ElMessage.warning('未找到 K9-2 明细数据，请先在 K9-2 登记明细'); return }
  let detail: any[]
  try { detail = typeof raw === 'string' ? JSON.parse(raw) : raw } catch { ElMessage.warning('K9-2 明细数据解析失败'); return }
  if (!Array.isArray(detail) || detail.length === 0) { ElMessage.warning('K9-2 明细为空'); return }
  const mapped = detail
    .filter((d: any) => String(d.accountName ?? '').trim())
    .map((d: any) => ({
      projectName: String(d.accountName).trim(),
      audited: Number(d.audited) || 0,
      priorAmount: Number(d.priorAmount) || 0,
    }))
  populateFromDetail(mapped)
  ElMessage.success(`已从 K9-2 带入 ${mapped.length} 项明细`)
}

// ═══ UI Helpers ═══
function rowClassName({ row }: { row: K9AnalysisRow }): string {
  return row.isAbnormal ? 'abnormal-row' : ''
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(v: number | null | undefined): string {
  if (v == null) return '—'
  return (v * 100).toFixed(1) + '%'
}

const aiLoading = ref(false)

function _analysisContext(): Record<string, unknown> {
  const abnormal = rows.value.filter(r => r.isAbnormal)
    .map(r => `${r.projectName}同比${r.changeRate != null ? (r.changeRate * 100).toFixed(0) + '%' : '—'}`)
  return {
    科目: '6602 管理费用（损益类，取发生额）',
    分析项目数: summary.value.totalItems,
    异常项数: summary.value.abnormalCount,
    本期合计: summary.value.totalAmount,
    异常波动项: abnormal.join('；') || '无超阈值波动',
  }
}

async function handleAiAssist(): Promise<void> {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    const content = await generateK9AiText(props.wpId, {
      prompt: '请根据下列管理费用实质性分析结果，生成异常波动的原因分析建议（逐项说明可能成因及需追加的审计程序）。',
      section: 'K9-4-fluctuation-analysis',
      context: _analysisContext(),
      existingContent: overallConclusion.value || '',
    })
    if (content) {
      saveOverallConclusion(overallConclusion.value ? `${overallConclusion.value}\n\n${content}` : content)
    }
  } finally {
    aiLoading.value = false
  }
}

async function handleAiConclusion(): Promise<void> {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    const content = await generateK9AiText(props.wpId, {
      prompt: '请根据管理费用实质性分析程序结果，生成实质性分析总体结论（概述比率分析结论、异常项处理及整体合理性判断）。',
      section: 'K9-4-overall-conclusion',
      context: _analysisContext(),
      existingContent: overallConclusion.value || '',
    })
    if (content) {
      saveOverallConclusion(overallConclusion.value ? `${overallConclusion.value}\n\n${content}` : content)
    }
  } finally {
    aiLoading.value = false
  }
}
</script>

<style scoped>
.k9-tab-substantive-analysis { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.analysis-toolbar { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 14px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.rev-input { display: flex; align-items: center; gap: 8px; }
.rev-label { font-size: 12px; color: var(--el-text-color-secondary); }
.rev-hint { font-size: 12px; color: var(--el-text-color-placeholder); }
.stats-card { display: flex; gap: 24px; padding: 12px 16px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 14px; }
.stat-item { display: flex; flex-direction: column; align-items: center; }
.stat-label { font-size: 12px; color: #6b7280; }
.stat-value { font-size: 18px; font-weight: 700; color: #1f2937; }
.stat-danger { color: #dc2626; }
.stat-success { color: #16a34a; }
.abnormal-tag { font-size: 12px; color: #dc2626; }
.project-name { font-weight: 500; color: #303133; }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; border-bottom: 1px dashed #909399; cursor: help; }
.abnormal-rate { color: #f56c6c !important; font-weight: 600; }
.required-field :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
.missing-reason { color: #f56c6c; font-weight: 500; }
.analysis-table { font-size: var(--wp-font-size, 13px); }
.conclusion-card { margin-top: 16px; }
.card-head { display: flex; align-items: center; justify-content: space-between; }
:deep(.abnormal-row) { background-color: #fef2f2 !important; }
:deep(.abnormal-row:hover > td) { background-color: #fee2e2 !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; }
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
