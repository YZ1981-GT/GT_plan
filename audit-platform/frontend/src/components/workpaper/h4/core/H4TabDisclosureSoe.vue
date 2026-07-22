<template>
  <div class="h4-disc-soe">
    <el-alert type="info" :closable="false" show-icon class="objective">
      审计目标：按国企附注格式编制「23、在建工程」汇总披露（在建工程 + 工程物资；账面余额/减值准备/账面价值 × 期末+期初），工程物资与 H4-1 勾稽，合计数详见 J2-1。
    </el-alert>

    <div class="toolbar">
      <div class="toolbar-left">
        <strong>附注披露信息（国有企业）</strong>
        <el-tag size="small" type="success" effect="plain">23、在建工程</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly" data-testid="h4-soe-pull" @click="pullFromSources">
          从审定取数（工程物资）
        </el-button>
        <el-button size="small" :disabled="isReadonly" data-testid="h4-soe-pull-cip" @click="pullCipFromH2(true)">
          从 H2 带入在建工程
        </el-button>
        <el-button
          v-if="significantNoteDraft"
          size="small"
          :disabled="isReadonly"
          data-testid="h4-soe-sig-note"
          @click="applySignificantNote"
        >
          重大变动→附注说明
        </el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:H4-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H2-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:J2-1" :context-project-id="projectId" /></span>
        <GtReviewTrigger section-id="H4-disclosure-soe" />
      </div>
    </div>

    <el-alert v-if="crossWarnings.length" type="warning" :closable="false" class="cross-warn">
      <ul class="warn-list">
        <li v-for="w in crossWarnings" :key="w">{{ w }}</li>
      </ul>
    </el-alert>

    <p class="xref-note">【在建工程与工程物资的合计数据披露详见J2-1】</p>

    <section class="block">
      <h3 class="block-title">23、在建工程</h3>
      <el-table :data="summaryDisplay" border size="small" class="wp-table">
        <el-table-column label="项  目" min-width="120" fixed>
          <template #default="{ row }">
            <span :class="{ 'is-total': !row.editable }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" align="center">
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.editable && !isReadonly"
                :model-value="row.endBook"
                :controls="false"
                size="small"
                style="width:100%"
                @update:model-value="(v: number | undefined) => updateSummary(row.key, 'endBook', v ?? 0)"
              />
              <span v-else class="formula-cell">{{ fmt(row.endBook) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="减值准备" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.editable && !isReadonly"
                :model-value="row.endImpairment"
                :controls="false"
                size="small"
                style="width:100%"
                @update:model-value="(v: number | undefined) => updateSummary(row.key, 'endImpairment', v ?? 0)"
              />
              <span v-else class="formula-cell">{{ fmt(row.endImpairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.endCarrying) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初余额" align="center">
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.editable && !isReadonly"
                :model-value="row.beginBook"
                :controls="false"
                size="small"
                style="width:100%"
                @update:model-value="(v: number | undefined) => updateSummary(row.key, 'beginBook', v ?? 0)"
              />
              <span v-else class="formula-cell">{{ fmt(row.beginBook) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="减值准备" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.editable && !isReadonly"
                :model-value="row.beginImpairment"
                :controls="false"
                size="small"
                style="width:100%"
                @update:model-value="(v: number | undefined) => updateSummary(row.key, 'beginImpairment', v ?? 0)"
              />
              <span v-else class="formula-cell">{{ fmt(row.beginImpairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.beginCarrying) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
      <p class="hint">账面价值 = 账面余额 − 减值准备（自动计算）。工程物资 ← H4-1；在建工程 ← H2 EventBus /「从 H2 带入」。</p>
    </section>

    <section class="block">
      <label class="note-label">附注披露说明</label>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="说明在建工程与工程物资汇总口径；重大增减、减值及与 J2-1 勾稽情况。"
        @change="scheduleSave"
      />
    </section>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>列结构严格对齐源 xlsx「附注披露信息（国有企业）」：23、在建工程汇总三栏结构（期末/期初 × 余额/减值/价值）。</li>
        <li>「从审定取数」仅刷新工程物资行；「从 H2 带入在建工程」读取 H2-1 审定 EventBus/会话缓存。</li>
        <li>H2 确认审定后自动带入在建工程行（不覆盖已有非零手工数；按钮可强制覆盖）。</li>
        <li>合计自动汇总；合计数披露交叉索引 J2-1。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabDisclosureSoe — 附注披露信息（国有企业）
 * CIP 行：H2 EventBus substantive:adjudicated + sessionStorage 回放
 */
import { ref, reactive, computed, inject, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import {
  H4_SOE_ITEM,
  buildH4SoeSummaryDisplay,
  createDefaultH4SoeSummary,
  num,
  type H4SoeSummaryRow,
} from '../../composables/h4SoeDisclosureModel'
import { useH4Disclosure } from '../../composables/useH4Disclosure'
import {
  parseH2CipFromAdjudicatedEvent,
  readH2CipSnapshot,
  type H2CipAdjudicatedSnapshot,
} from '../../composables/h2CipBridge'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  sheetName?: string
}>()

const isReadonly = computed(() => props.isReadonly)
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)
const { pullSoeSummary, soeCrossCheck, significantNoteDraft } = useH4Disclosure(allResponsesRef as any)

const summary = reactive<H4SoeSummaryRow[]>(createDefaultH4SoeSummary())
const noteText = ref('')
let saveTimer: ReturnType<typeof setTimeout> | null = null
let unsubBus: (() => void) | null = null

const summaryDisplay = computed(() => buildH4SoeSummaryDisplay(summary))
const crossWarnings = computed(() => soeCrossCheck(summary))

function fmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function parseJson(itemId: string): any {
  const raw = props.allResponses.get(itemId)?.remark
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

function cipRowEmpty(): boolean {
  const cip = summary.find((r) => r.key === 'cip')
  if (!cip) return true
  return !num(cip.endBook) && !num(cip.beginBook) && !num(cip.endImpairment) && !num(cip.beginImpairment)
}

function applyCipSnapshot(snap: H2CipAdjudicatedSnapshot, force: boolean): boolean {
  const cip = summary.find((r) => r.key === 'cip')
  if (!cip) return false
  if (!force && !cipRowEmpty()) return false
  cip.endBook = snap.endBook
  cip.endImpairment = snap.endImpairment
  cip.beginBook = snap.beginBook
  cip.beginImpairment = snap.beginImpairment
  scheduleSave()
  return true
}

function load() {
  const saved = parseJson(H4_SOE_ITEM.summary)
  if (Array.isArray(saved) && saved.length) {
    for (const row of saved) {
      const t = summary.find((x) => x.key === row.key)
      if (!t) continue
      t.endBook = num(row.endBook)
      t.endImpairment = num(row.endImpairment)
      t.beginBook = num(row.beginBook)
      t.beginImpairment = num(row.beginImpairment)
    }
  }
  noteText.value = String(props.allResponses.get(H4_SOE_ITEM.noteText)?.remark ?? '')
  const hasMat = summary.some((r) => r.key === 'materials' && (r.endBook || r.beginBook || r.endImpairment))
  if (!hasMat) pullFromSources(false)
  if (cipRowEmpty() && props.projectId) {
    const cached = readH2CipSnapshot(props.projectId)
    if (cached) applyCipSnapshot(cached, false)
  }
}

function persistAll() {
  if (isReadonly.value) return
  const payload = summary.map((r) => ({ ...r }))
  props.allResponses.set(H4_SOE_ITEM.summary, {
    item_id: H4_SOE_ITEM.summary,
    remark: JSON.stringify(payload),
    conclusion: null,
  })
  saveResponse(H4_SOE_ITEM.summary, JSON.stringify(payload))
  props.allResponses.set(H4_SOE_ITEM.noteText, {
    item_id: H4_SOE_ITEM.noteText,
    remark: noteText.value,
    conclusion: null,
  })
  saveResponse(H4_SOE_ITEM.noteText, noteText.value)
}

function scheduleSave() {
  if (isReadonly.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => persistAll(), 300)
}

function updateSummary(
  key: string,
  field: 'endBook' | 'endImpairment' | 'beginBook' | 'beginImpairment',
  value: number,
) {
  const row = summary.find((r) => r.key === key)
  if (!row) return
  row[field] = num(value)
  scheduleSave()
}

function pullFromSources(notify = true) {
  const next = pullSoeSummary(summary.map((r) => ({ ...r })))
  for (const row of next) {
    const t = summary.find((x) => x.key === row.key)
    if (!t) continue
    t.endBook = row.endBook
    t.endImpairment = row.endImpairment
    t.beginBook = row.beginBook
    t.beginImpairment = row.beginImpairment
  }
  if (!noteText.value.trim() && significantNoteDraft.value) {
    noteText.value = significantNoteDraft.value
  }
  scheduleSave()
  if (notify) ElMessage.success('已从 H4-1 审定同步工程物资行')
}

function pullCipFromH2(force = true) {
  if (isReadonly.value) return
  const cached = props.projectId ? readH2CipSnapshot(props.projectId) : null
  if (!cached) {
    ElMessage.warning('暂无 H2-1 审定缓存：请先在 H2 确认审定，或保持两底稿同会话打开')
    return
  }
  const ok = applyCipSnapshot(cached, force)
  if (ok) ElMessage.success('已从 H2 审定带入在建工程行')
  else ElMessage.info('在建工程行已有数据，未覆盖')
}

function applySignificantNote() {
  const draft = significantNoteDraft.value
  if (!draft) {
    ElMessage.warning('H4-1 暂无净值重大变动项')
    return
  }
  if (noteText.value.trim() && !noteText.value.includes('重大变动')) {
    noteText.value = `${noteText.value.trim()}\n${draft}`
  } else {
    noteText.value = draft
  }
  scheduleSave()
  ElMessage.success('已写入重大变动附注说明')
}

function onH2Adjudicated(detail: any) {
  if (isReadonly.value) return
  const snap = parseH2CipFromAdjudicatedEvent(detail)
  if (!snap) return
  if (applyCipSnapshot(snap, false)) {
    ElMessage.success('已自动带入 H2 在建工程审定数')
  }
}

onMounted(() => {
  load()
  const busHandler = (payload: any) => onH2Adjudicated(payload)
  eventBus.on('substantive:adjudicated', busHandler)
  const winHandler = (e: Event) => onH2Adjudicated((e as CustomEvent).detail)
  window.addEventListener('substantive:adjudicated', winHandler)
  unsubBus = () => {
    eventBus.off('substantive:adjudicated', busHandler)
    window.removeEventListener('substantive:adjudicated', winHandler)
  }
})

onUnmounted(() => {
  if (saveTimer) clearTimeout(saveTimer)
  unsubBus?.()
})
</script>

<style scoped>
.h4-disc-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective { margin-bottom: 12px; }
.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 8px; margin-bottom: 12px;
}
.toolbar-left { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.toolbar-right { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.cross-warn { margin-bottom: 10px; }
.warn-list { margin: 0; padding-left: 18px; }
.xref-note {
  color: #2563eb; font-size: 12px; margin: 0 0 10px;
  font-weight: 500;
}
.block { margin-bottom: 16px; }
.block-title { font-size: 14px; font-weight: 600; margin: 0 0 8px; }
.wp-table :deep(.el-input-number .el-input__inner) { text-align: right; }
.formula-cell { font-variant-numeric: tabular-nums; color: var(--el-color-primary); }
.is-total { font-weight: 600; }
.hint { margin: 8px 0 0; font-size: 12px; color: var(--el-text-color-secondary); }
.note-label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 6px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
