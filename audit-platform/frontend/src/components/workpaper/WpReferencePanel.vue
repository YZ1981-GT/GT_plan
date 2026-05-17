<template>
  <div class="gt-wp-ref-panel">
    <div v-if="loading" v-loading="true" style="min-height: 120px"></div>
    <el-empty v-else-if="!data || data.total_connections === 0" description="暂无跨模块引用" :image-size="64" />
    <el-collapse v-else v-model="activeNames">
      <!-- 上游依赖 -->
      <el-collapse-item name="incoming" :title="`上游依赖 (${data.incoming.length})`">
        <div v-for="item in data.incoming" :key="item.ref_id" class="gt-ref-item" @click="$emit('navigate', item.source_wp)">
          <div class="gt-ref-item__header">
            <el-tag :type="severityType(item.severity)" size="small">{{ item.severity }}</el-tag>
            <span class="gt-ref-item__wp">{{ item.source_wp }}</span>
          </div>
          <div class="gt-ref-item__desc">{{ item.description }}</div>
          <div v-if="item.formula" class="gt-ref-item__formula">公式: {{ item.formula }}</div>
        </div>
      </el-collapse-item>

      <!-- 下游影响 -->
      <el-collapse-item name="outgoing" :title="`下游影响 (${data.outgoing.length})`">
        <div v-for="item in data.outgoing" :key="item.ref_id" class="gt-ref-item" @click="$emit('navigate', item.target_wp)">
          <div class="gt-ref-item__header">
            <el-tag :type="severityType(item.severity)" size="small">{{ item.severity }}</el-tag>
            <span class="gt-ref-item__wp">→ {{ item.target_wp }}</span>
            <span v-if="item.target_sheet" class="gt-ref-item__sheet">{{ item.target_sheet }}</span>
          </div>
          <div class="gt-ref-item__desc">{{ item.description }}</div>
        </div>
      </el-collapse-item>

      <!-- 模块联动 -->
      <el-collapse-item name="modules" :title="`模块联动 (${data.module_links.length})`">
        <div v-for="item in data.module_links" :key="item.ref_id" class="gt-ref-item">
          <div class="gt-ref-item__header">
            <el-tag type="info" size="small">{{ item.link_type || '联动' }}</el-tag>
            <span class="gt-ref-item__wp">{{ item.target_module }}</span>
          </div>
          <div class="gt-ref-item__desc">{{ item.description }}</div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/services/apiProxy'

interface RefItem {
  ref_id: string
  source_wp?: string
  target_wp?: string
  target_sheet?: string
  target_module?: string
  link_type?: string
  description: string
  severity?: string
  formula?: string
  category?: string
}

interface RefData {
  wp_code: string
  primary_code: string
  incoming: RefItem[]
  outgoing: RefItem[]
  module_links: RefItem[]
  total_connections: number
}

const props = defineProps<{
  wpId: string
}>()

defineEmits<{
  navigate: [wpCode: string]
}>()

const data = ref<RefData | null>(null)
const loading = ref(false)
const activeNames = ref(['incoming', 'outgoing', 'modules'])

function severityType(severity?: string) {
  if (severity === 'error' || severity === 'critical') return 'danger'
  if (severity === 'warning') return 'warning'
  return 'info'
}

async function loadReferences() {
  if (!props.wpId) return
  loading.value = true
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/references`)
    data.value = res as RefData
  } catch (e) {
    console.warn('Failed to load references:', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadReferences()
})
</script>

<style scoped>
.gt-wp-ref-panel {
  padding: 8px;
}
.gt-ref-item {
  padding: 8px 12px;
  margin-bottom: 6px;
  border-radius: 6px;
  background: var(--gt-color-bg-light, #f8f7fc);
  cursor: pointer;
  transition: background 0.2s;
}
.gt-ref-item:hover {
  background: var(--gt-color-bg-hover, #f0edf5);
}
.gt-ref-item__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.gt-ref-item__wp {
  font-weight: 600;
  font-size: 13px;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-ref-item__sheet {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #999);
}
.gt-ref-item__desc {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #666);
  line-height: 1.4;
}
.gt-ref-item__formula {
  font-size: 11px;
  color: var(--gt-color-text-tertiary, #999);
  font-family: 'Courier New', monospace;
  margin-top: 2px;
}
</style>
