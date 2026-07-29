<template>
  <el-dialog v-model="visible" title="添加平台外工作" width="480px" :close-on-click-modal="false">
    <el-form :model="form" label-width="80px" size="default">
      <el-form-item label="活动类型" required>
        <el-select v-model="form.activityType" placeholder="选择活动类型" style="width:100%">
          <el-option v-for="t in ACTIVITY_TYPES" :key="t.value" :label="t.label" :value="t.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="时长(h)" required>
        <el-input-number v-model="form.hours" :min="0.25" :max="24" :step="0.25" :precision="2" style="width:100%" />
      </el-form-item>
      <el-form-item label="所属项目">
        <el-select v-model="form.projectId" placeholder="可选（非项目级工作可不选）" filterable clearable style="width:100%">
          <el-option v-for="p in projects" :key="p.project_id" :label="p.project_name" :value="p.project_id" />
        </el-select>
      </el-form-item>
      <el-form-item label="日期">
        <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="工作内容简述" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!canSave" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'

const ACTIVITY_TYPES = [
  { value: '现场访谈', label: '现场访谈' },
  { value: '内部会议', label: '内部会议' },
  { value: '差旅', label: '差旅' },
  { value: '培训', label: '培训' },
  { value: '客户沟通', label: '客户沟通' },
  { value: '其他', label: '其他' },
]

const props = defineProps<{
  projects?: Array<{ project_id: string; project_name: string }>
}>()

const emit = defineEmits<{
  saved: []
}>()

const visible = defineModel<boolean>('modelValue', { default: false })
const saving = ref(false)

const form = ref({
  activityType: '',
  hours: 1,
  projectId: '',
  date: new Date().toISOString().slice(0, 10),
  description: '',
})

const canSave = computed(() => !!form.value.activityType && form.value.hours > 0)

const projects = computed(() => props.projects || [])

watch(visible, (v) => {
  if (v) {
    form.value = {
      activityType: '',
      hours: 1,
      projectId: '',
      date: new Date().toISOString().slice(0, 10),
      description: '',
    }
  }
})

async function handleSave() {
  if (!canSave.value) return
  saving.value = true
  try {
    const { api } = await import('@/services/apiProxy')
    const body: any = {
      date: form.value.date,
      hours: form.value.hours,
      cycle: 'A',
      description: form.value.description || form.value.activityType,
      activity_type: form.value.activityType,
    }
    if (form.value.projectId) {
      body.project_id = form.value.projectId
    }
    await api.post('/api/workhours/batch', { items: [body] })
    ElMessage.success('已保存平台外工作')
    visible.value = false
    emit('saved')
  } catch (e: any) {
    ElMessage.error('保存失败: ' + (e?.message || '未知错误'))
  } finally {
    saving.value = false
  }
}
</script>
