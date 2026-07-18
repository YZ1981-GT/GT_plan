<template>
  <div class="h7-tab-disclosure-soe">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：按国有企业财务报表附注要求披露生产性生物资产的账面变动、计量政策与经营管理信息，
        数据与 H7-1 审定表勾稽一致。
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H7-1" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">国有企业版</el-tag>
      <el-tag size="small" :type="hasAdjudicatedData ? 'success' : 'warning'">{{ hasAdjudicatedData ? '已接收审定数' : '待审定' }}</el-tag>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>附注披露 — 国有企业版</span>
          <div class="title-actions">
            <el-button size="small" link @click="handleReview('H7-disc-soe')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-alert v-if="!hasAdjudicatedData" type="info" :closable="false" show-icon class="hint-alert">
        尚未接收审定数据。请先完成 H7-1 审定表并确认审定，本表将自动同步账面数据。
      </el-alert>

      <!-- （一）生产性生物资产账面变动 -->
      <div class="note-section">
        <h4>（一）生产性生物资产账面变动</h4>
        <el-table :data="movementRows" border size="small" class="note-table">
          <el-table-column prop="item" label="项目" min-width="150" />
          <el-table-column label="原值" min-width="130" align="right">
            <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.cost) }}</span></template>
          </el-table-column>
          <el-table-column label="累计折旧" min-width="130" align="right">
            <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.dep) }}</span></template>
          </el-table-column>
          <el-table-column label="减值准备" min-width="130" align="right">
            <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.imp) }}</span></template>
          </el-table-column>
          <el-table-column label="账面价值" min-width="130" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula-cell" title="账面价值=原值-累计折旧-减值准备">{{ fmtAmt(row.cost - row.dep - row.imp) }}</span></template>
          </el-table-column>
        </el-table>
      </div>

      <!-- （二）计量政策 -->
      <div class="note-section">
        <h4>（二）计量政策与折旧方法</h4>
        <el-input v-model="policyText" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="披露计量模式、折旧方法、折旧年限与残值率等会计政策..." :disabled="isReadonly" @blur="persist('H7-disc-soe-policy', policyText)" />
      </div>

      <!-- （三）经营管理与国资监管信息 -->
      <div class="note-section">
        <h4>（三）经营管理与国资监管信息</h4>
        <el-input v-model="disclosureText" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }" placeholder="补充披露内容（国有资产保值增值、重大处置审批、自然灾害损失、抵押担保等）..." :disabled="isReadonly" @blur="persist('H7-disc-soe-text', disclosureText)" />
      </div>
    </el-card>

    
    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 5 生物资产准则）</summary>
      <ul>
        <li>附注账面数据从 H7-1 审定表通过 EventBus(substantive:adjudicated) 自动同步。</li>
        <li>国有企业须按 CAS 5 及财政部报表格式披露分类原值/累计折旧/减值准备/账面价值。</li>
        <li>披露计量模式、折旧方法（直线法）、折旧年限、残值率等会计政策。</li>
        <li>关注国有资产保值增值、重大资产处置审批程序合规性。</li>
        <li>披露抵押担保、自然灾害损失、重大期后事项等特殊情况。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H7TabDisclosureSoe.vue — H7 附注披露（国有企业）
 *
 * 账面变动表(EventBus + allResponses 解析) + 政策/国资监管文字披露。
 * 无专属 disclosure composable → H5 附注同族范式(eventBus 订阅 + allResponses JSON 解析)，
 * 持久化走 api.put(remark)。
 *
 * Spec: .kiro/specs/h7-biological-assets/  Requirements: 附注披露·国企
 */
import { ref, computed, onMounted, onUnmounted, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const localResponses = ref<Map<string, any>>(new Map(props.allResponses ?? []))
const policyText = ref('')
const disclosureText = ref('')
const adjudicatedAmount = ref<number | null>(null)

function num(v: any): number { const n = Number(v); return Number.isFinite(n) ? n : 0 }

function getStr(itemId: string): string {
  const item = localResponses.value.get(itemId)
  return (item?.remark ?? item?.conclusion ?? '') as string
}

const hasAdjudicatedData = computed(() => adjudicatedAmount.value != null || localResponses.value.has('H7-1-cost-orig') || localResponses.value.has('H7-1-fair'))

const movementRows = computed(() => {
  const origRaw = getStr('H7-1-cost-orig')
  const depRaw = getStr('H7-1-cost-dep')
  const impRaw = getStr('H7-1-cost-imp')
  if (origRaw) {
    try {
      const orig = JSON.parse(origRaw)
      const dep = depRaw ? JSON.parse(depRaw) : {}
      const imp = impRaw ? JSON.parse(impRaw) : {}
      const cost = num(orig.unadjusted) + num(orig.aje) + num(orig.rje)
      const depEnd = num(dep.begin) + num(dep.credit) - num(dep.debit) + num(dep.aje)
      const impEnd = num(imp.begin) + num(imp.credit) - num(imp.debit) + num(imp.aje)
      return [{ item: '生产性生物资产（成本模式）', cost, dep: depEnd, imp: impEnd }]
    } catch { /* ignore */ }
  }
  const fairRaw = getStr('H7-1-fair')
  if (fairRaw) {
    try {
      const fair = JSON.parse(fairRaw)
      const cost = num(fair.unadjusted) + num(fair.aje)
      return [{ item: '生产性生物资产（公允价值模式）', cost, dep: 0, imp: 0 }]
    } catch { /* ignore */ }
  }
  return [{ item: '生产性生物资产', cost: adjudicatedAmount.value ?? 0, dep: 0, imp: 0 }]
})

function onAdjudicated(payload: any) {
  if (!payload) return
  if (payload.accountCode === '1621' || payload.componentType === 'h7-biological-assets') {
    adjudicatedAmount.value = num(payload.auditedAmount)
  }
}

async function loadOwn() {
  try {
    const list: any[] = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const m = new Map(localResponses.value)
    for (const r of (Array.isArray(list) ? list : [])) {
      if (r.item_id?.startsWith('H7-')) m.set(r.item_id, { item_id: r.item_id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
    }
    localResponses.value = m
  } catch { /* empty */ }
  policyText.value = getStr('H7-disc-soe-policy')
  disclosureText.value = getStr('H7-disc-soe-text')
}

async function persist(itemId: string, value: any) {
  const remark = value == null ? null : (typeof value === 'string' ? value : JSON.stringify(value))
  localResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark })
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: null, remark }],
    })
  } catch { ElMessage.error('保存失败，请稍后重试') }
}

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(() => {
  void loadOwn()
  eventBus.on('substantive:adjudicated', onAdjudicated)
})
onUnmounted(() => {
  eventBus.off('substantive:adjudicated', onAdjudicated)
})
</script>

<style scoped>
.h7-tab-disclosure-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.hint-alert { margin-bottom: 12px; }
.note-section { margin-top: 20px; }
.note-section h4 { font-size: 14px; margin-bottom: 8px; }
.note-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.note-table :deep(.auto-calc-col) { background: var(--el-fill-color-lighter); }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
