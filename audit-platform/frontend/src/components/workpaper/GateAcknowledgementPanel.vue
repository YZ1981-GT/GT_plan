<script setup lang="ts">
/**
 * S2 ADR-CCN-06: 门禁逐项确认面板
 *
 * 列出当前项目的门禁阻断项，显示五态中文标签，
 * enforce 模式下允许确认/撤销。observe 模式隐藏确认入口。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listAcks,
  acknowledge,
  revoke,
  type GateAcknowledgement,
} from '@/composables/useGateAcknowledgements'

/** 五态中文标签映射 */
const STATUS_LABELS: Record<string, string> = {
  passed: '通过',
  failed: '未通过',
  not_executed: '未执行',
  not_applicable: '不适用',
  error: '检查异常',
}

interface BlockingHit {
  rule_code: string
  error_code: string
  severity: string
  message: string
  location: Record<string, unknown>
  suggested_action?: string
  status?: string
  check_class?: string
}

const props = defineProps<{
  projectId: string
  year: number
  /** sign-readiness 返回的 blocking hit 列表 */
  blockingHits: BlockingHit[]
  /** 当前模式: observe / enforce */
  mode: string
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
}>()

const acks = ref<GateAcknowledgement[]>([])
const loading = ref(false)

// 确认弹窗状态
const confirmDialogVisible = ref(false)
const confirmReason = ref('')
const confirmingHit = ref<BlockingHit | null>(null)
const submitting = ref(false)

const isEnforce = computed(() => props.mode === 'enforce')

/** 加载确认列表 */
async function loadAcks() {
  loading.value = true
  try {
    acks.value = await listAcks(props.projectId, props.year)
  } catch {
    // 静默失败，列表保持空
  } finally {
    loading.value = false
  }
}

/** 查找某 hit 对应的有效（未撤销）确认 */
function findActiveAck(hit: BlockingHit): GateAcknowledgement | undefined {
  return acks.value.find(
    (a) => a.check_name === hit.rule_code && !a.revoked_at,
  )
}

/** 获取五态标签 */
function statusLabel(status: string | undefined): string {
  if (!status) return '未知'
  return STATUS_LABELS[status] || status
}

/** 打开确认弹窗 */
function openConfirmDialog(hit: BlockingHit) {
  confirmingHit.value = hit
  confirmReason.value = ''
  confirmDialogVisible.value = true
}

/** 提交确认 */
async function submitConfirm() {
  if (!confirmingHit.value) return
  if (confirmReason.value.trim().length < 10) {
    ElMessage.warning('确认原因至少需要 10 个字符')
    return
  }

  submitting.value = true
  try {
    const hit = confirmingHit.value
    const location = hit.location || {}
    await acknowledge(props.projectId, {
      year: props.year,
      check_name: hit.rule_code,
      branch_id: String(location.branch_id || ''),
      status: hit.status || hit.severity || 'failed',
      result_fingerprint: '', // 由后端计算或前端传入
      reason: confirmReason.value,
      check_class: hit.check_class || 'data-missing',
    })
    ElMessage.success('确认成功')
    confirmDialogVisible.value = false
    await loadAcks()
    emit('refresh')
  } catch (err: unknown) {
    const msg =
      err && typeof err === 'object' && 'message' in err
        ? (err as { message: string }).message
        : '确认失败'
    ElMessage.error(msg)
  } finally {
    submitting.value = false
  }
}

/** 撤销确认 */
async function handleRevoke(ack: GateAcknowledgement) {
  try {
    await ElMessageBox.confirm('确定撤销此确认？撤销后该项将恢复阻断状态。', '撤销确认', {
      confirmButtonText: '撤销',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return // 用户取消
  }

  try {
    await revoke(props.projectId, ack.id)
    ElMessage.success('已撤销')
    await loadAcks()
    emit('refresh')
  } catch {
    ElMessage.error('撤销失败')
  }
}

onMounted(loadAcks)
</script>

<template>
  <div class="gate-acknowledgement-panel">
    <div v-if="blockingHits.length === 0" class="empty-state">
      暂无阻断项
    </div>

    <div v-for="hit in blockingHits" :key="hit.rule_code" class="hit-item">
      <div class="hit-header">
        <span class="rule-code">{{ hit.rule_code }}</span>
        <span
          :class="['status-tag', `status-${hit.status || hit.severity}`]"
        >
          {{ statusLabel(hit.status || hit.severity) }}
        </span>
      </div>
      <div class="hit-message">{{ hit.message }}</div>

      <!-- 已确认的显示确认信息 + 撤销按钮 -->
      <template v-if="findActiveAck(hit)">
        <div class="ack-info">
          <span class="ack-label">已确认</span>
          <span class="ack-by">{{ findActiveAck(hit)!.acknowledged_role }}</span>
          <span class="ack-time">{{ findActiveAck(hit)!.created_at }}</span>
          <span class="ack-reason">原因：{{ findActiveAck(hit)!.reason }}</span>
          <el-button
            v-if="isEnforce"
            size="small"
            type="danger"
            plain
            @click="handleRevoke(findActiveAck(hit)!)"
          >
            撤销
          </el-button>
        </div>
      </template>

      <!-- enforce 模式且未确认，显示确认按钮 -->
      <template v-else-if="isEnforce">
        <el-button
          size="small"
          type="primary"
          plain
          class="confirm-btn"
          @click="openConfirmDialog(hit)"
        >
          确认并说明
        </el-button>
      </template>
    </div>

    <!-- 确认弹窗 -->
    <el-dialog
      v-model="confirmDialogVisible"
      title="确认阻断项"
      width="480px"
      :close-on-click-modal="false"
    >
      <div v-if="confirmingHit" class="confirm-dialog-body">
        <p>{{ confirmingHit.rule_code }}: {{ confirmingHit.message }}</p>
        <el-input
          v-model="confirmReason"
          type="textarea"
          :rows="4"
          placeholder="请填写确认原因（至少 10 个字符）"
          maxlength="500"
          show-word-limit
        />
      </div>
      <template #footer>
        <el-button @click="confirmDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="submitting"
          :disabled="confirmReason.trim().length < 10"
          @click="submitConfirm"
        >
          确认
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.gate-acknowledgement-panel {
  padding: 12px 0;
}
.hit-item {
  padding: 12px;
  margin-bottom: 8px;
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 4px;
}
.hit-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.rule-code {
  font-weight: 600;
}
.status-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}
.status-passed { background: #e1f3d8; color: #67c23a; }
.status-failed, .status-blocking { background: #fde2e2; color: #f56c6c; }
.status-not_executed { background: #faecd8; color: #e6a23c; }
.status-not_applicable { background: #e9e9eb; color: #909399; }
.status-error { background: #fde2e2; color: #f56c6c; }
.status-warning { background: #faecd8; color: #e6a23c; }
.hit-message {
  color: var(--el-text-color-secondary, #606266);
  font-size: 13px;
  margin-bottom: 8px;
}
.ack-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}
.ack-label {
  color: #67c23a;
  font-weight: 600;
}
.confirm-btn {
  margin-top: 4px;
}
.empty-state {
  color: var(--el-text-color-secondary, #909399);
  text-align: center;
  padding: 24px;
}
.confirm-dialog-body p {
  margin-bottom: 12px;
  color: var(--el-text-color-primary, #303133);
}
</style>
