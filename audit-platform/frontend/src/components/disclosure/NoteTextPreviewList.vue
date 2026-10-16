<script setup lang="ts">
/**
 * NoteTextPreviewList — 服务端预览结果三分组（推荐 / 需复核 / 不可用），上传与模板引用共用。
 *
 * - 文案全中文、显示章节标题而非内部 source_id（R-21）；
 * - 只有「推荐」默认勾选；候选映射须人工勾选确认；高风险章节不能直接勾，须在差异弹窗逐项核对（AC-3.3 / 9.1）；
 * - 不可用项可手工指定目标章节（AC-3.4），改动后须重新预览；
 * - 支持标题搜索与「仅看未匹配 / 已变更 / 已选 / 高风险」筛选（AC-2.1 / 设计 §9.3），底部勾选摘要（AC-9.6）。
 */
import { computed, ref } from 'vue'
import type { ApplyMode, PreviewItem, TargetSection } from '@/composables/useNoteTextBatch'
import { CONFIDENCE_LABELS, flagLabel, highRiskFlags, selectionSummary, targetLabel } from './noteTextBatchLabels'

const props = defineProps<{
  items: PreviewItem[]
  selected: string[]
  modes: Record<string, ApplyMode>
  editedIds?: string[]
  /** 提供时在不可用项上显示「指定目标章节」（可写入的节） */
  targets?: TargetSection[]
  /** 有子节点的章：只给有子标题的来源选，作定位锚点（第 23 组：先对应上级，其下小标题在该章内定位） */
  anchors?: TargetSection[]
  mappings?: Record<string, string>
}>()

const emit = defineEmits<{
  'update:selected': [ids: string[]]
  'open-diff': [item: PreviewItem]
  'map': [sourceId: string, targetNoteId: string | null]
}>()

const keyword = ref('')
const onlyUnmatched = ref(false)
const onlyEdited = ref(false)
const onlySelected = ref(false)
const onlyHighRisk = ref(false)
const selectedSet = computed(() => new Set(props.selected))

const visibleItems = computed(() => {
  const kw = keyword.value.trim()
  const edited = new Set(props.editedIds ?? [])
  return props.items.filter(i =>
    (!kw || i.source_title.includes(kw) || targetLabel(i).includes(kw))
    && (!onlyUnmatched.value || !i.target_note_id)
    && (!onlyEdited.value || edited.has(i.source_id))
    && (!onlySelected.value || selectedSet.value.has(i.source_id))
    && (!onlyHighRisk.value || highRiskFlags(i).length > 0))
})
/** AC-2.3：类别内再按目标所属一级章分组（保持预览顺序）；无目标的归「未匹配目标章节」 */
function byChapter(items: PreviewItem[]): Array<{ title: string; items: PreviewItem[] }> {
  const out: Array<{ title: string; items: PreviewItem[] }> = []
  for (const item of items) {
    const title = item.target_note_id ? (item.target_chapter_title || '其他章节') : '未匹配目标章节'
    const bucket = out.find(c => c.title === title)
    if (bucket) bucket.items.push(item)
    else out.push({ title, items: [item] })
  }
  return out
}

const groups = computed(() => [
  { key: 'recommended', title: '🟢 推荐引用', items: visibleItems.value.filter(i => i.category === 'recommended') },
  { key: 'review', title: '🟡 需复核', items: visibleItems.value.filter(i => i.category === 'review') },
  { key: 'unavailable', title: '⚪ 不可用', items: visibleItems.value.filter(i => i.category === 'unavailable') },
].filter(g => g.items.length).map(g => ({ ...g, chapters: byChapter(g.items) })))
const summary = computed(() => selectionSummary(props.items, selectedSet.value, props.modes))

function setChecked(item: PreviewItem, checked: boolean) {
  const next = new Set(props.selected)
  if (checked) next.add(item.source_id)
  else next.delete(item.source_id)
  emit('update:selected', [...next])
}

function modeLabel(item: PreviewItem): string {
  if (item.append_html === null) return '新增'
  return props.modes[item.source_id] === 'append' ? '追加' : '替换'
}
</script>

<template>
  <div class="gt-ntp">
    <div class="gt-ntp-filters">
      <el-input v-model="keyword" size="small" clearable placeholder="按章节标题搜索" style="width: 200px" />
      <el-checkbox v-model="onlyUnmatched" size="small">仅看未匹配</el-checkbox>
      <el-checkbox v-if="editedIds" v-model="onlyEdited" size="small">仅看已变更</el-checkbox>
      <el-checkbox v-model="onlySelected" size="small">仅看已选</el-checkbox>
      <el-checkbox v-model="onlyHighRisk" size="small">仅看高风险</el-checkbox>
    </div>
    <div v-if="!items.length" class="gt-ntp-empty">没有可预览的章节</div>
    <section v-for="g in groups" :key="g.key" :class="['gt-ntp-group', `gt-ntp-${g.key}`]">
      <h4>{{ g.title }}（{{ g.items.length }}）</h4>
      <template v-for="c in g.chapters" :key="c.title">
      <div class="gt-ntp-chapter">{{ c.title }}（{{ c.items.length }}）</div>
      <div v-for="item in c.items" :key="item.source_id" class="gt-ntp-row" :data-source-id="item.source_id">
        <template v-if="g.key !== 'unavailable'">
          <el-button v-if="highRiskFlags(item).length && !selectedSet.has(item.source_id)" size="small" type="warning" plain
            @click="emit('open-diff', item)">核对后采用</el-button>
          <el-checkbox v-else :model-value="selectedSet.has(item.source_id)" @change="(v: any) => setChecked(item, !!v)" />
          <span class="gt-ntp-title">{{ item.source_title }} → {{ targetLabel(item) }}</span>
          <el-tag size="small" :type="item.confidence === 'confirmed' ? 'success' : 'warning'">{{ CONFIDENCE_LABELS[item.confidence] ?? '需人工选择' }}</el-tag>
          <el-tag size="small" type="info">{{ modeLabel(item) }}</el-tag>
          <el-tag v-for="flag in item.quality_flags" :key="flag" size="small" type="danger" effect="plain">{{ flagLabel(flag) }}</el-tag>
          <el-button size="small" link type="primary" @click="emit('open-diff', item)">查看差异</el-button>
          <div class="gt-ntp-evidence">{{ item.evidence }}</div>
        </template>
        <template v-else>
          <span class="gt-ntp-title">{{ item.source_title }}</span>
          <span class="gt-ntp-reason">{{ item.unavailable_reason || '不可用' }}</span>
          <el-select v-if="targets" size="small" filterable clearable style="width: 280px"
            :placeholder="item.structural && anchors?.length ? '指定目标章或目标章节' : '指定目标章节'"
            :model-value="mappings?.[item.source_id] ?? ''"
            @update:model-value="(v: any) => emit('map', item.source_id, v || null)">
            <el-option-group v-if="item.structural && anchors?.length" label="目标章（其下小标题在该章内定位）">
              <el-option v-for="t in anchors" :key="t.id" :value="t.id" :label="`【章】${t.note_section} ${t.section_title}`" />
            </el-option-group>
            <el-option-group :label="item.structural && anchors?.length ? '写入章节（其下小标题一并并入）' : '写入章节'">
              <el-option v-for="t in targets" :key="t.id" :value="t.id" :label="`${t.note_section} ${t.section_title}`" />
            </el-option-group>
          </el-select>
        </template>
      </div>
      </template>
    </section>
    <div v-if="items.length" class="gt-ntp-summary">
      已选 {{ summary.total }} 章：新增 {{ summary.new }} · 替换 {{ summary.replace }} · 追加 {{ summary.append }}
      · 高风险 {{ summary.highRisk }} · 未映射 {{ summary.unmapped }}
    </div>
  </div>
</template>

<style scoped>
.gt-ntp-filters { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.gt-ntp-empty { text-align: center; color: var(--el-text-color-placeholder); padding: 32px 0; }
.gt-ntp-group h4 { margin: 12px 0 6px; font-size: 13px; }
.gt-ntp-chapter { margin: 8px 0 4px; padding-left: 4px; font-size: 12px; font-weight: 600; color: var(--el-text-color-regular); border-left: 3px solid var(--el-border-color); }
.gt-ntp-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 6px 8px; margin-bottom: 4px; border-radius: 4px; background: var(--el-fill-color-lighter); }
.gt-ntp-recommended .gt-ntp-row { background: var(--el-color-success-light-9); }
.gt-ntp-review .gt-ntp-row { background: var(--el-color-warning-light-9); }
.gt-ntp-title { font-size: 13px; }
.gt-ntp-reason { font-size: 12px; color: var(--el-text-color-secondary); }
.gt-ntp-evidence { flex-basis: 100%; font-size: 12px; color: var(--el-text-color-secondary); padding-left: 24px; }
.gt-ntp-summary { margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--el-border-color-lighter); font-size: 13px; color: var(--el-text-color-secondary); }
</style>
