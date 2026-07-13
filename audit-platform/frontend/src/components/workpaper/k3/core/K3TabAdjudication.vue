<template>
  <div class="k3-tab-adjudication">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>K3-1审定表审定其他应付款(2241贷方/<strong>负债类</strong>)。负债类期末=期初+贷方-借方（与资产类方向相反）。增加=贷方发生，减少=借方发生。审计重点为<strong>完整性认定</strong>（负债易少计）。</p>
    </div>

    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性（负债重点）：</b>所有应当记录的其他应付款均已记录，不存在少计负债；</li>
        <li><b>存在：</b>记录的其他应付款是存在的，且已记录在恰当的账户中；</li>
        <li><b>义务：</b>记录的其他应付款是被审计单位应当履行的偿还义务；</li>
        <li><b>计价和分摊：</b>其他应付款以恰当金额包括在报表中，相关计价或分摊调整已恰当记录；</li>
        <li><b>列报与披露：</b>已按企业会计准则规定作出恰当列报。</li>
      </ol>
    </el-alert>

    <!-- 一、按性质分类 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>一、按性质分类</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-nature')">
              <el-icon><MagicStick /></el-icon> AI说明
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('K3-1-nature')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-table
        :data="natureDisplayRows"
        border stripe size="small" class="adj-table"
        :max-height="tableMaxHeight"
      >
        <el-table-column prop="label" label="项目" min-width="130" fixed />
        <el-table-column label="期初" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.rowKey !== 'subtotal' && !isReadonly">
              <el-input-number
                :model-value="row.begin" :controls="false" size="small" class="amount-input"
                @change="onFieldChange('nature', row.rowKey, 'begin', $event)" />
            </template>
            <span v-else class="amount-cell">{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.rowKey !== 'subtotal' && !isReadonly">
              <el-input-number
                :model-value="row.credit" :controls="false" size="small" class="amount-input"
                @change="onFieldChange('nature', row.rowKey, 'credit', $event)" />
            </template>
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.rowKey !== 'subtotal' && !isReadonly">
              <el-input-number
                :model-value="row.debit" :controls="false" size="small" class="amount-input"
                @change="onFieldChange('nature', row.rowKey, 'debit', $event)" />
            </template>
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="负债类: 期末=期初+贷方-借方">{{ fmtAmt(row.end) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.rowKey !== 'subtotal' && !isReadonly">
              <el-input-number
                :model-value="row.unadjusted" :controls="false" size="small" class="amount-input"
                @change="onFieldChange('nature', row.rowKey, 'unadj', $event)" />
            </template>
            <span v-else class="amount-cell tb-auto">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.aje" :controls="false" size="small" class="amount-input"
              @change="onFieldChange('nature', row.rowKey, 'aje', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.rje" :controls="false" size="small" class="amount-input"
              @change="onFieldChange('nature', row.rowKey, 'rje', $event)" />
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
            <el-input v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.remark" size="small" placeholder=""
              @change="onRemarkChange('nature', row.rowKey, $event)" />
            <span v-else class="amount-cell">{{ row.remark || '' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 二、按账龄分类 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>二、按账龄分类</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-aging')">
              <el-icon><MagicStick /></el-icon> AI说明
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('K3-1-aging')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-table
        :data="agingDisplayRows"
        border stripe size="small" class="adj-table"
        :max-height="tableMaxHeight"
      >
        <el-table-column prop="label" label="项目" min-width="130" fixed />
        <el-table-column label="期初" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.rowKey !== 'subtotal' && !isReadonly">
              <el-input-number
                :model-value="row.begin" :controls="false" size="small" class="amount-input"
                @change="onFieldChange('aging', row.rowKey, 'begin', $event)" />
            </template>
            <span v-else class="amount-cell">{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.rowKey !== 'subtotal' && !isReadonly">
              <el-input-number
                :model-value="row.credit" :controls="false" size="small" class="amount-input"
                @change="onFieldChange('aging', row.rowKey, 'credit', $event)" />
            </template>
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.rowKey !== 'subtotal' && !isReadonly">
              <el-input-number
                :model-value="row.debit" :controls="false" size="small" class="amount-input"
                @change="onFieldChange('aging', row.rowKey, 'debit', $event)" />
            </template>
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="负债类: 期末=期初+贷方-借方">{{ fmtAmt(row.end) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row.rowKey !== 'subtotal' && !isReadonly">
              <el-input-number
                :model-value="row.unadjusted" :controls="false" size="small" class="amount-input"
                @change="onFieldChange('aging', row.rowKey, 'unadj', $event)" />
            </template>
            <span v-else class="amount-cell tb-auto">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.aje" :controls="false" size="small" class="amount-input"
              @change="onFieldChange('aging', row.rowKey, 'aje', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.rje" :controls="false" size="small" class="amount-input"
              @change="onFieldChange('aging', row.rowKey, 'rje', $event)" />
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
            <el-input v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.remark" size="small" placeholder=""
              @change="onRemarkChange('aging', row.rowKey, $event)" />
            <span v-else class="amount-cell">{{ row.remark || '' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 三角勾稽校验 -->
    <el-card shadow="never" class="block-card reconciliation-card">
      <template #header>
        <div class="section-title">
          <span>三角勾稽校验</span>
        </div>
      </template>
      <div class="reconciliation-result">
        <el-tag :type="reconciliation.isBalanced ? 'success' : 'danger'" size="large">
          {{ reconciliation.isBalanced ? '✓ 勾稽平衡' : '✗ 勾稽不平' }}
        </el-tag>
        <span v-if="!reconciliation.isBalanced" class="error-amount" style="margin-left:12px;">
          差额: {{ fmtAmt(reconciliation.diff) }}
        </span>
        <el-tag type="info" size="small" style="margin-left:12px;">
          性质合计审定: {{ fmtAmt(natureSubtotal.audited) }}
        </el-tag>
        <el-tag type="info" size="small" style="margin-left:8px;">
          账龄合计审定: {{ fmtAmt(agingSubtotal.audited) }}
        </el-tag>
      </div>
      <!-- 性质vs账龄交叉验证 -->
      <div v-if="crossDiff !== 0" class="cross-validation-warning">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          :title="`按性质合计(${fmtAmt(natureSubtotal.audited)}) ≠ 按账龄合计(${fmtAmt(agingSubtotal.audited)})，差额 ${fmtAmt(crossDiff)}`"
        />
      </div>
    </el-card>

    <!-- 审计说明+完整性认定 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('adj-conclusion')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计结论..." :disabled="isReadonly" @blur="saveConclusion" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>完整性认定说明</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('adj-completeness')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="completenessNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="负债类审计重点为完整性（负债易少计），请说明已执行的完整性程序（含反向截止测试）..."
        :disabled="isReadonly" @blur="saveCompleteness" />
    </el-card>

    <!-- 操作按钮 -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button type="primary" @click="handleWritebackTB" :loading="publishing">
        确认审定 → 回写TB（2241其他应付款）
      </el-button>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>其他应付款(2241)：<strong>负债类贷方科目</strong>，期末=期初+贷方-借方</li>
        <li>增加在贷方、减少在借方（与资产类方向相反）</li>
        <li>审定数=未审数+AJE+RJE，未审数从TB自动取入(只读)</li>
        <li>三角勾稽：期末=期初+增加(贷)-减少(借)，差额须为0</li>
        <li>按性质分类合计应等于按账龄分类合计（交叉验证）</li>
        <li>审计重点为<strong>完整性认定</strong>（负债易少计）→ 反向截止（期后偿付倒查未入账负债）</li>
        <li>"确认审定"将回写trial_balance(2241)并发布EventBus事件通知附注刷新</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K3TabAdjudication.vue — K3-1 审定表（负债类2241，50公式）
 * Spec: .kiro/specs/k3-other-payables/ | Task: 4.2
 * Requirements: 2.1-2.7, 7.3
 *
 * 双区块：按性质分类(保证金/往来款/代收代付/其他+合计) + 按账龄分类(1年内/1-2年/2-3年/3年以上+合计)
 * 列：项目|期初|本期贷方|本期借方|期末(公式)|未审|AJE|RJE|审定(公式)|变动率(公式)|备注
 * 公式列：虚线下划线+cursor:help+tooltip显示来源
 * 三角勾稽不平→红色高亮
 * TB回写按钮(2241其他应付款→writebackTB)
 * 底部审计说明el-card(审计结论textarea+完整性认定说明)
 * 复核对话按钮(inject openReviewDialog)
 * AI辅助按钮(section标题行右侧)
 * 编制提示details折叠底部
 * useK3Adjudication composable消费
 * useK3FormData消费
 *
 * 科目：2241 其他应付款（**贷方/负债类**）
 * ⚠️ 负债类！期末=期初+贷方-借方（与资产类相反）
 */
import { ref, computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useK3Adjudication, type K3AdjRow } from '../../composables/useK3Adjudication'
import { useK3FormData } from '../../composables/useK3FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted2241: number; audited2241: number }
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const tbDataRef = computed(() => props.tbData)

const {
  byNatureRows,
  byAgingRows,
  natureSubtotal,
  agingSubtotal,
  auditConclusion,
  completenessNote,
  reconciliation,
  getAuditedTotal,
} = useK3Adjudication({
  allResponses: allResponsesRef as any,
  tbData: tbDataRef as any,
  saveResponse: handleSaveItem,
})

const { writebackTB, debouncedSave } = useK3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetPrefix: 'K3-1',
})

const tableMaxHeight = 480
const publishing = ref(false)
const isReadonly = computed(() => props.isReadonly)

// ─── Display rows (with subtotal appended) ───────────────────────────────────

const natureDisplayRows = computed((): K3AdjRow[] => {
  return [...byNatureRows.value, { ...natureSubtotal.value, label: '合计' }]
})

const agingDisplayRows = computed((): K3AdjRow[] => {
  return [...byAgingRows.value, { ...agingSubtotal.value, label: '合计' }]
})

// ─── 交叉验证: 按性质合计 vs 按账龄合计 ─────────────────────────────────────

const crossDiff = computed(() => {
  return Math.round((natureSubtotal.value.audited - agingSubtotal.value.audited) * 100) / 100
})

// ─── 字段变化处理 ────────────────────────────────────────────────────────────

function onFieldChange(
  prefix: 'nature' | 'aging',
  rowKey: string,
  field: string,
  value: number | undefined,
) {
  const v = value ?? 0
  const itemId = `K3-1-${prefix}-${rowKey}-${field}`
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: String(v) })
  emit('save', itemId, { remark: String(v) })
}

function onRemarkChange(prefix: 'nature' | 'aging', rowKey: string, value: string) {
  const itemId = `K3-1-${prefix}-${rowKey}-remark`
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: value })
  emit('save', itemId, { remark: value })
}

// ─── 保存审计说明 ────────────────────────────────────────────────────────────

function handleSaveItem(itemId: string, data: any): void {
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: typeof data === 'string' ? data : data?.remark ?? '' })
  emit('save', itemId, data)
}

function saveConclusion() {
  const itemId = 'K3-1-audit-conclusion'
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: auditConclusion.value })
  debouncedSave(itemId, { remark: auditConclusion.value })
}

function saveCompleteness() {
  const itemId = 'K3-1-completeness-note'
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: completenessNote.value })
  debouncedSave(itemId, { remark: completenessNote.value })
}

// ─── TB回写 ─────────────────────────────────────────────────────────────────

async function handleWritebackTB() {
  publishing.value = true
  try {
    const auditedTotal = getAuditedTotal()
    await writebackTB(auditedTotal)
    ElMessage.success('审定数已回写TB（2241其他应付款）')
  } catch {
    ElMessage.error('TB回写失败')
  } finally {
    publishing.value = false
  }
}

// ─── AI / 复核 ──────────────────────────────────────────────────────────────

function handleAiGenerate(section: string) {
  console.log('AI generate:', section)
}

function handleReview(id: string) {
  openReviewDialog(id)
}

// ─── 金额格式化 ─────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k3-tab-adjudication {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* 方法论上下文 */
.methodology-context {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

/* 区块卡片 */
.block-card {
  margin-bottom: 16px;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.title-actions {
  display: flex;
  gap: 8px;
}

/* 表格 */
.adj-table {
  font-size: var(--wp-font-size, 13px);
}

.amount-cell {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.amount-input {
  width: 100%;
}

.amount-input :deep(.el-input__inner) {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* 公式列虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

.tb-auto {
  color: var(--el-text-color-secondary);
  font-style: italic;
}

/* 三角勾稽 */
.reconciliation-card {
  margin-bottom: 16px;
}

.reconciliation-result {
  display: flex;
  align-items: center;
  padding: 8px 0;
  flex-wrap: wrap;
  gap: 4px;
}

.error-amount {
  color: var(--el-color-danger);
  font-weight: 600;
}

.cross-validation-warning {
  margin-top: 12px;
}

/* 审计说明 */
.note-card {
  margin-bottom: 12px;
}

/* 操作按钮 */
.action-bar {
  margin-top: 16px;
  text-align: right;
}

/* 编制提示 */
.compile-hint {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}
</style>
