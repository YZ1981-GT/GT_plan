<script setup lang="ts">
/**
 * GtB22BDeficiencyEvaluation — B22B 内部控制缺陷评价表
 *
 * 单列滚动布局：缺陷卡片列表 + 整体评价结论区 + 复核区
 *
 * Spec: .kiro/specs/b22b-deficiency-evaluation/
 * Tasks: 3.1 ~ 3.9, 4.1
 */
import { ref, computed, toRef, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useB22BFormData } from './composables/useB22BFormData'
import {
  useB22BDeficiency,
  suggestSeverity,
  compareMateriality,
  SEVERITY_LEVELS,
  DEFICIENCY_CATEGORIES,
  FINANCIAL_STATEMENT_ITEMS,
  SEVERITY_COLOR_MAP,
  type SeverityLevel,
  type DeficiencyCategory,
  type FinancialStatementItem,
  type DeficiencyChangePayload,
} from './composables/useB22BDeficiency'
import { useB22BReview } from './composables/useB22BReview'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'

// ─── Props / Emits (Task 3.1) ────────────────────────────────────────────────

interface Props {
  wpId: string
  projectId: string
  wpCode: string
  year: number
  readonly?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── Composables 初始化 (Task 3.1) ──────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')
const externalReadonly = toRef(props, 'readonly')

const {
  allResponses,
  loading,
  saving,
  materialityLevel,
  loadAll,
  loadMaterialityLevel,
  saveImmediate,
  saveDebouncedText,
  getField,
  setFieldImmediate,
} = useB22BFormData(wpIdRef, projectIdRef)

const {
  deficiencyItems,
  eliminatedItems,
  syncFromEvent,
  loadFromB22A,
  setCategory,
  setAffectedAccounts,
  setPotentialMisstatement,
  setCompensatingControl,
  setCorrectiveAction,
  setSeverity,
  setSeverityOverride,
  overallConclusion,
  severityStats,
  allEvaluated,
  showAuditImpactWarning,
  overallNote,
  publishSeverityEvent,
} = useB22BDeficiency(allResponses, materialityLevel, saveImmediate)

const {
  isReviewed,
  isReadonly,
  canReview,
  pendingItems,
  reviewInfo,
  doReview,
  startAmendment,
} = useB22BReview(wpIdRef, allResponses, allEvaluated, deficiencyItems, externalReadonly, saveImmediate)

// ─── Local state ─────────────────────────────────────────────────────────────

const showEliminatedHistory = ref(false)
const overrideDialogVisible = ref(false)
const overrideDialogIndex = ref(-1)
const overrideDialogSeverity = ref<SeverityLevel>('一般缺陷')
const overrideDialogReason = ref('')
const amendmentDialogVisible = ref(false)
const amendmentReason = ref('')
const manualMaterialityInput = ref<number | null>(null)

// ─── Computed helpers ────────────────────────────────────────────────────────

/** 有效重要性水平（B15 > 手动输入） */
const effectiveMateriality = computed(() => {
  return materialityLevel.value ?? manualMaterialityInput.value
})

/** 获取系统建议严重程度 */
function getSuggestedSeverity(index: number): SeverityLevel | null {
  const item = deficiencyItems.value[index]
  if (!item) return null
  return suggestSeverity(
    item.potentialMisstatement,
    effectiveMateriality.value,
    item.hasCompensatingControl,
    item.hasCorrectiveAction
  )
}

/** 获取重要性水平对比结果 */
function getMaterialityComparison(amount: number | null) {
  if (amount === null) return null
  return compareMateriality(amount, effectiveMateriality.value)
}

// ─── Event handlers (Task 3.2 ~ 3.8) ────────────────────────────────────────

function handleCategoryChange(index: number, val: DeficiencyCategory) {
  if (isReadonly.value) return
  setCategory(index, val)
  emit('save')
}

function handleAccountsChange(index: number, val: FinancialStatementItem[]) {
  if (isReadonly.value) return
  setAffectedAccounts(index, val)
  emit('save')
}

function handleAmountChange(index: number, val: number | null) {
  if (isReadonly.value || val === null) return
  setPotentialMisstatement(index, val)
  emit('save')
}

function handleCompensatingChange(index: number, hasControl: boolean) {
  if (isReadonly.value) return
  const item = deficiencyItems.value[index]
  setCompensatingControl(index, hasControl, item?.compensatingControlDesc || '')
  emit('save')
}

function handleCompensatingDescChange(index: number, desc: string) {
  if (isReadonly.value) return
  const item = deficiencyItems.value[index]
  setCompensatingControl(index, item?.hasCompensatingControl ?? false, desc)
}

function handleCorrectiveChange(index: number, hasAction: boolean) {
  if (isReadonly.value) return
  const item = deficiencyItems.value[index]
  setCorrectiveAction(index, hasAction, item?.correctiveActionDesc || '')
  emit('save')
}

function handleCorrectiveDescChange(index: number, desc: string) {
  if (isReadonly.value) return
  const item = deficiencyItems.value[index]
  setCorrectiveAction(index, item?.hasCorrectiveAction ?? false, desc)
}

function handleSeverityChange(index: number, val: SeverityLevel) {
  if (isReadonly.value) return
  const suggested = getSuggestedSeverity(index)

  if (suggested && val !== suggested) {
    overrideDialogIndex.value = index
    overrideDialogSeverity.value = val
    overrideDialogReason.value = ''
    overrideDialogVisible.value = true
    return
  }

  setSeverity(index, val)
  emit('save')
}

function confirmOverride() {
  const reason = overrideDialogReason.value.trim()
  if (!reason) {
    ElMessage.warning('需填写调整理由')
    return
  }
  setSeverityOverride(overrideDialogIndex.value, overrideDialogSeverity.value, reason)
  overrideDialogVisible.value = false
  emit('save')
}

function handleOverallNoteChange(val: string) {
  if (isReadonly.value) return
  overallNote.value = val
  saveDebouncedText({ item_id: 'B22B-overall-note', conclusion: null, remark: val, wp_ref: null })
}

function handleManualMaterialityChange(val: number | null) {
  manualMaterialityInput.value = val
  if (val !== null) {
    setFieldImmediate('B22B-materiality-manual', { remark: String(val) })
  }
}

async function handleReview() {
  if (!canReview.value) return
  try {
    await ElMessageBox.confirm('确认完成复核签字？签字后全表将变为只读。', '复核确认', {
      confirmButtonText: '确认签字',
      cancelButtonText: '取消',
      type: 'info',
    })
    await doReview()
    emit('save')
    emit('completed')
    ElMessage.success('复核签字完成')
  } catch {
    // 用户取消
  }
}

function handleStartAmendment() {
  amendmentReason.value = ''
  amendmentDialogVisible.value = true
}

async function confirmAmendment() {
  const reason = amendmentReason.value.trim()
  if (!reason) {
    ElMessage.warning('修改原因不能为空')
    return
  }
  try {
    await startAmendment(reason)
    amendmentDialogVisible.value = false
    ElMessage.success('已解除复核锁定，可重新编辑')
  } catch (err: any) {
    ElMessage.error(err?.message || '修改申请失败')
  }
}

// ─── EventBus integration (Task 3.9) ────────────────────────────────────────

function onDeficiencyChanged(payload: any) {
  if (payload && (payload.added || payload.removed)) {
    syncFromEvent(payload as DeficiencyChangePayload)
  }
}

// ─── Lifecycle (Task 3.1) ────────────────────────────────────────────────────

onMounted(async () => {
  await loadAll()
  await loadMaterialityLevel()

  // 恢复手动输入重要性水平
  const manualItem = allResponses.value.get('B22B-materiality-manual')
  if (manualItem?.remark) {
    const parsed = parseFloat(manualItem.remark)
    if (!isNaN(parsed) && parsed > 0) {
      manualMaterialityInput.value = parsed
    }
  }

  // 从 B22A 加载现有缺陷
  try {
    const res = await api.get(`/api/projects/${props.projectId}/workpapers`, {
      params: { wp_code: 'B22A' },
    })
    const workpapers: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    if (workpapers.length > 0) {
      const b22aWpId = workpapers[0].id || workpapers[0].wp_id
      if (b22aWpId) {
        const b22aRes = await api.get(`/api/workpapers/${b22aWpId}/checklist-responses`)
        const b22aResponses: any[] = Array.isArray(b22aRes) ? b22aRes : (b22aRes?.data ?? [])
        loadFromB22A(b22aResponses)
      }
    }
  } catch {
    ElMessage.warning('缺陷来源加载失败，仅依赖已保存数据')
  }

  ;(eventBus as any).on('control:deficiency-changed', onDeficiencyChanged)
})

onBeforeUnmount(() => {
  ;(eventBus as any).off('control:deficiency-changed', onDeficiencyChanged)
})
</script>

<template>
  <div class="gt-b22b-deficiency-evaluation" v-loading="loading">
    <!-- 顶部状态横幅 (Task 3.7) -->
    <el-alert
      v-if="isReviewed && reviewInfo"
      type="success"
      :closable="false"
      show-icon
      class="b22b-review-banner"
    >
      <template #title>
        已复核 — {{ reviewInfo.reviewer }} ({{ reviewInfo.date }})
      </template>
    </el-alert>

    <el-alert
      v-if="showAuditImpactWarning"
      type="error"
      :closable="false"
      show-icon
      class="b22b-audit-warning"
    >
      <template #title>
        ⚠️ {{ overallConclusion }} — 影响审计报告意见类型，需与业务合伙人沟通
      </template>
    </el-alert>

    <!-- 重要性水平对比区 (Task 3.6) -->
    <el-card class="b22b-materiality-card" shadow="never">
      <template #header>
        <span class="card-title">重要性水平</span>
      </template>
      <div class="materiality-content">
        <div v-if="materialityLevel !== null" class="materiality-info">
          <el-tag type="info">B15 自动读取</el-tag>
          <span class="materiality-value">{{ materialityLevel.toLocaleString() }} 元</span>
        </div>
        <div v-else class="materiality-manual">
          <el-tag type="warning">请先完成 B15 重要性水平确定</el-tag>
          <el-input-number
            v-model="manualMaterialityInput"
            :disabled="isReadonly"
            :min="0"
            :precision="2"
            placeholder="手动输入重要性水平（元）"
            style="width: 240px; margin-left: 12px"
            @change="handleManualMaterialityChange"
          />
        </div>
      </div>
    </el-card>

    <!-- 缺陷列表区 (Task 3.2 ~ 3.4) -->
    <div v-if="deficiencyItems.length === 0 && !loading" class="b22b-empty">
      <el-empty description="暂无控制缺陷条目（来自 B22A）" />
    </div>

    <el-card
      v-for="(item, index) in deficiencyItems"
      :key="`def-${index}`"
      class="b22b-deficiency-card"
      shadow="hover"
      :body-style="{ padding: '16px' }"
    >
      <template #header>
        <div class="deficiency-card-header">
          <span class="deficiency-index">缺陷 {{ index + 1 }}</span>
          <el-tag
            v-if="item.severity"
            :style="{
              backgroundColor: SEVERITY_COLOR_MAP[item.severity].bg,
              color: SEVERITY_COLOR_MAP[item.severity].text,
              border: 'none',
            }"
          >
            {{ item.severity }}
            <span v-if="item.severityOverridden" style="font-size: 11px">（已手动调整）</span>
          </el-tag>
        </div>
      </template>

      <!-- 来源信息（只读） -->
      <div class="source-info">
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="所属要素">
            {{ item.source.elementName }}
          </el-descriptions-item>
          <el-descriptions-item label="控制要点">
            {{ item.source.controlPoint || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="缺陷类型">
            <el-tag size="small" type="danger">{{ item.source.deficiencyType }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 缺陷分类 -->
      <el-form-item label="缺陷分类" class="b22b-form-item">
        <el-select
          :model-value="item.category"
          :disabled="isReadonly"
          placeholder="选择分类"
          style="width: 160px"
          @change="(val: DeficiencyCategory) => handleCategoryChange(index, val)"
        >
          <el-option v-for="cat in DEFICIENCY_CATEGORIES" :key="cat" :label="cat" :value="cat" />
        </el-select>
      </el-form-item>

      <!-- 4 维度评价区 (Task 3.3) -->
      <el-divider content-position="left">多维度评价</el-divider>

      <!-- 维度 1: 影响报表项目 -->
      <el-form-item label="可能影响的报表项目范围" class="b22b-form-item">
        <el-select
          :model-value="item.affectedAccounts"
          :disabled="isReadonly"
          multiple
          placeholder="选择报表项目"
          style="width: 360px"
          @change="(val: FinancialStatementItem[]) => handleAccountsChange(index, val)"
        >
          <el-option v-for="acc in FINANCIAL_STATEMENT_ITEMS" :key="acc" :label="acc" :value="acc" />
        </el-select>
      </el-form-item>

      <!-- 维度 2: 潜在错报金额 + 重要性对比 -->
      <el-form-item label="潜在错报金额（元）" class="b22b-form-item">
        <div class="amount-row">
          <el-input-number
            :model-value="item.potentialMisstatement"
            :disabled="isReadonly"
            :min="0"
            :precision="2"
            placeholder="输入金额"
            style="width: 200px"
            @change="(val: number | null) => handleAmountChange(index, val)"
          />
          <span
            v-if="getMaterialityComparison(item.potentialMisstatement)"
            class="materiality-comparison"
            :style="{ color: getMaterialityComparison(item.potentialMisstatement)!.color === 'red' ? '#DC2626' : '#059669' }"
          >
            <template v-if="getMaterialityComparison(item.potentialMisstatement)!.exceeds">
              ↑ 超过重要性水平
              <span v-if="getMaterialityComparison(item.potentialMisstatement)!.difference !== null">
                （超出 {{ getMaterialityComparison(item.potentialMisstatement)!.difference!.toLocaleString() }} 元）
              </span>
            </template>
            <template v-else>✓ 未超过重要性水平</template>
          </span>
        </div>
      </el-form-item>

      <!-- 维度 3: 补偿性控制 -->
      <el-form-item label="是否存在补偿性控制" class="b22b-form-item">
        <el-radio-group
          :model-value="item.hasCompensatingControl"
          :disabled="isReadonly"
          @change="(val: boolean) => handleCompensatingChange(index, val)"
        >
          <el-radio :value="true">是</el-radio>
          <el-radio :value="false">否</el-radio>
        </el-radio-group>
        <el-input
          v-if="item.hasCompensatingControl"
          :model-value="item.compensatingControlDesc"
          :disabled="isReadonly"
          type="textarea"
          :rows="2"
          placeholder="描述补偿性控制"
          style="margin-top: 8px"
          @input="(val: string) => handleCompensatingDescChange(index, val)"
        />
      </el-form-item>

      <!-- 维度 4: 纠正措施 -->
      <el-form-item label="是否已采取纠正措施" class="b22b-form-item">
        <el-radio-group
          :model-value="item.hasCorrectiveAction"
          :disabled="isReadonly"
          @change="(val: boolean) => handleCorrectiveChange(index, val)"
        >
          <el-radio :value="true">是</el-radio>
          <el-radio :value="false">否</el-radio>
        </el-radio-group>
        <el-input
          v-if="item.hasCorrectiveAction"
          :model-value="item.correctiveActionDesc"
          :disabled="isReadonly"
          type="textarea"
          :rows="2"
          placeholder="描述纠正措施"
          style="margin-top: 8px"
          @input="(val: string) => handleCorrectiveDescChange(index, val)"
        />
      </el-form-item>

      <!-- 严重程度评定区 (Task 3.4) -->
      <el-divider content-position="left">严重程度评定</el-divider>

      <div class="severity-section">
        <div v-if="getSuggestedSeverity(index)" class="severity-suggestion">
          <el-tag type="info" size="small">系统建议</el-tag>
          <span class="suggestion-text">{{ getSuggestedSeverity(index) }}</span>
        </div>

        <el-form-item label="严重程度" class="b22b-form-item">
          <el-select
            :model-value="item.severity"
            :disabled="isReadonly"
            placeholder="评定严重程度"
            style="width: 180px"
            @change="(val: SeverityLevel) => handleSeverityChange(index, val)"
          >
            <el-option v-for="sev in SEVERITY_LEVELS" :key="sev" :label="sev" :value="sev" />
          </el-select>
          <el-tag v-if="item.severityOverridden" type="warning" size="small" style="margin-left: 8px">
            已手动调整
          </el-tag>
        </el-form-item>

        <div v-if="item.severityOverridden && item.overrideReason" class="override-reason">
          <span class="override-label">调整理由：</span>{{ item.overrideReason }}
        </div>
      </div>
    </el-card>

    <!-- 已消除缺陷历史区 (Task 3.2) -->
    <el-card v-if="eliminatedItems.length > 0" class="b22b-eliminated-card" shadow="never">
      <template #header>
        <div class="eliminated-header" @click="showEliminatedHistory = !showEliminatedHistory">
          <span>已消除缺陷历史（{{ eliminatedItems.length }} 项）</span>
          <el-icon><component :is="showEliminatedHistory ? 'ArrowUp' : 'ArrowDown'" /></el-icon>
        </div>
      </template>
      <div v-show="showEliminatedHistory">
        <div v-for="(elItem, idx) in eliminatedItems" :key="`elim-${idx}`" class="eliminated-item">
          <el-tag type="info" size="small">已消除</el-tag>
          <span class="eliminated-text">
            {{ elItem.source.elementName }} — {{ elItem.source.controlPoint || '无控制要点' }}
          </span>
        </div>
      </div>
    </el-card>

    <!-- 整体评价结论区 (Task 3.5) -->
    <el-card class="b22b-conclusion-card" shadow="never">
      <template #header>
        <span class="card-title">整体评价结论</span>
      </template>

      <div class="conclusion-content">
        <div class="conclusion-main">
          <span class="conclusion-label">评价结论：</span>
          <el-tag
            :type="overallConclusion === '未发现控制缺陷' ? 'success' : overallConclusion.includes('重大') ? 'danger' : overallConclusion.includes('重要') ? 'warning' : 'info'"
            size="large"
          >
            {{ overallConclusion }}
          </el-tag>
        </div>

        <div class="severity-stats">
          <el-tag type="danger" size="small">重大 {{ severityStats.material }} 项</el-tag>
          <el-tag type="warning" size="small">重要 {{ severityStats.significant }} 项</el-tag>
          <el-tag type="success" size="small">一般 {{ severityStats.general }} 项</el-tag>
          <el-tag type="info" size="small">合计 {{ severityStats.total }} 项</el-tag>
        </div>
      </div>

      <el-form-item label="整体评价说明" class="b22b-form-item" style="margin-top: 16px">
        <el-input
          :model-value="overallNote"
          :disabled="isReadonly"
          type="textarea"
          :rows="3"
          placeholder="填写整体评价说明（可选）"
          @input="handleOverallNoteChange"
        />
      </el-form-item>
    </el-card>

    <!-- 现场经理复核区 (Task 3.7, 3.8) -->
    <el-card class="b22b-review-card" shadow="never">
      <template #header>
        <span class="card-title">现场经理复核</span>
      </template>

      <div v-if="pendingItems.length > 0" class="pending-items">
        <el-alert type="warning" :closable="false" show-icon>
          <template #title>待完成事项（{{ pendingItems.length }} 项）</template>
        </el-alert>
        <ul class="pending-list">
          <li v-for="(p, idx) in pendingItems" :key="idx">{{ p }}</li>
        </ul>
      </div>

      <div class="review-actions">
        <el-button
          v-if="!isReviewed"
          type="primary"
          :disabled="!canReview || isReadonly"
          @click="handleReview"
        >
          复核签字
        </el-button>

        <el-button
          v-if="isReviewed && !externalReadonly"
          type="warning"
          @click="handleStartAmendment"
        >
          申请修改（Amendment）
        </el-button>
      </div>
    </el-card>

    <!-- 手动覆盖对话框 (Task 3.4) -->
    <el-dialog v-model="overrideDialogVisible" title="调整严重程度" width="420px" :close-on-click-modal="false">
      <p>系统建议严重程度与您的选择不同，请填写调整理由：</p>
      <el-input v-model="overrideDialogReason" type="textarea" :rows="3" placeholder="填写调整理由（必填）" />
      <template #footer>
        <el-button @click="overrideDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmOverride">确认调整</el-button>
      </template>
    </el-dialog>

    <!-- Amendment 对话框 (Task 3.8) -->
    <el-dialog v-model="amendmentDialogVisible" title="申请修改" width="420px" :close-on-click-modal="false">
      <p>复核后修改需填写修改原因，修改后需重新复核签字。</p>
      <el-input v-model="amendmentReason" type="textarea" :rows="3" placeholder="填写修改原因（必填）" />
      <template #footer>
        <el-button @click="amendmentDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAmendment">确认修改</el-button>
      </template>
    </el-dialog>

    <!-- 保存状态提示 -->
    <div v-if="saving" class="b22b-saving-indicator">
      <el-tag type="info" size="small">保存中...</el-tag>
    </div>
  </div>
</template>

<style scoped>
.gt-b22b-deficiency-evaluation {
  padding: 16px;
  max-width: 1200px;
  margin: 0 auto;
}

.b22b-review-banner,
.b22b-audit-warning {
  margin-bottom: 12px;
}

.b22b-materiality-card {
  margin-bottom: 16px;
}

.card-title {
  font-weight: 600;
  font-size: 15px;
}

.materiality-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.materiality-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.materiality-value {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.materiality-manual {
  display: flex;
  align-items: center;
}

.b22b-empty {
  margin: 40px 0;
}

.b22b-deficiency-card {
  margin-bottom: 16px;
}

.deficiency-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.deficiency-index {
  font-weight: 600;
  font-size: 14px;
}

.source-info {
  margin-bottom: 12px;
}

.b22b-form-item {
  margin-bottom: 12px;
}

.amount-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.materiality-comparison {
  font-size: 13px;
  font-weight: 500;
}

.severity-section {
  padding: 8px 0;
}

.severity-suggestion {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.suggestion-text {
  font-size: 13px;
  color: #606266;
}

.override-reason {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
  background: #fdf6ec;
  padding: 4px 8px;
  border-radius: 4px;
}

.override-label {
  font-weight: 500;
}

.b22b-eliminated-card {
  margin-bottom: 16px;
}

.eliminated-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  user-select: none;
}

.eliminated-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
}

.eliminated-item:last-child {
  border-bottom: none;
}

.eliminated-text {
  font-size: 13px;
  color: #909399;
}

.b22b-conclusion-card {
  margin-bottom: 16px;
}

.conclusion-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.conclusion-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.conclusion-label {
  font-weight: 500;
}

.severity-stats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.b22b-review-card {
  margin-bottom: 16px;
}

.pending-items {
  margin-bottom: 12px;
}

.pending-list {
  margin: 8px 0 0 20px;
  padding: 0;
  font-size: 13px;
  color: #606266;
}

.pending-list li {
  margin-bottom: 4px;
}

.review-actions {
  display: flex;
  gap: 12px;
}

.b22b-saving-indicator {
  position: fixed;
  bottom: 16px;
  right: 16px;
  z-index: 100;
}

/* ─── Print Styles (Task 4.1) ─────────────────────────────────────────────── */
@media print {
  .gt-b22b-deficiency-evaluation {
    padding: 0;
    max-width: none;
  }

  @page {
    size: A4 landscape;
    margin: 10mm;
  }

  * {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
    color-adjust: exact !important;
  }

  .el-button,
  .el-input,
  .el-input-number,
  .el-select,
  .el-radio-group,
  .el-dialog,
  .b22b-saving-indicator,
  .review-actions,
  .pending-items {
    display: none !important;
  }

  .b22b-deficiency-card {
    break-inside: avoid;
    margin-bottom: 8px;
    border: 1px solid #ddd;
  }

  .b22b-conclusion-card {
    break-inside: avoid;
  }

  .b22b-review-card {
    display: none !important;
  }

  .b22b-materiality-card .materiality-manual .el-input-number {
    display: none !important;
  }
}
</style>
