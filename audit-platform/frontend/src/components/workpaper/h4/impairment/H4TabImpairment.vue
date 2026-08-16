<template>
  <div class="h4-tab-impairment">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：按 CAS8 判断工程物资减值迹象，对存在迹象的物资比较账面价值与可收回金额，核实期末应提充分；长期资产减值一经确认不得转回。可收回明细测算见 H4-8。"
    />

    <el-alert
      v-if="concernN > 0"
      type="warning"
      :closable="false"
      show-icon
      class="objective-alert"
      :title="`H4-6 已推送 ${concernN} 项减值关注（闲置/积压/毁损/盘亏），可一键落成测算行`"
    >
      <template #default>
        <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'H4-6')">← 查看 H4-6</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          style="margin-left:8px"
          @click="handleImportConcerns"
        >
          一键落成测算行
        </el-button>
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:H4-7" :context-project-id="projectId" /></span>
        <el-tag size="small">测算 {{ state.calcRows.value.length }} 项</el-tag>
        <el-tag v-if="state.signYesCount.value" size="small" type="danger">迹象 {{ state.signYesCount.value }} 项</el-tag>
        <el-tag v-if="state.missingRecoverableRows.value.length" size="small" type="warning">
          缺 H4-8 {{ state.missingRecoverableRows.value.length }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:H4-8" :context-project-id="projectId" />
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', '可收回金额测试表H4-8')">→ H4-8</el-tag>
        <el-button v-if="!isReadonly" size="small" @click="handleImportH42">从 H4-2 带入</el-button>
        <el-button v-if="!isReadonly" size="small" @click="handleImportH41">从 H4-1 带入⑦</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          :disabled="concernN <= 0"
          @click="handleImportConcerns"
        >
          自 H4-6 引入关注{{ concernN ? `（${concernN}）` : '' }}
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          :disabled="state.totalSupplement.value <= 0"
          @click="handlePushAje"
        >
          推送补提AJE
          <template v-if="state.totalSupplement.value > 0">({{ fmtAmt(state.totalSupplement.value) }})</template>
        </el-button>
        <el-button size="small" circle @click="openReview('H4-7-impairment')">💬</el-button>
      </div>
    </div>

    <div class="methodology-context">
      <p>
        <strong>CAS8：</strong>⑤可收回 = MAX(③公允净额, ④DCF)；⑥应提 = MAX(②账面−⑤, 0)；⑧补提 = ⑥−⑦。
        ③/④由 H4-8 测算回写；⑧&lt;0 不得转回。
      </p>
    </div>

    <div class="section-header mode-row">
      <span>减值测算表 H4-7</span>
      <el-segmented
        :model-value="dualMode.currentMode.value"
        :options="dualMode.modeOptions"
        size="small"
        @change="dualMode.onModeChange"
      />
    </div>

    <GtOnlyOfficeSheet
      v-if="dualMode.currentMode.value === 'onlyoffice'"
      :wp-id="wpId"
      :sheet-name="sheetName"
      :project-id="projectId"
      class="impairment-oo"
    />

    <template v-else>
      <el-card shadow="never" class="block-card">
        <template #header>
          <div class="section-header"><span>一、减值迹象判断（CAS8 六项，贴合工程物资）</span></div>
        </template>
        <el-table :data="state.signRows.value" border stripe size="small">
          <el-table-column label="序号" width="50" align="center">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="indicator" label="减值迹象" min-width="280" />
          <el-table-column label="是否存在" width="110" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.exists"
                size="small"
                style="width: 90px"
                @change="(v: string) => state.updateSignCell(row.rowId, 'exists', v)"
              >
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
                <el-option label="不适用" value="不适用" />
              </el-select>
              <el-tag v-else :type="row.exists === '是' ? 'danger' : row.exists === '否' ? 'success' : 'info'" size="small">
                {{ row.exists || '待判' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="判断依据" min-width="200">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.evidence"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }"
                size="small"
                @update:model-value="(v: string) => { row.evidence = v }"
                @blur="state.updateSignCell(row.rowId, 'evidence', row.evidence)"
              />
              <span v-else>{{ row.evidence || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never" class="block-card">
        <template #header>
          <div class="section-header">
            <span>二、减值测算明细</span>
            <el-button size="small" :disabled="isReadonly" @click="state.addCalcRow()">+ 新增行</el-button>
          </div>
        </template>
        <el-table :data="state.calcRows.value" border size="small" empty-text="暂无测算行，可从 H4-2 带入或新增；有迹象请完成 H4-8 后回写">
          <el-table-column label="类别" width="100">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.category"
                size="small"
                clearable
                filterable
                allow-create
                @change="(v: string) => state.updateCalcCell(row.rowId, 'category', v)"
              >
                <el-option v-for="c in H4_MATERIAL_CATEGORIES" :key="c" :label="c" :value="c" />
              </el-select>
              <span v-else>{{ row.category || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="物资名称" min-width="120">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.name"
                size="small"
                @change="(v: string) => state.updateCalcCell(row.rowId, 'name', v)"
              />
              <span v-else>{{ row.name || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="迹象" width="72" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                :model-value="row.hasSign"
                size="small"
                clearable
                @change="(v: string) => state.updateCalcCell(row.rowId, 'hasSign', v || '')"
              >
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
              <span v-else>{{ row.hasSign || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="②账面" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly"
                :model-value="row.bookValue"
                size="small"
                @change="(v: number | undefined) => state.updateCalcCell(row.rowId, 'bookValue', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.bookValue) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="③公允净额" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmt(row.fairValueNet) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="④DCF" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmt(row.pvCashFlows) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="⑤可收回" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell highlight">{{ fmtAmt(row.recoverableAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="⑥应提" width="90" align="right">
            <template #default="{ row }">
              <span class="formula-cell" :class="{ 'diff-warn': row.requiredProvision > 0 }">
                {{ fmtAmt(row.requiredProvision) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="⑦已提" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.bookedProvision"
                :controls="false"
                size="small"
                @change="(v: number | undefined) => state.updateCalcCell(row.rowId, 'bookedProvision', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.bookedProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="⑧补提" width="90" align="right">
            <template #default="{ row }">
              <span :class="{ 'diff-warn': row.periodAdjustment > 0, 'error-amount': row.periodAdjustment < 0 }">
                {{ fmtAmt(row.periodAdjustment) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="索引" width="64" align="center">
            <template #default="{ row }">{{ row.wpIndex || '-' }}</template>
          </el-table-column>
          <el-table-column label="" width="52" align="center" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="danger" link :disabled="isReadonly" @click="state.removeCalcRow(row.rowId)">
                删
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-alert
          v-if="state.cas8ReversalRows.value.length"
          type="error"
          :closable="false"
          show-icon
          class="mt-8"
          :title="`有 ${state.cas8ReversalRows.value.length} 行⑧为负：CAS8 长期资产减值不得转回，请复核已提或处置结转。`"
        />
      </el-card>

      <el-card shadow="never" class="block-card">
        <template #header><span style="font-weight:600">汇总</span></template>
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="②账面合计">{{ fmtAmt(state.totalBookValue.value) }}</el-descriptions-item>
          <el-descriptions-item label="⑤可收回合计">{{ fmtAmt(state.totalRecoverable.value) }}</el-descriptions-item>
          <el-descriptions-item label="⑥应提合计">
            <span :class="{ 'diff-warn': state.totalRequiredProvision.value > 0 }">
              {{ fmtAmt(state.totalRequiredProvision.value) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="⑦已提合计">{{ fmtAmt(state.totalBookedProvision.value) }}</el-descriptions-item>
          <el-descriptions-item label="⑧补提合计">
            <span :class="{ 'diff-warn': state.totalSupplement.value > 0 }">
              {{ fmtAmt(state.totalSupplement.value) }}
            </span>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card shadow="never" class="audit-note-card">
        <template #header><div class="section-header"><span>审计说明</span></div></template>
        <el-input
          :model-value="state.auditNote.value"
          type="textarea"
          :autosize="{ minRows: 4 }"
          :disabled="isReadonly"
          placeholder="①六项迹象结论与依据；②测试单元；③可收回方法及 H4-8/评估来源；④⑧≠0 差异原因；⑤领用结转减值是否同步。"
          @change="(v: string) => state.saveNote(v)"
        />
      </el-card>

      <el-card shadow="never" class="audit-note-card">
        <template #header>
          <div class="section-header">
            <span>审计结论</span>
            <el-button size="small" :disabled="isReadonly" @click="handleDraftConclusion">生成结论草稿</el-button>
          </div>
        </template>
        <el-input
          :model-value="state.conclusion.value"
          type="textarea"
          :autosize="{ minRows: 3 }"
          :disabled="isReadonly"
          placeholder="请填写审计结论..."
          @change="(v: string) => state.saveConclusion(v)"
        />
      </el-card>
    </template>

    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>有减值迹象的物资应完成 H4-8 并回写本表③/④/⑤。</li>
        <li>可收回金额 = max(公允价值−处置费用, 预计未来现金流量现值)。</li>
        <li>减值一经确认不得转回；领用/结转时对应减值准备应一并结转。</li>
        <li>⑧&gt;0 可推送补提 AJE（6701/1605）至 H4-3。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H4TabImpairment.vue — H4-7 减值测算表
 * CAS8 迹象 + ①~⑧测算 + H4-2/H4-1 带入 + H4-8 回写接收 + 推送 AJE
 */
import { computed, inject, toRef, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { useH4Impairment, H4_MATERIAL_CATEGORIES } from '../../composables/useH4Impairment'
import { useH4DualMode } from '../../composables/useH4DualMode'
import GtIndexChip from '../../GtIndexChip.vue'
import { eventBus } from '@/utils/eventBus'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('../../GtOnlyOfficeSheet.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  sheetName: string
}>()

const emit = defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', () => {})

const dualMode = useH4DualMode({
  wpId: toRef(props, 'wpId'),
  sheetName: toRef(props, 'sheetName'),
})

const state = useH4Impairment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const concernN = computed(() => state.stocktakeConcernCount())

function handleImportH42() {
  const res = state.importFromH42()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function handleImportH41() {
  const res = state.importBookedFromH41()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function handleImportConcerns() {
  const res = state.importFromStocktakeConcerns()
  if (res.added + res.refreshed > 0) ElMessage.success(res.message)
  else ElMessage.info(res.message)
}

function handlePushAje() {
  const res = state.pushAjeDraftToH43()
  if (res.ok) {
    ElMessage.success(res.message)
    // 推送减值信号到 K11 资产减值损失（对齐 F2/H1/H3/H8/I1 范式）
    eventBus.emit('impairment:calculated', {
      wpCode: 'H4',
      supplement: state.totalSupplement.value,
      totalRequiredProvision: state.totalRequiredProvision.value,
      accountCode: '1605',
      timestamp: Date.now(),
    })
  } else {
    ElMessage.warning(res.message)
  }
}

function handleDraftConclusion() {
  state.fillConclusionDraft()
  ElMessage.success('已生成结论草稿')
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
.h4-tab-impairment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.nav-chip { cursor: pointer; }
.methodology-context {
  border-left: 3px solid #f0a020; background: #fdf8e8;
  padding: 12px 16px; margin-bottom: 16px; border-radius: 4px;
  font-size: 12px; line-height: 1.6; color: #92400e;
}
.mode-row { margin-bottom: 12px; }
.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600; gap: 8px; flex-wrap: wrap;
}
.impairment-oo { min-height: 500px; margin-bottom: 12px; }
.block-card, .audit-note-card { margin-bottom: 12px; }
.amt-cell, .formula-cell { font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.highlight { color: #409eff; font-weight: 600; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.mt-8 { margin-top: 8px; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
