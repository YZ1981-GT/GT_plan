<!-- GtCNoteTable.vue — C 类附注披露嵌套表 shell -->

<template>
  <div class="gt-c-note-table">
    <header class="gt-cnt__header">
      <div class="gt-cnt__header-meta">
        <span v-if="entityName" class="gt-cnt__entity">{{ entityName }}</span>
        <span v-if="periodEnd" class="gt-cnt__period">{{ periodEnd }}</span>
        <span v-if="sectionId" class="gt-cnt__section">附注章节：<strong>{{ sectionId }}</strong></span>
        <span v-if="indexNo" class="gt-cnt__index">索引号：<strong>{{ indexNo }}</strong></span>
      </div>
      <div class="gt-cnt__header-actions">
        <el-tag v-if="standardLabel" :type="standardTagType" size="small" effect="dark">
          {{ standardLabel }}
        </el-tag>
        <el-radio-group
          v-if="standardSwitchable && !readonly"
          v-model="currentStandardSubClass"
          size="small"
          @change="onStandardSwitch"
        >
          <el-radio-button value="listed">上市</el-radio-button>
          <el-radio-button value="soe">国企</el-radio-button>
        </el-radio-group>
      </div>
    </header>

    <!-- 上下文字段 -->
    <section v-if="contextFields.length" class="gt-cnt__context">
      <el-form
        :model="contextData"
        label-position="left"
        label-width="100px"
        inline
        :disabled="readonly"
        size="small"
      >
        <el-form-item
          v-for="field in contextFields"
          :key="field.name"
          :label="field.label"
        >
          <el-select
            v-if="field.type === 'enum'"
            v-model="contextData[field.name]"
            :disabled="readonly || !!field.readonly"
            clearable
            class="gt-cnt__context-select"
            @change="onContextChange(field.name)"
          >
            <el-option
              v-for="opt in field.enum || []"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>
          <el-input
            v-else
            v-model="contextData[field.name]"
            :disabled="readonly || !!field.readonly"
            class="gt-cnt__context-input"
            @change="onContextChange(field.name)"
          />
        </el-form-item>
      </el-form>
    </section>

    <!-- 隐藏子表恢复区 -->
    <section
      v-if="hiddenVisibleSubTables.length"
      class="gt-cnt__hidden-summary"
    >
      <el-alert type="info" :closable="false" show-icon>
        <template #default>
          <div class="gt-cnt__hidden-list">
            <span class="gt-cnt__hidden-label">已标记不适用：</span>
            <div class="gt-cnt__hidden-tags">
              <el-tag
                v-for="st in hiddenVisibleSubTables"
                :key="st.id"
                closable
                size="small"
                type="info"
                effect="plain"
                @close="onRestoreSubTable(st.id)"
              >
                {{ st.title }}
              </el-tag>
            </div>
          </div>
        </template>
      </el-alert>
    </section>

    <!-- 子表卡片列表 -->
    <el-collapse
      v-model="activeCollapse"
      class="gt-cnt__collapse"
    >
      <el-collapse-item
        v-for="st in visibleSubTables"
        :key="st.id"
        :name="st.id"
        class="gt-cnt__sub-card"
      >
        <template #title>
          <div class="gt-cnt__sub-title">
            <span class="gt-cnt__sub-title-text">{{ st.title }}</span>
            <el-tag
              v-for="badge in subClassBadges(st)"
              :key="badge.value"
              :type="badge.type"
              size="small"
              effect="plain"
              class="gt-cnt__sub-badge"
            >
              {{ badge.label }}
            </el-tag>
            <el-tag
              v-if="st.type === 'dynamic_rows'"
              size="small"
              effect="plain"
              class="gt-cnt__sub-badge"
            >
              {{ subTableRowCount(st.id) }} / {{ st.max_rows ?? 100 }} 行
            </el-tag>
            <el-button
              v-if="!readonly"
              link
              size="small"
              class="gt-cnt__sub-toggle"
              @click.stop="onHideSubTable(st.id)"
            >
              不适用
            </el-button>
          </div>
        </template>

        <p v-if="st.description" class="gt-cnt__sub-desc">{{ st.description }}</p>

        <CNoteSubTableCard
          :sub-table="st"
          :rows="st.type === 'static_rows' ? getStaticRowsView(st) : dynamicRowsView(st)"
          :readonly="readonly"
          :visible-columns="visibleColumns(st)"
          :cell-computed-value="cellComputedValue"
          :footer-columns="footerTotalColumns(st)"
          :footer-value="(col) => footerTotalValue(st, col)"
          :reached-max="reachedMaxRows(st)"
          @cell-change="(row, col) => onCellChange(st, row, col)"
          @add-row="onAddDynamicRow(st)"
          @remove-row="(i) => onRemoveDynamicRow(st, i)"
        />

        <CNoteInheritanceBadge :statuses="ruleStatusForSubTable(st.id)" />
      </el-collapse-item>
    </el-collapse>

    <!-- 引用来源 -->
    <section v-if="autoPullRefs.length" class="gt-cnt__refs">
      <h4 class="gt-cnt__refs-title">数据来源</h4>
      <ul class="gt-cnt__refs-list">
        <li
          v-for="refItem in autoPullRefs"
          :key="refItem.ref_id"
          class="gt-cnt__ref-item"
        >
          <GtIndexChip
            v-if="refItem.target_wp"
            :value="refItem.target_wp"
            :validate="true"
            @click="onJumpToReference(refItem.target_wp || '')"
          />
          <span class="gt-cnt__ref-desc">{{ refItem.description }}</span>
        </li>
      </ul>
    </section>

    <!-- 同步附注 -->
    <footer v-if="!readonly && hasSyncDownstream" class="gt-cnt__footer-actions">
      <el-button
        size="small"
        type="primary"
        plain
        :icon="UploadIcon"
        :loading="isSyncing"
        :disabled="isSyncing"
        @click="onSyncToDisclosureNotes"
      >
        同步到附注模块
      </el-button>
      <el-tooltip
        content="C 类附注 sheet 是编辑入口，保存时自动同步到 disclosure_notes 模块对应章节。点击此按钮可手动触发同步。"
        placement="top"
      >
        <el-icon class="gt-cnt__hint-icon"><InfoFilled /></el-icon>
      </el-tooltip>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, toRef } from 'vue'
import { useRoute } from 'vue-router'
import {
  ElMessageBox,
  ElMessage,
} from 'element-plus'
import {
  Upload as UploadIcon,
  InfoFilled,
} from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import CNoteSubTableCard from './cnote/CNoteSubTableCard.vue'
import CNoteInheritanceBadge from './cnote/CNoteInheritanceBadge.vue'
import { api } from '@/services/apiProxy'
import type {
  SubClass,
  ColumnDefWithKey,
  SubTableSchema,
  ContextField,
  CrossRefDef,
  LinkageDownstreamRule,
  CNoteTableSchema,
  RowData,
  CNoteTableHtmlData,
  SyncPayload,
} from './GtCNoteTable.types'
import {
  deriveStandardFromSubClass,
  staticRowsView,
  buildEmptyRow,
  labelColumnField,
} from './cnote/cnoteHelpers'
import { useCNoteFormula } from './cnote/composables/useCNoteFormula'
import { useCNoteInheritance } from './cnote/composables/useCNoteInheritance'
import { useCNotePersist } from './cnote/composables/useCNotePersist'

const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: CNoteTableSchema
  htmlData: CNoteTableHtmlData
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  'subtable-toggle': [subTableId: string]
  'standard-switch': [standard: string]
  'sync-to-disclosure-notes': [payload: SyncPayload]
  'jump-to-reference': [refCode: string]
  'save': [data: CNoteTableHtmlData]
}>()

const subTableData = ref<Record<string, RowData[]>>({})
const hiddenSubtables = ref<string[]>([])
const contextData = ref<Record<string, any>>({})
const currentStandardSubClass = ref<SubClass>('listed')
const activeCollapse = ref<string[]>([])
const isSyncing = ref(false)
const route = useRoute()

const { cellComputedValue, footerTotalColumns, footerTotalValue } = useCNoteFormula(subTableData, currentStandardSubClass)
const { ruleStatuses, ruleStatusForSubTable } = useCNoteInheritance(toRef(props, 'schema'), subTableData, currentStandardSubClass)

const fixedCells = computed(() => props.schema?.fixed_cells ?? {})
const entityName = computed(() => fixedCells.value?.A3 || '')
const periodEnd = computed(() => fixedCells.value?.A4 || '')
const indexNo = computed(() => fixedCells.value?.I3 || fixedCells.value?.H3 || fixedCells.value?.J3 || '')
const contextFields = computed<ContextField[]>(() => Array.isArray(props.schema?.fields) ? props.schema.fields : [])

const sectionId = computed<string>(() => {
  const sec = contextData.value?.section_id
  if (sec) return String(sec)
  const def = contextFields.value.find(f => f.name === 'section_id')
  return def?.default ? String(def.default) : ''
})

const versionVariants = computed(() => props.schema?.version_variants ?? {})
const standardLabel = computed(() => versionVariants.value[currentStandardSubClass.value]?.label || '')
const standardTagType = computed<'success' | 'warning' | 'info'>(() =>
  currentStandardSubClass.value === 'listed' ? 'success' : currentStandardSubClass.value === 'soe' ? 'warning' : 'info')
const standardSwitchable = computed(() => !!(versionVariants.value.listed || versionVariants.value.soe))

const allSubTables = computed<SubTableSchema[]>(() => {
  const arr = props.schema?.sub_tables ?? []
  return Array.isArray(arr) ? [...arr].sort((a, b) => (a.order ?? 999) - (b.order ?? 999)) : []
})

const visibleSubTables = computed<SubTableSchema[]>(() => {
  const sub = currentStandardSubClass.value
  return allSubTables.value.filter(st =>
    !(st.applicable_to_sub_class && !st.applicable_to_sub_class.includes(sub))
    && !hiddenSubtables.value.includes(st.id))
})

const hiddenVisibleSubTables = computed<SubTableSchema[]>(() => {
  const sub = currentStandardSubClass.value
  return allSubTables.value.filter(st =>
    !(st.applicable_to_sub_class && !st.applicable_to_sub_class.includes(sub))
    && hiddenSubtables.value.includes(st.id))
})

const autoPullRefs = computed<CrossRefDef[]>(() => {
  const arr = props.schema?.cross_refs ?? []
  return Array.isArray(arr) ? arr.filter(r => r.auto_pull && r.direction === 'inbound') : []
})

const downstreamRules = computed<LinkageDownstreamRule[]>(() => {
  const arr = props.schema?.linkage?.downstream
  return Array.isArray(arr) ? arr : []
})
const hasSyncDownstream = computed(() => downstreamRules.value.some(r => r.target === 'disclosure_notes'))

function visibleColumns(st: SubTableSchema): ColumnDefWithKey[] {
  const sub = currentStandardSubClass.value
  return Object.entries(st.columns ?? {})
    .filter(([, col]) => !(col.applicable_to_sub_class && !col.applicable_to_sub_class.includes(sub)))
    .map(([cell, col]) => ({ ...col, _cellKey: cell }))
}

function subClassBadges(st: SubTableSchema): Array<{ value: string; label: string; type: 'success' | 'warning' | 'info' }> {
  const arr = st.applicable_to_sub_class
  if (!arr || arr.length !== 1) return []
  if (arr[0] === 'listed') return [{ value: 'listed', label: '上市专属', type: 'success' }]
  if (arr[0] === 'soe') return [{ value: 'soe', label: '国企专属', type: 'warning' }]
  return []
}

function subTableRowCount(stId: string): number { return subTableData.value[stId]?.length ?? 0 }
function reachedMaxRows(st: SubTableSchema): boolean { return (subTableData.value[st.id]?.length ?? 0) >= (st.max_rows ?? 100) }

function getStaticRowsView(st: SubTableSchema): RowData[] {
  return staticRowsView(st, subTableData.value[st.id] ?? [], visibleColumns(st))
}

function dynamicRowsView(st: SubTableSchema): RowData[] { return subTableData.value[st.id] ?? [] }

const { initData, buildSavePayload, debounceSave } = useCNotePersist({ props, subTableData, hiddenSubtables, currentStandardSubClass, contextData, activeCollapse, sectionId, allSubTables, contextFields, visibleSubTables, labelColumnField: (st: SubTableSchema) => labelColumnField(st, visibleColumns(st)), emit })

function onCellChange(_st: SubTableSchema, _row: RowData, _col: ColumnDefWithKey) { debounceSave() }

function onAddDynamicRow(st: SubTableSchema) {
  if (reachedMaxRows(st)) return
  if (!subTableData.value[st.id]) subTableData.value[st.id] = []
  subTableData.value[st.id].push(buildEmptyRow(st, visibleColumns(st), subTableData.value[st.id].length))
  debounceSave()
}
function onRemoveDynamicRow(st: SubTableSchema, idx: number) {
  const rows = subTableData.value[st.id]
  if (!rows) return
  rows.splice(idx, 1)
  if (Object.values(st.columns ?? {}).some(c => c.field === 'seq'))
    rows.forEach((r, i) => { r.seq = i + 1 })
  debounceSave()
}
async function onHideSubTable(stId: string) {
  if (props.readonly) return
  try {
    await ElMessageBox.confirm('将此子表标记为「不适用」？标记后子表将折叠隐藏，但数据保留可恢复。', '标记不适用', { confirmButtonText: '确认标记', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  if (!hiddenSubtables.value.includes(stId)) hiddenSubtables.value.push(stId)
  activeCollapse.value = activeCollapse.value.filter(id => id !== stId)
  emit('subtable-toggle', stId)
  debounceSave()
}
function onRestoreSubTable(stId: string) {
  if (props.readonly) return
  hiddenSubtables.value = hiddenSubtables.value.filter(id => id !== stId)
  if (!activeCollapse.value.includes(stId)) activeCollapse.value.push(stId)
  emit('subtable-toggle', stId)
  debounceSave()
}
async function onStandardSwitch(newSub: string | number | boolean | undefined) {
  const target = String(newSub) as SubClass
  if (target !== 'listed' && target !== 'soe') return
  const requested = target
  const previous: SubClass = requested === 'listed' ? 'soe' : 'listed'
  const lostSubTables = allSubTables.value.filter(st => st.applicable_to_sub_class?.includes(previous) && !st.applicable_to_sub_class?.includes(requested))
  const gainedSubTables = allSubTables.value.filter(st => !st.applicable_to_sub_class?.includes(previous) && st.applicable_to_sub_class?.includes(requested))
  const messages: string[] = []
  if (lostSubTables.length) messages.push(`将隐藏 ${lostSubTables.length} 张${previous === 'listed' ? '上市' : '国企'}专属子表（数据保留）：${lostSubTables.map(s => s.title).join('、')}`)
  if (gainedSubTables.length) messages.push(`将显示 ${gainedSubTables.length} 张${requested === 'listed' ? '上市' : '国企'}专属子表：${gainedSubTables.map(s => s.title).join('、')}`)
  messages.push('共有字段值会保留，仅差异字段切换显示。')
  try {
    await ElMessageBox.confirm(messages.join('\n'), `切换到${requested === 'listed' ? '上市公司版' : '国企版'}`, { confirmButtonText: '确认切换', cancelButtonText: '取消', type: 'info' })
  } catch { currentStandardSubClass.value = previous; return }
  currentStandardSubClass.value = requested
  const newStandard = deriveStandardFromSubClass(requested, contextData.value._current_standard as string)
  contextData.value._current_standard = newStandard
  emit('standard-switch', newStandard)
  debounceSave()
}
function onJumpToReference(refCode: string) { if (refCode) emit('jump-to-reference', refCode) }
async function onSyncToDisclosureNotes() {
  if (!sectionId.value) { ElMessage.warning('未配置附注章节号（section_id），无法同步'); return }
  const payload: SyncPayload = { wp_id: props.wpId, sheet_name: props.sheetName, section_id: sectionId.value, sub_table_data: { ...subTableData.value }, current_standard: deriveStandardFromSubClass(currentStandardSubClass.value, contextData.value._current_standard as string) }
  emit('sync-to-disclosure-notes', payload)
  const projectId = route.params?.projectId as string | undefined
  if (!projectId) return
  if (isSyncing.value) return
  isSyncing.value = true
  try {
    const result: any = await api.post(`/api/projects/${projectId}/disclosure-notes/sync-from-workpaper`, payload)
    ElMessage.success(`已同步 ${Number(result?.rows_synced ?? 0)} 行到附注模块「${sectionId.value}」`)
  } catch (err: any) {
    ElMessage.error(`同步附注失败：${err?.response?.data?.detail ?? err?.message ?? '未知错误'}`)
  } finally { isSyncing.value = false }
}

function onContextChange(_name: string) { debounceSave() }

initData()
watch(() => props.htmlData, () => { initData() }, { deep: true })
watch(() => props.schema, () => { initData() }, { deep: true })
</script>


<style scoped>
.gt-c-note-table { display: flex; flex-direction: column; gap: 14px; padding: 16px; }
.gt-cnt__header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; padding: 10px 14px; background: var(--gt-color-bg-soft, #f5f7fa); border-radius: 6px; font-size: 13px; }
.gt-cnt__header-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; }
.gt-cnt__entity { font-weight: 600; color: var(--el-text-color-primary); }
.gt-cnt__period, .gt-cnt__section, .gt-cnt__index { color: var(--el-text-color-regular); font-size: 12px; }
.gt-cnt__section strong, .gt-cnt__index strong { color: var(--el-color-primary); margin-left: 4px; }
.gt-cnt__header-actions { display: flex; align-items: center; gap: 10px; }
.gt-cnt__context { border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 10px 14px; background: var(--gt-color-bg-white, #fff); }
.gt-cnt__context-input, .gt-cnt__context-select { width: 160px; }
.gt-cnt__hidden-summary { margin-top: 4px; }
.gt-cnt__hidden-list { display: flex; flex-direction: column; gap: 6px; }
.gt-cnt__hidden-label { font-weight: 600; color: var(--el-text-color-regular); }
.gt-cnt__hidden-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.gt-cnt__collapse { border: none; background: transparent; }
.gt-cnt__sub-card { margin-bottom: 6px; border: 1px solid var(--el-border-color-light); border-radius: 6px; background: var(--gt-color-bg-white, #fff); }
.gt-cnt__sub-card :deep(.el-collapse-item__header) { padding: 0 12px; background: var(--gt-color-bg-soft, #f5f7fa); border-radius: 6px 6px 0 0; }
.gt-cnt__sub-card :deep(.el-collapse-item__content) { padding: 12px; }
.gt-cnt__sub-title { display: flex; flex: 1; align-items: center; gap: 8px; flex-wrap: wrap; }
.gt-cnt__sub-title-text { font-weight: 600; color: var(--el-text-color-primary); font-size: 14px; }
.gt-cnt__sub-badge { font-size: 11px; }
.gt-cnt__sub-toggle { margin-left: auto; margin-right: 8px; color: var(--el-color-warning); }
.gt-cnt__sub-desc { margin: 0 0 10px 0; padding: 6px 10px; background: var(--el-color-info-light-9); border-left: 3px solid var(--el-color-info-light-3); border-radius: 0 4px 4px 0; color: var(--el-text-color-regular); font-size: 12px; line-height: 1.5; }
.gt-cnt__refs { border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 10px 14px; background: var(--el-color-info-light-9); }
.gt-cnt__refs-title { margin: 0 0 8px 0; font-size: 13px; font-weight: 600; color: var(--el-text-color-regular); }
.gt-cnt__refs-list { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 6px; }
.gt-cnt__ref-item { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--el-text-color-regular); }
.gt-cnt__ref-desc { flex: 1; }
.gt-cnt__footer-actions { display: flex; align-items: center; gap: 8px; padding-top: 8px; }
.gt-cnt__hint-icon { color: var(--el-color-info); font-size: 14px; }
</style>
