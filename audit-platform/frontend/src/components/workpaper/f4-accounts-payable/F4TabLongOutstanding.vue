<script setup lang="ts">
/**
 * F4TabLongOutstanding — F4-5 长期挂账检查
 * Spec: .kiro/specs/f4-accounts-payable/ Task 6.6
 * >2年橙色 / >3年红色 + 汇总 + 导入导出
 * Requirements: 8.1~8.6
 */
import { inject, toRef, ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { useF4LongOutstanding } from '../composables/useF4LongOutstanding'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  rows,
  summary,
  auditConclusion,
  addRow,
  removeRow,
  updateCell,
  rowClassName,
} = useF4LongOutstanding({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const aiLoading = ref(false)

async function generateAiConclusion() {
  aiLoading.value = true
  try {
    const { data } = await axios.post(`/api/workpapers/${props.wpId}/f4/ai/long-outstanding`)
    auditConclusion.value = data?.data?.conclusion || data?.conclusion || ''
    ElMessage.success('AI结论已生成')
  } catch { ElMessage.error('AI生成失败') }
  finally { aiLoading.value = false }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────
async function handleExportTemplate() {
  try {
    const resp = await axios.post(`/api/workpapers/${props.wpId}/f4/export-template?sheet=F4-5`, null, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'F4-5长期挂账模板.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出模板失败') }
}

async function handleExportData() {
  try {
    const resp = await axios.post(`/api/workpapers/${props.wpId}/f4/export-data?sheet=F4-5`, null, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'F4-5长期挂账数据.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出数据失败') }
}

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const fd = new FormData(); fd.append('file', file)
    try {
      await axios.post(`/api/workpapers/${props.wpId}/f4/import-data?sheet=F4-5`, fd)
      ElMessage.success('导入成功')
      window.location.reload()
    } catch { ElMessage.error('导入失败') }
  }
  input.click()
}

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <div class="f4-tab-long-outstanding">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 长期挂账检查关注超过2年未付的应付账款，评估是否应转营业外收入。</p>
        <p>2. 挂账天数 = 当前日期 - 挂账起始日（自动计算）。</p>
        <p>3. >2年橙色高亮（需关注）、>3年红色高亮（重点关注/建议转收入）。</p>
        <p>4. 汇总统计：总额、2年以上金额、3年以上金额、建议转营业外收入金额。</p>
      </div>
    </details>

    <div class="section-toolbar">
      <div class="toolbar-left">
        <el-button size="small" :disabled="isReadonly" @click="addRow">+ 新增行</el-button>
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <div class="toolbar-right">
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-5-long-outstanding')">复核</el-button>
      </div>
    </div>

    <el-table :data="rows" border size="small" :row-class-name="rowClassName" style="width:100%;font-size:13px">
      <el-table-column prop="seq" label="序号" width="60" />
      <el-table-column label="债权人" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.creditor" size="small" @change="(v: string) => updateCell(row.rowId, 'creditor', v)" />
          <span v-else>{{ row.creditor }}</span>
        </template>
      </el-table-column>
      <el-table-column label="挂账金额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.amount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'amount', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="挂账起始日" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.startDate" size="small" placeholder="YYYY-MM-DD" @change="(v: string) => updateCell(row.rowId, 'startDate', v)" />
          <span v-else>{{ row.startDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="挂账天数" min-width="100" align="right">
        <template #default="{ row }">
          <el-tooltip content="当前日期 - 挂账起始日" placement="top">
            <span class="formula-cell" :class="{ 'days-orange': row.highlightLevel === 'orange', 'days-red': row.highlightLevel === 'red' }">
              {{ row.outstandingDays }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="款项性质" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.paymentNature" size="small" @change="(v: string) => updateCell(row.rowId, 'paymentNature', v)" />
          <span v-else>{{ row.paymentNature }}</span>
        </template>
      </el-table-column>
      <el-table-column label="挂账原因" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reason" size="small" @change="(v: string) => updateCell(row.rowId, 'reason', v)" />
          <span v-else>{{ row.reason }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合同纠纷" min-width="90">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.hasDispute" size="small" @change="(v: string) => updateCell(row.rowId, 'hasDispute', v)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
          </el-select>
          <span v-else>{{ row.hasDispute }}</span>
        </template>
      </el-table-column>
      <el-table-column label="转营业外收入" min-width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.shouldTransferIncome" size="small" @change="(v: string) => updateCell(row.rowId, 'shouldTransferIncome', v)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
          </el-select>
          <span v-else>{{ row.shouldTransferIncome }}</span>
        </template>
      </el-table-column>
      <el-table-column label="处理建议" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.suggestion" size="small" @change="(v: string) => updateCell(row.rowId, 'suggestion', v)" />
          <span v-else>{{ row.suggestion }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" link size="small" type="danger" @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="subtotal-bar">
      总额：{{ fmtAmount(summary.totalAmount) }} ｜>2年：{{ fmtAmount(summary.over2YearAmount) }} ｜>3年：{{ fmtAmount(summary.over3YearAmount) }} ｜建议转收入：{{ fmtAmount(summary.transferAmount) }}
    </div>

    <el-card class="audit-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button size="small" :loading="aiLoading" :disabled="isReadonly" @click="generateAiConclusion">✨ AI生成</el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请输入长期挂账检查审计结论，或点击AI生成..."
      />
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-long-outstanding { font-size: 13px; }
.guidance-details { margin-bottom: 12px; font-size: 13px; }
.guidance-details .guidance-content { padding: 8px 12px; background: #fffbeb; border-left: 3px solid #f59e0b; margin-top: 6px; font-size: 12px; line-height: 1.8; }
.section-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 8px; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.days-orange { color: #e6a23c; font-weight: 600; }
.days-red { color: #f56c6c; font-weight: 700; }
:deep(.long-outstanding-orange td) { background: #fef3e6 !important; }
:deep(.long-outstanding-red td) { background: #fef0f0 !important; }
.subtotal-bar { margin-top: 8px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-weight: 600; font-size: 13px; }
.audit-card { margin-top: 12px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
