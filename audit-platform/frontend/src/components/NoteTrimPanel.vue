<template>
  <el-dialog append-to-body v-model="visible" title="附注章节裁剪" width="700px">
    <el-table :data="sections" border size="small" v-loading="loading" max-height="500">
      <el-table-column prop="section_number" label="编号" width="80" />
      <el-table-column prop="section_title" label="章节标题" min-width="200" />
      <el-table-column label="状态" width="200">
        <template #default="{ row }">
          <el-radio-group v-model="row.status" size="small">
            <el-radio-button value="retain">保留</el-radio-button>
            <el-radio-button value="skip">跳过</el-radio-button>
            <el-radio-button value="not_applicable">不适用</el-radio-button>
          </el-radio-group>
        </template>
      </el-table-column>
      <el-table-column label="理由" min-width="150">
        <template #default="{ row }">
          <el-input v-if="row.status !== 'retain'" v-model="row.skip_reason" size="small" placeholder="填写理由" />
        </template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="saveTrim" :loading="saving">保存裁剪</el-button>
    </template>
  </el-dialog>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
const props = defineProps<{ modelValue: boolean; projectId: string; templateType?: string }>()
const emit = defineEmits(['update:modelValue', 'saved'])
const visible = ref(props.modelValue)
watch(() => props.modelValue, v => { visible.value = v; if (v) loadSections() })
watch(visible, v => emit('update:modelValue', v))
watch(() => props.templateType, () => { if (visible.value) loadSections() })
const sections = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const requestParams = computed(() => props.templateType ? { template_type: props.templateType } : {})
async function loadSections() {
  loading.value = true
  try {
    const data = await api.get(`/api/disclosure-notes/${props.projectId}/sections`, { params: requestParams.value })
    sections.value = data
    if (!Array.isArray(sections.value)) sections.value = []
  } finally { loading.value = false }
}
async function saveTrim() {
  saving.value = true
  try {
    await api.put(`/api/disclosure-notes/${props.projectId}/sections/trim`, {
      items: sections.value.map(s => ({ id: s.id, status: s.status, skip_reason: s.skip_reason })),
    }, { params: requestParams.value })
    ElMessage.success('裁剪已保存')
    visible.value = false
    emit('saved')
  } finally { saving.value = false }
}
</script>
