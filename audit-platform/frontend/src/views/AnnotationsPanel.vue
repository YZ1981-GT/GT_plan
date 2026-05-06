<template>
  <div class="gt-annotations gt-fade-in">
    <div class="gt-page-header">
      <h2 class="gt-page-title">复核批注</h2>
      <div class="gt-header-actions">
        <el-select v-model="filters.status" placeholder="状态" clearable size="default" @change="fetch">
          <el-option label="待处理" value="pending" />
          <el-option label="已回复" value="replied" />
          <el-option label="已解决" value="resolved" />
        </el-select>
        <el-select v-model="filters.priority" placeholder="优先级" clearable size="default" @change="fetch">
          <el-option label="高" value="high" />
          <el-option label="中" value="medium" />
          <el-option label="低" value="low" />
        </el-select>
        <el-button type="primary" @click="showCreate = true">添加批注</el-button>
      </div>
    </div>
    <el-table :data="annotations" stripe>
      <el-table-column prop="cell_ref" label="单元格" width="120" />
      <el-table-column prop="content" label="内容" show-overflow-tooltip />
      <el-table-column prop="priority" label="优先级" width="80">
        <template #default="{ row }">
          <el-tag :type="row.priority === 'high' ? 'danger' : row.priority === 'medium' ? 'warning' : 'info'" size="small">
            {{ row.priority === 'high' ? '高' : row.priority === 'medium' ? '中' : '低' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="(row.status === 'pending' ? 'warning' : row.status === 'replied' ? '' : 'success') || undefined" size="small">
            {{ row.status === 'pending' ? '待处理' : row.status === 'replied' ? '已回复' : '已解决' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button size="small" @click="onResolve(row.id)" v-if="row.status !== 'resolved'">解决</el-button>
          <el-button size="small" @click="onReply(row.id)" v-if="row.status === 'pending'">回复</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog append-to-body v-model="showCreate" title="添加批注" width="480px">
      <el-form label-width="80px">
        <el-form-item label="对象类型">
          <el-select v-model="form.object_type">
            <el-option label="底稿" value="workpaper" />
            <el-option label="附注" value="disclosure_note" />
          </el-select>
        </el-form-item>
        <el-form-item label="单元格"><el-input v-model="form.cell_ref" placeholder="如 E9-1!B15" /></el-form-item>
        <el-form-item label="内容"><el-input v-model="form.content" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="form.priority"><el-option label="高" value="high" /><el-option label="中" value="medium" /><el-option label="低" value="low" /></el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="onCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listAnnotations, createAnnotation, updateAnnotation } from '@/services/commonApi'
const route = useRoute()
const projectId = ref(route.params.projectId as string || '')
const annotations = ref<any[]>([])
const filters = ref({ status: '', priority: '' })
const showCreate = ref(false)
const form = ref({ object_type: 'workpaper', object_id: '00000000-0000-0000-0000-000000000000', cell_ref: '', content: '', priority: 'medium' })
async function fetch() {
  if (!projectId.value) return
  annotations.value = await listAnnotations(projectId.value, { status: filters.value.status || undefined, priority: filters.value.priority || undefined })
}
async function onCreate() {
  if (!form.value.content) return ElMessage.warning('请输入内容')
  await createAnnotation(projectId.value, form.value)
  showCreate.value = false
  ElMessage.success('批注已创建')
  await fetch()
}
async function onResolve(id: string) { await updateAnnotation(id, { status: 'resolved' }); await fetch() }
async function onReply(id: string) { await updateAnnotation(id, { status: 'replied' }); await fetch() }
onMounted(fetch)
</script>
<style scoped>
.gt-annotations { padding: var(--gt-space-4); }
.gt-page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-header-actions { display: flex; gap: var(--gt-space-2); }
</style>
