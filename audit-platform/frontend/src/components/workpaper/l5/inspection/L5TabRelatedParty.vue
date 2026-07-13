<template>
  <div class="l5-tab-related-party">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L5-6 关联方及交易检查</h3>
        <el-tag v-if="unfairCount > 0" type="danger" size="small">{{ unfairCount }}项不公允</el-tag>
        <el-tag v-if="pendingCount > 0" type="warning" size="small">{{ pendingCount }}项待评估</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增关联方
        </el-button>
        <el-button size="small" @click="handleAI('relatedParty')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      <template #title>
        <strong>审计目标：</strong>识别关联方长期应付款交易，核实关联关系与定价依据，评估是否存在非公允安排（低息/免息/超长期限）及披露完整性。
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>关联方交易公允性检查：</strong>
        识别关联方长期应付款交易（融资租赁/分期付款等），核实关联关系和定价依据。
        净额 = 长期应付款余额 − 未确认融资费用余额（账面价值）。
        评估是否存在非公允安排（低息/免息/超长期限等）。
      </div>
    </div>

    <!-- ═══ 关联方检查表主体 ═══ -->
    <el-table :data="computedRows" border size="small" style="width: 100%" highlight-current-row>
      <el-table-column type="index" label="#" width="50" align="center" />
      <el-table-column label="关联方名称" min-width="160">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.partyName" size="small" @change="(val: string) => handleUpdate($index, 'partyName', val)" />
          <span v-else>{{ row.partyName || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="关联关系" min-width="120">
        <template #default="{ row, $index }">
          <el-select v-if="!isReadonly" :model-value="row.relationship" size="small" style="width:100%" @change="(val: string) => handleUpdate($index, 'relationship', val)">
            <el-option label="母公司" value="母公司" />
            <el-option label="子公司" value="子公司" />
            <el-option label="联营企业" value="联营企业" />
            <el-option label="合营企业" value="合营企业" />
            <el-option label="关键管理人员" value="关键管理人员" />
            <el-option label="其他关联方" value="其他关联方" />
          </el-select>
          <span v-else>{{ row.relationship || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="应付款余额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.payableBalance" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'payableBalance', val ?? 0)" />
          <span v-else>{{ fmtAmount(row.payableBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="未确认余额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.unrecognizedBalance" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'unrecognizedBalance', val ?? 0)" />
          <span v-else>{{ fmtAmount(row.unrecognizedBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账面净额" min-width="120" align="right">
        <template #header>
          <el-tooltip content="应付款 − 未确认融资费用" placement="top">
            <span class="formula-col-header">账面净额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.netBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="交易金额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" :model-value="row.transactionAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'transactionAmount', val ?? 0)" />
          <span v-else>{{ fmtAmount(row.transactionAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="定价依据" min-width="200">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.pricingBasis" size="small" @change="(val: string) => handleUpdate($index, 'pricingBasis', val)" />
          <span v-else>{{ row.pricingBasis || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="公允性评价" min-width="120" align="center">
        <template #default="{ row, $index }">
          <el-select v-if="!isReadonly" :model-value="row.fairnessLevel" size="small" style="width:100%" @change="(val: string) => handleUpdate($index, 'fairnessLevel', val)">
            <el-option label="公允" value="公允" />
            <el-option label="基本公允" value="基本公允" />
            <el-option label="不公允" value="不公允" />
            <el-option label="待评估" value="待评估" />
          </el-select>
          <el-tag v-else :type="getFairnessTagType(row.fairnessLevel)" size="small">
            {{ row.fairnessLevel }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
        <template #default="{ $index }">
          <el-button type="danger" text size="small" @click="handleRemoveRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计区 ═══ -->
    <div class="summary-bar">
      <span>关联交易合计：<strong>{{ fmtAmount(totalTransactionAmount) }}</strong></span>
      <span>净额合计：<strong>{{ fmtAmount(totalNetBalance) }}</strong></span>
      <span>共 <strong>{{ computedRows.length }}</strong> 笔关联方交易</span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>识别所有关联方长期应付款/融资租赁安排</li>
        <li>评估定价依据是否公允（利率、期限、条件）</li>
        <li>如存在"不公允"项需在审计报告中考虑披露影响</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L5TabRelatedParty — L5-6 关联方及交易检查
 * Requirements: 5.1
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { useL5FormData } from '../../composables/useL5FormData'
import {
  useL5RelatedParty,
  type L5RelatedPartyRow,
  type L5FairnessLevel,
} from '../../composables/useL5RelatedParty'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

// ─── FormData + Composable ──────────────────────────────────────────────────

const formData = useL5FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const relatedPartyRows = ref<L5RelatedPartyRow[]>([])

const {
  computedRows,
  totalTransactionAmount,
  totalNetBalance,
  unfairCount,
  pendingCount,
  addRow,
  removeRow,
  updateRow,
} = useL5RelatedParty(formData, relatedPartyRows)

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddRow() { addRow() }
function handleRemoveRow(index: number) { removeRow(index) }
function handleUpdate(index: number, field: keyof L5RelatedPartyRow, value: string | number) {
  updateRow(index, field, value)
}
function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l5-related-party-${section}`,
      prompt: `请基于长期应付款底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog?.() }

function getFairnessTagType(level: L5FairnessLevel): string {
  switch (level) {
    case '公允': return 'success'
    case '基本公允': return 'info'
    case '不公允': return 'danger'
    case '待评估': return 'warning'
    default: return 'info'
  }
}

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l5-tab-related-party { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.summary-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l5-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
