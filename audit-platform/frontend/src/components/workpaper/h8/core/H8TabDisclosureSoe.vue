<template>
  <div class="h8-disc-soe">
    <el-alert type="info" :closable="false" show-icon class="objective">
      审计目标：按国有企业附注格式编制使用权资产披露——原值/累计折旧/净值/减值/账面价值分类增减，与 H8-1/H8-2/H8-10 勾稽，并同步至附注「{{ noteSectionId }}」。
    </el-alert>

    <div class="methodology-context">
      <p>
        编制逻辑：横向 期初+增−减=期末；纵向 净值=原值−折旧、账面价值=净值−减值。
        净值与账面价值层增减列不适用（——）。同步目标附注八、26。
      </p>
    </div>

    <div class="toolbar">
      <div class="toolbar-left">
        <strong>附注披露信息（国企）</strong>
        <el-tag size="small" type="success" effect="plain">八、26 使用权资产</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly" @click="handlePull">从审定/明细/减值取数</el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          data-testid="h8-disclosure-soe-sync"
          @click="syncToNotes"
        >
          同步到附注
        </el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注（八、26）</el-button>
        <el-button size="small" :disabled="!projectId" @click="checkNoteConsistency(false)">✅ 校对附注</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:H8-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H8-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H8-10" :context-project-id="projectId" /></span>
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

    <section v-for="block in layers" :key="block.layer" class="block">
      <h3 class="block-title">{{ layerTitle(block.layer) }}</h3>
      <el-table :data="blockRows(block)" border size="small" class="wp-table">
        <el-table-column label="项  目" min-width="200">
          <template #default="{ row }">
            <span :class="{ 'is-total': row.isTotal }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && row.editable && !isReadonly"
              :model-value="row.begin"
              :controls="false"
              size="small"
              style="width:100%"
              @update:model-value="(v: number | undefined) => updateCell(block.layer, row.key, 'begin', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.isTotal || !row.editable }">{{ fmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" width="130" align="right">
          <template #default="{ row }">
            <span v-if="movementNa(block.layer)">——</span>
            <el-input-number
              v-else-if="!row.isTotal && row.editable && !isReadonly"
              :model-value="row.increase"
              :controls="false"
              size="small"
              style="width:100%"
              @update:model-value="(v: number | undefined) => updateCell(block.layer, row.key, 'increase', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" width="130" align="right">
          <template #default="{ row }">
            <span v-if="movementNa(block.layer)">——</span>
            <el-input-number
              v-else-if="!row.isTotal && row.editable && !isReadonly"
              :model-value="row.decrease"
              :controls="false"
              size="small"
              style="width:100%"
              @update:model-value="(v: number | undefined) => updateCell(block.layer, row.key, 'decrease', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(row.end) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <WpDisclosureConsistencyPanel :results="consistencyChecks" :project-id="projectId" />

    <section class="block guidance-block">
      <h4 class="sub-title">披露提示</h4>
      <el-alert type="info" :closable="false" class="guide-alert">{{ H8_SOE_GUIDANCE.impairment }}</el-alert>
      <WpNoteTextArea
        v-model="noteImpairment"
        label="减值测试披露说明"
        testid-prefix="h8-soe-impairment"
        :min-rows="3"
        :max-rows="8"
        :disabled="isReadonly"
        :placeholder="H8_SOE_GUIDANCE.impairment"
        :ai-loading="aiLoadingSection === 'impairment'"
        @change="persist"
        @ai="runAi('impairment')"
        @review="openReview('impairment')"
      />
    </section>

    <el-card shadow="never" class="audit-card">
      <WpNoteTextArea
        v-model="auditNote"
        card
        label="审计说明"
        testid-prefix="h8-soe-auditNote"
        :min-rows="4"
        :disabled="isReadonly"
        placeholder="说明分类口径、取数来源及与附注勾稽…"
        :ai-loading="aiLoadingSection === 'auditNote'"
        @change="persist"
        @ai="runAi('auditNote')"
        @review="openReview('auditNote')"
      />
    </el-card>
    <el-card shadow="never" class="audit-card">
      <WpNoteTextArea
        v-model="auditConclusion"
        card
        label="审计结论"
        testid-prefix="h8-soe-auditConclusion"
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
        <li>减值层优先取 H8-10（⑦已提→期初，⑧补提→本期增加），覆盖明细上的减值字段</li>
        <li>净值/账面价值层增减列固定为「——」，由原值−折旧、净值−减值自动推导</li>
        <li>「同步到附注」写入「{{ noteSectionId }}」子表「使用权资产」</li>
        <li>分类：土地 / 房屋建筑物 / 机器运输办公设备 / 其他（对齐源模板）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabDisclosureSoe — 使用权资产附注披露（国企）
 */
import { computed, ref, toRef, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { useHCycleDisclosureAi } from '../../composables/useHCycleDisclosureAi'
import { H8_NOTE_AI_SECTIONS } from '../../composables/h8NoteAiSections'
import WpNoteTextArea from '../../shared/disclosure/WpNoteTextArea.vue'
import WpDisclosureConsistencyPanel from '../../shared/disclosure/WpDisclosureConsistencyPanel.vue'
import { buildH8SoeChecks } from '../../composables/h8DisclosureConsistency'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH8SoeDisclosure } from '../../composables/useH8Disclosure'
import {
  H8_SOE_CATEGORIES,
  H8_SOE_GUIDANCE,
  H8_SOE_LAYER_META,
  layerTotal,
  resolveCategoryEnd,
  type H8SoeLayer,
  type H8SoeLayerBlock,
} from '../../composables/h8SoeDisclosureModel'
import { buildH8SoeSyncPayloads } from '../../composables/h8DisclosureSyncPayload'
import { H8_NOTE_SECTION } from '../../composables/h8NoteSectionMap'
import { useAuditContext } from '@/composables/useAuditContext'

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

const noteSectionId = H8_NOTE_SECTION.soe
const isSyncing = ref(false)

// 🔴 `useAuditContext()` 只能在 setup 顶层调用（内部依赖 inject / effect scope）。
// 历史实现写在 `checkNoteConsistency()` 里 → 点击时抛 TypeError 被 catch 吞成
// `noteCheckState='error'`，「校对附注」永远报错。见 H8TabDisclosureListed 同款注释。
const { year: auditYear } = useAuditContext()

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
  layers,
  noteImpairment,
  auditNote,
  auditConclusion,
  persist,
  updateCell,
  pullFromSources,
} = useH8SoeDisclosure({
  allResponses: toRef(props, 'allResponses'),
  onSave: (id, v) => { emit('save', id, v); autoSync.scheduleAutoSync(syncToNotes) },
})

// ─── 披露说明 AI 辅助 + 复核 ─────────────────────────────────────────────────
// 见 H8TabDisclosureListed 同款注释：原 `emit('open-ai'|'open-review')` 宿主零处理 = 死按钮。
const { aiLoadingSection: aiLoadingRef, runAi, openReview } = useHCycleDisclosureAi({
  wpCode: 'H8',
  variant: 'soe',
  wpId: () => props.wpId,
  isReadonly: () => props.isReadonly,
  noteSectionId,
  labels: H8_NOTE_AI_SECTIONS.soe,
  fields: {
    impairment: { get: () => noteImpairment.value || '', set: (v) => { noteImpairment.value = v; persist() } },
    auditNote: { get: () => auditNote.value || '', set: (v) => { auditNote.value = v; persist() } },
    auditConclusion: { get: () => auditConclusion.value || '', set: (v) => { auditConclusion.value = v; persist() } },
  },
})
const aiLoadingSection = computed(() => aiLoadingRef.value)

const consistencyChecks = computed(() => buildH8SoeChecks(layers.value))

function fmt(n: number): string {
  return (Number(n) || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function layerTitle(layer: H8SoeLayer) {
  return H8_SOE_LAYER_META[layer].title
}
function movementNa(layer: H8SoeLayer) {
  return H8_SOE_LAYER_META[layer].movementNa
}

function blockRows(block: H8SoeLayerBlock) {
  const meta = H8_SOE_LAYER_META[block.layer]
  const tot = layerTotal(block)
  const derived = meta.movementNa || block.layer === 'cost' || block.layer === 'dep' || block.layer === 'impair'
  const editable = !meta.movementNa
  const rows = [
    {
      key: '__total__',
      label: meta.title,
      isTotal: true,
      editable: false,
      begin: tot.begin,
      increase: tot.increase,
      decrease: tot.decrease,
      end: tot.end,
    },
    ...H8_SOE_CATEGORIES.map((c) => {
      const m = block.categories.find((x) => x.key === c.key)
      return {
        key: c.key,
        label: c.label,
        isTotal: false,
        editable,
        begin: m?.begin ?? 0,
        increase: m?.increase ?? 0,
        decrease: m?.decrease ?? 0,
        end: m ? resolveCategoryEnd(m, meta.movementNa) : 0,
      }
    }),
  ]
  void derived
  return rows
}

function handlePull() {
  ElMessage.success(pullFromSources().message)
}

async function syncToNotes() {
  if (isSyncing.value || props.isReadonly || !props.projectId || !props.wpId) return
  persist()
  const payloads = buildH8SoeSyncPayloads(props.wpId, props.applicableStandards || [], {
    layers: layers.value,
    noteImpairment: noteImpairment.value,
  })
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
    const year = auditYear.value || new Date().getFullYear()
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
    // 国企版合计=5层叶子行期末余额之和（account面值层期末=期初+增-减）
    let localTotal = 0
    for (const block of layers.value) {
      for (const row of block.items) {
        if (!row.isSubtotal) {
          localTotal += (Number(row.begin) || 0) + (Number(row.increase) || 0) - (Number(row.decrease) || 0)
        }
      }
    }
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
.h8-disc-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.block { margin-bottom: 18px; }
.block-title { margin: 0 0 8px; font-size: 14px; }
.sub-title { margin: 0 0 8px; font-size: 14px; }
.is-total { font-weight: 700; }
.formula-cell {
  border-bottom: 1px dashed #909399; font-variant-numeric: tabular-nums;
  background: #fafafa; display: inline-block; min-width: 100%; text-align: right;
}
.guidance-block { background: #f8fafc; border-radius: 8px; padding: 12px; border: 1px solid #ebeef5; }
.guide-alert { margin-bottom: 8px; }
.note-field { margin: 8px 0 0; }
.note-field label { display: block; font-size: 12px; color: #606266; margin-bottom: 4px; font-weight: 500; }
.audit-card { margin-bottom: 12px; }
.card-title { font-weight: 600; }
.compile-hint {
  margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff;
  border-radius: 4px; padding: 8px 12px; font-size: 12px; color: #606266;
}
.compile-hint summary { cursor: pointer; color: #409eff; margin-bottom: 6px; }
</style>
