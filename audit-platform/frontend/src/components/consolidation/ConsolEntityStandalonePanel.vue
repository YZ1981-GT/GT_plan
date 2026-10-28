<!--
  数据节点的单体项目报表 / 附注（spec consol-autotree-linkage-closure R6，ADR-CAL-007）。
  左树选中本部单体户、单体母公司户、子公司、分公司时，合并页右侧直接显示该企业单体项目的报表（本期 / 上期）
  或附注（章节目录 + 表格只读，按单体模板表头），均提供「进入该企业项目」。
  读单体项目已有接口；没有单体项目、无权查看、尚未生成时给中文说明，不拿合并口径数据冒充。
-->
<template>
  <div class="gt-cesp" data-testid="consol-standalone-panel">
    <div class="gt-cesp-head">
      <span class="gt-cesp-title" data-testid="cesp-title">
        {{ entity.name }} · 单体项目{{ mode === 'report' ? '报表' : '附注' }}（只读）
      </span>
      <span class="gt-cesp-spacer" />
      <el-button v-if="entity.projectId" size="small" :loading="loading" data-testid="cesp-refresh" @click="load">🔄 刷新</el-button>
      <el-button v-if="entity.projectId && state !== 'forbidden'" size="small" type="primary" data-testid="cesp-enter"
        @click="emit('enter-project')">进入该企业项目</el-button>
    </div>

    <div v-if="state" class="gt-cesp-state" data-testid="cesp-state">{{ stateText }}</div>

    <!-- 报表：行次 / 项目 / 本期 / 上期 -->
    <div v-else-if="mode === 'report'" v-loading="loading" class="gt-cesp-scroll">
      <table v-if="rows.length" class="gt-cesp-table" data-testid="cesp-report">
        <thead>
          <tr><th style="width:80px">行次</th><th>项目</th><th style="width:150px">本期</th><th style="width:150px">上期</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.row_code" :class="{ 'gt-cesp-total': row.is_total_row }">
            <td class="gt-cesp-code">{{ row.row_code }}</td>
            <td :style="{ paddingLeft: 8 + (row.indent_level || 0) * 14 + 'px' }">{{ row.row_name }}</td>
            <td class="gt-cesp-num" :data-testid="`cesp-cur-${row.row_code}`">{{ amount(row.current_period_amount) }}</td>
            <td class="gt-cesp-num">{{ amount(row.prior_period_amount) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 附注：章节目录 + 只读表格 -->
    <div v-else v-loading="loading" class="gt-cesp-notes">
      <aside class="gt-cesp-catalog">
        <el-input v-model="sectionSearch" size="small" placeholder="搜索章节" clearable data-testid="cesp-search" />
        <ul class="gt-cesp-sections">
          <li v-for="s in visibleSections" :key="s.note_section"
            :class="{ 'is-active': s.note_section === currentSection, 'is-empty': !s.has_data }"
            :title="s.has_data ? '' : '该章节没有数据'" :data-testid="`cesp-section-${s.note_section}`"
            @click="selectSection(s.note_section)">
            {{ s.note_section }} {{ s.section_title }}
          </li>
        </ul>
      </aside>
      <div v-loading="detailLoading" class="gt-cesp-note-body">
        <div v-if="detailError" class="gt-cesp-state" data-testid="cesp-detail-error">{{ detailError }}</div>
        <NoteTablesReadonly v-else-if="detail" :note="detail" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { disclosureNotes as P_notes, reports as P_reports } from '@/services/apiPaths'
import { useProjectStore } from '@/stores/project'
import { fmtAmount } from '@/utils/formatters'
import NoteTablesReadonly from '@/components/consolidation/NoteTablesReadonly.vue'
import type { StandaloneEntity } from '@/components/consolidation/composables/consolTreeView'
import {
  MATRIX_REPORT_TYPES,
  firstSectionWithData,
  projectVisibleInOptions,
  reportNotGenerated,
  sortNoteSections,
  standaloneStateText,
  stateFromError,
  type NoteSectionItem,
  type StandaloneMode,
  type StandaloneState,
} from '@/components/consolidation/composables/consolEntityView'

defineOptions({ name: 'ConsolEntityStandalonePanel' })

const props = defineProps<{
  mode: StandaloneMode
  entity: StandaloneEntity
  year: number | null
  /** 报表模式：与合并报表页顶部的报表标签共用 */
  reportType?: string
}>()

const emit = defineEmits<{ (e: 'enter-project'): void }>()

const projectStore = useProjectStore()
const loading = ref(false)
const state = ref<StandaloneState>(null)
const stateText = computed(() => standaloneStateText(state.value, props.mode))
const rows = ref<any[]>([])
const sections = ref<NoteSectionItem[]>([])
const sectionSearch = ref('')
const currentSection = ref<string | null>(null)
const detail = ref<any>(null)
const detailLoading = ref(false)
const detailError = ref('')
let seq = 0

const visibleSections = computed(() => {
  const q = sectionSearch.value.trim()
  if (!q) return sections.value
  return sections.value.filter((s) => `${s.note_section} ${s.section_title}`.includes(q))
})

function amount(v: unknown): string {
  return v === null || v === undefined || v === '' ? '' : fmtAmount(v)
}

/** 前端预检：不在本人可见项目内 ⇒ 无权查看（只用于提示；权限仍由单体接口判定）。列表可能被截断时不拦。 */
async function canAccess(projectId: string): Promise<boolean> {
  try {
    await projectStore.loadProjectOptions()
  } catch {
    return true
  }
  return projectVisibleInOptions(projectStore.projectOptions, projectId)
}

async function load() {
  const my = ++seq
  rows.value = []
  sections.value = []
  detail.value = null
  detailError.value = ''
  currentSection.value = null
  state.value = null
  const pid = props.entity?.projectId
  if (!pid) {
    state.value = 'no_project'
    return
  }
  if (!props.year) return
  if (props.mode === 'report' && MATRIX_REPORT_TYPES.has(props.reportType || '')) {
    state.value = 'matrix'
    return
  }
  loading.value = true
  try {
    if (!(await canAccess(pid))) {
      if (my === seq) state.value = 'forbidden'
      return
    }
    if (props.mode === 'report') {
      const data = await api.get(P_reports.get(pid, props.year, props.reportType || 'balance_sheet'), { _silent: true } as any)
      if (my !== seq) return
      const list = Array.isArray(data) ? data : []
      if (reportNotGenerated(list)) state.value = 'not_generated'
      else rows.value = list
      return
    }
    const data = await api.get(P_notes.tree(pid, props.year), { _silent: true } as any)
    if (my !== seq) return
    sections.value = sortNoteSections(Array.isArray(data) ? data : [])
    if (!sections.value.length) {
      state.value = 'not_generated'
      return
    }
    const first = firstSectionWithData(sections.value)
    if (first) await selectSection(first)
  } catch (e) {
    if (my === seq) state.value = stateFromError(e)
  } finally {
    if (my === seq) loading.value = false
  }
}

async function selectSection(section: string) {
  const pid = props.entity?.projectId
  if (!pid || !props.year) return
  const my = seq
  currentSection.value = section
  detailLoading.value = true
  detailError.value = ''
  try {
    const data = await api.get(P_notes.detail(pid, props.year, section), { _silent: true } as any)
    if (my !== seq || currentSection.value !== section) return
    detail.value = data
  } catch (e) {
    if (my !== seq || currentSection.value !== section) return
    detail.value = null
    const s = stateFromError(e)
    detailError.value = s === 'forbidden' ? standaloneStateText(s, 'note') : s === 'not_generated' ? '该章节不存在或尚未生成' : '读取该章节失败，请稍后重试'
  } finally {
    if (my === seq) detailLoading.value = false
  }
}

watch(() => [props.entity?.projectId, props.entity?.nodeKey, props.year, props.mode, props.reportType] as const, () => load(),
  { immediate: true })

defineExpose({ load, state, rows, sections, currentSection })
</script>

<style scoped>
.gt-cesp { display: flex; flex-direction: column; gap: 8px; }
.gt-cesp-head { display: flex; align-items: center; gap: 8px; }
.gt-cesp-title { font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-primary); }
.gt-cesp-spacer { flex: 1; }
.gt-cesp-state {
  padding: 24px; text-align: center; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary);
  background: var(--gt-color-bg-light, #f5f5f7); border-radius: var(--gt-radius-sm, 4px);
}
.gt-cesp-scroll { max-height: calc(100vh - 320px); overflow: auto; }
.gt-cesp-table { width: 100%; border-collapse: collapse; font-size: var(--gt-font-size-xs); }
.gt-cesp-table th, .gt-cesp-table td { border: 1px solid var(--gt-color-border-light, #ebeef5); padding: 3px 8px; }
.gt-cesp-table th { position: sticky; top: 0; background: var(--gt-color-primary-bg, #f4f0fa); z-index: 1; }
.gt-cesp-code { text-align: center; color: var(--gt-color-text-tertiary); }
.gt-cesp-num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.gt-cesp-total td { font-weight: 700; }
.gt-cesp-notes { display: flex; gap: 12px; min-height: 360px; }
.gt-cesp-catalog { width: 240px; flex-shrink: 0; display: flex; flex-direction: column; gap: 6px; }
.gt-cesp-sections { list-style: none; margin: 0; padding: 0; max-height: calc(100vh - 340px); overflow-y: auto; }
.gt-cesp-sections li {
  padding: 4px 8px; font-size: var(--gt-font-size-xs); cursor: pointer; border-radius: var(--gt-radius-sm, 4px);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.gt-cesp-sections li:hover { background: var(--gt-color-primary-bg, #f4f0fa); }
.gt-cesp-sections li.is-active { background: var(--gt-color-primary-bg, #f4f0fa); color: var(--gt-color-primary); font-weight: 600; }
.gt-cesp-sections li.is-empty { color: var(--gt-color-text-placeholder); }
.gt-cesp-note-body { flex: 1; min-width: 0; max-height: calc(100vh - 300px); overflow: auto; }
</style>
