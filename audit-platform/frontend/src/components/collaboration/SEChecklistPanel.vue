<template>
  <div class="se-checklist-panel">
    <div class="toolbar">
      <el-button v-if="canEdit" type="primary" size="small" @click="openAddDialog">添加清单项</el-button>
    </div>

    <el-table :data="items" v-loading="loading" stripe size="small">
      <el-table-column prop="item_code" label="项目编号" width="120" />
      <el-table-column prop="item_name" label="检查事项" />
      <el-table-column prop="category" label="类别" width="120">
        <template #default="{ row }">
          <el-tag size="small">{{ categoryLabel(row.category) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="check_status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="(statusColor(row.check_status)) || undefined" size="small">{{ statusLabel(row.check_status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="checked_by_username" label="检查人" width="100" />
      <el-table-column prop="checked_at" label="检查时间" width="160" />
      <el-table-column prop="notes" label="备注" show-overflow-tooltip />
      <el-table-column label="操作" width="120" v-if="canEdit">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openEditDialog(row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog append-to-body v-model="dialogVisible" :title="isEditing ? '编辑清单项' : '添加清单项'" width="480px">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
        <el-form-item label="事项编号" prop="item_code">
          <el-input v-model="form.item_code" placeholder="如: SE-01" />
        </el-form-item>
        <el-form-item label="事项名称" prop="item_name">
          <el-input v-model="form.item_name" placeholder="检查事项名称" />
        </el-form-item>
        <el-form-item label="类别" prop="category">
          <el-select v-model="form.category" placeholder="选择类别">
            <el-option label="期后调整" value="adjustment" />
            <el-option label="非调整事项" value="non_adjusting" />
            <el-option label="持续经营" value="going_concern" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.check_status">
            <el-option label="待检查" value="pending" />
            <el-option label="通过" value="pass" />
            <el-option label="未通过" value="fail" />
            <el-option label="不适用" value="na" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, FormInstance, FormRules } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { api } from '@/services/apiProxy'
import { useAuthStore } from '@/stores/auth'
import { projects as P_proj } from '@/services/apiPaths'

const props = defineProps<{ projectId: string }>()
const authStore = useAuthStore()

const items = ref<any[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const isEditing = ref(false)
const formRef = ref<FormInstance>()

const canEdit = computed(() => ['admin', 'partner', 'manager'].includes(
  authStore.user?.role ?? ''
))

const form = ref({
  id: '',
  item_code: '',
  item_name: '',
  category: 'adjustment',
  check_status: 'pending',
  notes: '',
})

const rules: FormRules = {
  item_code: [{ required: true, message: '请输入编号', trigger: 'blur' }],
  item_name: [{ required: true, message: '请输入事项名称', trigger: 'blur' }],
  category: [{ required: true, message: '请选择类别', trigger: 'change' }],
}

const categoryLabel = (c: string) => ({
  adjustment: '期后调整', non_adjusting: '非调整事项', going_concern: '持续经营', other: '其他',
}[c] || c)

const statusLabel = (s: string) => ({
  pending: '待检查', pass: '通过', fail: '未通过', na: '不适用',
}[s] || s)

const statusColor = (s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' => ({
  pending: 'info', pass: 'success', fail: 'danger', na: 'warning',
} as Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'>)[s] || 'info'

const loadItems = async () => {
  if (!props.projectId) return
  loading.value = true
  try {
    const data = await api.get(`${P_proj.detail(props.projectId)}/se-checklist`)
    items.value = Array.isArray(data) ? data : []
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

const openAddDialog = () => {
  isEditing.value = false
  form.value = { id: '', item_code: '', item_name: '', category: 'adjustment', check_status: 'pending', notes: '' }
  dialogVisible.value = true
}

const openEditDialog = (row: any) => {
  isEditing.value = true
  form.value = { ...row }
  dialogVisible.value = true
}

const handleSave = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      if (isEditing.value) {
        await api.put(`${P_proj.detail(props.projectId)}/se-checklist/${form.value.id}`, form.value)
        ElMessage.success('已更新')
      } else {
        await api.post(`${P_proj.detail(props.projectId)}/se-checklist`, form.value)
        ElMessage.success('已添加')
      }
      dialogVisible.value = false
      loadItems()
    } catch (e) {
      handleApiError(e, '保存')
    }
  })
}

const handleDelete = async (row: any) => {
  try {
    await api.delete(`${P_proj.detail(props.projectId)}/se-checklist/${row.id}`)
    ElMessage.success('已删除')
    loadItems()
  } catch (e) {
    handleApiError(e, '删除')
  }
}

defineExpose({ loadItems })
onMounted(loadItems)
</script>

<style scoped>
.se-checklist-panel { padding: 8px 0; }
.toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
</style>
