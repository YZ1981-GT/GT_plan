<script setup lang="ts">
/**
 * SubDocNavigator — A17 子文档快速导航栏
 *
 * 横向导航栏列出 A17-2 ~ A17-7（KAM/业务咨询/分歧记录/完成核对表/总结会/独立性声明）。
 * 已创建：可点击跳转；未创建：禁用 + tooltip。
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/services/apiProxy'
import type { SubDocItem } from './subDocMapping'

const props = defineProps<{
  projectId: string
}>()

const router = useRouter()

// ─── State ───
const subDocs = ref<SubDocItem[]>([])
const loading = ref(false)

// ─── Methods ───

async function fetchSubDocs() {
  if (!props.projectId) return
  loading.value = true
  try {
    const data = await api.get('/api/a17/sub-documents', {
      params: { project_id: props.projectId },
    })
    subDocs.value = (data as SubDocItem[]) || []
  } catch {
    subDocs.value = []
  } finally {
    loading.value = false
  }
}

function handleNavigate(item: SubDocItem) {
  if (!item.exists || !item.wp_id) return
  router.push({
    name: 'WorkpaperEditor',
    params: {
      projectId: props.projectId,
      wpId: item.wp_id,
    },
  })
}

// ─── Lifecycle ───
onMounted(() => {
  fetchSubDocs()
})

defineExpose({ refresh: fetchSubDocs })
</script>

<template>
  <div class="sub-doc-navigator" v-loading="loading">
    <span class="sub-doc-navigator__label">A17 子文档：</span>
    <div class="sub-doc-navigator__items">
      <el-tooltip
        v-for="item in subDocs"
        :key="item.wp_code"
        :content="item.exists ? `跳转至 ${item.wp_code} ${item.label}` : '该子文档尚未创建'"
        placement="bottom"
      >
        <span
          class="sub-doc-navigator__item"
          :class="{ 'is-active': item.exists, 'is-disabled': !item.exists }"
          @click="handleNavigate(item)"
        >
          {{ item.label }}
        </span>
      </el-tooltip>
    </div>
  </div>
</template>

<style scoped>
.sub-doc-navigator { display: flex; align-items: center; gap: var(--gt-space-2, 8px); padding: var(--gt-space-2, 8px) 0; border-bottom: 1px solid var(--gt-color-border-light, #ebeef5); margin-bottom: var(--gt-space-3, 12px); flex-wrap: wrap; }
.sub-doc-navigator__label { font-size: var(--gt-font-size-xs, 12px); color: var(--gt-color-text-tertiary, #a8abb2); white-space: nowrap; }
.sub-doc-navigator__items { display: flex; align-items: center; gap: var(--gt-space-1, 4px); flex-wrap: wrap; }
.sub-doc-navigator__item { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 3px; font-size: 12px; transition: all 0.2s; }
.sub-doc-navigator__item.is-active { background: var(--gt-color-primary-bg, #ecf5ff); color: var(--gt-color-primary, #409eff); border: 1px solid var(--gt-color-primary-light, #b3d8ff); cursor: pointer; }
.sub-doc-navigator__item.is-active:hover { background: var(--gt-color-primary, #409eff); color: #fff; }
.sub-doc-navigator__item.is-disabled { background: var(--gt-color-bg, #f5f7fa); color: var(--gt-color-text-placeholder, #a8abb2); border: 1px solid var(--gt-color-border-lighter, #ebeef5); cursor: not-allowed; }
</style>
