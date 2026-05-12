<template>
  <div class="conflict-workbench">
    <GtPageHeader title="离线冲突处理" :show-back="false" />
    <div class="conflict-layout">
      <!-- 左栏：冲突列表 -->
      <div class="conflict-left">
        <h4>离线冲突（{{ conflicts.length }}）</h4>
        <div
          v-for="c in conflicts" :key="c.id"
          :class="['conflict-item', c.status, { active: selected?.id === c.id }]"
          @click="selected = c"
        >
          <span class="field-name">{{ c.field_name }}</span>
          <el-tag :type="c.status === 'open' ? 'danger' : c.status === 'resolved' ? 'success' : 'info'" size="small">
            {{ c.status === 'open' ? '待处理' : c.status === 'resolved' ? '已解决' : '已驳回' }}
          </el-tag>
        </div>
        <el-empty v-if="!conflicts.length" description="无冲突" />
      </div>

      <!-- 中栏：冲突详情对比 -->
      <div class="conflict-center" v-if="selected">
        <h4>{{ selected.field_name }} 差异对比</h4>
        <div class="diff-compare">
          <div class="diff-side local">
            <div class="diff-label">本地值</div>
            <pre class="diff-value">{{ JSON.stringify(selected.local_value, null, 2) }}</pre>
          </div>
          <div class="diff-arrow">⇄</div>
          <div class="diff-side remote">
            <div class="diff-label">远程值</div>
            <pre class="diff-value">{{ JSON.stringify(selected.remote_value, null, 2) }}</pre>
          </div>
        </div>
      </div>

      <!-- 右栏：处置操作 -->
      <div class="conflict-right" v-if="selected && selected.status === 'open'">
        <h4>处置操作</h4>
        <el-radio-group v-model="resolution" class="resolution-group">
          <el-radio label="accept_local">采纳本地值</el-radio>
          <el-radio label="accept_remote">采纳远程值</el-radio>
          <el-radio label="manual_merge">手动合并</el-radio>
        </el-radio-group>

        <div v-if="resolution === 'manual_merge'" style="margin-top:8px">
          <el-input v-model="mergedValueStr" type="textarea" :rows="4" placeholder='输入合并后的 JSON 值' />
        </div>

        <el-select v-model="reasonCode" placeholder="原因码" style="width:100%;margin-top:8px" size="small">
          <el-option label="数据不一致" value="DATA_MISMATCH" />
          <el-option label="证据不足" value="EVIDENCE_MISSING" />
          <el-option label="策略冲突" value="POLICY_VIOLATION" />
        </el-select>

        <el-button type="primary" style="margin-top:12px;width:100%" @click="handleResolve" :loading="resolving">
          确认处置
        </el-button>

        <div v-if="qcReplayStatus" class="qc-status" style="margin-top:8px">
          <el-tag :type="qcReplayStatus === 'running' ? 'warning' : 'success'" size="small">
            QC 重跑：{{ qcReplayStatus }}
          </el-tag>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listConflicts, resolveConflict } from '@/services/governanceApi'
import { handleApiError } from '@/utils/errorHandler'

const route = useRoute()
const projectId = route.params.projectId as string

const conflicts = ref<any[]>([])
const selected = ref<any>(null)
const resolution = ref('accept_local')
const reasonCode = ref('')
const mergedValueStr = ref('')
const resolving = ref(false)
const qcReplayStatus = ref('')

async function loadData() {
  try {
    const result = await listConflicts({ project_id: projectId, page_size: 200 })
    conflicts.value = result.items || []
  } catch (e: any) { handleApiError(e, '加载冲突列表') }
}

async function handleResolve() {
  if (!selected.value || !reasonCode.value) {
    ElMessage.warning('请选择原因码')
    return
  }
  resolving.value = true
  qcReplayStatus.value = 'running'
  try {
    let merged = undefined
    if (resolution.value === 'manual_merge') {
      try { merged = JSON.parse(mergedValueStr.value) } catch (e: any) { handleApiError(e, '合并值 JSON 格'); resolving.value = false; return }
    }
    const result = await resolveConflict({
      conflict_id: selected.value.id,
      resolution: resolution.value as any,
      merged_value: merged,
      resolver_id: 'current_user_id',
      reason_code: reasonCode.value,
    })
    selected.value.status = 'resolved'
    qcReplayStatus.value = result.qc_replay_job_id ? 'triggered' : 'skipped'
    ElMessage.success('冲突已处置')
    await loadData()
  } catch (e: any) {
    handleApiError(e, '处置')
    qcReplayStatus.value = ''
  } finally { resolving.value = false }
}

onMounted(loadData)
</script>

<style scoped>
.conflict-workbench { padding: 16px; }
.conflict-layout { display: flex; gap: 16px; }
.conflict-left { width: 240px; border: 1px solid #eee; border-radius: 8px; padding: 12px; max-height: 600px; overflow-y: auto; }
.conflict-item { padding: 8px; border-bottom: 1px solid #f0f0f0; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
.conflict-item.active { background: #f5f0ff; }
.conflict-item.open .field-name { color: var(--el-color-danger); }
.conflict-item.resolved .field-name { color: var(--el-color-success); }
.conflict-center { flex: 1; border: 1px solid #eee; border-radius: 8px; padding: 16px; }
.diff-compare { display: flex; gap: 12px; align-items: flex-start; }
.diff-side { flex: 1; }
.diff-label { font-size: 12px; color: #999; margin-bottom: 4px; }
.diff-side.local .diff-label { color: var(--el-color-primary); }
.diff-side.remote .diff-label { color: var(--el-color-warning); }
.diff-value { background: #f9f9f9; padding: 8px; border-radius: 4px; font-size: 12px; max-height: 200px; overflow-y: auto; white-space: pre-wrap; }
.diff-arrow { font-size: 20px; color: #ccc; padding-top: 20px; }
.conflict-right { width: 280px; border: 1px solid #eee; border-radius: 8px; padding: 16px; }
.resolution-group { display: flex; flex-direction: column; gap: 8px; }
</style>
