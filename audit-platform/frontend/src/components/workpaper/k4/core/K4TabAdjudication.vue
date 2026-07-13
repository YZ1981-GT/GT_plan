<template>
  <div class="k4-tab-adjudication">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>K4-1审定表审定其他流动负债(2245贷方/<strong>负债类</strong>)。负债类期末=期初+贷方-借方（与资产类方向相反）。增加=贷方发生，减少=借方发生。审计重点为<strong>完整性认定</strong>（负债易少计）。</p>
    </div>

    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性（负债重点）：</b>所有应当记录的其他流动负债均已记录，不存在少计负债；</li>
        <li><b>存在：</b>记录的其他流动负债是存在的，且已记录在恰当的账户中；</li>
        <li><b>义务：</b>记录的其他流动负债是被审计单位应当履行的偿还义务；</li>
        <li><b>计价和分摊：</b>其他流动负债以恰当金额包括在报表中，相关计价或分摊调整已恰当记录；</li>
        <li><b>列报与披露：</b>已按企业会计准则规定作出恰当列报。</li>
      </ol>
    </el-alert>

    <!-- ═══ 审定表主表 ═══ -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>K4-1 其他流动负债审定表</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-main')">
              <el-icon><MagicStick /></el-icon> AI说明
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('K4-1')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-table
        :data="displayRows"
        border
        stripe
        size="small"
        class="adj-table"
        :max-height="520"
        :row-class-name="getRowClassName"
      >
        <el-table-column prop="label" label="项目" min-width="160" fixed />
        <el-table-column label="期初" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row.rowKey !== 'subtotal' && !isReadonly">
              <el-input-number
                :model-value="row.begin"
                :controls="false"
                size="small"
                class="amount-input"
                @change="onFieldChange(row.rowKey, 'begin', $event)"
              />
            </template>
            <span v-else class="amount-cell">{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row.rowKey !== 'subtotal' && !isReadonly">
              <el-input-number
                :model-value="row.credit"
                :controls="false"
                size="small"
                class="amount-input"
                @change="onFieldChange(row.rowKey, 'credit', $event)"
              />
            </template>
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row.rowKey !== 'subtotal' && !isReadonly">
              <el-input-number
                :model-value="row.debit"
                :controls="false"
                size="small"
                class="amount-input"
                @change="onFieldChange(row.rowKey, 'debit', $event)"
              />
            </template>
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="负债类: 期末=期初+贷方-借方" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.end) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row.rowKey !== 'subtotal' && !isReadonly">
              <el-input-number
                :model-value="row.unadjusted"
                :controls="false"
                size="small"
                class="amount-input"
                @change="onFieldChange(row.rowKey, 'unadj', $event)"
              />
            </template>
            <span v-else class="amount-cell tb-auto">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.aje"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onFieldChange(row.rowKey, 'aje', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.rje"
              :controls="false"
              size="small"
              class="amount-input"
              @change="onFieldChange(row.rowKey, 'rje', $event)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="审定=未审+AJE+RJE" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.audited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="90" align="right">
          <template #default="{ row }">
            <el-tooltip content="变动率=(审定-上期审定)/上期审定" placement="top">
              <span class="formula-cell">
                {{ row.changeRate != null ? (row.changeRate * 100).toFixed(1) + '%' : '-' }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.remark"
              size="small"
              placeholder=""
              @change="onRemarkChange(row.rowKey, $event)"
            />
            <span v-else class="amount-cell">{{ row.remark || '' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 三角勾稽校验 ═══ -->
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
          合计审定: {{ fmtAmt(subtotalRow.audited) }}
        </el-tag>
      </div>
    </el-card>

    <!-- ═══ 审计说明+结论 ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('adj-conclusion')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计结论..."
        :disabled="isReadonly"
        @blur="saveConclusion"
      />
    </el-card>

    <!-- ═══ 操作按钮 ═══ -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button type="primary" @click="handleWritebackTB" :loading="publishing">
        确认审定 → 回写TB（2245其他流动负债）
      </el-button>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>其他流动负债(2245)：<strong>负债类贷方科目</strong>，期末=期初+贷方-借方</li>
        <li>增加在贷方、减少在借方（与资产类方向相反）</li>
        <li>审定数=未审数+AJE+RJE，未审数从TB自动取入(只读)</li>
        <li>三角勾稽：期末=期初+增加(贷)-减少(借)，差额须为0</li>
        <li>审计重点为<strong>完整性认定</strong>（负债易少计）→ 反向截止（期后偿付倒查未入账负债）</li>
        <li>"确认审定"将回写trial_balance(2245)并发布EventBus事件通知附注刷新</li>
        <li>明细表（K4-2）合计应与本表审定数一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K4TabAdjudication.vue — K4-1 审定表（负债类2245，72公式）
 * Spec: .kiro/specs/k4-other-current-liabilities/ | Task: 4.2
 * Requirements: 2.1-2.7
 *
 * 单区块审定表（21行项目）
 * 列：项目|期初|本期贷方|本期借方|期末(公式)|未审|AJE|RJE|审定(公式)|变动率(公式)|备注
 * 公式列：虚线下划线+cursor:help+tooltip显示来源
 * 三角勾稽不平→红色高亮
 * TB回写按钮(2245其他流动负债→writebackTB)
 * 底部审计说明el-card(审计结论textarea)
 * 复核对话按钮(inject openReviewDialog)
 * AI辅助按钮(section标题行右侧)
 * 编制提示details折叠底部
 * Consumes: useK4Adjudication + useK4FormData
 *
 * 科目：2245 其他流动负债（**贷方/负债类**）
 * ⚠️ 负债类！期末=期初+贷方-借方（与资产类相反）
 */
import { ref, computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useK4Adjudication, type K4AdjRow } from '../../composables/useK4Adjudication'
import { useK4FormData } from '../../composables/useK4FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted2245: number; audited2245: number }
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
  rows,
  subtotalRow,
  auditConclusion,
  reconciliation,
  getAuditedTotal,
} = useK4Adjudication({
  allResponses: allResponsesRef as any,
  tbData: tbDataRef as any,
  saveResponse: handleSaveItem,
})

const { writebackTB, debouncedSave } = useK4FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetPrefix: 'K4-1',
})

const publishing = ref(false)
const isReadonly = computed(() => props.isReadonly)

// ─── Display rows (data + subtotal appended) ─────────────────────────────────

const displayRows = computed((): K4AdjRow[] => {
  return [...rows.value, { ...subtotalRow.value, label: '合计' }]
})

// ─── 行样式：合计行加粗 / 三角勾稽不平红色 ──────────────────────────────────

function getRowClassName({ row }: { row: K4AdjRow }): string {
  if (row.rowKey === 'subtotal') return 'subtotal-row'
  return ''
}

// ─── 字段变化处理 ────────────────────────────────────────────────────────────

function onFieldChange(rowKey: string, field: string, value: number | undefined) {
  const v = value ?? 0
  const itemId = `K4-1-${rowKey}-${field}`
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: String(v) })
  emit('save', itemId, { remark: String(v) })
}

function onRemarkChange(rowKey: string, value: string) {
  const itemId = `K4-1-${rowKey}-remark`
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: value })
  emit('save', itemId, { remark: value })
}

// ─── 保存逻辑 ────────────────────────────────────────────────────────────────

function handleSaveItem(itemId: string, data: any): void {
  props.allResponses.set(itemId, {
    item_id: itemId,
    conclusion: null,
    remark: typeof data === 'string' ? data : data?.remark ?? '',
  })
  emit('save', itemId, data)
}

function saveConclusion() {
  const itemId = 'K4-1-audit-conclusion'
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: auditConclusion.value })
  debouncedSave(itemId, { remark: auditConclusion.value })
}

// ─── TB回写 ─────────────────────────────────────────────────────────────────

async function handleWritebackTB() {
  publishing.value = true
  try {
    const auditedTotal = getAuditedTotal()
    await writebackTB(auditedTotal)
    ElMessage.success('审定数已回写TB（2245其他流动负债）')
  } catch {
    ElMessage.error('TB回写失败')
  } finally {
    publishing.value = false
  }
}

// ─── AI / 复核 ──────────────────────────────────────────────────────────────

function handleAiGenerate(section: string) {
  console.log('[K4-1] AI generate:', section)
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
.k4-tab-adjudication {
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

/* 合计行加粗 */
:deep(.subtotal-row) {
  font-weight: 600;
  background-color: #f5f7fa !important;
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
