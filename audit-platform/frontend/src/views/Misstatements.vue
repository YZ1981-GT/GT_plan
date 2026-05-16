<template>
  <div class="gt-misstatements gt-fade-in" :class="{ 'gt-fullscreen': isFullscreen }">
    <!-- 页面横幅 [R7-S3-01] -->
    <GtPageHeader title="未更正错报汇总" @back="router.push('/projects')">
      <GtInfoBar
        :show-unit="true"
        :show-year="true"
        :unit-value="selectedProjectId"
        :year-value="selectedYear"
        :badges="[{ value: '累计错报 vs 重要性水平' }]"
        @unit-change="onProjectChange"
        @year-change="onYearChange"
      />
      <template #actions>
        <GtToolbar>
          <template #left>
            <el-button size="small" type="primary" @click="openCreateDialog">+ 新增错报</el-button>
            <el-button size="small" plain @click="toggleFullscreen">{{ isFullscreen ? '退出全屏' : '全屏' }}</el-button>
          </template>
        </GtToolbar>
      </template>
    </GtPageHeader>

    <!-- 重要性水平对比卡片 -->
    <div class="gt-ms-materiality-cards" v-if="summary">
      <div class="gt-ms-mat-card">
        <span class="gt-ms-mat-label">累计错报金额</span>
        <span class="gt-ms-mat-value" :class="{ 'gt-ms-exceeded': summary.exceeds_materiality }">
          {{ fmtAmt(summary.cumulative_amount) }}
        </span>
      </div>
      <div class="gt-ms-mat-card">
        <span class="gt-ms-mat-label">整体重要性</span>
        <span class="gt-ms-mat-value">{{ fmtAmt(summary.overall_materiality) }}</span>
      </div>
      <div class="gt-ms-mat-card">
        <span class="gt-ms-mat-label">实际执行重要性</span>
        <span class="gt-ms-mat-value">{{ fmtAmt(summary.performance_materiality) }}</span>
      </div>
      <div class="gt-ms-mat-card">
        <span class="gt-ms-mat-label">微小错报临界值</span>
        <span class="gt-ms-mat-value">{{ fmtAmt(summary.trivial_threshold) }}</span>
      </div>
      <div class="gt-ms-mat-card">
        <span class="gt-ms-mat-label">评价完整性</span>
        <span class="gt-ms-mat-value" :class="summary.evaluation_complete ? 'gt-ms-complete' : 'gt-ms-incomplete'">
          {{ summary.evaluation_complete ? '✓ 完整' : '✗ 不完整' }}
        </span>
      </div>
    </div>

    <!-- 超限预警横幅 -->
    <el-alert v-if="summary?.exceeds_materiality" type="error" :closable="false"
      class="gt-ms-threshold-warning" show-icon>
      未更正错报累计金额({{ fmtAmt(summary.cumulative_amount) }})已达到或超过整体重要性水平({{ fmtAmt(summary.overall_materiality) }})，可能需要出具保留意见或否定意见
    </el-alert>

    <!-- 按类型分组小计 -->
    <div class="gt-ms-type-summary" v-if="summary?.by_type?.length">
      <el-table :data="summary.by_type" border size="small" style="margin-bottom: 16px">
        <el-table-column label="错报类型" width="150">
          <template #default="{ row }">
            <el-tag :type="(typeTagType(row.misstatement_type)) || undefined" size="small">
              {{ typeLabel(row.misstatement_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="count" label="数量" width="80" align="center" />
        <el-table-column label="小计金额" align="right">
          <template #default="{ row }">{{ fmtAmt(row.total_amount) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 错报列表 -->
    <el-alert
      v-if="!loading && items.length === 0"
      type="info" show-icon :closable="false" style="margin-bottom: 12px"
    >
      <template #title>暂无未更正错报</template>
      <div style="font-size: var(--gt-font-size-xs); line-height: 1.6">
        点击"新增"手动录入，或在调整分录页面驳回 AJE 时自动生成。累计金额超过重要性水平时系统会预警。
      </div>
    </el-alert>
    <el-table
      ref="msTableRef"
      :data="items"
      v-loading="loading"
      border
      stripe
      style="width: 100%"
      @cell-contextmenu="onCellContextMenu"
    >
      <el-table-column prop="misstatement_description" label="错报描述" min-width="200" show-overflow-tooltip />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">
          <el-tag :type="(typeTagType(row.misstatement_type)) || undefined" size="small">
            {{ typeLabel(row.misstatement_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="affected_account_code" label="科目编码" width="120" />
      <el-table-column prop="affected_account_name" label="科目名称" width="140" show-overflow-tooltip />
      <el-table-column label="金额" width="130" align="right">
        <template #default="{ row }">
          <GtAmountCell :value="row.misstatement_amount" :clickable="true" @click="penetrate.toLedger(row.affected_account_code)" />
        </template>
      </el-table-column>
      <!-- Spec A R1：重要性变更时未重评估的错报标 stale -->
      <el-table-column label="新鲜度" width="80" align="center">
        <template #default="{ row }">
          <el-tooltip
            v-if="staleMissIdSet.has(row.id)"
            content="重要性已变更，建议重新评估"
            placement="top"
          >
            <el-tag type="warning" size="small" round>🟡</el-tag>
          </el-tooltip>
          <span v-else style="color: var(--gt-color-success); font-size: var(--gt-font-size-xs)">✓</span>
        </template>
      </el-table-column>
      <el-table-column label="结转" width="70" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.is_carried_forward" type="info" size="small">结转</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="management_reason" label="管理层原因" min-width="150" show-overflow-tooltip />
      <el-table-column prop="auditor_evaluation" label="审计师评价" min-width="150" show-overflow-tooltip />
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- R10 Spec B / F7：错报右键菜单 - 查看关联底稿 -->
    <CellContextMenu
      :visible="msCtx.contextMenu.visible"
      :x="msCtx.contextMenu.x"
      :y="msCtx.contextMenu.y"
      :item-name="msCtx.contextMenu.itemName"
    >
      <div class="gt-ucell-ctx-item" @click="onCtxRelatedWp">
        <span class="gt-ucell-ctx-icon">📝</span> 查看关联底稿
      </div>
    </CellContextMenu>

    <!-- 新建/编辑弹窗 -->
    <el-dialog append-to-body v-model="formVisible" :title="isEditing ? '编辑错报' : '新增错报'" width="600px" destroy-on-close>
      <el-form :model="form" label-width="100px">
        <el-form-item label="错报类型">
          <el-select v-model="form.misstatement_type" style="width: 100%">
            <el-option label="事实错报" value="factual" />
            <el-option label="判断错报" value="judgmental" />
            <el-option label="推断错报" value="projected" />
          </el-select>
        </el-form-item>
        <el-form-item label="错报描述">
          <el-input v-model="form.misstatement_description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="科目编码">
          <el-input v-model="form.affected_account_code" />
        </el-form-item>
        <el-form-item label="科目名称">
          <el-input v-model="form.affected_account_name" />
        </el-form-item>
        <el-form-item label="错报金额">
          <el-input-number v-model="form.misstatement_amount" :precision="2" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="管理层原因">
          <el-input v-model="form.management_reason" type="textarea" :rows="2" placeholder="管理层不调整的原因" />
        </el-form-item>
        <el-form-item label="审计师评价">
          <el-input v-model="form.auditor_evaluation" type="textarea" :rows="2" placeholder="审计师对管理层原因的评价" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" @click="onSubmit" :loading="submitLoading"
          :disabled="!form.misstatement_description || !form.misstatement_amount">
          {{ isEditing ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { confirmDelete } from '@/utils/confirm'
import { usePasteImport } from '@/composables/usePasteImport'
import { usePenetrate } from '@/composables/usePenetrate'
import { useFullscreen } from '@/composables/useFullscreen'
// R10 Spec B / F7：错报右键菜单
import { useCellSelection } from '@/composables/useCellSelection'
import CellContextMenu from '@/components/common/CellContextMenu.vue'
import { handleApiError } from '@/utils/errorHandler'
// Spec A R1：跨视图 stale 摘要（错报阈值变化时显示标志）
import { useStaleSummaryFull } from '@/composables/useStaleSummaryFull'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtInfoBar from '@/components/common/GtInfoBar.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import {
  listMisstatements, createMisstatement, updateMisstatement,
  deleteMisstatement, getMisstatementSummary,
  type MisstatementItem, type MisstatementSummaryData,
} from '@/services/auditPlatformApi'
import { useProjectSelector } from '@/composables/useProjectSelector'
import { fmtAmount } from '@/utils/formatters'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import GtAmountCell from '@/components/common/GtAmountCell.vue'

const route = useRoute()
const router = useRouter()
const penetrate = usePenetrate()
const { isFullscreen, toggleFullscreen } = useFullscreen()
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

// R10 Spec B / F7：错报单元格选中 + 右键菜单
const msCtx = useCellSelection()
let _ctxRow: any = null
function onCellContextMenu(row: any, _column: any, _cell: HTMLElement, event: MouseEvent) {
  _ctxRow = row
  msCtx.contextMenu.itemName = row.affected_account_name || row.misstatement_description || '错报'
  msCtx.openContextMenu(event, msCtx.contextMenu.itemName, row)
}
async function onCtxRelatedWp() {
  msCtx.closeContextMenu()
  const m = _ctxRow
  if (!m) return
  try {
    const data: any = await api.get(
      `/api/projects/${projectId.value}/misstatements/${m.id}/related-workpapers`,
    )
    const wps = data?.workpapers || []
    if (!wps.length) {
      ElMessage.info('该错报暂无关联底稿')
      return
    }
    if (wps.length === 1) {
      router.push({
        name: 'WorkpaperEditor',
        params: { projectId: projectId.value, wpId: wps[0].id },
      })
      return
    }
    const list = wps.map((w: any) => `${w.wp_code} ${w.wp_name}`).join('\n')
    ElMessage.info(`该错报关联 ${wps.length} 张底稿：\n${list}`)
  } catch (e: any) {
    handleApiError(e, '查看关联底稿')
  }
}

const {
  projectId, selectedProjectId, projectOptions, selectedYear, yearOptions,
  onProjectChange, onYearChange, loadProjectOptions, syncFromRoute,
} = useProjectSelector('misstatements')

// Spec A R1：跨视图 stale 摘要（misstatements 模块）
const { misstatements: missStaleSummary } = useStaleSummaryFull(projectId, year)
const staleMissIdSet = computed(() => new Set(missStaleSummary.value.items.map((it: any) => it.id)))

const loading = ref(false)
const submitLoading = ref(false)
const items = ref<MisstatementItem[]>([])
const summary = ref<MisstatementSummaryData | null>(null)

// R7 技术债 5：粘贴入库
const msTableRef = ref<HTMLElement | null>(null)
usePasteImport({
  containerRef: msTableRef,
  columns: [
    { key: 'misstatement_description', label: '错报描述' },
    { key: 'misstatement_type', label: '类型' },
    { key: 'affected_account_code', label: '科目编码' },
    { key: 'misstatement_amount', label: '金额' },
  ],
  onInsert: async (rows) => {
    for (const r of rows) {
      await createMisstatement(projectId.value, {
        misstatement_type: r.misstatement_type || 'factual',
        misstatement_description: r.misstatement_description || '',
        affected_account_code: r.affected_account_code || '',
        affected_account_name: '',
        misstatement_amount: String(parseFloat(r.misstatement_amount) || 0),
        year: year.value,
      })
    }
    fetchItems()
    fetchSummary()
  },
})

const formVisible = ref(false)
const isEditing = ref(false)
const editingId = ref('')
const form = ref({
  misstatement_type: 'factual',
  misstatement_description: '',
  affected_account_code: '',
  affected_account_name: '',
  misstatement_amount: 0,
  management_reason: '',
  auditor_evaluation: '',
})

const fmtAmt = fmtAmount

function typeLabel(t: string) {
  const m: Record<string, string> = { factual: '事实错报', judgmental: '判断错报', projected: '推断错报' }
  return m[t] || t
}

function typeTagType(t: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = { factual: 'danger', judgmental: 'warning', projected: 'info' }
  return m[t] || 'info'
}

async function fetchItems() {
  loading.value = true
  try {
    items.value = await listMisstatements(projectId.value, year.value)
  } finally {
    loading.value = false
  }
}

async function fetchSummary() {
  try {
    summary.value = await getMisstatementSummary(projectId.value, year.value)
  } catch { /* ignore */ }
}

function openCreateDialog() {
  isEditing.value = false
  editingId.value = ''
  form.value = {
    misstatement_type: 'factual',
    misstatement_description: '',
    affected_account_code: '',
    affected_account_name: '',
    misstatement_amount: 0,
    management_reason: '',
    auditor_evaluation: '',
  }
  formVisible.value = true
}

function openEditDialog(row: MisstatementItem) {
  isEditing.value = true
  editingId.value = row.id
  form.value = {
    misstatement_type: row.misstatement_type,
    misstatement_description: row.misstatement_description,
    affected_account_code: row.affected_account_code || '',
    affected_account_name: row.affected_account_name || '',
    misstatement_amount: parseFloat(String(row.misstatement_amount)) || 0,
    management_reason: row.management_reason || '',
    auditor_evaluation: row.auditor_evaluation || '',
  }
  formVisible.value = true
}

async function onSubmit() {
  submitLoading.value = true
  try {
    const body = {
      ...form.value,
      misstatement_amount: String(form.value.misstatement_amount),
    }
    if (isEditing.value) {
      await updateMisstatement(projectId.value, editingId.value, body)
      ElMessage.success('保存成功')
    } else {
      await createMisstatement(projectId.value, { ...body, year: year.value })
      ElMessage.success('创建成功')
    }
    formVisible.value = false
    fetchItems()
    fetchSummary()
  } finally {
    submitLoading.value = false
  }
}

async function onDelete(row: MisstatementItem) {
  await confirmDelete('该错报记录')
  await deleteMisstatement(projectId.value, row.id)
  ElMessage.success('删除成功')
  fetchItems()
  fetchSummary()
}

onMounted(() => {
  syncFromRoute()
  fetchItems()
  fetchSummary()
  loadProjectOptions()
  // R8-S2-13：订阅重要性变更事件，自动刷新阈值和列表
  eventBus.on('materiality:changed', onMaterialityChanged)
})

onUnmounted(() => {
  eventBus.off('materiality:changed', onMaterialityChanged)
})

async function onMaterialityChanged(payload: { projectId: string; year?: number }) {
  if (payload.projectId !== projectId.value) return
  // R8 复盘修正：除了重新拉列表，还要调后端 recheck-threshold 触发重新评估
  try {
    const { misstatements: P_ms } = await import('@/services/apiPaths')
    await api.post(P_ms.recheckThreshold(projectId.value) + `?year=${year.value}`)
  } catch { /* 后端端点异常不阻塞 UI 刷新 */ }
  await Promise.all([fetchItems(), fetchSummary()])
  ElMessage.info('重要性水平已变更，错报阈值已重新评估')
}
</script>

<style scoped>
.gt-misstatements { padding: var(--gt-space-5); }

/* ── 页面横幅 ── */
.gt-ms-banner {
  display: flex; flex-direction: column; gap: 10px;
  background: var(--gt-gradient-primary);
  border-radius: var(--gt-radius-lg);
  padding: 18px 28px;
  margin-bottom: var(--gt-space-5);
  color: var(--gt-color-text-inverse);
  position: relative; overflow: hidden;
  box-shadow: 0 4px 20px rgba(75, 45, 119, 0.2);
  background-image: var(--gt-gradient-primary), linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
  background-size: 100% 100%, 20px 20px, 20px 20px;
}
.gt-ms-banner::before {
  content: '';
  position: absolute; top: -40%; right: -10%;
  width: 45%; height: 180%;
  background: radial-gradient(ellipse, rgba(255,255,255,0.07) 0%, transparent 65%);
  pointer-events: none;
}
.gt-ms-banner-row1 {
  display: flex; align-items: center; gap: 16px;
  position: relative; z-index: 1;
}
.gt-ms-title { margin: 0; font-size: var(--gt-font-size-xl); font-weight: 700; white-space: nowrap; }
.gt-ms-info-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.gt-ms-info-item { display: flex; align-items: center; gap: 4px; }
.gt-ms-info-label { font-size: var(--gt-font-size-xs); opacity: 0.8; white-space: nowrap; }
.gt-ms-info-badge { font-size: var(--gt-font-size-xs); background: rgba(255,255,255,0.18); padding: 2px 10px; border-radius: 10px; white-space: nowrap; }
.gt-ms-info-sep { width: 1px; height: 16px; background: rgba(255,255,255,0.25); }
.gt-ms-unit-select, .gt-ms-year-select { width: 160px; }
.gt-ms-unit-select :deep(.el-input__wrapper),
.gt-ms-year-select :deep(.el-input__wrapper) {
  background: rgba(255,255,255,0.15) !important;
  border: 1px solid rgba(255,255,255,0.25) !important;
  box-shadow: none !important;
}
.gt-ms-unit-select :deep(.el-input__inner),
.gt-ms-year-select :deep(.el-input__inner) { color: var(--gt-color-text-inverse) !important; font-size: var(--gt-font-size-xs); }
.gt-ms-unit-select :deep(.el-input__suffix),
.gt-ms-year-select :deep(.el-input__suffix) { color: rgba(255,255,255,0.7) !important; }
.gt-ms-banner-row2 {
  display: flex; gap: 8px; align-items: center;
  position: relative; z-index: 1;
}
.gt-ms-banner-row2 .el-button { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); color: #fff; }
.gt-ms-banner-row2 .el-button:hover { background: rgba(255,255,255,0.25); }

.gt-ms-materiality-cards { display: flex; gap: var(--gt-space-3); margin-bottom: var(--gt-space-5); flex-wrap: wrap; }
.gt-ms-mat-card {
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  padding: var(--gt-space-4) var(--gt-space-5);
  box-shadow: var(--gt-shadow-sm); min-width: 150px; text-align: center;
  border: 1px solid rgba(75, 45, 119, 0.04);
  transition: all var(--gt-transition-base);
  position: relative; overflow: hidden;
}
.gt-ms-mat-card:hover { transform: translateY(-2px); box-shadow: var(--gt-shadow-md); }
.gt-ms-mat-card::after {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--gt-gradient-primary);
  opacity: 0;
  transition: opacity var(--gt-transition-fast);
}
.gt-ms-mat-card:hover::after { opacity: 1; }
.gt-ms-mat-label { display: block; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); font-weight: 500; }
.gt-ms-mat-value { display: block; font-size: var(--gt-font-size-xl); font-weight: 800; color: var(--gt-color-primary); margin-top: 4px; letter-spacing: -0.3px; }
.gt-ms-mat-value.gt-ms-exceeded { color: var(--gt-color-coral); }
.gt-ms-mat-value.gt-ms-complete { color: var(--gt-color-success); }
.gt-ms-mat-value.gt-ms-incomplete { color: var(--gt-color-coral); }
.gt-ms-threshold-warning { margin-bottom: var(--gt-space-4); }
.gt-ms-type-summary { margin-bottom: var(--gt-space-2); }
</style>
