<template>
  <div class="h9-disc-listed">
    <el-alert type="info" :closable="false" show-icon class="objective">
      审计目标：按上市公司附注格式编制租赁负债披露——分类期末/上年年末余额、扣减一年内到期及利息费用说明，与 H9-1/H9-2 勾稽，并同步至附注「{{ noteSectionId }}」。
    </el-alert>

    <div class="methodology-context">
      <p>
        编制逻辑（对齐致同 Excel + CAS21）：①按租赁类别列示余额 → ②小计 − 一年内到期 = 列报合计 →
        ③补充利息费用计入财务费用/资本化说明 → ④同步附注五、47。
      </p>
    </div>

    <div class="toolbar">
      <div class="toolbar-left">
        <strong>附注披露信息（上市公司）</strong>
        <el-tag size="small" type="success" effect="plain">五、47 租赁负债</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly" data-testid="h9-listed-pull" @click="handlePull">
          从审定/明细取数
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          data-testid="h9-disclosure-listed-sync"
          @click="syncToNotes"
        >
          同步到附注
        </el-button>
        <el-button size="small" type="warning" plain :loading="isSyncing" :disabled="isReadonly || !projectId" @click="handlePullAndSync">
          取数并同步
        </el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('listed')">↩ 跳转回附注（五、47）</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:H9-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H9-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
      </div>
    </div>

    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title">
          <span>47、租赁负债</span>
          <el-button v-if="!isReadonly" size="small" @click="promptAddCategory">+ 增加类别</el-button>
        </div>
      </template>

      <el-table :data="displayRows" border size="small" class="disclosure-table" :row-class-name="rowClass">
        <el-table-column label="项  目" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="row.kind === 'category' && !isReadonly"
              :model-value="row.item"
              size="small"
              @update:model-value="(v: string) => updateCategory(row.rowIndex!, 'item', v)"
            />
            <span v-else :class="{ 'summary-label': row.kind !== 'category' && row.kind !== 'within' }">
              {{ row.item }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="(row.kind === 'category' || row.kind === 'within') && !isReadonly"
              :model-value="row.endBalance ?? undefined"
              :controls="false"
              :precision="2"
              size="small"
              class="num-input"
              @update:model-value="(v: number | undefined) => onEndChange(row, v)"
            />
            <span v-else class="formula-cell">{{ fmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上年年末余额" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="(row.kind === 'category' || row.kind === 'within') && !isReadonly"
              :model-value="row.lastYearEnd ?? undefined"
              :controls="false"
              :precision="2"
              size="small"
              class="num-input"
              @update:model-value="(v: number | undefined) => onLastChange(row, v)"
            />
            <span v-else class="formula-cell">{{ fmt(row.lastYearEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="56" align="center">
          <template #default="{ row }">
            <el-button
              v-if="row.kind === 'category'"
              link
              type="danger"
              size="small"
              @click="removeCategory(row.rowIndex!)"
            >
              删
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="hint">小计/合计虚线为公式列；一年内到期取自 H9-2 重分类（可改）。</p>
    </el-card>

    <el-card shadow="never" class="supplement-card">
      <template #header><span class="card-title">利息费用说明</span></template>
      <div class="interest-grid">
        <el-form-item label="年度">
          <el-input
            v-model="state.interest.year"
            :disabled="isReadonly"
            style="width: 100px"
            @change="persist"
          />
        </el-form-item>
        <el-form-item label="计提利息(元)">
          <el-input-number
            v-model="state.interest.total"
            :controls="false"
            :precision="2"
            :disabled="isReadonly"
            @change="onInterestChange"
          />
        </el-form-item>
        <el-form-item label="计入财务费用(元)">
          <el-input-number
            v-model="state.interest.financeExpense"
            :controls="false"
            :precision="2"
            :disabled="isReadonly"
            @change="onInterestChange"
          />
        </el-form-item>
        <el-form-item label="计入固定资产(元)">
          <el-input-number
            v-model="state.interest.capitalized"
            :controls="false"
            :precision="2"
            :disabled="isReadonly"
            @change="onInterestChange"
          />
        </el-form-item>
      </div>
      <WpNoteTextArea
        :model-value="interestNoteDisplay"
        label="租赁负债利息费用说明"
        testid-prefix="h9-listed-interestNote"
        :min-rows="2"
        :max-rows="6"
        :disabled="isReadonly"
        :placeholder="H9_LISTED_GUIDANCE.interest"
        :ai-loading="aiLoadingSection === 'interestNote'"
        @update:model-value="onInterestNoteEdit"
        @ai="runAi('interestNote')"
        @review="openReview('interestNote')"
      />
      <p class="hint">默认按上方金额自动生成万元口径说明；手动改写后将覆盖自动文本。</p>
    </el-card>

    <section class="guidance-block">
      <h4 class="sub-title">【提示】</h4>
      <el-alert
        v-for="(t, i) in H9_LISTED_GUIDANCE.tips"
        :key="i"
        type="info"
        :closable="false"
        class="guide-alert"
        :title="`（${i + 1}）${t}`"
      />
    </section>

    <el-card shadow="never" class="audit-card">
      <WpNoteTextArea
        v-model="state.auditNote"
        card
        label="审计说明"
        testid-prefix="h9-listed-auditNote"
        :min-rows="3"
        :disabled="isReadonly"
        placeholder="说明取数来源（H9-1/H9-2）、分类口径、与附注勾稽情况…"
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
        testid-prefix="h9-listed-auditConclusion"
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
        <li>「从审定/明细取数」：H9-1 负债原值按名称归类；H9-2 重分类→一年内到期；利息→结构化说明</li>
        <li>「同步到附注」写入附注「{{ noteSectionId }}」子表「租赁负债」，并触发 disclosure:note-text-updated</li>
        <li>列报合计 = 小计 − 一年内到期的租赁负债（与资产负债表非流动负债列示一致）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H9TabDisclosureListed — 租赁负债附注披露（上市公司）
 * 对齐源模板 A1:F18 + note_template 五、47；同步附注模块
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
import WpNoteTextArea from '../../shared/disclosure/WpNoteTextArea.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH9ListedDisclosure } from '../../composables/useH9Disclosure'
import {
  H9_LISTED_GUIDANCE,
  buildListedDisplayRows,
  resolveListedInterestNote,
  type H9ListedDisplayRow,
} from '../../composables/h9DisclosureModel'
import { buildH9ListedSyncPayloads } from '../../composables/h9DisclosureSyncPayload'
import { H9_NOTE_SECTION } from '../../composables/h9NoteSectionMap'

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

const noteSectionId = H9_NOTE_SECTION.listed
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
  updateCategory,
  updateWithin,
  addCategory,
  removeCategory,
} = useH9ListedDisclosure({
  allResponses: toRef(props, 'allResponses'),
  onSave: (id, v) => { emit('save', id, v); autoSync.scheduleAutoSync(syncToNotes) },
})

const displayRows = computed(() => buildListedDisplayRows(state.value))
const interestNoteDisplay = computed(() => resolveListedInterestNote(state.value) || '')

function fmt(n: number | null | undefined): string {
  if (n == null || n === ('' as any)) return ''
  return Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClass({ row }: { row: H9ListedDisplayRow }) {
  if (row.kind === 'subtotal' || row.kind === 'total') return 'row-calc'
  return ''
}

function onEndChange(row: H9ListedDisplayRow, v: number | undefined) {
  if (row.kind === 'within') updateWithin('end', v ?? null)
  else if (row.kind === 'category' && row.rowIndex != null) updateCategory(row.rowIndex, 'endBalance', v ?? null)
}

function onLastChange(row: H9ListedDisplayRow, v: number | undefined) {
  if (row.kind === 'within') updateWithin('last', v ?? null)
  else if (row.kind === 'category' && row.rowIndex != null) updateCategory(row.rowIndex, 'lastYearEnd', v ?? null)
}

function onInterestChange() {
  state.value.interestNoteOverride = ''
  persist()
}

function onInterestNoteEdit(v: string) {
  state.value.interestNoteOverride = v
  persist()
}

// ─── 披露说明 AI 辅助 + 复核 ─────────────────────────────────────────────────
// 🔴 原实现是 `emit('open-ai'|'open-review', …)`，而宿主 `GtH9LeaseLiabilities.vue`
// 只声明了 change / navigate-sheet / refresh-complete / save → 两个按钮零网络请求。
// 现改接共享 `useDisclosureNoteAi`（真调 review-dialog/ai-generate）。
const { aiLoadingSection: aiLoadingRef, runAi, openReview } = useHCycleDisclosureAi({
  wpCode: 'H9',
  variant: 'listed',
  wpId: () => props.wpId,
  isReadonly: () => props.isReadonly,
  noteSectionId,
  labels: H9_NOTE_AI_SECTIONS.listed,
  fields: {
    interestNote: { get: () => interestNoteDisplay.value || '', set: (v) => onInterestNoteEdit(v) },
    auditNote: { get: () => state.value.auditNote || '', set: (v) => { state.value.auditNote = v; persist() } },
    auditConclusion: {
      get: () => state.value.auditConclusion || '',
      set: (v) => { state.value.auditConclusion = v; persist() },
    },
  },
})
const aiLoadingSection = computed(() => aiLoadingRef.value)

/**
 * 新增租赁类别 —— 先输名再创建（平台铁律：动态行新增需命名的必须先 prompt）。
 *
 * 撞名由 `addCategory` 拒绝（附注同步按行标签匹配，同名会互相覆盖丢数据）。
 */
async function promptAddCategory(): Promise<void> {
  let name = ''
  try {
    const { value } = await ElMessageBox.prompt('请输入租赁类别名称', '增加类别', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPlaceholder: '如：土地租赁 / 仓储租赁',
      inputValidator: (v: string) => (v && v.trim() ? true : '名称不能为空'),
    })
    name = String(value ?? '').trim()
  } catch {
    return // 用户取消
  }
  const res = addCategory(name)
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
  const payloads = buildH9ListedSyncPayloads(props.wpId, props.applicableStandards || [], state.value)
  if (!payloads.length) {
    ElMessage.warning('当前不适用上市附注同步')
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
.h9-disc-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.disclosure-card, .supplement-card, .audit-card { margin-bottom: 14px; }
.disclosure-table { width: 100%; }
.num-input { width: 100%; }
.formula-cell {
  border-bottom: 1px dashed #909399; font-variant-numeric: tabular-nums;
  background: #fafafa; display: inline-block; min-width: 100%; text-align: right;
}
.summary-label { font-weight: 600; }
.hint { font-size: 12px; color: #909399; margin: 6px 0 0; }
.interest-grid {
  display: flex; flex-wrap: wrap; gap: 8px 16px; margin-bottom: 8px;
}
.interest-grid :deep(.el-form-item) { margin-bottom: 4px; }
.guidance-block { background: #f8fafc; border-radius: 8px; padding: 12px; border: 1px solid #ebeef5; margin-bottom: 14px; }
.sub-title { margin: 0 0 8px; font-size: 14px; }
.guide-alert { margin-bottom: 8px; }
.card-title { font-weight: 600; }
.compile-hint {
  margin-top: 12px; border-left: 3px solid #409eff; background: #ecf5ff;
  border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266;
}
.compile-hint summary { cursor: pointer; color: #409eff; margin-bottom: 6px; }
:deep(.row-calc) { background: #fafafa; font-weight: 600; }
</style>
