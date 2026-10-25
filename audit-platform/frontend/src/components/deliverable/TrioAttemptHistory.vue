<template>
  <div class="trio-attempt-history">
    <div v-if="loading" class="trio-attempt-history__loading">
      <el-skeleton :rows="2" animated />
    </div>
    <div v-else-if="!attempts.length" class="trio-attempt-history__empty">
      暂无尝试记录
    </div>
    <el-timeline v-else>
      <el-timeline-item
        v-for="attempt in sortedAttempts"
        :key="attempt.id"
        :type="statusTimelineType(attempt.status)"
        :timestamp="formatTime(attempt.started_at)"
        placement="top"
      >
        <div class="trio-attempt-history__item">
          <div class="trio-attempt-history__header">
            <span class="trio-attempt-history__no">第 {{ attempt.attempt_no }} 次尝试</span>
            <el-tag :type="statusTagType(attempt.status)" size="small">
              {{ statusLabel(attempt.status) }}
            </el-tag>
          </div>

          <div v-if="attempt.error_message" class="trio-attempt-history__error">
            <el-icon style="color: var(--el-color-danger); margin-right: 4px"><WarningFilled /></el-icon>
            {{ attempt.error_message }}
          </div>

          <el-collapse
            v-if="attempt.error_type || attempt.diagnostic_detail"
            class="trio-attempt-history__detail"
          >
            <el-collapse-item title="诊断详情">
              <div v-if="attempt.error_type" class="trio-attempt-history__meta">
                <span class="trio-attempt-history__label">错误类型：</span>
                <code>{{ attempt.error_type }}</code>
              </div>
              <div v-if="attempt.diagnostic_detail" class="trio-attempt-history__meta">
                <span class="trio-attempt-history__label">诊断信息：</span>
                <pre class="trio-attempt-history__pre">{{ attempt.diagnostic_detail }}</pre>
              </div>
              <div v-if="attempt.snapshot_id" class="trio-attempt-history__meta">
                <span class="trio-attempt-history__label">snapshot_id：</span>
                <code>{{ attempt.snapshot_id }}</code>
              </div>
            </el-collapse-item>
          </el-collapse>

          <div v-if="attempt.finished_at" class="trio-attempt-history__time">
            完成时间：{{ formatTime(attempt.finished_at) }}
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<script setup lang="ts">
/**
 * 三件套尝试历史面板。
 *
 * Spec: chain-closure-phase4-deliverable-center-trio — 需求 5.4, 6.5
 * 展示 item 的所有 attempt（append-only），失败记录保留不覆盖。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import { getTrioItemAttempts, type TrioJobAttempt } from '@/services/deliverableApi'

const props = defineProps<{
  projectId: string
  itemId: string
}>()

const loading = ref(false)
const attempts = ref<TrioJobAttempt[]>([])

/** 按 attempt_no 升序排列 */
const sortedAttempts = computed(() =>
  [...attempts.value].sort((a, b) => a.attempt_no - b.attempt_no),
)

function statusTagType(status: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'succeeded') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'warning'
  return 'info'
}

function statusTimelineType(status: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'succeeded') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'warning'
  return 'info'
}

function statusLabel(status: string): string {
  if (status === 'succeeded') return '成功'
  if (status === 'failed') return '失败'
  if (status === 'running') return '运行中'
  return status
}

function formatTime(ts: string | null): string {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleString('zh-CN')
  } catch {
    return ts
  }
}

async function load() {
  if (!props.itemId) return
  loading.value = true
  try {
    attempts.value = await getTrioItemAttempts(props.projectId, props.itemId)
  } catch {
    attempts.value = []
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.projectId, props.itemId],
  () => load(),
)

onMounted(load)

defineExpose({ reload: load })
</script>

<style scoped>
.trio-attempt-history {
  padding: 8px 0;
}
.trio-attempt-history__loading,
.trio-attempt-history__empty {
  padding: 12px 0;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}
.trio-attempt-history__item {
  font-size: 13px;
}
.trio-attempt-history__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.trio-attempt-history__no {
  font-weight: 600;
}
.trio-attempt-history__error {
  display: flex;
  align-items: flex-start;
  color: var(--el-color-danger);
  margin: 4px 0;
  font-size: 12px;
  line-height: 1.5;
}
.trio-attempt-history__detail {
  margin-top: 4px;
}
.trio-attempt-history__detail :deep(.el-collapse-item__header) {
  height: 28px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.trio-attempt-history__meta {
  margin: 4px 0;
  font-size: 12px;
}
.trio-attempt-history__label {
  color: var(--el-text-color-secondary);
}
.trio-attempt-history__pre {
  margin: 4px 0;
  padding: 6px 8px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 120px;
  overflow: auto;
}
.trio-attempt-history__time {
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
</style>
