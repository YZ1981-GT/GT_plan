<template>
  <div class="gt-subsequent-events-panel">
    <el-tabs v-model="activeTab" class="events-tabs">
      <!-- Tab 1: 期后事项记录 -->
      <el-tab-pane label="期后事项记录" name="events">
        <div class="tab-header">
          <el-button type="primary" @click="openCreateDialog">新建</el-button>
        </div>

        <el-table :data="events" stripe>
          <el-table-column prop="event_date" label="事项日期" width="120" />
          <el-table-column prop="event_type" label="事项类型" width="140">
            <template #default="{ row }">
              <el-tag :type="row.event_type === 'ADJUSTING' ? 'warning' : 'info'" size="small">
                {{ row.event_type }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" />
          <el-table-column prop="financial_impact" label="财务影响" width="150">
            <template #default="{ row }">
              {{ row.financial_impact !== null ? Number(row.financial_impact).toFixed(2) : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="已披露" width="120">
            <template #default="{ row }">
              <el-tag :type="row.is_disclosed ? 'success' : 'info'" size="small">
                {{ row.is_disclosed ? 'Yes' : 'No' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab 2: 审阅程序清单 -->
      <el-tab-pane label="审阅程序清单" name="checklist">
        <div class="tab-header">
          <el-button type="primary" @click="initChecklist">初始化清单</el-button>
        </div>

        <el-table :data="checklistItems" stripe>
          <el-table-column prop="item_code" label="编号" width="120" />
          <el-table-column prop="description" label="描述" />
          <el-table-column label="完成状态" width="120">
            <template #default="{ row }">
              <el-tag :type="row.is_completed ? 'success' : 'info'" size="small">
                {{ row.is_completed ? '已完成' : '待完成' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="completed_at" label="完成时间" width="180">
            <template #default="{ row }">
              {{ row.completed_at || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button size="small" type="success" :disabled="row.is_completed" @click="completeItem(row)">
                标记完成
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 新建对话框 -->
    <el-dialog append-to-body v-model="dialogVisible" title="新建期后事项" width="500px">
      <el-form ref="eventFormRef" :model="eventForm" :rules="eventRules" label-width="100px">
        <el-form-item label="事项日期" prop="event_date">
          <el-date-picker
            v-model="eventForm.event_date"
            type="date"
            placeholder="选择日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="事项类型" prop="event_type">
          <el-select v-model="eventForm.event_type" placeholder="选择类型" style="width: 100%">
            <el-option label="调整事项" value="ADJUSTING" />
            <el-option label="非调整事项" value="NON_ADJUSTING" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="eventForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="财务影响">
          <el-input v-model.number="eventForm.financial_impact" type="number" placeholder="0.00" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="createEvent">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { subsequentEventApi } from '@/services/collaborationApi'
import { rules } from '@/utils/formRules'

const projectId = 'current-project-id'
const activeTab = ref('events')
const events = ref<any[]>([])
const checklistItems = ref<any[]>([])
const dialogVisible = ref(false)
const eventFormRef = ref<FormInstance>()

const eventForm = ref({
  event_date: '',
  event_type: 'ADJUSTING',
  description: '',
  financial_impact: null as number | null,
})

const eventRules: FormRules = {
  event_date: [{ required: true, message: '请选择事件日期', trigger: 'change' }],
  description: [rules.required('描述')],
}

onMounted(async () => {
  await loadEvents()
  await loadChecklist()
})

async function loadEvents() {
  try {
    const { data } = await subsequentEventApi.getEvents(projectId)
    events.value = data || []
  } catch (e) {
    console.error('加载期后事项失败', e)
  }
}

async function loadChecklist() {
  try {
    const { data } = await subsequentEventApi.getChecklist(projectId)
    checklistItems.value = data || []
  } catch (e) {
    console.error('加载清单失败', e)
  }
}

function openCreateDialog() {
  eventForm.value = {
    event_date: '',
    event_type: 'ADJUSTING',
    description: '',
    financial_impact: null,
  }
  dialogVisible.value = true
}

async function createEvent() {
  if (!eventForm.value.event_date || !eventForm.value.description) {
    ElMessage.warning('请填写必填项')
    return
  }
  try {
    await subsequentEventApi.createEvent(projectId, eventForm.value)
    ElMessage.success('创建成功')
    dialogVisible.value = false
    await loadEvents()
  } catch (e) {
    handleApiError(e, '创建')
  }
}

async function initChecklist() {
  try {
    await subsequentEventApi.initChecklist(projectId)
    ElMessage.success('清单已初始化')
    await loadChecklist()
  } catch (e) {
    handleApiError(e, '初始化')
  }
}

async function completeItem(row: any) {
  try {
    await subsequentEventApi.completeChecklistItem(projectId, row.id)
    ElMessage.success('已标记完成')
    row.is_completed = true
  } catch (e) {
    handleApiError(e, '操作')
  }
}
</script>

<style scoped>
.gt-subsequent-events-panel {
  padding: 16px;
}

.tab-header {
  margin-bottom: 16px;
}
</style>
