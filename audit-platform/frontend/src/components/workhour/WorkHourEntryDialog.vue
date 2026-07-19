<template>
  <el-dialog
    :model-value="modelValue"
    :title="isEdit ? '编辑工时条目' : '新增工时条目'"
    width="560px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
    @open="onOpen"
  >
    <!-- 非 draft 状态 tag -->
    <div v-if="isEdit && entryStatus && entryStatus !== 'draft'" class="status-tag-bar">
      <el-tag :color="statusColor" effect="dark" size="small">
        {{ statusLabel }}
      </el-tag>
    </div>

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="80px"
      :disabled="isReadonly"
    >
      <el-form-item label="日期" prop="date">
        <el-date-picker
          v-model="form.date"
          type="date"
          placeholder="选择日期"
          value-format="YYYY-MM-DD"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="循环" prop="cycle">
        <el-select v-model="form.cycle" placeholder="选择循环" style="width: 100%">
          <el-option
            v-for="c in cycleOptions"
            :key="c"
            :label="c"
            :value="c"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="底稿编码" prop="wp_code">
        <el-input v-model="form.wp_code" placeholder="如 D2-1、F3A" />
      </el-form-item>

      <el-form-item label="程序" prop="procedure">
        <el-input v-model="form.procedure" placeholder="审计程序描述" />
      </el-form-item>

      <el-form-item label="小时" prop="hours">
        <el-input-number
          v-model="form.hours"
          :min="0.5"
          :max="24"
          :step="0.5"
          :precision="1"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="描述" prop="description">
        <el-input
          v-model="form.description"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          placeholder="工作内容描述（选填）"
        />
      </el-form-item>
    </el-form>

    <!-- 剩余可用小时提示 -->
    <div v-if="remainingHours !== null" class="remaining-hint">
      <el-icon><InfoFilled /></el-icon>
      <span>当日已填 {{ usedHours.toFixed(1) }}h，剩余可用 {{ remainingHours.toFixed(1) }}h</span>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button
        v-if="!isReadonly"
        type="primary"
        :loading="submitting"
        @click="handleSubmit"
      >
        {{ isEdit ? '更新' : '创建' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import {
  createEntry,
  updateEntry,
  getEntrySummary,
  listEntries,
} from '@/services/staffApi'
import type { WorkHourEntryRecord } from '@/services/staffApi'

const props = defineProps<{
  projectId: string
  entryId?: string
  date?: string
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: []
}>()

// ─── 常量 ───
const cycleOptions = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','S','OTHER']

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft:     { label: '草稿', color: '#909399' },
  submitted: { label: '已提交', color: '#409EFF' },
  approved:  { label: '已通过', color: '#67C23A' },
  rejected:  { label: '已退回', color: '#F56C6C' },
}

// ─── 状态 ───
const formRef = ref<FormInstance>()
const submitting = ref(false)
const entryStatus = ref<string>('')
const usedHours = ref(0)
const remainingHours = ref<number | null>(null)
const cycleManuallySet = ref(false)

const form = reactive({
  date: '',
  cycle: '',
  wp_code: '',
  procedure: '',
  hours: 1,
  description: '',
})

// ─── 计算属性 ───
const isEdit = computed(() => !!props.entryId)
const isReadonly = computed(() => isEdit.value && entryStatus.value !== 'draft')
const statusColor = computed(() => STATUS_MAP[entryStatus.value]?.color || '#909399')
const statusLabel = computed(() => STATUS_MAP[entryStatus.value]?.label || entryStatus.value)

// ─── 表单校验规则 ───
const rules: FormRules = {
  date: [{ required: true, message: '请选择日期', trigger: 'change' }],
  cycle: [{ required: true, message: '请选择循环', trigger: 'change' }],
  hours: [{ required: true, message: '请输入小时数', trigger: 'blur' }],
}

// ─── wp_code watch → 自动推断 cycle（首字母 A~S） ───
watch(() => form.wp_code, (val) => {
  if (cycleManuallySet.value) return
  if (!val) return
  const first = val.charAt(0).toUpperCase()
  if (first >= 'A' && first <= 'S') {
    form.cycle = first
  }
})

// 检测用户手动选择 cycle（之后 wp_code 变化不再自动推断）
watch(() => form.cycle, (_, oldVal) => {
  // 首次加载不算手动
  if (oldVal === '') return
  cycleManuallySet.value = true
})

// ─── 弹窗打开 ───
async function onOpen() {
  resetForm()
  cycleManuallySet.value = false

  if (props.date) {
    form.date = props.date
  }

  if (isEdit.value && props.entryId) {
    await loadEntry()
  }

  // 延迟加载 summary
  if (form.date) {
    await loadSummary(form.date)
  }
}

function resetForm() {
  form.date = ''
  form.cycle = ''
  form.wp_code = ''
  form.procedure = ''
  form.hours = 1
  form.description = ''
  entryStatus.value = ''
  usedHours.value = 0
  remainingHours.value = null
  formRef.value?.clearValidate()
}

// ─── 编辑模式：GET 回填 ───
async function loadEntry() {
  try {
    const entries = await listEntries(props.projectId, {})
    const entry = entries.find((e: WorkHourEntryRecord) => e.id === props.entryId)
    if (entry) {
      form.date = entry.date
      form.cycle = entry.cycle || ''
      form.wp_code = entry.wp_code || ''
      form.procedure = entry.procedure || ''
      form.hours = entry.hours
      form.description = entry.description || ''
      entryStatus.value = entry.status
    }
  } catch (e) {
    console.error('加载工时条目失败', e)
  }
}

// ─── summary 校验 24h ───
async function loadSummary(date: string) {
  try {
    const summary = await getEntrySummary(props.projectId)
    const dayTotal = summary.by_day?.[date] || 0
    // 编辑模式：减去当前条目本身的小时数
    const selfHours = isEdit.value ? form.hours : 0
    usedHours.value = dayTotal - selfHours
    remainingHours.value = 24 - usedHours.value
  } catch {
    remainingHours.value = null
  }
}

// date 变化时刷新 summary
watch(() => form.date, (val) => {
  if (val) loadSummary(val)
})

// ─── 提交 ───
async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  // 前端校验 24h
  const effectiveRemaining = remainingHours.value ?? 24
  if (form.hours > effectiveRemaining) {
    ElMessage.warning(`当日剩余可用 ${effectiveRemaining.toFixed(1)}h，当前填报 ${form.hours}h，超出限制`)
    return
  }

  submitting.value = true
  try {
    const payload = {
      date: form.date,
      hours: form.hours,
      cycle: form.cycle || undefined,
      wp_code: form.wp_code || undefined,
      procedure: form.procedure || undefined,
      description: form.description || undefined,
    }

    if (isEdit.value && props.entryId) {
      await updateEntry(props.projectId, props.entryId, payload)
      ElMessage.success('工时条目已更新')
    } else {
      await createEntry(props.projectId, payload)
      ElMessage.success('工时条目已创建')
    }

    emit('saved')
    emit('update:modelValue', false)
  } catch (e: any) {
    const msg = e?.response?.data?.message || e?.message || '操作失败'
    ElMessage.error(msg)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.status-tag-bar {
  margin-bottom: 16px;
  text-align: right;
}

.remaining-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #f0f9ff;
  border-radius: 4px;
  font-size: 13px;
  color: #606266;
}
</style>
