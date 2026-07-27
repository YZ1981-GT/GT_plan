<template>
  <div class="h8-disc-listed">
    <el-alert type="info" :closable="false" show-icon class="objective">
      审计目标：按上市公司附注格式编制使用权资产披露——原值/累计折旧/减值/账面价值分类变动，与 H8-1/H8-2/H8-10/H8-13 勾稽，并同步至附注「{{ noteSectionId }}」。
    </el-alert>

    <div class="methodology-context">
      <p>
        编制逻辑（对齐致同 Excel + CAS21）：①按资产类别列示变动 → ②期末=期初+增−减、账面价值=原值−折旧−减值 →
        ③补充短期/低价值费用与减值测试说明 → ④同步附注五、25。
      </p>
    </div>

    <div class="toolbar">
      <div class="toolbar-left">
        <strong>附注披露信息（上市公司）</strong>
        <el-tag size="small" type="success" effect="plain">五、25 使用权资产</el-tag>
        <el-tag size="small" type="info" effect="plain">源模板 48 行</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly" @click="handlePull">从审定/明细/减值取数</el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          data-testid="h8-disclosure-listed-sync"
          @click="syncToNotes"
        >
          同步到附注
        </el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('listed')">↩ 跳转回附注（五、25）</el-button>
        <el-button size="small" :disabled="!projectId" @click="checkNoteConsistency(false)">✅ 校对附注</el-button>
        <el-button size="small" type="primary" plain @click="emit('open-ai', 'disclosure-listed')">AI 辅助</el-button>
        <el-button size="small" @click="emit('open-review', 'disclosure-listed')">复核</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:H8-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H8-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H8-10" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H8-13" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
      </div>
    </div>

    <!-- 校对附注结果 -->
    <el-alert
      v-if="noteCheckState === 'ok'"
      type="success" :closable="true" show-icon style="margin-bottom: 8px"
    >{{ noteCheckMessage }}</el-alert>
    <el-alert
      v-else-if="noteCheckState === 'diff'"
      type="warning" :closable="false" show-icon style="margin-bottom: 8px"
    >{{ noteCheckMessage }}</el-alert>
    <el-alert
      v-else-if="noteCheckState === 'missing'"
      type="info" :closable="true" show-icon style="margin-bottom: 8px"
    >{{ noteCheckMessage }}</el-alert>

    <section class="block">
      <div class="block-head">
        <h3 class="block-title">使用权资产变动表</h3>
        <div v-if="!isReadonly" class="cat-bar">
          <el-button size="small" @click="handleAddCat">+ 增加资产类别列</el-button>
          <span class="hint">源模板「……」列：按被审计单位实际类别扩展</span>
        </div>
      </div>
      <div class="movement-wrap">
        <el-table
          :data="movementRowDefs"
          border
          size="small"
          class="wp-table movement-table"
          :row-class-name="movementRowClass"
        >
          <el-table-column label="项  目" min-width="200" fixed>
            <template #default="{ row }">
              <span :style="{ paddingLeft: `${row.indent * 12}px` }" :class="`kind-${row.kind}`">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column
            v-for="cat in categories"
            :key="cat.key"
            :label="cat.label"
            min-width="120"
            align="right"
          >
            <template #header>
              <div class="cat-header">
                <span>{{ cat.label }}</span>
                <el-button
                  v-if="!isReadonly && !isDefaultCat(cat.key)"
                  link
                  size="small"
                  type="danger"
                  @click="removeCategory(cat.key)"
                >
                  删
                </el-button>
              </div>
            </template>
            <template #default="{ row }">
              <template v-if="row.kind === 'section'">—</template>
              <el-input-number
                v-else-if="row.editable && !isReadonly"
                :model-value="rawCell(movement, row.key, cat.key)"
                :controls="false"
                size="small"
                style="width:100%"
                @update:model-value="(v: number | undefined) => updateMovement(row.key, cat.key, v ?? 0)"
              />
              <span v-else class="formula-cell">{{ fmt(cellOf(row, cat.key)) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合  计" min-width="120" align="right" fixed="right">
            <template #default="{ row }">
              <span v-if="row.kind === 'section'">—</span>
              <span v-else class="formula-cell">{{ fmt(totalOf(row)) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <p class="hint">公式列虚线：期末=期初+增−减；账面价值=原值−累计折旧−减值。宜与 H8-1 审定净值勾稽。</p>
    </section>

    <section class="block guidance-block">
      <h4 class="sub-title">披露提示与说明</h4>
      <el-alert type="info" :closable="false" class="guide-alert">{{ H8_LISTED_GUIDANCE.shortLow }}</el-alert>
      <div class="note-field">
        <label>短期/低价值租赁费用说明</label>
        <el-input
          v-model="noteShortLow"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          :placeholder="H8_LISTED_GUIDANCE.shortLow"
          @change="persist"
        />
      </div>
      <el-alert type="info" :closable="false" class="guide-alert">{{ H8_LISTED_GUIDANCE.impairment }}</el-alert>
      <el-alert type="warning" :closable="false" class="guide-alert warn">{{ H8_LISTED_GUIDANCE.impairmentNote }}</el-alert>
      <div class="note-field">
        <label>减值测试披露说明</label>
        <el-input
          v-model="noteImpairment"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          :placeholder="H8_LISTED_GUIDANCE.impairment"
          @change="persist"
        />
      </div>
    </section>

    <el-card shadow="never" class="audit-card">
      <template #header><span class="card-title">审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="说明取数来源（H8-1/H8-2）、分类口径、与附注勾稽情况…"
        @change="persist"
      />
    </el-card>
    <el-card shadow="never" class="audit-card">
      <template #header><span class="card-title">审计结论</span></template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2 }"
        :disabled="isReadonly"
        placeholder="本表披露是否恰当、完整…"
        @change="persist"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>「从审定/明细/减值取数」：H8-2 汇总原值折旧；H8-10 ⑦已提→减值期初、⑧补提→本期计提，并草稿减值披露说明；H8-13 可带短期/低价值费用</li>
        <li>「同步到附注」写入附注「{{ noteSectionId }}」子表「使用权资产」，并触发 disclosure:note-text-updated</li>
        <li>减值测试即使未计提也需披露方法与参数（源模板注意条款）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabDisclosureListed — 使用权资产附注披露（上市公司）
 * HTML 主表 + 同步附注五、25；OO 不再作为唯一编辑面
 */
import { ref, toRef, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH8ListedDisclosure } from '../../composables/useH8Disclosure'
import {
  H8_LISTED_DEFAULT_CATEGORIES,
  H8_LISTED_GUIDANCE,
  H8_LISTED_MOVEMENT_ROWS,
  h8ListedCellValue,
  h8ListedTotalCellValue,
  rawCell,
  type MovementRowDef,
} from '../../composables/h8ListedDisclosureModel'
import { buildH8ListedSyncPayloads } from '../../composables/h8DisclosureSyncPayload'
import { H8_NOTE_SECTION } from '../../composables/h8NoteSectionMap'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
}>()

const noteSectionId = H8_NOTE_SECTION.listed
const isSyncing = ref(false)
const movementRowDefs = H8_LISTED_MOVEMENT_ROWS

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId, 'H8', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

const {
  categories,
  movement,
  noteShortLow,
  noteImpairment,
  auditNote,
  auditConclusion,
  persist,
  updateMovement,
  addCategory,
  removeCategory,
  pullFromSources,
} = useH8ListedDisclosure({
  allResponses: toRef(props, 'allResponses'),
  onSave: (id, v) => { emit('save', id, v); autoSync.scheduleAutoSync(syncToNotes) },
})

function fmt(n: number): string {
  return (Number(n) || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function isDefaultCat(key: string) {
  return H8_LISTED_DEFAULT_CATEGORIES.some((c) => c.key === key)
}
function cellOf(row: MovementRowDef, catKey: string) {
  return h8ListedCellValue(movement.value, row, catKey)
}
function totalOf(row: MovementRowDef) {
  return h8ListedTotalCellValue(movement.value, row, categories.value)
}
function movementRowClass({ row }: { row: MovementRowDef }) {
  if (row.kind === 'section') return 'row-section'
  if (row.kind === 'calc' || row.kind === 'book' || row.kind === 'subtotal') return 'row-calc'
  return ''
}

async function handleAddCat() {
  const { value } = await ElMessageBox.prompt('资产类别名称', '增加类别列', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    inputPlaceholder: '如：电子设备',
  })
  if (value) addCategory(value)
}

function handlePull() {
  const res = pullFromSources()
  ElMessage.success(res.message)
}

async function syncToNotes() {
  if (isSyncing.value || props.isReadonly || !props.projectId || !props.wpId) return
  persist()
  const payloads = buildH8ListedSyncPayloads(props.wpId, props.applicableStandards || [], {
    categories: categories.value,
    movement: movement.value,
    noteShortLow: noteShortLow.value,
    noteImpairment: noteImpairment.value,
  })
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
      accountCode: '1901',
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

// ─── P2-⑪ 校对附注（只读比对披露表合计 vs 附注当前数据） ──────────────────────
const noteCheckState = ref<'idle' | 'loading' | 'ok' | 'diff' | 'missing' | 'error'>('idle')
const noteCheckMessage = ref('')

async function checkNoteConsistency(silent = false) {
  if (!props.projectId) return
  noteCheckState.value = 'loading'
  try {
    const year = new Date().getFullYear() // 实际应由 useAuditContext 提供，此处兜底
    const res: any = await api.get(
      `/api/disclosure-notes/${props.projectId}/${year}/${noteSectionId}`,
      { _silent: true } as any,
    )
    const detail = res?.data ?? res
    if (!detail || !detail.note_section) {
      noteCheckState.value = 'missing'
      noteCheckMessage.value = `附注「${noteSectionId}」尚未生成`
      if (!silent) ElMessage.info(noteCheckMessage.value)
      return
    }
    // 取附注表格合计行（取第一张表 is_total 行的首个数值列）
    const tables = detail._tables || (detail.table_data ? [detail.table_data] : [])
    let noteTotal: number | null = null
    for (const tbl of tables) {
      const totalRow = (tbl.rows || []).find((r: any) => r.is_total)
      if (totalRow?.values?.length) {
        noteTotal = Number(totalRow.values[0]) || 0
        break
      }
    }
    if (noteTotal == null) {
      noteCheckState.value = 'ok'
      noteCheckMessage.value = '附注无合计行可比对'
      if (!silent) ElMessage.info(noteCheckMessage.value)
      return
    }
    // 本页合计（变动表期末账面价值总计）
    const localTotal = totalOf(movementRowDefs.find((r) => r.key === 'book_end')!)
    const diff = Math.round((localTotal - noteTotal) * 100) / 100
    if (Math.abs(diff) <= 1) {
      noteCheckState.value = 'ok'
      noteCheckMessage.value = `与附注「${noteSectionId}」核对一致`
      if (!silent) ElMessage.success(noteCheckMessage.value)
    } else {
      noteCheckState.value = 'diff'
      noteCheckMessage.value = `与附注「${noteSectionId}」不一致，差额 ${diff.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元`
      if (!silent) ElMessage.warning(noteCheckMessage.value)
    }
  } catch {
    noteCheckState.value = 'error'
    noteCheckMessage.value = '校对附注异常'
    if (!silent) ElMessage.warning(noteCheckMessage.value)
  }
}
</script>

<style scoped>
.h8-disc-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.block { margin-bottom: 20px; }
.block-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.block-title { margin: 0; font-size: 15px; }
.sub-title { margin: 0 0 8px; font-size: 14px; }
.hint { font-size: 12px; color: #909399; margin: 6px 0 0; }
.cat-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.movement-wrap { overflow-x: auto; }
.cat-header { display: flex; align-items: center; justify-content: center; gap: 4px; }
.formula-cell {
  border-bottom: 1px dashed #909399; font-variant-numeric: tabular-nums;
  background: #fafafa; display: inline-block; min-width: 100%; text-align: right;
}
.kind-section { font-weight: 700; }
.guidance-block { background: #f8fafc; border-radius: 8px; padding: 12px; border: 1px solid #ebeef5; }
.guide-alert { margin-bottom: 8px; }
.guide-alert.warn :deep(.el-alert__content) { color: #856404; }
.note-field { margin: 8px 0 14px; }
.note-field label { display: block; font-size: 12px; color: #606266; margin-bottom: 4px; font-weight: 500; }
.audit-card { margin-bottom: 12px; }
.card-title { font-weight: 600; }
.compile-hint {
  margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff;
  border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266;
}
.compile-hint summary { cursor: pointer; color: #409eff; margin-bottom: 6px; }
:deep(.row-section) { background: #f5f7fa; font-weight: 600; }
:deep(.row-calc) { background: #fafafa; }
</style>
