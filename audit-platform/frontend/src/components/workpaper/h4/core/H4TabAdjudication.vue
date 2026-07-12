<template>
  <div class="h4-tab-adjudication">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>科目1605工程物资（借方/资产类）：期末余额 = 期初 + 借方发生(增加) - 贷方发生(减少)；审定数 = 未审数 + AJE + RJE。三段结构：原值 - 减值准备 = 净值。</p>
    </div>

    <!-- Section 1: 原值（Original Cost） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一、原值（Original Cost）</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('original')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H4-1-original')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="originalDisplayRows" border stripe size="small" class="adj-table"
        :row-class-name="rowClassName">
        <el-table-column prop="name" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.isSubtotal }">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.beginBalance"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'beginBalance', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方发生(增加)" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.debitAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'debitAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方发生(减少)" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.creditAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'creditAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末 = 期初 + 借方 - 贷方">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.unadjusted"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'unadjusted', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.aje"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'aje', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.rje"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'rje', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定 = 未审 + AJE + RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="45" v-if="!props.isReadonly">
          <template #default="{ row }">
            <el-button v-if="!row.isSubtotal" size="small" type="danger" link
              @click="handleDeleteRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="add-row-bar" v-if="!props.isReadonly">
        <el-button size="small" @click="handleAddRow('original')">+ 新增原值分类</el-button>
      </div>
    </el-card>

    <!-- Section 2: 减值准备（Impairment） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、减值准备（Impairment）</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('impairment')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H4-1-impairment')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="impairmentDisplayRows" border stripe size="small" class="adj-table"
        :row-class-name="rowClassName">
        <el-table-column prop="name" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.isSubtotal }">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.beginBalance"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'beginBalance', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方发生(增加)" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.debitAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'debitAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方发生(减少)" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.creditAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'creditAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末 = 期初 + 借方 - 贷方">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.unadjusted"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'unadjusted', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.aje"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'aje', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.rje"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'rje', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定 = 未审 + AJE + RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="45" v-if="!props.isReadonly">
          <template #default="{ row }">
            <el-button v-if="!row.isSubtotal" size="small" type="danger" link
              @click="handleDeleteRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="add-row-bar" v-if="!props.isReadonly">
        <el-button size="small" @click="handleAddRow('impairment')">+ 新增减值分类</el-button>
      </div>
    </el-card>

    <!-- Section 3: 净值（Net Value = 原值 - 减值） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>三、净值（Net Value = 原值 - 减值准备）</span>
        </div>
      </template>
      <el-table :data="[netTotalRow]" border size="small" class="adj-table net-table">
        <el-table-column prop="name" label="项目" min-width="140" fixed>
          <template #default><span class="subtotal-label">工程物资净值</span></template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default>
            <span class="formula-cell" title="原值期初 - 减值期初">{{ fmtAmt(state.netTotal.value.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方发生(增加)" min-width="130" align="right">
          <template #default>
            <span class="formula-cell">{{ fmtAmt(state.netTotal.value.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方发生(减少)" min-width="130" align="right">
          <template #default>
            <span class="formula-cell">{{ fmtAmt(state.netTotal.value.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="120" align="right">
          <template #default>
            <span class="formula-cell" title="原值期末 - 减值期末">{{ fmtAmt(state.netTotal.value.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default>
            <span class="formula-cell">{{ fmtAmt(state.netTotal.value.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default>
            <span class="formula-cell">{{ fmtAmt(state.netTotal.value.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default>
            <span class="formula-cell">{{ fmtAmt(state.netTotal.value.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="120" align="right">
          <template #default>
            <span class="formula-cell" title="净值审定 = 原值审定 - 减值审定">{{ fmtAmt(state.netTotal.value.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- TB取数 + 差异核对 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>TB取数核对（科目1605）</span></div>
      </template>
      <div class="tb-compare">
        <div class="tb-row">
          <span class="tb-label">审定合计(净值)：</span>
          <span class="tb-value">{{ fmtAmt(state.adjudicatedTotal.value) }}</span>
        </div>
        <div class="tb-row">
          <span class="tb-label">TB未审数(1605)：</span>
          <span class="tb-value">{{ fmtAmt(state.tbUnadjusted.value) }}</span>
        </div>
        <div class="tb-row">
          <span class="tb-label">TB审定数(1605)：</span>
          <span class="tb-value">{{ fmtAmt(state.tbAudited.value) }}</span>
        </div>
        <div class="tb-row">
          <span class="tb-label">差异(审定-TB审定)：</span>
          <span class="tb-value" :class="{ 'error-amount': !state.isTbMatch.value }">
            {{ fmtAmt(state.tbDiff.value) }}
          </span>
        </div>
      </div>
    </el-card>

    <!-- 跨sheet校验警告 -->
    <el-alert v-if="crossSheetWarning" type="warning" :closable="false" show-icon
      style="margin-bottom: 12px">
      <template #title>{{ crossSheetWarning }}</template>
    </el-alert>

    <!-- 三角勾稽校验 -->
    <el-alert v-if="triangleErrors.length > 0" type="error" :closable="false" show-icon
      style="margin-bottom: 12px">
      <template #title>三角勾稽异常：{{ triangleErrors.length }}项差额非零</template>
      <template #default>
        <div v-for="e in triangleErrors" :key="e.name" class="triangle-err">
          {{ e.name }}：差额 {{ fmtAmt(e.diff) }}
        </div>
      </template>
    </el-alert>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-note')">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
            <el-button size="small" circle @click="openReview('H4-1-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计说明..." :disabled="props.isReadonly"
        @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计结论</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-conclusion')">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
            <el-button size="small" circle @click="openReview('H4-1-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写审计结论..." :disabled="props.isReadonly"
        @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <!-- 操作按钮 -->
    <div class="action-bar" v-if="!props.isReadonly">
      <el-button type="primary" @click="handlePublish" :loading="publishing">
        确认审定 → 回写TB(1605)
      </el-button>
    </div>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>科目1605工程物资（资产类/借方）：期末=期初+借方-贷方</li>
        <li>三段结构：原值分类行 → 减值准备分类行 → 净值=原值-减值</li>
        <li>审定数=未审数+AJE+RJE；合计行/净值行自动汇总不可编辑</li>
        <li>审定数与H4-2明细合计交叉验证（不一致显示黄色警告）</li>
        <li>"确认审定"将回写trial_balance并发布EventBus事件通知附注/报表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabAdjudication.vue — H4-1 审定表（51公式）
 *
 * 三段结构：原值(5分类+小计) / 减值准备(5分类+小计) / 净值合计
 * 列：项目 | 期初余额 | 本期借方发生(增加) | 本期贷方发生(减少) | 期末余额 | 未审数 | AJE | RJE | 审定数
 * 公式：期末=期初+借-贷 | 审定=未审+AJE+RJE | 合计=SUM | 三角勾稽=0
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 4.2
 * Requirements: 2.1-2.10
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH4Adjudication, type H4AdjudicationRow } from '../../composables/useH4Adjudication'
import { useH4CrossSheet } from '../../composables/useH4CrossSheet'
import { calcTriangleReconciliation } from '../../composables/useH4FormulaEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const publishing = ref(false)

// ─── Composable: useH4Adjudication ──────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses)

// TB 取数种子（科目1605）：主入口 provide 的 render 策略 tb_values，供审定表只读核对
const tbValues = inject<Ref<Record<string, number>>>('h4TbValues', ref({}))
const tbData = computed(() => ({
  unadjusted1605: Number(tbValues.value?.eng_mat_1605_unadjusted) || 0,
  audited1605: Number(tbValues.value?.eng_mat_1605_audited) || 0,
}))

const state = useH4Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  tbData,
  onSave: (itemId: string, value: any) => {
    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
  },
  onWritebackTB: async (amount: number) => {
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: { wpCode: 'H4', accountCode: '1605', auditedAmount: amount },
    }))
  },
})

// ─── Composable: useH4CrossSheet ────────────────────────────────────────────
const crossSheet = useH4CrossSheet(allResponsesRef as any)

// ─── Display Rows ────────────────────────────────────────────────────────────

interface DisplayRow extends H4AdjudicationRow {
  isSubtotal: boolean
}

const originalDisplayRows = computed<DisplayRow[]>(() => {
  const rows: DisplayRow[] = state.originalRows.value.map(r => ({ ...r, isSubtotal: false }))
  const sub = state.originalSubtotal.value
  rows.push({
    rowId: 'original-subtotal',
    name: '原值小计',
    section: 'original',
    beginBalance: sub.beginBalance,
    debitAmount: sub.debitAmount,
    creditAmount: sub.creditAmount,
    endBalance: sub.endBalance,
    unadjusted: sub.unadjusted,
    aje: sub.aje,
    rje: sub.rje,
    audited: sub.audited,
    isSubtotal: true,
  })
  return rows
})

const impairmentDisplayRows = computed<DisplayRow[]>(() => {
  const rows: DisplayRow[] = state.impairmentRows.value.map(r => ({ ...r, isSubtotal: false }))
  const sub = state.impairmentSubtotal.value
  rows.push({
    rowId: 'impairment-subtotal',
    name: '减值小计',
    section: 'impairment',
    beginBalance: sub.beginBalance,
    debitAmount: sub.debitAmount,
    creditAmount: sub.creditAmount,
    endBalance: sub.endBalance,
    unadjusted: sub.unadjusted,
    aje: sub.aje,
    rje: sub.rje,
    audited: sub.audited,
    isSubtotal: true,
  })
  return rows
})

const netTotalRow = computed(() => ({
  rowId: 'net-total',
  name: '工程物资净值',
  section: 'net' as const,
  ...state.netTotal.value,
  isSubtotal: true,
}))

// ─── 三角勾稽校验 ────────────────────────────────────────────────────────────
const triangleErrors = computed(() => {
  const errors: { name: string; diff: number }[] = []
  for (const row of state.originalRows.value) {
    const diff = calcTriangleReconciliation(row.beginBalance, row.debitAmount, row.creditAmount, row.endBalance)
    if (Math.abs(diff) > 0.01) {
      errors.push({ name: `原值-${row.name}`, diff })
    }
  }
  for (const row of state.impairmentRows.value) {
    const diff = calcTriangleReconciliation(row.beginBalance, row.debitAmount, row.creditAmount, row.endBalance)
    if (Math.abs(diff) > 0.01) {
      errors.push({ name: `减值-${row.name}`, diff })
    }
  }
  return errors
})

// ─── 跨sheet校验警告 ─────────────────────────────────────────────────────────
const crossSheetWarning = computed<string>(() => {
  const check = crossSheet.adjudicationVsDetail.value
  if (!check.isMatch && (check.diff !== 0 || state.adjudicatedTotal.value !== 0)) {
    const sign = check.diff > 0 ? '+' : ''
    return `审定数≠H4-2合计，差额：${sign}${fmtAmt(check.diff)}元`
  }
  return ''
})

// ─── Actions ─────────────────────────────────────────────────────────────────

function rowClassName({ row }: { row: DisplayRow }) {
  if (row.isSubtotal) return 'subtotal-row'
  return ''
}

function onCellChange(rowId: string, field: string, value: number | null) {
  state.updateCell(rowId, field, value ?? 0)
}

async function handleAddRow(section: 'original' | 'impairment') {
  try {
    const label = section === 'original' ? '原值物资分类' : '减值物资分类'
    const { value } = await ElMessageBox.prompt(`请输入${label}名称`, `新增${label}`, {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) state.addRow(value, section)
  } catch { /* cancelled */ }
}

function handleDeleteRow(rowId: string) {
  state.deleteRow(rowId)
}

async function handlePublish() {
  publishing.value = true
  try {
    await state.publishAdjudicated()
  } finally {
    publishing.value = false
  }
}

function handleAiGenerate(section: string) {
  console.log('[H4-1] AI generate:', section)
}

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  if (val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h4-tab-adjudication { padding: 16px; font-size: var(--wp-font-size, 13px); }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.6;
}

.block-card { margin-bottom: 16px; }
.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.adj-table { font-size: var(--wp-font-size, 13px); }
.amt-input { width: 100%; }
.amt-cell { display: block; text-align: right; }

.formula-cell {
  display: block; text-align: right;
  border-bottom: 1px dashed #67c23a;
  cursor: help;
  color: var(--el-text-color-primary);
}

.subtotal-label { font-weight: 700; }
:deep(.subtotal-row) { background-color: #f0f9eb !important; font-weight: 600; }
.net-table :deep(tr) { background-color: #ecf5ff !important; font-weight: 700; }

.add-row-bar { margin-top: 8px; }

.tb-compare { display: flex; flex-wrap: wrap; gap: 16px; padding: 8px 0; }
.tb-row { display: flex; align-items: center; gap: 8px; }
.tb-label { color: var(--el-text-color-secondary); min-width: 130px; }
.tb-value { font-weight: 500; font-variant-numeric: tabular-nums; }

.error-amount { color: #f56c6c; font-weight: 600; }
.triangle-err { font-size: 12px; margin-top: 4px; color: #f56c6c; }
.audit-note-card { margin-bottom: 12px; }
.action-bar { display: flex; justify-content: flex-end; margin-bottom: 12px; padding-top: 8px; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
