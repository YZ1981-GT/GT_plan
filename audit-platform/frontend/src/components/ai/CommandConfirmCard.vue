<template>
  <div class="gt-command-confirm-card">
    <div class="card-header">
      <span class="card-icon">⚡</span>
      <span class="card-title">{{ displayTitle }}</span>
    </div>
    <div class="card-body">
      <div v-if="command.description" class="command-description">{{ command.description }}</div>
      <div v-if="readableParams.length > 0" class="command-params">
        <div v-for="(item, idx) in readableParams" :key="idx" class="param-item">
          <span class="param-key">{{ item.label }}：</span>
          <span class="param-value">{{ item.value }}</span>
        </div>
      </div>
    </div>
    <div class="card-actions">
      <button
        class="btn-confirm"
        @click="handleConfirm"
        :disabled="confirming"
      >
        {{ confirming ? '执行中...' : '✅ 确认执行' }}
      </button>
      <button class="btn-cancel" @click="$emit('cancel', command)">❌ 取消</button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  command: { type: Object, required: true },
})
const emit = defineEmits(['confirm', 'cancel'])

const confirming = ref(false)

const displayTitle = computed(() => {
  const type = props.command.action || props.command.type || props.command.intent_type || ''
  const labels = {
    switch_project: '切换项目',
    switch_year: '切换年度',
    generate_report: '生成分类报告',
    generate_workpaper: '生成本稿',
    query_data: '数据查询',
    analyze_file: '分析文件',
    navigation: '页面导航',
    system_operation: '系统操作',
    chat: 'AI对话',
  }
  const base = labels[type] || props.command.label || '系统操作'

  // 附加参数显示
  const params = props.command.params || {}
  if (params.projectName) return `切换到项目：${params.projectName}`
  if (params.reportType) return `生成分类报告：${params.reportType}`
  if (params.workpaperName) return `生成底稿：${params.workpaperName}`
  if (params.accountCode) return `分析科目：${params.accountCode}`

  return base
})

const readableParams = computed(() => {
  const params = props.command.params || {}
  const labelMap = {
    projectName: '项目名称',
    projectId: '项目ID',
    projectId: '项目ID',
    accountCode: '科目代码',
    accountName: '科目名称',
    reportType: '报告类型',
    workpaperId: '底稿ID',
    workpaperName: '底稿名称',
    workpaperType: '底稿类型',
    filePath: '文件路径',
    fileName: '文件名',
    year: '年度',
    month: '月份',
    quarter: '季度',
    startDate: '开始日期',
    endDate: '结束日期',
  }

  return Object.entries(params)
    .filter(([, val]) => val !== null && val !== undefined && val !== '')
    .map(([key, value]) => ({
      label: labelMap[key] || key,
      value: typeof value === 'object' ? JSON.stringify(value) : String(value),
    }))
})

async function handleConfirm() {
  confirming.value = true
  try {
    emit('confirm', props.command)
  } finally {
    // 父组件负责 auto-dismiss，0.5s 后自动解锁按钮
    setTimeout(() => {
      confirming.value = false
    }, 500)
  }
}
</script>

<style scoped>
.gt-command-confirm-card {
  border: 1.5px solid #faad14;
  border-radius: 8px;
  background: #fffbe6;
  padding: 10px;
  margin-top: 8px;
  max-width: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.card-icon { font-size: 16px; }

.card-title {
  font-weight: 600;
  font-size: 13px;
  color: #d48806;
}

.card-body { font-size: 12px; }

.command-description {
  color: #555;
  margin-bottom: 6px;
  line-height: 1.5;
}

.command-params {
  background: rgba(0,0,0,0.04);
  border-radius: 4px;
  padding: 6px 8px;
}

.param-item { margin: 2px 0; display: flex; gap: 4px; }
.param-key { color: #888; }
.param-value { color: #333; font-weight: 500; word-break: break-all; }

.card-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  justify-content: flex-end;
}

.btn-confirm, .btn-cancel {
  padding: 4px 14px;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.2s;
}

.btn-confirm {
  background: #52c41a;
  color: #fff;
}

.btn-confirm:hover:not(:disabled) { background: #389e0d; }
.btn-confirm:disabled { background: #a3d99f; cursor: not-allowed; }

.btn-cancel {
  background: #f5f5f5;
  color: #666;
}

.btn-cancel:hover { background: #e8e8e8; }
</style>
