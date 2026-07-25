<template>
  <div class="gt-confirmation-hub gt-fade-in">
    <div class="gt-hub-header">
      <div class="gt-hub-header__title">
        <h2>函证管理</h2>
        <span class="gt-hub-header__count">共 {{ confirmations.length }} 项</span>
      </div>
      <div class="gt-hub-header__actions">
        <el-button size="small" plain @click="openImport()">
          <el-icon class="gt-btn-icon"><Download /></el-icon>从底稿导入
        </el-button>
        <el-button type="primary" size="small" @click="openCreate()">
          <el-icon class="gt-btn-icon"><Plus /></el-icon>新建函证
        </el-button>
      </div>
    </div>

    <!-- 函证清单表格 -->
    <el-card shadow="never" class="gt-hub-card">
      <el-table
        :data="confirmations"
        size="small"
        style="width:100%"
        v-loading="loading"
        :header-cell-style="{ background: '#f7f8fa', color: '#606266', fontWeight: '600' }"
      >
        <el-table-column prop="counterparty" label="函证对象" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="gt-cp-name">{{ row.counterparty }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="confirm_type" label="类型" width="90">
          <template #default="{ row }">
            <el-tag :type="typeTagType(row.confirm_type)" size="small" effect="light" round>
              {{ typeLabel(row.confirm_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="96">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" effect="light" round>
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="账面金额" width="140" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.book_amount" /></template>
        </el-table-column>
        <el-table-column label="回函金额" width="140" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.confirmed_amount" /></template>
        </el-table-column>
        <el-table-column label="差异" width="130" align="right">
          <template #default="{ row }">
            <GtAmountCell v-if="row.diff_amount != null" :value="row.diff_amount" />
            <span v-else class="gt-text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="关联底稿" width="110" align="center">
          <template #default="{ row }">
            <el-button v-if="row.wp_id" link type="primary" size="small" @click.stop="gotoWp(row.wp_id)">查看</el-button>
            <span v-else class="gt-text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="188" fixed="right">
          <template #default="{ row }">
            <div class="gt-row-actions">
              <el-button
                v-if="nextStatus(row.status) || row.status === 'returned'"
                link type="primary" size="small" @click="doTransition(row)"
              >{{ transitionLabel(row.status) }}</el-button>
              <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" size="small" @click="onDelete(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <div class="gt-hub-empty">
            <el-empty description="暂无函证" :image-size="90">
              <el-button type="primary" size="small" plain @click="openImport()">从底稿导入</el-button>
            </el-empty>
          </div>
        </template>
      </el-table>
    </el-card>

    <!-- 新建/编辑弹窗 -->
    <el-dialog
      v-model="showFormDialog"
      :title="editRow ? '编辑函证' : '新建函证'"
      width="500px"
      append-to-body
    >
      <el-form :model="form" label-width="100px">
        <el-form-item label="函证类型" prop="confirm_type" required>
          <el-select v-model="form.confirm_type" placeholder="请选择类型">
            <el-option label="应收" value="receivable" />
            <el-option label="应付" value="payable" />
            <el-option label="银行" value="bank" />
            <el-option label="借款" value="loan" />
          </el-select>
        </el-form-item>
        <el-form-item label="函证对象" prop="counterparty" required>
          <el-input v-model="form.counterparty" placeholder="请输入函证对象名称" />
        </el-form-item>
        <el-form-item label="科目编码">
          <el-input v-model="form.account_code" placeholder="关联 TB 科目编码（可选）" />
        </el-form-item>
        <el-form-item label="账面金额">
          <el-input-number v-model="form.book_amount" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="回函金额">
          <el-input-number v-model="form.confirmed_amount" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="差异金额">
          <el-input-number v-model="form.diff_amount" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="差异说明">
          <el-input v-model="form.diff_note" type="textarea" :rows="2" placeholder="差异原因说明" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showFormDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <!-- 从底稿导入弹窗 -->
    <el-dialog
      v-model="showImportDialog"
      title="从底稿导入函证对象"
      width="720px"
      append-to-body
    >
      <div class="gt-import-toolbar">
        <span class="gt-import-toolbar__label">函证类型</span>
        <el-select v-model="importType" size="small" style="width:160px" @change="loadCandidates">
          <el-option label="银行（货币资金）" value="bank" />
          <el-option label="应收" value="receivable" />
          <el-option label="应付" value="payable" />
          <el-option label="借款" value="loan" />
        </el-select>
        <span class="gt-import-hint">
          从辅助余额表按核算维度提取候选，勾选后一键批量创建（已存在的自动跳过）
        </span>
      </div>

      <el-table
        ref="candidateTableRef"
        :data="candidates"
        border
        size="small"
        height="360"
        v-loading="candidatesLoading"
        @selection-change="onCandidateSelect"
      >
        <el-table-column type="selection" width="44" :selectable="isCandidateSelectable" />
        <el-table-column prop="counterparty" label="函证对象" min-width="220" show-overflow-tooltip />
        <el-table-column prop="account_code" label="科目" width="90" />
        <el-table-column label="账面金额" width="150" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.book_amount" /></template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="isExisting(row)" type="info" size="small">已存在</el-tag>
            <el-tag v-else type="success" size="small" effect="plain">可导入</el-tag>
          </template>
        </el-table-column>
        <template #empty>
          <span class="gt-text-muted">该类型底稿暂无可提取的函证对象（请确认已导入辅助余额表）</span>
        </template>
      </el-table>

      <template #footer>
        <span class="gt-import-count">已选 {{ selectedCandidates.length }} 项</span>
        <el-button @click="showImportDialog = false">取消</el-button>
        <el-button
          type="primary"
          :loading="importing"
          :disabled="selectedCandidates.length === 0"
          @click="handleImport"
        >导入选中</el-button>
      </template>
    </el-dialog>

    <!-- returned 状态选择弹窗（相符/差异） -->
    <el-dialog v-model="showReturnedChoice" title="回函结果" width="360px" append-to-body>
      <p>请选择回函结果：</p>
      <div class="gt-confirmation-hub__choice">
        <el-button type="success" @click="doReturnedTransition('matched')">相符（无差异）</el-button>
        <el-button type="warning" @click="doReturnedTransition('discrepancy')">差异</el-button>
      </div>
      <template #footer>
        <el-button @click="showReturnedChoice = false">取消</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download, Plus } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import { confirmDelete } from '@/utils/confirm'
import { eventBus } from '@/utils/eventBus'
import { useProjectStore } from '@/stores/project'
import GtAmountCell from '@/components/common/GtAmountCell.vue'

// ─── 数据 ───

interface ConfirmationItem {
  id: string
  confirm_type: string
  counterparty: string
  status: string
  book_amount: number | null
  confirmed_amount: number | null
  diff_amount: number | null
  diff_note: string | null
  account_code: string | null
  wp_id: string | null
}

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const projectId = computed(() => projectStore.projectId || (route.params.projectId as string) || '')

const loading = ref(false)
const confirmations = ref<ConfirmationItem[]>([])

// ─── 表单 ───

const showFormDialog = ref(false)
const editRow = ref<ConfirmationItem | null>(null)

const emptyForm = () => ({
  confirm_type: '',
  counterparty: '',
  account_code: '',
  book_amount: null as number | null,
  confirmed_amount: null as number | null,
  diff_amount: null as number | null,
  diff_note: '',
})
const form = ref(emptyForm())

// ─── returned 选择 ───

const showReturnedChoice = ref(false)
const returnedRow = ref<ConfirmationItem | null>(null)

// ─── 从底稿导入 ───

interface CandidateItem {
  confirm_type: string
  counterparty: string
  account_code: string | null
  book_amount: number | null
}

const showImportDialog = ref(false)
const importType = ref<'bank' | 'receivable' | 'payable' | 'loan'>('bank')
const candidates = ref<CandidateItem[]>([])
const candidatesLoading = ref(false)
const selectedCandidates = ref<CandidateItem[]>([])
const importing = ref(false)
const candidateTableRef = ref<any>(null)

// 已存在集合（counterparty+type 归一），用于跳过与禁选
const existingKeys = computed<Set<string>>(() => {
  const s = new Set<string>()
  for (const c of confirmations.value) {
    s.add(`${(c.counterparty || '').trim().toLowerCase()}::${c.confirm_type}`)
  }
  return s
})

function isExisting(row: CandidateItem): boolean {
  return existingKeys.value.has(`${(row.counterparty || '').trim().toLowerCase()}::${row.confirm_type}`)
}

function isCandidateSelectable(row: CandidateItem): boolean {
  return !isExisting(row)
}

function onCandidateSelect(rows: CandidateItem[]) {
  selectedCandidates.value = rows
}

function openImport() {
  showImportDialog.value = true
  importType.value = 'bank'
  loadCandidates()
}

async function loadCandidates() {
  candidatesLoading.value = true
  candidates.value = []
  selectedCandidates.value = []
  try {
    const res = await api.get(
      `/api/projects/${projectId.value}/confirmations/candidates`,
      { params: { confirm_type: importType.value } } as any,
    )
    candidates.value = res.items ?? []
    // 默认勾选所有「可导入」（未存在）行
    nextTick(() => {
      candidates.value.forEach((row) => {
        if (!isExisting(row)) candidateTableRef.value?.toggleRowSelection(row, true)
      })
    })
  } catch (e) {
    handleApiError(e, '加载底稿候选')
  } finally {
    candidatesLoading.value = false
  }
}

async function handleImport() {
  if (selectedCandidates.value.length === 0) return
  importing.value = true
  try {
    const items = selectedCandidates.value.map((c) => ({
      confirm_type: c.confirm_type,
      counterparty: c.counterparty,
      account_code: c.account_code || undefined,
      book_amount: c.book_amount,
    }))
    const res: any = await api.post(
      `/api/projects/${projectId.value}/confirmations/batch-sync`,
      { items },
    )
    const created = res?.created ?? 0
    const updated = res?.updated ?? 0
    ElMessage.success(`导入完成：新增 ${created} 条${updated ? `，更新 ${updated} 条` : ''}`)
    showImportDialog.value = false
    await fetchList()
  } catch (e) {
    handleApiError(e, '批量导入函证')
  } finally {
    importing.value = false
  }
}

// ─── 枚举映射 ───

const TYPE_LABELS: Record<string, string> = {
  receivable: '应收',
  payable: '应付',
  bank: '银行',
  loan: '借款',
}

const STATUS_LABELS: Record<string, string> = {
  pending: '待发函',
  sent: '已发函',
  returned: '已回函',
  matched: '相符',
  discrepancy: '差异',
}

function typeLabel(t: string): string {
  return TYPE_LABELS[t] || t
}

function typeTagType(t: string): 'success' | 'warning' | 'info' | 'danger' | 'primary' | undefined {
  const map: Record<string, 'success' | 'warning' | 'info' | 'danger' | 'primary' | undefined> = {
    bank: 'primary',
    receivable: 'success',
    payable: 'warning',
    loan: 'danger',
  }
  return map[t]
}

function statusLabel(s: string): string {
  return STATUS_LABELS[s] || s
}

function statusTagType(s: string): 'success' | 'warning' | 'info' | 'danger' | undefined {
  const map: Record<string, 'success' | 'warning' | 'info' | 'danger' | undefined> = {
    pending: 'info',
    sent: 'warning',
    returned: undefined,
    matched: 'success',
    discrepancy: 'danger',
  }
  return map[s]
}

// ─── 状态推进逻辑 ───

function nextStatus(status: string): string | null {
  const map: Record<string, string | null> = {
    pending: 'sent',
    sent: 'returned',
    returned: null, // 特殊处理：需选相符/差异
    matched: null,
    discrepancy: null,
  }
  return map[status] ?? null
}

function transitionLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '发函',
    sent: '登记回函',
    returned: '确认结果',
  }
  return map[status] || '推进'
}

async function doTransition(row: ConfirmationItem) {
  if (row.status === 'returned') {
    // 已回函 → 需选相符/差异
    returnedRow.value = row
    showReturnedChoice.value = true
    return
  }
  const target = nextStatus(row.status)
  if (!target) return
  await executeTransition(row, target)
}

async function doReturnedTransition(target: 'matched' | 'discrepancy') {
  if (!returnedRow.value) return
  await executeTransition(returnedRow.value, target)
  showReturnedChoice.value = false
  returnedRow.value = null
}

async function executeTransition(row: ConfirmationItem, target: string) {
  try {
    await api.post(`/api/projects/${projectId.value}/confirmations/${row.id}/transition`, {
      target_status: target,
    })
    // 回函终态（已回函/相符/差异）→ emit eventBus，统一驱动下游刷新（摘要卡/底稿）。
    // 后端 transition 端点会从记录 wp_id 反查 wp_code 触发 CONFIRMATION_RECEIVED 下游 stale，
    // 前端此事件仅负责客户端刷新，两条链触发点在终态对齐（G1/G2）。
    if (target === 'returned' || target === 'matched' || target === 'discrepancy') {
      eventBus.emit('confirmation:received', {
        projectId: projectId.value,
        confirmationId: row.id,
        accountCode: row.account_code || undefined,
      })
    }
    ElMessage.success('状态更新成功')
    await fetchList()
  } catch (e) {
    handleApiError(e, '状态推进')
  }
}

// ─── CRUD ───

async function fetchList() {
  loading.value = true
  try {
    const res = await api.get(`/api/projects/${projectId.value}/confirmations`)
    confirmations.value = res.items ?? []
  } catch (e) {
    handleApiError(e, '获取函证列表')
  } finally {
    loading.value = false
  }
}

function openEdit(row: ConfirmationItem) {
  editRow.value = row
  form.value = {
    confirm_type: row.confirm_type,
    counterparty: row.counterparty,
    account_code: row.account_code || '',
    book_amount: row.book_amount,
    confirmed_amount: row.confirmed_amount,
    diff_amount: row.diff_amount,
    diff_note: row.diff_note || '',
  }
  showFormDialog.value = true
}

function openCreate() {
  editRow.value = null
  form.value = emptyForm()
  showFormDialog.value = true
}

async function handleSubmit() {
  if (!form.value.confirm_type || !form.value.counterparty) {
    ElMessage.warning('请填写必填项（类型和函证对象）')
    return
  }
  try {
    if (editRow.value) {
      await api.put(`/api/projects/${projectId.value}/confirmations/${editRow.value.id}`, form.value)
      ElMessage.success('更新成功')
    } else {
      await api.post(`/api/projects/${projectId.value}/confirmations`, form.value)
      ElMessage.success('创建成功')
    }
    showFormDialog.value = false
    await fetchList()
  } catch (e) {
    handleApiError(e, editRow.value ? '更新函证' : '创建函证')
  }
}

async function onDelete(row: ConfirmationItem) {
  try {
    await confirmDelete({ name: `函证「${row.counterparty}」` })
  } catch {
    return // 用户取消
  }
  try {
    await api.delete(`/api/projects/${projectId.value}/confirmations/${row.id}`)
    ElMessage.success('删除成功')
    await fetchList()
  } catch (e) {
    handleApiError(e, '删除函证')
  }
}

// ─── 生命周期 ───

function gotoWp(wpId: string) {
  router.push(`/projects/${projectId.value}/workpapers/${wpId}`)
}

onMounted(() => {
  fetchList()
})
</script>

<style scoped>
.gt-confirmation-hub {
  padding: var(--gt-space-4);
  font-size: 13px;
}

.gt-hub-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.gt-hub-header__title {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.gt-hub-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--gt-color-text-primary, #1a1a1a);
  position: relative;
  padding-left: 11px;
}
.gt-hub-header h2::before {
  content: '';
  position: absolute;
  left: 0; top: 50%;
  transform: translateY(-50%);
  width: 4px; height: 16px;
  border-radius: 2px;
  background: var(--gt-color-primary, #4b2d77);
}
.gt-hub-header__count {
  font-size: 13px;
  color: var(--gt-color-text-tertiary, #909399);
}
.gt-hub-header__actions {
  display: flex;
  gap: 8px;
}
.gt-btn-icon { margin-right: 3px; vertical-align: -1px; }

/* 表格卡片：无边框 + 圆角 + 贴边 */
.gt-hub-card {
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  border-radius: 8px;
  overflow: hidden;
}
.gt-hub-card :deep(.el-card__body) { padding: 0; }
.gt-hub-card :deep(.el-table) { font-size: 13px; }
.gt-hub-card :deep(.el-table th.el-table__cell) { font-size: 13px; }
.gt-hub-card :deep(.el-table .cell) { line-height: 1.5; }
.gt-hub-card :deep(.el-table td.el-table__cell) { padding: 9px 0; }

.gt-cp-name { color: var(--gt-color-text-primary, #303133); }

.gt-row-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: nowrap;
}
.gt-row-actions :deep(.el-button) { padding: 0; height: auto; }

.gt-hub-empty { padding: 28px 0; }

.gt-link {
  color: var(--gt-purple, #4b2d77);
  cursor: pointer;
  font-size: 13px;
}
.gt-link:hover { text-decoration: underline; }
.gt-text-muted { color: var(--gt-color-text-tertiary, #c0c4cc); font-size: 13px; }

.gt-confirmation-hub__choice {
  display: flex;
  gap: 16px;
  justify-content: center;
  margin: 16px 0;
}

.gt-hub-header__actions {
  display: flex;
  gap: 8px;
}

.gt-import-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.gt-import-toolbar__label {
  font-size: 13px;
  color: var(--gt-color-text-secondary, #606266);
}
.gt-import-hint {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}
.gt-import-count {
  margin-right: auto;
  font-size: 13px;
  color: var(--gt-color-text-secondary, #606266);
}
</style>
