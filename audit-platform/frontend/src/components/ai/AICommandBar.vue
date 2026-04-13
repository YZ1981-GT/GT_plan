<template>
  <div class="gt-ai-command-bar">
    <!-- 命令输入区 -->
    <div class="command-input-area">
      <div class="input-wrapper">
        <span class="input-icon">⚡</span>
        <input
          v-model="query"
          class="command-input"
          :placeholder="placeholder"
          @keydown.enter="submitQuery"
          @keydown.up="navigateHistory(-1)"
          @keydown.down="navigateHistory(1)"
          @focus="showExamples = true"
          @blur="onBlur"
        />
        <button
          class="btn-submit"
          @click="submitQuery"
          :disabled="loading || !query.trim()"
          title="发送"
        >
          <span v-if="loading" class="loading-dots">...</span>
          <span v-else>▶</span>
        </button>
      </div>

      <!-- 示例指令 -->
      <div v-if="showExamples" class="examples-panel">
        <div class="examples-header">
          <span class="examples-title">💡 示例指令：</span>
          <button class="btn-close-examples" @click="showExamples = false">×</button>
        </div>
        <div class="examples-grid">
          <button
            v-for="(ex, idx) in examples"
            :key="idx"
            class="example-item"
            @click="fillExample(ex.text)"
          >
            {{ ex.text }}
          </button>
        </div>
      </div>
    </div>

    <!-- 命令确认卡片覆盖层 -->
    <div v-if="pendingCommand" class="command-overlay">
      <div class="command-confirm-wrapper">
        <div class="confirm-header">
          <span class="confirm-icon">⚡</span>
          <span class="confirm-title">{{ confirmTitle }}</span>
          <button class="btn-close-confirm" @click="cancelCommand">×</button>
        </div>
        <div class="confirm-body">
          <div class="action-preview">
            <span class="action-label">操作类型：</span>
            <span class="action-value">{{ actionLabel(pendingCommand.action) }}</span>
          </div>
          <div class="params-preview">
            <div class="param-row" v-for="(val, key) in pendingCommand.params" :key="key">
              <span class="param-key">{{ formatParamKey(key) }}：</span>
              <span class="param-value">{{ formatParamValue(val) }}</span>
            </div>
          </div>
        </div>
        <div class="confirm-actions">
          <button class="btn-confirm-execute" @click="executeCommand">
            ✅ 确认执行
          </button>
          <button class="btn-cancel-execute" @click="cancelCommand">
            取消
          </button>
        </div>
      </div>
    </div>

    <!-- 执行结果提示 -->
    <transition name="fade">
      <div v-if="resultMessage" :class="['result-toast', resultType]">
        <span class="result-icon">{{ resultType === 'success' ? '✅' : '❌' }}</span>
        <span class="result-text">{{ resultMessage }}</span>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { nlCommand } from '@/services/aiApi'

const props = defineProps({
  projectId: { type: String, required: true },
  placeholder: {
    type: String,
    default: '用自然语言下达指令，如：「帮我生成本月销售收入的截止测试底稿」',
  },
})

const emit = defineEmits(['executed', 'cancelled'])

// ─── Input ───
const query = ref('')
const loading = ref(false)
const showExamples = ref(false)

// ─── Command history ───
const commandHistory = ref([])
const historyIndex = ref(-1)

// ─── Confirmation ───
const pendingCommand = ref(null)
const confirmTitle = ref('系统操作确认')

// ─── Result ───
const resultMessage = ref('')
const resultType = ref('success')
let resultTimer = null

// ─── Examples ───
const examples = [
  { text: '生成本月销售收入的截止测试底稿' },
  { text: '分析前十大供应商的变动情况' },
  { text: '检查本期是否有重大非常规交易' },
  { text: '生成应收账款账龄分析表' },
  { text: '导出本期所有调整分录' },
  { text: '切换到项目：XX公司2024审计' },
  { text: '生成分类报告' },
  { text: '检查银行函证的地址一致性' },
]

// ─── Submit ───
async function submitQuery() {
  if (!query.value.trim() || loading.value) return

  const input = query.value.trim()
  loading.value = true

  try {
    // 解析意图
    const parsed = await nlCommand.parseIntent(input)
    const intent = parsed.data || parsed

    // 检查是否需要确认
    if (intent.action === 'system_operation' || intent.confidence >= 0.7) {
      // 需要用户确认的操作
      pendingCommand.value = {
        id: `cmd-${Date.now()}`,
        action: intent.action || intent.intent_type,
        type: intent.intent_type,
        params: intent.params || {},
        label: intent.label || getDefaultLabel(intent.intent_type),
        description: intent.description || '',
      }
      confirmTitle.value = intent.intent_type === 'switch_project'
        ? '切换项目确认'
        : intent.intent_type === 'generate_report'
          ? '生成分类报告确认'
          : '系统操作确认'
    } else {
      // 直接执行
      await executeDirect(intent)
    }

    // 保存到历史
    if (input && !commandHistory.value.includes(input)) {
      commandHistory.value.unshift(input)
      if (commandHistory.value.length > 20) commandHistory.value.pop()
    }
    historyIndex.value = -1
    query.value = ''
  } catch (e) {
    console.error('Command parse error:', e)
    showResult('解析失败，请重试', 'error')
  } finally {
    loading.value = false
  }
}

async function executeDirect(intent) {
  try {
    const result = await nlCommand.executeCommand(intent, props.projectId)
    showResult(`✅ ${result.message || '操作执行成功'}`, 'success')
    emit('executed', result)
  } catch (e) {
    console.error('Execute error:', e)
    showResult('执行失败，请稍后重试', 'error')
    emit('cancelled')
  }
}

// ─── Confirm & Execute ───
async function executeCommand() {
  if (!pendingCommand.value) return

  const cmd = pendingCommand.value
  pendingCommand.value = null

  try {
    const result = await nlCommand.executeCommand(
      {
        action: cmd.action,
        params: cmd.params,
        intent_type: cmd.type,
      },
      props.projectId
    )
    showResult(`✅ ${cmd.label} 执行成功`, 'success')
    emit('executed', result)
  } catch (e) {
    console.error('Execute confirmed command error:', e)
    showResult('执行失败，请稍后重试', 'error')
    emit('cancelled')
  }
}

function cancelCommand() {
  const cmd = pendingCommand.value
  pendingCommand.value = null
  showResult(`❌ 已取消：${cmd?.label || '操作'}`, 'error')
  emit('cancelled', cmd)
}

// ─── Helpers ───
function getDefaultLabel(intentType) {
  const labels = {
    switch_project: '切换到项目',
    generate_report: '生成分类报告',
    query_data: '查询数据',
    analyze_file: '分析文件',
    generate_workpaper: '生成底稿',
    navigation: '页面导航',
  }
  return labels[intentType] || '系统操作'
}

function actionLabel(action) {
  const labels = {
    switch_project: '切换项目',
    switch_year: '切换年度',
    generate_report: '生成分类报告',
    generate_workpaper: '生成底稿',
    query_data: '数据查询',
    analyze_file: '文件分析',
    navigation: '页面导航',
    chat: 'AI对话',
  }
  return labels[action] || action
}

function formatParamKey(key) {
  // 驼峰转中文
  const map = {
    projectName: '项目名称',
    projectId: '项目ID',
    accountCode: '科目代码',
    reportType: '报告类型',
    workpaperId: '底稿ID',
    workpaperName: '底稿名称',
    filePath: '文件路径',
    year: '年度',
    month: '月份',
  }
  return map[key] || key
}

function formatParamValue(val) {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function fillExample(text) {
  query.value = text
  showExamples.value = false
}

function navigateHistory(dir) {
  if (commandHistory.value.length === 0) return
  historyIndex.value += dir
  if (historyIndex.value < 0) historyIndex.value = 0
  if (historyIndex.value >= commandHistory.value.length) {
    historyIndex.value = commandHistory.value.length - 1
  }
  query.value = commandHistory.value[historyIndex.value] || ''
}

function onBlur() {
  // 延迟关闭以便点击示例
  setTimeout(() => { showExamples.value = false }, 200)
}

function showResult(message, type) {
  if (resultTimer) clearTimeout(resultTimer)
  resultMessage.value = message
  resultType.value = type
  resultTimer = setTimeout(() => {
    resultMessage.value = ''
  }, 4000)
}
</script>

<style scoped>
.gt-ai-command-bar {
  position: relative;
  width: 100%;
}

/* Input area */
.command-input-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fff;
  border: 1.5px solid #ddd;
  border-radius: 24px;
  padding: 8px 12px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.input-wrapper:focus-within {
  border-color: #4b2d77;
  box-shadow: 0 0 0 2px rgba(75, 45, 119, 0.1);
}

.input-icon { font-size: 18px; flex-shrink: 0; }

.command-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 13px;
  background: transparent;
  color: #333;
}
.command-input::placeholder { color: #bbb; }

.btn-submit {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #4b2d77;
  color: #fff;
  border: none;
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.2s;
}
.btn-submit:disabled { background: #ccc; cursor: not-allowed; }
.btn-submit:hover:not(:disabled) { background: #3d2066; }

.loading-dots { animation: pulse 1s infinite; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Examples panel */
.examples-panel {
  background: #fff;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 10px 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.examples-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.examples-title {
  font-size: 12px;
  color: #999;
}

.btn-close-examples {
  background: none;
  border: none;
  cursor: pointer;
  color: #999;
  font-size: 16px;
  padding: 0 4px;
}

.examples-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.example-item {
  background: #f5f5f5;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  color: #4b2d77;
  border: 1px solid transparent;
  transition: all 0.2s;
}
.example-item:hover {
  background: rgba(75, 45, 119, 0.1);
  border-color: rgba(75, 45, 119, 0.2);
}

/* Command confirm overlay */
.command-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.command-confirm-wrapper {
  background: #fff;
  border-radius: 10px;
  width: 440px;
  max-width: 90vw;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}

.confirm-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #fffbe6;
  border-bottom: 1px solid #ffe58f;
}

.confirm-icon { font-size: 18px; }

.confirm-title {
  flex: 1;
  font-weight: 600;
  font-size: 14px;
  color: #d48806;
}

.btn-close-confirm {
  background: none;
  border: none;
  cursor: pointer;
  color: #999;
  font-size: 20px;
  padding: 0 4px;
}

.confirm-body {
  padding: 16px;
}

.action-preview {
  margin-bottom: 12px;
  display: flex;
  gap: 8px;
  align-items: center;
}

.action-label { color: #888; font-size: 13px; }
.action-value {
  font-weight: 600;
  font-size: 14px;
  color: #4b2d77;
  background: rgba(75, 45, 119, 0.08);
  padding: 2px 10px;
  border-radius: 4px;
}

.params-preview {
  background: #fafafa;
  border-radius: 6px;
  padding: 10px 12px;
  border: 1px solid #eee;
}

.param-row {
  display: flex;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}
.param-row:not(:last-child) { border-bottom: 1px solid #f0f0f0; }

.param-key { color: #888; min-width: 80px; }
.param-value { color: #333; font-weight: 500; }

.confirm-actions {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  background: #f9f9f9;
  border-top: 1px solid #eee;
  justify-content: flex-end;
}

.btn-confirm-execute, .btn-cancel-execute {
  padding: 6px 18px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  border: none;
}
.btn-confirm-execute {
  background: #52c41a;
  color: #fff;
}
.btn-confirm-execute:hover { background: #389e0d; }
.btn-cancel-execute {
  background: #f0f0f0;
  color: #666;
}
.btn-cancel-execute:hover { background: #e0e0e0; }

/* Result toast */
.result-toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  z-index: 300;
}
.result-toast.success { background: #f6ffed; color: #52c41a; border: 1px solid #b7eb8f; }
.result-toast.error { background: #fff2f0; color: #ff4d4f; border: 1px solid #ffccc7; }

.result-icon { font-size: 16px; }

/* Transition */
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s, transform 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateX(-50%) translateY(10px); }
</style>
