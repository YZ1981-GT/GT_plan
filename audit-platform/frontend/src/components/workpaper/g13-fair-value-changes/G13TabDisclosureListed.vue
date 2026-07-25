<template>
  <div class="g13-disclosure">
    <div class="section-head">
      <h3 class="sheet-title">{{ dis.title.value }}</h3>
      <div class="head-actions">
        <GtIndexChip v-if="noteChip" :value="noteChip" :context-project-id="projectId" />
        <el-button
          v-if="!isReadonly && projectId"
          size="small"
          type="primary"
          plain
          data-testid="g13-disclosure-listed-sync-notes"
          :loading="isSyncing"
          @click="syncToNotes"
        >同步到附注</el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('listed')">↩ 跳转回附注</el-button>
        <el-button size="small" :loading="dis.aiLoading.value" :disabled="isReadonly"
          @click="dis.generateAiConclusion()">🤖 AI辅助</el-button>
        <el-button size="small" :disabled="isReadonly" @click="dis.syncFromDetail()">从明细同步</el-button>
        <el-button size="small" :disabled="isReadonly" @click="dis.applyAutoNoteDraft()">生成附注叙述</el-button>
        <GtReviewTrigger section-id="G13-disclosure-listed" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="objective-alert"
      title="审计目标：核实上市公司口径公允价值变动收益（6101）附注披露的完整性与准确性，各来源分类与金额与 G13-1 审定表、G13-2 明细勾稽一致（CAS 39 公允价值计量 / CAS 30 财务报表列报）。" />

    <el-alert type="warning" :closable="false" show-icon class="rule-alert">
      <template #title>
        公允价值变动收益（注：以下不存在的项目可以删除）
      </template>
      无发生额项目默认不显示。「同步到附注」推送至「{{ noteSectionId }}」时排除空行；「其中」备忘有数才披露且不计入合计，并强制保留所属主行。
    </el-alert>

    <el-alert v-if="dis.adjudicatedAmount.value != null" type="success" :closable="false" class="sync-hint">
      已同步审定数（6101）：{{ fmt(dis.adjudicatedAmount.value) }}
      <el-button link size="small" @click="dis.pullLatestAdjudicated()">刷新</el-button>
    </el-alert>

    <div class="table-toolbar">
      <el-switch
        :model-value="dis.showEmptyRows.value"
        :disabled="isReadonly"
        inline-prompt
        active-text="显示空行"
        inactive-text="隐藏空行"
        @update:model-value="dis.setShowEmptyRows"
      />
      <span v-if="dis.hiddenEmptyCount.value > 0" class="toolbar-hint">
        已隐藏 {{ dis.hiddenEmptyCount.value }} 个无发生额项目
      </span>
    </div>

    <el-table :data="dis.displayRows.value" border size="small" style="font-size:13px" max-height="480"
      data-testid="g13-disclosure-listed-table"
      :row-class-name="rowClassName"
      empty-text="本期及上期均无公允价值变动收益发生额">
      <el-table-column label="产生公允价值变动收益的来源" prop="label" min-width="280" fixed />
      <el-table-column label="本期发生额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.currentAmount" size="small"
            :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'currentAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.currentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期发生额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.priorAmount" size="small"
            :controls="false" style="width:100%"
            @update:model-value="(v: number) => dis.updateField(row.rowKey, 'priorAmount', v ?? 0)" />
          <span v-else>{{ fmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动额" width="120" align="right">
        <template #default="{ row }"><span class="formula-cell">{{ fmt(row.changeAmount) }}</span></template>
      </el-table-column>
      <el-table-column label="备注" min-width="80">
        <template #default="{ row }">
          <el-input v-if="row.rowKey !== 'total' && !isReadonly" :model-value="row.remark" size="small"
            @change="(v: string) => dis.updateField(row.rowKey, 'remark', v)" />
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="note-card">
      <template #header>附注说明</template>
      <el-input :model-value="dis.noteText.value" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }"
        :disabled="isReadonly" placeholder="公允价值变动收益附注披露说明…"
        @update:model-value="dis.updateNoteText" />
    </el-card>

    <GCycleDisclosureExtras
      cycle-label="G13 公允价值变动"
      :account-code="G13_ACCOUNT_CODE"
      :adjudicated-amount="dis.adjudicatedAmount.value"
      :disclosure-total="dis.totalRow.value.currentAmount"
      :formula-map="[...G13_DISCLOSURE_FORMULA_MAP]"
      :manual-formula-notes="[
        `同步目标：附注模块「${noteSectionId}」`,
        '空行默认隐藏；「其中」备忘不计入合计，有数才披露',
      ]"
      :is-readonly="isReadonly"
      @refresh="onReconcileRefresh"
    />

    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <p>1. 上市公司口径披露 9 类来源+合计；无发生额行默认隐藏，附注模块不披露空行。</p>
      <p>2. 「同步到附注」推送子表至「{{ noteSectionId }}」；「其中：指定为…」备忘有数才推送，不计入合计。</p>
      <p>3. 上期发生额可自 G13-1 带入或手工修订；变动额=本期−上期。</p>
      <p>4. 「生成附注叙述」仅汇总非空分项；编制提示语不会写入附注正文。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useG13Disclosure } from '../composables/useG13Disclosure'
import { G13_ACCOUNT_CODE, G13_DISCLOSURE_FORMULA_MAP } from '../composables/g13Constants'
import { buildG13SyncPayloads } from '../composables/g13DisclosureSyncPayload'
import { G13_NOTE_SECTION } from '../composables/g13NoteSectionMap'
import type { ChecklistResponse } from '../composables/useF1FormData'
import { api } from '@/services/apiProxy'
import GCycleDisclosureExtras from '../shared/GCycleDisclosureExtras.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  applicableStandards?: string[]
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const dis = useG13Disclosure({
  variant: 'listed',
  allResponses: toRef(props, 'allResponses'),
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  isReadonly: computed(() => props.isReadonly),
  debouncedSave: props.debouncedSave,
})

const isSyncing = ref(false)
const noteSectionId = G13_NOTE_SECTION.listed
const noteChip = computed(() => `Note:${noteSectionId}`)

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'G13', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

async function syncToNotes(): Promise<void> {
  if (isSyncing.value || props.isReadonly || !props.projectId || !props.wpId) return
  const payloads = buildG13SyncPayloads(
    props.wpId,
    'listed',
    props.applicableStandards ?? [],
    dis.getSyncSnapshot(),
  )
  if (!payloads.length) {
    ElMessage.warning('当前项目准则不适用上市附注同步')
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
    ElMessage.success(`已同步 ${rows} 行到附注「${noteSectionId}」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function rowClassName({ row }: { row: { rowKey: string } }): string {
  if (row.rowKey === 'total') return 'g13-row-total'
  if (row.rowKey.startsWith('designated_fv')) return 'g13-row-ofwhich'
  return ''
}

function fmt(v: number): string {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onReconcileRefresh(): void {
  dis.pullLatestAdjudicated()
  dis.syncFromDetail()
}
</script>

<style scoped>
.g13-disclosure { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.sync-hint { margin-bottom: 12px; }
.objective-alert, .rule-alert { margin-bottom: 12px; }
.table-toolbar {
  display: flex; align-items: center; gap: 12px; margin-bottom: 8px;
}
.toolbar-hint { font-size: 12px; color: #909399; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; background: #fafafa; display: inline-block; width: 100%; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266; }
.compile-hint summary { cursor: pointer; color: #409eff; margin-bottom: 6px; }
:deep(.g13-row-total) { font-weight: 700; background: #f5f7fa; }
:deep(.g13-row-ofwhich) { color: #606266; font-size: 12px; }
</style>
