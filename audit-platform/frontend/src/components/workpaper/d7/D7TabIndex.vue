<script setup lang="ts">
/**
 * D7TabIndex — 统一底稿目录（比照 D5TabIndex）
 */
import { computed, inject } from 'vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { D7_INDEX_ROWS, resolveD7SheetLabel } from '../composables/d7SheetLabels'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  availableSheets?: Array<{ sheet_name?: string }>
}>()

const indexRows = computed(() =>
  D7_INDEX_ROWS.map(row => ({
    ...row,
    sheetLabel: resolveD7SheetLabel(row.code, props.availableSheets),
  })),
)

function hasJsonRows(m: Map<string, any>, key: string): boolean {
  const raw = m.get(key)?.remark
  if (!raw) return false
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) && parsed.length > 0
  } catch {
    return false
  }
}

function isSheetComplete(code: string, m: Map<string, any>): boolean {
  switch (code) {
    case 'D7A':
      return [...m.keys()].some(k => k.startsWith('D7-proc-'))
    case 'D7-1':
      return [...m.keys()].some(k => k.startsWith('D7-1-adj-'))
    case 'D7-2':
      return hasJsonRows(m, 'D7-2-rows')
    case 'D7-3':
      return hasJsonRows(m, 'D7-3-rows')
    case 'D7-4':
      return hasJsonRows(m, 'D7-4-rows')
    case 'D7-5':
      return hasJsonRows(m, 'D7-5-rows')
    case 'D7-6':
      return hasJsonRows(m, 'D7-6-rows')
    case 'D7-7':
      return hasJsonRows(m, 'D7-7-rows')
    case 'D7-附注上市':
    case 'D7-附注国企':
      return [...m.keys()].some(k => k.startsWith('D7-note-'))
    default:
      return false
  }
}

const applicableRows = computed(() => indexRows.value.filter(r => r.applicable))

const completedCount = computed(() =>
  applicableRows.value.filter(r => isSheetComplete(r.code, props.allResponses)).length,
)

const progressPct = computed(() => {
  const total = applicableRows.value.length
  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0
})

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

function navigateToSheet(row: { applicable: boolean; sheetLabel: string }) {
  if (!row.applicable || !jumpToSection) return
  jumpToSection(row.sheetLabel)
}
</script>

<template>
  <div class="d7-tab-index">
    <div class="index-header">
      <h3>D7 合同负债底稿目录</h3>
      <GtReviewTrigger section-id="D7-index-directory" />
      <div class="progress-wrap">
        <span class="progress-label">编制进度 {{ completedCount }}/{{ applicableRows.length }}</span>
        <el-progress :percentage="progressPct" :stroke-width="8" :show-text="false" />
      </div>
    </div>

    <el-table :data="indexRows" border size="small" style="width: 100%">
      <el-table-column prop="seq" label="序号" width="60" align="center" />
      <el-table-column prop="name" label="底稿名称" min-width="260" />
      <el-table-column prop="code" label="编码" width="110" align="center" />
      <el-table-column prop="group" label="分组" width="80" align="center" />
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="isSheetComplete(row.code, allResponses)" type="success" size="small">已编制</el-tag>
          <el-tag v-else type="info" size="small">待编制</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="跳转" width="80" align="center">
        <template #default="{ row }">
          <span
            v-if="row.applicable"
            class="gt-index-chip"
            :title="`跳转到 ${row.name}`"
            @click="navigateToSheet(row)"
          >→</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.d7-tab-index { padding: 12px; }
.index-header { margin-bottom: 16px; }
.index-header h3 { margin: 0 0 12px; font-size: 16px; }
.progress-wrap { padding: 12px 16px; background: #f5f7fa; border-radius: 6px; }
.progress-label { display: block; margin-bottom: 8px; font-size: 13px; color: #606266; }
.gt-index-chip {
  display: inline-block;
  padding: 2px 8px;
  font-size: 12px;
  background: #e6f7ff;
  border: 1px solid #91d5ff;
  border-radius: 4px;
  color: #1890ff;
  cursor: pointer;
}
.gt-index-chip:hover { background: #bae7ff; }
</style>
