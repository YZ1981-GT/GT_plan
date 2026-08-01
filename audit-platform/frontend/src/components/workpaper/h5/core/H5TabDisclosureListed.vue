<template>
  <div class="h5-tab-disclosure-listed">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：复核油气资产附注披露(上市公司版)的完整性与准确性，确保符合 CAS27 披露要求（储量信息、折耗方法、弃置费用）。" class="objective-alert" />

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>附注披露 — 上市公司版</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="openReview('disclosure')">💬 复核</el-button>
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
        <WpNoteTextArea
          v-model="disclosureText"
          label="（三）补充披露"
          testid-prefix="h5-listed-disclosure"
          :min-rows="4"
          :max-rows="12"
          :disabled="isReadonly"
          placeholder="补充披露内容（折耗方法、储量信息等）..."
          :ai-loading="aiLoadingSection === 'disclosure'"
          @change="persistText"
          @ai="runAi('disclosure')"
          @review="openReview('disclosure')"
        />
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
import { ref, computed, inject, onMounted, onUnmounted, toRef, watch } from 'vue'
import { eventBus } from '@/utils/eventBus'
import WpNoteTextArea from '../../shared/disclosure/WpNoteTextArea.vue'
import { useHCycleDisclosureAi } from '../../composables/useHCycleDisclosureAi'
import { H_CYCLE_NOTE_AI_SECTIONS } from '../../composables/hCycleNoteAiSections'
import { H5_NOTE_SECTION } from '../../composables/h5NoteSectionMap'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()

const disclosureText = ref('')

// 🔴 原实现里 `disclosureText` **完全没有持久化路径**（无 `saveResponse`、无 watch）
// → 用户填的补充披露刷新即丢，AI 生成的文本同样存不下来。此处补齐 hydrate + persist。
const H5_LISTED_TEXT_ITEM = 'H5-disc-listed-text'
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

function readPersistedText(): string {
  const raw = props.allResponses.get(H5_LISTED_TEXT_ITEM)
  return String(raw?.remark ?? '')
}

function persistText(): void {
  if (props.isReadonly) return
  saveResponse(H5_LISTED_TEXT_ITEM, { remark: disclosureText.value || '' })
}

watch(
  () => props.allResponses,
  () => {
    const persisted = readPersistedText()
    // 只在本地为空时回填，避免宿主异步刷新覆盖用户刚录入的内容
    if (persisted && !disclosureText.value) disclosureText.value = persisted
  },
  { immediate: true, deep: true },
)

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

// ─── 披露说明 AI 辅助 + 复核（原本无 AI 按钮） ───────────────────────────────
const { aiLoadingSection: aiLoadingRef, runAi, openReview } = useHCycleDisclosureAi({
  wpCode: 'H5',
  variant: 'listed',
  wpId: () => props.wpId,
  isReadonly: () => props.isReadonly,
  noteSectionId: H5_NOTE_SECTION.listed ?? '五、油气资产',
  labels: H_CYCLE_NOTE_AI_SECTIONS.H5.listed,
  fields: {
    disclosure: {
      get: () => disclosureText.value || '',
      set: (v) => { disclosureText.value = v; persistText() },
    },
  },
})
const aiLoadingSection = computed(() => aiLoadingRef.value)

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

// 复核入口统一走 `useHCycleDisclosureAi().openReview`（平台 `openReviewDialog` 的
// 规范签名是**对象入参**，见 `composables/useReviewDialogProvider.ts`；
// 原实现 `openReviewDialog('H5-disc-L')` 传字符串 → 弹窗拿不到 sectionId）。
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.note-section { margin-top: 20px; }
.note-section h4 { font-size: 14px; margin-bottom: 8px; }
.note-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
