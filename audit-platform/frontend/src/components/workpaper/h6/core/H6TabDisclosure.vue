<template>
  <div :class="rootClass">
    <el-alert type="info" :closable="false" show-icon class="objective">
      {{ ui.objective }}
    </el-alert>

    <div class="toolbar">
      <div class="toolbar-left">
        <strong>{{ ui.title }}</strong>
        <el-tag size="small" :type="ui.tagType" effect="plain">{{ ui.badge }}</el-tag>
        <el-tag v-if="transitZero" size="small" type="success">1606 已清零</el-tag>
        <el-tag v-else size="small" type="danger">1606 未清零</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button
          size="small"
          :disabled="isReadonly"
          :data-testid="ui.pullTestId"
          @click="pullFromSources"
        >
          从 H6-1/H6-2 取数
        </el-button>
        <el-button
          size="small"
          :disabled="isReadonly || !projectId"
          :data-testid="ui.pullH1TestId"
          @click="pullFa"
        >
          从 H1 取固定资产
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          :data-testid="ui.syncTestId"
          @click="syncToNotes"
        >同步到附注</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:H6-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H6-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H1-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
        <GtReviewTrigger :section-id="ui.reviewSectionId" />
      </div>
    </div>

    <el-alert v-if="warnings.length" type="warning" :closable="false" class="cross-warn">
      <ul class="warn-list">
        <li v-for="w in warnings" :key="w">{{ w }}</li>
      </ul>
    </el-alert>

    <p class="xref-note">{{ H6_XREF_H1 }}</p>

    <section class="block">
      <h3 class="block-title">{{ ui.summaryTitle }}</h3>
      <el-table :data="summaryDisplay" border size="small" class="wp-table" style="max-width: 520px">
        <el-table-column label="项  目" min-width="140">
          <template #default="{ row }">
            <span :class="{ 'is-total': row.key === '__total__' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="ui.endCol" width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.key === 'fixed_assets' && !isReadonly"
              v-model="state.faEnd"
              :controls="false"
              size="small"
              style="width:100%"
              @change="scheduleSave"
            />
            <span v-else :class="{ 'formula-cell': row.key !== 'fixed_assets' }">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="ui.priorCol" width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.key === 'fixed_assets' && !isReadonly"
              v-model="state.faPrior"
              :controls="false"
              size="small"
              style="width:100%"
              @change="scheduleSave"
            />
            <span v-else :class="{ 'formula-cell': row.key !== 'fixed_assets' }">{{ fmtAmt(row.priorBalance) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <p class="hint">清理行 =（2）明细合计；固定资产行可手填或从 H1 带入；合计数披露交叉索引 H1-1。</p>
    </section>

    <section class="block">
      <div class="block-head">
        <h3 class="block-title">（2）固定资产清理</h3>
        <el-button v-if="!isReadonly" size="small" @click="addClearingRow">+ 添加行</el-button>
      </div>
      <el-table :data="clearingDisplay" border size="small" class="wp-table">
        <el-table-column label="项  目" min-width="140">
          <template #default="{ row }">
            <span v-if="row.rowId === '__total__'" class="is-total">合  计</span>
            <el-input v-else-if="!isReadonly" v-model="row.name" size="small" @change="onClearingChange" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="ui.endCol" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowId !== '__total__' && !isReadonly"
              v-model="row.endBalance"
              :controls="false"
              size="small"
              style="width:100%"
              @change="onClearingChange"
            />
            <span v-else class="formula-cell">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="ui.priorCol" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowId !== '__total__' && !isReadonly"
              v-model="row.priorBalance"
              :controls="false"
              size="small"
              style="width:100%"
              @change="scheduleSave"
            />
            <span v-else class="formula-cell">{{ fmtAmt(row.priorBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转入清理的原因" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="row.rowId !== '__total__' && !isReadonly"
              v-model="row.reason"
              size="small"
              @change="scheduleSave"
            />
            <span v-else>{{ row.reason }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60">
          <template #default="{ row }">
            <el-button
              v-if="row.rowId !== '__total__'"
              link
              type="danger"
              size="small"
              @click="removeClearing(row.rowId)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="note-field">
        <label>{{ ui.noteLabel }}</label>
        <el-input
          v-model="state.clearingNote"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          :placeholder="H6_CLEARING_PROGRESS_HINT"
          @change="scheduleSave"
        />
      </div>
    </section>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li v-for="(tip, i) in ui.tips" :key="i">{{ tip }}</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H6TabDisclosure — 附注披露（上市 / 国企）参数化组件
 * variant=listed|soe；Listed/Soe 薄包装保留原入口与 data-testid
 */
import { ref, reactive, computed, inject, onMounted, onUnmounted, onBeforeUnmount } from 'vue'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import {
  H6_CLEARING_PROGRESS_HINT,
  H6_NOTE_SECTION,
  H6_XREF_H1,
  type H6DisclosureVariant,
} from '../../composables/h6NoteSectionMap'
import {
  buildH6ListedSyncPayloads,
  buildH6SoeSyncPayloads,
} from '../../composables/h6DisclosureSyncPayload'
import {
  H6_LISTED_KEYS,
  H6_SOE_KEYS,
  buildClearingDisplay,
  buildSummaryDisplay,
  createDefaultState,
  emptyClearingRow,
  fmtAmt,
  hydrateClearingRows,
  parsePack,
  serializePack,
  type H6ClearingRow,
} from '../../composables/h6DisclosureModel'
import { useH6Disclosure } from '../../composables/useH6Disclosure'

const props = defineProps<{
  variant: H6DisclosureVariant
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  sheetName?: string
}>()

const isReadonly = computed(() => props.isReadonly)
const isListed = computed(() => props.variant === 'listed')
const keys = computed(() => (isListed.value ? H6_LISTED_KEYS : H6_SOE_KEYS))
const noteSectionId = computed(() =>
  isListed.value ? H6_NOTE_SECTION.listed : H6_NOTE_SECTION.soe,
)
const rootClass = computed(() => (isListed.value ? 'h6-disc-listed' : 'h6-disc-soe'))

const ui = computed(() => {
  if (isListed.value) {
    return {
      title: '附注披露信息（上市公司）',
      badge: '（2）固定资产清理',
      tagType: 'success' as const,
      objective:
        `审计目标：按上市公司附注格式编制固定资产清理披露——汇总（固定资产+清理）、（2）清理明细及超1年进展，与 H6-1/H6-2 勾稽，并同步至附注「${noteSectionId.value}」子表「固定资产清理」。合计数详见 H1-1。`,
      summaryTitle: '固定资产',
      endCol: '期末余额',
      priorCol: '上年年末余额',
      noteLabel: '超 1 年清理进展说明',
      pullTestId: 'h6-listed-pull',
      pullH1TestId: 'h6-listed-pull-h1',
      syncTestId: 'h6-disclosure-listed-sync',
      reviewSectionId: 'H6-disclosure-listed',
      tips: [
        '列结构严格对齐源 xlsx「附注披露信息（上市公司）」：汇总三行 +（2）清理明细 + 超1年进展说明。',
        '「从 H6-1/H6-2 取数」按审定余额与明细状态映射清理行，超1年自动草拟进展说明。',
        `「同步到附注」仅推送「固定资产清理」子表及说明至「${noteSectionId.value}」，与 H1 其他子表按 key 浅合并。`,
        '1606 为过渡科目，期末宜清零；未清零须在附注披露清理项目。',
      ],
    }
  }
  return {
    title: '附注披露信息（国有企业）',
    badge: '八、22 · 清理',
    tagType: 'warning' as const,
    objective:
      `审计目标：按国有企业附注格式编制固定资产清理披露——汇总（固定资产+清理账面价值）、（2）清理明细及超1年进展，与 H6-1/H6-2 勾稽，并同步至附注「${noteSectionId.value}」子表「固定资产清理」。合计数详见 H1-1。`,
    summaryTitle: '22、固定资产',
    endCol: '期末账面价值',
    priorCol: '期初账面价值',
    noteLabel: '注：转入清理超过1年的进展说明',
    pullTestId: 'h6-soe-pull',
    pullH1TestId: 'h6-soe-pull-h1',
    syncTestId: 'h6-disclosure-soe-sync',
    reviewSectionId: 'H6-disclosure-soe',
    tips: [
      '列结构严格对齐源 xlsx「附注披露信息（国有企业）」：22、固定资产汇总 +（2）清理明细 + 超1年注。',
      '「从 H6-1/H6-2 取数」与 H1 国企附注「从 H6 同步清理」同源，保证底稿与附注一致。',
      `「同步到附注」仅推送「固定资产清理」子表及说明至「${noteSectionId.value}」，不覆盖 H1 已推送的其他子表。`,
      '1606 过渡科目期末宜清零；长期挂账须在附注说明进展。',
    ],
  }
})

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)
const { crossWarnings, pullFromLocalSources, pullFaFromH1, autoFill } = useH6Disclosure(allResponsesRef as any)

const state = reactive(createDefaultState())
const isSyncing = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null
let unsubAdj: (() => void) | null = null

const summaryDisplay = computed(() => buildSummaryDisplay(state))
const clearingDisplay = computed(() => buildClearingDisplay(state.clearingRows))
const warnings = computed(() => crossWarnings(state))
const transitZero = computed(() => autoFill.value.transitZero)

function hydrate() {
  const k = keys.value
  const pack = parsePack(props.allResponses.get(k.pack)?.remark)
  if (pack) {
    state.faEnd = pack.faEnd ?? 0
    state.faPrior = pack.faPrior ?? 0
    if (pack.clearingRows?.length) state.clearingRows = pack.clearingRows
    if (typeof pack.clearingNote === 'string') state.clearingNote = pack.clearingNote
  }
  if (!state.clearingRows.length) {
    const raw = props.allResponses.get(k.clearingRows)?.remark
    let parsed: unknown = null
    if (raw) {
      try { parsed = JSON.parse(raw) } catch { parsed = null }
    }
    const rows = hydrateClearingRows(parsed)
    if (rows.length) state.clearingRows = rows
  }
  const note = props.allResponses.get(k.clearingNote)?.remark
  if (typeof note === 'string' && note && !state.clearingNote) state.clearingNote = note
}

function persistAll() {
  const k = keys.value
  saveResponse(k.pack, serializePack(state))
  saveResponse(k.clearingRows, JSON.stringify(state.clearingRows))
  saveResponse(k.clearingNote, state.clearingNote)
  saveResponse(k.faEnd, state.faEnd)
  if (isListed.value) {
    saveResponse(H6_LISTED_KEYS.faPrior, state.faPrior)
  } else {
    saveResponse(H6_SOE_KEYS.faBegin, state.faPrior)
  }
  autoSync.scheduleAutoSync(syncToNotes)
}

function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => persistAll(), 300)
}

function onClearingChange() {
  scheduleSave()
}

function addClearingRow() {
  state.clearingRows.push(emptyClearingRow())
  scheduleSave()
}

function removeClearing(rowId: string) {
  const i = state.clearingRows.findIndex((r) => r.rowId === rowId)
  if (i >= 0) {
    state.clearingRows.splice(i, 1)
    scheduleSave()
  }
}

function pullFromSources() {
  const r = pullFromLocalSources({
    overwriteNote: !state.clearingNote.trim(),
    existingNote: state.clearingNote,
  })
  if (r.status === 'empty') {
    ElMessage.info(r.message)
    return
  }
  if (r.status !== 'ok') {
    ElMessage.warning(r.message)
    return
  }
  state.clearingRows = r.clearingRows.map((x: H6ClearingRow) => ({ ...x }))
  if (r.clearingNoteDraft && !state.clearingNote.trim()) {
    state.clearingNote = r.clearingNoteDraft
  }
  persistAll()
  ElMessage.success(r.message)
}

async function pullFa() {
  const r = await pullFaFromH1(props.projectId, props.variant)
  if (r.status === 'ok') {
    state.faEnd = r.faEnd
    state.faPrior = r.faPrior
    persistAll()
    ElMessage.success(r.message)
  } else {
    ElMessage.warning(r.message)
  }
}

async function syncToNotes() {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  persistAll()
  const payloadState = {
    faEnd: state.faEnd,
    faPrior: state.faPrior,
    clearingRows: state.clearingRows,
    clearingNote: state.clearingNote,
  }
  const payloads = isListed.value
    ? buildH6ListedSyncPayloads(props.wpId, [], payloadState)
    : buildH6SoeSyncPayloads(props.wpId, [], payloadState)
  if (!payloads.length) {
    ElMessage.warning(isListed.value ? '当前项目准则不适用上市附注同步' : '当前项目准则不适用国企附注同步')
    return
  }
  isSyncing.value = true
  try {
    const result: any = await api.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payloads[0],
    )
    const data = result?.data ?? result
    ElMessage.success(`已同步 ${Number(data?.rows_synced ?? 0)} 行到附注「${noteSectionId.value}」固定资产清理`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function onAdjudicated(e: Event) {
  const detail = (e as CustomEvent).detail
  if (detail?.wpCode === 'H6' || detail?.accountCode === '1606') {
    const r = pullFromLocalSources({ overwriteNote: false, existingNote: state.clearingNote })
    if (r.status === 'ok' && !state.clearingRows.length) {
      state.clearingRows = r.clearingRows.map((x) => ({ ...x }))
      persistAll()
    }
  }
}

onMounted(() => {
  hydrate()
  if (!state.clearingRows.length) {
    const r = pullFromLocalSources({ overwriteNote: !state.clearingNote.trim(), existingNote: state.clearingNote })
    if (r.status === 'ok') {
      state.clearingRows = r.clearingRows.map((x) => ({ ...x }))
      if (r.clearingNoteDraft && !state.clearingNote.trim()) state.clearingNote = r.clearingNoteDraft
      persistAll()
    }
  }
  window.addEventListener('substantive:adjudicated', onAdjudicated)
  unsubAdj = () => window.removeEventListener('substantive:adjudicated', onAdjudicated)
})

onUnmounted(() => {
  unsubAdj?.()
  if (saveTimer) clearTimeout(saveTimer)
})

onBeforeUnmount(() => { autoSync.cancelPending() })
</script>

<style scoped>
.h6-disc-listed,
.h6-disc-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective { margin-bottom: 12px; }
.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-bottom: 12px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.cross-warn { margin-bottom: 10px; }
.warn-list { margin: 0; padding-left: 18px; }
.xref-note {
  color: #2563eb; font-size: 12px; margin: 0 0 12px;
  padding: 6px 10px; background: #eff6ff; border-radius: 4px;
}
.block { margin-bottom: 16px; }
.block-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.block-title { margin: 0 0 8px; font-size: 14px; font-weight: 600; }
.block-head .block-title { margin: 0; }
.hint { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 6px; }
.is-total { font-weight: 600; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  font-variant-numeric: tabular-nums;
}
.note-field { margin-top: 10px; }
.note-field label {
  display: block; font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px;
}
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
