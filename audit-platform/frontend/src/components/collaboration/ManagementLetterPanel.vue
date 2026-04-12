<template>
  <div class="management-letter-panel">
    <div class="panel-header">
      <h3>管理建议书</h3>
      <div class="header-actions">
        <el-button type="info" size="small" @click="carryForwardFromPriorYear">
          <el-icon><RefreshRight /></el-icon> 上年结转
        </el-button>
        <el-button type="primary" size="small" @click="showAddDialog = true">
          <el-icon><Plus /></el-icon> 添加事项
        </el-button>
      </div>
    </div>

    <!-- Management Letter Items Table -->
    <el-table :data="items" stripe class="letter-table" max-height="400">
      <el-table-column prop="item_code" label="事项编号" width="160" />
      <el-table-column prop="deficiency_type" label="缺陷类型" width="140">
        <template #default="{ row }">
          <el-tag :type="deficiencyTag(row.deficiency_type)" size="small">
            {{ formatDeficiencyType(row.deficiency_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="deficiency_description" label="缺陷描述" min-width="200" show-overflow-tooltip />
      <el-table-column prop="recommendation" label="建议" min-width="150" show-overflow-tooltip />
      <el-table-column prop="management_response" label="管理层回复" min-width="150" show-overflow-tooltip />
      <el-table-column prop="response_deadline" label="回复截止日" width="120">
        <template #default="{ row }">
          {{ row.response_deadline || '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="follow_up_status" label="跟踪状态" width="110">
        <template #default="{ row }">
          <el-tag :type="followUpTag(row.follow_up_status)" size="small">
            {{ followUpLabel(row.follow_up_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="updateFollowUp(row)">更新跟踪</el-button>
          <el-button type="danger" link size="small" @click="deleteItem(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Summary Statistics -->
    <div class="summary-stats">
      <el-row :gutter="20">
        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-value">{{ items.length }}</div>
            <div class="stat-label">总事项数</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-value">{{ unresolvedCount }}</div>
            <div class="stat-label">未解决</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-value">{{ inProgressCount }}</div>
            <div class="stat-label">进行中</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-value">{{ resolvedCount }}</div>
            <div class="stat-label">已解决</div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- Add Item Dialog -->
    <el-dialog v-model="showAddDialog" title="添加管理建议事项" width="650px">
      <el-form :model="newItem" label-width="130px">
        <el-form-item label="缺陷类型">
          <el-select v-model="newItem.deficiency_type">
            <el-option label="重大缺陷" value="material_weakness" />
            <el-option label="重要缺陷" value="significant_deficiency" />
            <el-option label="其他缺陷" value="other_deficiency" />
          </el-select>
        </el-form-item>
        <el-form-item label="缺陷描述">
          <el-input v-model="newItem.deficiency_description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="潜在影响">
          <el-input v-model="newItem.potential_impact" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="审计建议">
          <el-input v-model="newItem.recommendation" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="管理层回复">
          <el-input v-model="newItem.management_response" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="回复截止日">
          <el-date-picker
            v-model="newItem.response_deadline"
            type="date"
            placeholder="选择日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="addItem">确定</el-button>
      </template>
    </el-dialog>

    <!-- Update Follow-up Dialog -->
    <el-dialog v-model="showFollowUpDialog" title="更新跟踪状态" width="500px">
      <el-form label-width="120px">
        <el-form-item label="当前状态">
          <el-tag :type="followUpTag(selectedItem?.follow_up_status)" size="small">
            {{ followUpLabel(selectedItem?.follow_up_status) }}
          </el-tag>
        </el-form-item>
        <el-form-item label="新状态">
          <el-select v-model="followUpData.follow_up_status">
            <el-option label="新增" value="new" />
            <el-option label="进行中" value="in_progress" />
            <el-option label="已解决" value="resolved" />
            <el-option label="结转" value="carried_forward" />
          </el-select>
        </el-form-item>
        <el-form-item label="管理层回复">
          <el-input v-model="followUpData.management_response" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="回复截止日">
          <el-date-picker
            v-model="followUpData.response_deadline"
            type="date"
            placeholder="选择日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="followUpData.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showFollowUpDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmFollowUp">确定</el-button>
      </template>
    </el-dialog>

    <!-- Carry Forward Dialog -->
    <el-dialog v-model="showCarryForwardDialog" title="上年事项结转" width="400px">
      <el-form label-width="120px">
        <el-form-item label="来源项目">
          <el-input v-model="sourceProjectId" placeholder="请输入上年项目ID" />
        </el-form-item>
        <el-alert
          title="说明"
          type="info"
          :closable="false"
          description="将只结转未解决的事项（状态不为"已解决"）"
          show-icon
        />
      </el-form>
      <template #footer>
        <el-button @click="showCarryForwardDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmCarryForward">确认结转</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Plus, RefreshRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { managementLetterApi } from '@/services/collaborationApi'

interface LetterItem {
  id: string
  project_id: string
  item_code: string
  deficiency_type: string
  deficiency_description: string
  potential_impact: string
  recommendation: string
  management_response: string | null
  response_deadline: string | null
  prior_year_item_id: string | null
  follow_up_status: string
  created_at: string
  updated_at: string
}

const props = defineProps<{
  projectId: string
}>()

const items = ref<LetterItem[]>([])
const showAddDialog = ref(false)
const showFollowUpDialog = ref(false)
const showCarryForwardDialog = ref(false)
const selectedItem = ref<LetterItem | null>(null)
const sourceProjectId = ref('')

const newItem = ref({
  deficiency_type: 'significant_deficiency',
  deficiency_description: '',
  potential_impact: '',
  recommendation: '',
  management_response: '',
  response_deadline: '',
})

const followUpData = ref({
  follow_up_status: 'new',
  management_response: '',
  response_deadline: '',
  notes: '',
})

const unresolvedCount = computed(() => items.value.filter(i => i.follow_up_status === 'new').length)
const inProgressCount = computed(() => items.value.filter(i => i.follow_up_status === 'in_progress').length)
const resolvedCount = computed(() => items.value.filter(i => i.follow_up_status === 'resolved').length)

function deficiencyTag(type: string): string {
  const map: Record<string, string> = {
    material_weakness: 'danger',
    significant_deficiency: 'warning',
    other_deficiency: 'info',
  }
  return map[type] || 'info'
}

function formatDeficiencyType(type: string): string {
  const map: Record<string, string> = {
    material_weakness: '重大缺陷',
    significant_deficiency: '重要缺陷',
    other_deficiency: '其他缺陷',
  }
  return map[type] || type
}

function followUpTag(status: string | undefined): string {
  const map: Record<string, string> = {
    new: 'info',
    in_progress: 'warning',
    resolved: 'success',
    carried_forward: '',
  }
  return map[status || ''] || 'info'
}

function followUpLabel(status: string | undefined): string {
  const map: Record<string, string> = {
    new: '新增',
    in_progress: '进行中',
    resolved: '已解决',
    carried_forward: '已结转',
  }
  return map[status || ''] || status || ''
}

async function loadItems() {
  try {
    const { data } = await managementLetterApi.list(props.projectId)
    items.value = data || []
  } catch {
    items.value = []
  }
}

async function addItem() {
  if (!newItem.value.deficiency_description) {
    ElMessage.warning('请填写缺陷描述')
    return
  }
  try {
    const { data } = await managementLetterApi.create(props.projectId, newItem.value)
    items.value.push(data)
    showAddDialog.value = false
    resetNewItem()
    ElMessage.success('事项已添加')
  } catch {
    ElMessage.error('添加失败')
  }
}

function updateFollowUp(item: LetterItem) {
  selectedItem.value = item
  followUpData.value = {
    follow_up_status: item.follow_up_status,
    management_response: item.management_response || '',
    response_deadline: item.response_deadline || '',
    notes: '',
  }
  showFollowUpDialog.value = true
}

async function confirmFollowUp() {
  if (!selectedItem.value) return
  try {
    await managementLetterApi.updateFollowUp(selectedItem.value.id, followUpData.value)
    // Update local state
    const idx = items.value.findIndex(i => i.id === selectedItem.value!.id)
    if (idx !== -1) {
      items.value[idx] = {
        ...items.value[idx],
        ...followUpData.value,
      }
    }
    showFollowUpDialog.value = false
    ElMessage.success('跟踪状态已更新')
  } catch {
    ElMessage.error('更新失败')
  }
}

function carryForwardFromPriorYear() {
  sourceProjectId.value = ''
  showCarryForwardDialog.value = true
}

async function confirmCarryForward() {
  if (!sourceProjectId.value) {
    ElMessage.warning('请输入来源项目ID')
    return
  }
  try {
    const { data } = await managementLetterApi.carryForward(props.projectId, {
      source_project_id: sourceProjectId.value,
    })
    // Add carried items to list
    if (data?.carried_items) {
      items.value.push(...data.carried_items)
    }
    showCarryForwardDialog.value = false
    ElMessage.success(`已结转 ${data?.carried_items?.length || 0} 个事项`)
  } catch {
    ElMessage.error('结转失败')
  }
}

async function deleteItem(item: LetterItem) {
  items.value = items.value.filter(i => i.id !== item.id)
  ElMessage.success('事项已删除')
}

function resetNewItem() {
  newItem.value = {
    deficiency_type: 'significant_deficiency',
    deficiency_description: '',
    potential_impact: '',
    recommendation: '',
    management_response: '',
    response_deadline: '',
  }
}

loadItems()
</script>

<style scoped>
.management-letter-panel {
  padding: 16px;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.panel-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.header-actions {
  display: flex;
  gap: 8px;
}
.letter-table {
  font-size: 13px;
}
.summary-stats {
  margin-top: 16px;
}
.stat-card {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #409EFF;
}
.stat-label {
  font-size: 12px;
  color: #606266;
  margin-top: 4px;
}
</style>
