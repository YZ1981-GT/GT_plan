<template>
  <div class="h1-tab-adjudication">
    <!-- 原值区块 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>一、固定资产-原值（科目1601）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-note')">
              <el-icon><MagicStick /></el-icon> AI说明
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-1-cost')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="costDisplayRows" border stripe size="small" class="adj-table" show-summary :summary-method="costSummaryMethod">
        <el-table-column prop="category" label="资产分类" min-width="120" fixed />
        <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.beginBalance" :controls="false" size="small" class="amount-input"
              @change="onCellChange('cost', row.rowId, 'beginBalance', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debit" label="本期借方(增加)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.debit" :controls="false" size="small" class="amount-input"
              @change="onCellChange('cost', row.rowId, 'debit', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="credit" label="本期贷方(减少)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.credit" :controls="false" size="small" class="amount-input"
              @change="onCellChange('cost', row.rowId, 'credit', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末=期初+借方-贷方">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell tb-auto">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.aje" :controls="false" size="small" class="amount-input"
              @change="onCellChange('cost', row.rowId, 'aje', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.rje" :controls="false" size="small" class="amount-input"
              @change="onCellChange('cost', row.rowId, 'rje', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定=未审+AJE+RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 累计折旧区块 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>二、累计折旧（科目1602·备抵）</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H1-1-dep')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="depDisplayRows" border stripe size="small" class="adj-table">
        <el-table-column prop="category" label="资产分类" min-width="120" fixed />
        <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.beginBalance" :controls="false" size="small" class="amount-input"
              @change="onCellChange('dep', row.rowId, 'beginBalance', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debit" label="本期借方(减少)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.debit" :controls="false" size="small" class="amount-input"
              @change="onCellChange('dep', row.rowId, 'debit', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="credit" label="本期贷方(增加)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.credit" :controls="false" size="small" class="amount-input"
              @change="onCellChange('dep', row.rowId, 'credit', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="备抵期末=期初+贷方-借方">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell tb-auto">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.aje" :controls="false" size="small" class="amount-input"
              @change="onCellChange('dep', row.rowId, 'aje', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.rje" :controls="false" size="small" class="amount-input"
              @change="onCellChange('dep', row.rowId, 'rje', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定=未审+AJE+RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 净值 + 三角勾稽 -->
    <el-card shadow="never" class="reconciliation-card">
      <template #header>
        <div class="section-title">
          <span>三、净值与三角勾稽校验</span>
        </div>
      </template>
      <div class="net-value-row">
        <span>固定资产净值 = 原值审定 - 累计折旧审定 = </span>
        <span class="formula-cell" title="净值=原值-折旧-减值">{{ fmtAmt(netValueAudited) }}</span>
      </div>
      <el-divider />
      <el-table :data="reconciliationResults" size="small" border>
        <el-table-column prop="layer" label="校验层" width="120" />
        <el-table-column label="差额" width="150" align="right">
          <template #default="{ row }">
            <span :class="['amount-cell', { 'error-amount': !row.isBalanced }]">
              {{ fmtAmt(row.difference) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.isBalanced ? 'success' : 'danger'" size="small">
              {{ row.isBalanced ? '平衡' : '不平' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <!-- TB差异 -->
      <div class="tb-diff-section" v-if="differenceRows.length">
        <h4>TB差异核对</h4>
        <el-table :data="differenceRows" size="small" border>
          <el-table-column prop="label" label="科目" width="150" />
          <el-table-column prop="audited" label="审定数" align="right" width="130">
            <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.audited) }}</span></template>
          </el-table-column>
          <el-table-column prop="tbAmount" label="TB金额" align="right" width="130">
            <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.tbAmount) }}</span></template>
          </el-table-column>
          <el-table-column prop="difference" label="差异" align="right" width="130">
            <template #default="{ row }">
              <span :class="['amount-cell', { 'error-amount': Math.abs(row.difference) > 0.01 }]">{{ fmtAmt(row.difference) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <!-- 交叉验证H1-2 -->
      <div v-if="crossValidation.hasCostWarning || crossValidation.hasDepWarning" class="cross-warning">
        <el-alert type="warning" :closable="false" show-icon>
          <template #title>
            交叉验证异常：
            <span v-if="crossValidation.hasCostWarning">原值差异 {{ fmtAmt(crossValidation.costDiff) }}</span>
            <span v-if="crossValidation.hasDepWarning"> 折旧差异 {{ fmtAmt(crossValidation.depDiff) }}</span>
          </template>
        </el-alert>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('adj-note')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请填写审计说明..."
        :disabled="isReadonly" @blur="saveNote(auditNote)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('adj-conclusion')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="请填写审计结论..."
        :disabled="isReadonly" @blur="saveConclusion(auditConclusion)" />
    </el-card>

    <!-- 操作按钮 -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button type="primary" @click="handlePublish" :loading="publishing">
        确认审定 → 回写TB
      </el-button>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>原值区块(1601)：资产类，期末=期初+借方-贷方</li>
        <li>折旧区块(1602)：备抵类，期末=期初+贷方-借方</li>
        <li>三角勾稽：期末=期初+增加-减少，两层均须平衡</li>
        <li>审定数=未审数+AJE+RJE，未审数从TB自动取入(只读)</li>
        <li>"确认审定"将回写trial_balance并发布EventBus事件</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH1Adjudication } from '../../composables/useH1Adjudication'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)
const publishing = ref(false)

const {
  costRows,
  depRows,
  auditNote,
  auditConclusion,
  costSubtotal,
  depSubtotal,
  netValueAudited,
  reconciliationResults,
  differenceRows,
  crossValidation,
  updateCell,
  publishAdjudicated,
  saveNote,
  saveConclusion,
} = useH1Adjudication(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
)

const costDisplayRows = computed(() => {
  const rows = [...costRows.value]
  rows.push({ ...costSubtotal.value })
  return rows
})

const depDisplayRows = computed(() => {
  const rows = [...depRows.value]
  rows.push({ ...depSubtotal.value })
  return rows
})

function onCellChange(block: 'cost' | 'dep', rowId: string, field: string, value: number) {
  updateCell(block, rowId, field as any, value ?? 0)
}

function costSummaryMethod(_ctx: any) {
  return [] // handled by subtotal row
}

async function handlePublish() {
  publishing.value = true
  try {
    await publishAdjudicated()
  } finally {
    publishing.value = false
  }
}

function handleAiGenerate(section: string) {
  // AI generate integration - calls backend ai endpoint
  console.log('AI generate:', section)
}

function handleReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-adjudication { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.adj-table { font-size: 13px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.tb-auto { color: var(--el-text-color-secondary); font-style: italic; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.reconciliation-card { margin-bottom: 16px; }
.net-value-row { font-size: 14px; font-weight: 500; padding: 8px 0; }
.tb-diff-section { margin-top: 16px; }
.tb-diff-section h4 { margin-bottom: 8px; font-size: 13px; }
.cross-warning { margin-top: 12px; }
.note-card { margin-bottom: 12px; }
.action-bar { margin-top: 16px; text-align: right; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
