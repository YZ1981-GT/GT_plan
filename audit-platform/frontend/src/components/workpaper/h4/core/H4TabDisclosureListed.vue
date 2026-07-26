<template>
  <div class="h4-disc-listed">
    <el-alert type="info" :closable="false" show-icon class="objective">
      审计目标：按上市公司附注格式编制「（2）工程物资」分类披露（专用材料/专用设备/工器具 − 减值 = 合计），与 H4-1/H4-2/H4-7 勾稽；在建工程与工程物资合计数详见 J2-1。
    </el-alert>

    <div class="toolbar">
      <div class="toolbar-left">
        <strong>附注披露信息（上市公司）</strong>
        <el-tag size="small" type="success" effect="plain">（2）工程物资</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly" data-testid="h4-listed-pull" @click="pullFromSources">
          从明细/减值取数
        </el-button>
        <el-button
          v-if="significantNoteDraft"
          size="small"
          :disabled="isReadonly"
          data-testid="h4-listed-sig-note"
          @click="applySignificantNote"
        >
          重大变动→附注说明
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          data-testid="h4-disclosure-listed-sync"
          @click="syncToNotes"
        >同步到附注</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:H4-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H4-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H4-7" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:J2-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
        <GtReviewTrigger section-id="H4-disclosure-listed" />
      </div>
    </div>

    <el-alert v-if="crossWarnings.length" type="warning" :closable="false" class="cross-warn">
      <ul class="warn-list">
        <li v-for="w in crossWarnings" :key="w">{{ w }}</li>
      </ul>
    </el-alert>

    <p class="xref-note">【在建工程与工程物资的合计数披露详见J2-1】</p>

    <section class="block">
      <h3 class="block-title">（2）工程物资</h3>
      <el-table :data="materialsDisplay" border size="small" class="wp-table" style="max-width: 560px">
        <el-table-column label="项  目" min-width="180">
          <template #default="{ row }">
            <span :class="{ 'is-total': row.key === '__total__' || row.key === '__gross__' }">
              {{ row.label || '\u00a0' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="160" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.endBalance"
              :controls="false"
              size="small"
              style="width:100%"
              @update:model-value="(v: number | undefined) => updateMaterial(row.key, 'endBalance', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': !row.editable }">
              {{ row.isDeduction ? formatDeduction(row.endBalance) : fmt(row.endBalance) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="上年年末余额" width="160" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.priorBalance"
              :controls="false"
              size="small"
              style="width:100%"
              @update:model-value="(v: number | undefined) => updateMaterial(row.key, 'priorBalance', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': !row.editable }">
              {{ row.isDeduction ? formatDeduction(row.priorBalance) : fmt(row.priorBalance) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <p class="hint">空白小计行 = 专用材料 + 专用设备 + 工器具；合计 = 小计 − 工程物资减值准备。减值以括号列示。</p>
    </section>

    <section class="block">
      <label class="note-label">附注披露说明</label>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="说明工程物资分类依据、减值计提情况；如无重大变动可简述。"
        @change="scheduleSave"
      />
    </section>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>列结构严格对齐源 xlsx「附注披露信息（上市公司）」：（2）工程物资三分类 + 减值抵减 + 合计。</li>
        <li>「从明细/减值取数」按 H4-2 分类（专用材料/设备/工器具）汇总期末与期初，减值优先取 H4-7 期末应提。</li>
        <li>「同步到附注」推送至「{{ noteSectionId }}」工程物资子表（与 H2 在建工程子表按 key 合并，互不覆盖）。</li>
        <li>披露合计期末应与 H4-1 审定净值一致；合计数披露交叉索引 J2-1。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabDisclosureListed — 附注披露信息（上市公司）
 * 对齐源 xlsx：（2）工程物资分类表
 */
import { ref, reactive, computed, inject, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import {
  H4_LISTED_ITEM,
  buildH4ListedMaterialsDisplay,
  createDefaultH4ListedMaterials,
  num,
  type H4ListedMaterialKey,
  type H4ListedMaterialRow,
} from '../../composables/h4ListedDisclosureModel'
import { useH4Disclosure } from '../../composables/useH4Disclosure'
import { H2_NOTE_SECTION } from '../../composables/h2NoteSectionMap'
import { buildH4ListedSyncPayloads } from '../../composables/h4DisclosureSyncPayload'
import { useAuditContext } from '@/composables/useAuditContext'
import { eventBus } from '@/utils/eventBus'

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
const { pullListedMaterials, listedCrossCheck, significantNoteDraft } = useH4Disclosure(allResponsesRef as any)

const materials = reactive<H4ListedMaterialRow[]>(createDefaultH4ListedMaterials())
const noteText = ref('')
let saveTimer: ReturnType<typeof setTimeout> | null = null
let unsubscribe: (() => void) | null = null

// ─── 同步到附注所需变量（修复原模板引用未定义标识） ─────────────────────────
const noteSectionId = H2_NOTE_SECTION.listed  // 五、23（与 H2 共用子表按 key 合并）
const isSyncing = ref(false)
const { year: auditYear } = useAuditContext()

async function syncToNotes() {
  if (isSyncing.value || isReadonly.value) return
  isSyncing.value = true
  try {
    const payloads = buildH4ListedSyncPayloads(props.wpId, null, {
      materials: [...materials],
      noteText: noteText.value,
    })
    if (!payloads.length) {
      ElMessage.warning('不适用同步（当前变体非上市）')
      return
    }
    for (const payload of payloads) {
      await http.post(
        `/api/projects/${props.projectId}/disclosure-notes/${auditYear?.value || ''}/sync-from-workpaper`,
        { ...payload, year: auditYear?.value },
      )
    }
    eventBus.emit('disclosure:note-text-updated', {
      wpCode: 'H4',
      accountCode: '1605',
      projectId: props.projectId,
      sectionIds: [noteSectionId],
    })
    ElMessage.success('已同步到附注（五、23 工程物资子表）')
  } catch (e: any) {
    ElMessage.error(`同步失败: ${e?.message || e}`)
  } finally {
    isSyncing.value = false
  }
}

const materialsDisplay = computed(() => buildH4ListedMaterialsDisplay(materials))
const crossWarnings = computed(() => listedCrossCheck(materials))

function fmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatDeduction(val: number): string {
  if (!val) return '-'
  return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
}

function parseJson(itemId: string): any {
  const raw = props.allResponses.get(itemId)?.remark
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

function applyMaterials(src: H4ListedMaterialRow[]) {
  const byKey = new Map(src.map((r) => [r.key, r]))
  for (const row of materials) {
    const s = byKey.get(row.key)
    if (!s) continue
    row.endBalance = num(s.endBalance)
    row.priorBalance = num(s.priorBalance)
  }
}

function load() {
  const saved = parseJson(H4_LISTED_ITEM.materials)
  if (Array.isArray(saved) && saved.length) {
    applyMaterials(saved.map((r: any) => ({
      key: r.key,
      label: r.label,
      endBalance: num(r.endBalance),
      priorBalance: num(r.priorBalance),
      isDeduction: !!r.isDeduction,
    })))
  }
  noteText.value = String(props.allResponses.get(H4_LISTED_ITEM.noteText)?.remark ?? '')
  const hasData = materials.some((r) => r.endBalance || r.priorBalance)
  if (!hasData) pullFromSources(false)
}

function persistAll() {
  if (isReadonly.value) return
  props.allResponses.set(H4_LISTED_ITEM.materials, {
    item_id: H4_LISTED_ITEM.materials,
    remark: JSON.stringify(materials.map((r) => ({ ...r }))),
    conclusion: null,
  })
  saveResponse(H4_LISTED_ITEM.materials, JSON.stringify(materials.map((r) => ({ ...r }))))
  props.allResponses.set(H4_LISTED_ITEM.noteText, {
    item_id: H4_LISTED_ITEM.noteText,
    remark: noteText.value,
    conclusion: null,
  })
  saveResponse(H4_LISTED_ITEM.noteText, noteText.value)
}

function scheduleSave() {
  if (isReadonly.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => persistAll(), 300)
}

function updateMaterial(key: string, field: 'endBalance' | 'priorBalance', value: number) {
  const row = materials.find((r) => r.key === key as H4ListedMaterialKey)
  if (!row) return
  row[field] = num(value)
  scheduleSave()
}

function pullFromSources(notify = true) {
  applyMaterials(pullListedMaterials())
  // 附注说明为空时自动带入重大变动摘要
  if (!noteText.value.trim() && significantNoteDraft.value) {
    noteText.value = significantNoteDraft.value
  }
  scheduleSave()
  if (notify) ElMessage.success('已从 H4-2 分类明细及 H4-7 减值同步')
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

onMounted(() => {
  load()
  const handler = (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail?.wpCode === 'H4' || detail?.accountCode === '1605') {
      // 审定变更后仅提示，不强刷以免覆盖手工调整
    }
  }
  window.addEventListener('substantive:adjudicated', handler)
  unsubscribe = () => window.removeEventListener('substantive:adjudicated', handler)
})

onUnmounted(() => {
  if (saveTimer) clearTimeout(saveTimer)
  unsubscribe?.()
})
</script>

<style scoped>
.h4-disc-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
