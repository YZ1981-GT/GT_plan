<template>
  <div class="deliverable-shortcut">
    <div class="deliverable-shortcut__header" @click="navigateToCenter">
      <el-icon class="deliverable-shortcut__icon"><Document /></el-icon>
      <span class="deliverable-shortcut__title">交付物管理</span>
      <el-icon class="deliverable-shortcut__arrow"><ArrowRight /></el-icon>
    </div>

    <div class="deliverable-shortcut__summary">
      <div class="deliverable-shortcut__status-row">
        <span class="deliverable-shortcut__label">完整性</span>
        <el-tag
          :type="completeness.passed ? 'success' : 'warning'"
          size="small"
          effect="plain"
        >
          {{ completeness.passed ? '齐全' : '待完善' }}
        </el-tag>
      </div>
      <div v-if="completeness.warnings.length" class="deliverable-shortcut__warnings">
        <span
          v-for="(w, idx) in completeness.warnings.slice(0, 2)"
          :key="idx"
          class="deliverable-shortcut__warning-item"
        >
          {{ w }}
        </span>
      </div>
      <div class="deliverable-shortcut__stats">
        <span>{{ stats.total }} 件交付物</span>
        <span v-if="stats.confirmed">· {{ stats.confirmed }} 已确认</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Document, ArrowRight } from '@element-plus/icons-vue'
import { api } from '@/utils/apiProxy'

interface CompletenessResult {
  passed: boolean
  warnings: string[]
  missing_doc_types: string[]
  has_confirmed: boolean
}

const props = defineProps<{
  projectId: string
  year?: number
}>()

const emit = defineEmits<{
  'status-change': [passed: boolean]
}>()

const router = useRouter()

const completeness = ref<CompletenessResult>({
  passed: false,
  warnings: [],
  missing_doc_types: [],
  has_confirmed: false,
})

const stats = ref({ total: 0, confirmed: 0 })

async function loadCompleteness() {
  try {
    const year = props.year || new Date().getFullYear()
    const data = await api.get(
      `/api/projects/${props.projectId}/deliverables/completeness`,
      { params: { year } }
    )
    if (data) {
      completeness.value = data as CompletenessResult
      emit('status-change', completeness.value.passed)
    }
  } catch {
    // 降级：不阻塞侧边栏渲染
  }
}

async function loadStats() {
  try {
    const list = await api.get(
      `/api/projects/${props.projectId}/deliverables/`
    ) as Array<{ status: string }> | null
    if (Array.isArray(list)) {
      stats.value.total = list.length
      stats.value.confirmed = list.filter(
        (d) => d.status === 'confirmed' || d.status === 'signed'
      ).length
    }
  } catch {
    // 降级
  }
}

function navigateToCenter() {
  router.push({
    name: 'deliverable-center',
    params: { projectId: props.projectId },
  })
}

onMounted(() => {
  loadCompleteness()
  loadStats()
})

watch(() => props.projectId, () => {
  loadCompleteness()
  loadStats()
})
</script>

<style scoped>
.deliverable-shortcut {
  padding: 12px;
  border: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  border-radius: 8px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  cursor: pointer;
  transition: box-shadow 0.2s;
}
.deliverable-shortcut:hover {
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.12);
}
.deliverable-shortcut__header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}
.deliverable-shortcut__icon {
  font-size: 16px;
}
.deliverable-shortcut__title {
  flex: 1;
}
.deliverable-shortcut__arrow {
  font-size: 14px;
  opacity: 0.6;
}
.deliverable-shortcut__summary {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.deliverable-shortcut__status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.deliverable-shortcut__label {
  font-size: 12px;
}
.deliverable-shortcut__warnings {
  margin: 4px 0;
}
.deliverable-shortcut__warning-item {
  display: block;
  color: var(--el-color-warning);
  font-size: 11px;
  line-height: 1.4;
}
.deliverable-shortcut__stats {
  margin-top: 6px;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
</style>
