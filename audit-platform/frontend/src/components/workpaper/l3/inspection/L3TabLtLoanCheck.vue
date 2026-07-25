<template>
  <div class="l3-tab-lt-loan-check">
    <!-- ═══ 返回目录 + 标题 + 操作栏 ═══ -->
    <div class="l3-check-header">
      <div class="l3-check-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="l3-check-title">L3-9 长期借款检查表（凭证级）</h3>
      </div>
      <div class="l3-check-header-right">
        <el-button size="small" @click="$emit('open-review', 'L3-9')">复核</el-button>
      </div>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" class="audit-objective" show-icon>
      <template #title>审计目标</template>
      <ul class="ao-list">
        <li>1. 资产负债表中记录的长期借款是存在的，且已记录于恰当账户（存在）</li>
        <li>2. 记录的长期借款由被审计单位拥有或控制（权利和义务）</li>
        <li>3. 长期借款以恰当金额列示，计价或分摊调整已恰当记录（准确性、计价和分摊）</li>
      </ul>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="l3-methodology-context">
      <div class="l3-methodology-text">
        <strong>凭证级检查：</strong>
        选取长期借款相关记账凭证，逐笔核对①原始凭证齐全 ②记账凭证与原始凭证相符 ③账务处理正确
        ④会计期间归属正确 ⑤其他核对事项。检查比例 = 检查合计 ÷ 本期发生额（来自 L3-2 明细），比例过低应扩大样本。
      </div>
    </div>

    <!-- ═══ 测试原因 ═══ -->
    <el-card class="l3-section-card" shadow="never">
      <template #header><span class="l3-section-title">二、测试原因</span></template>
      <div class="test-reasons">
        <el-checkbox :model-value="testReasons.large" :disabled="isReadonly" @change="(v: any) => onReason('large', v)">大额</el-checkbox>
        <el-checkbox :model-value="testReasons.relatedParty" :disabled="isReadonly" @change="(v: any) => onReason('relatedParty', v)">关联方</el-checkbox>
        <el-checkbox :model-value="testReasons.frequent" :disabled="isReadonly" @change="(v: any) => onReason('frequent', v)">大额交易频繁</el-checkbox>
        <el-checkbox :model-value="testReasons.abnormal" :disabled="isReadonly" @change="(v: any) => onReason('abnormal', v)">异常</el-checkbox>
        <el-checkbox :model-value="testReasons.other" :disabled="isReadonly" @change="(v: any) => onReason('other', v)">其他</el-checkbox>
        <el-input v-if="testReasons.other" :model-value="testReasons.otherText" size="small" style="width: 200px" placeholder="其他原因说明" :readonly="isReadonly" @input="(v: string) => onReasonText(v)" />
      </div>
    </el-card>

    <!-- ═══ 凭证级检查表 ═══ -->
    <el-card class="l3-section-card" shadow="never">
      <template #header>
        <div class="l3-section-header">
          <span class="l3-section-title">凭证级检查</span>
          <div class="l3-check-header-right">
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
        <el-table-column label="借方金额(归还)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" size="small" style="width: 100%" @change="(v: number | undefined) => updateRow(row.rowId, 'debitAmount', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方金额(借入)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width: 100%" @change="(v: number | undefined) => updateRow(row.rowId, 'creditAmount', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="支持性文件" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supportingDoc" size="small" placeholder="如借款合同/借据/还款单" @input="(v: string) => updateRow(row.rowId, 'supportingDoc', v)" />
            <span v-else>{{ row.supportingDoc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-for="(label, i) in L3_CHECK_LABELS" :key="i" :label="String(i + 1)" width="48" align="center">
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
    <el-card class="l3-section-card" shadow="never">
      <template #header><span class="l3-section-title">检查比例</span></template>
      <el-table :data="ratioRows" border size="small" style="width: 100%">
        <el-table-column prop="label" label="项目" min-width="140" />
        <el-table-column label="借方(归还)" min-width="150" align="right">
          <template #default="{ row }">{{ row.isRatio ? fmtRate(row.debit) : fmtAmount(row.debit) }}</template>
        </el-table-column>
        <el-table-column label="贷方(借入)" min-width="150" align="right">
          <template #default="{ row }">{{ row.isRatio ? fmtRate(row.credit) : fmtAmount(row.credit) }}</template>
        </el-table-column>
      </el-table>
      <div class="ratio-hint">本期发生额来自 L3-2 明细表（贷方=Σ本期借入，借方=Σ本期归还）；检查比例过低应扩大样本。</div>
    </el-card>

    <!-- ═══ 审计说明 ═══ -->
    <el-card class="l3-section-card" shadow="never">
      <template #header>
        <div class="l3-section-header">
          <span class="l3-section-title">三、审计说明</span>
          <el-button v-if="!isReadonly" size="small" type="warning" plain :loading="aiLoading" @click="handleAi">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 3 }" :readonly="isReadonly" placeholder="记录凭证检查过程、发现的异常及处理..." @input="(v: string) => updateNote('note', v)" />
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card class="l3-conclusion-card" shadow="never">
      <template #header><span class="l3-section-title">四、审计结论</span></template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :readonly="isReadonly" placeholder="A、未见异常。 B、除上述重大不符事项外，其余未见异常。 C、由于存在重大未调整事项，不可确认。" @input="(v: string) => updateNote('conclusion', v)" />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>凭证级检查</strong>：选取长期借款相关记账凭证，逐笔核对①~⑤项，记录索引号与异常</li>
        <li><strong>测试原因</strong>：勾选选样理由（大额/关联方/大额交易频繁/异常/其他）</li>
        <li><strong>检查比例</strong>：检查合计 ÷ 本期发生额（来自 L3-2）；比例过低应扩大样本</li>
        <li><strong>支持性证据</strong>：取得年度内所有借款合同/担保合同/借据/还款单；与银行存款一起发函询证</li>
        <li><strong>关联底稿</strong>：明细 L3-2、征信核对 L3-4、利息测算 L3-5、逾期 L3-7、抵质押 L3-8</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L3TabLtLoanCheck — L3-9 长期借款检查表（凭证级，源模板重建）
 *
 * - 测试原因 + 记账凭证级检查行（核对内容①~⑤）+ 检查比例（来自 L3-2）
 * - 审计说明（AI辅助）+ 审计结论
 *
 * 科目：2501 长期借款（贷方/负债类）
 */
import { computed, inject, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'
import { useL3VoucherCheck } from '@/components/workpaper/composables/useL3VoucherCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
  (e: 'ai-assist', section: string): void
  (e: 'open-review', section: string): void
}>()

const formData = inject<ReturnType<typeof useL3FormData>>('l3FormData')!

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
  L3_CHECK_LABELS,
} = useL3VoucherCheck({
  allResponses: formData.allResponses,
  saveField: formData.saveField,
  debouncedSave: formData.debouncedSave,
})

const ratioRows = computed(() => [
  { label: '检查合计', debit: checkedDebitTotal.value, credit: checkedCreditTotal.value, isRatio: false },
  { label: '本期发生额', debit: periodDebitOccurrence.value, credit: periodCreditOccurrence.value, isRatio: false },
  { label: '检查比例', debit: debitCheckRatio.value, credit: creditCheckRatio.value, isRatio: true },
])

function onReason(field: keyof typeof testReasons.value, val: any): void {
  ;(testReasons.value as any)[field] = Boolean(val)
  updateTestReasons()
}
function onReasonText(val: string): void {
  testReasons.value.otherText = val
  updateTestReasons()
}

const aiLoading = ref(false)
async function handleAi(): Promise<void> {
  aiLoading.value = true
  try {
    const http = (await import('@/utils/http')).default
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'l3-voucher-check-note',
      prompt: '请根据长期借款凭证检查结果，撰写审计说明（检查过程、发现的异常及处理）',
      context: {
        检查笔数: String(rows.value.length),
        异常笔数: String(abnormalCount.value),
        借方检查比例: `${(debitCheckRatio.value * 100).toFixed(2)}%`,
        贷方检查比例: `${(creditCheckRatio.value * 100).toFixed(2)}%`,
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

function rowClass({ row }: { row: { abnormal: boolean } }): string {
  return row.abnormal ? 'abnormal-row' : ''
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtRate(val: number | null | undefined): string {
  if (val == null) return '-'
  return `${(val * 100).toFixed(2)}%`
}
</script>

<style scoped>
.l3-tab-lt-loan-check {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.l3-check-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.l3-check-header-left { display: flex; align-items: center; gap: 12px; }
.l3-check-header-right { display: flex; align-items: center; gap: 8px; }
.l3-check-title { font-size: 15px; font-weight: 600; color: #303133; margin: 0; }

.audit-objective { margin-bottom: 14px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-list { padding-left: 18px; line-height: 1.55; font-size: 12px; margin: 4px 0 0; }

.l3-methodology-context {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  color: #78350f;
  line-height: 1.6;
}
.l3-methodology-text strong { color: #b45309; }

.l3-section-card { margin-bottom: 16px; }
.l3-section-header { display: flex; align-items: center; justify-content: space-between; }
.l3-section-title { font-weight: 600; font-size: 14px; color: #303133; }

.test-reasons { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
.check-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.ratio-hint { margin-top: 8px; font-size: 12px; color: #909399; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table th .cell) { font-size: var(--wp-font-size, 13px); font-weight: 600; }
:deep(.abnormal-row) { background-color: #fef0f0 !important; }

.l3-conclusion-card { margin-top: 16px; }

.l3-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.l3-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.l3-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
