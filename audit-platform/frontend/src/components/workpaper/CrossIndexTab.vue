<script setup lang="ts">
/**
 * 交叉索引 Tab — 引用了/被引用 双向清单+点击跳转
 * Sprint 11 Task 11.6
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/services/apiProxy'

interface CrossRef {
  wp_code: string
  wp_name?: string
  wp_id?: string
  cell_ref?: string
  page?: number
}

const props = defineProps<{ wpId: string; wpCode: string; projectId: string }>()
const router = useRouter()

const activeTab = ref<'outgoing' | 'incoming'>('outgoing')
const outgoingRefs = ref<CrossRef[]>([])
const incomingRefs = ref<CrossRef[]>([])
const loading = ref(false)

async function loadRefs() {
  loading.value = true
  try {
    // Stub: actual API calls
    outgoingRefs.value = []
    incomingRefs.value = []
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

function navigateToWp(ref: CrossRef) {
  if (ref.wp_id) {
    router.push(`/projects/${props.projectId}/workpapers/${ref.wp_id}`)
  }
}

onMounted(loadRefs)
</script>

<template>
  <div class="cross-index-tab">
    <el-radio-group v-model="activeTab" size="small" style="margin-bottom: 12px;">
      <el-radio-button label="outgoing">引用了 ({{ outgoingRefs.length }})</el-radio-button>
      <el-radio-button label="incoming">被引用 ({{ incomingRefs.length }})</el-radio-button>
    </el-radio-group>

    <el-scrollbar max-height="300px" v-loading="loading">
      <template v-if="activeTab === 'outgoing'">
        <div v-if="outgoingRefs.length === 0" class="empty-tip">暂无引用</div>
        <div
          v-for="(r, i) in outgoingRefs"
          :key="i"
          class="ref-item"
          @click="navigateToWp(r)"
        >
          <span class="ref-code">→{{ r.wp_code }}</span>
          <span v-if="r.page" class="ref-page">第{{ r.page }}页</span>
          <span class="ref-name">{{ r.wp_name || '' }}</span>
        </div>
      </template>
      <template v-else>
        <div v-if="incomingRefs.length === 0" class="empty-tip">暂无被引用</div>
        <div
          v-for="(r, i) in incomingRefs"
          :key="i"
          class="ref-item"
          @click="navigateToWp(r)"
        >
          <span class="ref-code">{{ r.wp_code }}→</span>
          <span class="ref-cell">{{ r.cell_ref || '' }}</span>
          <span class="ref-name">{{ r.wp_name || '' }}</span>
        </div>
      </template>
    </el-scrollbar>
  </div>
</template>

<style scoped>
.cross-index-tab { padding: 12px; }
.ref-item { padding: 8px; border-bottom: 1px solid var(--gt-color-border-light); cursor: pointer; display: flex; gap: 8px; align-items: center; }
.ref-item:hover { background: var(--gt-color-primary-bg); }
.ref-code { font-weight: 600; color: var(--gt-color-primary); }
.ref-page { font-size: var(--gt-font-size-xs); color: var(--gt-color-info); }
.ref-name { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-regular); }
.ref-cell { font-size: var(--gt-font-size-xs); color: var(--gt-color-info); }
.empty-tip { text-align: center; padding: 24px; color: var(--gt-color-info); }
</style>
