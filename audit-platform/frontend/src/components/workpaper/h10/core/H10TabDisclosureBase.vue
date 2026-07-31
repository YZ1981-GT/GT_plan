<template>
  <div class="h10-disclosure" :data-testid="variant === 'listed' ? 'h10-disclosure-listed' : 'h10-disclosure-soe'">
    <div class="section-head">
      <h3 class="sheet-title">{{ dis.title.value }}</h3>
      <div class="head-actions">
        <GtIndexChip v-if="noteChip" :value="noteChip" :context-project-id="projectId" />
        <el-button
          v-if="!isReadonly && projectId"
          size="small"
          type="primary"
          plain
          data-testid="h10-disclosure-sync-notes"
          :loading="isSyncing"
          @click="syncToNotes"
        >同步到附注</el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote(variant)">↩ 跳转回附注</el-button>
        <el-button size="small" :disabled="isReadonly" data-testid="h10-disclosure-pull-adj" @click="dis.pullFromAdjudication()">
          从审定表带入
        </el-button>
        <el-button size="small" :loading="dis.aiLoading.value" :disabled="isReadonly" data-testid="h10-disclosure-ai-btn" @click="dis.generateAiConclusion()">🤖 AI</el-button>
        <GtReviewTrigger :section-id="variant === 'listed' ? 'H10-disclosure-listed' : 'H10-disclosure-soe'" />
      </div>
    </div>

    <details class="guidance-details" open>
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 资产处置损益（6115）本期合计应与 H10-1 审定数一致；点「从审定表带入」按分项同步，再「同步到附注」写入附注模块「{{ noteSectionLabel }}」。</p>
        <p>2. 不构成业务的资产组处置（含持有待售后出售）计入本项目；构成业务（子公司/分公司）的处置计入投资收益。</p>
        <p>3. 单项投资性房地产处置计入「其他业务收入/成本」，不计入本项目。</p>
        <p v-if="variant === 'listed'">4. 试运行销售：与日常活动相关的计入营业收入/成本；非日常活动的计入资产处置损益，并须单独披露收入与成本（解释第15号）。</p>
        <p v-if="variant === 'soe'">4. 「计入当期非经常性损益的金额」按证监会非经常性损益口径填列；处置长期资产损益通常属非经常性损益。</p>
        <p>5. 债务重组、非货币性资产交换中因处置非流动资产产生的损益包含在本项目；使用权资产、油气资产处置亦计入本项目；无发生额项目可不披露。</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" class="objective-alert"
      :title="`审计目标：核实资产处置损益附注披露的完整性与准确性，本期/上期发生额与审定表一致${variant === 'soe' ? '，非经常性损益列示恰当' : '，试运行销售单独披露充分'}。`" />

    <el-alert v-if="dis.adjudicatedAmount.value != null" :type="reconcileAlertType" :closable="false" class="sync-hint">
      已同步审定数（6115）：{{ fmt(dis.adjudicatedAmount.value) }}
      ；披露本期合计 {{ fmt(dis.disclosureTotal.value.currentAmount) }}
      <template v-if="dis.reconcileDiff.value != null && Math.abs(dis.reconcileDiff.value) > 0.005">
        ；差异 {{ fmt(dis.reconcileDiff.value) }}
      </template>
      <el-button link size="small" @click="dis.pullLatestAdjudicated()">刷新</el-button>
    </el-alert>

    <el-alert
      v-if="variant === 'soe' && lastSyncedNonRecurring != null"
      type="info"
      :closable="false"
      class="sync-hint"
      data-testid="h10-soe-nonrecurring-hint"
    >
      上次同步附注后：本期合计 {{ fmt(lastSyncedNonRecurring.current) }}，非经常性损益列合计 {{ fmt(lastSyncedNonRecurring.nonRecurring) }}
      <template v-if="Math.abs(lastSyncedNonRecurring.diff) > 0.005">
        （差额 {{ fmt(lastSyncedNonRecurring.diff) }}，请确认是否存在经常性处置损益）
      </template>
      <template v-else>；两列勾稽一致。</template>
    </el-alert>

    <div class="table-toolbar">
      <el-switch
        :model-value="dis.showEmptyRows.value"
        :disabled="isReadonly"
        inline-prompt
        active-text="显示空行"
        inactive-text="隐藏空行"
        data-testid="h10-disclosure-empty-toggle"
        @update:model-value="dis.setShowEmptyRows"
      />
      <span v-if="dis.hiddenEmptyCount.value > 0" class="toolbar-hint">
        已隐藏 {{ dis.hiddenEmptyCount.value }} 个无发生额项目
      </span>
    </div>

    <el-table :data="dis.displayRows.value" border size="small" style="font-size:13px" max-height="480"
      :row-class-name="({ row }) => rowClass(row.rowKey)">
      <el-table-column label="项目" prop="label" min-width="260" fixed>
        <template #default="{ row }">
          <span :class="{ 'trial-label': row.rowKey === 'trial_operation_sales' }">{{ row.label }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期发生额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'total' && !(variant === 'listed' && row.rowKey === 'trial_operation_sales') && !isReadonly"
            :model-value="row.currentAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'currentAmount', v ?? 0)"
          />
          <span v-else :class="{ 'formula-cell': (variant === 'listed' && row.rowKey === 'trial_operation_sales') || row.rowKey === 'total' }">
            {{ fmt(row.currentAmount) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="上期发生额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowKey !== 'total' && !(variant === 'listed' && row.rowKey === 'trial_operation_sales') && !isReadonly"
            :model-value="row.priorAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'priorAmount', v ?? 0)"
          />
          <span v-else :class="{ 'formula-cell': (variant === 'listed' && row.rowKey === 'trial_operation_sales') || row.rowKey === 'total' }">
            {{ fmt(row.priorAmount) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column v-if="variant === 'soe'" label="计入当期非经常性损益的金额" width="160" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.nonRecurringAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'nonRecurringAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.nonRecurringAmount ?? 0) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动额" width="110" align="right">
        <template #default="{ row }"><span class="formula-cell">{{ fmt(row.changeAmount) }}</span></template>
      </el-table-column>
    </el-table>

    <!-- 上市：试运行销售收入/成本明细 -->
    <div v-if="variant === 'listed'" class="trial-block" data-testid="h10-disclosure-trial">
      <div class="trial-head">
        <span class="trial-title">试运行销售损益明细</span>
        <span class="trial-hint">净额（收入−成本）自动回写上表「试运行销售损益」</span>
      </div>
      <el-alert
        v-if="Math.abs(dis.trialNetTotal.value) > 0.005"
        type="warning"
        :closable="false"
        show-icon
        class="trial-ie15"
        data-testid="h10-trial-ie15-hint"
      >
        解释第15号：若试运行销售与日常活动相关，相关收入/成本应列报营业收入，勿与 6115 双计。请核对
        <GtIndexChip value="wp:D4" :context-project-id="projectId" label="D4 营业收入" />
        。本期试运行净额 {{ fmt(dis.trialNetTotal.value) }}。
      </el-alert>
      <el-table :data="dis.trialDisplayRows.value" border size="small" style="font-size:13px"
        :row-class-name="({ row }) => row.rowKey === 'total' ? 'total-row' : ''">
        <el-table-column label="项目" prop="label" min-width="180" fixed />
        <el-table-column label="本期发生额" align="center">
          <el-table-column label="收入" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentIncome" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => dis.updateTrialField(row.rowKey, 'currentIncome', v ?? 0)" />
              <span v-else>{{ fmt(row.currentIncome) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="成本" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentCost" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => dis.updateTrialField(row.rowKey, 'currentCost', v ?? 0)" />
              <span v-else>{{ fmt(row.currentCost) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="上期发生额" align="center">
          <el-table-column label="收入" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.priorIncome" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => dis.updateTrialField(row.rowKey, 'priorIncome', v ?? 0)" />
              <span v-else>{{ fmt(row.priorIncome) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="成本" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.priorCost" size="small" :controls="false" style="width:100%"
                @update:model-value="(v: number) => dis.updateTrialField(row.rowKey, 'priorCost', v ?? 0)" />
              <span v-else>{{ fmt(row.priorCost) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </div>

    <el-card shadow="never" class="note-card">
      <template #header>附注文本</template>
      <el-input :model-value="dis.noteText.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" placeholder="写入附注模块的披露说明（编辑后自动联动；也可点「同步到附注」推送结构化表格）。"
        @update:model-value="dis.updateNoteText" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述附注披露与审定表的核对情况、披露项目的完整性及口径判断。"
        @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：附注披露完整、准确，与审定表勾稽一致，列报口径恰当。"
        @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { useH10Disclosure } from '../../composables/useH10Disclosure'
import { buildH10SyncPayloads } from '../../composables/h10DisclosureSyncPayload'
import { H10_NOTE_SECTION, H10_NOTE_SECTION_DISPLAY } from '../../composables/h10NoteSectionMap'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import { api } from '@/services/apiProxy'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  variant: 'listed' | 'soe'
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  applicableStandards?: string[]
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())

const wrappedDebouncedSave: typeof props.debouncedSave = (itemId, data) => {
  props.debouncedSave(itemId, data)
  autoSync.scheduleAutoSync(syncToNotes)
}

const dis = useH10Disclosure({
  variant: props.variant,
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: wrappedDebouncedSave,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  isReadonly: toRef(props, 'isReadonly'),
})

const isSyncing = ref(false)
// 定位用：必须逐字等于模板 section_number（listed 侧是 md 截断值 `三、资产处置收益（损`）
const noteSectionId = H10_NOTE_SECTION[props.variant]
// 展示用：截断值直接显示不可读
const noteSectionLabel = H10_NOTE_SECTION_DISPLAY[props.variant]
const noteChip = computed(() => `Note:${noteSectionId}`)

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'H10', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}
const reconcileAlertType = computed(() => {
  const d = dis.reconcileDiff.value
  if (d == null) return 'success'
  return Math.abs(d) > 0.005 ? 'warning' : 'success'
})

const lastSyncedNonRecurring = ref<{ current: number; nonRecurring: number; diff: number } | null>(null)

async function syncToNotes(): Promise<void> {
  if (isSyncing.value || props.isReadonly || !props.projectId || !props.wpId) return
  const payloads = buildH10SyncPayloads(
    props.wpId,
    props.variant,
    props.applicableStandards ?? [],
    dis.getSyncSnapshot(),
  )
  if (!payloads.length) {
    ElMessage.warning('当前项目准则不适用本口径附注同步')
    return
  }
  isSyncing.value = true
  try {
    let rows = 0
    for (const payload of payloads) {
      const result: any = await api.post(
        `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
        payload,
      )
      const data = result?.data ?? result
      rows += Number(data?.rows_synced ?? 0)
    }
    dis.publishNoteUpdate()
    if (props.variant === 'soe') {
      const current = dis.disclosureTotal.value.currentAmount
      const nonRecurring = Number(dis.disclosureTotal.value.nonRecurringAmount ?? 0)
      lastSyncedNonRecurring.value = {
        current,
        nonRecurring,
        diff: Math.round((current - nonRecurring) * 100) / 100,
      }
    }
    ElMessage.success(`已同步 ${rows} 行到附注「${noteSectionLabel}」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function rowClass(rowKey: string): string {
  if (rowKey === 'total') return 'total-row'
  if (rowKey === 'trial_operation_sales') return 'trial-row'
  return ''
}

// 多变体（listed/soe）后缀区分 item_id，防串写
const auditNote = ref('')
const auditConclusion = ref('')
const noteKey = () => `H10-disclosure-${props.variant}-audit-note`
const conclusionKey = () => `H10-disclosure-${props.variant}-audit-conclusion`

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const key = noteKey()
  props.allResponses.set(key, { item_id: key, conclusion: null, remark: val })
  props.debouncedSave(key, { conclusion: null, remark: val })
  autoSync.scheduleAutoSync(syncToNotes)
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const key = conclusionKey()
  props.allResponses.set(key, { item_id: key, conclusion: null, remark: val })
  props.debouncedSave(key, { conclusion: null, remark: val })
  autoSync.scheduleAutoSync(syncToNotes)
}

function hydrate(): void {
  const n = props.allResponses.get(noteKey())
  auditNote.value = n?.remark ?? ''
  const c = props.allResponses.get(conclusionKey())
  auditConclusion.value = c?.remark ?? ''
}

onMounted(hydrate)
watch(() => props.variant, hydrate)

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h10-disclosure { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.sheet-title { margin: 0; font-size: 15px; }
.sync-hint { margin-bottom: 8px; }
.formula-cell { border-bottom: 1px dashed #999; }
.note-card { margin-top: 8px; }
.guidance-details { margin-bottom: 8px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 8px; }
.table-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.toolbar-hint { font-size: 12px; color: #909399; }
.trial-block { margin-top: 16px; }
.trial-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 8px; }
.trial-title { font-weight: 600; font-size: 14px; color: #c45656; }
.trial-hint { font-size: 12px; color: #909399; }
.trial-ie15 { margin-bottom: 8px; }
.trial-label { color: #c45656; font-weight: 500; }
:deep(.total-row) { font-weight: 600; background: #f5f7fa; }
:deep(.trial-row) { background: #fef0f0; }
</style>
