<template>
  <el-drawer
    v-model="visible"
    title="📜 对比上年底稿"
    direction="rtl"
    size="80%"
    :before-close="handleClose"
    class="prior-year-compare-drawer"
  >
    <div v-if="loading" class="drawer-loading">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <p>正在加载上年底稿...</p>
    </div>

    <div v-else-if="error" class="drawer-error">
      <el-empty :description="error" />
    </div>

    <div v-else class="compare-container">
      <!-- 双栏对比 -->
      <div class="compare-columns">
        <!-- 左栏：当前底稿（只读） -->
        <div class="compare-column">
          <div class="column-header">
            <el-tag type="primary" size="small">当前</el-tag>
            <span class="column-title">{{ currentWpCode }} - 当前年度</span>
          </div>
          <div class="column-body">
            <div class="readonly-data-card" v-if="currentData">
              <div class="data-row" v-if="currentData.conclusion">
                <label>结论：</label>
                <div class="data-value conclusion-text">{{ currentData.conclusion }}</div>
              </div>
              <div class="data-row" v-if="currentData.audited_amount != null">
                <label>审定金额：</label>
                <div class="data-value">{{ formatAmount(currentData.audited_amount) }}</div>
              </div>
              <div class="data-row" v-if="!currentData.conclusion && currentData.audited_amount == null">
                <el-empty description="当前底稿暂无结论数据" :image-size="60" />
              </div>
            </div>
          </div>
        </div>

        <!-- 右栏：上年底稿（只读） -->
        <div class="compare-column">
          <div class="column-header">
            <el-tag type="success" size="small">上年</el-tag>
            <span class="column-title">{{ priorYearData?.wp_code || '—' }} - 上年度</span>
          </div>
          <div class="column-body">
            <div class="readonly-data-card" v-if="priorYearData">
              <div class="data-row" v-if="priorYearData.conclusion">
                <label>结论：</label>
                <div class="data-value conclusion-text">{{ priorYearData.conclusion }}</div>
              </div>
              <div class="data-row" v-if="priorYearData.audited_amount != null">
                <label>审定金额：</label>
                <div class="data-value">{{ formatAmount(priorYearData.audited_amount) }}</div>
              </div>
              <div class="data-row" v-if="priorYearData.file_url">
                <label>底稿文件：</label>
                <div class="data-value">
                  <el-link type="primary" :href="priorYearData.file_url" target="_blank">
                    查看上年底稿文件
                  </el-link>
                </div>
              </div>
              <div class="data-row" v-if="!priorYearData.conclusion && priorYearData.audited_amount == null">
                <el-empty description="上年底稿暂无结论数据" :image-size="60" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 操作区 -->
      <div class="compare-actions" v-if="priorYearData?.conclusion">
        <el-button
          type="primary"
          @click="onCopyConclusion"
          :loading="copying"
        >
          📋 复制上年结论到今年
        </el-button>
        <span class="action-hint">将上年结论复制到当前底稿结论区（需确认）</span>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'

interface PriorYearData {
  wp_id: string
  wp_code: string
  file_url: string | null
  conclusion: string | null
  audited_amount: number | null
}

const props = defineProps<{
  projectId: string
  wpId: string
  currentWpCode: string
  currentConclusion?: string | null
  currentAuditedAmount?: number | null
}>()

const emit = defineEmits<{
  (e: 'copy-conclusion', conclusion: string): void
  (e: 'close'): void
}>()

const visible = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const copying = ref(false)
const priorYearData = ref<PriorYearData | null>(null)

const currentData = ref<{ conclusion: string | null; audited_amount: number | null }>({
  conclusion: null,
  audited_amount: null,
})

// 同步 props 到 currentData
watch(
  () => [props.currentConclusion, props.currentAuditedAmount],
  () => {
    currentData.value = {
      conclusion: props.currentConclusion ?? null,
      audited_amount: props.currentAuditedAmount ?? null,
    }
  },
  { immediate: true },
)

/** 打开抽屉并加载上年数据 */
async function open() {
  visible.value = true
  loading.value = true
  error.value = null
  priorYearData.value = null

  try {
    const data = await api.get<PriorYearData>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/prior-year`,
      { validateStatus: (s: number) => s < 600 },
    )

    // 检查是否返回了错误（404 等）
    if (!data || (data as any)?.detail || (data as any)?.status === 404) {
      error.value = '未找到上年对应底稿（该底稿可能为首次审计）'
      return
    }

    priorYearData.value = data

    // 记录审计日志事件
    logPriorYearViewed()
  } catch (err: any) {
    error.value = '加载上年底稿失败: ' + (err?.message || '未知错误')
  } finally {
    loading.value = false
  }
}

/** 记录 audit_logger_enhanced 事件 workpaper_prior_year_viewed */
async function logPriorYearViewed() {
  try {
    await api.post('/api/audit-log/event', {
      event_type: 'workpaper_prior_year_viewed',
      payload: {
        project_id: props.projectId,
        wp_id: props.wpId,
        prior_year_wp_id: priorYearData.value?.wp_id || null,
      },
    }, { validateStatus: (s: number) => s < 600 })
  } catch {
    // 审计日志记录失败不阻断用户操作
  }
}

/** 复制上年结论到今年 */
async function onCopyConclusion() {
  if (!priorYearData.value?.conclusion) return

  try {
    await ElMessageBox.confirm(
      `确定将上年结论复制到当前底稿？\n\n上年结论：\n"${priorYearData.value.conclusion.slice(0, 200)}${priorYearData.value.conclusion.length > 200 ? '...' : ''}"`,
      '复制上年结论',
      {
        confirmButtonText: '确定复制',
        cancelButtonText: '取消',
        type: 'info',
      },
    )
  } catch {
    // 用户取消
    return
  }

  copying.value = true
  try {
    emit('copy-conclusion', priorYearData.value.conclusion)
    ElMessage.success('已复制上年结论到当前底稿')
  } finally {
    copying.value = false
  }
}

function handleClose(done: () => void) {
  emit('close')
  done()
}

function formatAmount(amount: number | null | undefined): string {
  if (amount == null) return '—'
  return amount.toLocaleString('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
  })
}

// 暴露 open 方法供父组件调用
defineExpose({ open })
</script>

<style scoped>
.prior-year-compare-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.drawer-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  gap: 12px;
  color: #999;
}

.drawer-error {
  padding: 40px 20px;
}

.compare-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 16px;
}

.compare-columns {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.compare-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.column-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--el-fill-color-lighter);
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 14px;
  font-weight: 500;
}

.column-title {
  color: var(--el-text-color-primary);
}

.column-body {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}

.readonly-data-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.data-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.data-row label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: 500;
}

.data-value {
  font-size: 14px;
  color: var(--el-text-color-primary);
  line-height: 1.6;
}

.conclusion-text {
  background: var(--el-fill-color-lighter);
  padding: 10px 12px;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
}

.compare-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  border-top: 1px solid var(--el-border-color-lighter);
}

.action-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
