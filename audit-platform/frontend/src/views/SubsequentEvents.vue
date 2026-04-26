<template>
  <div class="gt-events gt-fade-in">
    <div class="gt-events-header">
      <h2 class="gt-page-title">后续事项</h2>
      <el-button type="primary" @click="showCreate = true">新增事项</el-button>
    </div>
    <el-table :data="events" border stripe v-loading="loading">
      <el-table-column prop="event_type" label="类型" width="120">
        <template #default="{ row }">
          <el-tag :type="row.event_type === 'adjusting' ? 'warning' : 'info'" size="small">
            {{ row.event_type === 'adjusting' ? '调整事项' : '非调整事项' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="event_description" label="描述" min-width="300" />
      <el-table-column prop="impact_amount" label="影响金额" width="140" align="right" />
      <el-table-column prop="treatment" label="处理方式" width="120" />
      <el-table-column prop="review_status" label="状态" width="100" />
    </el-table>
    <el-dialog append-to-body v-model="showCreate" title="新增后续事项" width="550px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="事项类型">
          <el-radio-group v-model="form.event_type">
            <el-radio value="adjusting">调整事项</el-radio>
            <el-radio value="non_adjusting">非调整事项</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="事项描述"><el-input v-model="form.event_description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="影响金额"><el-input-number v-model="form.impact_amount" :precision="2" style="width: 100%" /></el-form-item>
        <el-form-item label="处理方式">
          <el-select v-model="form.treatment" style="width: 100%">
            <el-option label="已调整" value="adjusted" />
            <el-option label="已披露" value="disclosed" />
            <el-option label="无需处理" value="no_action_needed" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="saveEvent" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listSubsequentEvents, createSubsequentEvent } from '@/services/commonApi'
const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const events = ref<any[]>([])
const loading = ref(false)
const showCreate = ref(false)
const saving = ref(false)
const form = ref({ event_type: 'adjusting', event_description: '', impact_amount: 0, treatment: 'adjusted' })
async function loadEvents() {
  loading.value = true
  try {
    events.value = await listSubsequentEvents(projectId.value)
  } catch { events.value = [] }
  finally { loading.value = false }
}
async function saveEvent() {
  saving.value = true
  try {
    await createSubsequentEvent(projectId.value, form.value)
    ElMessage.success('保存成功')
    showCreate.value = false
    await loadEvents()
  } finally { saving.value = false }
}
onMounted(loadEvents)
</script>
<style scoped>
.gt-events { padding: var(--gt-space-4); }
.gt-events-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-4); }
</style>
