<template>
  <div class="h9-disc-soe">
    <el-alert type="info" :closable="false" show-icon class="objective">
      审计目标：按国企附注格式编制租赁负债披露——租赁付款额、未确认融资费用、一年内重分类及净额，与 H9-1/H9-2 勾稽，并同步至附注「{{ noteSectionId }}」。
    </el-alert>

    <div class="methodology-context">
      <p>
        编制逻辑（对齐致同 Excel + CAS21）：①租赁付款额（原值）− 未确认融资费用 − 一年内重分类 = 净额 →
        ②与 H9-1 双区块及 H9-2 重分类勾稽 → ③同步附注八、52。
      </p>
    </div>

    <div class="toolbar">
      <div class="toolbar-left">
        <strong>附注披露信息（国企）</strong>
        <el-tag size="small" type="warning" effect="plain">八、52 租赁负债</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly" data-testid="h9-soe-pull" @click="handlePull">
          从审定/明细取数
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          data-testid="h9-disclosure-soe-sync"
          @click="syncToNotes"
        >
          同步到附注
        </el-button>
        <el-button size="small" type="warning" plain :loading="isSyncing" :disabled="isReadonly || !projectId" @click="handlePullAndSync">
          取数并同步
        </el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注（八、52）</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:H9-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H9-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H9-3" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
      </div>
    </div>

    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title">
          <span>49、租赁负债</span>
          <el-button v-if="!isReadonly" size="small" @click="promptAddExtra">
            + 续加扣减项
          </el-button>
        </div>
      </template>

      <el-table :data="displayRows" border size="small" class="disclosure-table" :row-class-name="rowClass">
        <el-table-column prop="item" label="项  目" min-width="240" />
        <el-table-column label="期末余额" min-width="140" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.kind === 'line' && !isReadonly"
              :model-value="row.endBalance ?? undefined"
              size="small"
              class="num-input"
              @update:model-value="(v: number | undefined) => updateLine(row.rowIndex!, 'endBalance', v ?? null)"
            />
            <span v-else class="formula-cell">{{ fmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="140" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.kind === 'line' && !isReadonly"
              :model-value="row.beginBalance ?? undefined"
              size="small"
              class="num-input"
              @update:model-value="(v: number | undefined) => updateLine(row.rowIndex!, 'beginBalance', v ?? null)"
            />
            <span v-else class="formula-cell">{{ fmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="72" align="center">
          <template #default="{ row }">
            <!-- 仅续加扣减项可删；固定三行是准则用语（composable 也会拒绝） -->
            <el-button
              v-if="row.key === 'extra'"
              type="danger"
              size="small"
              link
              @click="handleRemoveExtra(row.rowIndex!)"
            >
              删
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="hint">
        净额 = 租赁付款额 − 未确认融资费用 − 重分类至一年内到期 − 续加扣减项（公式列）。
      </p>
    </el-card>

    <WpDisclosureConsistencyPanel :results="consistencyChecks" :project-id="projectId" />

    <section class="guidance-block">
      <h4 class="sub-title">【提示】</h4>
      <el-alert
        v-for="(t, i) in H9_SOE_GUIDANCE.tips"
        :key="i"
        type="info"
        :closable="false"
        class="guide-alert"
        :title="`${i + 1}、${t}`"
      />
      <WpNoteTextArea
        v-model="state.supplementNote"
        label="补充披露说明（可选，同步至附注文本）"
        testid-prefix="h9-soe-supplementNote"
        :min-rows="2"
        :max-rows="6"
        :disabled="isReadonly"
        placeholder="如有额外披露事项可在此填写；CAS21 提示见上方，无需重复粘贴。"
        :ai-loading="aiLoadingSection === 'supplementNote'"
        @change="persist"
        @ai="runAi('supplementNote')"
        @review="openReview('supplementNote')"
      />
    </section>

    <el-card shadow="never" class="audit-card">
      <WpNoteTextArea
        v-model="state.auditNote"
        card
        label="审计说明"
        testid-prefix="h9-soe-auditNote"
        :min-rows="3"
        :disabled="isReadonly"
        placeholder="说明取数来源（H9-1/H9-2/H9-3）、与附注勾稽情况…"
        :ai-loading="aiLoadingSection === 'auditNote'"
        @change="persist"
        @ai="runAi('auditNote')"
        @review="openReview('auditNote')"
      />
    </el-card>
    <el-card shadow="never" class="audit-card">
      <WpNoteTextArea
        v-model="state.auditConclusion"
        card
        label="审计结论"
        testid-prefix="h9-soe-auditConclusion"
        :min-rows="2"
        :disabled="isReadonly"
        placeholder="本表披露是否恰当、完整…"
        :ai-loading="aiLoadingSection === 'auditConclusion'"
        @change="persist"
        @ai="runAi('auditConclusion')"
        @review="openReview('auditConclusion')"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>「从审定/明细取数」：H9-1 原值→租赁付款额、未确认融资费用；H9-2 重分类→一年内到期</li>
        <li>「同步到附注」写入附注「{{ noteSectionId }}」子表「租赁负债」</li>
        <li>增值税不纳入租赁付款额计量；保证金单独作为资产/负债</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H9TabDisclosureSoe — 租赁负债附注披露（国企）
 * 对齐源模板 A1:F16 + note_template 八、52；同步附注模块
 */
import { computed, ref, toRef, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { useHCycleDisclosureAi } from '../../composables/useHCycleDisclosureAi'
import { H9_NOTE_AI_SECTIONS } from '../../composables/h9NoteAiSections'
import WpDisclosureConsistencyPanel from '../../shared/disclosure/WpDisclosureConsistencyPanel.vue'
import { buildH9SoeChecks } from '../../composables/h9DisclosureConsistency'
import WpNoteTextArea from '../../shared/disclosure/WpNoteTextArea.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH9SoeDisclosure } from '../../composables/useH9Disclosure'
import {
  buildSoeDisplayRows,
  type H9SoeDisplayRow,
} from '../../composables/h9DisclosureModel'
import { buildH9SoeSyncPayloads } from '../../composables/h9DisclosureSyncPayload'
import { H9_NOTE_SECTION, H9_SOE_GUIDANCE } from '../../composables/h9NoteSectionMap'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

const noteSectionId = H9_NOTE_SECTION.soe
const isSyncing = ref(false)

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId, 'H9', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

const {
  state,
  persist,
  pullFromSources,
  updateLine,
  addExtraDeduction,
  removeExtraDeduction,
} = useH9SoeDisclosure({
  allResponses: toRef(props, 'allResponses'),
  onSave: (id, v) => { emit('save', id, v); autoSync.scheduleAutoSync(syncToNotes) },
})

const displayRows = computed(() => buildSoeDisplayRows(state.value))

const consistencyChecks = computed(() => buildH9SoeChecks(state.value))

// ─── 披露说明 AI 辅助 + 复核 ─────────────────────────────────────────────────
// 见 H9TabDisclosureListed 同款注释：原 `emit('open-ai'|'open-review')` 宿主零处理 = 死按钮。
const { aiLoadingSection: aiLoadingRef, runAi, openReview } = useHCycleDisclosureAi({
  wpCode: 'H9',
  variant: 'soe',
  wpId: () => props.wpId,
  isReadonly: () => props.isReadonly,
  noteSectionId,
  labels: H9_NOTE_AI_SECTIONS.soe,
  fields: {
    supplementNote: {
      get: () => state.value.supplementNote || '',
      set: (v) => { state.value.supplementNote = v; persist() },
    },
    auditNote: { get: () => state.value.auditNote || '', set: (v) => { state.value.auditNote = v; persist() } },
    auditConclusion: {
      get: () => state.value.auditConclusion || '',
      set: (v) => { state.value.auditConclusion = v; persist() },
    },
  },
})
const aiLoadingSection = computed(() => aiLoadingRef.value)

function fmt(n: number | null | undefined): string {
  if (n == null || n === ('' as any)) return ''
  return Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClass({ row }: { row: H9SoeDisplayRow }) {
  return row.kind === 'net' ? 'row-calc' : ''
}

/**
 * 续加扣减项 —— 对应源模板 `A11` 的 `……` 可续行。
 *
 * 固定三行（租赁付款额 / 减：未确认的融资费用 / 重分类至一年内到期）是准则用语，
 * 不可增删改名；本按钮只在其后追加。
 */
async function promptAddExtra(): Promise<void> {
  let name = ''
  try {
    const { value } = await ElMessageBox.prompt('请输入扣减项名称', '续加扣减项', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPlaceholder: '如：减：售后回租扣减',
      inputValidator: (v: string) => (v && v.trim() ? true : '名称不能为空'),
    })
    name = String(value ?? '').trim()
  } catch {
    return
  }
  const res = addExtraDeduction(name)
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

/** 删除续加扣减项（固定行会被 composable 拒绝） */
function handleRemoveExtra(index: number): void {
  const res = removeExtraDeduction(index)
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

function handlePull() {
  const res = pullFromSources()
  ElMessage.success(res.message)
}

/** 取数并同步：一键完成「从审定/明细取数」+「同步到附注」 */
async function handlePullAndSync() {
  const res = pullFromSources()
  if (res.message.includes('未找到')) {
    ElMessage.warning(res.message)
    return
  }
  ElMessage.success(res.message + '，正在同步到附注...')
  await syncToNotes()
}

async function syncToNotes() {
  if (isSyncing.value || props.isReadonly || !props.projectId || !props.wpId) return
  persist()
  const payloads = buildH9SoeSyncPayloads(props.wpId, props.applicableStandards || [], state.value)
  if (!payloads.length) {
    ElMessage.warning('当前不适用国企附注同步')
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
    eventBus.emit('disclosure:note-text-updated' as any, {
      projectId: props.projectId,
      sectionIds: [noteSectionId],
      wpId: props.wpId,
      sheet: payloads[0].sheet_name,
    })
    ElMessage.success(`已同步 ${rows} 行到附注「${noteSectionId}」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}
</script>

<style scoped>
.h9-disc-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective { margin-bottom: 12px; }
.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 14px; font-size: 12px; color: #92400e;
}
.methodology-context p { margin: 0; }
.toolbar {
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;
  margin-bottom: 14px;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.disclosure-card, .audit-card { margin-bottom: 14px; }
.disclosure-table { width: 100%; }
.num-input { width: 100%; }
.formula-cell {
  border-bottom: 1px dashed #909399; font-variant-numeric: tabular-nums;
  background: #fafafa; display: inline-block; min-width: 100%; text-align: right;
}
.hint { font-size: 12px; color: #909399; margin: 6px 0 0; }
.guidance-block { background: #f8fafc; border-radius: 8px; padding: 12px; border: 1px solid #ebeef5; margin-bottom: 14px; }
.sub-title { margin: 0 0 8px; font-size: 14px; }
.guide-alert { margin-bottom: 8px; }
.note-field { margin-top: 10px; }
.note-field label { display: block; font-size: 12px; color: #606266; margin-bottom: 4px; font-weight: 500; }
.card-title { font-weight: 600; }
.compile-hint {
  margin-top: 12px; border-left: 3px solid #409eff; background: #ecf5ff;
  border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266;
}
.compile-hint summary { cursor: pointer; color: #409eff; margin-bottom: 6px; }
:deep(.row-calc) { background: #fafafa; font-weight: 600; }
</style>
