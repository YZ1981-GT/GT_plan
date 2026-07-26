<template>
  <div class="h4-tab-adjudication">
    <details class="guidance-details">
      <summary>📋 编制提示（对齐致同 Excel 审定表 H4-1）</summary>
      <div class="guidance-content">
        <p>1. 结构：一、工程物资原值 → 二、减值准备 → 三、净值；列组为期初/期末×未审·账项调整·审定 + 审定变动额/率。</p>
        <p>2. 审定数=未审数+账项调整；净值=原值−减值；期初审定应与上年末审定数一致。</p>
        <p>3. 优先「从 H4-2 回填分类」带入未审/调整；H4-3 确认后「回写期末账项调整」（1605 净额按未审权重分摊）。</p>
        <p>4. 净值变动率≥{{ state.CHANGE_RATE_THRESHOLD }}% 须在审计说明(1)解释；与报表核对填入(3)。在建工程可「带入(H2/TB)」，重大变动可一键写入说明/附注。</p>
        <p>5.「带入调整」：从集中登记按科目 1605 拉取调整分录（资产借方净额=借−贷），逐笔分配到各分类的期末账项调整（增量累加），带入后审定数自动更新并联动附注。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实工程物资（科目1605）原值及减值准备期末余额的存在、完整与计价；审定净值=原值−减值；与 H4-2/TB/报表勾稽，为列报提供审定依据。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button
          v-if="!props.isReadonly"
          size="small"
          type="primary"
          plain
          @click="handleSyncFromH42"
        >
          从 H4-2 回填分类
        </el-button>
        <el-button
          v-if="!props.isReadonly && (Math.abs(state.h43EmAjeNet.value) > 0.005 || Math.abs(state.h43ImpairAjeNet.value) > 0.005)"
          size="small"
          plain
          @click="handleSyncFromH43"
        >
          从 H4-3 回写期末账项调整
        </el-button>
        <el-button
          v-if="!props.isReadonly"
          size="small"
          plain
          :loading="seedingCip"
          @click="handleSeedCip"
        >
          带入在建工程(H2/TB)
        </el-button>
        <el-button
          v-if="!props.isReadonly && state.significantChangeItems.value.length"
          size="small"
          plain
          @click="handleApplySignificantNote"
        >
          重大变动→说明(1)
        </el-button>
        <el-button
          v-if="!props.isReadonly"
          size="small"
          type="primary"
          plain
          :loading="adjPull.loading.value"
          @click="openBringInAdjustment"
        >
          <el-icon><Download /></el-icon>带入调整
        </el-button>
        <el-tag size="small" type="info" effect="plain">
          TB·1605 未审 {{ fmtAmt(state.tbUnadjusted.value) }} / 审定 {{ fmtAmt(state.tbAudited.value) }}
        </el-tag>
        <el-tag
          v-if="Math.abs(state.unadjustedVsTbDiff.value) > 0.01 && state.originalRows.value.length"
          size="small"
          type="warning"
          effect="plain"
        >
          净值未审 vs TB差 {{ fmtAmt(state.unadjustedVsTbDiff.value) }}
        </el-tag>
        <el-tag
          v-if="Math.abs(state.h43EmAjeNet.value) > 0.005"
          size="small"
          type="info"
          effect="plain"
        >
          H4-3：1605原值账项 {{ fmtAmt(state.h43EmAjeNet.value) }}
        </el-tag>
        <el-tag
          v-if="Math.abs(state.h43ImpairAjeNet.value) > 0.005"
          size="small"
          type="warning"
          effect="plain"
        >
          H4-3：减值账项 {{ fmtAmt(state.h43ImpairAjeNet.value) }}
        </el-tag>
        <el-tag
          v-if="state.significantNetChanges.value.length"
          size="small"
          type="danger"
          effect="plain"
        >
          净值变动≥{{ state.CHANGE_RATE_THRESHOLD }}%：{{ state.significantNetChanges.value.length }} 项
        </el-tag>
        <el-tag
          v-if="cipSeedNeeded"
          size="small"
          type="warning"
          effect="plain"
        >
          报表核对·在建工程未填 — 请点「带入在建工程(H2/TB)」
        </el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H4-1" :context-project-id="props.projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H4-2" :validate="false" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H4-3" :validate="false" /></span>
        <el-tag size="small" type="info">分类 {{ state.originalRows.value.length }} 项</el-tag>
        <el-button size="small" link type="default" @click="openReview('H4-1')">💬 复核</el-button>
      </div>
    </div>

    <!-- 一、原值 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一、工程物资原值（科目1605）</span>
          <el-button size="small" circle @click="openReview('H4-1-original')">💬</el-button>
        </div>
      </template>
      <AdjAmountTable
        :rows="originalDisplayRows"
        :is-readonly="props.isReadonly"
        @cell-change="onCellChange"
        @remove="handleDeleteRow"
      />
      <div v-if="!props.isReadonly" class="add-row-bar">
        <el-button size="small" @click="handleAddRow('original')">+ 新增原值分类</el-button>
      </div>
    </el-card>

    <!-- 二、减值准备 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、减值准备</span>
          <span class="section-hint">可与 H4-7/H4-8 勾稽</span>
        </div>
      </template>
      <AdjAmountTable
        :rows="impairmentDisplayRows"
        :is-readonly="props.isReadonly"
        @cell-change="onCellChange"
        @remove="handleDeleteRow"
      />
      <div v-if="!props.isReadonly" class="add-row-bar">
        <el-button size="small" @click="handleAddRow('impairment')">+ 新增减值分类</el-button>
      </div>
    </el-card>

    <!-- 三、净值 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>三、净值（=原值−减值）</span>
          <el-tag
            v-if="Math.abs(state.netIdentityDiff.value) > 0.01"
            size="small"
            type="danger"
          >
            身份校验差 {{ fmtAmt(state.netIdentityDiff.value) }}
          </el-tag>
          <el-tag v-else size="small" type="success" effect="plain">身份校验通过</el-tag>
        </div>
      </template>
      <el-table
        :data="[...state.netRows.value, state.netTotalRow.value]"
        border
        stripe
        size="small"
        class="adj-table"
        :row-class-name="netRowClass"
      >
        <el-table-column prop="name" label="项目" min-width="140" fixed />
        <el-table-column label="期初未审" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amt-cell">{{ fmtAmt(row.beginUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初审定" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="原值期初审定−减值期初审定">{{ fmtAmt(row.beginAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末未审" min-width="110" align="right">
          <template #default="{ row }">
            <span class="amt-cell">{{ fmtAmt(row.endUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="原值期末审定−减值期末审定">{{ fmtAmt(row.endAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定变动额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmt(row.auditedChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定变动率" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'rate-significant': row.isSignificant }">
              {{ fmtRate(row.auditedChangeRate) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <p class="net-hint">
        审定净值合计 <b>{{ fmtAmt(state.netTotalRow.value.endAudited) }}</b>
        （期初 {{ fmtAmt(state.netTotalRow.value.beginAudited) }}）。
        变动率绝对值≥{{ state.CHANGE_RATE_THRESHOLD }}% 须在下方说明(1)解释原因。
      </p>
    </el-card>

    <!-- TB 核对 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>与试算平衡表核对（科目1605）</span></div>
      </template>
      <div class="tb-compare">
        <div class="tb-row">
          <span class="tb-label">审定净值合计：</span>
          <span class="tb-value">{{ fmtAmt(state.adjudicatedTotal.value) }}</span>
        </div>
        <div class="tb-row">
          <span class="tb-label">TB未审数(1605)：</span>
          <span class="tb-value">{{ fmtAmt(state.tbUnadjusted.value) }}</span>
        </div>
        <div class="tb-row">
          <span class="tb-label">TB审定数(1605)：</span>
          <span class="tb-value">{{ fmtAmt(state.tbAudited.value) }}</span>
        </div>
        <div class="tb-row">
          <span class="tb-label">差异(审定−TB审定)：</span>
          <span class="tb-value" :class="{ 'error-amount': !state.isTbMatch.value }">
            {{ fmtAmt(state.tbDiff.value) }}
          </span>
        </div>
      </div>
    </el-card>

    <!-- (3) 与经审计的财务报表核对 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>(3) 与经审计的财务报表核对</span>
          <span class="section-hint">在建工程 + 工程物资 ↔ 报表「在建工程」列报</span>
        </div>
      </template>
      <el-table :data="state.fsCompareRows.value" size="small" border>
        <el-table-column prop="label" label="项目" min-width="200" />
        <el-table-column label="期末审定" align="right" min-width="130">
          <template #default="{ row }">
            <template v-if="row.editable && !props.isReadonly">
              <el-input-number
                :model-value="row.label.startsWith('在建') ? state.fsReconcile.value.cipEndAudited : state.fsReconcile.value.fsEndAmount"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number) => onFsChange(row.label, 'end', v ?? 0)"
              />
            </template>
            <span v-else :class="{ 'error-amount': row.label === '差异' && Math.abs(row.endAudited) > 0.01 }">
              {{ fmtAmt(row.endAudited) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="期初审定" align="right" min-width="130">
          <template #default="{ row }">
            <template v-if="row.editable && !props.isReadonly">
              <el-input-number
                :model-value="row.label.startsWith('在建') ? state.fsReconcile.value.cipBeginAudited : state.fsReconcile.value.fsBeginAmount"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number) => onFsChange(row.label, 'begin', v ?? 0)"
              />
            </template>
            <span v-else :class="{ 'error-amount': row.label === '差异' && Math.abs(row.beginAudited) > 0.01 }">
              {{ fmtAmt(row.beginAudited) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-alert
      v-if="crossSheetWarning"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      :title="crossSheetWarning"
    />
    <el-alert
      v-if="Math.abs(state.detailDiff.value) > 0.01"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      :title="`交叉验证：原值审定合计 vs H4-2 差异 ${fmtAmt(state.detailDiff.value)}`"
    />

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>1、审计说明</span>
          <el-button size="small" circle @click="openReview('H4-1-note')">💬</el-button>
        </div>
      </template>
      <div class="qual-grid">
        <div class="qual-item">
          <label>
            (1) 净值重大变动原因
            <span class="req-hint">（变动率≥{{ state.CHANGE_RATE_THRESHOLD }}%须说明）</span>
          </label>
          <el-input
            v-model="state.qualitativeNotes.value.fluctuation"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            :disabled="props.isReadonly"
            :placeholder="fluctuationPlaceholder"
            @blur="state.saveQualitativeNotes()"
          />
        </div>
        <div class="qual-item">
          <label>(2) 情况说明</label>
          <el-input
            v-model="state.qualitativeNotes.value.situation"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="props.isReadonly"
            placeholder="减值迹象、积压呆滞、与 H4-4/H4-5/H4-6/H4-7 相关说明…"
            @blur="state.saveQualitativeNotes()"
          />
        </div>
      </div>
      <el-divider content-position="left">综合说明</el-divider>
      <el-input
        v-model="state.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="概述取数来源、勾稽结果、重大调整及风险应对…"
        :disabled="props.isReadonly"
        @blur="state.saveNote(state.auditNote.value)"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>2、审计结论</span>
          <div v-if="!props.isReadonly" class="conclusion-actions">
            <el-button size="small" @click="state.applyConclusionTemplate('A')">套用 A</el-button>
            <el-button size="small" @click="state.applyConclusionTemplate('B')">套用 B</el-button>
            <el-button size="small" type="warning" @click="state.applyConclusionTemplate('C')">套用 C</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="state.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="参考：A、未见异常。 B、除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。 C、由于存在重大未调整事项或范围限制，不可确认。"
        :disabled="props.isReadonly"
        @blur="state.saveConclusion(state.auditConclusion.value)"
      />
    </el-card>

    <div v-if="!props.isReadonly" class="action-bar">
      <el-button type="primary" :loading="publishing" @click="handlePublish">
        确认审定 → 回写TB(1605)
      </el-button>
    </div>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1605 工程物资"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabAdjudication.vue — H4-1 工程物资及减值准备审定表
 * 对齐致同 Excel：期初/期末×未审·账项调整·审定 + 变动额/率；三段+报表核对+结构化说明
 */
import { ref, computed, inject, toRef, defineComponent, h, onMounted, onUnmounted, type Ref } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, ElTable, ElTableColumn, ElInputNumber, ElButton } from 'element-plus'
import http from '@/utils/http'
import { useAcnr } from '@/services/acnr/useAcnr'
import {
  useH4Adjudication,
  type H4AdjudicationRow,
} from '../../composables/useH4Adjudication'
import { useH4CrossSheet } from '../../composables/useH4CrossSheet'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', () => {})
const publishing = ref(false)
const seedingCip = ref(false)
const { resolveInstance } = useAcnr()

const allResponsesRef = computed(() => props.allResponses)
const tbValues = inject<Ref<Record<string, number>>>('h4TbValues', ref({}))

const tbData = computed(() => ({
  unadjusted1605: Number(tbValues.value?.eng_mat_1605_unadjusted) || 0,
  audited1605: Number(tbValues.value?.eng_mat_1605_audited) || 0,
  unadjusted1604:
    Number(tbValues.value?.cip_1604_unadjusted ?? tbValues.value?.cip_unadjusted) || 0,
  audited1604:
    Number(tbValues.value?.cip_1604_audited ?? tbValues.value?.cip_audited) || 0,
  opening1604:
    Number(tbValues.value?.cip_1604_unadjusted_opening) || 0,
}))

const state = useH4Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  tbData,
  onSave: (itemId: string, value: any) => {
    // 与 H4-2/H4-3/H4-4 一致：走主入口 persistResponse 落库
    saveResponse(itemId, value)
  },
  onWritebackTB: async (amount: number) => {
    // 真实回写 trial_balance（端点按 LIKE 前缀匹配子科目）
    try {
      await http.put(`/api/projects/${props.projectId}/trial-balance/writeback`, {
        account_code: '1605',
        audited_amount: amount,
      })
    } catch (e: any) {
      ElMessage.warning(`TB回写请求失败: ${e?.message || e}`)
    }
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: { wpCode: 'H4', accountCode: '1605', auditedAmount: amount },
    }))
    ElMessage.success(`已回写 TB 科目1605 审定数 ${fmtAmt(amount)}`)
  },
})

const crossSheet = useH4CrossSheet(allResponsesRef as any)

// ─── 从集中登记带入调整（1605 工程物资，资产借方；单一账项调整列→带入期末账项调整，增量累加） ───
const bringInRows = computed(() =>
  state.originalRows.value.map((r) => ({ rowKey: r.rowId, name: r.name, aje: 0, rje: 0 })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1605',
  direction: 'debit',
  subjectCode: '1605',
  wpCode: 'H4',
  subjectLabel: '工程物资(1605)',
  rows: bringInRows,
  // 单一账项调整列：忽略 field，读期末账项调整实时值增量累加
  updateCell: (rowKey: string, _field: any, value: number) => {
    const r = state.originalRows.value.find((x) => x.rowId === rowKey)
    const cur = Number(r?.endAdjustment) || 0
    state.updateCell(rowKey, 'endAdjustment', cur + value)
  },
  totalAudited: () => state.originalTotal.value.endAudited,
})

const originalDisplayRows = computed(() => [
  ...state.originalRows.value,
  state.originalTotal.value,
])
const impairmentDisplayRows = computed(() => [
  ...state.impairmentRows.value,
  state.impairmentTotal.value,
])

const crossSheetWarning = computed(() => {
  const check = crossSheet.adjudicationVsDetail.value
  if (!check.isMatch && (check.diff !== 0 || state.adjudicatedTotal.value !== 0)) {
    const sign = check.diff > 0 ? '+' : ''
    return `审定数≠H4-2合计，差额：${sign}${fmtAmt(check.diff)}元`
  }
  return ''
})

const fluctuationPlaceholder = computed(() => {
  const items = state.significantNetChanges.value
  if (!items.length) return '本期净值变动率均未超过阈值，如有其他重大变动说明可填写…'
  return `请说明：${items.map((r) => `${r.name}(${fmtRate(r.auditedChangeRate)})`).join('、')}`
})

/** 冷启动提示：报表核对在建工程为空且有 TB/可带入线索时提示 */
const cipSeedNeeded = computed(() => {
  const fs = state.fsReconcile.value
  return fs.cipEndAudited === 0 && fs.cipBeginAudited === 0
})

function netRowClass({ row }: { row: { isTotal?: boolean; isSignificant?: boolean } }) {
  if (row.isTotal) return 'total-row'
  if (row.isSignificant) return 'significant-row'
  return ''
}

function onCellChange(rowId: string, field: string, value: number | null) {
  state.updateCell(rowId, field, value ?? 0)
}

function onFsChange(label: string, side: 'end' | 'begin', value: number) {
  if (label.startsWith('在建')) {
    state.updateFsField(side === 'end' ? 'cipEndAudited' : 'cipBeginAudited', value)
  } else if (label === '报表数') {
    state.updateFsField(side === 'end' ? 'fsEndAmount' : 'fsBeginAmount', value)
  }
}

async function handleAddRow(section: 'original' | 'impairment') {
  try {
    const label = section === 'original' ? '原值物资分类' : '减值物资分类'
    const { value } = await ElMessageBox.prompt(`请输入${label}名称`, `新增${label}`, {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) state.addRow(value, section)
  } catch { /* cancelled */ }
}

function handleDeleteRow(rowId: string) {
  state.deleteRow(rowId)
}

function handleSyncFromH42() {
  const r = state.syncFromH42('overwrite')
  if (r.applied) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleSyncFromH43() {
  const r = state.syncEndAdjFromH43()
  if (r.applied) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

async function fetchH21CostRows(): Promise<any[] | null> {
  if (!props.projectId) return null
  try {
    const inst = await resolveInstance(props.projectId, 'H2', 'H2-1')
    const wpId = inst?.found ? inst.wp_id : undefined
    if (!wpId) {
      const inst2 = await resolveInstance(props.projectId, 'H2', 'H2')
      if (!inst2?.found || !inst2.wp_id) return null
      const { data } = await http.get(`/api/workpapers/${inst2.wp_id}/checklist-responses`, { _silent: true } as any)
      const list: any[] = Array.isArray(data) ? data : (data?.data ?? data?.items ?? [])
      const item = list.find((x: any) => x.item_id === 'H2-1-rows' || x.itemId === 'H2-1-rows')
      const raw = item?.remark ?? item?.conclusion
      if (!raw) return null
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      return Array.isArray(parsed) ? parsed : null
    }
    const { data } = await http.get(`/api/workpapers/${wpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(data) ? data : (data?.data ?? data?.items ?? [])
    const item = list.find((x: any) => x.item_id === 'H2-1-rows' || x.itemId === 'H2-1-rows')
    const raw = item?.remark ?? item?.conclusion
    if (!raw) return null
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}

async function handleSeedCip() {
  seedingCip.value = true
  try {
    const rows = await fetchH21CostRows()
    const r = rows?.length
      ? state.seedCipFromH21Rows(rows, 'overwrite')
      : state.seedCipFromTb('overwrite')
    if (r.applied) ElMessage.success(r.message)
    else ElMessage.warning(r.message)
  } finally {
    seedingCip.value = false
  }
}

function handleApplySignificantNote() {
  const r = state.applySignificantNoteDraft(false)
  if (r.applied) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function onH2Adjudicated(ev: Event) {
  const detail = (ev as CustomEvent).detail || {}
  const wp = String(detail.wpCode ?? detail.wp_code ?? '')
  if (wp !== 'H2') return
  const end = Number(detail.end_audited ?? detail.audited_amount ?? detail.auditedAmount) || 0
  const begin = Number(detail.begin_audited ?? detail.beginAudited) || 0
  if (!end && !begin) return
  // 仅空值时自动同步，避免覆盖手工修改
  const r = state.seedCipFromExternal(
    { endAudited: end, beginAudited: begin || end, source: 'event' },
    'fillEmpty',
  )
  if (r.applied) ElMessage.info(r.message)
}

onMounted(() => {
  window.addEventListener('substantive:adjudicated', onH2Adjudicated)
})
onUnmounted(() => {
  window.removeEventListener('substantive:adjudicated', onH2Adjudicated)
})

async function handlePublish() {
  publishing.value = true
  try {
    await state.publishAdjudicated()
  } finally {
    publishing.value = false
  }
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  if (val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(val: number | null | undefined): string {
  if (val == null) return '-'
  return `${val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}

/** 嵌套金额表：期初/期末 × 未审·账项调整·审定 + 变动 */
const AdjAmountTable = defineComponent({
  name: 'H4AdjAmountTable',
  props: {
    rows: { type: Array as () => H4AdjudicationRow[], required: true },
    isReadonly: { type: Boolean, default: false },
  },
  emits: ['cell-change', 'remove'],
  setup(p, { emit }) {
    function rowClass({ row }: { row: H4AdjudicationRow }) {
      if (row.isTotal) return 'total-row'
      if (row.isSignificant) return 'significant-row'
      return ''
    }
    function cell(
      row: H4AdjudicationRow,
      field: keyof H4AdjudicationRow,
      editable: boolean,
    ) {
      if (editable && !row.isTotal && !p.isReadonly) {
        return h(ElInputNumber, {
          modelValue: row[field] as number,
          controls: false,
          size: 'small',
          class: 'amt-input',
          onChange: (v: number | undefined) =>
            emit('cell-change', row.rowId, field, v ?? 0),
        })
      }
      const isFormula =
        field === 'beginAudited' || field === 'endAudited' || field === 'auditedChange'
      return h(
        'span',
        {
          class: isFormula ? 'formula-cell amt-cell' : 'amt-cell',
          title: isFormula ? '审定=未审+账项调整' : undefined,
        },
        fmtAmt(row[field] as number),
      )
    }
    function rateCell(row: H4AdjudicationRow) {
      return h(
        'span',
        { class: { 'rate-significant': row.isSignificant } },
        fmtRate(row.auditedChangeRate),
      )
    }

    return () =>
      h(
        ElTable,
        {
          data: p.rows,
          border: true,
          stripe: true,
          size: 'small',
          class: 'adj-table',
          rowClassName: rowClass,
        },
        {
          default: () => [
            h(ElTableColumn, { prop: 'name', label: '项目', minWidth: 140, fixed: true }),
            h(ElTableColumn, { label: '期初数', align: 'center' }, {
              default: () => [
                h(ElTableColumn, { label: '未审数', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H4AdjudicationRow }) =>
                    cell(row, 'beginUnadjusted', true),
                }),
                h(ElTableColumn, { label: '账项调整', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H4AdjudicationRow }) =>
                    cell(row, 'beginAdjustment', true),
                }),
                h(ElTableColumn, { label: '审定数', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H4AdjudicationRow }) =>
                    cell(row, 'beginAudited', false),
                }),
              ],
            }),
            h(ElTableColumn, { label: '期末数', align: 'center' }, {
              default: () => [
                h(ElTableColumn, { label: '未审数', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H4AdjudicationRow }) =>
                    cell(row, 'endUnadjusted', true),
                }),
                h(ElTableColumn, { label: '账项调整', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H4AdjudicationRow }) =>
                    cell(row, 'endAdjustment', true),
                }),
                h(ElTableColumn, { label: '审定数', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H4AdjudicationRow }) =>
                    cell(row, 'endAudited', false),
                }),
              ],
            }),
            h(ElTableColumn, { label: '本期审定数与上期审定数的比较', align: 'center' }, {
              default: () => [
                h(ElTableColumn, { label: '变动额', minWidth: 110, align: 'right' }, {
                  default: ({ row }: { row: H4AdjudicationRow }) =>
                    cell(row, 'auditedChange', false),
                }),
                h(ElTableColumn, { label: '变动率', minWidth: 90, align: 'right' }, {
                  default: ({ row }: { row: H4AdjudicationRow }) => rateCell(row),
                }),
              ],
            }),
            !p.isReadonly
              ? h(ElTableColumn, { label: '', width: 50 }, {
                  default: ({ row }: { row: H4AdjudicationRow }) =>
                    !row.isTotal
                      ? h(
                          ElButton,
                          {
                            size: 'small',
                            type: 'danger',
                            link: true,
                            onClick: () => emit('remove', row.rowId),
                          },
                          () => '✕',
                        )
                      : null,
                })
              : null,
          ],
        },
      )
  },
})
</script>

<style scoped>
.h4-tab-adjudication { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details {
  margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-secondary);
  border: 1px solid var(--el-border-color-lighter); border-radius: 4px; padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: var(--el-text-color-primary); }
.guidance-content p { margin: 6px 0 0; line-height: 1.5; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 16px; }
.section-header {
  display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;
  font-size: 14px; font-weight: 600;
}
.section-hint { font-size: 12px; color: var(--el-text-color-secondary); font-weight: 400; }
.adj-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color); cursor: help;
  font-variant-numeric: tabular-nums;
}
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.rate-significant { color: var(--el-color-danger); font-weight: 600; }
:deep(.total-row) { background-color: #f0f9eb !important; font-weight: 600; }
:deep(.significant-row) { background-color: #fef0f0 !important; }
.add-row-bar { margin-top: 8px; }
.tb-compare { display: flex; flex-wrap: wrap; gap: 16px; padding: 8px 0; }
.tb-row { display: flex; align-items: center; gap: 8px; }
.tb-label { color: var(--el-text-color-secondary); min-width: 140px; }
.tb-value { font-weight: 500; font-variant-numeric: tabular-nums; }
.cross-alert { margin-bottom: 12px; }
.net-hint { margin: 8px 0 0; font-size: 12px; color: var(--el-text-color-secondary); }
.audit-note-card { margin-bottom: 12px; }
.qual-grid { display: flex; flex-direction: column; gap: 12px; }
.qual-item label { display: block; margin-bottom: 4px; font-size: 13px; font-weight: 500; }
.req-hint { color: var(--el-color-danger); font-weight: 400; font-size: 12px; }
.conclusion-actions { display: flex; gap: 4px; }
.action-bar { display: flex; justify-content: flex-end; margin-bottom: 12px; padding-top: 8px; }
</style>
