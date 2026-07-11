<!--
  K1TabOverdueCheck.vue — K1-10 长期未收回款项检查

  列表型检查: 合规/不合规/不适用 tri-state + 审计证据 + 不合规红色摘要
  行级抽凭 📎 + AI辅助 per-section

  Spec: .kiro/specs/k1-other-receivables/ Task 4.6
  Requirements: 8.2, 8.5, 8.6
-->
<template>
  <div class="k1-tab-overdue-check">
    <!-- 方法论上下文（琥珀色） -->
    <div class="methodology-context">
      <p>K1-10长期未收回款项检查表用于识别和评估长期挂账的其他应收款项目。重点关注：
        ①账龄超过1年未收回原因 ②管理层催收措施 ③可回收性评估 ④是否需计提减值或核销。
        长期未收回款项可能暗示信用风险显著增加。</p>
    </div>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K1-10 长期未收回款项检查</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate('K1-10')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleAddItem">＋ 新增</el-button>
        <el-button size="small" @click="handleReview('K1-10-check')">💬 复核</el-button>
      </div>
    </div>

    <!-- 检查表格 -->
    <el-table :data="sectionItems" border size="small" class="check-table" :row-style="checkRowStyle">
      <el-table-column type="index" label="#" width="40" align="center" />

      <el-table-column label="检查项目" min-width="200">
        <template #default="{ row }">
          <span>{{ row.label }}</span>
          <p v-if="row.description" class="item-desc">{{ row.description }}</p>
        </template>
      </el-table-column>

      <el-table-column label="合规判定" width="130" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.compliance" size="small"
            placeholder="请选择" clearable
            @change="(v: string) => handleComplianceChange(row.id, v)">
            <el-option label="合规" value="合规" />
            <el-option label="不合规" value="不合规" />
            <el-option label="不适用" value="不适用" />
          </el-select>
          <el-tag v-else :type="complianceTagType(row.compliance)" size="small">
            {{ row.compliance || '未判定' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="审计证据" min-width="180">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
            :model-value="row.evidence" size="small" placeholder="审计证据/说明"
            @change="(v: string) => handleEvidenceChange(row.id, v)" />
          <span v-else>{{ row.evidence || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="📎" width="50" align="center">
        <template #default="{ row }">
          <el-button size="small" link @click="handleAttach(row.id)">📎</el-button>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleRemoveItem(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 不合规红色摘要 -->
    <div v-if="nonComplianceItems.length > 0" class="non-compliance-summary">
      <div class="ncs-header">⚠️ 不合规项摘要（{{ nonComplianceItems.length }} 项）</div>
      <ul class="ncs-list">
        <li v-for="item in nonComplianceItems" :key="item.id">
          <b>{{ item.label }}</b>：{{ item.evidence || '未说明' }}
        </li>
      </ul>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>关注账龄1年以上的款项，检查是否有合理的商业理由持续挂账</li>
        <li>核查管理层催收记录（函件/电话/法律措施）</li>
        <li>评估可回收性时考虑：债务人财务状况、担保物、账龄、行业环境</li>
        <li>长期未收回→可能信用风险显著增加→ECL Stage升级→K1-7联动</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabOverdueCheck.vue — K1-10 长期未收回款项检查
 * Spec: .kiro/specs/k1-other-receivables/ | Task: 4.6
 * Requirements: 8.2, 8.5, 8.6
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK1Checks, type K1CheckItem, type ComplianceState } from '../../composables/useK1Checks'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ (e: 'save', itemId: string, value: any): void }>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)
const { sections, loadSections, updateItemCompliance, updateItemEvidence, addItem, removeItem, serializeSection } =
  useK1Checks({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId), allResponses: allResponsesRef as any })

const SECTION_ID = 'K1-10'

const sectionItems = computed(() => {
  const section = sections.value.find(s => s.sectionId === SECTION_ID)
  return section?.items ?? []
})

const nonComplianceItems = computed(() =>
  sectionItems.value.filter(i => i.compliance === '不合规')
)

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadSections()
  if (sectionItems.value.length === 0) initDefaultItems()
})

function initDefaultItems() {
  const defaults = [
    '长期挂账原因是否合理（业务实质/合同约定）',
    '管理层是否采取有效催收措施',
    '催收记录是否完整（函件/电话/法律）',
    '债务人当前财务状况和偿债能力',
    '是否存在担保/抵押物并核实现值',
    '可回收性评估是否充分（减值迹象识别）',
    '是否需上调ECL阶段（Stage升级）',
    '相关减值计提是否充分',
  ]
  for (const label of defaults) { addItem(SECTION_ID, label) }
  persistSection()
}

// ─── 操作 ────────────────────────────────────────────────────────────────────

function handleComplianceChange(itemId: string, value: string) {
  updateItemCompliance(SECTION_ID, itemId, (value || null) as ComplianceState)
  persistSection()
}

function handleEvidenceChange(itemId: string, value: string) {
  updateItemEvidence(SECTION_ID, itemId, value)
  persistSection()
}

async function handleAddItem() {
  try {
    const { value } = await ElMessageBox.prompt('请输入检查项名称', '新增检查项',
      { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (!value?.trim()) { ElMessage.warning('名称不能为空'); return }
    addItem(SECTION_ID, value.trim())
    persistSection()
  } catch { /* cancelled */ }
}

function handleRemoveItem(id: string) { removeItem(SECTION_ID, id); persistSection() }

function persistSection() {
  const itemId = `${SECTION_ID}-check-items`
  const data = serializeSection(SECTION_ID)
  const payload = { item_id: itemId, conclusion: null, remark: data }
  props.allResponses.set(itemId, payload)
  emit('save', itemId, { remark: data })
}

function handleAttach(itemId: string) { console.log('[K1-10] Attach voucher for:', itemId) }

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function complianceTagType(val: string | null): 'success' | 'danger' | 'info' | 'warning' {
  if (val === '合规') return 'success'
  if (val === '不合规') return 'danger'
  if (val === '不适用') return 'info'
  return 'warning'
}

function checkRowStyle({ row }: { row: K1CheckItem }): Record<string, string> {
  if (row.compliance === '不合规') return { 'background-color': '#fef2f2' }
  return {}
}

function handleAiGenerate(section: string) { console.log('[K1-10] AI generate:', section) }
function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.k1-tab-overdue-check { padding: 16px; font-size: 13px; }

.methodology-context {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb; padding: 10px 14px; margin-bottom: 16px;
  font-size: 12px; color: var(--el-text-color-regular); line-height: 1.6;
}

.section-head {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;
}
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }

.check-table { font-size: 13px; }
.item-desc { font-size: 11px; color: var(--el-text-color-secondary); margin: 4px 0 0; }

.non-compliance-summary {
  margin-top: 16px; padding: 12px; border-radius: 6px;
  background: #fef2f2; border: 1px solid #fecaca;
}
.ncs-header { font-weight: 600; color: var(--el-color-danger); margin-bottom: 8px; }
.ncs-list { padding-left: 20px; margin: 0; line-height: 1.8; color: var(--el-color-danger-dark-2); }

.compile-hint {
  margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary);
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
