<script setup lang="ts">
/**
 * EQCR 充分性评价视图 — 关键底稿筛选+快捷评价+IssueTicket 联动
 * Sprint 11 Task 11.4
 */
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

interface WorkpaperItem {
  id: string
  wp_code: string
  wp_name: string
  verdict?: string
}

const props = defineProps<{ projectId: string }>()

const workpapers = ref<WorkpaperItem[]>([])
const loading = ref(false)
const evaluating = ref<string | null>(null)

const verdictOptions = [
  { value: 'sufficient', label: '充分', type: 'success' as const },
  { value: 'needs_supplement', label: '需补充', type: 'warning' as const },
  { value: 'major_concern', label: '重大疑虑', type: 'danger' as const },
]

async function loadWorkpapers() {
  loading.value = true
  try {
    // Load key workpapers for EQCR evaluation
    const data = await api.get(`/api/projects/${props.projectId}/eqcr-evaluation`)
    workpapers.value = (data as any).evaluations || []
  } catch {
    // Fallback empty
  } finally {
    loading.value = false
  }
}

async function submitVerdict(wp: WorkpaperItem, verdict: string) {
  evaluating.value = wp.id
  try {
    await api.post(`/api/projects/${props.projectId}/eqcr-evaluation`, {
      wp_id: wp.id,
      verdict,
    })
    wp.verdict = verdict
    ElMessage.success('评价已提交')
  } catch {
    ElMessage.error('提交失败')
  } finally {
    evaluating.value = null
  }
}

function verdictTag(verdict?: string) {
  return verdictOptions.find(v => v.value === verdict)
}

onMounted(loadWorkpapers)
</script>

<template>
  <div class="eqcr-evaluation-panel">
    <div class="panel-header">
      <span class="title">EQCR 充分性评价</span>
    </div>
    <el-table :data="workpapers" v-loading="loading" size="small">
      <el-table-column prop="wp_code" label="底稿编码" width="120" />
      <el-table-column prop="wp_name" label="底稿名称" />
      <el-table-column label="评价" width="280">
        <template #default="{ row }">
          <div v-if="row.verdict" class="verdict-display">
            <el-tag :type="verdictTag(row.verdict)?.type || 'info'" size="small">
              {{ verdictTag(row.verdict)?.label || row.verdict }}
            </el-tag>
          </div>
          <div v-else class="verdict-actions">
            <el-button
              v-for="opt in verdictOptions"
              :key="opt.value"
              :type="opt.type"
              size="small"
              :loading="evaluating === row.id"
              @click="submitVerdict(row, opt.value)"
            >
              {{ opt.label }}
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.eqcr-evaluation-panel { padding: 12px; }
.panel-header { margin-bottom: 12px; }
.title { font-weight: 600; font-size: var(--gt-font-size-sm); }
.verdict-actions { display: flex; gap: 4px; }
</style>
