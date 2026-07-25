<template>
  <div class="l2-tab-interest-check">
    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>检查表目标：</strong>
        检查与应付利息有关的记账凭证和相应支持性证据，以确定交易的真实性，是否按规定进行相应的会计处理和披露。
        逐笔核对①原始凭证齐全 ②经授权批准 ③会计处理正确 ④记账凭证与原始凭证金额相符 ⑤会计期间归属正确。
      </div>
    </div>

    <!-- ═══ 跨底稿引用导航 ═══ -->
    <div class="cross-wp-references">
      <span class="cross-wp-label">关联底稿：</span>
      <GtIndexChip
        v-for="r in crossWpRefs"
        :key="r.targetWpCode"
        :value="r.targetWpCode"
        :context="r.label"
        class="cross-wp-chip"
      />
    </div>

    <!-- ═══ L1/L3 计提核对摘要 ═══ -->
    <div class="accrual-summary-bar">
      <span class="indicator-label">L1/L3测算 vs L2账面计提：</span>
      <el-tag :type="accrualStatusType" size="small" effect="plain">{{ accrualStatusText }}</el-tag>
    </div>

    <!-- ═══ 测试原因 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="section-card-title">二、测试原因</span></template>
      <div class="test-reasons">
        <el-checkbox :model-value="testReasons.large" :disabled="isReadonly" @change="(v: any) => onReason('large', v)">大额</el-checkbox>
        <el-checkbox :model-value="testReasons.relatedParty" :disabled="isReadonly" @change="(v: any) => onReason('relatedParty', v)">关联方</el-checkbox>
        <el-checkbox :model-value="testReasons.frequent" :disabled="isReadonly" @change="(v: any) => onReason('frequent', v)">大额交易频繁</el-checkbox>
        <el-checkbox :model-value="testReasons.abnormal" :disabled="isReadonly" @change="(v: any) => onReason('abnormal', v)">异常</el-checkbox>
        <el-checkbox :model-value="testReasons.other" :disabled="isReadonly" @change="(v: any) => onReason('other', v)">其他</el-checkbox>
        <el-input
          v-if="testReasons.other"
          :model-value="testReasons.otherText"
          size="small"
          style="width: 200px"
          placeholder="其他原因说明"
          :readonly="isReadonly"
          @input="(v: string) => onReasonText(v)"
        />
      </div>
    </el-card>

    <!-- ═══ 凭证级检查表 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-card-header">
          <span class="section-card-title">凭证级检查</span>
          <div class="section-card-actions">
            <el-tag v-if="abnormalCount > 0" type="danger" size="small">异常 {{ abnormalCount }}</el-tag>
            <el-tag v-if="incompleteRows.length > 0" type="warning" size="small">未核对完整 {{ incompleteRows.length }}</el-tag>
            <el-button v-if="!isReadonly" type="primary" size="small" @click="addRow">+ 新增凭证</el-button>
          </div>
        </div>
      </template>

      <el-table :data="rows" border size="small" style="width: 100%" max-height="480" :row-class-name="rowClass">
        <el-table-column type="index" label="#" width="40" align="center" fixed />
        <el-table-column label="日期" width="130" fixed>
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.date" type="date" value-format="YYYY-MM-DD" size="small" style="width: 100%" @update:model-value="(v: string) => updateRow(row.rowId, 'date', v || '')" />
            <span v-else>{{ row.date || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @input="(v: string) => updateRow(row.rowId, 'voucherNo', v)" />
            <span v-else>{{ row.voucherNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.businessContent" size="small" @input="(v: string) => updateRow(row.rowId, 'businessContent', v)" />
            <span v-else>{{ row.businessContent || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small" @input="(v: string) => updateRow(row.rowId, 'counterAccount', v)" />
            <span v-else>{{ row.counterAccount || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方明细科目" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.counterSubAccount" size="small" @input="(v: string) => updateRow(row.rowId, 'counterSubAccount', v)" />
            <span v-else>{{ row.counterSubAccount || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" size="small" style="width: 100%" @change="(v: number | undefined) => updateRow(row.rowId, 'debitAmount', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width: 100%" @change="(v: number | undefined) => updateRow(row.rowId, 'creditAmount', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="支持性文件" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supportingDoc" size="small" placeholder="如借款合同/回单" @input="(v: string) => updateRow(row.rowId, 'supportingDoc', v)" />
            <span v-else>{{ row.supportingDoc || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 核对内容①~⑤ -->
        <el-table-column v-for="(label, i) in CHECK_LABELS" :key="i" :label="String(i + 1)" width="48" align="center">
          <template #header>
            <el-tooltip :content="label" placement="top"><span class="check-col-header">{{ i + 1 }}</span></el-tooltip>
          </template>
          <template #default="{ row }">
            <el-checkbox :model-value="row['check' + (i + 1)]" :disabled="isReadonly" @change="(v: any) => updateRow(row.rowId, 'check' + (i + 1), v)" />
          </template>
        </el-table-column>
        <el-table-column label="索引号" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.indexNo" size="small" @input="(v: string) => updateRow(row.rowId, 'indexNo', v)" />
            <span v-else>{{ row.indexNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="70" align="center">
          <template #default="{ row }">
            <el-checkbox :model-value="row.abnormal" :disabled="isReadonly" @change="(v: any) => updateRow(row.rowId, 'abnormal', v)" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @input="(v: string) => updateRow(row.rowId, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" text size="small" @click="removeRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 检查比例 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="section-card-title">检查比例</span></template>
      <el-table :data="ratioRows" border size="small" style="width: 100%">
        <el-table-column prop="label" label="项目" min-width="140" />
        <el-table-column label="借方" min-width="140" align="right">
          <template #default="{ row }">{{ row.isRatio ? fmtRate(row.debit) : fmtAmount(row.debit) }}</template>
        </el-table-column>
        <el-table-column label="贷方" min-width="140" align="right">
          <template #default="{ row }">{{ row.isRatio ? fmtRate(row.credit) : fmtAmount(row.credit) }}</template>
        </el-table-column>
      </el-table>
      <div class="ratio-hint">本期发生额来自 L2-2 明细表（贷方=Σ本期计提，借方=Σ本期支付）；检查比例过低应扩大样本。</div>
    </el-card>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-card-header">
          <span class="section-card-title">三、审计说明</span>
          <el-button v-if="!isReadonly" size="small" type="warning" plain :loading="aiLoading" @click="handleAi">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 3 }" :readonly="isReadonly" placeholder="记录凭证检查过程、发现的异常及处理..." @input="(v: string) => updateNote('note', v)" />
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-card-header">
          <span class="section-card-title">四、审计结论</span>
          <GtReviewTrigger section-id="L2-4" label="复核" />
        </div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :readonly="isReadonly" placeholder="A、未见异常。 B、除上述重大不符事项外，其余未见异常。 C、由于存在重大未调整事项，不可确认。" @input="(v: string) => updateNote('conclusion', v)" />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>凭证级检查</strong>：逐笔选取应付利息相关记账凭证，核对①~⑤项，记录索引号与异常</li>
        <li><strong>测试原因</strong>：勾选选样理由（大额/关联方/大额交易频繁/异常/其他）</li>
        <li><strong>检查比例</strong>：检查合计 ÷ 本期发生额（来自 L2-2）；比例过低应扩大样本</li>
        <li><strong>计提核对</strong>：核对 L1 短期借款/L3 长期借款利息测算与账面计提差异</li>
        <li><strong>关联底稿</strong>：L1 短期借款、L3 长期借款、L8 财务费用</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L2TabInterestCheck.vue — L2-4 应付利息检查表（凭证级，源模板重建）
 *
 * - 测试原因 + 记账凭证级检查行（核对内容①~⑤）+ 检查比例（来自 L2-2）
 * - 保留 L1/L3 计提核对摘要 + 跨底稿引用（GtIndexChip）
 * - 审计说明（AI辅助）+ 审计结论（复核圆点）
 *
 * 科目：2231 应付利息（贷方/负债类）
 */
import { computed, ref, toRef, provide, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useL2FormData } from '../../composables/useL2FormData'
import { useL2CrossSheet } from '../../composables/useL2CrossSheet'
import { useL2VoucherCheck } from '../../composables/useL2VoucherCheck'
import { useWorkpaperReviewThreads } from '../../composables/useWorkpaperReviewThreads'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── 复核圆点 provide ────────────────────────────────────────────────────────
const wpIdRef = toRef(props, 'wpId')
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

// ─── Composables ─────────────────────────────────────────────────────────────
const formData = useL2FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetName: 'L2-4',
})

const crossSheet = useL2CrossSheet(formData.allResponses)
const crossWpRefs = crossSheet.cross_wp_references

const {
  rows,
  testReasons,
  updateTestReasons,
  addRow,
  removeRow,
  updateRow,
  checkedDebitTotal,
  checkedCreditTotal,
  periodDebitOccurrence,
  periodCreditOccurrence,
  debitCheckRatio,
  creditCheckRatio,
  abnormalCount,
  incompleteRows,
  auditNote,
  auditConclusion,
  updateNote,
  CHECK_LABELS,
} = useL2VoucherCheck({
  allResponses: formData.allResponses,
  saveField: formData.saveField,
  debouncedSave: formData.debouncedSave,
})

// ─── L1/L3 计提核对摘要 ──────────────────────────────────────────────────────
const accrualStatusText = computed(() => {
  if (!crossSheet.isInterestDataReady.value) return '待L1/L3利息测算完成'
  const r = crossSheet.accrualVsL1L3.value
  if (r.isConsistent) return `一致（差异${r.diff}元）`
  return `不一致，差异${r.diff}元（${r.diff > 0 ? '账面少计提' : '账面多计提'}）`
})
const accrualStatusType = computed<'success' | 'warning' | 'danger' | 'info'>(() => {
  if (!crossSheet.isInterestDataReady.value) return 'info'
  return crossSheet.accrualVsL1L3.value.isConsistent ? 'success' : 'danger'
})

// ─── 检查比例表 ──────────────────────────────────────────────────────────────
const ratioRows = computed(() => [
  { label: '检查合计', debit: checkedDebitTotal.value, credit: checkedCreditTotal.value, isRatio: false },
  { label: '本期发生额', debit: periodDebitOccurrence.value, credit: periodCreditOccurrence.value, isRatio: false },
  { label: '检查比例', debit: debitCheckRatio.value, credit: creditCheckRatio.value, isRatio: true },
])

// ─── 测试原因 ────────────────────────────────────────────────────────────────
function onReason(field: keyof typeof testReasons.value, val: any): void {
  ;(testReasons.value as any)[field] = Boolean(val)
  updateTestReasons()
}
function onReasonText(val: string): void {
  testReasons.value.otherText = val
  updateTestReasons()
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────
const aiLoading = ref(false)
async function handleAi(): Promise<void> {
  aiLoading.value = true
  try {
    const http = (await import('@/utils/http')).default
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'l2-voucher-check-note',
      prompt: '请根据应付利息凭证检查结果，撰写审计说明（检查过程、发现的异常及处理）',
      context: {
        检查笔数: String(rows.value.length),
        异常笔数: String(abnormalCount.value),
        借方检查比例: `${(debitCheckRatio.value * 100).toFixed(2)}%`,
        贷方检查比例: `${(creditCheckRatio.value * 100).toFixed(2)}%`,
        计提核对: accrualStatusText.value,
      },
    })
    const content = res.data?.data?.content || res.data?.content
    if (content) {
      updateNote('note', content)
      ElMessage.success('AI建议已生成')
    } else {
      ElMessage.info('AI辅助暂不可用')
    }
  } catch {
    ElMessage.info('AI辅助暂不可用')
  } finally {
    aiLoading.value = false
  }
}

// ─── 行样式 ──────────────────────────────────────────────────────────────────
function rowClass({ row }: { row: { abnormal: boolean } }): string {
  return row.abnormal ? 'abnormal-row' : ''
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────
function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtRate(val: number | null | undefined): string {
  if (val == null) return '-'
  return `${(val * 100).toFixed(2)}%`
}

// ─── Init ────────────────────────────────────────────────────────────────────
onMounted(() => {
  formData.loadData()
})
</script>

<style scoped>
.l2-tab-interest-check {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.methodology-context {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  color: #78350f;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b45309;
}

.cross-wp-references {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: #f0f5ff;
  border: 1px solid #d6e4ff;
  border-radius: 6px;
  margin-bottom: 14px;
}

.cross-wp-label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #606266;
  white-space: nowrap;
}

.cross-wp-chip {
  margin-right: 4px;
}

.accrual-summary-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  margin-bottom: 16px;
}

.indicator-label {
  font-weight: 500;
  color: #606266;
}

.section-card {
  margin-bottom: 16px;
}

.section-card-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.section-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.test-reasons {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
}

.check-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.ratio-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

:deep(.abnormal-row) {
  background-color: #fef0f0 !important;
}

.l2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.l2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
