<!--
  附注表格只读呈现（spec consol-autotree-linkage-closure R6）：按单体模板表头渲染附注章节 ——
  `_tables` 多表 / 旧格式单表、`headers` + `_column_groups` 两级、`multi_header` 多级（rowspan / colspan），
  续表并入主表（与附注编辑器同一投影 useNoteTableProjection；投影给出 `_column_tree` 时直接用，否则按
  consolNoteColumns 建列树，与编辑器列树同一读法），合计 / 小计行加粗；
  表后文字（章节正文）按纯文字显示，不渲染库里的 HTML。
-->
<template>
  <div class="gt-ntr" data-testid="note-tables-readonly">
    <h4 v-if="note?.section_title" class="gt-ntr-title" data-testid="ntr-title">
      {{ note.note_section }} {{ note.section_title }}
    </h4>
    <el-empty v-if="!tables.length && !text" :image-size="60" description="该章节没有表格与正文" />
    <div v-for="(t, ti) in tables" :key="ti" class="gt-ntr-block">
      <div v-if="t.name" class="gt-ntr-name" data-testid="ntr-table-name">{{ t.name }}</div>
      <div class="gt-ntr-scroll">
        <table class="gt-ntr-table" :data-testid="`ntr-table-${ti}`">
          <thead v-if="t.head.length">
            <tr v-for="(hr, hi) in t.head" :key="hi">
              <th v-for="(cell, ci) in hr" :key="ci" :colspan="cell.colspan" :rowspan="cell.rowspan">{{ cell.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in t.rows" :key="ri" :class="{ 'gt-ntr-total': isTotalRow(row) }">
              <td v-for="idx in t.leaves" :key="idx" :class="idx === 0 ? 'gt-ntr-label' : 'gt-ntr-num'">{{ noteCellText(row, idx) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div v-if="text" class="gt-ntr-text" data-testid="ntr-text">{{ text }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useNoteTableProjection } from '@/views/composables/useNoteTableProjection'
import { deriveLegacyTableHeaders, projectSubTablesClient } from '@/components/workpaper/composables/disclosureColumnDefs'
import { buildColumnTree } from '@/components/consolidation/composables/consolNoteColumns'
import {
  headerRows,
  isTotalRow,
  leafIndexes,
  noteCellText,
  plainText,
} from '@/components/consolidation/composables/consolEntityView'

defineOptions({ name: 'NoteTablesReadonly' })

const props = defineProps<{
  /** 附注章节详情（`GET /api/disclosure-notes/{pid}/{year}/{section}`）；null = 未选章节 */
  note: { note_section?: string; section_title?: string; table_data?: any; text_content?: string | null } | null
}>()

const { currentNoteTables } = useNoteTableProjection({
  currentNote: computed(() => props.note),
  projectSubTablesClient,
  deriveLegacyTableHeaders,
})

const tables = computed(() => currentNoteTables.value.map((t: any) => {
  const tree = Array.isArray(t._column_tree) ? t._column_tree : buildColumnTree(t)
  const leaves = leafIndexes(tree)
  return {
    name: String(t.name || ''),
    head: headerRows(tree),
    // 没有表头的表也要显示行名
    leaves: leaves.length ? leaves : [0],
    rows: Array.isArray(t.rows) ? t.rows : [],
  }
}))

const text = computed(() => plainText(props.note?.text_content))
</script>

<style scoped>
.gt-ntr { display: flex; flex-direction: column; gap: 12px; }
.gt-ntr-title { margin: 0; font-size: var(--gt-font-size-sm); color: var(--gt-color-primary); }
.gt-ntr-name { font-size: var(--gt-font-size-xs); font-weight: 600; color: var(--gt-color-text-primary); margin-bottom: 4px; }
.gt-ntr-scroll { overflow-x: auto; }
.gt-ntr-table { border-collapse: collapse; min-width: 100%; font-size: var(--gt-font-size-xs); }
.gt-ntr-table th, .gt-ntr-table td {
  border: 1px solid var(--gt-color-border-light, #ebeef5); padding: 3px 8px; white-space: nowrap;
}
.gt-ntr-table th { background: var(--gt-color-primary-bg, #f4f0fa); font-weight: 600; text-align: center; }
.gt-ntr-label { text-align: left; }
.gt-ntr-num { text-align: right; font-variant-numeric: tabular-nums; }
.gt-ntr-total td { font-weight: 700; }
.gt-ntr-text {
  white-space: pre-wrap; font-size: var(--gt-font-size-xs); line-height: 1.7;
  color: var(--gt-color-text-regular, #606266);
}
</style>
