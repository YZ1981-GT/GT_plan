<template>
  <div class="g2-tab-index" data-testid="g2-tab-index">
    <div class="g2-tab-index__toolbar">
      <el-button size="small" type="primary" plain @click="emit('open-handbook', 'preparation')">
        📖 编制手册
      </el-button>
      <el-button size="small" @click="emit('open-handbook', 'usage')">使用手册</el-button>
    </div>

    <h3 class="g2-tab-index__title">底稿目录</h3>
    <p class="g2-tab-index__hint">点击索引号跳转对应底稿（对齐 D4 目录体验）</p>

    <el-table :data="rows" border stripe style="width: 100%" size="small">
      <el-table-column prop="seq" label="序号" width="60" align="center" />
      <el-table-column prop="indexCode" label="索引号" width="110">
        <template #default="{ row }">
          <GtIndexChip
            v-if="row.indexCode"
            :label="row.indexCode"
            @click="onJump(row.indexCode)"
          />
          <span v-else>{{ row.indexCode }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="底稿名称" min-width="220" />
      <el-table-column label="Excel Sheet" min-width="200">
        <template #default="{ row }">
          <span class="g2-tab-index__sheet">{{ resolveLabel(row.indexCode) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <GCycleBIndexExtras
      v-if="showArchitecture"
      class="g2-tab-index__architecture"
      :wp-id="wpId"
      :project-id="projectId"
      :sheet-name="sheetName"
      :wp-code="wpCode"
      :html-data="architectureHtmlData"
      :available-sheets="resolvedSheets"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * G2TabIndex — 应收利息底稿目录（对齐 D4TabIndex：静态清单 + 跳转）
 */
import { computed, inject } from 'vue'
import GtIndexChip from '../GtIndexChip.vue'
import GCycleBIndexExtras from '../shared/GCycleBIndexExtras.vue'
import {
  G2_DIRECTORY_ROWS,
  G2_SHEET_LABEL_MAP,
  buildG2FallbackSheets,
  resolveG2SheetLabel,
} from '../composables/g2SheetLabels'
import { buildCycleArchitectureHtmlData } from '../composables/gCycleIndexRouting'

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: Record<string, unknown>
  availableSheets?: Array<{ sheet_name?: string; componentType?: string }>
}>()

const emit = defineEmits<{
  (e: 'open-handbook', tab: 'preparation' | 'usage'): void
  (e: 'jump', code: string): void
}>()

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const rows = G2_DIRECTORY_ROWS

const resolvedSheets = computed(() => {
  if (props.availableSheets?.length) return props.availableSheets
  return buildG2FallbackSheets()
})

const architectureHtmlData = computed(() =>
  buildCycleArchitectureHtmlData(props.htmlData, resolvedSheets.value, props.wpCode),
)

const showArchitecture = computed(() => {
  const rowsNav = architectureHtmlData.value?.navigation_rows
  return Array.isArray(rowsNav) && rowsNav.length > 0
})

function resolveLabel(code: string): string {
  return resolveG2SheetLabel(code, resolvedSheets.value) || G2_SHEET_LABEL_MAP[code] || code
}

function onJump(code: string) {
  const label = resolveLabel(code)
  emit('jump', code)
  if (jumpToSection) jumpToSection(label)
}
</script>

<style scoped>
.g2-tab-index { padding: 4px 0 12px; }
.g2-tab-index__toolbar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.g2-tab-index__title { margin: 0 0 4px; font-size: 15px; font-weight: 600; }
.g2-tab-index__hint { margin: 0 0 12px; color: var(--el-text-color-secondary); font-size: 12px; }
.g2-tab-index__sheet { color: var(--el-text-color-secondary); font-size: 12px; }
.g2-tab-index__architecture { margin-top: 20px; }
</style>
