<template>
  <div class="g6-reversal-writeoff" data-testid="g6-reversal-writeoff">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="一、审计目标：其他债权投资以恰当的金额包括在财务报表中，与之相关的计价调整已恰当记录。"
      class="objective-alert"
    />

    <el-alert
      v-if="!rw.gate.value.ready"
      type="warning"
      :closable="false"
      show-icon
      class="gate-alert"
      :title="gateAlertTitle"
    />

    <div class="methodology-context">
      <p class="methodology-title">编制逻辑（对齐 Excel G6-14）：</p>
      <p>（一）转回/收回：金额 ≤ 累计已计提；须说明原因、收回方式、原计提依据与合理性</p>
      <p>（二）核销：关注投资性质、核销程序、是否关联交易及合理性分析</p>
      <p>转回合计宜与 G6-12「本年转回」勾稽；可用「从 G6-12 带入」预填候选行。</p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:G6-14" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G6-12" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G6-15" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">
          转回 {{ rw.reversals.value.length }} · 核销 {{ rw.writeOffs.value.length }}
        </el-tag>
        <el-tag size="small" :type="rw.gate.value.ready ? 'success' : 'warning'">
          闸门 {{ rw.gate.value.ready ? '通过' : '待补' }}
        </el-tag>
        <el-tag
          v-if="rw.gate.value.g12ReversalTotal != null"
          size="small"
          :type="rw.gate.value.g12ReversalGap > 0.05 ? 'danger' : 'success'"
        >
          vs G6-12 本年转回差 {{ fmtNum(rw.gate.value.g12ReversalGap) }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <el-segmented v-model="rw.activeTab.value" :options="segmentOptions" size="small" />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 新增行
        </el-button>
        <el-button
          size="small"
          :disabled="isReadonly"
          :loading="pullingG612"
          @click="pullFromG612"
        >
          从 G6-12 带入转回
        </el-button>
        <G6EclImportExportDropdown
          :wp-id="wpId"
          sheet="G6-14"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <el-button
          size="small"
          :disabled="isReadonly || !aiAvailable"
          :loading="aiLoading"
          @click="handleAi"
        >🤖 AI</el-button>
        <el-button size="small" @click="openReviewDialog('G6-14-reversal-writeoff')">💬复核</el-button>
      </div>
    </div>

    <p class="section-label">
      二、审计过程 ·
      {{ rw.activeTab.value === 'tab1' ? '（一）本期重要的减值准备转回或转销检查' : '（二）本期重要的核销检查' }}
    </p>

    <!-- Tab1: 转回/收回 -->
    <el-table
      v-show="rw.activeTab.value === 'tab1'"
      :data="reversalDisplayRows"
      border
      size="small"
      max-height="480"
      row-key="id"
      :row-class-name="reversalRowClass"
      class="rw-table"
      highlight-current-row
      @current-change="onReversalCurrent"
    >
      <el-table-column label="序号" width="55" align="center">
        <template #default="{ row }">
          <span v-if="row._isTotal" class="total-label">合计</span>
          <span v-else>{{ row.seq }}</span>
        </template>
      </el-table-column>
      <el-table-column label="单位名称" min-width="130">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.unitName"
            size="small"
            @change="(v: string) => { row.unitName = v; persist() }"
          />
          <span v-else>{{ row.unitName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="100" align="center">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <el-select
            v-else-if="!isReadonly"
            :model-value="row.kind || '转回'"
            size="small"
            style="width: 100%"
            @change="(v: string) => { row.kind = v as any; persist() }"
          >
            <el-option value="转回" label="转回" />
            <el-option value="收回" label="收回" />
          </el-select>
          <span v-else>{{ row.kind || '转回' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="转回原因" min-width="130">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.reversalReason"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            @update:model-value="(v: string) => { row.reversalReason = v; persist() }"
          />
          <span v-else>{{ row.reversalReason || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="收回方式" min-width="110">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.recoveryMethod"
            size="small"
            placeholder="现金/抵债..."
            @change="(v: string) => { row.recoveryMethod = v; persist() }"
          />
          <span v-else>{{ row.recoveryMethod || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="原确定减值准备的依据" min-width="140">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.originalBasis"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            @update:model-value="(v: string) => { row.originalBasis = v; persist() }"
          />
          <span v-else>{{ row.originalBasis || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="收回或转回金额" min-width="120" align="right">
        <template #default="{ row }">
          <span v-if="row._isTotal" class="total-num">{{ fmtNum(rw.reversalSummary.value.totalReversalAmount) }}</span>
          <WpAmountInput
            v-else-if="!isReadonly"
            :model-value="row.reversalAmount"
            size="small"
            class="amt"
            :class="{ 'amt-invalid': !rw.isRowValid(row) }"
            @change="(v: number | undefined) => { row.reversalAmount = v ?? 0; persist() }"
          />
          <span v-else :class="{ 'amt-invalid-text': !rw.isRowValid(row) }">{{ fmtNum(row.reversalAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="转回前累计已计提" min-width="130" align="right">
        <template #default="{ row }">
          <span v-if="row._isTotal" class="total-num">{{ fmtNum(rw.reversalSummary.value.totalAccumulatedProvision) }}</span>
          <WpAmountInput
            v-else-if="!isReadonly"
            :model-value="row.accumulatedProvision"
            size="small"
            class="amt"
            @change="(v: number | undefined) => { row.accumulatedProvision = v ?? 0; persist() }"
          />
          <span v-else>{{ fmtNum(row.accumulatedProvision) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合理性分析" min-width="140">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.reasonAnalysis"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            @update:model-value="(v: string) => { row.reasonAnalysis = v; persist() }"
          />
          <span v-else>{{ row.reasonAnalysis || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="是否合理" width="110" align="center">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <el-select
            v-else-if="!isReadonly"
            :model-value="row.isReasonable"
            size="small"
            style="width: 100%"
            @change="(v: string) => { row.isReasonable = v as any; persist() }"
          >
            <el-option value="合理" label="合理" />
            <el-option value="基本合理" label="基本合理" />
            <el-option value="不合理" label="不合理" />
          </el-select>
          <span v-else>{{ row.isReasonable || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="90" align="center">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <GtIndexChip
            v-else
            :value="row.indexRef"
            @update="(v: string) => { row.indexRef = v; persist() }"
          />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-popconfirm
            v-if="!row._isTotal"
            title="确认删除？"
            @confirm="rw.removeReversalRow(row.id); persist()"
          >
            <template #reference>
              <el-icon class="delete-icon"><Delete /></el-icon>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- Tab2: 核销 -->
    <el-table
      v-show="rw.activeTab.value === 'tab2'"
      :data="writeOffDisplayRows"
      border
      size="small"
      max-height="480"
      row-key="id"
      :row-class-name="writeOffRowClass"
      class="rw-table"
      highlight-current-row
      @current-change="onWriteOffCurrent"
    >
      <el-table-column label="序号" width="55" align="center">
        <template #default="{ row }">
          <span v-if="row._isTotal" class="total-label">合计</span>
          <span v-else>{{ row.seq }}</span>
        </template>
      </el-table-column>
      <el-table-column label="单位名称" min-width="130">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.unitName"
            size="small"
            @change="(v: string) => { row.unitName = v; persist() }"
          />
          <span v-else>{{ row.unitName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="其他债权投资的性质" min-width="140">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.writeOffType"
            size="small"
            placeholder="债券/信托..."
            @change="(v: string) => { row.writeOffType = v; persist() }"
          />
          <span v-else>{{ row.writeOffType || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="核销金额" min-width="120" align="right">
        <template #default="{ row }">
          <span v-if="row._isTotal" class="total-num">{{ fmtNum(rw.writeOffSummary.value.totalWriteOffAmount) }}</span>
          <WpAmountInput
            v-else-if="!isReadonly"
            :model-value="row.writeOffAmount"
            size="small"
            class="amt"
            @change="(v: number | undefined) => { row.writeOffAmount = v ?? 0; persist() }"
          />
          <span v-else>{{ fmtNum(row.writeOffAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="核销原因" min-width="130">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.writeOffReason"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            @update:model-value="(v: string) => { row.writeOffReason = v; persist() }"
          />
          <span v-else>{{ row.writeOffReason || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="履行的核销程序" min-width="140">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.writeOffProcedure"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            @update:model-value="(v: string) => { row.writeOffProcedure = v; persist() }"
          />
          <span v-else>{{ row.writeOffProcedure || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="是否关联交易" width="110" align="center">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <el-switch
            v-else-if="!isReadonly"
            :model-value="row.isRelatedParty"
            @change="(v: boolean) => { row.isRelatedParty = v; persist() }"
          />
          <el-tag v-else :type="row.isRelatedParty ? 'warning' : 'info'" size="small">
            {{ row.isRelatedParty ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="合理性分析" min-width="140">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.reasonAnalysis"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            :class="{ 'field-required': row.isRelatedParty && !row.reasonAnalysis }"
            :placeholder="row.isRelatedParty ? '关联交易须说明' : ''"
            @update:model-value="(v: string) => { row.reasonAnalysis = v; persist() }"
          />
          <span v-else>{{ row.reasonAnalysis || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="是否合理" width="110" align="center">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <el-select
            v-else-if="!isReadonly"
            :model-value="row.isReasonable"
            size="small"
            style="width: 100%"
            @change="(v: string) => { row.isReasonable = v as any; persist() }"
          >
            <el-option value="合理" label="合理" />
            <el-option value="基本合理" label="基本合理" />
            <el-option value="不合理" label="不合理" />
          </el-select>
          <span v-else>{{ row.isReasonable || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="90" align="center">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <GtIndexChip
            v-else
            :value="row.indexRef"
            @update="(v: string) => { row.indexRef = v; persist() }"
          />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-popconfirm
            v-if="!row._isTotal"
            title="确认删除？"
            @confirm="rw.removeWriteOffRow(row.id); persist()"
          >
            <template #reference>
              <el-icon class="delete-icon"><Delete /></el-icon>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="summary-bar">
      <span class="sum-item">转回合计 <strong>{{ fmtNum(rw.reversalSummary.value.totalReversalAmount) }}</strong></span>
      <span class="sum-item">核销合计 <strong>{{ fmtNum(rw.writeOffSummary.value.totalWriteOffAmount) }}</strong></span>
      <span v-if="rw.reversalSummary.value.invalidCount > 0" class="sum-warn">
        超限 {{ rw.reversalSummary.value.invalidCount }} 项
      </span>
      <span v-if="rw.writeOffSummary.value.relatedPartyCount > 0" class="sum-warn">
        关联交易核销 {{ rw.writeOffSummary.value.relatedPartyCount }} 项
      </span>
    </div>

    <el-card shadow="never" class="section-card">
      <template #header><div class="section-header"><span class="section-title">三、审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="概述转回/核销检查程序、审批核查、关联交易关注事项及与 G6-12 本年转回勾稽。"
        @update:model-value="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">四、审计结论</span>
          <el-button size="small" :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="handleAi">🤖 AI</el-button>
        </div>
      </template>
      <el-input
        v-model="rw.conclusion.value"
        type="textarea"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="A、转回/核销恰当。B、除下述事项外未见异常。C、存在重大不当事项须调整。"
        @change="persist"
      />
    </el-card>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>转回/收回金额不得超过转回前累计已计提减值准备。</li>
        <li>核销须检查审批程序；关联交易须额外说明合理性。</li>
        <li>转回合计宜与 G6-12「本年转回」勾稽核对。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G6TabReversalWriteOff.vue — 对齐 Excel《减值准备转回（收回）、核销检查表G6-14》
 */
import { ref, computed, inject, onMounted, onBeforeUnmount } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useG6EclFormData } from '../../composables/useG6EclFormData'
import type { G6ReversalRow, G6WriteOffRow } from '../../composables/useG6EclFormData'
import { useG6EclReversalWriteOff } from '../../composables/useG6EclReversalWriteOff'
import { useG6EclAiGenerate } from '../../composables/useG6EclAiGenerate'
import {
  parseG6ChecklistPayload,
  parseG6ChecklistRows,
  fetchG612ImpairmentRows,
  G6_12_DATA_KEY,
  G6_14_DATA_KEY,
  G6_14_ROWS_KEY,
} from '../../composables/g6CrossHelpers'
import GtIndexChip from '../../GtIndexChip.vue'
import G6EclImportExportDropdown from '../G6EclImportExportDropdown.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

const DATA_KEY = G6_14_DATA_KEY
const NOTE_KEY = 'G6-14-reversal-writeoff-audit-note'
const CONCLUSION_KEY = 'G6-14-reversal-writeoff-conclusion'

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const isReadonly = computed(() => props.isReadonly)
const wpIdRef = computed(() => props.wpId)

const rw = useG6EclReversalWriteOff()
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG6EclAiGenerate(wpIdRef)
const formData = useG6EclFormData({
  wpId: wpIdRef,
  projectId: computed(() => props.projectId),
})

const auditNote = ref('')
const segmentOptions = [
  { label: '（一）转回/收回', value: 'tab1' },
  { label: '（二）核销', value: 'tab2' },
]

const gateAlertTitle = computed(() => {
  const g = rw.gate.value
  const parts: string[] = []
  if (g.invalidReversals) parts.push(`${g.invalidReversals} 项转回超限`)
  if (g.relatedMissingAnalysis) parts.push(`${g.relatedMissingAnalysis} 项关联核销缺分析`)
  if (g.unreasonableReversals || g.unreasonableWriteOffs) {
    parts.push(`${g.unreasonableReversals + g.unreasonableWriteOffs} 项判定不合理`)
  }
  if (g.g12ReversalTotal != null && g.g12ReversalGap > 0.05) {
    parts.push(`与 G6-12 本年转回差 ${g.g12ReversalGap.toFixed(2)}`)
  }
  return parts.length ? `质量闸门待补：${parts.join('；')}` : ''
})

const pullingG612 = ref(false)
type RevDisplay = G6ReversalRow & { _isTotal?: boolean }
type WoDisplay = G6WriteOffRow & { _isTotal?: boolean }

const reversalDisplayRows = computed<RevDisplay[]>(() => {
  const list = rw.reversals.value as RevDisplay[]
  if (!list.length) return []
  return [
    ...list,
    {
      ...list[0],
      id: '__total_rev__',
      seq: 0,
      unitName: '',
      _isTotal: true,
      reversalAmount: rw.reversalSummary.value.totalReversalAmount,
      accumulatedProvision: rw.reversalSummary.value.totalAccumulatedProvision,
    },
  ]
})

const writeOffDisplayRows = computed<WoDisplay[]>(() => {
  const list = rw.writeOffs.value as WoDisplay[]
  if (!list.length) return []
  return [
    ...list,
    {
      ...list[0],
      id: '__total_wo__',
      seq: 0,
      unitName: '',
      _isTotal: true,
      writeOffAmount: rw.writeOffSummary.value.totalWriteOffAmount,
    },
  ]
})

function reversalRowClass({ row }: { row: RevDisplay }): string {
  if (row._isTotal) return 'row-total'
  if (!rw.isRowValid(row)) return 'row-invalid'
  if (row.isReasonable === '不合理') return 'row-unreasonable'
  return ''
}

function writeOffRowClass({ row }: { row: WoDisplay }): string {
  if (row._isTotal) return 'row-total'
  if (row.isRelatedParty) return 'row-related'
  if (row.isReasonable === '不合理') return 'row-unreasonable'
  return ''
}

function onReversalCurrent(row: RevDisplay | null) {
  if (!row || row._isTotal) return
  const idx = rw.reversals.value.findIndex(r => r.id === row.id)
  if (idx >= 0) rw.activeRowIndex.value = idx
}

function onWriteOffCurrent(row: WoDisplay | null) {
  if (!row || row._isTotal) return
  const idx = rw.writeOffs.value.findIndex(r => r.id === row.id)
  if (idx >= 0) rw.activeRowIndex.value = idx
}

async function handleAddRow() {
  if (rw.activeTab.value === 'tab1') await rw.addReversalRow()
  else await rw.addWriteOffRow()
  persist()
}

function persist(): void {
  if (props.isReadonly) return
  const payload = rw.toJSON()
  const json = JSON.stringify(payload)
  formData.debouncedSave(DATA_KEY, {
    conclusion: json,
    remark: json,
  })
  formData.debouncedSave(G6_14_ROWS_KEY, {
    conclusion: json,
    remark: json,
  })
  formData.debouncedSave(CONCLUSION_KEY, { conclusion: rw.conclusion.value })
}

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}

async function loadG612Rows(): Promise<any[]> {
  const remote = await fetchG612ImpairmentRows(props.projectId, props.wpId)
  if (remote.length) return remote
  try { await formData.loadAll() } catch { /* ignore */ }
  const payload = parseG6ChecklistPayload(formData.allResponses.value.get(G6_12_DATA_KEY))
  if (Array.isArray(payload?.rows)) return payload.rows
  if (Array.isArray(payload)) return payload
  return []
}

async function refreshG12ReversalTotal(): Promise<void> {
  const rows = await loadG612Rows()
  const total = rows.reduce((s: number, r: any) => s + (Number(r?.currentReversal) || 0), 0)
  rw.setG12ReversalTotal(Math.round(total * 100) / 100)
}

async function pullFromG612(): Promise<void> {
  if (props.isReadonly) return
  pullingG612.value = true
  try {
    const rows = await loadG612Rows()
    if (!rows.length) {
      ElMessage.warning('未解析到 G6-12 减值测算行，请确认 ECL 实例已创建并完成 G6-12')
      return
    }
    const result = rw.importFromImpairmentRows(rows)
    persist()
    ElMessage.success(
      `已从 G6-12 带入转回：新增 ${result.added}，刷新 ${result.refreshed}`
        + (result.skipped ? `；跳过 ${result.skipped}` : ''),
    )
  } catch {
    ElMessage.error('从 G6-12 带入失败')
  } finally {
    pullingG612.value = false
  }
}

async function handleAi(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'reversal-writeoff-conclusion',
    rw.conclusion.value || '',
    {
      reversalCount: rw.reversals.value.length,
      writeOffCount: rw.writeOffs.value.length,
      totals: {
        reversal: rw.reversalSummary.value.totalReversalAmount,
        writeOff: rw.writeOffSummary.value.totalWriteOffAmount,
      },
      gate: rw.gate.value,
    },
    'AI 审计结论',
  )
  if (text) {
    rw.conclusion.value = text
    persist()
  }
}

function fmtNum(v: unknown): string {
  const n = Number(v)
  if (!Number.isFinite(n) || Math.abs(n) < 1e-9) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function onImported(): Promise<void> {
  try { await formData.loadAll() } catch { /* ignore */ }
  initFromData()
  await refreshG12ReversalTotal()
  emit('imported')
  ElMessage.success('G6-14 数据已导入并刷新')
}

function initFromData(): void {
  const primary = parseG6ChecklistPayload(formData.allResponses.value.get(DATA_KEY))
  const legacy = parseG6ChecklistPayload(formData.allResponses.value.get(G6_14_ROWS_KEY))
  const fromRows = parseG6ChecklistRows(formData.allResponses.value.get(G6_14_ROWS_KEY))
  let raw: any = primary
  if (!raw || (!raw.reversals && !raw.writeOffs && !raw.rows)) {
    raw = legacy
  }
  if ((!raw || (!raw.reversals && !raw.writeOffs)) && fromRows.length) {
    raw = { rows: fromRows, conclusion: '' }
  }
  if (!raw) raw = formData.parseContent()?.reversalWriteOff
  if (!raw && props.htmlData?.reversalWriteOff) raw = props.htmlData.reversalWriteOff
  rw.loadData(raw)
  const conc = formData.allResponses.value.get(CONCLUSION_KEY)
  if (conc?.conclusion) rw.conclusion.value = conc.conclusion
}

onMounted(async () => {
  await formData.loadAll()
  initFromData()
  await refreshG12ReversalTotal()
  const n = formData.allResponses.value.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
})

onBeforeUnmount(() => {
  persist()
  formData.flushPending()
})

defineExpose({ toJSON: () => rw.toJSON() })
</script>

<style scoped>
.g6-reversal-writeoff { padding: 12px; font-size: var(--wp-font-size, 13px); }
.objective-alert, .gate-alert { margin-bottom: 10px; }
.methodology-context {
  border-left: 4px solid #e6a23c; background: #fdf6ec;
  padding: 10px 14px; margin-bottom: 12px; border-radius: 0 4px 4px 0;
  font-size: 12px; line-height: 1.7; color: #6b5900;
}
.methodology-title { font-weight: 600; margin: 0 0 4px; }
.methodology-context p { margin: 2px 0; }
.tab-toolbar {
  display: flex; justify-content: space-between; gap: 8px; margin-bottom: 10px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.section-label { margin: 0 0 8px; font-size: 13px; color: #606266; font-weight: 600; }
.rw-table { font-size: var(--wp-font-size, 13px); }
.amt { width: 100%; }
.amt :deep(.el-input__inner) { text-align: right; }
:deep(.amt-invalid .el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
.amt-invalid-text { color: #f56c6c; font-weight: 600; }
:deep(.field-required .el-textarea__inner) { box-shadow: 0 0 0 1px #e6a23c inset; }
:deep(.row-total) { background: #ecf5ff !important; font-weight: 700; }
:deep(.row-invalid) { background: #fef0f0 !important; }
:deep(.row-related) { background: #fdf6ec !important; }
:deep(.row-unreasonable) { background: #fef0f0 !important; }
.total-label { color: #409eff; font-weight: 700; }
.total-num { font-weight: 700; }
.delete-icon { cursor: pointer; color: #909399; }
.delete-icon:hover { color: #f56c6c; }
.summary-bar {
  display: flex; gap: 14px; flex-wrap: wrap; align-items: center;
  margin: 12px 0; padding: 8px 12px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px;
  font-size: 13px; color: #606266;
}
.sum-item strong { color: #303133; }
.sum-warn { color: #e6a23c; font-weight: 600; }
.section-card { margin-top: 14px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
.section-title { font-weight: 600; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
