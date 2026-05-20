<template>
  <el-dialog
    :model-value="visible"
    title="单元格公式详情"
    width="680px"
    append-to-body
    destroy-on-close
    @update:model-value="$emit('update:visible', $event)"
  >
    <div v-loading="loading" class="gt-cell-detail">
      <!-- URI 标识 -->
      <div class="gt-cell-detail-uri">
        <el-tag type="info" size="small">{{ detail?.uri || '—' }}</el-tag>
        <el-tag v-if="detail?.is_stale" type="warning" size="small">⚠ Stale</el-tag>
      </div>

      <!-- 公式 -->
      <div v-if="detail?.formula" class="gt-cell-detail-section">
        <div class="gt-cell-detail-title">📐 公式</div>
        <div class="gt-cell-detail-formula">{{ detail.formula }}</div>
      </div>

      <!-- 来源（上游） -->
      <div class="gt-cell-detail-section">
        <div class="gt-cell-detail-title">⬆ 来源 ({{ detail?.upstream?.length || 0 }})</div>
        <div v-if="!detail?.upstream?.length" class="gt-cell-detail-empty">无上游来源</div>
        <div v-else class="gt-cell-detail-list">
          <div
            v-for="(item, idx) in detail.upstream"
            :key="'up-' + idx"
            class="gt-cell-detail-item"
            @click="onNavigate(item)"
          >
            <span class="gt-cell-detail-icon">{{ getModuleIcon(item.module) }}</span>
            <span class="gt-cell-detail-item-uri">{{ item.uri }}</span>
          </div>
        </div>
      </div>

      <!-- 去向（下游） -->
      <div class="gt-cell-detail-section">
        <div class="gt-cell-detail-title">⬇ 去向 ({{ detail?.downstream?.length || 0 }})</div>
        <div v-if="!detail?.downstream?.length" class="gt-cell-detail-empty">无下游引用</div>
        <div v-else class="gt-cell-detail-list">
          <div
            v-for="(item, idx) in detail.downstream"
            :key="'dn-' + idx"
            class="gt-cell-detail-item"
            @click="onNavigate(item)"
          >
            <span class="gt-cell-detail-icon">{{ getModuleIcon(item.module) }}</span>
            <span class="gt-cell-detail-item-uri">{{ item.uri }}</span>
          </div>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import http from '@/utils/http'
import { linkageBus } from '@/services/apiPaths'

interface UriItem {
  uri: string
  module: string
  code: string
  sheet: string
  label: string
}

interface CellDetail {
  uri: string
  upstream: UriItem[]
  downstream: UriItem[]
  formula: string
  is_stale: boolean
}

const props = defineProps<{
  visible: boolean
  wpCode: string
  sheetName: string
  label: string
  module?: string  // 模块标识 WP/TB/REPORT/NOTE/ADJ，默认 WP
}>()

const emit = defineEmits<{
  'update:visible': [val: boolean]
  navigate: [uri: string]
}>()

const loading = ref(false)
const detail = ref<CellDetail | null>(null)

watch(() => props.visible, async (val) => {
  if (!val) return
  await fetchDetail()
})

async function fetchDetail() {
  if (!props.wpCode) return
  loading.value = true
  try {
    const mod = (props.module || 'WP').toUpperCase()
    if (mod === 'WP') {
      // WP 模块走 cell-detail（一站式 upstream + downstream）
      const params: Record<string, string> = { wp_code: props.wpCode }
      if (props.sheetName) params.sheet_name = props.sheetName
      if (props.label) params.label = props.label
      const res = await http.get(linkageBus.cellDetail, { params })
      detail.value = res.data
    } else {
      // 其他模块组合 /formulas-for（上游来源）+ /formula-usage（下游引用）
      const baseUri = `${mod}:${props.wpCode}:${props.sheetName || ''}:${props.label || ''}`
      const [forRes, usageRes] = await Promise.all([
        http.get(linkageBus.formulasFor, { params: { module: mod, code: props.wpCode } })
          .catch(() => ({ data: { formulas: [] } })),
        http.get(linkageBus.formulaUsage, { params: { formula_uri: baseUri } })
          .catch(() => ({ data: { references: [] } })),
      ])
      const upstreamMap = new Map<string, any>()
      for (const f of (forRes.data?.formulas || [])) {
        const u = f.source_uri || ''
        if (!u || upstreamMap.has(u)) continue
        const parts = u.split(':')
        upstreamMap.set(u, {
          uri: u,
          module: parts[0] || '',
          code: parts[1] || '',
          sheet: parts[2] || '',
          label: parts[3] || '',
        })
      }
      const upstream = Array.from(upstreamMap.values())
      const downstream = usageRes.data?.references || []
      detail.value = {
        uri: baseUri,
        upstream,
        downstream,
        formula: '',
        is_stale: false,
      }
    }
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
}

function getModuleIcon(module: string): string {
  const icons: Record<string, string> = {
    WP: '📋',
    TB: '📊',
    REPORT: '📈',
    NOTE: '📝',
    ADJ: '✏️',
    FORMULA: 'ƒx',
    MAPPING: '🔗',
  }
  return icons[module?.toUpperCase()] || '📄'
}

function onNavigate(item: UriItem) {
  emit('navigate', item.uri)
}
</script>

<style scoped>
.gt-cell-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.gt-cell-detail-uri {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-cell-detail-section {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px;
}
.gt-cell-detail-title {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
}
.gt-cell-detail-formula {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  background: var(--el-fill-color-light);
  padding: 8px 12px;
  border-radius: 4px;
  word-break: break-all;
}
.gt-cell-detail-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 200px;
  overflow-y: auto;
}
.gt-cell-detail-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}
.gt-cell-detail-item:hover {
  background: var(--el-fill-color-light);
}
.gt-cell-detail-icon {
  flex-shrink: 0;
}
.gt-cell-detail-item-uri {
  font-size: 12px;
  color: var(--el-text-color-regular);
  font-family: 'Consolas', 'Monaco', monospace;
}
.gt-cell-detail-empty {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  text-align: center;
  padding: 8px;
}
</style>
