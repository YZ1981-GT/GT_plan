<template>
  <div class="k9-contract-check">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>发生与准确性：</b>合同项下管理费用（咨询/租赁/服务等）真实发生、金额与合同一致；</li>
        <li><b>截止与分类：</b>按合同履行期间恰当确认与分摊，记入正确期间与账户。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K9-5 合同检查表</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" text @click="handleAiAssist"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        <el-button size="small" text @click="openReviewDialog?.('K9-5-contract-check')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>检查重大管理费用合同（中介服务/咨询/租赁等），核实合同真实性、金额匹配、审批完整性及合规性。不合规项红色标记。金额匹配容差±100元。支持行级抽凭📎+OCR识别。</p>
    </div>

    <!-- ═══ 不合规摘要（有不合规项时显示） ═══ -->
    <el-alert v-if="nonComplianceSummary.count > 0" type="error" :closable="false" show-icon style="margin-bottom:10px">
      <template #title>⚠️ 发现 {{ contractNonCompliance }} 项合同不合规</template>
      <template #default>
        <ul class="non-compliance-list">
          <li v-for="item in nonComplianceSummary.items.filter(i => i.sheetId === 'K9-5')" :key="item.label">{{ item.label }}：{{ item.evidence || '未说明' }}</li>
        </ul>
      </template>
    </el-alert>

    <!-- ═══ 合同检查表格 ═══ -->
    <el-table :data="contractRows" border size="small" style="width:100%;font-size:13px" max-height="450" :row-class-name="contractRowClassName">
      <el-table-column type="index" label="#" width="42" align="center" />
      <el-table-column prop="contractName" label="合同名称" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.contractName" size="small" @change="(v: string) => updateContractCell(row.rowKey, 'contractName', v)" />
          <span v-else>{{ row.contractName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="contractType" label="类型" width="100">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.contractType" size="small" @change="(v: string) => updateContractCell(row.rowKey, 'contractType', v)">
            <el-option value="中介服务" label="中介服务" />
            <el-option value="咨询" label="咨询" />
            <el-option value="租赁" label="租赁" />
            <el-option value="维修" label="维修" />
            <el-option value="其他" label="其他" />
          </el-select>
          <span v-else>{{ row.contractType || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="contractAmount" label="合同金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.contractAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateContractCell(row.rowKey, 'contractAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.contractAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="paidAmount" label="实付金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.paidAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateContractCell(row.rowKey, 'paidAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.paidAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="匹配" width="65" align="center">
        <template #default="{ row }">
          <el-tag :type="row.amountMatched ? 'success' : 'danger'" size="small">{{ row.amountMatched ? '✓' : '✗' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="approvalComplete" label="审批" width="95">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.approvalComplete" size="small" placeholder="—" @change="(v: string) => updateContractCell(row.rowKey, 'approvalComplete', v)">
            <el-option value="合规" label="合规" /><el-option value="不合规" label="不合规" /><el-option value="不适用" label="不适用" />
          </el-select>
          <span v-else :class="{ 'non-comply': row.approvalComplete === '不合规' }">{{ row.approvalComplete || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="authenticity" label="真实性" width="95">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.authenticity" size="small" placeholder="—" @change="(v: string) => updateContractCell(row.rowKey, 'authenticity', v)">
            <el-option value="合规" label="合规" /><el-option value="不合规" label="不合规" /><el-option value="不适用" label="不适用" />
          </el-select>
          <span v-else :class="{ 'non-comply': row.authenticity === '不合规' }">{{ row.authenticity || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="compliance" label="综合合规" width="95">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.compliance" size="small" placeholder="—" @change="(v: string) => updateContractCell(row.rowKey, 'compliance', v)">
            <el-option value="合规" label="合规" /><el-option value="不合规" label="不合规" /><el-option value="不适用" label="不适用" />
          </el-select>
          <span v-else :class="{ 'non-comply': row.compliance === '不合规' }">{{ row.compliance || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="evidence" label="证据" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.evidence" size="small" @change="(v: string) => updateContractCell(row.rowKey, 'evidence', v)" />
          <span v-else>{{ row.evidence || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="55" align="center">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="removeContractRow(row.rowKey)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 操作栏 ═══ -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddContract">+ 新增合同</el-button>
    </div>

    <!-- ═══ 检查结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><span>合同检查结论</span></template>
      <el-input
        :model-value="contractConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="请填写合同检查结论..."
        @blur="(e: FocusEvent) => saveContractConclusion((e.target as HTMLTextAreaElement)?.value ?? '')"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>检查重大费用合同：中介服务/咨询/租赁等</li>
        <li>核实合同金额与实际支付匹配（容差±100元）</li>
        <li>检查审批流程完整性、合同真实性</li>
        <li>不合规项红色标记并填写审计证据</li>
        <li>支持行级抽凭📎核查原始合同+OCR识别</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K9TabContractCheck.vue — K9-5 合同检查表
 *
 * Spec: .kiro/specs/k9-admin-expenses/ | Task: 4.6
 * Requirements: 6.1-6.4
 *
 * 功能：
 * - 检查重大费用合同（中介服务/咨询/租赁）的真实性/金额匹配/审批
 * - 合规判断三态（合规/不合规/不适用）
 * - 不合规项红色摘要
 * - 行级抽凭+OCR
 */
import { toRef, computed, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useK9Checks } from '@/components/workpaper/composables/useK9Checks'
import type { Ref } from 'vue'
import type { K9ContractCheckRow } from '@/components/workpaper/composables/useK9Checks'

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
  contractRows,
  contractConclusion,
  nonComplianceSummary,
  addContractRow,
  removeContractRow,
  updateContractCell,
  saveContractConclusion,
} = useK9Checks({
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  projectId: toRef(props, 'projectId'),
  wpId: toRef(props, 'wpId'),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, typeof value === 'string' ? { remark: value } : { remark: JSON.stringify(value) }),
})

// ═══ 统计 ═══
const contractNonCompliance = computed(() => contractRows.value.filter(r => r.compliance === '不合规').length)

// ═══ 新增合同（弹窗输入名称） ═══
async function handleAddContract(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入合同名称', '新增合同检查', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：XX咨询服务合同',
    })
    if (value?.trim()) {
      addContractRow(value.trim())
    }
  } catch { /* cancelled */ }
}

// ═══ UI Helpers ═══
function contractRowClassName({ row }: { row: K9ContractCheckRow }): string {
  return row.compliance === '不合规' ? 'non-compliance-row' : ''
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleAiAssist(): void {
  ElMessage.info('AI辅助合同检查评估...')
}
</script>

<style scoped>
.k9-contract-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.non-compliance-list { margin: 4px 0 0; padding-left: 16px; font-size: 12px; }
.non-comply { color: #f56c6c; font-weight: 600; }
.table-actions { display: flex; gap: 8px; margin-top: 12px; }
.conclusion-card { margin-top: 16px; }
:deep(.non-compliance-row) { background-color: #fef2f2 !important; }
:deep(.non-compliance-row:hover > td) { background-color: #fee2e2 !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; }
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
