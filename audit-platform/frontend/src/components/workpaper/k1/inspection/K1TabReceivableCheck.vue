<!-- K1TabReceivableCheck.vue — K1-12 其他应收款检查表 | Task 4.6 | Req 8.4-8.6 -->
<template>
  <div class="k1-tab-receivable-check">
    <!-- 方法论上下文（琥珀色） -->
    <div class="methodology-context">
      <p>K1-12其他应收款综合检查表对其他应收款科目进行全面合规性审查。涵盖：
        ①确认和计量的准确性 ②分类列报的恰当性 ③期后回款情况 ④减值评估的充分性
        ⑤信息披露的完整性。逐项判定合规/不合规/不适用，形成综合审计结论。</p>
    </div>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K1-12 其他应收款检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate('K1-12')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleAddItem">＋ 新增</el-button>
        <el-button size="small" @click="handleReview('K1-12-check')">💬 复核</el-button>
      </div>
    </div>

    <!-- 进度统计 -->
    <div class="progress-bar">
      <span>已完成 {{ completedCount }}/{{ sectionItems.length }}</span>
      <el-progress :percentage="progressPct" :stroke-width="6" :show-text="false" style="flex:1; margin-left: 12px;" />
    </div>

    <!-- 检查表格 -->
    <el-table :data="sectionItems" border size="small" class="check-table" :row-style="checkRowStyle">
      <el-table-column type="index" label="#" width="40" align="center" />

      <el-table-column label="检查项目" min-width="220">
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

    <!-- 综合结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <span class="conclusion-title">综合审计结论</span>
      </template>
      <el-input
        v-if="!isReadonly"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        :model-value="conclusion"
        placeholder="基于上述检查情况，形成综合审计结论..."
        @change="handleConclusionChange"
      />
      <div v-else class="readonly-content">{{ conclusion || '（未填写）' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>综合检查涵盖确认/计量/列报/披露四大认定维度</li>
        <li>期后回款核查：截止日后回款金额与期末余额比对</li>
        <li>重分类检查：应转入预付/应收账款/其他流动资产的项目</li>
        <li>完成全部检查项后形成综合结论，如有不合规项须提出调整建议</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabReceivableCheck.vue — K1-12 其他应收款检查表
 * Spec: .kiro/specs/k1-other-receivables/ | Task: 4.6
 * Requirements: 8.4, 8.5, 8.6
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

const SECTION_ID = 'K1-12'

const sectionItems = computed(() => {
  const section = sections.value.find(s => s.sectionId === SECTION_ID)
  return section?.items ?? []
})

const nonComplianceItems = computed(() =>
  sectionItems.value.filter(i => i.compliance === '不合规')
)

const completedCount = computed(() =>
  sectionItems.value.filter(i => i.compliance !== null).length
)

const progressPct = computed(() => {
  if (sectionItems.value.length === 0) return 0
  return Math.round((completedCount.value / sectionItems.value.length) * 100)
})

const conclusion = ref<string>('')

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadSections()
  if (sectionItems.value.length === 0) initDefaultItems()
  conclusion.value = props.allResponses.get('K1-12-conclusion')?.remark || ''
})

function initDefaultItems() {
  const defaults = [
    '其他应收款确认是否满足资产确认条件',
    '期末余额计量是否准确（与明细核对）',
    '科目分类是否恰当（非预付/非应收账款/非长期）',
    '账龄计算是否准确',
    '减值评估是否充分（ECL模型应用）',
    '期后回款情况核查',
    '外币其他应收款汇率折算是否正确',
    '重分类是否适当（流动/非流动划分）',
    '附注披露是否完整（性质/账龄/减值/关联方）',
    '是否存在需调整事项',
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

function handleConclusionChange(value: string) {
  conclusion.value = value
  const itemId = 'K1-12-conclusion'
  const payload = { item_id: itemId, conclusion: value, remark: value }
  props.allResponses.set(itemId, payload)
  emit('save', itemId, { conclusion: value, remark: value })
}

function handleAttach(itemId: string) { console.log('[K1-12] Attach voucher for:', itemId) }

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

function handleAiGenerate(section: string) { console.log('[K1-12] AI generate:', section) }
function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.k1-tab-receivable-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

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

.progress-bar {
  display: flex; align-items: center; margin-bottom: 12px;
  font-size: 12px; color: var(--el-text-color-secondary);
}

.check-table { font-size: var(--wp-font-size, 13px); }
.item-desc { font-size: 11px; color: var(--el-text-color-secondary); margin: 4px 0 0; }

.non-compliance-summary {
  margin-top: 16px; padding: 12px; border-radius: 6px;
  background: #fef2f2; border: 1px solid #fecaca;
}
.ncs-header { font-weight: 600; color: var(--el-color-danger); margin-bottom: 8px; }
.ncs-list { padding-left: 20px; margin: 0; line-height: 1.8; color: var(--el-color-danger-dark-2); }

.conclusion-card { margin-top: 20px; }
.conclusion-title { font-weight: 600; }
.readonly-content {
  padding: 8px 12px; background: var(--el-fill-color-lighter);
  border-radius: 4px; min-height: 40px; white-space: pre-wrap; line-height: 1.6;
}

.compile-hint {
  margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary);
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
