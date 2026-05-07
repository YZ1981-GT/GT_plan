<template>
  <div v-loading="loading" class="eqcr-tab">
    <el-alert
      v-if="!canWrite"
      :closable="false"
      type="info"
      show-icon
      title="EQCR 视角为只读"
      description="关联方注册与交易录入由项目经理负责，EQCR 仅就数据与意见判断。"
    />

    <!-- 关联方注册表（子组件） -->
    <EqcrRelatedPartyTable
      :registries="registries"
      :can-write="canWrite"
      @add="openRegistryDialog(null)"
      @edit="openRegistryDialog"
      @delete="confirmDeleteRegistry"
    />

    <!-- 关联方交易表（子组件） -->
    <EqcrRelatedPartyTxnTable
      :transactions="transactions"
      :can-write="canWrite"
      :has-registries="registries.length > 0"
      :registry-name-map="registryNameMap"
      @add="openTxnDialog(null)"
      @edit="openTxnDialog"
      @delete="confirmDeleteTxn"
    />

    <!-- EQCR 复核意见 -->
    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <span class="eqcr-tab__section-title">EQCR 复核意见</span>
      </template>
      <EqcrOpinionForm
        :project-id="projectId"
        domain="related_party"
        :current-opinion="currentOpinion"
        :history-opinions="historyOpinions"
        @saved="onOpinionSaved"
      />
    </el-card>

    <!-- 关联方注册弹窗（子组件） -->
    <EqcrRelatedPartyFormDialog
      v-model="registryDialogVisible"
      :editing="editingRegistry"
      :saving="saving"
      @submit="submitRegistry"
    />

    <!-- 关联方交易弹窗（子组件） -->
    <EqcrRelatedPartyTxnFormDialog
      v-model="txnDialogVisible"
      :editing="editingTxn"
      :registries="registries"
      :saving="saving"
      @submit="submitTxn"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmDelete } from '@/utils/confirm'
import {
  eqcrApi,
  type EqcrDomainPayload,
  type EqcrOpinion,
  type EqcrRelatedPartyData,
  type EqcrRelatedPartyRegistry,
  type EqcrRelatedPartyTransaction,
} from '@/services/eqcrService'
import EqcrOpinionForm from './EqcrOpinionForm.vue'
import EqcrRelatedPartyTable from './EqcrRelatedPartyTable.vue'
import EqcrRelatedPartyTxnTable from './EqcrRelatedPartyTxnTable.vue'
import EqcrRelatedPartyFormDialog from './EqcrRelatedPartyFormDialog.vue'
import EqcrRelatedPartyTxnFormDialog from './EqcrRelatedPartyTxnFormDialog.vue'

const props = defineProps<{
  projectId: string
  /** 是否可写（由父组件根据用户角色决定），默认 false（只读） */
  canWrite?: boolean
}>()

// ─── 状态 ──────────────────────────────────────────────────────────────────

const loading = ref(false)
const saving = ref(false)
const payload = ref<EqcrDomainPayload<EqcrRelatedPartyData> | null>(null)

const canWrite = computed(() => props.canWrite ?? false)

const registries = computed<EqcrRelatedPartyRegistry[]>(
  () => payload.value?.data.registries ?? [],
)
const transactions = computed<EqcrRelatedPartyTransaction[]>(
  () => payload.value?.data.transactions ?? [],
)
const currentOpinion = computed<EqcrOpinion | null>(
  () => payload.value?.current_opinion ?? null,
)
const historyOpinions = computed<EqcrOpinion[]>(
  () => payload.value?.history_opinions ?? [],
)

const registryNameMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const r of registries.value) {
    map[r.id] = r.name
  }
  return map
})

// ─── 数据加载 ──────────────────────────────────────────────────────────────

async function load() {
  loading.value = true
  try {
    payload.value = await eqcrApi.getRelatedParties(props.projectId)
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '加载关联方数据失败')
    payload.value = null
  } finally {
    loading.value = false
  }
}

function onOpinionSaved(_: EqcrOpinion) {
  load()
}

onMounted(load)

// ─── 关联方注册 CRUD ──────────────────────────────────────────────────────

const registryDialogVisible = ref(false)
const editingRegistry = ref<EqcrRelatedPartyRegistry | null>(null)

function openRegistryDialog(row: EqcrRelatedPartyRegistry | null) {
  editingRegistry.value = row
  registryDialogVisible.value = true
}

async function submitRegistry(form: { name: string; relation_type: string; is_controlled_by_same_party: boolean }) {
  saving.value = true
  try {
    if (editingRegistry.value) {
      await eqcrApi.updateRelatedParty(props.projectId, editingRegistry.value.id, form)
      ElMessage.success('关联方已更新')
    } else {
      await eqcrApi.createRelatedParty(props.projectId, form)
      ElMessage.success('关联方已创建')
    }
    registryDialogVisible.value = false
    await load()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    saving.value = false
  }
}

async function confirmDeleteRegistry(row: EqcrRelatedPartyRegistry) {
  try {
    await confirmDelete('关联方「' + row.name + '」')
  } catch {
    return
  }
  try {
    await eqcrApi.deleteRelatedParty(props.projectId, row.id)
    ElMessage.success('已删除')
    await load()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '删除失败')
  }
}

// ─── 关联方交易 CRUD ──────────────────────────────────────────────────────

const txnDialogVisible = ref(false)
const editingTxn = ref<EqcrRelatedPartyTransaction | null>(null)

function openTxnDialog(row: EqcrRelatedPartyTransaction | null) {
  editingTxn.value = row
  txnDialogVisible.value = true
}

async function submitTxn(form: {
  related_party_id: string
  transaction_type: string
  amount: string | null
  is_arms_length: boolean | null
  evidence_refs: string[] | null
}) {
  saving.value = true
  try {
    if (editingTxn.value) {
      await eqcrApi.updateTransaction(props.projectId, editingTxn.value.id, form)
      ElMessage.success('交易已更新')
    } else {
      await eqcrApi.createTransaction(props.projectId, form)
      ElMessage.success('交易已创建')
    }
    txnDialogVisible.value = false
    await load()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '操作失败')
  } finally {
    saving.value = false
  }
}

async function confirmDeleteTxn(row: EqcrRelatedPartyTransaction) {
  const partyName = registryNameMap.value[row.related_party_id] ?? '（已删除）'
  try {
    await confirmDelete('「' + partyName + '」的交易记录')
  } catch {
    return
  }
  try {
    await eqcrApi.deleteTransaction(props.projectId, row.id)
    ElMessage.success('已删除')
    await load()
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '删除失败')
  }
}
</script>

<style scoped>
.eqcr-tab {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.eqcr-tab__section {
  border-radius: var(--gt-radius-md, 6px);
}
.eqcr-tab__section-title {
  font-weight: 600;
  color: var(--gt-color-text, #303133);
  margin-right: 10px;
}
</style>
