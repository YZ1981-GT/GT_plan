<template>
  <el-dialog
    v-model="visible"
    title="D2-13 业务模式分析"
    width="800px"
    :close-on-press-escape="true"
    :close-on-click-modal="false"
    @close="onClose"
    class="gt-business-pattern-dialog"
  >
    <div class="gt-bp-content">
      <!-- 分析状态提示 -->
      <el-alert
        v-if="!loading && !analyzed"
        type="info"
        :closable="false"
        show-icon
      >
        点击"开始分析"按钮，系统将基于序时账客户付款数据自动分析业务模式。
      </el-alert>

      <!-- 加载中 -->
      <div v-if="loading" class="gt-bp-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在分析客户付款模式...</span>
      </div>

      <!-- 分析结果 -->
      <template v-if="analyzed && !loading">
        <!-- 客户付款模式表格 -->
        <div class="gt-bp-section">
          <h4>客户付款周期分布</h4>
          <el-table
            :data="patterns"
            border
            size="small"
            stripe
            class="gt-bp-table"
          >
            <el-table-column prop="customer" label="客户名称" min-width="180" />
            <el-table-column
              prop="payment_cycle_days"
              label="付款周期(天)"
              width="120"
              align="right"
            >
              <template #default="{ row }">
                <span class="gt-amt">{{ row.payment_cycle_days }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="category" label="分类" width="120" align="center">
              <template #default="{ row }">
                <el-tag
                  :type="getCategoryTagType(row.category)"
                  size="small"
                >
                  {{ row.category }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- LLM 建议 -->
        <div class="gt-bp-section">
          <h4>LLM 分析建议</h4>
          <div class="gt-bp-suggestion">
            <pre class="gt-bp-suggestion-text">{{ llmSuggestion }}</pre>
          </div>
        </div>
      </template>
    </div>

    <template #footer>
      <div class="gt-bp-footer">
        <el-button
          v-if="!analyzed"
          type="primary"
          :loading="loading"
          @click="onAnalyze"
        >
          开始分析
        </el-button>
        <template v-else>
          <el-button @click="onAnalyze" :loading="loading">重新分析</el-button>
          <el-button type="success" @click="onConfirm">确认采纳</el-button>
          <el-button type="warning" @click="onModify">手动修改</el-button>
        </template>
        <el-button @click="onClose">关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * BusinessPatternDialog — D2-13 业务模式分析弹窗
 *
 * 调用 POST /api/projects/{pid}/workpapers/D2/business-pattern-analysis
 * 展示客户付款周期分布 + LLM 分类建议
 * 用户可确认采纳或手动修改
 */
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'

interface CustomerPattern {
  customer: string
  payment_cycle_days: number
  category: string
}

interface Props {
  visible: boolean
  projectId: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:visible': [v: boolean]
  confirmed: [patterns: CustomerPattern[]]
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (v: boolean) => emit('update:visible', v),
})
const visible = dialogVisible

const loading = ref(false)
const analyzed = ref(false)
const patterns = ref<CustomerPattern[]>([])
const llmSuggestion = ref('')

function getCategoryTagType(category: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  switch (category) {
    case '现销型':
      return 'success'
    case '短期信用':
      return ''
    case '中期信用':
      return 'warning'
    case '长期信用':
      return 'danger'
    default:
      return 'info'
  }
}

async function onAnalyze() {
  loading.value = true
  try {
    const res = await api.post(
      `/api/projects/${props.projectId}/workpapers/D2/business-pattern-analysis`,
      {}
    ) as { patterns: CustomerPattern[]; llm_suggestion: string }

    patterns.value = res.patterns || []
    llmSuggestion.value = res.llm_suggestion || '暂无建议'
    analyzed.value = true
  } catch (err: any) {
    ElMessage.error('分析失败：' + (err?.message || '请稍后重试'))
  } finally {
    loading.value = false
  }
}

function onConfirm() {
  emit('confirmed', patterns.value)
  ElMessage.success('业务模式分析结果已确认')
  emit('update:visible', false)
}

function onModify() {
  ElMessage.info('请在 D2-13 工作表中手动修改业务模式分类')
  emit('update:visible', false)
}

function onClose() {
  emit('update:visible', false)
}
</script>

<style scoped>
.gt-business-pattern-dialog :deep(.el-dialog__body) {
  padding: 12px 20px;
  max-height: 60vh;
  overflow-y: auto;
}

.gt-bp-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-bp-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 0;
  color: var(--el-text-color-secondary);
}

.gt-bp-section h4 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.gt-bp-table {
  width: 100%;
}

.gt-bp-suggestion {
  background: var(--el-fill-color-lighter, #f5f7fa);
  border-radius: 4px;
  padding: 12px 16px;
}

.gt-bp-suggestion-text {
  margin: 0;
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  font-family: inherit;
}

.gt-bp-footer {
  text-align: right;
}
</style>
