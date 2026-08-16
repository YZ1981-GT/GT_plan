<template>
  <div class="h2-tab-impairment">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：判断在建工程是否存在减值迹象（CAS8），对存在迹象的项目按可收回金额测算减值，确认期末应提充分；长期资产减值一经确认不得转回。" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="info">测算 {{ state.calcRows.value.length }} 项</el-tag>
        <el-tag v-if="state.signYesCount.value" size="small" type="danger">
          迹象 {{ state.signYesCount.value }} 项
        </el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-15" :context-project-id="projectId" /></span>
        <el-tag v-if="state.staleSyncCount.value" size="small" type="danger">
          H2-16 未同步 {{ state.staleSyncCount.value }}
        </el-tag>
        <el-button v-if="!isReadonly" size="small" @click="handleImportBookValues">从 H2-2/H2-1 带入账面</el-button>
        <el-button v-if="!isReadonly" size="small" @click="handleImportStopped">从 H2-13 带入停工</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          :disabled="state.totalSupplement.value <= 0"
          @click="handlePushAje"
        >
          推送补提AJE至 H2-3
          <template v-if="state.totalSupplement.value > 0">
            ({{ fmtAmt(state.totalSupplement.value) }})
          </template>
        </el-button>
        <el-button size="small" circle @click="openReview('H2-15')">💬</el-button>
      </div>
    </div>

    <!-- 区域1: 减值迹象判断 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一、减值迹象判断（CAS8六项）</span>
          <div class="section-header-actions">
            <GtIndexChip value="H2-13" label="→ H2-13盘点" />
            <el-button size="small" circle @click="openReview('H2-15')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.signRows.value" border stripe size="small" class="sign-table">
        <el-table-column prop="seq" label="序号" width="50" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="indicator" label="减值迹象" min-width="250">
          <template #default="{ row }">
            <span>{{ row.indicator }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="exists" label="是否存在" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.exists" size="small" style="width:80px"
              @change="onSignChange(row.rowId, 'exists', $event)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <el-tag v-else :type="row.exists === '是' ? 'danger' : row.exists === '否' ? 'success' : 'info'" size="small">
              {{ row.exists || '待判' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="evidence" label="判断依据/说明" min-width="250">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.evidence" type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }" size="small"
              @blur="onSignChange(row.rowId, 'evidence', row.evidence)" />
            <span v-else>{{ row.evidence || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="sign-conclusion">
        <el-tag :type="state.hasImpairmentSign.value ? 'danger' : 'success'" size="default">
          {{ state.hasImpairmentSign.value ? '存在减值迹象，需进行减值测算' : '未发现减值迹象' }}
        </el-tag>
        <el-alert
          v-if="state.impairmentGateBlocked.value"
          type="error"
          :closable="false"
          show-icon
          class="gate-alert"
          title="门禁阻断：减值迹象≥2项且 H2-16 未完成。不可出具「未见异常」类结论；请先完成可收回金额测试。"
        />
        <el-alert
          v-else-if="state.needsRecoverableTest.value"
          type="warning"
          :closable="false"
          show-icon
          class="gate-alert"
          title="减值迹象≥2项：须完成 H2-16 可收回金额测试后回写本表。"
        />
      </div>
    </el-card>

    <!-- 区域2: 减值测算表（对齐 Excel H2-15） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、减值测算</span>
          <div class="section-header-actions">
            <GtIndexChip value="H2-16" label="→ H2-16可收回" />
            <el-tag size="small" type="info">⑤=MAX(③,④)　⑥=MAX(②−⑤,0)　⑧=⑥−⑦</el-tag>
          </div>
        </div>
      </template>

      <el-alert
        v-if="!state.hasImpairmentSign.value"
        type="info"
        :closable="false"
        show-icon
        class="mb-8"
        title="主体层面未发现减值迹象时，测算表可留空或仅留档；若个别工程仍有迹象，可在下方按工程填写。"
      />
      <el-alert
        v-if="state.missingRecoverableRows.value.length"
        type="warning"
        :closable="false"
        show-icon
        class="mb-8"
        :title="`有 ${state.missingRecoverableRows.value.length} 项存在迹象但尚未填③/④或回写可收回金额，请至 H2-16 测算。`"
      />
      <el-alert
        v-if="state.cas8ReversalRows.value.length"
        type="error"
        :closable="false"
        show-icon
        class="mb-8"
        :title="`发现 ${state.cas8ReversalRows.value.length} 项本期调整为负（拟冲回）。CAS8 长期资产减值不得转回，请核实⑦账面已提金额或迹象判断。`"
      />

      <el-table :data="state.calcRows.value" border stripe size="small" class="calc-table"
        :row-class-name="calcRowClass">
        <el-table-column prop="name" label="工程项目名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small"
              @change="onCalcChange(row.rowId, 'name', row.name)" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否存在减值迹象" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.hasSign" size="small" style="width:88px"
              @change="onCalcChange(row.rowId, 'hasSign', $event)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <el-tag v-else :type="row.hasSign === '是' ? 'danger' : 'info'" size="small">
              {{ row.hasSign || '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="①减值迹象描述" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.signDesc" size="small"
              :disabled="row.hasSign === '否'"
              @change="onCalcChange(row.rowId, 'signDesc', row.signDesc)" />
            <span v-else>{{ row.signDesc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="②账面价值" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.bookValue"
              size="small" class="amt-input" @change="onCalcChange(row.rowId, 'bookValue', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="可收回金额" align="center">
          <el-table-column label="③公允净额" min-width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly"
                v-model="row.fairValueNet"
                size="small"
                class="amt-input"
                :disabled="row.hasSign === '否'"
                @change="onCalcChange(row.rowId, 'fairValueNet', $event)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.fairValueNet) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="④现值" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.pvCashFlows"
                :controls="false"
                size="small"
                class="amt-input"
                :disabled="row.hasSign === '否'"
                @change="onCalcChange(row.rowId, 'pvCashFlows', $event)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.pvCashFlows) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="⑤较高者" min-width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="=MAX(③,④)">{{ fmtAmt(row.recoverableAmount) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="⑥应提减值" min-width="100" align="right">
          <template #default="{ row }">
            <span
              :class="['formula-cell', { 'error-amount': row.requiredProvision > 0 }]"
              title="=MAX(②−⑤,0)（当⑤＜②）"
            >
              {{ fmtAmt(row.requiredProvision) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="⑦账面已提" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" v-model="row.bookedProvision"
              size="small" class="amt-input" @change="onCalcChange(row.rowId, 'bookedProvision', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.bookedProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑧本期补提" min-width="100" align="right">
          <template #default="{ row }">
            <span
              :class="['formula-cell', {
                'error-amount': row.periodAdjustment > 0,
                'warn-amount': row.periodAdjustment < 0,
              }]"
              title="=⑥−⑦；CAS8不得转回，⑧＜0需关注"
            >
              {{ fmtAmt(row.periodAdjustment) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.wpIndex" size="small" placeholder="H2-16"
              @change="onCalcChange(row.rowId, 'wpIndex', row.wpIndex)" />
            <span v-else>{{ row.wpIndex || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="onCalcChange(row.rowId, 'remark', row.remark)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemoveCalc(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-line">
        <span>账面合计 <strong>{{ fmtAmt(state.totalBookValue.value) }}</strong></span>
        <span>应提合计 <strong class="error-amount">{{ fmtAmt(state.totalRequiredProvision.value) }}</strong></span>
        <span>已提合计 <strong>{{ fmtAmt(state.totalBookedProvision.value) }}</strong></span>
        <span>
          本期补提合计
          <strong :class="state.totalPeriodAdjustment.value < 0 ? 'warn-amount' : 'error-amount'">
            {{ fmtAmt(state.totalPeriodAdjustment.value) }}
          </strong>
        </span>
        <GtIndexChip v-if="state.totalSupplement.value > 0" value="H2-3" label="→ H2-3调整" />
      </div>
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddCalc">+ 新增测算项目</el-button>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>三、审计说明</span></div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述减值迹象判断依据（CAS8 六项）、测算方法（可收回金额确定）及数据来源、复核情况。" :disabled="isReadonly"
        @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>四、审计结论</span>
          <div class="section-header-actions">
            <el-button v-if="!isReadonly" size="small" @click="fillConclusionDraft">生成结论草稿</el-button>
            <el-button
              v-if="!isReadonly && state.impairmentGateBlocked.value"
              size="small"
              type="danger"
              plain
              @click="fillBlockedConclusion"
            >
              填入范围受限结论
            </el-button>
          </div>
        </div>
      </template>
      <el-alert
        v-if="state.impairmentGateBlocked.value"
        type="error"
        :closable="false"
        show-icon
        class="mb-8"
        title="当前门禁阻断清洁结论。保存「未见异常/计提充分」类表述将被拒绝。"
      />
      <el-input v-model="state.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写减值测算结论..." :disabled="isReadonly"
        @blur="onSaveConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>编制路径：主体迹象判断 → 从 H2-2/H2-1 带入②/⑦ → 填③/④（或 H2-16 回写）→ 核对⑥与⑦ → ⑧≠0 推送 AJE 至 H2-3</li>
        <li>⑤=MAX(③公允净额, ④预计未来现金流量现值)；⑥=MAX(②−⑤, 0)（Excel 表头「⑤−②」为笔误，公式以②−⑤为准）</li>
        <li>工程「是否存在减值迹象=否」时，不做减值测试，⑧置0（维持已提现状）</li>
        <li>CAS8：在建工程等长期资产减值一经确认不得转回；⑧为负时须核实，不得直接冲回损益</li>
        <li>迹象≥2项须完成 H2-16；停工可从 H2-13 带入后，用「从 H2-2/H2-1 带入账面」补齐②/⑦</li>
        <li>⑧&gt;0 时「推送补提AJE至 H2-3」生成：借6701资产减值损失 / 贷1604在建工程减值准备（重复推送会替换旧自动草稿）</li>
        <li>H2-16 回写后本表工具栏会提示「未同步」项；请保持③/④与 H2-16 一致</li>
        <li>测算结果应与 H2-1 审定表减值准备列勾稽</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H2TabImpairment.vue — H2-15 减值测算
 * 双区域(迹象判断6项+测算表对齐Excel) + GtIndexChip→H2-16/H2-13
 * Spec: Task 4.18 | Requirements: 12.1-12.2, 12.5-12.7
 */
import { inject, toRef, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useH2Impairment } from '../../composables/useH2Impairment'
import { buildBlockedImpairmentConclusion } from '../../composables/h2ImpairmentGate'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2Impairment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  section: 'impairment',
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

function onSignChange(rowId: string, field: string, value: any) {
  state.updateSignCell(rowId, field, value)
}

function onCalcChange(rowId: string, field: string, value: any) {
  state.updateCalcCell(rowId, field, value)
}

function handleAddCalc() {
  state.addCalcRow()
}

function handleRemoveCalc(rowId: string) {
  state.removeCalcRow(rowId)
}

function handleImportStopped() {
  const res = state.importStoppedFromH213()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function handleImportBookValues() {
  const res = state.importBookValuesFromH2()
  if (res.ok) {
    if (res.h1Diff != null && Math.abs(res.h1Diff) >= 0.01) ElMessage.warning(res.message)
    else ElMessage.success(res.message)
  } else {
    ElMessage.warning(res.message)
  }
}

function handlePushAje() {
  const res = state.pushAjeDraftToH23()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function fillConclusionDraft() {
  const signs = state.signYesCount.value
  const n = state.calcRows.value.length
  const adj = state.totalPeriodAdjustment.value
  const rev = state.cas8ReversalRows.value.length
  let text = ''
  if (state.impairmentGateBlocked.value) {
    text = buildBlockedImpairmentConclusion(signs)
  } else if (!state.hasImpairmentSign.value && n === 0) {
    text = '经按 CAS8 六项迹象检查，未发现在建工程减值迹象，本期无需进行减值测算，减值准备计提充分。'
  } else {
    text = `经检查，主体层面识别减值迹象 ${signs} 项，对 ${n} 个工程项目测算可收回金额。`
    text += `期末应提减值准备合计 ${fmtAmt(state.totalRequiredProvision.value)}，账面已提 ${fmtAmt(state.totalBookedProvision.value)}，本期应补提 ${fmtAmt(adj)}。`
    if (rev > 0) {
      text += `另有 ${rev} 项测算结果低于账面已提，按 CAS8 长期资产减值不得转回，已提示关注，未建议冲回。`
    }
    text += state.needsRecoverableTest.value
      ? '可收回金额已通过 H2-16 复核后回写。综上，除上述关注事项外，减值准备计提在所有重大方面公允。'
      : '综上，减值准备计提在所有重大方面公允。'
  }
  const res = state.saveConclusion(text)
  if (res.ok) ElMessage.success('已生成结论草稿，请复核后定稿')
  else ElMessage.error(res.message || '结论保存失败')
}

function fillBlockedConclusion() {
  const text = buildBlockedImpairmentConclusion(state.signYesCount.value)
  const res = state.saveConclusion(text)
  if (res.ok) ElMessage.warning('已填入范围受限结论')
  else ElMessage.error(res.message || '结论保存失败')
}

function onSaveConclusion() {
  const res = state.saveConclusion(state.conclusion.value)
  if (!res.ok) {
    ElMessage.error(res.message || '结论保存失败')
  }
}

function calcRowClass({ row }: { row: { hasSign: string; periodAdjustment: number } }) {
  if (row.periodAdjustment < 0) return 'row-reversal'
  if (row.hasSign === '是') return 'row-has-sign'
  return ''
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-impairment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.section-header-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.sign-table, .calc-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help; font-variant-numeric: tabular-nums;
}
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.warn-amount { color: var(--el-color-warning); font-weight: 600; }
.sign-conclusion {
  margin-top: 12px; display: flex; flex-direction: column; align-items: center; gap: 8px;
}
.gate-alert, .mb-8 { margin-bottom: 8px; width: 100%; }
.summary-line {
  display: flex; flex-wrap: wrap; gap: 16px;
  padding: 12px 0; font-size: var(--wp-font-size, 13px);
  border-top: 1px solid var(--el-border-color-lighter); margin-top: 12px;
}
.add-row-bar { margin-top: 12px; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
:deep(.row-has-sign) { background: var(--el-color-danger-light-9); }
:deep(.row-reversal) { background: var(--el-color-warning-light-9); }
</style>
