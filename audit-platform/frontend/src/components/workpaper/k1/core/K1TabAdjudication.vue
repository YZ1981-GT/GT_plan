<template>
  <div class="k1-tab-adjudication">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>K1-1审定表审定其他应收款(1221借方/资产类)与坏账准备(备抵类)，计算账面净值。资产类期末=期初+借方-贷方；备抵类期末=期初+贷方-借方；净值=应收-坏账。</p>
    </div>

    <!-- 一、其他应收款（1221） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>一、其他应收款（1221）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-receivable')">
              <el-icon><MagicStick /></el-icon> AI说明
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('K1-1-receivable')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-table
        :data="receivableDisplayRows"
        border stripe size="small" class="adj-table"
        :max-height="tableMaxHeight"
      >
        <el-table-column prop="label" label="项目" min-width="130" fixed />
        <el-table-column label="期初" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="资产类: 期末=期初+借方-贷方">{{ fmtAmt(row.end) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell tb-auto">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.aje" :controls="false" size="small" class="amount-input"
              @change="onAjeChange('receivable', row.rowKey, $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.rje" :controls="false" size="small" class="amount-input"
              @change="onRjeChange('receivable', row.rowKey, $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定=未审+AJE+RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="变动率=(审定-上期审定)/上期审定">
              {{ row.changeRate != null ? (row.changeRate * 100).toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <span class="amount-cell">{{ row.remark || '' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 二、坏账准备 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>二、坏账准备</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-baddebt')">
              <el-icon><MagicStick /></el-icon> AI说明
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('K1-1-baddebt')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-table
        :data="badDebtDisplayRows"
        border stripe size="small" class="adj-table"
        :max-height="tableMaxHeight"
      >
        <el-table-column prop="label" label="项目" min-width="130" fixed />
        <el-table-column label="期初" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="备抵类: 期末=期初+贷方-借方">{{ fmtAmt(row.end) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amount-cell tb-auto">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.aje" :controls="false" size="small" class="amount-input"
              @change="onAjeChange('baddebt', row.rowKey, $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.rje" :controls="false" size="small" class="amount-input"
              @change="onRjeChange('baddebt', row.rowKey, $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定=未审+AJE+RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="变动率=(审定-上期审定)/上期审定">
              {{ row.changeRate != null ? (row.changeRate * 100).toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <span class="amount-cell">{{ row.remark || '' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 三、账面净值 + 三角勾稽 -->
    <el-card shadow="never" class="block-card reconciliation-card">
      <template #header>
        <div class="section-title">
          <span>三、账面净值</span>
        </div>
      </template>
      <el-table :data="netValueDisplayRows" border stripe size="small" class="adj-table" :max-height="280">
        <el-table-column prop="label" label="项目" min-width="130" fixed />
        <el-table-column label="期初" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="净值=应收-坏账">{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="净值=应收期末-坏账期末">{{ fmtAmt(row.end) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="净值=应收未审-坏账未审">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="净值=应收审定-坏账审定">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="变动率">
              {{ row.changeRate != null ? (row.changeRate * 100).toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <!-- 三角勾稽校验 -->
      <el-divider content-position="left">三角勾稽校验</el-divider>
      <div class="reconciliation-result">
        <el-tag :type="reconciliation.isBalanced ? 'success' : 'danger'" size="large">
          {{ reconciliation.isBalanced ? '✓ 勾稽平衡' : '✗ 勾稽不平' }}
        </el-tag>
        <span v-if="!reconciliation.isBalanced" class="error-amount" style="margin-left:12px;">
          差额: {{ fmtAmt(reconciliation.diff) }}
        </span>
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
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计说明..." :disabled="isReadonly" @blur="saveNote" />
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
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写审计结论..." :disabled="isReadonly" @blur="saveConclusion" />
    </el-card>

    <!-- 操作按钮 -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button type="primary" @click="handleWritebackTB" :loading="publishing">
        确认审定 → 回写TB
      </el-button>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>其他应收款(1221)：资产类，期末=期初+借方-贷方</li>
        <li>坏账准备：备抵类，期末=期初+贷方-借方</li>
        <li>账面净值=其他应收款-坏账准备</li>
        <li>三角勾稽：期末=期初+增加-减少，差额须为0</li>
        <li>审定数=未审数+AJE+RJE，未审数从TB自动取入(只读)</li>
        <li>"确认审定"将回写trial_balance(1221+坏账准备)并发布EventBus事件</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabAdjudication.vue — K1-1 审定表
 * Spec: .kiro/specs/k1-other-receivables/ | Task: 4.2
 * Requirements: 2.1-2.10
 * 双区块(1221+坏账准备)+净值+47公式+三角勾稽+TB回写+89行虚拟滚动
 */
import { ref, computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useK1Adjudication, type K1AdjRow } from '../../composables/useK1Adjudication'
import { useK1FormData } from '../../composables/useK1FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted1221: number; audited1221: number; unadjustedBadDebt: number; auditedBadDebt: number }
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)

const {
  adjudicationSections,
  reconciliation,
  auditNote,
  auditConclusion,
} = useK1Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
})

const { writebackTB, debouncedSave } = useK1FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const tableMaxHeight = 520
const publishing = ref(false)

const receivableSection = computed(() => adjudicationSections.value[0])
const badDebtSection = computed(() => adjudicationSections.value[1])
const netValueSection = computed(() => adjudicationSections.value[2])

const receivableDisplayRows = computed((): K1AdjRow[] => {
  const sec = receivableSection.value
  if (!sec) return []
  return [...sec.rows, { ...sec.subtotalRow, label: '合计' }]
})
const badDebtDisplayRows = computed((): K1AdjRow[] => {
  const sec = badDebtSection.value
  if (!sec) return []
  return [...sec.rows, { ...sec.subtotalRow, label: '合计' }]
})
const netValueDisplayRows = computed((): K1AdjRow[] => {
  const sec = netValueSection.value
  if (!sec) return []
  return [...sec.rows, { ...sec.subtotalRow, label: '合计' }]
})

function onAjeChange(block: 'receivable' | 'baddebt', rowKey: string, value: number | undefined) {
  const v = value ?? 0
  const itemId = `K1-1-${block}-${rowKey}-aje`
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: String(v) })
  emit('save', itemId, { remark: String(v) })
}
function onRjeChange(block: 'receivable' | 'baddebt', rowKey: string, value: number | undefined) {
  const v = value ?? 0
  const itemId = `K1-1-${block}-${rowKey}-rje`
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: String(v) })
  emit('save', itemId, { remark: String(v) })
}
function saveNote() {
  const itemId = 'K1-1-audit-note'
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: auditNote.value })
  debouncedSave(itemId, { remark: auditNote.value })
}
function saveConclusion() {
  const itemId = 'K1-1-audit-conclusion'
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: auditConclusion.value })
  debouncedSave(itemId, { remark: auditConclusion.value })
}
async function handleWritebackTB() {
  publishing.value = true
  try {
    const recSec = receivableSection.value
    const bdSec = badDebtSection.value
    if (!recSec || !bdSec) return
    await writebackTB(recSec.subtotalRow.audited, bdSec.subtotalRow.audited)
    ElMessage.success('审定数已回写TB（1221+坏账准备）')
  } catch { ElMessage.error('TB回写失败') }
  finally { publishing.value = false }
}
function handleAiGenerate(section: string) { console.log('AI generate:', section) }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k1-tab-adjudication { padding: 16px; font-size: 13px; }
.methodology-context {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.adj-table { font-size: 13px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.tb-auto { color: var(--el-text-color-secondary); font-style: italic; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.reconciliation-card { margin-bottom: 16px; }
.reconciliation-result { display: flex; align-items: center; padding: 8px 0; }
.note-card { margin-bottom: 12px; }
.action-bar { margin-top: 16px; text-align: right; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
