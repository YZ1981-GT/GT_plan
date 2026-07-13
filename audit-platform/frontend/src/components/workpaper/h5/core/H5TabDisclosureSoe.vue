<template>
  <div class="h5-tab-disclosure-soe">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：复核油气资产附注披露(国企版)的完整性与准确性，满足国资监管补充披露要求（产能利用率、安全生产投入、环保投入）。" class="objective-alert" />

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>附注披露 — 国企版</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-disc-S')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-alert v-if="!hasAdjudicatedData" type="info" :closable="false" show-icon>
        尚未接收审定数据。请先完成H5-1审定表并确认审定。
      </el-alert>

      <!-- 国企版：简化嵌套表格 -->
      <div class="note-section">
        <h4>油气资产</h4>
        <el-table :data="summaryRows" border size="small" class="note-table">
          <el-table-column prop="item" label="项目" min-width="140" />
          <el-table-column prop="endBalance" label="期末余额" min-width="110" align="right">
            <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.endBalance) }}</span></template>
          </el-table-column>
          <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
            <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span></template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 国企特殊披露 -->
      <div class="note-section">
        <h4>补充披露（国资监管要求）</h4>
        <el-input v-model="soeDisclosureText" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }"
          placeholder="国企特殊披露内容（产能利用率、储量变动、安全生产投入等）..." :disabled="isReadonly" />
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNoteText" :autosize="{ minRows: 5 }"
        placeholder="填写附注披露审计说明..." :disabled="isReadonly" @change="savePolishNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusionText" :autosize="{ minRows: 3 }"
        placeholder="填写附注披露审计结论..." :disabled="isReadonly" @change="savePolishConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>国企版附注格式较上市公司版简化</li>
        <li>需额外披露：产能利用率、安全生产投入、环保投入</li>
        <li>国资委监管报表可能要求额外的分类信息</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, onUnmounted, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useH5FormData } from '../../composables/useH5FormData'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

// 审计说明/结论（component-local，沿用 useH5FormData 契约，conclusion:null）
const NOTE_KEY = 'H5-disc-S-audit-note'
const CONCLUSION_KEY = 'H5-disc-S-audit-conclusion'
const auditNoteText = ref('')
const auditConclusionText = ref('')
function savePolishNote(val: string): void {
  if (props.isReadonly) return
  auditNoteText.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void formData.saveResponse(NOTE_KEY, val)
}
function savePolishConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusionText.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void formData.saveResponse(CONCLUSION_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusionText.value = c.remark
})

const soeDisclosureText = ref('')
const adjudicatedData = ref<{ costAudited: number; depletionAudited: number; impairmentAudited: number; netValue: number } | null>(null)

const hasAdjudicatedData = computed(() => adjudicatedData.value !== null || props.allResponses.has('H5-1-cost-rows'))

// Subscribe to EventBus 'substantive:adjudicated' for real-time refresh
function onAdjudicated(payload: any) {
  if (!payload) return
  if (payload.accountCode === '1631' || payload.accountCode === '1632' || payload.wp_code === 'H5' || payload.account_codes?.includes('1631')) {
    adjudicatedData.value = {
      costAudited: payload.cost_audited ?? payload.auditedAmount ?? 0,
      depletionAudited: payload.depletion_audited ?? 0,
      impairmentAudited: payload.impairment_audited ?? 0,
      netValue: payload.net_value ?? 0,
    }
  }
}

onMounted(() => {
  eventBus.on('substantive:adjudicated', onAdjudicated)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', onAdjudicated)
})

const summaryRows = computed(() => {
  const data = adjudicatedData.value
  if (data) {
    return [
      { item: '油气资产原值', endBalance: data.costAudited, beginBalance: 0 },
      { item: '减：累计折耗', endBalance: data.depletionAudited, beginBalance: 0 },
      { item: '减：减值准备', endBalance: data.impairmentAudited, beginBalance: 0 },
      { item: '油气资产净值', endBalance: data.netValue, beginBalance: 0 },
    ]
  }
  // Fallback from allResponses
  let costTotal = 0
  let deplTotal = 0
  const costRaw = props.allResponses.get('H5-1-cost-rows')
  const deplRaw = props.allResponses.get('H5-1-depletion-rows')
  if (costRaw?.remark) { try { costTotal = JSON.parse(costRaw.remark).reduce((s: number, r: any) => s + (Number(r.audited) || 0), 0) } catch {} }
  if (deplRaw?.remark) { try { deplTotal = JSON.parse(deplRaw.remark).reduce((s: number, r: any) => s + (Number(r.audited) || 0), 0) } catch {} }
  return [
    { item: '油气资产原值', endBalance: costTotal, beginBalance: 0 },
    { item: '减：累计折耗', endBalance: deplTotal, beginBalance: 0 },
    { item: '减：减值准备', endBalance: 0, beginBalance: 0 },
    { item: '油气资产净值', endBalance: costTotal - deplTotal, beginBalance: 0 },
  ]
})

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-disclosure-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.note-section { margin-top: 20px; }
.note-section h4 { font-size: 14px; margin-bottom: 8px; }
.note-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
