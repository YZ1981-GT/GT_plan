<template>
  <div class="h3-tab-transfer-review">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表审核投资性房地产与自用房地产/在建工程之间的三方向转换（CAS3 第12-18条）。</p>
        <p>2. 成本模式下以账面价值转换；公允价值模式下自用→投资差额计入其他综合收益(公允&gt;账面)或当期损益(公允&lt;账面)，投资→自用以转换日公允价值入账。</p>
        <p>3. 每笔转换须满足「转出方金额 = 转入方金额」验证（✓/✗）；转换日为用途实际改变日。</p>
        <p>4. 转换金额通过 EventBus 联动 H1 固定资产、H2 在建工程。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实投资性房地产转换的时点、金额与会计处理恰当性，验证成本/公允价值模式下转换差额处理与转出/转入平衡。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-6" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ selfToInvestRows.length + investToSelfRows.length + cipToInvestRows.length }} 项</el-tag>
    </div>

    <!-- 方法论上下文 -->
    <div class="method-context">
      <div class="context-bar">
        <strong>CAS3 第12-15条 转换准则摘要：</strong>投资性房地产与自用房地产/存货之间转换，转换日为用途实际改变日。
        公允模式下自用→投资差额计入其他综合收益(公允>账面)或当期损益(公允&lt;账面)；投资→自用以转换日公允价值作为入账价值。
      </div>
    </div>

    <!-- 三方向分区 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(A) 自用 → 投资性房地产</span>
          <span class="action-btns">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('selfToInvest')">+ 新增</el-button>
            <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H1-1 审定表')">→ H1固定资产</el-tag>
          </span>
        </div>
      </template>
      <el-table :data="selfToInvestRows" border size="small" class="audit-table">
        <el-table-column prop="assetName" label="资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-model="row.assetName" size="small" :disabled="isReadonly" @change="onRowChange('selfToInvest', row)" />
          </template>
        </el-table-column>
        <el-table-column prop="transferDate" label="转换日" width="120">
          <template #default="{ row }">
            <el-input v-model="row.transferDate" size="small" :disabled="isReadonly" @change="onRowChange('selfToInvest', row)" />
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面价值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.bookValue" size="small" :disabled="isReadonly" @change="onRowChange('selfToInvest', row)" />
          </template>
        </el-table-column>
        <el-table-column prop="fairValue" label="转换日公允" min-width="110" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.fairValue" size="small" :disabled="isReadonly" @change="onRowChange('selfToInvest', row)" />
          </template>
        </el-table-column>
        <el-table-column label="差额" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'text-danger': row.fairValue - row.bookValue < 0 }" title="公允-账面">
              {{ fmtNum(row.fairValue - row.bookValue) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="差额处理" min-width="140">
          <template #default="{ row }">
            <span v-if="row.fairValue >= row.bookValue">其他综合收益</span>
            <span v-else class="text-danger">当期损益</span>
          </template>
        </el-table-column>
        <el-table-column prop="transferOut" label="转出方金额" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transferOut" size="small" :disabled="isReadonly" @change="onRowChange('selfToInvest', row)" />
          </template>
        </el-table-column>
        <el-table-column prop="transferIn" label="转入方金额" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transferIn" size="small" :disabled="isReadonly" @change="onRowChange('selfToInvest', row)" />
          </template>
        </el-table-column>
        <el-table-column label="验证" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="Math.abs(row.transferOut - row.transferIn) < 0.01 ? 'success' : 'danger'" size="small">
              {{ Math.abs(row.transferOut - row.transferIn) < 0.01 ? '✓' : '✗' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(B) 投资性房地产 → 自用</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('investToSelf')">+ 新增</el-button>
        </div>
      </template>
      <el-table :data="investToSelfRows" border size="small" class="audit-table">
        <el-table-column prop="assetName" label="资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-model="row.assetName" size="small" :disabled="isReadonly" @change="onRowChange('investToSelf', row)" />
          </template>
        </el-table-column>
        <el-table-column prop="transferDate" label="转换日" width="120">
          <template #default="{ row }">
            <el-input v-model="row.transferDate" size="small" :disabled="isReadonly" @change="onRowChange('investToSelf', row)" />
          </template>
        </el-table-column>
        <el-table-column prop="fairValue" label="转换日公允(入账值)" min-width="130" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.fairValue" size="small" :disabled="isReadonly" @change="onRowChange('investToSelf', row)" />
          </template>
        </el-table-column>
        <el-table-column prop="transferOut" label="转出方金额" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transferOut" size="small" :disabled="isReadonly" @change="onRowChange('investToSelf', row)" />
          </template>
        </el-table-column>
        <el-table-column prop="transferIn" label="转入方金额" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transferIn" size="small" :disabled="isReadonly" @change="onRowChange('investToSelf', row)" />
          </template>
        </el-table-column>
        <el-table-column label="验证" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="Math.abs(row.transferOut - row.transferIn) < 0.01 ? 'success' : 'danger'" size="small">
              {{ Math.abs(row.transferOut - row.transferIn) < 0.01 ? '✓' : '✗' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(C) 在建工程 → 投资性房地产</span>
          <span class="action-btns">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('cipToInvest')">+ 新增</el-button>
            <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H2-1 审定表')">→ H2在建工程</el-tag>
          </span>
        </div>
      </template>
      <el-table :data="cipToInvestRows" border size="small" class="audit-table">
        <el-table-column prop="assetName" label="资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-model="row.assetName" size="small" :disabled="isReadonly" @change="onRowChange('cipToInvest', row)" />
          </template>
        </el-table-column>
        <el-table-column prop="transferDate" label="转换日" width="120">
          <template #default="{ row }">
            <el-input v-model="row.transferDate" size="small" :disabled="isReadonly" @change="onRowChange('cipToInvest', row)" />
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="在建账面值" min-width="110" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.bookValue" size="small" :disabled="isReadonly" @change="onRowChange('cipToInvest', row)" />
          </template>
        </el-table-column>
        <el-table-column label="入账价值" min-width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" :title="measurementModel === 'cost' ? '账面价值' : '公允价值'">
              {{ fmtNum(measurementModel === 'cost' ? row.bookValue : row.fairValue) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="fairValue" label="公允价值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.fairValue" size="small" :disabled="isReadonly" @change="onRowChange('cipToInvest', row)" />
          </template>
        </el-table-column>
        <el-table-column prop="transferOut" label="转出方" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transferOut" size="small" :disabled="isReadonly" @change="onRowChange('cipToInvest', row)" />
          </template>
        </el-table-column>
        <el-table-column prop="transferIn" label="转入方" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transferIn" size="small" :disabled="isReadonly" @change="onRowChange('cipToInvest', row)" />
          </template>
        </el-table-column>
        <el-table-column label="验证" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="Math.abs(row.transferOut - row.transferIn) < 0.01 ? 'success' : 'danger'" size="small">
              {{ Math.abs(row.transferOut - row.transferIn) < 0.01 ? '✓' : '✗' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-6')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-6')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：转换时点判定、差额处理（成本/公允模式）、转出=转入验证及与 H1/H2 的勾稽。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：A、转换时点与金额处理恰当、转出转入平衡。B、除下列事项外未见异常。C、转换处理存在重大问题，不可确认。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabTransferReview.vue — H3-6 互转审核表
 * 三方向分区(36列25公式)+转出=转入验证+方法论上下文+GtIndexChip→H1/H2+AI+💬复核
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { useH3TransferReview } from '../../composables/useH3TransferReview'
import type { TransferDirection } from '../../composables/useH3TransferReview'
import { useH3FormData } from '../../composables/useH3FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  measurementModel: 'cost' | 'fair_value'
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: toRef(props, 'measurementModel') as any,
})

const {
  selfToInvestRows, investToSelfRows, cipToInvestRows, addRow: addTransferRow, updateTransferRow,
} = useH3TransferReview({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
  measurementModel: toRef(props, 'measurementModel') as any,
})

// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-6-audit-note'
const CONCLUSION_KEY = 'H3-6-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

function addRow(direction: TransferDirection) {
  addTransferRow(direction)
}

function onRowChange(direction: string, row: any) {
  updateTransferRow(direction, 0, row)
  // 互转联动：publish EventBus 事件通知 H1/H2
  if (direction === 'selfToInvest' || direction === 'investToSelf') {
    publishTransferEvent('h3:transfer-from-h1', {
      direction,
      amount: row.transferOut || row.transferIn,
      assetName: row.assetName,
      date: row.transferDate,
    })
  }
  if (direction === 'cipToInvest') {
    publishTransferEvent('h3:transfer-from-h2', {
      direction,
      amount: row.transferOut || row.transferIn,
      assetName: row.assetName,
      date: row.transferDate,
    })
  }
}

/** EventBus publish 互转联动事件 */
function publishTransferEvent(eventName: string, payload: Record<string, any>) {
  try {
    http.post(`/api/projects/${props.projectId}/events/publish`, {
      event_type: eventName,
      payload: { ...payload, wp_id: props.wpId, measurement_model: props.measurementModel },
    }).catch(() => { /* silent retry not needed for cross-wp events */ })
  } catch { /* best effort */ }
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-transfer-review { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.method-context { margin-bottom: 16px; }
.context-bar { border-left: 3px solid #d97706; background: #fffbe6; padding: 10px 14px; border-radius: 4px; font-size: 12px; line-height: 1.6; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; align-items: center; gap: 8px; }
.nav-chip { cursor: pointer; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-danger { color: var(--el-color-danger); }
.conclusion-card { margin-top: 16px; }
</style>
