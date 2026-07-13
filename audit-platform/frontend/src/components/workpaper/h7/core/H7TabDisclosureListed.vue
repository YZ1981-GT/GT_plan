<template>
  <div class="h7-tab-disclosure-listed">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：按上市公司年报附注要求披露生产性生物资产的账面变动、计量模式、折旧政策与公允价值信息，
        数据与 H7-1 审定表勾稽一致。
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H7-1" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">上市公司版</el-tag>
      <el-tag size="small" :type="hasAdjudicatedData ? 'success' : 'warning'">{{ hasAdjudicatedData ? '已接收审定数' : '待审定' }}</el-tag>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>附注披露 — 上市公司版</span>
          <div class="title-actions">
            <el-button size="small" link @click="handleReview('H7-disc-listed')">💬 复核</el-button>
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

      <!-- （二）计量模式与折旧政策 -->
      <div class="note-section">
        <h4>（二）计量模式与折旧政策</h4>
        <el-input v-model="policyText" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="披露生产性生物资产的计量模式（成本/公允价值）、折旧方法、折旧年限与残值率..." :disabled="isReadonly" @blur="persist('H7-disc-listed-policy', policyText)" />
      </div>

      <!-- （三）补充披露 -->
      <div class="note-section">
        <h4>（三）补充披露</h4>
        <el-input v-model="disclosureText" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }" placeholder="补充披露内容（重大自然灾害、期后事项、公允价值层级与关键参数、抵押担保情况等）..." :disabled="isReadonly" @blur="persist('H7-disc-listed-text', disclosureText)" />
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly" placeholder="记录附注披露项的编制依据、与审定表勾稽核对情况。" @blur="persist('H7-disc-listed-note', auditNote)" />
    </el-card>
    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="附注披露完整、准确，与审定数一致，未见异常。" @blur="persist('H7-disc-listed-conclusion', auditConclusion)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 5 生物资产准则）</summary>
      <ul>
        <li>附注账面数据从 H7-1 审定表通过 EventBus(substantive:adjudicated) 自动同步。</li>
        <li>上市公司须按 CAS 5 及年报格式披露：分类原值/累计折旧/减值准备/账面价值。</li>
        <li>披露计量模式、折旧方法（直线法）、折旧年限、残值率等会计政策。</li>
        <li>公允价值模式须披露层级(L1/L2/L3)、估值技术与关键参数。</li>
        <li>披露抵押担保、自然灾害损失、重大期后事项等特殊情况。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H7TabDisclosureListed.vue — H7 附注披露（上市公司）
 *
 * 账面变动表(EventBus substantive:adjudicated + allResponses 解析) + 政策/补充文字披露。
 * 无专属 disclosure composable → 采用 H5 附注同族范式(eventBus 订阅 + allResponses JSON 解析)，
 * 持久化走 api.put(remark)。
 *
 * Spec: .kiro/specs/h7-biological-assets/  Requirements: 附注披露·上市
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
const auditNote = ref('')
const auditConclusion = ref('')
const adjudicatedAmount = ref<number | null>(null)

function num(v: any): number { const n = Number(v); return Number.isFinite(n) ? n : 0 }

function getStr(itemId: string): string {
  const item = localResponses.value.get(itemId)
  return (item?.remark ?? item?.conclusion ?? '') as string
}

const hasAdjudicatedData = computed(() => adjudicatedAmount.value != null || localResponses.value.has('H7-1-cost-orig') || localResponses.value.has('H7-1-fair'))

// 从审定表(成本/公允)解析账面数据
const movementRows = computed(() => {
  // 成本模式
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
  // 公允价值模式
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
  policyText.value = getStr('H7-disc-listed-policy')
  disclosureText.value = getStr('H7-disc-listed-text')
  auditNote.value = getStr('H7-disc-listed-note')
  auditConclusion.value = getStr('H7-disc-listed-conclusion')
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
.h7-tab-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.block-card { margin-bottom: 16px; }
.note-card { margin-bottom: 16px; }
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
