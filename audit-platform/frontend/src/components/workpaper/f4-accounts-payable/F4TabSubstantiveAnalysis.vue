<script setup lang="ts">
/**
 * F4TabSubstantiveAnalysis — F4-4 实质性分析
 * Spec: .kiro/specs/f4-accounts-payable/ Task 6.6
 * 变动率>20% 橙色高亮 + AI审计结论
 * Requirements: 7.1~7.6
 */
import { inject, toRef, ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { useF4SubstantiveAnalysis } from '../composables/useF4SubstantiveAnalysis'
import GtIndexChip from '../GtIndexChip.vue'

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
} = useF4SubstantiveAnalysis({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const aiLoading = ref(false)

async function generateAiConclusion() {
  aiLoading.value = true
  try {
    const { data } = await axios.post(`/api/workpapers/${props.wpId}/f4/ai/substantive-analysis`)
    auditConclusion.value = data?.data?.conclusion || data?.conclusion || ''
    ElMessage.success('AI结论已生成')
  } catch { ElMessage.error('AI生成失败') }
  finally { aiLoading.value = false }
}

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(v: number | 'N/A'): string {
  if (v === 'N/A') return 'N/A'
  return `${v.toFixed(2)}%`
}
</script>

<template>
  <div class="f4-tab-substantive">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 实质性分析将应付账款各构成按项目分析同比变动。</p>
        <p>2. 变动额 = 本期 - 上期；变动率 = (本期-上期)/上期 × 100%。</p>
        <p>3. 变动率超过20%的行橙色高亮，需要提供合理解释。</p>
        <p>4. 预期差异 = 本期 - 预期值，辅助判断是否存在异常波动。</p>
      </div>
    </details>

    <el-alert
      class="audit-objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：通过实质性分析程序识别应付账款(2202)各构成的异常波动，评估余额变动的合理性，为进一步审计程序提供方向。"
    />

    <div class="section-toolbar">
      <div class="toolbar-left">
        <el-button size="small" :disabled="isReadonly" @click="addRow">+ 新增行</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F4-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-4-substantive')">复核</el-button>
      </div>
    </div>

    <el-table :data="rows" border size="small" :row-class-name="rowClassName" style="width:100%;font-size:13px">
      <el-table-column prop="seq" label="序号" width="60" />
      <el-table-column label="分析项目" min-width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.item" size="small" @change="(v: string) => updateCell(row.rowId, 'item', v)" />
          <span v-else>{{ row.item }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期金额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.currentAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'currentAmount', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.currentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.priorAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'priorAmount', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动额" min-width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="变动额 = 本期 - 上期" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.changeAmount) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="变动率" min-width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="变动率 = (本期-上期)/上期 × 100%" placement="top">
            <span class="formula-cell" :class="{ 'high-rate': row.isHighChange }">{{ fmtRate(row.changeRate) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="预期值" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.expectedValue" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'expectedValue', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.expectedValue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="预期差异" min-width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="预期差异 = 本期 - 预期" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.expectedDifference) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="分析说明" min-width="180">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.explanation" size="small" @change="(v: string) => updateCell(row.rowId, 'explanation', v)" />
          <span v-else>{{ row.explanation }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" link size="small" type="danger" @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="subtotal-bar">
      本期合计：{{ fmtAmount(summary.totalCurrent) }} ｜上期合计：{{ fmtAmount(summary.totalPrior) }} ｜超阈值项：{{ summary.highChangeCount }}项
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:F4-1" :context-project-id="projectId" />
          </div>
        </div>
      </template>
      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :loading="aiLoading" :disabled="isReadonly" @click="generateAiConclusion">🤖 AI辅助</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-4-substantive')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditConclusion"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="请输入实质性分析审计结论，或点击AI辅助生成..."
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-substantive { font-size: 13px; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; font-size: 13px; }
.guidance-details .guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-details .guidance-content p { margin: 2px 0; }
.audit-objective { margin-bottom: 12px; }
.section-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.high-rate { color: #e6a23c; font-weight: 600; }
:deep(.high-change-row td) { background: #fef3e6 !important; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.subtotal-bar { margin-top: 8px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-weight: 600; font-size: 13px; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; }
</style>
