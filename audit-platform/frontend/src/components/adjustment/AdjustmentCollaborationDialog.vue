<!--
  AdjustmentCollaborationDialog — 调整分录协作接力对话框
  spec: adjustment-collaboration-and-propagation

  分录组级：转派→知晓→补充明细行→确认→退回，含事件时间线。
  - 无活跃协作：发起人选项目成员 + 说明 → 转派。
  - 活跃协作 + 当前用户=被指派人：知晓 / 补充明细行 / 确认 / 退回。
  - 活跃协作 + 当前用户≠被指派人：查看进度 + 退回（发起人）。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    title="调整分录协作"
    width="720px"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @open="onOpen"
  >
    <div v-loading="loading" class="gt-adj-collab">
      <div class="gt-collab-head">
        <span class="gt-collab-no">{{ adjustmentNo || entryGroupId?.slice(0, 8) }}</span>
        <el-tag v-if="collab" :type="(statusTag as any)" size="small">{{ statusLabel }}</el-tag>
        <el-tag v-else type="info" size="small" effect="plain">尚无协作</el-tag>
        <span v-if="collab" class="gt-collab-round">第 {{ collab.round }} 轮</span>
      </div>

      <!-- 退回原因 -->
      <el-alert
        v-if="collab && collab.status === 'rejected' && collab.rejection_reason"
        type="warning" :closable="false" show-icon style="margin-bottom: 10px"
        :title="`已退回：${collab.rejection_reason}`"
      />

      <!-- 发起转派（无活跃协作时） -->
      <div v-if="canAssign" class="gt-collab-section">
        <div class="gt-collab-title">转派补充</div>
        <el-select v-model="assigneeId" filterable placeholder="选择项目成员" size="small" style="width: 240px">
          <el-option v-for="m in members" :key="m.staff_id" :label="`${m.staff_name}（${m.role}）`" :value="m.staff_id" />
        </el-select>
        <el-input v-model="assignNote" size="small" placeholder="转派说明（可选）" style="width: 260px; margin-left: 8px" />
        <el-button type="primary" size="small" :loading="busy" :disabled="!assigneeId" style="margin-left: 8px" @click="doAssign">
          {{ collab ? '再次转派' : '转派' }}
        </el-button>
      </div>

      <!-- 被指派人操作 -->
      <div v-if="isAssignee && isActive" class="gt-collab-section">
        <div class="gt-collab-title">我的协作（补充明细行）</div>
        <el-button v-if="collab!.status === 'pending'" size="small" :loading="busy" @click="doAcknowledge">✓ 我已知晓</el-button>

        <el-table :data="contribRows" border size="small" style="margin: 8px 0">
          <el-table-column label="科目" min-width="200">
            <template #default="{ row }">
              <el-select v-model="row.standard_account_code" filterable placeholder="选择科目" size="small" style="width: 100%">
                <el-option v-for="o in accountOptions" :key="o.code" :label="`${o.code} ${o.name}`" :value="o.code" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="借方" width="130">
            <template #default="{ row }">
              <el-input-number v-model="row.debit_amount" :min="0" :precision="2" :controls="false" size="small" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="贷方" width="130">
            <template #default="{ row }">
              <el-input-number v-model="row.credit_amount" :min="0" :precision="2" :controls="false" size="small" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column width="48">
            <template #default="{ $index }">
              <el-button size="small" type="danger" text :disabled="contribRows.length <= 1" @click="contribRows.splice($index, 1)">✕</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="gt-collab-balance" :class="{ ok: balanced }">
          借 {{ totalDebit.toFixed(2) }} / 贷 {{ totalCredit.toFixed(2) }}
          <span v-if="!balanced">（不平衡，差额 {{ (totalDebit - totalCredit).toFixed(2) }}）</span>
          <span v-else>（平衡）</span>
        </div>
        <el-input v-model="contribNote" size="small" placeholder="补充说明（可选）" style="margin: 6px 0" />
        <div>
          <el-button size="small" @click="addRow">+ 明细行</el-button>
          <el-button type="primary" size="small" :loading="busy" :disabled="!balanced" @click="doContribute">提交补充</el-button>
          <el-button v-if="collab!.status === 'contributed'" type="success" size="small" :loading="busy" @click="doConfirm">✓ 确认</el-button>
          <el-button type="danger" size="small" plain :loading="busy" @click="doReject">退回</el-button>
        </div>
      </div>

      <!-- 发起人视角（活跃但非被指派人） -->
      <div v-else-if="isActive && !isAssignee" class="gt-collab-section">
        <el-text type="info">协作进行中，等待被指派人补充/确认。</el-text>
        <el-button type="danger" size="small" plain :loading="busy" style="margin-left: 8px" @click="doReject">退回</el-button>
      </div>

      <!-- 事件时间线 -->
      <div class="gt-collab-section">
        <div class="gt-collab-title">协作历史</div>
        <el-timeline v-if="timeline.length">
          <el-timeline-item v-for="ev in timeline" :key="ev.id" :timestamp="fmtTime(ev.created_at)" placement="top">
            {{ eventLabel(ev.event_type) }}
            <span v-if="ev.payload && ev.payload.note" style="color: var(--el-text-color-secondary)">：{{ ev.payload.note }}</span>
            <span v-if="ev.payload && ev.payload.reason" style="color: var(--el-color-danger)">：{{ ev.payload.reason }}</span>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无协作历史" :image-size="60" />
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { listAssignments, type Assignment } from '@/services/staffApi'
import {
  useAdjustmentCollaboration,
  COLLAB_STATUS_LABELS,
  COLLAB_STATUS_TAG,
} from '@/components/workpaper/composables/useAdjustmentCollaboration'

interface AccountOption { code: string; name: string }
interface LineItem { standard_account_code?: string; account_name?: string; debit_amount: number; credit_amount: number }

const props = defineProps<{
  modelValue: boolean
  projectId: string
  year: number
  entryGroupId: string
  adjustmentNo?: string
  accountOptions?: AccountOption[]
  lineItems?: LineItem[]
  canEdit?: boolean
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'updated'): void }>()

const auth = useAuthStore()
const collabApi = useAdjustmentCollaboration({
  projectId: () => props.projectId,
  year: () => props.year,
})
const busy = collabApi.busy

const loading = ref(false)
const collab = ref<any>(null)
const timeline = ref<any[]>([])
const members = ref<Assignment[]>([])
const assigneeId = ref('')
const assignNote = ref('')
const contribRows = ref<LineItem[]>([])
const contribNote = ref('')

const ACTIVE = ['pending', 'acknowledged', 'contributed']
const isActive = computed(() => !!collab.value && ACTIVE.includes(collab.value.status))
const isAssignee = computed(() => !!collab.value && collab.value.assignee_id === auth.userId)
const canAssign = computed(() => (props.canEdit !== false) && !isActive.value)
const statusLabel = computed(() => (collab.value ? COLLAB_STATUS_LABELS[collab.value.status] || collab.value.status : ''))
const statusTag = computed(() => (collab.value ? COLLAB_STATUS_TAG[collab.value.status] || 'info' : 'info'))

const totalDebit = computed(() => contribRows.value.reduce((s, r) => s + (Number(r.debit_amount) || 0), 0))
const totalCredit = computed(() => contribRows.value.reduce((s, r) => s + (Number(r.credit_amount) || 0), 0))
const balanced = computed(() => Math.abs(totalDebit.value - totalCredit.value) < 0.005 && (totalDebit.value > 0 || totalCredit.value > 0))

function fmtTime(t: string | null): string {
  if (!t) return ''
  const d = new Date(t.endsWith('Z') || t.includes('+') ? t : t + 'Z')
  return d.toLocaleString('zh-CN')
}
function eventLabel(type: string): string {
  return ({
    assigned: '转派', reassigned: '重派', acknowledged: '已知晓',
    contributed: '提交补充', confirmed: '已确认', rejected: '退回',
    commented: '评论', closed: '关闭',
  } as Record<string, string>)[type] || type
}

function addRow(): void {
  contribRows.value.push({ standard_account_code: '', account_name: '', debit_amount: 0, credit_amount: 0 })
}

async function onOpen(): Promise<void> {
  loading.value = true
  try {
    const [g, m] = await Promise.all([
      collabApi.getGroupCollaboration(props.entryGroupId),
      listAssignments(props.projectId).catch(() => [] as Assignment[]),
    ])
    collab.value = g.collaboration
    timeline.value = g.timeline || []
    members.value = m
    // 补充行预填：优先当前分录组明细，否则空行
    contribRows.value = (props.lineItems && props.lineItems.length)
      ? props.lineItems.map(li => ({ ...li }))
      : [{ standard_account_code: '', account_name: '', debit_amount: 0, credit_amount: 0 }]
    assigneeId.value = ''
    assignNote.value = ''
    contribNote.value = ''
  } finally {
    loading.value = false
  }
}

async function reload(): Promise<void> {
  const g = await collabApi.getGroupCollaboration(props.entryGroupId)
  collab.value = g.collaboration
  timeline.value = g.timeline || []
  emit('updated')
}

async function doAssign(): Promise<void> {
  if (!assigneeId.value) return
  if (await collabApi.assign(props.entryGroupId, assigneeId.value, assignNote.value || undefined)) {
    assignNote.value = ''
    await reload()
  }
}
async function doAcknowledge(): Promise<void> {
  if (collab.value && await collabApi.acknowledge(collab.value.id)) await reload()
}
async function doContribute(): Promise<void> {
  if (!collab.value) return
  if (!balanced.value) { ElMessage.error('借贷不平衡，无法提交'); return }
  const items = contribRows.value.filter(r => (Number(r.debit_amount) || 0) !== 0 || (Number(r.credit_amount) || 0) !== 0)
  if (await collabApi.contribute(collab.value.id, items, contribNote.value || undefined)) await reload()
}
async function doConfirm(): Promise<void> {
  if (collab.value && await collabApi.confirm(collab.value.id)) await reload()
}
async function doReject(): Promise<void> {
  if (!collab.value) return
  try {
    const { value } = await ElMessageBox.prompt('请输入退回原因', '退回协作', {
      confirmButtonText: '退回', cancelButtonText: '取消',
      inputValidator: (v: string) => (v && v.trim() ? true : '请输入退回原因'),
    })
    if (await collabApi.reject(collab.value.id, value.trim())) await reload()
  } catch { /* 取消 */ }
}
</script>

<style scoped>
.gt-adj-collab { font-size: 13px; }
.gt-collab-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.gt-collab-no { font-weight: 600; }
.gt-collab-round { color: var(--el-text-color-secondary); font-size: 12px; }
.gt-collab-section { padding: 10px 0; border-top: 1px solid var(--el-border-color-lighter); }
.gt-collab-title { font-weight: 600; margin-bottom: 8px; color: var(--el-color-primary); }
.gt-collab-balance { font-size: 12px; color: var(--el-color-danger); }
.gt-collab-balance.ok { color: var(--el-color-success); }
</style>
