<template>
  <div class="procedure-table-renderer" v-loading="loading">
    <div v-if="error" class="pt-error">{{ error }}</div>
    <template v-else-if="tableData">
      <div class="pt-header">
        <h3>{{ tableData.table_name }}</h3>
      </div>
      <el-table :data="tableData.items" class="gt-compact-table" stripe>
        <el-table-column prop="seq" label="序号" width="60" align="center" />
        <el-table-column prop="content" label="审计程序" min-width="280" />
        <el-table-column prop="ref_index" label="索引号" width="110">
          <template #default="{ row }">
            <el-button v-if="row.ref_index" link type="primary" size="small" @click="jumpToRef(row.ref_index)">
              {{ row.ref_index }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="适用" width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="row.applicable === 'yes' ? 'success' : row.applicable === 'na' ? 'info' : 'warning'" size="small">
              {{ row.applicable === 'yes' ? '是' : row.applicable === 'na' ? 'N/A' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="自动状态" min-width="160">
          <template #default="{ row }">
            <span v-if="row.summary" class="pt-auto-summary">{{ row.summary }}</span>
            <span v-else class="pt-no-data">—</span>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { apiProxy } from '@/utils/apiProxy'
import { useRouter } from 'vue-router'

const props = defineProps<{
  wpId: string
  projectId?: string
  wpCode?: string
  year?: number
}>()

const emit = defineEmits<{ (e: 'save'): void }>()

const router = useRouter()
const loading = ref(false)
const error = ref('')
const tableData = ref<any>(null)

async function load() {
  if (!props.wpCode || !props.projectId) {
    error.value = '缺少程序表编码或项目信息'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const year = props.year || new Date().getFullYear()
    tableData.value = await apiProxy.get(
      `/api/projects/${props.projectId}/procedure-tables/${props.wpCode}?year=${year}`
    )
  } catch (e: any) {
    error.value = e?.message || '加载程序表失败'
  } finally {
    loading.value = false
  }
}

function jumpToRef(refIndex: string) {
  // 使用 useWorkpaperNavigation 的跳转逻辑
  if (props.projectId) {
    router.push({ name: 'WorkpaperByCode', params: { projectId: props.projectId }, query: { wp_code: refIndex } })
  }
}

onMounted(load)
watch(() => props.wpCode, load)
</script>

<style scoped>
.procedure-table-renderer { padding: 16px; }
.pt-header h3 { margin: 0 0 12px; font-size: 16px; color: var(--gt-color-text-primary); }
.pt-auto-summary { color: var(--gt-purple, #4b2d77); font-size: 12px; }
.pt-no-data { color: var(--el-text-color-placeholder); }
.pt-error { color: var(--el-color-danger); padding: 24px; text-align: center; }
</style>
