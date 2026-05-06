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

    <!-- 关联方注册表 -->
    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <div class="eqcr-tab__section-header">
          <div>
            <span class="eqcr-tab__section-title">关联方注册</span>
            <el-tag size="small" type="info" effect="plain">
              共 {{ summary.registry_count }} 家
            </el-tag>
          </div>
          <el-button
            v-if="canWrite"
            type="primary"
            size="small"
            @click="openRegistryDialog(null)"
          >
            + 新增关联方
          </el-button>
        </div>
      </template>

      <el-empty
        v-if="!loading && registries.length === 0"
        description="该项目尚未登记关联方"
        :image-size="60"
      />

      <el-table
        v-else
        :data="registries"
        size="small"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column prop="name" label="关联方名称" min-width="220" />
        <el-table-column prop="relation_type" label="关系类型" width="160">
          <template #default="{ row }">
            {{ RELATION_TYPE_LABELS[row.relation_type] || row.relation_type }}
          </template>
        </el-table-column>
        <el-table-column label="同一控制" width="110">
          <template #default="{ row }">
            <el-tag
              v-if="row.is_controlled_by_same_party"
              type="warning"
              size="small"
              effect="light"
            >
              是
            </el-tag>
            <span v-else class="eqcr-muted">否</span>
          </template>
        </el-table-column>
        <el-table-column label="登记时间" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column v-if="canWrite" label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openRegistryDialog(row)">
              编辑
            </el-button>
            <el-button size="small" link type="danger" @click="confirmDeleteRegistry(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 关联方交易表 -->
    <el-card shadow="never" class="eqcr-tab__section">
      <template #header>
        <div class="eqcr-tab__section-header">
          <div>
            <span class="eqcr-tab__section-title">关联方交易</span>
            <el-tag size="small" type="info" effect="plain">
              共 {{ summary.transaction_count }} 笔
            </el-tag>
          </div>
          <el-button
            v-if="canWrite && registries.length > 0"
            type="primary"
            size="small"
            @click="openTxnDialog(null)"
          >
            + 新增交易
          </el-button>
        </div>
      </template>

      <el-empty
        v-if="!loading && transactions.length === 0"
        description="该项目尚未登记关联方交易"
        :image-size="60"
      />

      <el-table
        v-else
        :data="transactions"
        size="small"
        border
        stripe
        style="width: 100%"
      >
        <el-table-column label="关联方" min-width="220">
          <template #default="{ row }">
            {{ registryName(row.related_party_id) }}
          </template>
        </el-table-column>
        <el-table-column label="交易类型" width="140">
          <template #default="{ row }">
            {{ TXN_TYPE_LABELS[row.transaction_type] || row.transaction_type }}
          </template>
        </el-table-column>
        <el-table-column label="金额" width="180" align="right">
          <template #default="{ row }">
            {{ formatAmount(row.amount) }}
          </template>
        </el-table-column>
        <el-table-column label="是否公允" width="110">
          <template #default="{ row }">
            <el-tag
              v-if="row.is_arms_length === true"
              type="success"
              size="small"
              effect="light"
            >
              公允
            </el-tag>
            <el-tag
              v-else-if="row.is_arms_length === false"
              type="danger"
              size="small"
              effect="light"
            >
              非公允
            </el-tag>
            <span v-else class="eqcr-muted">未评</span>
          </template>
        </el-table-column>
        <el-table-column label="证据引用" min-width="200">
          <template #default="{ row }">
            <span v-if="!row.evidence_refs" class="eqcr-muted">—</span>
            <span v-else>{{ renderEvidence(row.evidence_refs) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="canWrite" label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openTxnDialog(row)">
              编辑
            </el-button>
            <el-button size="small" link type="danger" @click="confirmDeleteTxn(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

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

    <!-- 关联方注册弹窗 -->
    <el-dialog
      v-model="registryDialogVisible"
      :title="editingRegistry ? '编辑关联方' : '新增关联方'"
      width="500px"
      destroy-on-close
    >
      <el-form
        ref="registryFormRef"
        :model="registryForm"
        :rules="registryRules"
        label-width="100px"
      >
        <el-form-item label="名称" prop="name">
          <el-input v-model="registryForm.name" placeholder="请输入关联方名称" maxlength="200" />
        </el-form-item>
        <el-form-item label="关系类型" prop="relation_type">
          <el-select v-model="registryForm.relation_type" placeholder="请选择" style="width: 100%">
            <el-option
              v-for="opt in RELATION_TYPE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="同一控制">
          <el-switch v-model="registryForm.is_controlled_by_same_party" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="registryDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitRegistry">
          确定
        </el-button>
      </template>
    </el-dialog>

    <!-- 关联方交易弹窗 -->
    <el-dialog
      v-model="txnDialogVisible"
      :title="editingTxn ? '编辑交易' : '新增交易'"
      width="560px"
      destroy-on-close
    >
      <el-form
        ref="txnFormRef"
        :model="txnForm"
        :rules="txnRules"
        label-width="100px"
      >
        <el-form-item label="关联方" prop="related_party_id">
          <el-select v-model="txnForm.related_party_id" placeholder="请选择关联方" style="width: 100%">
            <el-option
              v-for="r in registries"
              :key="r.id"
              :label="r.name"
              :value="r.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="交易类型" prop="transaction_type">
          <el-select v-model="txnForm.transaction_type" placeholder="请选择" style="width: 100%">
            <el-option
              v-for="opt in TXN_TYPE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="金额" prop="amount">
          <el-input v-model="txnForm.amount" placeholder="请输入金额" />
        </el-form-item>
        <el-form-item label="是否公允">
          <el-radio-group v-model="txnForm.is_arms_length_str">
            <el-radio value="true">公允</el-radio>
            <el-radio value="false">非公允</el-radio>
            <el-radio value="null">未评</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="证据引用">
          <el-input
            v-model="txnForm.evidence_refs_text"
            type="textarea"
            :rows="2"
            placeholder="多条用逗号分隔"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="txnDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitTxn">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import {
  eqcrApi,
  type EqcrDomainPayload,
  type EqcrOpinion,
  type EqcrRelatedPartyData,
  type EqcrRelatedPartyRegistry,
  type EqcrRelatedPartyTransaction,
} from '@/services/eqcrService'
import EqcrOpinionForm from './EqcrOpinionForm.vue'

const props = defineProps<{
  projectId: string
  /** 是否可写（由父组件根据用户角色决定），默认 false（只读） */
  canWrite?: boolean
}>()

// ─── 常量 ──────────────────────────────────────────────────────────────────

const RELATION_TYPE_OPTIONS = [
  { value: 'parent', label: '母公司' },
  { value: 'subsidiary', label: '子公司' },
  { value: 'associate', label: '联营企业' },
  { value: 'joint_venture', label: '合营企业' },
  { value: 'key_management', label: '关键管理人员' },
  { value: 'family_member', label: '家庭成员' },
  { value: 'other', label: '其他' },
]

const RELATION_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  RELATION_TYPE_OPTIONS.map((o) => [o.value, o.label]),
)

const TXN_TYPE_OPTIONS = [
  { value: 'sales', label: '销售' },
  { value: 'purchase', label: '采购' },
  { value: 'loan', label: '借款' },
  { value: 'guarantee', label: '担保' },
  { value: 'service', label: '服务' },
  { value: 'asset_transfer', label: '资产转让' },
  { value: 'other', label: '其他' },
]

const TXN_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  TXN_TYPE_OPTIONS.map((o) => [o.value, o.label]),
)

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
const summary = computed(
  () =>
    payload.value?.data.summary ?? {
      registry_count: 0,
      transaction_count: 0,
    },
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

function registryName(id: string): string {
  return registryNameMap.value[id] ?? '（已删除）'
}

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
const registryFormRef = ref<FormInstance>()
const registryForm = reactive({
  name: '',
  relation_type: '',
  is_controlled_by_same_party: false,
})

const registryRules: FormRules = {
  name: [{ required: true, message: '请输入关联方名称', trigger: 'blur' }],
  relation_type: [{ required: true, message: '请选择关系类型', trigger: 'change' }],
}

function openRegistryDialog(row: EqcrRelatedPartyRegistry | null) {
  editingRegistry.value = row
  if (row) {
    registryForm.name = row.name
    registryForm.relation_type = row.relation_type || ''
    registryForm.is_controlled_by_same_party = row.is_controlled_by_same_party
  } else {
    registryForm.name = ''
    registryForm.relation_type = ''
    registryForm.is_controlled_by_same_party = false
  }
  registryDialogVisible.value = true
}

async function submitRegistry() {
  const formEl = registryFormRef.value
  if (!formEl) return
  const valid = await formEl.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    if (editingRegistry.value) {
      await eqcrApi.updateRelatedParty(props.projectId, editingRegistry.value.id, {
        name: registryForm.name,
        relation_type: registryForm.relation_type,
        is_controlled_by_same_party: registryForm.is_controlled_by_same_party,
      })
      ElMessage.success('关联方已更新')
    } else {
      await eqcrApi.createRelatedParty(props.projectId, {
        name: registryForm.name,
        relation_type: registryForm.relation_type,
        is_controlled_by_same_party: registryForm.is_controlled_by_same_party,
      })
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
    await ElMessageBox.confirm(
      `确定删除关联方「${row.name}」？相关交易记录不会自动删除。`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
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
const txnFormRef = ref<FormInstance>()
const txnForm = reactive({
  related_party_id: '',
  transaction_type: '',
  amount: '',
  is_arms_length_str: 'null' as string,
  evidence_refs_text: '',
})

const amountValidator = (_rule: any, value: string, callback: any) => {
  if (value && value.trim() !== '' && isNaN(Number(value))) {
    callback(new Error('金额必须为数字'))
  } else {
    callback()
  }
}

const txnRules: FormRules = {
  related_party_id: [{ required: true, message: '请选择关联方', trigger: 'change' }],
  transaction_type: [{ required: true, message: '请选择交易类型', trigger: 'change' }],
  amount: [{ validator: amountValidator, trigger: 'blur' }],
}

function openTxnDialog(row: EqcrRelatedPartyTransaction | null) {
  editingTxn.value = row
  if (row) {
    txnForm.related_party_id = row.related_party_id
    txnForm.transaction_type = row.transaction_type || ''
    txnForm.amount = row.amount ?? ''
    txnForm.is_arms_length_str =
      row.is_arms_length === true ? 'true' : row.is_arms_length === false ? 'false' : 'null'
    txnForm.evidence_refs_text = Array.isArray(row.evidence_refs)
      ? row.evidence_refs.join('、')
      : row.evidence_refs
        ? String(row.evidence_refs)
        : ''
  } else {
    txnForm.related_party_id = ''
    txnForm.transaction_type = ''
    txnForm.amount = ''
    txnForm.is_arms_length_str = 'null'
    txnForm.evidence_refs_text = ''
  }
  txnDialogVisible.value = true
}

function parseEvidenceRefs(text: string): string[] | null {
  if (!text.trim()) return null
  return text
    .split(/[,，、]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

async function submitTxn() {
  const formEl = txnFormRef.value
  if (!formEl) return
  const valid = await formEl.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const evidenceRefs = parseEvidenceRefs(txnForm.evidence_refs_text)
    const amountVal = txnForm.amount.trim() === '' ? null : txnForm.amount.trim()
    const isArmsLength =
      txnForm.is_arms_length_str === 'true' ? true
        : txnForm.is_arms_length_str === 'false' ? false
          : null

    if (editingTxn.value) {
      await eqcrApi.updateTransaction(props.projectId, editingTxn.value.id, {
        related_party_id: txnForm.related_party_id,
        transaction_type: txnForm.transaction_type,
        amount: amountVal,
        is_arms_length: isArmsLength,
        evidence_refs: evidenceRefs,
      })
      ElMessage.success('交易已更新')
    } else {
      await eqcrApi.createTransaction(props.projectId, {
        related_party_id: txnForm.related_party_id,
        transaction_type: txnForm.transaction_type,
        amount: amountVal,
        is_arms_length: isArmsLength,
        evidence_refs: evidenceRefs,
      })
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
  const partyName = registryName(row.related_party_id)
  try {
    await ElMessageBox.confirm(
      `确定删除「${partyName}」的交易记录（${TXN_TYPE_LABELS[row.transaction_type || ''] || row.transaction_type}）？`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
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

// ─── 辅助 ──────────────────────────────────────────────────────────────────

function formatAmount(value: string | null): string {
  if (value === null || value === undefined || value === '') return '—'
  const num = Number(value)
  if (Number.isNaN(num)) return value
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

function renderEvidence(refs: any): string {
  if (Array.isArray(refs)) {
    return refs.length === 0 ? '—' : refs.join('、')
  }
  if (typeof refs === 'string') return refs
  try {
    return JSON.stringify(refs)
  } catch {
    return '—'
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
.eqcr-tab__section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.eqcr-tab__section-title {
  font-weight: 600;
  color: var(--gt-color-text, #303133);
  margin-right: 10px;
}
.eqcr-muted {
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
