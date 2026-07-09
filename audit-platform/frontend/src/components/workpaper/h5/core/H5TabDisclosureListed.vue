<template>
  <div class="h5-tab-disclosure-listed">
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>附注披露 — 上市公司版</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate"><el-icon><MagicStick /></el-icon> AI生成</el-button>
            <el-button size="small" type="default" link @click="handleReview('H5-disc-L')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <!-- EventBus subscribe: 从H5-1审定数自动拉取 -->
      <el-alert v-if="!hasAdjudicatedData" type="info" :closable="false" show-icon>
        尚未接收审定数据。请先完成H5-1审定表并确认审定。
      </el-alert>

      <!-- 嵌套附注表：原值变动 -->
      <div class="note-section">
        <h4>（一）油气资产原值</h4>
        <el-table :data="costNoteRows" border size="small" class="note-table">
          <el-table-column prop="item" label="项目" min-width="120" />
          <el-table-column prop="beginBalance" label="期初余额" min-width="100" align="right">
            <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span></template>
          </el-table-column>
          <el-table-column prop="increase" label="本期增加" min-width="100" align="right">
            <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.increase) }}</span></template>
          </el-table-column>
          <el-table-column prop="decrease" label="本期减少" min-width="100" align="right">
            <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.decrease) }}</span></template>
          </el-table-column>
          <el-table-column prop="endBalance" label="期末余额" min-width="100" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.endBalance) }}</span></template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 嵌套附注表：累计折耗 -->
      <div class="note-section">
        <h4>（二）累计折耗</h4>
        <el-table :data="depletionNoteRows" border size="small" class="note-table">
          <el-table-column prop="item" label="项目" min-width="120" />
          <el-table-column prop="beginBalance" label="期初余额" min-width="100" align="right">
            <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span></template>
          </el-table-column>
          <el-table-column prop="provision" label="本期计提" min-width="100" align="right">
            <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.provision) }}</span></template>
          </el-table-column>
          <el-table-column prop="endBalance" label="期末余额" min-width="100" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.endBalance) }}</span></template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 文字性披露 -->
      <div class="note-section">
        <h4>（三）补充披露</h4>
        <el-input v-model="disclosureText" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }"
          placeholder="补充披露内容（折耗方法、储量信息等）..." :disabled="isReadonly" />
      </div>
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>附注数据从H5-1审定表通过EventBus subscribe自动获取</li>
        <li>上市公司需按CAS27披露：储量信息、折耗方法、弃置费用</li>
        <li>嵌套表格格式需符合年报附注标准</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, onUnmounted } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const disclosureText = ref('')
const adjudicatedData = ref<{ costAudited: number; depletionAudited: number; netValue: number } | null>(null)

const hasAdjudicatedData = computed(() => adjudicatedData.value !== null || props.allResponses.has('H5-1-cost-rows'))

// Subscribe to EventBus 'substantive:adjudicated' for real-time refresh
function onAdjudicated(payload: any) {
  if (!payload) return
  // Only react to H5 adjudication events (account 1631/1632)
  if (payload.accountCode === '1631' || payload.accountCode === '1632' || payload.wp_code === 'H5' || payload.account_codes?.includes('1631')) {
    adjudicatedData.value = {
      costAudited: payload.cost_audited ?? payload.auditedAmount ?? 0,
      depletionAudited: payload.depletion_audited ?? 0,
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

// 从allResponses中获取审定数据构建附注表格
const costNoteRows = computed(() => {
  if (adjudicatedData.value) {
    return [{ item: '油气资产合计', beginBalance: 0, increase: 0, decrease: 0, endBalance: adjudicatedData.value.costAudited }]
  }
  // Fallback: 尝试从 allResponses 解析
  const costRowsRaw = props.allResponses.get('H5-1-cost-rows')
  if (costRowsRaw?.remark) {
    try {
      const rows = JSON.parse(costRowsRaw.remark)
      const total = Array.isArray(rows) ? rows.reduce((s: number, r: any) => s + (Number(r.audited) || 0), 0) : 0
      return [{ item: '油气资产合计', beginBalance: 0, increase: 0, decrease: 0, endBalance: total }]
    } catch { /* ignore */ }
  }
  return [{ item: '油气资产合计', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 }]
})

const depletionNoteRows = computed(() => {
  if (adjudicatedData.value) {
    return [{ item: '累计折耗合计', beginBalance: 0, provision: 0, endBalance: adjudicatedData.value.depletionAudited }]
  }
  const deplRowsRaw = props.allResponses.get('H5-1-depletion-rows')
  if (deplRowsRaw?.remark) {
    try {
      const rows = JSON.parse(deplRowsRaw.remark)
      const total = Array.isArray(rows) ? rows.reduce((s: number, r: any) => s + (Number(r.audited) || 0), 0) : 0
      return [{ item: '累计折耗合计', beginBalance: 0, provision: 0, endBalance: total }]
    } catch { /* ignore */ }
  }
  return [{ item: '累计折耗合计', beginBalance: 0, provision: 0, endBalance: 0 }]
})

function handleAiGenerate() {}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-disclosure-listed { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.note-section { margin-top: 20px; }
.note-section h4 { font-size: 14px; margin-bottom: 8px; }
.note-table { font-size: 13px; margin-bottom: 12px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
