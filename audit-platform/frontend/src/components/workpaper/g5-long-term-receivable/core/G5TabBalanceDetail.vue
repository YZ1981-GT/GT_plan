<template>
  <div class="g5-balance-detail">
    <div class="section-head">
      <h3 class="sheet-title">G5-2 余额明细表</h3>
      <div class="head-actions tab-toolbar">
        <GtIndexChip value="wp:G5-2" />
        <G5ImportExportDropdown
          :wp-id="props.wpId"
          sheet="G5-2"
          :disabled="!!props.readonly"
          @imported="onImported"
        />
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="!!props.readonly"
          :loading="!!props.rollForwardLoading"
          @click="emit('roll-forward')"
        >
          上年结转
        </el-button>
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
        <GtReviewTrigger section-id="g5-2-balance-detail" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：核实长期应收款各债务人期末余额、未实现融资收益及净额，按账龄分段验证合计勾稽，识别关联方及长账龄风险。
    </el-alert>

    <!-- 区段Tab切换 -->
    <div class="segment-tabs">
      <el-segmented v-model="detail.activeTab.value" :options="tabOptions" size="small" />
      <div class="aging-toolbar">
        <span class="muted">账龄口径</span>
        <el-select
          :model-value="detail.agingPreset.value"
          size="small"
          style="width: 120px"
          :disabled="!!props.readonly"
          @change="onAgingPresetChange"
        >
          <el-option label="3年段" value="THREE_YEAR" />
          <el-option label="5年段" value="FIVE_YEAR" />
          <el-option label="自定义" value="CUSTOM" />
        </el-select>
        <el-tag size="small" type="info">{{ detail.segments.value.length }} 段</el-tag>
      </div>
      <div class="tab-actions">
        <el-button size="small" type="primary" plain @click="detail.addRow()" :disabled="props.readonly">
          + 新增债务人
        </el-button>
      </div>
    </div>

    <el-dialog v-model="showAgingDialog" title="自定义账龄段" width="420px" destroy-on-close @close="cancelAgingDialog">
      <p class="muted">每行一个账龄段名称（至少 2 段，最多 10 段）。</p>
      <el-input
        v-model="agingDraft"
        type="textarea"
        :autosize="{ minRows: 6, maxRows: 12 }"
        placeholder="例：&#10;1年以内&#10;1-2年&#10;2-3年&#10;3年以上"
      />
      <template #footer>
        <el-button @click="cancelAgingDialog">取消</el-button>
        <el-button type="primary" @click="confirmAgingCustom">确定</el-button>
      </template>
    </el-dialog>

    <!-- Tab1: 债务人基础信息 -->
    <el-table
      v-show="detail.activeTab.value === 'basic'"
      :data="detail.rows.value"
      :height="500"
      border stripe
      style="width: 100%; font-size: 13px"
      highlight-current-row
      @current-change="onRowChange"
    >
      <el-table-column type="index" label="序号" width="50" />
      <el-table-column prop="debtorName" label="债务人名称" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.debtorName" size="small" :disabled="props.readonly" @change="onRowEdit(row)" />
        </template>
      </el-table-column>
      <el-table-column prop="businessType" label="业务类型" width="100">
        <template #default="{ row }">
          <el-select v-model="row.businessType" size="small" :disabled="props.readonly" @change="onRowEdit(row)">
            <el-option label="融资租赁" value="lease" />
            <el-option label="分期销售" value="installment" />
            <el-option label="保理" value="factoring" />
            <el-option label="其他" value="other" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="contractNo" label="合同编号" min-width="100">
        <template #default="{ row }">
          <el-input v-model="row.contractNo" size="small" :disabled="props.readonly" @change="persistRows" />
        </template>
      </el-table-column>
      <el-table-column prop="startDate" label="起始日" width="110">
        <template #default="{ row }">
          <el-input v-model="row.startDate" size="small" placeholder="YYYY-MM-DD" :disabled="props.readonly" @change="persistRows" />
        </template>
      </el-table-column>
      <el-table-column prop="maturityDate" label="到期日" width="110">
        <template #default="{ row }">
          <el-input v-model="row.maturityDate" size="small" placeholder="YYYY-MM-DD" :disabled="props.readonly" @change="persistRows" />
        </template>
      </el-table-column>
      <el-table-column prop="isWithinOneYear" label="1年内到期" width="90" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.isWithinOneYear" :disabled="props.readonly" @change="persistRows" />
        </template>
      </el-table-column>
      <el-table-column prop="contractAmount" label="合同总额" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.contractAmount" size="small" :controls="false" :disabled="props.readonly" @change="onRowEdit(row)" />
        </template>
      </el-table-column>
      <el-table-column prop="recoveredAmount" label="已收回金额" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.recoveredAmount" size="small" :controls="false" :disabled="props.readonly" @change="onRowEdit(row)" />
        </template>
      </el-table-column>
      <el-table-column label="期末余额" min-width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="合同总额-已收回">{{ fmt(row.closingBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="debitOccurrence" label="借方发生" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.debitOccurrence" size="small" :controls="false" :disabled="props.readonly" @change="persistRows" />
        </template>
      </el-table-column>
      <el-table-column prop="creditOccurrence" label="贷方发生" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.creditOccurrence" size="small" :controls="false" :disabled="props.readonly" @change="persistRows" />
        </template>
      </el-table-column>
      <el-table-column prop="isRelatedParty" label="关联方" width="70" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.isRelatedParty" :disabled="props.readonly" @change="persistRows" />
        </template>
      </el-table-column>
    </el-table>

    <!-- Tab2: 余额分析+账龄（动态列，基于 bands from useAgingConfig） -->
    <el-table
      v-show="detail.activeTab.value === 'aging'"
      :data="detail.rows.value"
      :height="500"
      border stripe
      style="width: 100%; font-size: 13px"
      highlight-current-row
      @current-change="onRowChange"
    >
      <el-table-column type="index" label="序号" width="50" />
      <el-table-column prop="debtorName" label="债务人名称" min-width="120" />
      <el-table-column prop="unrealizedIncome" label="未实现融资收益" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.unrealizedIncome" size="small" :controls="false" :disabled="props.readonly" @change="onRowEdit(row)" />
        </template>
      </el-table-column>
      <el-table-column label="净额" min-width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="期末余额-未实现融资收益">{{ fmt(row.netAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column
        v-for="band in bands"
        :key="band.key"
        :label="band.label"
        min-width="90"
        align="right"
      >
        <template #default="{ row }">
          <el-input-number
            :model-value="row.agingAudited[band.key] ?? 0"
            size="small"
            :controls="false"
            :disabled="props.readonly"
            @update:model-value="(v: number) => { row.agingAudited[band.key] = v; onRowEdit(row) }"
          />
        </template>
      </el-table-column>
      <el-table-column label="账龄合计" min-width="90" align="right">
        <template #default="{ row }">
          <span
            class="formula-cell"
            :class="{ 'mismatch': Math.abs(row.agingTotal - row.netAmount) > 0.01 }"
            title="各账龄段之和"
          >{{ fmt(row.agingTotal) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-model="row.remark" size="small" :disabled="props.readonly" @change="persistRows" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部合计 -->
    <div class="totals-bar">
      合同总额: {{ fmt(detail.totals.value.contractAmount) }} |
      已收回: {{ fmt(detail.totals.value.recoveredAmount) }} |
      期末余额: {{ fmt(detail.totals.value.closingBalance) }} |
      净额: {{ fmt(detail.totals.value.netAmount) }}
    </div>

    <G5AuditTextCards
      :wp-id="props.wpId"
      :is-readonly="!!props.readonly"
      :note="auditNote"
      :conclusion="auditConclusion"
      note-ai-section="detail-note"
      conclusion-ai-section="detail-conclusion"
      note-placeholder="填写审计说明：可概述明细核对情况、账龄勾稽结果、关联方及长账龄风险，以及拟调整/未调整事项及其影响。"
      @update:note="saveAuditNote"
      @update:conclusion="saveAuditConclusion"
    />

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>期末余额 = 合同总额 − 已收回金额（自动计算列）</li>
        <li>净额 = 期末余额 − 未实现融资收益</li>
        <li>账龄合计应等于净额，若不一致（红色）需核对账龄分段录入</li>
        <li>账龄口径支持 3年段 / 5年段 / 自定义；也可在项目「底稿配置」中统一调整</li>
        <li>关联方债务人须勾选，供关联方交易披露与减值单独评估</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, onMounted, watch } from 'vue'
import { useG5BalanceDetail } from '../../composables/useG5BalanceDetail'
import { useInjectedG5FormData } from '../../composables/useG5LonRecFormData'
import { G5_ITEM_IDS, readCanonicalRaw } from '../../composables/g5StorageContract'
import type { G5AgingPreset } from '../../composables/g5AgingScheme'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'
import G5AuditTextCards from '../G5AuditTextCards.vue'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  readonly?: boolean
  rollForwardLoading?: boolean
}>()

const emit = defineEmits<{ imported: []; 'roll-forward': [] }>()

const detail = useG5BalanceDetail(toRef(props, 'projectId'))
const { bands } = detail

const ROWS_KEY = G5_ITEM_IDS.G5_2_ROWS
const PRESET_KEY = G5_ITEM_IDS.G5_2_AGING_PRESET
const CUSTOM_KEY = G5_ITEM_IDS.G5_2_AGING_CUSTOM
const g5Notes = useInjectedG5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const auditConclusion = ref('')
const G5_NOTE_KEY = 'G5-2-audit-note'
const G5_CONCLUSION_KEY = 'G5-2-audit-conclusion'
const showAgingDialog = ref(false)
const agingDraft = ref('')
const lastNonCustomPreset = ref<G5AgingPreset>('FIVE_YEAR')
let hydrating = false

function persistAgingMeta(): void {
  if (props.readonly || hydrating) return
  const preset = detail.agingPreset.value
  void g5Notes.saveImmediate(PRESET_KEY, { conclusion: preset, remark: preset })
  const labels = detail.customAgingLabels.value
  const customJson = JSON.stringify(labels)
  void g5Notes.saveImmediate(CUSTOM_KEY, { conclusion: customJson, remark: customJson })
  try {
    window.dispatchEvent(new CustomEvent('g5:aging-preset-changed', {
      detail: { preset, customLabels: [...labels], segments: detail.segments.value },
    }))
  } catch { /* silent */ }
}

function persistRows(): void {
  if (props.readonly || hydrating) return
  const json = detail.serializeRows()
  g5Notes.debouncedSave(ROWS_KEY, { remark: json, conclusion: json })
  try {
    window.dispatchEvent(new CustomEvent('g5:detail-updated', {
      detail: {
        closingBalance: detail.totals.value.closingBalance,
        netAmount: detail.totals.value.netAmount,
        rowCount: detail.rows.value.length,
      },
    }))
  } catch { /* silent */ }
}

function onAgingPresetChange(val: G5AgingPreset) {
  if (val === 'CUSTOM') {
    agingDraft.value = (detail.customAgingLabels.value.length
      ? detail.customAgingLabels.value
      : detail.segments.value.map((s) => s.label)
    ).join('\n')
    showAgingDialog.value = true
    return
  }
  lastNonCustomPreset.value = val
  if (detail.setAgingPreset(val)) {
    persistAgingMeta()
    persistRows()
  }
}

function confirmAgingCustom() {
  const labels = agingDraft.value.split('\n').map((l) => l.trim()).filter(Boolean)
  if (detail.setAgingPreset('CUSTOM', labels)) {
    showAgingDialog.value = false
    persistAgingMeta()
    persistRows()
  }
}

function cancelAgingDialog() {
  showAgingDialog.value = false
  if (detail.agingPreset.value !== 'CUSTOM') return
  if (!detail.customAgingLabels.value.length) {
    detail.setAgingPreset(lastNonCustomPreset.value)
  }
}

function onRowEdit(row: any): void {
  detail.recalcRow(row)
  persistRows()
}

function saveAuditNote(val: string): void {
  if (props.readonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.readonly) return
  auditConclusion.value = val
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val })
}
onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  hydrating = true
  const presetRaw = readCanonicalRaw(g5Notes.allResponses.value.get(PRESET_KEY))
  const customRaw = readCanonicalRaw(g5Notes.allResponses.value.get(CUSTOM_KEY))
  detail.loadAgingPreset(presetRaw, customRaw)
  if (detail.agingPreset.value === 'THREE_YEAR' || detail.agingPreset.value === 'FIVE_YEAR') {
    lastNonCustomPreset.value = detail.agingPreset.value
  }
  const raw = readCanonicalRaw(g5Notes.allResponses.value.get(ROWS_KEY))
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) detail.loadRows(parsed)
    } catch { /* ignore */ }
  }
  hydrating = false
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

watch(() => detail.rows.value.length, () => { if (!hydrating) persistRows() })

const tabOptions = [
  { label: '债务人基础信息', value: 'basic' },
  { label: '余额分析+账龄', value: 'aging' },
]

function onRowChange(row: any) {
  if (row) {
    const idx = detail.rows.value.findIndex(r => r.id === row.id)
    if (idx >= 0) detail.activeRowIndex.value = idx
  }
}

function onImported() {
  void (async () => {
    try { await g5Notes.loadAll() } catch { /* ignore */ }
    hydrating = true
    const raw = readCanonicalRaw(g5Notes.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) detail.loadRows(parsed)
      } catch { /* ignore */ }
    }
    hydrating = false
    emit('imported')
  })()
}

function fmt(v: number): string {
  return v?.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '-'
}
</script>

<style scoped>
.g5-balance-detail { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 8px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.segment-tabs { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.aging-toolbar { display: flex; align-items: center; gap: 8px; }
.muted { font-size: 12px; color: #909399; }
.tab-actions { margin-left: auto; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.mismatch { color: #f56c6c; font-weight: 600; }
.totals-bar { margin-top: 8px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-size: 12px; }
</style>
