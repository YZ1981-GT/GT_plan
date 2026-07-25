<template>
  <div class="g11-disclosure" :data-testid="variant === 'listed' ? 'g11-disclosure-listed' : 'g11-disclosure-soe'">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表按{{ variant === 'listed' ? '上市公司' : '国有企业' }}附注格式列示投资收益的构成明细（本期/上期发生额及变动）。</p>
        <p>2. 各分项发生额应与 G11-1 审定表、G11-2 明细分析表勾稽一致；合计应等于利润表「投资收益」项目金额。</p>
        <p>3. 可点击「从 G11-1/G11-2 分项带入」自动填充主表行（明细优先，审定兜底）；「其中：」「减：」展开行需手工填写且不计入合计。</p>
        <p v-if="variant === 'listed'">4. 处置业务（含持有待售）损益整笔计入投资收益并结转相关 OCI；有套期业务时注意与附注九、3 一致。</p>
        <p v-else>4. 若投资收益汇回有重大限制的，应予以说明；若不存在此类重大限制，也应做出说明。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实投资收益附注披露的构成、金额及分类完整准确，与审定表/明细表及利润表勾稽一致，符合列报要求。"
    />

    <div class="section-head">
      <h3 class="sheet-title">{{ dis.title.value }}</h3>
      <div class="head-actions">
        <G11ImportExportDropdown
          :wp-id="wpId"
          :sheet="variant === 'listed' ? '附注上市' : '附注国企'"
          @imported="onDisclosureImported"
        />
        <el-button
          v-if="!isReadonly && projectId"
          size="small"
          type="primary"
          plain
          data-testid="g11-disclosure-sync-notes"
          :loading="isSyncing"
          @click="syncToNotes"
        >同步到附注</el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="!projectId"
          data-testid="g11-disclosure-jump-note"
          @click="jumpToNote(variant)"
        >↩ 跳转回附注</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          data-testid="g11-disclosure-pull-adj"
          @click="dis.pullFromAdjudication()"
        >↓ 从 G11-1/G11-2 分项带入</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          plain
          data-testid="g11-disclosure-generate-note"
          @click="dis.generateNoteFromStore(true)"
        >生成附注文本</el-button>
        <el-button
          size="small"
          :loading="dis.aiLoading.value"
          :disabled="isReadonly"
          data-testid="g11-disclosure-ai-note"
          @click="dis.generateAiConclusion()"
        >🤖 AI 审计说明</el-button>
        <GtReviewTrigger :section-id="variant === 'listed' ? 'G11-disclosure-listed' : 'G11-disclosure-soe'" />
      </div>
    </div>

    <el-alert
      v-if="dis.adjudicatedAmount.value != null && !dis.hasAdjCrossMismatch.value"
      type="success"
      :closable="false"
      class="sync-hint"
    >
      已同步审定数（6111）：{{ fmt(dis.adjudicatedAmount.value) }}；附注{{ dis.colLabels.value.current }}合计
      {{ fmt(dis.disclosureCurrentSum.value) }} 勾稽一致。
      <el-button link size="small" @click="dis.pullLatestAdjudicated(false)">刷新</el-button>
    </el-alert>

    <el-alert
      v-if="dis.adjChangedSincePull.value"
      type="info"
      :closable="false"
      show-icon
      class="sync-hint"
      data-testid="g11-disclosure-adj-stale"
    >
      G11-1 审定数已更新为 {{ fmt(dis.adjudicatedAmount.value ?? 0) }}，披露分项尚未重新带入（不会自动覆盖手工数）。
      <el-button
        v-if="!isReadonly"
        link
        size="small"
        type="primary"
        @click="dis.pullFromAdjudication()"
      >重新分项带入</el-button>
    </el-alert>

    <el-alert
      v-if="dis.pullSummary.value"
      :type="dis.lastPullUsedResidual.value ? 'warning' : 'info'"
      :closable="true"
      class="sync-hint"
      data-testid="g11-disclosure-pull-meta"
      @close="dis.clearPullSummary()"
    >
      带入来源：{{ dis.pullSummary.value }}
    </el-alert>

    <el-alert
      v-if="dis.hasAdjCrossMismatch.value"
      type="warning"
      :closable="false"
      show-icon
      class="sync-hint"
      data-testid="g11-disclosure-adj-cross"
    >
      附注{{ dis.colLabels.value.current }}合计 {{ fmt(dis.disclosureCurrentSum.value) }} 与 G11-1 审定数
      {{ fmt(dis.adjudicatedAmount.value ?? 0) }} 差异
      {{ fmt(dis.adjCrossVariance.value ?? 0) }}。
      <el-button
        v-if="!isReadonly"
        link
        size="small"
        type="primary"
        data-testid="g11-disclosure-sync-adj"
        @click="dis.pullFromAdjudication()"
      >从 G11-1/G11-2 分项带入</el-button>
      <el-button link size="small" @click="dis.pullLatestAdjudicated(false)">刷新</el-button>
    </el-alert>

    <el-table :data="dis.displayRows.value" border size="small" style="font-size:13px" max-height="480"
      :row-class-name="({ row }) => rowClass(row)">
      <el-table-column :label="dis.colLabels.value.item" prop="label" min-width="220" fixed />
      <el-table-column :label="dis.colLabels.value.current" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'currentAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.currentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="dis.colLabels.value.prior" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.priorAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'priorAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动额" width="110" align="right">
        <template #default="{ row }"><span class="formula-cell">{{ fmt(row.changeAmount) }}</span></template>
      </el-table-column>
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.remark" size="small"
            @update:model-value="(v: string) => dis.updateField(row.rowKey, 'remark', v)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 上市：处置交易性金融资产明细（Excel 注1） -->
    <template v-if="variant === 'listed'">
      <div class="sub-section-head">
        <h4 class="sub-title">注：处置交易性金融资产取得的投资收益</h4>
      </div>
      <el-alert type="warning" :closable="false" show-icon class="sync-hint">
        {{ dis.tradingDisposeHint }}
      </el-alert>
      <el-alert
        v-if="dis.hasTradingDisposeMismatch.value"
        type="warning"
        :closable="false"
        show-icon
        class="sync-hint"
        data-testid="g11-trading-dispose-cross"
      >
        子表合计 {{ fmt(dis.tradingDisposeDisplayRows.value.find((r) => r.rowKey === 'total')?.currentAmount ?? 0) }}
        与主表「处置交易性金融资产」{{ fmt(dis.tradingDisposeMainAmount.value) }}
        差异 {{ fmt(dis.tradingDisposeCrossVariance.value ?? 0) }}。
      </el-alert>
      <el-table
        :data="dis.tradingDisposeDisplayRows.value"
        border
        size="small"
        style="font-size:13px"
        max-height="280"
        data-testid="g11-trading-dispose-table"
        :row-class-name="({ row }) => row.rowKey === 'total' ? 'total-row' : ''"
      >
        <el-table-column label="项目" prop="label" min-width="280" />
        <el-table-column :label="dis.colLabels.value.current" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'total' && !isReadonly"
              :model-value="row.currentAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateTradingDisposeField(row.rowKey, 'currentAmount', v ?? 0)"
            />
            <span v-else>{{ fmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.prior" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'total' && !isReadonly"
              :model-value="row.priorAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateTradingDisposeField(row.rowKey, 'priorAmount', v ?? 0)"
            />
            <span v-else>{{ fmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动额" width="110" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.changeAmount) }}</span></template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 国企：投资收益汇回重大限制说明 -->
    <el-card v-if="variant === 'soe'" shadow="never" class="note-card" data-testid="g11-repatriation-note">
      <template #header>投资收益汇回限制说明</template>
      <el-input
        :model-value="dis.repatriationNote.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="若投资收益汇回有重大限制的，应予以说明；若不存在此类重大限制，也应做出说明。"
        @update:model-value="dis.updateRepatriationNote"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>附注文本</template>
      <el-input :model-value="dis.noteText.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" @update:model-value="dis.updateNoteText" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：可概述附注披露与审定表/明细表/利润表的勾稽核对情况及披露完整性检查结果。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：投资收益附注披露构成、金额及分类完整准确，勾稽一致，未见异常（或列明不符事项）。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useG11Disclosure } from '../../composables/useG11Disclosure'
import { isG11DisclosureLeaf } from '../../composables/g11SchemaRows'
import { buildG11SyncPayloads } from '../../composables/g11DisclosureSyncPayload'
import { G11_NOTE_SECTION } from '../../composables/g11NoteSectionMap'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import { api } from '@/services/apiProxy'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G11ImportExportDropdown from '../G11ImportExportDropdown.vue'

const props = defineProps<{
  variant: 'listed' | 'soe'
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  applicableStandards?: string[]
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const dis = useG11Disclosure({
  variant: props.variant,
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  wpId: toRef(props, 'wpId'),
  isReadonly: toRef(props, 'isReadonly'),
})

function onDisclosureImported(): void {
  emit('imported')
  dis.pullLatestAdjudicated(false)
}
const NOTE_KEY = `G11-disclosure-audit-note-${props.variant}`
const CONCLUSION_KEY = `G11-disclosure-audit-conclusion-${props.variant}`
const auditNote = ref('')
const auditConclusion = ref('')
const isSyncing = ref(false)
const noteSectionId = computed(() => G11_NOTE_SECTION[props.variant])

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'G11', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

async function syncToNotes(): Promise<void> {
  if (isSyncing.value || props.isReadonly || !props.projectId || !props.wpId) return
  const snap = dis.getSyncSnapshot(auditNote.value, auditConclusion.value)
  const payloads = buildG11SyncPayloads(
    props.wpId,
    props.variant,
    props.applicableStandards ?? [],
    snap,
  )
  if (!payloads.length) {
    ElMessage.warning('当前项目准则不适用附注同步')
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
    ElMessage.success(`已同步 ${rows} 行到附注「${noteSectionId.value} 投资收益」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  props.debouncedSave(NOTE_KEY, { remark: val, conclusion: null })
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: val, remark: null })
  props.debouncedSave(CONCLUSION_KEY, { conclusion: val, remark: null })
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.conclusion || c?.remark) auditConclusion.value = String(c.conclusion ?? c.remark ?? '')
})

function rowClass(row: { rowKey: string }): string {
  if (row.rowKey === 'total') return 'total-row'
  if (!isG11DisclosureLeaf(row.rowKey)) return 'sub-row'
  return ''
}

function fmt(v: number) { return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.g11-disclosure { font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; align-items: center; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.sync-hint { margin-bottom: 8px; }
.sub-section-head { margin: 16px 0 8px; }
.sub-title { margin: 0; font-size: 14px; color: #c45656; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #999; }
.note-card { margin-top: 8px; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
:deep(.total-row) { font-weight: 600; background: #f5f7fa; }
:deep(.sub-row) { color: #606266; background: #fafafa; }
</style>
