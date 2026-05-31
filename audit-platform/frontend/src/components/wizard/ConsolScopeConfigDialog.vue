<template>
  <!--
    ConsolScopeConfigDialog — 配置合并范围（Phase 3 需求 5.1）
    合并项目（report_scope=consolidated）创建后弹出，选择已有单体项目挂为子公司。
    确认后调 attach-subsidiaries 端点，后端设置 parent_project_id + 广播 CONSOL_SCOPE_CHANGED，
    合并模块企业树随即自动刷新。可"暂不配置"跳过（后续在合并模块再配）。
  -->
  <el-dialog
    :model-value="modelValue"
    title="配置合并范围"
    width="640px"
    append-to-body
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @open="handleOpen"
  >
    <div v-loading="loading">
      <p class="gt-scope-hint">
        选择要纳入本合并项目的已有单体项目作为子公司。也可以点击「暂不配置」，稍后在「合并项目」模块配置。
      </p>

      <el-empty v-if="!loading && candidates.length === 0" description="暂无可纳入的单体项目" />

      <el-table
        v-else
        ref="tableRef"
        :data="candidates"
        border
        size="small"
        max-height="360"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column label="项目名称" min-width="220">
          <template #default="{ row }">
            {{ row.name || row.client_name || '未命名项目' }}
          </template>
        </el-table-column>
        <el-table-column label="客户名称" min-width="180">
          <template #default="{ row }">{{ row.client_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.parent_project_id ? 'success' : 'info'">
              {{ row.parent_project_id ? '已纳入' : '未纳入' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">暂不配置</el-button>
      <el-button
        type="primary"
        :loading="saving"
        :disabled="selected.length === 0"
        @click="onConfirm"
      >
        纳入选中（{{ selected.length }}）
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { projects as P_proj } from '@/services/apiPaths'

interface CandidateProject {
  id: string
  name: string | null
  client_name: string
  parent_project_id: string | null
}

const props = defineProps<{
  modelValue: boolean
  projectId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  /** 纳入成功后通知父组件（携带纳入的项目数） */
  attached: [count: number]
}>()

const loading = ref(false)
const saving = ref(false)
const candidates = ref<CandidateProject[]>([])
const selected = ref<CandidateProject[]>([])
const tableRef = ref<any>(null)

async function handleOpen() {
  await fetchCandidates()
}

async function fetchCandidates() {
  if (!props.projectId) return
  loading.value = true
  candidates.value = []
  selected.value = []
  try {
    const data = await api.get<CandidateProject[]>(P_proj.availableSubsidiaries(props.projectId))
    candidates.value = Array.isArray(data) ? data : []
  } catch {
    // 端点不可用时友好降级为空列表（用户可稍后在合并模块配置）
    candidates.value = []
  } finally {
    loading.value = false
  }
}

function onSelectionChange(rows: CandidateProject[]) {
  selected.value = rows
}

async function onConfirm() {
  if (!props.projectId || selected.value.length === 0) return
  saving.value = true
  try {
    const childIds = selected.value.map((p) => p.id)
    const data = await api.post<CandidateProject[]>(
      P_proj.attachSubsidiaries(props.projectId),
      { child_project_ids: childIds },
    )
    const count = Array.isArray(data) ? data.length : 0
    ElMessage.success(`已纳入 ${count} 个子公司`)
    emit('attached', count)
    emit('update:modelValue', false)
  } catch {
    ElMessage.error('配置合并范围失败，请稍后在合并模块重试')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.gt-scope-hint {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  line-height: 1.6;
  margin: 0 0 12px;
}
</style>
