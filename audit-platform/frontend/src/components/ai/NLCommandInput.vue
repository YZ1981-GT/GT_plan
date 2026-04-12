<template>
  <div class="nl-command-input">
    <div class="input-wrapper">
      <span class="nl-icon">💬</span>
      <input
        v-model="query"
        class="nl-input"
        placeholder="用自然语言下达指令，如：「帮我生成本月销售收入的截止测试底稿」"
        @keydown.enter="execute"
        @focus="showHelp = true"
        @blur="showHelp = false"
      />
      <button class="btn-execute" @click="execute" :disabled="executing">
        {{ executing ? '...' : '▶' }}
      </button>
    </div>
    <div v-if="showHelp" class="help-panel">
      <div class="help-title">示例指令：</div>
      <div class="help-items">
        <span v-for="(example, i) in examples" :key="i" class="help-item" @click="fillExample(example)">
          {{ example }}
        </span>
      </div>
    </div>
    <div v-if="lastResult" class="result-panel">
      <div class="result-status">
        <span :class="['status-badge', lastResult.status]">{{ lastResult.message }}</span>
      </div>
      <div v-if="lastResult.action" class="result-action">
        <strong>{{ lastResult.action.label }}</strong>
        <span v-if="lastResult.action.description">{{ lastResult.action.description }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { nlCommandApi } from '@/api'

const props = defineProps({ projectId: { type: String, required: true } })
const emit = defineEmits(['action-confirmed', 'action-cancelled'])

const query = ref('')
const executing = ref(false)
const showHelp = ref(false)
const lastResult = ref(null)

const examples = [
  '生成本月销售收入的截止测试底稿',
  '分析前十大供应商的变动情况',
  '检查本期是否有重大非常规交易',
  '生成应收账款账龄分析表',
  '导出本期所有调整分录',
]

async function execute() {
  if (!query.value.trim() || executing.value) return
  executing.value = true
  try {
    const res = await nlCommandApi.execute(props.projectId, query.value)
    lastResult.value = res.data || {}
    if (lastResult.value.action) {
      emit('action-confirmed', lastResult.value.action)
    }
  } catch (e) {
    console.error(e)
    lastResult.value = { status: 'error', message: '指令执行失败' }
  } finally {
    executing.value = false
  }
}

function fillExample(text) {
  query.value = text
  showHelp.value = false
}
</script>

<style scoped>
.nl-command-input { width: 100%; }
.input-wrapper { display: flex; align-items: center; gap: 8px; background: #fff; border: 1.5px solid #ddd; border-radius: 24px; padding: 8px 12px; transition: border-color 0.2s; }
.input-wrapper:focus-within { border-color: #4b2d77; }
.nl-icon { font-size: 18px; }
.nl-input { flex: 1; border: none; outline: none; font-size: 13px; background: transparent; }
.btn-execute { background: #4b2d77; color: #fff; border: none; border-radius: 50%; width: 28px; height: 28px; cursor: pointer; font-size: 12px; display: flex; align-items: center; justify-content: center; }
.btn-execute:disabled { background: #ccc; cursor: not-allowed; }

.help-panel { background: #fff; border: 1px solid #eee; border-radius: 8px; padding: 12px; margin-top: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
.help-title { font-size: 12px; color: #999; margin-bottom: 8px; }
.help-items { display: flex; flex-wrap: wrap; gap: 6px; }
.help-item { background: #f5f5f5; padding: 4px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; color: #4b2d77; }
.help-item:hover { background: rgba(75,45,119,0.1); }

.result-panel { margin-top: 8px; padding: 10px 12px; background: #f9f9f9; border-radius: 8px; font-size: 13px; }
.result-action { margin-top: 6px; display: flex; flex-direction: column; gap: 2px; }
.status-badge { padding: 2px 8px; border-radius: 4px; font-size: 12px; }
.status-badge.success { background: #f6ffed; color: #52c41a; }
.status-badge.action_required { background: #fff7e6; color: #fa8c16; }
.status-badge.error { background: #fff2f0; color: #ff4d4f; }
</style>
