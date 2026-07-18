<template>
  <div class="h6-tab-disclosure-listed">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实上市公司固定资产清理相关附注披露完整、准确，清理损益与 H6-1 审定表及 H10 处置损益勾稽一致，过渡科目 1606 期末余额清零，披露格式符合 CAS 及监管要求。"
    />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>附注披露信息（上市公司）：按照CAS准则和证监会要求，披露固定资产清理期初/期末余额、本期增减变动及清理损益。数据从H6-1审定表自动取数填入关键字段，过渡科目1606期末余额应为零（清理完毕）。</p>
    </div>

    <!-- Section Title -->
    <div class="section-header">
      <span>附注披露信息（上市公司）</span>
      <div class="section-header-actions">
        <el-segmented v-model="dualMode.currentMode.value" :options="dualMode.modeOptions"
          size="small" @change="dualMode.onModeChange" />
        <el-button size="small" circle @click="openReview('H6-disclosure-listed')" style="margin-left: 8px">💬</el-button>
      </div>
    </div>

    <!-- OnlyOffice 模式 -->
    <GtOnlyOfficeSheet
      v-if="dualMode.currentMode.value === 'onlyoffice'"
      :wp-id="props.wpId"
      :sheet-name="props.sheetName || '附注披露信息（上市公司）'"
      :project-id="props.projectId"
      class="disclosure-oo"
    />

    <!-- HTML 结构化视图 -->
    <div v-else class="disclosure-summary">
      <el-card shadow="never">
        <template #header>
          <div style="display:flex;align-items:center;justify-content:space-between">
            <span style="font-weight: 600">固定资产清理附注关键数据（自动取数）</span>
            <el-tag v-if="transitStatus.isZero" size="small" type="success">已全部结转</el-tag>
            <el-tag v-else size="small" type="danger">存在未结转</el-tag>
          </div>
        </template>

        <!-- 清理过程关键数据 -->
        <el-table :data="disclosureRows" border size="small" style="width: 100%"
          :header-cell-style="{ background: '#f5f7fa', fontSize: '12px' }">
          <el-table-column prop="item" label="项目" width="180" />
          <el-table-column prop="bookCost" label="账面原值" align="right" min-width="120">
            <template #default="{ row }">
              <span class="amt-cell">{{ fmtAmt(row.bookCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="impairment" label="减值准备" align="right" min-width="120">
            <template #default="{ row }">
              <span class="amt-cell">{{ fmtAmt(row.impairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="bookValue" label="账面价值" align="right" min-width="120">
            <template #default="{ row }">
              <span class="amt-cell highlight">{{ fmtAmt(row.bookValue) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="140">
            <template #default="{ row }">
              <span class="remark-cell">{{ row.remark || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 清理损益汇总 -->
      <el-card shadow="never" class="gain-loss-card">
        <template #header>
          <span style="font-weight: 600">清理损益汇总</span>
        </template>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="清理净损益">
            <span class="amt-cell" :class="{ 'loss-cell': gainLossData.netGainLoss < 0 }">
              {{ fmtAmt(gainLossData.netGainLoss) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="H10对应金额">
            <span class="amt-cell">{{ fmtAmt(gainLossData.h10Amount) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="差额">
            <span class="amt-cell" :class="{ 'warn-cell': !gainLossData.isMatch }">
              {{ fmtAmt(gainLossData.diff) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="期末余额（过渡科目）">
            <span class="amt-cell" :class="{ 'warn-cell': !transitStatus.isZero }">
              {{ fmtAmt(transitStatus.balance) }}
            </span>
          </el-descriptions-item>
        </el-descriptions>
        <!-- 过渡科目期末警告 -->
        <el-alert v-if="!transitStatus.isZero" type="error" :closable="false" style="margin-top: 8px"
          :title="`⚠ 过渡科目期末余额应为0，当前余额：${fmtAmt(transitStatus.balance)}，请检查是否有未完成清理项目`" />
        <!-- H10差异警告 -->
        <el-alert v-if="!gainLossData.isMatch" type="warning" :closable="false" style="margin-top: 8px"
          :title="`净损益≠H10资产处置损益，差额：${fmtAmt(gainLossData.diff)}`" />
      </el-card>

      <!-- 附注文本编辑 -->
      <el-card shadow="never" class="note-text-card">
        <template #header>
          <div class="section-header" style="margin-bottom:0">
            <span>附注披露文本</span>
          </div>
        </template>
        <el-input v-model="noteText" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }"
          placeholder="请填写附注披露文本内容..." :disabled="props.isReadonly"
          @blur="saveNoteText" />
      </el-card>
    </div>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>关键数据从H6-1审定表自动取数，H6-1审定完成后自动刷新</li>
        <li>1606固定资产清理为过渡科目，期末余额应为零</li>
        <li>需核对清理净损益与H10资产处置损益是否一致</li>
        <li>上市公司需按年报格式披露清理项目明细及损益</li>
        <li>处置固定资产涉及的税费需在附注中说明</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H6TabDisclosureListed.vue — 附注披露信息（上市公司）
 *
 * 18行×5列嵌套表：项目 | 账面原值 | 减值准备 | 账面价值 | 备注
 * OO-primary + HTML fallback showing disclosure data from H6-1 审定表.
 * Subscribe to EventBus 'substantive:adjudicated' to refresh when H6-1 audited changes.
 * Uses useH6CrossSheet for transit account status and gain/loss vs H10 check.
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/
 * Task: 4.6
 * Requirements: 1.2
 */
import { ref, computed, defineAsyncComponent, inject, toRef, onMounted, onUnmounted } from 'vue'
import { useH6DualMode } from '../../composables/useH6DualMode'
import { useH6CrossSheet } from '../../composables/useH6CrossSheet'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('../../GtOnlyOfficeSheet.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  sheetName?: string
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
// 父入口提供的持久化函数（更新共享 Map + 防抖 PUT checklist-responses）。Bug C 修复：此前仅写内存 Map。
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', (itemId, value) => {
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
})

// ─── Dual Mode ───────────────────────────────────────────────────────────────
const dualMode = useH6DualMode({
  wpId: toRef(props, 'wpId'),
})

// ─── Cross-Sheet Data ────────────────────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses)
const { transitAccountStatus, disposalGainLossVsH10 } = useH6CrossSheet(allResponsesRef as any)
const transitStatus = computed(() => transitAccountStatus.value)

// 清理净损益及H10对比
const gainLossData = computed(() => {
  const check = disposalGainLossVsH10.value
  const netGainLoss = getNum('H6-1-disposal-gain-loss')
  const h10Amount = getNum('H10-disposal-income')
  return {
    netGainLoss,
    h10Amount,
    diff: check.diff,
    isMatch: check.isMatch,
  }
})

// ─── 附注披露表格数据（18行 from H6-1审定表） ─────────────────────────────────
/** 固定资产清理按类别披露 */
const disclosureRows = computed(() => {
  const categories = [
    { key: 'building', label: '房屋及建筑物' },
    { key: 'machinery', label: '机器设备' },
    { key: 'transport', label: '运输设备' },
    { key: 'electronic', label: '电子设备' },
    { key: 'office', label: '办公设备' },
    { key: 'other', label: '其他设备' },
  ]

  return categories.map(cat => {
    const bookCost = getNum(`H6-disc-listed-${cat.key}-cost`)
    const impairment = getNum(`H6-disc-listed-${cat.key}-impairment`)
    const bookValue = getNum(`H6-disc-listed-${cat.key}-value`)
    const remark = getStr(`H6-disc-listed-${cat.key}-remark`)
    return {
      item: cat.label,
      bookCost,
      impairment,
      bookValue: bookValue || (bookCost - impairment),
      remark,
    }
  }).concat([{
    item: '合计',
    bookCost: getNum('H6-disc-listed-total-cost'),
    impairment: getNum('H6-disc-listed-total-impairment'),
    bookValue: getNum('H6-disc-listed-total-value'),
    remark: '',
  }])
})

// ─── Note Text ───────────────────────────────────────────────────────────────
const noteText = ref('')
const noteResp = props.allResponses.get('H6-disclosure-listed-text')
if (noteResp?.remark) noteText.value = noteResp.remark

function saveNoteText() {
  saveResponse('H6-disclosure-listed-text', noteText.value)
}

// ─── EventBus Subscribe ──────────────────────────────────────────────────────
let unsubscribe: (() => void) | null = null

onMounted(() => {
  const handler = (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail?.wpCode === 'H6' || detail?.accountCode === '1606') {
      console.log('[H6-Disclosure-Listed] Received substantive:adjudicated, refreshing')
    }
  }
  window.addEventListener('substantive:adjudicated', handler)
  unsubscribe = () => window.removeEventListener('substantive:adjudicated', handler)
})

onUnmounted(() => {
  unsubscribe?.()
})

// ─── Helpers ─────────────────────────────────────────────────────────────────
function getNum(key: string): number {
  const resp = props.allResponses.get(key)
  const n = Number(resp?.remark)
  return Number.isFinite(n) ? n : 0
}

function getStr(key: string): string {
  const resp = props.allResponses.get(key)
  return resp?.remark ?? ''
}

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────
function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h6-tab-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }

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

.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600; margin-bottom: 12px;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.disclosure-oo { min-height: 400px; margin-bottom: 12px; }

.disclosure-summary { margin-bottom: 12px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.highlight { color: #409eff; font-weight: 600; }
.loss-cell { color: #f56c6c; font-weight: 600; }
.warn-cell { color: #e6a23c; font-weight: 600; }
.remark-cell { color: var(--el-text-color-secondary); font-size: 12px; }

.gain-loss-card { margin-top: 12px; }
.note-text-card { margin-top: 12px; }

.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
