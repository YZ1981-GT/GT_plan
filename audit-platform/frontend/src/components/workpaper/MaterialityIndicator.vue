<!--
  MaterialityIndicator — A13-1 三色预警指示器

  状态映射：
  - green (success): cumulative < SAT
  - yellow (warning): SAT ≤ cumulative < PM
  - red (error): cumulative ≥ PM
  - info: PM 未确定 (null/0)
  - fraud badge: fraud_count > 0 时额外显示红色标记

  Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 3.7
-->
<template>
  <div class="materiality-indicator">
    <!-- PM 未确定态 -->
    <el-alert
      v-if="status === 'undetermined'"
      type="info"
      :closable="false"
      show-icon
    >
      <template #title>
        <span>重要性水平未确定</span>
        <el-link type="primary" class="materiality-indicator__link" @click="goToB15">
          前往 B15 设置 →
        </el-link>
      </template>
    </el-alert>

    <!-- 正常三色态 -->
    <el-alert
      v-else
      :type="alertType"
      :closable="false"
      show-icon
    >
      <template #title>
        <span class="materiality-indicator__title">
          累计未更正错报: {{ prefs.fmt(cumulativeTotal) }} 元
          <template v-if="materiality?.pm">
            &nbsp;/ PM: {{ prefs.fmt(materiality.pm) }} 元
            &nbsp;/ 比率: {{ ratioPercent }}
          </template>
        </span>
        <!-- fraud badge (Req 3.7) -->
        <el-badge
          v-if="fraudCount > 0"
          :value="fraudCount"
          class="materiality-indicator__fraud-badge"
          type="danger"
        >
          <el-tag type="danger" size="small" effect="dark">
            舞弊相关错报
          </el-tag>
        </el-badge>
      </template>
      <template #default>
        <span class="materiality-indicator__desc">{{ statusDescription }}</span>
      </template>
    </el-alert>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

interface MaterialityInfo {
  pm: number | null
  te?: number | null
  sat?: number | null
  ratio: number | null
  status: string
  fraud_flag?: boolean
}

const props = defineProps<{
  materiality?: MaterialityInfo | null
  cumulativeTotal: number
  fraudCount: number
  projectId: string
}>()

const router = useRouter()

/** 计算当前状态 */
const status = computed<string>(() => {
  if (!props.materiality) return 'undetermined'
  const pm = props.materiality.pm
  if (!pm || pm <= 0) return 'undetermined'
  return props.materiality.status || 'undetermined'
})

/** el-alert type 映射 */
const alertType = computed<'success' | 'warning' | 'error' | 'info'>(() => {
  switch (status.value) {
    case 'green': return 'success'
    case 'yellow': return 'warning'
    case 'red': return 'error'
    default: return 'info'
  }
})

/** 比率百分比 */
const ratioPercent = computed(() => {
  const ratio = props.materiality?.ratio
  if (ratio == null) return '—'
  return `${(ratio * 100).toFixed(1)}%`
})

/** 状态描述文字 */
const statusDescription = computed(() => {
  switch (status.value) {
    case 'green': return '累计未更正错报低于明显微小临界值(SAT)，不影响审计意见。'
    case 'yellow': return '累计未更正错报已超过明显微小临界值(SAT)但未达重要性水平(PM)，需持续关注。'
    case 'red': return '累计未更正错报已达到或超过重要性水平(PM)，可能影响审计意见，请评估是否出具保留意见。'
    default: return ''
  }
})

const prefs = useDisplayPrefsStore()


function goToB15() {
  router.push({
    name: 'Materiality',
    params: { projectId: props.projectId },
  })
}
</script>

<style scoped>
.materiality-indicator {
  margin-bottom: 16px;
}
.materiality-indicator__title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.materiality-indicator__fraud-badge {
  margin-left: 12px;
}
.materiality-indicator__link {
  margin-left: 12px;
  font-size: var(--wp-font-size, 13px);
}
.materiality-indicator__desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
