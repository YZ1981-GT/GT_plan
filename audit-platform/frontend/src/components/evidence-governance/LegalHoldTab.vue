<script setup lang="ts">
/**
 * LegalHoldTab — 法定保全列表/创建/范围/解除 + 清理任务四条件门禁（useLegalHoldGovernance）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening (R13)
 */
import { ref, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useLegalHoldGovernance,
  type LegalHoldItem,
  type HoldScopeNode,
  type PurgeResult,
} from '@/composables/useLegalHoldGovernance'

const props = defineProps<{ projectId: string; year: number }>()
const projectIdRef = toRef(props, 'projectId') as any
const yearRef = toRef(props, 'year') as any
const {
  loading, error, holds,
  listHolds, createHold, getHoldScope, releaseHold, createPurgeJob,
} = useLegalHoldGovernance(projectIdRef, yearRef)

const newReason = ref('')
const seedType = ref('attachment_version')
const seedId = ref('')

const scopeNodes = ref<HoldScopeNode[]>([])
const scopeHoldId = ref('')

// purge
const purgeType = ref('attachment_version')
const purgeId = ref('')
const retentionExpired = ref(false)
const purgeResult = ref<PurgeResult | null>(null)

async function refresh() {
  await listHolds()
  if (error.value) ElMessage.error(error.value)
}

async function onCreate() {
  if (!newReason.value) { ElMessage.warning('请填写保全原因'); return }
  const seeds = seedId.value ? [{ node_type: seedType.value, node_id: seedId.value }] : []
  const res = await createHold({ reason: newReason.value, seed_nodes: seeds })
  if (res) {
    ElMessage.success(`已创建保全（直接 ${res.direct_count} · 传递 ${res.transitive_count}）`)
    newReason.value = ''; seedId.value = ''
    await refresh()
  } else if (error.value) ElMessage.error(error.value)
}

async function onViewScope(id: string) {
  scopeHoldId.value = id
  scopeNodes.value = await getHoldScope(id)
  if (error.value) ElMessage.error(error.value)
}

async function onRelease(id: string) {
  try {
    const { value } = await ElMessageBox.prompt('输入解除原因（保留期未届满时仍禁止清理）', '解除法定保全', {})
    if (!value) return
    const res = await releaseHold(id, value)
    if (res) { ElMessage.success('保全已解除'); await refresh() }
    else if (error.value) ElMessage.error(error.value)
  } catch { /* cancelled */ }
}

async function onPurge() {
  if (!purgeId.value) { ElMessage.warning('请填写清理目标 ID'); return }
  purgeResult.value = await createPurgeJob({
    node_type: purgeType.value,
    node_id: purgeId.value,
    retention_expired: retentionExpired.value,
    purge_reason: 'retention_expired',
  })
  if (purgeResult.value) {
    if (purgeResult.value.allowed) ElMessage.success('清理已授权并写入墓碑')
    else ElMessage.warning(`清理零效果，未满足：${purgeResult.value.unmet_conditions.join('、')}`)
  } else if (error.value) ElMessage.error(error.value)
}

const stateType = (s: string) => (s === 'active' ? 'danger' : 'info')

onMounted(refresh)
</script>

<template>
  <div class="evgov-tab">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="法定保全生效期间，对其直接与传递关联对象的删除/清理/覆盖恒为零效果（任何角色含管理员均不可绕过）。仅 hold 已解除 ∧ 保留期届满 ∧ 授权 ∧ 无悬空引用时可清理。"
      style="margin-bottom: 12px"
    />

    <el-card shadow="never" header="创建法定保全" style="margin-bottom: 16px">
      <el-form :inline="true" size="default">
        <el-form-item label="原因">
          <el-input v-model="newReason" placeholder="保全原因" style="width: 240px" />
        </el-form-item>
        <el-form-item label="种子节点类型">
          <el-select v-model="seedType" style="width: 160px">
            <el-option label="附件版本" value="attachment_version" />
            <el-option label="EvidenceRef" value="evidence_ref" />
            <el-option label="OCR 任务" value="ocr_job" />
            <el-option label="归档清单" value="archive_manifest" />
          </el-select>
        </el-form-item>
        <el-form-item label="种子 ID">
          <el-input v-model="seedId" placeholder="node_id（可选）" style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="onCreate">创建保全</el-button>
          <el-button @click="refresh">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-alert v-if="error" type="error" :title="error" show-icon :closable="true" style="margin-bottom: 12px" />

    <el-table :data="holds" size="small" border stripe v-loading="loading" empty-text="暂无法定保全">
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="stateType(row.state)">{{ row.state === 'active' ? '生效中' : '已解除' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="reason" label="原因" min-width="180" />
      <el-table-column prop="graph_watermark" label="图 watermark" min-width="140">
        <template #default="{ row }"><span class="mono">{{ row.graph_watermark ? row.graph_watermark.slice(0, 14) + '…' : '-' }}</span></template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" min-width="150" />
      <el-table-column label="操作" width="160" align="center">
        <template #default="{ row }">
          <el-button size="small" type="primary" text @click="onViewScope(row.id)">范围</el-button>
          <el-button v-if="row.state === 'active'" size="small" type="danger" text @click="onRelease(row.id)">解除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card v-if="scopeNodes.length" shadow="never" header="保全保护范围" style="margin-top: 16px">
      <el-table :data="scopeNodes" size="small" border stripe>
        <el-table-column prop="node_type" label="节点类型" width="160" />
        <el-table-column prop="node_id" label="节点 ID" min-width="200" />
        <el-table-column label="范围" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.scope_kind === 'direct' ? '' : 'warning'">
              {{ row.scope_kind === 'direct' ? '直接' : '传递' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" header="清理任务（四条件门禁）" style="margin-top: 16px">
      <el-form :inline="true" size="default">
        <el-form-item label="节点类型">
          <el-select v-model="purgeType" style="width: 160px">
            <el-option label="附件版本" value="attachment_version" />
            <el-option label="EvidenceRef" value="evidence_ref" />
            <el-option label="OCR 任务" value="ocr_job" />
          </el-select>
        </el-form-item>
        <el-form-item label="节点 ID">
          <el-input v-model="purgeId" placeholder="node_id" style="width: 200px" />
        </el-form-item>
        <el-form-item label="保留期已届满">
          <el-switch v-model="retentionExpired" />
        </el-form-item>
        <el-form-item>
          <el-button type="danger" plain :loading="loading" @click="onPurge">提交清理</el-button>
        </el-form-item>
      </el-form>
      <el-alert v-if="purgeResult" :type="purgeResult.allowed ? 'success' : 'warning'" :closable="true" show-icon style="margin-top: 8px"
        :title="purgeResult.allowed ? `清理已授权（delta=${purgeResult.delta}，墓碑 ${purgeResult.tombstone_id}）` : `零效果，未满足条件：${purgeResult.unmet_conditions.join('、')}`" />
    </el-card>
  </div>
</template>

<style scoped>
.evgov-tab { padding: 4px 0; }
.mono { font-family: 'Courier New', monospace; font-size: 12px; }
</style>
