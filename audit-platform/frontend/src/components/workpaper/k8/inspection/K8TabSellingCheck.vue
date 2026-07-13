<template>
  <div class="k8-selling-check">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>发生：</b>记录的销售费用确已发生且与本期经营相关；</li>
        <li><b>完整性与准确性：</b>销售费用记录完整、金额准确，无虚列或漏记；</li>
        <li><b>截止与分类：</b>费用归属期间正确、明细分类恰当。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K8-8 销售费用综合检查表</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" text @click="handleAiAssist"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        <el-button size="small" text @click="openReviewDialog?.('K8-8-selling-check')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>逐项检查销售费用相关控制合规性，每项判断"合规/不合规/不适用"。不合规项需填写审计证据并红色标记。覆盖费用归属期间、分类正确性、关联方交易、大额异常支出等。</p>
    </div>

    <!-- ═══ 不合规摘要 ═══ -->
    <el-alert v-if="sellingNonComplianceCount > 0" type="error" :closable="false" show-icon style="margin-bottom:10px">
      <template #title>⚠️ 发现 {{ sellingNonComplianceCount }} 项不合规</template>
    </el-alert>

    <!-- ═══ 综合检查表格 ═══ -->
    <el-table :data="sellingCheckRows" border size="small" style="width:100%;font-size:13px" max-height="450" :row-class-name="sellingRowClassName">
      <el-table-column type="index" label="#" width="42" align="center" />
      <el-table-column prop="checkItem" label="检查项" min-width="130">
        <template #default="{ row }">
          <span class="check-item-name">{{ row.checkItem }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="200">
        <template #default="{ row }">
          <span class="check-desc">{{ row.description }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合规判断" width="130" align="center">
        <template #default="{ row }">
          <el-radio-group v-if="!isReadonly" :model-value="row.compliance" size="small" @change="(v: string) => updateSellingCheckCompliance(row.rowKey, v as any)">
            <el-radio-button value="合规">合规</el-radio-button>
            <el-radio-button value="不合规">不合规</el-radio-button>
            <el-radio-button value="不适用">N/A</el-radio-button>
          </el-radio-group>
          <el-tag v-else :type="complianceTagType(row.compliance)" size="small">{{ row.compliance || '待判断' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="evidence" label="证据/说明" min-width="160">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.evidence" size="small" placeholder="审计证据" @change="(v: string) => updateSellingCheckEvidence(row.rowKey, v)" />
          <span v-else>{{ row.evidence || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateSellingCheckCell(row.rowKey, 'remark', v)" />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 统计汇总 ═══ -->
    <div class="check-summary">
      <span class="summary-item"><el-tag type="success" size="small">合规</el-tag> {{ complianceCount }} 项</span>
      <span class="summary-item"><el-tag type="danger" size="small">不合规</el-tag> {{ sellingNonComplianceCount }} 项</span>
      <span class="summary-item"><el-tag type="info" size="small">不适用</el-tag> {{ naCount }} 项</span>
      <span class="summary-item"><el-tag size="small">待判断</el-tag> {{ pendingCount }} 项</span>
      <el-button size="small" plain @click="showSamplingDialog = true">🎲 抽凭</el-button>
    </div>

    <!-- ═══ 抽凭引擎 Dialog ═══ -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 6601 销售费用-综合检查）" width="720px" :close-on-click-modal="false" destroy-on-close>
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

    <!-- ═══ 综合检查结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><span>综合检查结论</span></template>
      <el-input
        :model-value="sellingConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="请填写销售费用综合检查结论..."
        @blur="(e: FocusEvent) => saveSellingConclusion((e.target as HTMLTextAreaElement)?.value ?? '')"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>逐项判断：合规/不合规/不适用三态</li>
        <li>不合规项红色高亮，必须填写审计证据</li>
        <li>覆盖：费用期间归属、分类正确性、关联方、大额异常、政策一致性、税前扣除限额、凭证完整性、审批流程</li>
        <li>检查项来源：审计程序表K8A中确定的检查要点</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K8TabSellingCheck.vue — K8-8 销售费用综合检查表
 *
 * Spec: .kiro/specs/k8-selling-expenses/ | Task: 4.6
 * Requirements: 6.1-6.4
 *
 * 功能：
 * - 逐项合规判断（合规/不合规/不适用）
 * - 不合规项红色摘要
 * - 行级抽凭+OCR
 * - 统计各状态计数
 */
import { ref, toRef, computed, inject, defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useK8Checks } from '@/components/workpaper/composables/useK8Checks'
import type { Ref } from 'vue'
import type { K8SellingCheckRow, ComplianceState } from '@/components/workpaper/composables/useK8Checks'

const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'),
)

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
  sellingCheckRows,
  sellingConclusion,
  updateSellingCheckCompliance,
  updateSellingCheckEvidence,
  updateSellingCheckCell,
  saveSellingConclusion,
} = useK8Checks({
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  projectId: toRef(props, 'projectId'),
  wpId: toRef(props, 'wpId'),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, typeof value === 'string' ? { remark: value } : { remark: JSON.stringify(value) }),
})

// ═══ 统计 ═══
const sellingNonComplianceCount = computed(() => sellingCheckRows.value.filter(r => r.compliance === '不合规').length)
const complianceCount = computed(() => sellingCheckRows.value.filter(r => r.compliance === '合规').length)
const naCount = computed(() => sellingCheckRows.value.filter(r => r.compliance === '不适用').length)
const pendingCount = computed(() => sellingCheckRows.value.filter(r => !r.compliance).length)

// ═══ UI Helpers ═══
function sellingRowClassName({ row }: { row: K8SellingCheckRow }): string {
  return row.compliance === '不合规' ? 'non-compliance-row' : ''
}

function complianceTagType(state: ComplianceState | null): 'success' | 'danger' | 'info' | '' {
  if (state === '合规') return 'success'
  if (state === '不合规') return 'danger'
  if (state === '不适用') return 'info'
  return ''
}

function handleAiAssist(): void {
  ElMessage.info('AI辅助综合检查评估...')
}

// ═══ 抽凭引擎 ═══
const showSamplingDialog = ref(false)
const currentYear = computed(() => new Date().getFullYear())

function handleVoucherFilled(payload: any): void {
  showSamplingDialog.value = false
  const vouchers = payload?.samples ?? []
  if (vouchers.length) ElMessage.success(`已选取${vouchers.length}笔凭证样本`)
}
</script>

<style scoped>
.k8-selling-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.check-item-name { font-weight: 500; color: #303133; }
.check-desc { font-size: 12px; color: #606266; }
.check-summary { display: flex; gap: 16px; margin-top: 12px; padding: 10px 14px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; }
.summary-item { display: flex; align-items: center; gap: 4px; font-size: var(--wp-font-size, 13px); }
.conclusion-card { margin-top: 16px; }
:deep(.non-compliance-row) { background-color: #fef2f2 !important; }
:deep(.non-compliance-row:hover > td) { background-color: #fee2e2 !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-radio-button__inner) { padding: 4px 8px; font-size: 11px; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; }
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
