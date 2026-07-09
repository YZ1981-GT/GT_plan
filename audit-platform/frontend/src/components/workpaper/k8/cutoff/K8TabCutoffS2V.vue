<template>
  <div class="k8-cutoff-s2v">
    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <span class="section-title">K8-7 截止性测试（原始凭证→记账凭证）</span>
      <div class="section-actions">
        <el-button size="small" type="primary" text @click="handleAiAssist"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        <el-button size="small" text @click="openReviewDialog?.('K8-7-cutoff-s2v')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>反向截止测试：从<strong>原始凭证</strong>出发，核对是否及时完整入账。验证已发生的销售费用是否在正确期间及时入账（完整性认定）。<br/>跨期判定标准：原始凭证日期与记账日期分属不同会计期间，表明费用未及时入账。跨期行红色高亮。</p>
    </div>

    <!-- ═══ 统计卡片 ═══ -->
    <div class="stats-card">
      <div class="stat-item"><span class="stat-label">总样本数</span><span class="stat-value">{{ summary.totalSamples }}</span></div>
      <div class="stat-item"><span class="stat-label">跨期笔数</span><span class="stat-value stat-danger">{{ summary.crossPeriodCount }}</span></div>
      <div class="stat-item"><span class="stat-label">正常笔数</span><span class="stat-value stat-success">{{ summary.normalCount }}</span></div>
    </div>

    <!-- ═══ 截止样本表格（44行） ═══ -->
    <el-table
      :data="samples"
      border
      size="small"
      class="cutoff-table"
      max-height="480"
      :row-class-name="rowClassName"
    >
      <el-table-column type="index" label="#" width="42" fixed align="center" />
      <el-table-column prop="voucherNo" label="原始凭证号" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => updateCell(row.rowKey, 'voucherNo', v)" />
          <span v-else>{{ row.voucherNo || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="sourceDate" label="原始凭证日期" min-width="130">
        <template #default="{ row }">
          <el-date-picker v-if="!isReadonly" :model-value="row.sourceDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="(v: string) => updateCell(row.rowKey, 'sourceDate', v)" />
          <span v-else>{{ row.sourceDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="summary" label="摘要" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small" @change="(v: string) => updateCell(row.rowKey, 'summary', v)" />
          <span v-else>{{ row.summary || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="amount" label="金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.amount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowKey, 'amount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="bookDate" label="记账日期" min-width="130">
        <template #default="{ row }">
          <el-date-picker v-if="!isReadonly" :model-value="row.bookDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="(v: string) => updateCell(row.rowKey, 'bookDate', v)" />
          <span v-else>{{ row.bookDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="是否及时入账" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.isTimely ? 'success' : 'danger'" size="small">{{ row.isTimely ? '及时' : '滞后' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="是否跨期" width="85" align="center">
        <template #default="{ row }">
          <el-tag :type="row.isCross ? 'danger' : 'success'" size="small">{{ row.isCross ? '跨期' : '正常' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="conclusion" label="结论" min-width="90">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.conclusion" size="small" @change="(v: string) => updateCell(row.rowKey, 'conclusion', v)">
            <el-option value="正常" label="正常" />
            <el-option value="跨期" label="跨期" />
            <el-option value="需调整" label="需调整" />
          </el-select>
          <span v-else>{{ row.conclusion || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateCell(row.rowKey, 'remark', v)" />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="55" fixed="right" align="center">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="removeSample(row.rowKey)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 操作栏 ═══ -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addSample()">+ 新增</el-button>
      <el-button size="small" type="warning" plain :loading="isLoading" :disabled="isReadonly" @click="autoSample">自动抽样</el-button>
      <el-button size="small" type="success" plain :disabled="isReadonly" @click="showCutoffPanel = true">📥 截止自动提取</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="showSamplingDialog = true">🎲 抽凭</el-button>
    </div>

    <!-- ═══ useCutoffAutoSampling 面板 ═══ -->
    <GtCutoffAutoSampling
      v-if="showCutoffPanel"
      account-code="6601"
      cutoff-direction="pre_cutoff"
      :default-conditions="{ daysBefore: 5, daysAfter: 5 }"
      :workpaper-id="props.wpId"
      :project-id="props.projectId"
      :year="currentYear"
      @filled="handleCutoffFilled"
    />

    <!-- ═══ 抽凭引擎 Dialog ═══ -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 6601 销售费用-截止S2V）" width="720px" :close-on-click-modal="false" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :workpaper-id="props.wpId"
        account-code="6601"
        phase="substantive"
        :year="currentYear"
        @filled="handleVoucherFilled"
      />
    </el-dialog>

    <!-- ═══ 汇总结论 ═══ -->
    <el-card shadow="never" class="summary-card">
      <template #header><span>截止测试结论</span></template>
      <el-input
        :model-value="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="请填写反向截止测试（原始→记账）结论..."
        @blur="(e: FocusEvent) => saveConclusion((e.target as HTMLTextAreaElement)?.value ?? '')"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>反向截止：从原始凭证出发，核对是否已及时完整入账</li>
        <li>验证完整性认定：已发生费用是否在正确期间入账</li>
        <li>"自动抽样"从序时账期末±5天采样（6601销售费用）</li>
        <li>跨期行红色高亮，需关注费用遗漏入账的风险</li>
        <li>样本量一般为44行（可增减）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K8TabCutoffS2V.vue — K8-7 截止性测试(原始凭证至记账凭证)，44行
 *
 * Spec: .kiro/specs/k8-selling-expenses/ | Task: 4.5
 * Requirements: 5.1-5.6
 *
 * 功能：
 * - 从原始凭证到记账凭证方向验证完整性
 * - 自动从序时账±5天抽样（useCutoffAutoSampling）
 * - 跨期判断自动计算 + 红色高亮
 * - 行级抽凭 + 手动新增行
 * - 汇总统计（总样本/跨期/正常）
 */
import { ref, toRef, inject, computed, defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useK8Cutoff } from '@/components/workpaper/composables/useK8Cutoff'
import type { Ref } from 'vue'
import type { K8CutoffRow } from '@/components/workpaper/composables/useK8Cutoff'
import type { ExtractedVoucher, FillMode } from '@/components/workpaper/composables/useCutoffAutoSampling'

const GtCutoffAutoSampling = defineAsyncComponent(() => import('../../cutoff/GtCutoffAutoSampling.vue'))
const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ (e: 'save', itemId: string, value: any): void }>()
const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

// ═══ Composable ═══
const {
  samples,
  summary,
  conclusion,
  isLoading,
  autoSample,
  addSample,
  removeSample,
  updateCell,
  saveConclusion,
} = useK8Cutoff({
  direction: 'S2V',
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  projectId: toRef(props, 'projectId'),
  wpId: toRef(props, 'wpId'),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, typeof value === 'string' ? { remark: value } : { remark: JSON.stringify(value) }),
})

// ═══ UI Helpers ═══
function rowClassName({ row }: { row: K8CutoffRow }): string {
  return row.isCross ? 'cross-period-row' : ''
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleAiAssist(): void {
  ElMessage.info('AI辅助分析截止测试结论...')
}

// ═══ useCutoffAutoSampling 集成（序时账±5天） ═══
const showCutoffPanel = ref(false)
const currentYear = computed(() => new Date().getFullYear())

function handleCutoffFilled(payload: { samples: ExtractedVoucher[]; fillMode: FillMode }): void {
  for (const v of payload.samples) {
    addSample()
    const lastRow = samples.value[samples.value.length - 1]
    if (lastRow) {
      updateCell(lastRow.rowKey, 'voucherNo', v.voucherNo)
      updateCell(lastRow.rowKey, 'sourceDate', v.voucherDate)
      updateCell(lastRow.rowKey, 'summary', v.summary || '')
      const amt = v.debitAmount ? parseFloat(v.debitAmount) : (v.creditAmount ? parseFloat(v.creditAmount) : 0)
      updateCell(lastRow.rowKey, 'amount', amt)
    }
  }
  showCutoffPanel.value = false
  ElMessage.success(`已填入${payload.samples.length}笔截止样本`)
}

// ═══ 抽凭引擎 ═══
const showSamplingDialog = ref(false)

function handleVoucherFilled(payload: any): void {
  const vouchers = payload?.samples ?? []
  for (const v of vouchers) {
    addSample()
    const lastRow = samples.value[samples.value.length - 1]
    if (lastRow) {
      updateCell(lastRow.rowKey, 'voucherNo', v.voucherNo || v.voucher_no || '')
      updateCell(lastRow.rowKey, 'sourceDate', v.voucherDate || v.voucher_date || '')
      updateCell(lastRow.rowKey, 'summary', v.summary || '')
      const amt = v.debitAmount ? parseFloat(v.debitAmount) : (v.creditAmount ? parseFloat(v.creditAmount) : 0)
      updateCell(lastRow.rowKey, 'amount', amt)
    }
  }
  showSamplingDialog.value = false
  if (vouchers.length) ElMessage.success(`已填入${vouchers.length}笔凭证`)
}
</script>

<style scoped>
.k8-cutoff-s2v { font-size: 13px; padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }
.stats-card { display: flex; gap: 24px; padding: 12px 16px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 14px; }
.stat-item { display: flex; flex-direction: column; align-items: center; }
.stat-label { font-size: 12px; color: #6b7280; }
.stat-value { font-size: 18px; font-weight: 700; color: #1f2937; }
.stat-danger { color: #dc2626; }
.stat-success { color: #16a34a; }
.cutoff-table { font-size: 13px; }
.table-actions { display: flex; gap: 8px; margin-top: 12px; }
.summary-card { margin-top: 16px; }
:deep(.cross-period-row) { background-color: #fef2f2 !important; }
:deep(.cross-period-row:hover > td) { background-color: #fee2e2 !important; }
:deep(.el-table) { font-size: 13px; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; }
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
