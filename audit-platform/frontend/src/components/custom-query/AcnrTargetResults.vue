<!--
  AcnrTargetResults.vue — 单元格取值结果区（acnr-foundation-defect-closure T16，design §2.2 / §2.6，需求 1.6 / 1.7）

  展示后端 `acnr_results` 块：中文名 / 引用 / 值 / 状态 / 原因 / 下钻。取不到（missing）与无法确定（blocked）显示原因、
  值列「—」，不显示空白或 0；文本格（text）显示原文。下钻优先用后端给的 `source.jump_route`（绑定到父底稿时也有，
  带 `sheet=`），缺它才按 addr_id 经 ACNR 解析。
-->
<template>
  <div v-if="block && block.items.length" class="gt-acnr-results" data-testid="acnr-target-results">
    <div class="gt-acnr-results-title">
      单元格取值
      <span class="gt-acnr-results-meta">年度 {{ block.year }} · 目录版本 {{ block.registry_version }}</span>
    </div>
    <el-table :data="block.items" size="small" border>
      <el-table-column label="中文名" min-width="220">
        <template #default="{ row }">{{ row.display_label || row.addr_id || row.input }}</template>
      </el-table-column>
      <el-table-column label="引用" min-width="200">
        <template #default="{ row }">{{ row.formula_ref || row.input }}</template>
      </el-table-column>
      <el-table-column label="值" min-width="120">
        <template #default="{ row }">
          <span :class="{ 'gt-amt': row.state === 'ok' }" data-testid="acnr-value">{{ valueText(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="STATE_TAG[row.state] || 'info'" effect="plain">
            {{ STATE_LABELS[row.state] || row.state }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="原因" min-width="180">
        <template #default="{ row }"><span data-testid="acnr-reason">{{ row.reason || '' }}</span></template>
      </el-table-column>
      <el-table-column label="下钻" width="120">
        <template #default="{ row }">
          <GtIndexChip
            v-if="row.addr_id"
            :value="addrIdToIndexRef(row.addr_id) || ''"
            :context-project-id="projectId || ''"
            :validate="false"
            prevent-navigate
            context="打开单元格所在底稿"
            @click="openItem(row)"
          />
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { addrIdToIndexRef, useAcnrDrill } from '@/composables/useAcnrDrill'

export interface AcnrTargetSource {
  wp_code: string | null
  sheet_code: string | null
  sheet_key?: string | null
  cell: string | null
  wp_id: string | null
  jump_route: string | null
}
export interface AcnrTargetItem {
  input: string
  addr_id: string | null
  display_label: string | null
  formula_ref: string | null
  state: 'ok' | 'text' | 'missing' | 'blocked'
  value: string | null
  text: string | null
  reason_code: string | null
  reason: string | null
  source: AcnrTargetSource | null
}
export interface AcnrResultsBlock {
  registry_version: string
  year: number
  items: AcnrTargetItem[]
}

const props = defineProps<{ block?: AcnrResultsBlock | null; projectId?: string | null }>()

/** 与后端导出「单元格取值」工作表同一套中文（export_service._STATE_LABELS） */
const STATE_LABELS: Record<string, string> = { ok: '已取值', text: '文本', missing: '取不到', blocked: '无法确定' }
const STATE_TAG: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
  ok: 'success', text: 'info', missing: 'warning', blocked: 'danger',
}

const { drill, openRoute } = useAcnrDrill(() => props.projectId || '')

function valueText(item: AcnrTargetItem): string {
  if (item.state === 'ok') return item.value ?? '—'
  if (item.state === 'text') return item.text ?? '—'
  return '—'
}

function openItem(item: AcnrTargetItem): void {
  const route = item.source?.jump_route
  if (route) openRoute(route, item.source?.cell)
  else void drill(item.addr_id)
}

defineExpose({ valueText, openItem })
</script>

<style scoped>
.gt-acnr-results { margin-bottom: 12px; }
.gt-acnr-results-title { font-weight: 600; margin-bottom: 6px; }
.gt-acnr-results-meta { margin-left: 8px; font-weight: 400; font-size: 12px; color: var(--gt-color-info, #909399); }
</style>
