<script setup lang="ts">
/**
 * F4TabRelatedParty — F4-6 关联方检查表
 * Spec: .kiro/specs/f4-accounts-payable/ Task 6.6
 * 集中度>30% 橙色高亮 + 汇总 + 导入导出
 * Requirements: 9.1~9.6
 */
import { inject, toRef, ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { useF4RelatedParty } from '../composables/useF4RelatedParty'

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
  auditNote,
  addRow,
  removeRow,
  updateCell,
  rowClassName,
} = useF4RelatedParty({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const aiLoading = ref(false)

async function generateAiConclusion() {
  aiLoading.value = true
  try {
    const { data } = await axios.post(`/api/workpapers/${props.wpId}/f4/ai/related-evaluation`)
    auditNote.value = data?.data?.conclusion || data?.conclusion || ''
    ElMessage.success('AI结论已生成')
  } catch { ElMessage.error('AI生成失败') }
  finally { aiLoading.value = false }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────
async function handleExportTemplate() {
  try {
    const resp = await axios.post(`/api/workpapers/${props.wpId}/f4/export-template?sheet=F4-6`, null, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'F4-6关联方检查模板.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出模板失败') }
}

async function handleExportData() {
  try {
    const resp = await axios.post(`/api/workpapers/${props.wpId}/f4/export-data?sheet=F4-6`, null, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'F4-6关联方检查数据.xlsx'; a.click()
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
      await axios.post(`/api/workpapers/${props.wpId}/f4/import-data?sheet=F4-6`, fd)
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
  <div class="f4-tab-related-party">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 关联方检查表检查关联方应付账款的合理性和定价公允性。</p>
        <p>2. 期末余额(公式) = 期初余额 + 本期增加 - 本期减少。</p>
        <p>3. 占比(公式) = 单笔期末余额 / 关联方应付总余额 × 100%。</p>
        <p>4. 占比>30%的行橙色高亮，表示集中度过高需重点关注。</p>
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
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-6-related-party')">复核</el-button>
      </div>
    </div>

    <el-table :data="rows" border size="small" :row-class-name="rowClassName" style="width:100%;font-size:13px">
      <el-table-column prop="seq" label="序号" width="60" />
      <el-table-column label="关联方名称" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.partyName" size="small" @change="(v: string) => updateCell(row.rowId, 'partyName', v)" />
          <span v-else>{{ row.partyName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="关联关系" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.relationship" size="small" @change="(v: string) => updateCell(row.rowId, 'relationship', v)" />
          <span v-else>{{ row.relationship }}</span>
        </template>
      </el-table-column>
      <el-table-column label="款项性质" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.paymentNature" size="small" @change="(v: string) => updateCell(row.rowId, 'paymentNature', v)" />
          <span v-else>{{ row.paymentNature }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初余额" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.openingBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'openingBalance', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.openingBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期增加" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.currentIncrease" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'currentIncrease', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.currentIncrease) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期减少" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.currentDecrease" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'currentDecrease', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.currentDecrease) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" min-width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期末 = 期初 + 增加 - 减少" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.closingBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="占比(%)" min-width="90" align="right">
        <template #default="{ row }">
          <el-tooltip content="占比 = 余额/总额 × 100%" placement="top">
            <span class="formula-cell" :class="{ 'high-concentration': row.isHighConcentration }">{{ row.concentration.toFixed(2) }}%</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="结算周期" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.settlementCycle" size="small" @change="(v: string) => updateCell(row.rowId, 'settlementCycle', v)" />
          <span v-else>{{ row.settlementCycle }}</span>
        </template>
      </el-table-column>
      <el-table-column label="是否超期" min-width="80">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.isOverdue" size="small" @change="(v: string) => updateCell(row.rowId, 'isOverdue', v)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
          </el-select>
          <span v-else>{{ row.isOverdue }}</span>
        </template>
      </el-table-column>
      <el-table-column label="定价公允性" min-width="100">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.fairness" size="small" @change="(v: string) => updateCell(row.rowId, 'fairness', v)">
            <el-option label="公允" value="公允" />
            <el-option label="基本公允" value="基本公允" />
            <el-option label="不公允" value="不公允" />
            <el-option label="未知" value="未知" />
          </el-select>
          <span v-else>{{ row.fairness }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" link size="small" type="danger" @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="subtotal-bar">
      关联方应付总额：{{ fmtAmount(summary.totalClosing) }} ｜超期：{{ summary.overdueCount }}笔 ｜高集中度(>30%)：{{ summary.highConcentrationCount }}笔
    </div>

    <el-card class="audit-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button size="small" :loading="aiLoading" :disabled="isReadonly" @click="generateAiConclusion">✨ AI生成</el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请输入关联方检查审计结论，或点击AI生成..."
      />
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-related-party { font-size: 13px; }
.guidance-details { margin-bottom: 12px; font-size: 13px; }
.guidance-details .guidance-content { padding: 8px 12px; background: #fffbeb; border-left: 3px solid #f59e0b; margin-top: 6px; font-size: 12px; line-height: 1.8; }
.section-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 8px; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.high-concentration { color: #e6a23c; font-weight: 600; }
:deep(.concentration-warn td) { background: #fef3e6 !important; }
.subtotal-bar { margin-top: 8px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-weight: 600; font-size: 13px; }
.audit-card { margin-top: 12px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
