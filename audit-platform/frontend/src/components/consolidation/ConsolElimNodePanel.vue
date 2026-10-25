<template>
  <!--
    差额分录面板（spec consol-tree-three-code-autobuild 任务 10.5 / 需求 9.3）
    点击企业树的差额节点（合并差额 / 母分差额）打开：列出归属本节点的分录（含状态），
    新增 / 修改 / 删除草稿 / 提交审批 / 审批 / 驳回 / 撤销审批，并显示按科目归一后的节点金额。
    新增与修改用 ConsolElimEntryForm（与合并抵消分录明细表同一表单，spec consol-elimination-single-source-push 需求 1.3），
    归属固定为本节点。分录由其他合并项目承载（下级合并企业的差额）时只读，给出前往链接。
    关闭：抽屉开始离场（close 事件）就通知父组件关闭 —— Element Plus 默认到离场动画结束才回写 false，
    其间父组件仍为打开态，用户此时点另一个差额节点的「打开」会被吞掉。
  -->
  <el-drawer
    :model-value="modelValue"
    :title="drawerTitle"
    size="760px"
    append-to-body
    destroy-on-close
    data-testid="elim-panel"
    @close="emit('update:modelValue', false)"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div v-if="node" class="elim-panel">
      <el-alert v-if="readonly" type="info" :closable="false" show-icon data-testid="elim-panel-readonly">
        <template #title>
          <span>本节点的分录由「{{ hostLabel }}」合并项目承载，这里只能查看。</span>
          <el-link v-if="node.host_project_id" type="primary" style="margin-left:8px" data-testid="elim-panel-goto"
            @click="goHost">前往该合并项目录入</el-link>
        </template>
      </el-alert>
      <p class="elim-panel-hint">{{ scopeHint }}</p>

      <div class="elim-panel-toolbar">
        <span class="elim-panel-count">共 {{ entries.length }} 笔分录，已审批 {{ approvedCount }} 笔</span>
        <span style="flex:1" />
        <el-button size="small" :loading="loading" @click="reload">🔄 刷新</el-button>
        <el-button v-if="!readonly" size="small" type="primary" data-testid="elim-panel-new" @click="openCreate">
          + 新增分录
        </el-button>
      </div>
      <el-table v-loading="loading" :data="entries" border size="small" max-height="320" data-testid="elim-panel-list"
        empty-text="暂无分录">
        <!-- 列宽合计 ≤ 抽屉内容宽（760 − 2×20 内边距）：超出会横向滚动，右侧固定的操作列会盖住状态列 -->
        <el-table-column prop="entry_no" label="编号" width="120" />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">{{ typeLabel(row.entry_type) }}</template>
        </el-table-column>
        <el-table-column label="说明" min-width="100" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '—' }}</template>
        </el-table-column>
        <el-table-column label="借方合计" width="110" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.debit_amount" /></template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.review_status)" :data-testid="`elim-status-${row.entry_no}`">
              {{ statusLabel(row.review_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="!readonly" label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canEdit(row)" size="small" link type="primary" @click="openEdit(row)">修改</el-button>
            <el-button v-if="canSubmit(row)" size="small" link type="primary" :data-testid="`elim-submit-${row.entry_no}`"
              @click="act(row, 'submit')">提交审批</el-button>
            <el-button v-if="canApprove(row)" size="small" link type="success" :data-testid="`elim-approve-${row.entry_no}`"
              @click="act(row, 'approve')">审批</el-button>
            <el-button v-if="canApprove(row)" size="small" link type="warning" @click="rejectEntry(row)">驳回</el-button>
            <el-button v-if="canRevoke(row)" size="small" link type="warning" :data-testid="`elim-revoke-${row.entry_no}`"
              @click="revokeEntry(row)">撤销审批</el-button>
            <el-button v-if="canEdit(row)" size="small" link type="danger" :data-testid="`elim-delete-${row.entry_no}`"
              @click="removeEntry(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="elim-panel-section-title">节点金额（按科目自然方向归一，只计已审批分录）</div>
      <el-table v-loading="amountsLoading" :data="amountRows" border size="small" max-height="260"
        data-testid="elim-panel-amounts" empty-text="暂无已审批分录">
        <el-table-column label="科目" min-width="160">
          <template #default="{ row }">{{ row.account_code }} {{ row.account_name || '' }}</template>
        </el-table-column>
        <el-table-column label="方向" width="90" align="center">
          <template #default="{ row }">{{ row.direction === 'credit' ? '贷方性质' : '借方性质' }}</template>
        </el-table-column>
        <el-table-column label="调整" width="120" align="right">
          <template #default="{ row }"><GtAmountCell :value="adjustmentNet(row)" /></template>
        </el-table-column>
        <el-table-column label="抵销" width="120" align="right">
          <template #default="{ row }"><GtAmountCell :value="eliminationNet(row)" /></template>
        </el-table-column>
        <el-table-column label="合计影响" width="130" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.net_difference" /></template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新增 / 修改分录：与合并抵消分录明细表同一表单组件，归属固定为本节点 -->
    <ConsolElimEntryForm
      v-if="!readonly"
      v-model="formVisible"
      :project-id="projectId"
      :year="year"
      :targets="panelTargets"
      lock-target
      :accounts="accounts"
      :entry="editingEntry"
      @saved="onSaved"
    />
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import ConsolElimEntryForm from '@/components/consolidation/ConsolElimEntryForm.vue'
import {
  deleteElimination,
  drillToEliminations,
  getEliminations,
  getNodeAmounts,
  getWorksheetAccounts,
  reviewElimination,
  type ConsolAccountOption,
  type ConsolTreeNode,
  type EliminationEntry,
  type NodeAmountRow,
} from '@/services/consolidationApi'
import { confirmDangerous, confirmDelete, promptRejectReason } from '@/utils/confirm'
import { findConsolNodeByProject, nodeLabel } from '@/components/consolidation/composables/consolTreeView'
import {
  canApprove,
  canEdit,
  canRevoke,
  canSubmit,
  elimTargetOf,
  isCounted,
  normalizeDrillRow,
  signedNet,
  statusLabel,
  statusTagType,
  typeLabel,
} from '@/components/consolidation/composables/elimNodePanel'

defineOptions({ name: 'ConsolElimNodePanel' })

const props = defineProps<{
  modelValue: boolean
  projectId: string
  year: number | null
  node: ConsolTreeNode | null
  tree: ConsolTreeNode | null
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'changed'): void
}>()

const router = useRouter()

// ─── 列表与节点金额 ──────────────────────────────────────────────────────────
const loading = ref(false)
const amountsLoading = ref(false)
const entries = ref<EliminationEntry[]>([])
const amountRows = ref<NodeAmountRow[]>([])
const accounts = ref<ConsolAccountOption[]>([])

/** 差额节点由其他合并项目承载（下级合并企业的差额）⇒ 只读，到承载项目录入 */
const readonly = computed(() => !!props.node?.host_project_id && props.node.host_project_id !== props.projectId)
const hostLabel = computed(() => {
  const host = findConsolNodeByProject(props.tree, props.node?.host_project_id)
  return host ? nodeLabel(host) : '其他'
})
const drawerTitle = computed(() => (props.node ? `差额分录 — ${nodeLabel(props.node)}` : '差额分录'))
const approvedCount = computed(() => entries.value.filter(isCounted).length)
const scopeHint = computed(() => {
  const n = props.node
  if (!n) return ''
  if (n.role === 'branch_elim') {
    return `母分差额：${n.company_name}本部与其分公司之间的内部抵销及调整，只计入${n.company_name}的汇总数。`
  }
  return `合并差额：${n.company_name}合并层面的抵销及调整，计入「${n.company_name}（合并）」。`
})

let accountsFor = ''

async function reload() {
  const node = props.node
  if (!node || !props.projectId) return
  loading.value = true
  try {
    if (readonly.value) {
      // 承载项目不是当前项目：经当前合并项目的穿透接口读取（本树内分录，含各审批状态）
      const res = props.year ? await drillToEliminations(props.projectId, props.year, node.node_key) : null
      entries.value = (res?.rows || []).map(normalizeDrillRow)
    } else {
      entries.value = await getEliminations(props.projectId, props.year, { nodeKey: node.node_key })
    }
  } catch {
    entries.value = []
  } finally {
    loading.value = false
  }
  loadAmounts()
  const scope = `${props.projectId}:${props.year ?? ''}`
  if (!readonly.value && accountsFor !== scope) {
    accountsFor = scope
    loadAccounts()
  }
}

// 打开面板或在打开状态下切换到另一个差额节点 ⇒ 重新读取（同一节点的引用刷新不重复读取）
watch(
  () => [props.modelValue, props.node?.node_key] as const,
  ([visible, key], old) => {
    if (!visible || !key) return
    if (old && old[0] && old[1] === key) return
    reload()
  },
  { immediate: true },
)

async function loadAmounts() {
  const node = props.node
  if (!node) return
  amountsLoading.value = true
  try {
    const res = await getNodeAmounts(props.projectId, node.node_key, props.year)
    amountRows.value = res?.rows || []
  } catch {
    amountRows.value = []
  } finally {
    amountsLoading.value = false
  }
}

async function loadAccounts() {
  try {
    const res = await getWorksheetAccounts(props.projectId, props.year)
    accounts.value = res?.accounts || []
  } catch {
    accounts.value = []
  }
}

function adjustmentNet(row: NodeAmountRow): string { return signedNet(row, 'adjustment') }
function eliminationNet(row: NodeAmountRow): string { return signedNet(row, 'elimination') }

// ─── 新增 / 修改（表单组件与明细表共用）──────────────────────────────────────
const formVisible = ref(false)
const editingEntry = ref<EliminationEntry | null>(null)
/** 归属固定为本节点（合并差额 ⇒ null，母分差额 ⇒ 该企业代码） */
const panelTargets = computed(() => (props.node ? [elimTargetOf(props.node)] : []))

function openCreate() {
  editingEntry.value = null
  formVisible.value = true
}

function openEdit(row: EliminationEntry) {
  editingEntry.value = row
  formVisible.value = true
}

async function onSaved() {
  await reload()
  emit('changed')
}

// ─── 删除草稿 / 提交审批 / 审批 / 驳回 / 撤销审批 ─────────────────────────────
async function removeEntry(row: EliminationEntry) {
  try {
    await confirmDelete(`分录 ${row.entry_no}`)
  } catch {
    return
  }
  try {
    await deleteElimination(row.id, props.projectId)
    ElMessage.success('分录已删除')
    await reload()
    emit('changed')
  } catch {
    /* 由 http 拦截器提示 */
  }
}

async function act(row: EliminationEntry, action: 'submit' | 'approve') {
  try {
    await reviewElimination(row.id, props.projectId, { action })
    ElMessage.success(action === 'submit' ? '已提交审批' : '已审批，合并数将自动重算')
    await reload()
    emit('changed')
  } catch {
    /* 由 http 拦截器提示（如归属节点已不在企业树中） */
  }
}

/** 撤销审批：已审批 → 草稿；推送后合并数回到审批前（合并锁定时后端 423 拒绝，由拦截器提示） */
async function revokeEntry(row: EliminationEntry) {
  try {
    await confirmDangerous({
      title: '撤销审批',
      message: `撤销分录 ${row.entry_no} 的审批？撤销后分录回到草稿，合并试算、报表与附注将重新推送。`,
      confirmText: '撤销审批',
    })
  } catch {
    return
  }
  try {
    await reviewElimination(row.id, props.projectId, { action: 'revoke' })
    ElMessage.success('已撤销审批，合并数将自动重算')
    await reload()
    emit('changed')
  } catch {
    /* 由 http 拦截器提示（如合并已锁定） */
  }
}

async function rejectEntry(row: EliminationEntry) {
  let reason = ''
  try {
    reason = await promptRejectReason(`分录 ${row.entry_no}`)
  } catch {
    return
  }
  try {
    await reviewElimination(row.id, props.projectId, { action: 'reject', rejection_reason: reason || undefined })
    ElMessage.success('已驳回')
    await reload()
    emit('changed')
  } catch {
    /* 由 http 拦截器提示 */
  }
}

function goHost() {
  const pid = props.node?.host_project_id
  if (!pid) return
  emit('update:modelValue', false)
  router.push({ path: `/projects/${pid}/consolidation`, query: props.year ? { year: String(props.year) } : undefined })
}

defineExpose({ reload })
</script>

<style scoped>
.elim-panel { display: flex; flex-direction: column; gap: 10px; }
.elim-panel-hint { margin: 0; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.elim-panel-toolbar { display: flex; align-items: center; gap: 8px; }
.elim-panel-count { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.elim-panel-section-title {
  margin-top: 6px; font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-primary);
}
</style>
