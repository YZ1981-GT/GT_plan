<!--
  G3TabDisclosureListed.vue — 附注披露（上市公司）

  按被投资方列示增减变动 + 合计数交叉索引（Excel M1-1 → K1-1 / Note:五、8）
  Subscribe: substantive:adjudicated(1131)
  Publish: disclosure:note-text-updated；同步至附注五、8
-->
<template>
  <div class="g3-disclosure-listed" data-testid="g3-disclosure-listed">
    <div class="section-head">
      <h3 class="sheet-title">附注披露信息（上市公司）</h3>
      <div class="head-actions">
        <span class="chip-wrap">
          <GtIndexChip :value="noteChip" :context-project-id="projectId" />
        </span>
        <el-tag size="small" type="info">五、8 · 应收股利</el-tag>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly"
          @click="syncFromAdjudication(true)"
        >
          从 G3-1 带入
        </el-button>
        <el-button
          size="small"
          type="primary"
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          @click="syncToDisclosureNotes"
        >
          同步至附注
        </el-button>
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('G3-disclosure-listed')">💬复核</el-button>
        <GtIndexChip value="wp:G3-note-listed" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ tableRows.length }} 行</el-tag>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：复核上市公司应收股利附注披露的完整性与准确性，确保与审定数勾稽一致，并回写附注五、8（其他应收款下应收股利明细）。"
    />

    <!-- Excel 合计数交叉索引：M1-1 → K1-1 / Note:五、8 -->
    <div class="combined-cross-ref" role="navigation" aria-label="合计数披露交叉索引">
      <span class="cross-ref-text">
        【其他应收款、应收股利与应收利息的合计数披露详见
        <button
          type="button"
          class="legacy-index-link"
          title="Excel 索引 M1-1 → 跳转其他应收款合计数底稿 K1-1"
          @click="jumpCombinedWp"
        >M1-1</button>
        】
      </span>
      <div class="cross-ref-chips">
        <span class="chip-hint">平台索引</span>
        <GtIndexChip
          :value="combinedWpChip"
          :context-project-id="projectId"
          context="其他应收款审定表 — 合计数（应收利息+应收股利+其他应收款项）归集"
        />
        <GtIndexChip
          :value="combinedNoteChip"
          :context-project-id="projectId"
          context="附注五、8 其他应收款 — 汇总表含应收股利行"
        />
      </div>
    </div>

    <el-table :data="tableRows" border size="small" max-height="400" class="disclosure-table">
      <el-table-column label="被投资方" min-width="140">
        <template #default="{ row }">
          <el-input
            :model-value="row.investeeName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateTableRow(row.id, 'investeeName', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="上年年末余额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.openingBalance"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => updateTableRow(row.id, 'openingBalance', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="本期增加" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.currentIncrease"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => updateTableRow(row.id, 'currentIncrease', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="本期减少" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.currentDecrease"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => updateTableRow(row.id, 'currentDecrease', v ?? 0)"
          />
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="120" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="期末余额 = 上年年末 + 增加 - 减少">
            {{ fmtNum(row.openingBalance + row.currentIncrease - row.currentDecrease) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="备注" width="140">
        <template #default="{ row }">
          <el-input
            :model-value="row.remark"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateTableRow(row.id, 'remark', v)"
          />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-icon class="delete-icon" @click="removeTableRow(row.id)"><Delete /></el-icon>
        </template>
      </el-table-column>
    </el-table>

    <el-button v-if="!isReadonly" size="small" style="margin-top:8px" @click="addTableRow">＋ 新增行</el-button>

    <p class="template-tip merge-tip">
      坏账准备也可在其他应收款项下合并披露，并索引至
      <GtIndexChip
        value="Note:五、8"
        :context-project-id="projectId"
        context="附注五、8（3）③ 其他应收款坏账准备"
      />
      。
    </p>

    <G3AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="noteText"
      :show-conclusion="false"
      note-title="附注披露文本"
      note-ai-section="disclosure-listed-note"
      :related-context="{ 科目: '1131', 披露类型: '上市公司', 表格行数: tableRows.length }"
      note-placeholder="上市公司应收股利附注：按被投资方列示余额，并说明与审定数及合计数（K1-1 / 五、8）勾稽…"
      note-hint="保存后发布 disclosure:note-text-updated；「同步至附注」写入五、8。合计数见 M1-1→K1-1。"
      :note-min-rows="6"
    />

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 按被投资方列示上年年末/本期增减/期末；期末 = 上年年末 + 增加 − 减少。</p>
        <p>2. Excel「详见 M1-1」为合计数旧索引，平台跳转 <strong>K1-1</strong> 与附注 <strong>五、8</strong>。</p>
        <p>3. 监听 substantive:adjudicated(1131)；「同步至附注」写入五、8 应收股利子表。</p>
        <p class="cas-basis">CAS 30 / CAS 37：应收股利在附注中充分披露，合计数归其他应收款注释。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, inject } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter, useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import GtIndexChip from '../GtIndexChip.vue'
import G3AuditTextCards from './G3AuditTextCards.vue'
import {
  buildListedDisclosureFromAdj,
  isG3DisclosurePlaceholder,
  parseG3AdjStore,
} from '../composables/g3AdjudicationItems'
import { G3_ADJ_STORAGE_KEY } from '../composables/g3Constants'
import { buildG3ListedSyncPayloads } from '../composables/g3DisclosureSyncPayload'
import {
  G3_ACCOUNT_CODE,
  G3_COMBINED_DISCLOSURE_INDEX,
  G3_NOTE_SECTION,
  resolveG3NoteSectionTarget,
} from '../composables/g3NoteSectionMap'
import type { ChecklistResponse } from '../composables/useF1FormData'

interface DisclosureTableRow {
  id: string
  investeeName: string
  openingBalance: number
  currentIncrease: number
  currentDecrease: number
  remark: string
}

const props = withDefaults(defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  applicableStandards?: string[]
}>(), {
  applicableStandards: () => [],
})

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const router = useRouter()
const route = useRoute()
const isSyncing = ref(false)

const noteTarget = computed(() => resolveG3NoteSectionTarget('listed', props.applicableStandards))
const noteChip = computed(() => noteTarget.value?.chipValue ?? `Note:${G3_NOTE_SECTION.listed}`)
const combinedWpChip = computed(() => noteTarget.value?.combinedWpChip ?? `wp:${G3_COMBINED_DISCLOSURE_INDEX.wpCode}`)
const combinedNoteChip = computed(() => noteTarget.value?.combinedNoteChip ?? `Note:${G3_NOTE_SECTION.listed}`)

const TEXT_KEY = 'G3-disclosure-listed-text'
const TABLE_KEY = 'G3-disclosure-listed-table'

const noteText = ref('')

watch(() => props.allResponses.get(TEXT_KEY)?.remark, (v) => {
  if (v && v !== noteText.value) noteText.value = v
}, { immediate: true })

watch(noteText, (val) => {
  if (props.isReadonly) return
  props.debouncedSave(TEXT_KEY, { conclusion: null, remark: val })
  try {
    eventBus.emit('disclosure:note-text-updated', {
      wpCode: 'G3',
      section: 'listed',
      timestamp: Date.now(),
    })
  } catch { /* silent */ }
})

function generateId(): string {
  return `dl-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyTableRow(): DisclosureTableRow {
  return { id: generateId(), investeeName: '', openingBalance: 0, currentIncrease: 0, currentDecrease: 0, remark: '' }
}

function loadTableRows(): DisclosureTableRow[] {
  const raw = props.allResponses.get(TABLE_KEY)?.conclusion
  if (!raw) return [emptyTableRow()]
  try {
    const parsed = JSON.parse(raw) as Partial<DisclosureTableRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [emptyTableRow()]
    return parsed.map((p) => ({ ...emptyTableRow(), ...p, id: p.id ?? generateId() }))
  } catch { return [emptyTableRow()] }
}

const tableRows = ref<DisclosureTableRow[]>(loadTableRows())

watch(() => props.allResponses.get(TABLE_KEY)?.conclusion, (raw) => {
  if (raw) tableRows.value = loadTableRows()
}, { immediate: false })

function persistTable() {
  if (!props.isReadonly) {
    props.debouncedSave(TABLE_KEY, { conclusion: JSON.stringify(tableRows.value) })
  }
}

function updateTableRow(id: string, field: keyof DisclosureTableRow, value: string | number) {
  if (props.isReadonly) return
  tableRows.value = tableRows.value.map((r) => (r.id === id ? { ...r, [field]: value } : r))
  persistTable()
}

function addTableRow() {
  if (props.isReadonly) return
  tableRows.value = [...tableRows.value, emptyTableRow()]
  persistTable()
}

function removeTableRow(id: string) {
  if (props.isReadonly || tableRows.value.length <= 1) return
  tableRows.value = tableRows.value.filter((r) => r.id !== id)
  persistTable()
}

function handleAdjudicated(d: {
  accountCode: string
  auditedAmount?: number
  adjudicatedAmount?: number
}): void {
  if (d?.accountCode !== G3_ACCOUNT_CODE || props.isReadonly) return
  const amt = d.auditedAmount ?? (d as { adjudicatedAmount?: number }).adjudicatedAmount
  if (amt == null || !Number.isFinite(Number(amt))) return
  const line = `本期应收股利审定数 ${Number(amt).toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元。`
  if (!noteText.value.includes('审定数')) {
    noteText.value = noteText.value ? `${line}\n${noteText.value}` : line
  }
  // 表为空占位时自动带入 G3-1 行
  if (isG3DisclosurePlaceholder(tableRows.value)) {
    syncFromAdjudication(false)
  }
}

/** 从 G3-1 审定行带入附注增减表 */
function syncFromAdjudication(manual: boolean): void {
  if (props.isReadonly) return
  const store = parseG3AdjStore(props.allResponses.get(G3_ADJ_STORAGE_KEY)?.remark)
  const seeded = buildListedDisclosureFromAdj(store)
  if (!seeded.length) {
    if (manual) ElMessage.warning('G3-1 尚无可带入的被投资方行')
    return
  }
  if (!manual && !isG3DisclosurePlaceholder(tableRows.value)) return
  tableRows.value = seeded.map((r) => ({ ...r }))
  persistTable()
  if (manual) ElMessage.success(`已从 G3-1 带入 ${seeded.length} 行`)
}

function jumpCombinedWp() {
  const pid = props.projectId || (route.params.projectId as string) || ''
  if (!pid) {
    ElMessage.warning('缺少项目上下文，无法跳转合计数底稿')
    return
  }
  void router.push({
    name: route.name || undefined,
    params: { ...route.params, projectId: pid },
    query: {
      ...route.query,
      wpCode: G3_COMBINED_DISCLOSURE_INDEX.wpCode,
      sheet: 'K1-1',
    },
  }).catch(() => {
    void router.push({
      path: route.path,
      query: { ...route.query, wpCode: G3_COMBINED_DISCLOSURE_INDEX.wpCode },
    })
  })
  ElMessage.info(`正在跳转合计数底稿 ${G3_COMBINED_DISCLOSURE_INDEX.wpCode}（Excel 索引 ${G3_COMBINED_DISCLOSURE_INDEX.excelLegacy}）`)
}

async function syncToDisclosureNotes() {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  const payloads = buildG3ListedSyncPayloads(
    props.wpId,
    props.applicableStandards,
    tableRows.value,
    noteText.value,
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
    ElMessage.success(`已同步 ${rows} 行到附注模块「五、8 其他应收款（应收股利）」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

onMounted(() => { eventBus.on('substantive:adjudicated', handleAdjudicated) })
onBeforeUnmount(() => { eventBus.off('substantive:adjudicated', handleAdjudicated) })

function fmtNum(v: unknown): string {
  if (v === 0) return '—'
  if (typeof v === 'number') {
    if (!Number.isFinite(v) || v === 0) return '—'
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}
</script>

<style scoped>
.g3-disclosure-listed {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-objective { margin-bottom: 12px; }
.disclosure-table { width: 100%; }

.combined-cross-ref {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 16px;
  margin-bottom: 12px;
  padding: 10px 14px;
  background: linear-gradient(90deg, #f0f7ff 0%, #fafcff 100%);
  border: 1px solid #c6e2ff;
  border-radius: 4px;
}
.cross-ref-text { color: #303133; font-size: 13px; line-height: 1.5; }
.legacy-index-link {
  appearance: none;
  border: none;
  background: none;
  padding: 0;
  margin: 0 2px;
  color: #0563c1;
  font: inherit;
  font-weight: 600;
  text-decoration: underline;
  cursor: pointer;
}
.legacy-index-link:hover { color: #003d82; }
.cross-ref-chips {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.chip-hint { font-size: 12px; color: #909399; }

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 40px;
  padding: 0 4px;
  text-align: right;
  background: #f5f7fa;
  border-radius: 2px;
}
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover { color: #f56c6c; }

.template-tip {
  margin: 12px 0;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.55;
  color: #0563c1;
  background: #f5f9ff;
  border-radius: 4px;
}
.merge-tip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
}

.guidance-details {
  margin-top: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }
.guidance-content .cas-basis {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}
</style>
