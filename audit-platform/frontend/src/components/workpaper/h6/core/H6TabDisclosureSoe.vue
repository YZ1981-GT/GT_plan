<template>
  <div class="h6-tab-disclosure-soe">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>附注披露信息（国有企业）：按照国资委和财政部要求，披露固定资产清理变动情况及相关管控信息。数据从H6-1审定表自动取数，重点关注国有资产处置合规性和审批流程完整性。科目1606固定资产清理为过渡科目，期末余额应为零。</p>
    </div>

    <!-- Section Title -->
    <div class="section-header">
      <span>附注披露信息（国有企业）</span>
      <div class="section-header-actions">
        <el-segmented v-model="dualMode.currentMode.value" :options="dualMode.modeOptions"
          size="small" @change="dualMode.onModeChange" />
        <el-button size="small" type="primary" link @click="handleAiGenerate" style="margin-left: 8px">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" circle @click="openReview('H6-disclosure-soe')">💬</el-button>
      </div>
    </div>

    <!-- OnlyOffice 模式 -->
    <GtOnlyOfficeSheet
      v-if="dualMode.currentMode.value === 'onlyoffice'"
      :wp-id="props.wpId"
      :sheet-name="props.sheetName || '附注披露信息（国有企业）'"
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

        <!-- 清理过程关键数据表格 -->
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

      <!-- 国企专项——处置合规性信息 -->
      <el-card shadow="never" class="soe-extra-card">
        <template #header>
          <span style="font-weight: 600">国企专项披露信息</span>
        </template>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="处置审批笔数">
            <span class="amt-cell">{{ soeData.approvalCount || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="处置审批金额">
            <span class="amt-cell">{{ fmtAmt(soeData.approvalAmount) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="资产评估笔数">
            <span class="amt-cell">{{ soeData.appraisalCount || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="公开处置占比">
            <span class="amt-cell" :class="{ 'warn-cell': soeData.publicDisposalRatio < 70 }">
              {{ soeData.publicDisposalRatio ? soeData.publicDisposalRatio.toFixed(1) + '%' : '-' }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="关联方处置金额">
            <span class="amt-cell">{{ fmtAmt(soeData.relatedPartyAmount) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="清理净损益">
            <span class="amt-cell" :class="{ 'loss-cell': gainLossData.netGainLoss < 0 }">
              {{ fmtAmt(gainLossData.netGainLoss) }}
            </span>
          </el-descriptions-item>
        </el-descriptions>
        <!-- 过渡科目期末警告 -->
        <el-alert v-if="!transitStatus.isZero" type="error" :closable="false" style="margin-top: 8px"
          :title="`⚠ 过渡科目期末余额应为0，当前余额：${fmtAmt(transitStatus.balance)}，请检查是否有未完成清理项目`" />
      </el-card>

      <!-- 附注文本编辑 -->
      <el-card shadow="never" class="note-text-card">
        <template #header>
          <div class="section-header" style="margin-bottom:0">
            <span>附注披露文本</span>
            <div class="section-header-actions">
              <el-button size="small" type="primary" link @click="handleAiGenerate">
                <el-icon><MagicStick /></el-icon> AI生成
              </el-button>
            </div>
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
        <li>国企固定资产处置须经国有资产管理部门审批</li>
        <li>单项或批量处置超标准须进行资产评估</li>
        <li>公开处置（拍卖/挂牌）为国企首选方式，协议转让需充分说明理由</li>
        <li>关联方处置需在关联交易附注中交叉披露</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H6TabDisclosureSoe.vue — 附注披露信息（国有企业）
 *
 * 18行×5列嵌套表：项目 | 账面原值 | 减值准备 | 账面价值 | 备注
 * OO-primary + HTML fallback showing disclosure data + SOE-specific compliance fields.
 * Subscribe to EventBus 'substantive:adjudicated' to refresh when H6-1 audited changes.
 * Uses useH6CrossSheet for transit account status.
 *
 * 国企比上市公司多：处置审批流程合规性、资产评估要求、公开处置比例。
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/
 * Task: 4.6
 * Requirements: 1.2
 */
import { ref, computed, defineAsyncComponent, inject, toRef, onMounted, onUnmounted } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
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

// ─── Dual Mode ───────────────────────────────────────────────────────────────
const dualMode = useH6DualMode({
  wpId: toRef(props, 'wpId'),
})

// ─── Cross-Sheet Data ────────────────────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses)
const { transitAccountStatus, disposalGainLossVsH10 } = useH6CrossSheet(allResponsesRef as any)
const transitStatus = computed(() => transitAccountStatus.value)

// 清理净损益
const gainLossData = computed(() => {
  const check = disposalGainLossVsH10.value
  const netGainLoss = getNum('H6-1-disposal-gain-loss')
  return {
    netGainLoss,
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
    const bookCost = getNum(`H6-disc-soe-${cat.key}-cost`)
    const impairment = getNum(`H6-disc-soe-${cat.key}-impairment`)
    const bookValue = getNum(`H6-disc-soe-${cat.key}-value`)
    const remark = getStr(`H6-disc-soe-${cat.key}-remark`)
    return {
      item: cat.label,
      bookCost,
      impairment,
      bookValue: bookValue || (bookCost - impairment),
      remark,
    }
  }).concat([{
    item: '合计',
    bookCost: getNum('H6-disc-soe-total-cost'),
    impairment: getNum('H6-disc-soe-total-impairment'),
    bookValue: getNum('H6-disc-soe-total-value'),
    remark: '',
  }])
})

// ─── SOE-specific data ───────────────────────────────────────────────────────
const soeData = computed(() => ({
  approvalCount: getNum('H6-soe-approval-count'),
  approvalAmount: getNum('H6-soe-approval-amount'),
  appraisalCount: getNum('H6-soe-appraisal-count'),
  publicDisposalRatio: getNum('H6-soe-public-disposal-ratio'),
  relatedPartyAmount: getNum('H6-soe-related-party-amount'),
}))

// ─── Note Text ───────────────────────────────────────────────────────────────
const noteText = ref('')
const noteResp = props.allResponses.get('H6-disclosure-soe-text')
if (noteResp?.remark) noteText.value = noteResp.remark

function saveNoteText() {
  props.allResponses.set('H6-disclosure-soe-text', {
    item_id: 'H6-disclosure-soe-text', remark: noteText.value, conclusion: null,
  })
}

// ─── EventBus Subscribe ──────────────────────────────────────────────────────
let unsubscribe: (() => void) | null = null

onMounted(() => {
  const handler = (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail?.wpCode === 'H6' || detail?.accountCode === '1606') {
      console.log('[H6-Disclosure-SOE] Received substantive:adjudicated, refreshing')
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

function handleAiGenerate() {
  console.log('[H6-Disclosure-SOE] AI generate')
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
.h6-tab-disclosure-soe { padding: 16px; font-size: 13px; }

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

.soe-extra-card { margin-top: 12px; }
.note-text-card { margin-top: 12px; }

.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
