<template>
  <div class="g6-tab-business-model">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：评价管理层对其他债权投资业务模式的判断（既以收取合同现金流量又以出售为目标），支持其 FVOCI 分类结论的恰当性。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:G6-7" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ bm.section1.value.items.length + bm.section2.value.items.length }} 项检查</el-tag>
    </div>

    <!-- 方法论上下文（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p><strong>CAS22 业务模式三类定义：</strong></p>
      <p>① <strong>持有以收取合同现金流量</strong>：管理金融资产的目标是收取合同现金流量，而非持有并出售</p>
      <p>② <strong>既以收取合同现金流量又以出售为目标</strong>：通过收取合同现金流量和出售金融资产两者实现目标</p>
      <p>③ <strong>其他</strong>：不符合上述两类的业务模式（如以交易为目的持有）</p>
      <p style="color: #92400e; font-size: 11px; margin-top: 4px;">
        依据CAS22《金融工具确认和计量》第十六条至第十九条，企业应在金融资产组合层次确定其业务模式，而非逐个金融资产确定。
      </p>
    </div>

    <!-- ═══ (一) 业务模式确定 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(一) 业务模式确定</span>
          <div class="section-actions">
            <el-tag size="small" type="info">
              完成度：{{ bm.section1CompletionRate.value }}%
            </el-tag>
            <el-button size="small" :disabled="isReadonly" @click="handleAi('section1')">✨ AI辅助</el-button>
            <el-button size="small" @click="openReview('G6-7-business-model-s1')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="bm.section1.value.items" border size="small" class="bm-table">
        <el-table-column label="序号" width="50" align="center">
          <template #default="{ row }">{{ row.seq }}</template>
        </el-table-column>
        <el-table-column label="检查项目" width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.checkItem }}</template>
        </el-table-column>
        <el-table-column label="审计要求" width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.auditRequirement }}</template>
        </el-table-column>
        <el-table-column label="管理层说明" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.managementExplanation"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              placeholder="管理层对该事项的说明..."
              @update:model-value="(v: string) => handleUpdateField('section1', row.id, 'managementExplanation', v)"
            />
            <span v-else class="cell-text">{{ row.managementExplanation || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否满足" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.isSatisfied"
              size="small"
              placeholder="选择"
              clearable
              style="width: 85px"
              @update:model-value="(v: boolean | null) => handleUpdateIsSatisfied('section1', row.id, v)"
            >
              <el-option :value="true" label="是" />
              <el-option :value="false" label="否" />
            </el-select>
            <el-tag v-else-if="row.isSatisfied === true" type="success" size="small">是</el-tag>
            <el-tag v-else-if="row.isSatisfied === false" type="danger" size="small">否</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="审计结论" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.auditConclusion"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              placeholder="审计结论..."
              @update:model-value="(v: string) => handleUpdateField('section1', row.id, 'auditConclusion', v)"
            />
            <span v-else class="cell-text">{{ row.auditConclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险评级" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.riskLevel"
              size="small"
              placeholder="风险"
              clearable
              style="width: 85px"
              @update:model-value="(v: string | null) => handleUpdateRisk('section1', row.id, v as any)"
            >
              <el-option value="high" label="高" />
              <el-option value="medium" label="中" />
              <el-option value="low" label="低" />
            </el-select>
            <el-tag v-else-if="row.riskLevel === 'high'" type="danger" size="small">高</el-tag>
            <el-tag v-else-if="row.riskLevel === 'medium'" type="warning" size="small">中</el-tag>
            <el-tag v-else-if="row.riskLevel === 'low'" type="success" size="small">低</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="80">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.indexRef"
              size="small"
              placeholder="索引"
              @update:model-value="(v: string) => handleUpdateField('section1', row.id, 'indexRef', v)"
            />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ (二) 出售情况分析 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">(二) 出售情况分析</span>
          <div class="section-actions">
            <el-tag size="small" type="info">
              完成度：{{ bm.section2CompletionRate.value }}%
            </el-tag>
            <el-button size="small" :disabled="isReadonly" @click="handleAi('section2')">✨ AI辅助</el-button>
            <el-button size="small" @click="openReview('G6-7-business-model-s2')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="bm.section2.value.items" border size="small" class="bm-table">
        <el-table-column label="序号" width="50" align="center">
          <template #default="{ row }">{{ row.seq }}</template>
        </el-table-column>
        <el-table-column label="检查项目" width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.checkItem }}</template>
        </el-table-column>
        <el-table-column label="审计要求" width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.auditRequirement }}</template>
        </el-table-column>
        <el-table-column label="管理层说明" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.managementExplanation"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              placeholder="管理层对该事项的说明..."
              @update:model-value="(v: string) => handleUpdateField('section2', row.id, 'managementExplanation', v)"
            />
            <span v-else class="cell-text">{{ row.managementExplanation || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否满足" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.isSatisfied"
              size="small"
              placeholder="选择"
              clearable
              style="width: 85px"
              @update:model-value="(v: boolean | null) => handleUpdateIsSatisfied('section2', row.id, v)"
            >
              <el-option :value="true" label="是" />
              <el-option :value="false" label="否" />
            </el-select>
            <el-tag v-else-if="row.isSatisfied === true" type="success" size="small">是</el-tag>
            <el-tag v-else-if="row.isSatisfied === false" type="danger" size="small">否</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="审计结论" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.auditConclusion"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              placeholder="审计结论..."
              @update:model-value="(v: string) => handleUpdateField('section2', row.id, 'auditConclusion', v)"
            />
            <span v-else class="cell-text">{{ row.auditConclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险评级" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.riskLevel"
              size="small"
              placeholder="风险"
              clearable
              style="width: 85px"
              @update:model-value="(v: string | null) => handleUpdateRisk('section2', row.id, v as any)"
            >
              <el-option value="high" label="高" />
              <el-option value="medium" label="中" />
              <el-option value="low" label="低" />
            </el-select>
            <el-tag v-else-if="row.riskLevel === 'high'" type="danger" size="small">高</el-tag>
            <el-tag v-else-if="row.riskLevel === 'medium'" type="warning" size="small">中</el-tag>
            <el-tag v-else-if="row.riskLevel === 'low'" type="success" size="small">低</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="80">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.indexRef"
              size="small"
              placeholder="索引"
              @update:model-value="(v: string) => handleUpdateField('section2', row.id, 'indexRef', v)"
            />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ (三) 综合判断 ═══ -->
    <el-card shadow="never" class="section-card conclusion-section">
      <template #header>
        <div class="section-header">
          <span class="section-title">(三) 综合判断</span>
          <div class="section-actions">
            <el-tag
              v-if="bm.finalConclusion.value"
              :type="bm.conclusionLabel.value.type"
              size="small"
            >
              {{ bm.conclusionLabel.value.label }}
            </el-tag>
            <el-button size="small" :disabled="isReadonly" @click="handleAi('conclusion')">✨ AI辅助</el-button>
            <el-button size="small" @click="openReview('G6-7-business-model-conclusion')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="conclusion-grid">
        <!-- 最终分类结论下拉 -->
        <div class="conclusion-item">
          <label class="conclusion-label">最终分类结论</label>
          <el-select
            v-if="!isReadonly"
            :model-value="bm.finalConclusion.value"
            placeholder="请选择最终业务模式分类"
            clearable
            style="width: 280px"
            @update:model-value="handleFinalConclusionChange"
          >
            <el-option value="hold_collect" label="持有以收取合同现金流量" />
            <el-option value="hold_and_sell" label="既以收取合同现金流量又以出售为目标" />
            <el-option value="other" label="其他（以交易为目的等）" />
          </el-select>
          <el-tag
            v-else-if="bm.finalConclusion.value"
            :type="bm.conclusionLabel.value.type"
          >
            {{ bm.conclusionLabel.value.label }}
          </el-tag>
          <span v-else class="no-data">未确定</span>
        </div>

        <!-- 自动推导提示 -->
        <div v-if="bm.derivedConclusion.value && bm.isComplete.value" class="derived-hint">
          <el-icon style="color: #f59e0b; margin-right: 4px;">⚡</el-icon>
          <span>系统根据填写结果自动推导为：{{ getDerivedLabel(bm.derivedConclusion.value) }}</span>
        </div>

        <!-- 高风险项提示 -->
        <div v-if="bm.highRiskCount.value > 0" class="risk-alert">
          <el-alert
            :title="`存在 ${bm.highRiskCount.value} 个高风险检查项，请重点关注`"
            type="warning"
            :closable="false"
            show-icon
          />
        </div>

        <!-- 综合分析说明 textarea -->
        <div class="conclusion-item full-width">
          <label class="conclusion-label">综合分析说明</label>
          <el-input
            v-if="!isReadonly"
            :model-value="bm.finalAnalysis.value"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 12 }"
            placeholder="综合分析说明：结合业务模式确定和出售情况分析两部分结论，说明最终分类为持有收取/兼有/其他的理由..."
            @update:model-value="handleFinalAnalysisChange"
          />
          <div v-else class="readonly-analysis">{{ bm.finalAnalysis.value || '（未填写）' }}</div>
        </div>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="section-card audit-note-card">
      <template #header>
        <div class="section-header"><span class="section-title">审计说明</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述业务模式确定与出售情况分析的测试情况及结果、对分类判断的支持性、拟调整与未调整事项及其影响。"
        @update:model-value="saveAuditNote"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guide-details">
      <summary>📋 编制提示</summary>
      <div class="guide-content">
        <p>1. 业务模式评估应在金融资产组合层次进行，而非逐笔评估</p>
        <p>2. 评估时应基于管理层确定业务模式的实际行动，而非仅声明的意图</p>
        <p>3. 业务模式不取决于管理层对某项特定金融资产的意图，而非资产组合管理方式</p>
        <p>4. 需关注以下因素：①日常出售频率和金额 ②业绩评价方式 ③管理层薪酬机制 ④风险管理策略</p>
        <p>5. 出售分析重点：出售原因（信用恶化/临近到期/偶发事件）是否构成业务模式变更</p>
        <p>6. 业务模式结论直接影响金融资产分类：①持有收取→AC或FVOCI-Debt ②兼有→FVOCI-Debt ③其他→FVTPL</p>
        <p>7. 如存在出售但满足以下条件可不改变业务模式：出售不频繁、金额不大（即使合计重大）、或出售原因为信用风险恶化</p>
        <p>8. 特别关注：临近到期的出售通常不影响业务模式判断</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabBusinessModel.vue — G6-7 业务模式分析（三section问卷式）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 7.2
 * Requirements: 4.1, 4.2, 4.3
 *
 * 功能：
 * - 方法论上下文(琥珀色): CAS22业务模式三类定义(①持有收取 ②兼有 ③其他)
 * - 三section结构:
 *   (一) 业务模式确定 — 8列表格问卷
 *   (二) 出售情况分析 — 8列表格问卷
 *   (三) 综合判断 — 最终分类下拉 + 综合分析textarea autosize
 * - 每section标题行右侧: AI辅助按钮 + 复核按钮
 * - 综合判断自动推导: 基于section1/section2的isSatisfied推导finalConclusion
 * - 编制提示details折叠底部
 * - emit 'save' debounced
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useG6SppiBusinessModel, type BusinessModelData } from '../../composables/useG6SppiBusinessModel'
import { useG6SppiFormData } from '../../composables/useG6SppiFormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  save: []
}>()

// ─── 复核对话 inject ───
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

function openReview(sectionId: string): void {
  openReviewDialog(sectionId)
}

// ─── 数据层 ───
const formData = useG6SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const bm = useG6SppiBusinessModel()

// ─── 审计说明（独立持久化 checklist_responses） ───
const NOTE_KEY = 'G6-7-business-model-audit-note'
const auditNote = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { remark: val })
}

// ─── 数据加载 ───
onMounted(async () => {
  await formData.loadAll()
  initFromFormData()
  const noteResp = formData.allResponses.value.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
})

watch(() => props.htmlData, (newData) => {
  if (newData) {
    initFromFormData()
  }
})

function initFromFormData(): void {
  const content = formData.parseContent()
  if (content.businessModel) {
    bm.loadData(content.businessModel as BusinessModelData)
  }
}

// ─── 保存逻辑（debounced） ───
let _saveTimer: ReturnType<typeof setTimeout> | null = null

function triggerSave(): void {
  if (_saveTimer) clearTimeout(_saveTimer)
  _saveTimer = setTimeout(() => {
    formData.debouncedSave('G6-7-business-model-data', {
      conclusion: JSON.stringify(bm.toJSON()),
    })
    emit('save')
  }, 800)
}

// ─── 字段更新 handlers ───
function handleUpdateField(
  sectionKey: 'section1' | 'section2',
  itemId: string,
  field: 'managementExplanation' | 'auditConclusion' | 'indexRef',
  value: string,
): void {
  if (field === 'managementExplanation') {
    bm.updateManagementExplanation(sectionKey, itemId, value)
  } else if (field === 'auditConclusion') {
    bm.updateAuditConclusion(sectionKey, itemId, value)
  } else if (field === 'indexRef') {
    bm.updateIndexRef(sectionKey, itemId, value)
  }
  triggerSave()
}

function handleUpdateIsSatisfied(
  sectionKey: 'section1' | 'section2',
  itemId: string,
  value: boolean | null,
): void {
  bm.updateIsSatisfied(sectionKey, itemId, value)
  triggerSave()
}

function handleUpdateRisk(
  sectionKey: 'section1' | 'section2',
  itemId: string,
  value: 'high' | 'medium' | 'low' | null,
): void {
  bm.updateRiskLevel(sectionKey, itemId, value)
  triggerSave()
}

function handleFinalConclusionChange(value: 'hold_collect' | 'hold_and_sell' | 'other' | null): void {
  bm.setFinalConclusion(value)
  triggerSave()
}

function handleFinalAnalysisChange(value: string): void {
  bm.setFinalAnalysis(value)
  triggerSave()
}

// ─── AI辅助 ───
function handleAi(section: string): void {
  ElMessage.info(`AI辅助(业务模式-${section})功能将在AI模块完成后启用`)
}

// ─── 推导结论文字映射 ───
function getDerivedLabel(value: string): string {
  const map: Record<string, string> = {
    hold_collect: '持有以收取合同现金流量',
    hold_and_sell: '既以收取合同现金流量又以出售为目标',
    other: '其他（以交易为目的等）',
  }
  return map[value] || '未知'
}

// ─── 暴露接口 ───
defineExpose({
  toJSON: () => bm.toJSON(),
})
</script>

<style scoped>
.g6-tab-business-model {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 审计目标 / 工具栏 ─── */
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.chip-wrap {
  display: inline-flex;
  align-items: center;
}
.audit-note-card {
  margin-top: 16px;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景）─── */
.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.8;
}

.methodology-context p {
  margin: 0 0 2px;
}

/* ─── Section卡片 ─── */
.section-card {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
}

.section-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ─── 表格 ─── */
.bm-table {
  font-size: var(--wp-font-size, 13px);
}

.bm-table :deep(.el-table__cell) {
  padding: 6px 0;
}

.cell-text {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  line-height: 1.5;
}

/* ─── 综合判断section ─── */
.conclusion-section {
  border-top: 2px solid #f59e0b;
}

.conclusion-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.conclusion-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.conclusion-item.full-width {
  width: 100%;
}

.conclusion-label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: #303133;
}

.no-data {
  color: #909399;
  font-size: var(--wp-font-size, 13px);
}

.derived-hint {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: #92400e;
  background: #fffbeb;
  border-radius: 4px;
  padding: 6px 10px;
}

.risk-alert {
  margin-top: 4px;
}

.readonly-analysis {
  white-space: pre-wrap;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
  color: #303133;
  background: #f5f7fa;
  padding: 8px 12px;
  border-radius: 4px;
  min-height: 60px;
}

/* ─── 编制提示 ─── */
.guide-details {
  margin-top: 16px;
}

.guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  font-weight: 600;
}

.guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.guide-content p {
  margin: 0;
}
</style>
