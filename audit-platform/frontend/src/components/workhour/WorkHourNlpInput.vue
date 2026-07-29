<template>
  <el-dialog v-model="visible" title="自然语言输入工时" width="560px" :close-on-click-modal="false">
    <el-input
      v-model="inputText"
      type="textarea"
      :autosize="{ minRows: 3, maxRows: 6 }"
      placeholder="例如：今天上午去客户现场访谈3小时，下午团队内部讨论2小时，晚上做了1小时底稿"
    />
    <div style="margin-top:12px;text-align:right">
      <el-button type="primary" :loading="parsing" :disabled="!inputText.trim()" @click="handleParse">
        🤖 解析
      </el-button>
    </div>

    <!-- 解析结果预览 -->
    <div v-if="parsedItems.length" style="margin-top:16px">
      <el-divider>解析结果（可修改后确认）</el-divider>
      <div v-for="(item, idx) in parsedItems" :key="idx" class="nlp-item-card">
        <el-row :gutter="8">
          <el-col :span="8">
            <el-input v-model="item.project_name" size="small" placeholder="项目" />
            <el-tag v-if="!item.project_id" size="small" type="warning" style="margin-top:4px">待关联</el-tag>
          </el-col>
          <el-col :span="6">
            <el-select v-model="item.activity_type" size="small" style="width:100%">
              <el-option v-for="t in TYPES" :key="t" :label="t" :value="t" />
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-input-number v-model="item.hours" :min="0.25" :max="24" :step="0.25" size="small" style="width:100%" />
          </el-col>
          <el-col :span="6">
            <el-input v-model="item.description" size="small" placeholder="描述" />
          </el-col>
        </el-row>
      </div>
      <div style="margin-top:12px;text-align:right">
        <el-button @click="parsedItems = []">清除</el-button>
        <el-button type="primary" :loading="confirming" @click="handleConfirm">确认创建</el-button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const TYPES = ['底稿编制', '复核', '抽凭', 'AI操作', '现场访谈', '内部会议', '差旅', '培训', '客户沟通', '其他']

const props = defineProps<{
  projects?: Array<{ project_id: string; project_name: string }>
}>()

const emit = defineEmits<{ saved: [] }>()

const visible = defineModel<boolean>('modelValue', { default: false })
const inputText = ref('')
const parsing = ref(false)
const confirming = ref(false)
const parsedItems = ref<any[]>([])

async function handleParse() {
  if (!inputText.value.trim()) return
  parsing.value = true
  parsedItems.value = []
  try {
    const { api } = await import('@/services/apiProxy')
    const res = await api.post('/api/workhours/parse-natural-language', {
      text: inputText.value,
      projects: props.projects || [],
    }) as any
    parsedItems.value = res?.items || []
    if (!parsedItems.value.length) {
      ElMessage.info('未能解析出工时条目，请换个描述方式')
    }
  } catch {
    ElMessage.warning('解析失败，请手动填写')
  } finally {
    parsing.value = false
  }
}

async function handleConfirm() {
  if (!parsedItems.value.length) return
  confirming.value = true
  try {
    const { api } = await import('@/services/apiProxy')
    const today = new Date().toISOString().slice(0, 10)
    const items = parsedItems.value.map(item => ({
      date: today,
      hours: item.hours,
      cycle: 'A',
      description: item.description || item.project_name,
      activity_type: item.activity_type,
      project_id: item.project_id || undefined,
    }))
    await api.post('/api/workhours/batch', { items })
    ElMessage.success(`已创建 ${items.length} 条工时`)
    parsedItems.value = []
    visible.value = false
    emit('saved')
  } catch (e: any) {
    ElMessage.error('创建失败')
  } finally {
    confirming.value = false
  }
}
</script>

<style scoped>
.nlp-item-card {
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
