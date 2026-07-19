<template>
  <div class="g4-tab-business-model">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认管理债权投资的业务模式判断恰当（以收取合同现金流量为目标），作为金融资产分类计量的基础。"
      style="margin-bottom: 12px"
    />
    <!-- 工具栏（索引 chip） -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <G4SppiImportExportDropdown
          :wp-id="wpId"
          sheet="G4-5"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:G4-5" :context-project-id="projectId" /></span>
      </div>
    </div>
    <!-- Section标题 + 复核按钮 -->
    <div class="section-header">
      <h3 class="section-title">G4-5 业务模式分析</h3>
      <div class="section-actions">
        <el-button
          size="small"
          type="success"
          plain
          :disabled="props.isReadonly || bm.conclusion.value === 'INCOMPLETE'"
          @click="bm.writeClassificationToG42()"
        >
          回写分类至 G4-2
        </el-button>
        <el-button size="small" :icon="ChatDotRound" @click="handleReview('G4-5业务模式分析')">复核</el-button>
      </div>
    </div>

    <!-- 方法论上下文（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p>确定管理债权投资的业务模式，以此为基础对债权投资进行分类。根据《企业会计准则第22号——金融工具确认和计量》（CAS22），企业应当在金融资产组合层次上确定管理金融资产的业务模式。</p>
    </div>

    <!-- ═══ (一) 以单一业务模式管理所有债权投资 ═══ -->
    <el-divider content-position="left">
      <span class="divider-title">(一) 以单一业务模式管理所有债权投资</span>
    </el-divider>

    <!-- Excel 否定筛查问卷（是=不利 AC） -->
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="说明：下列问题为否定筛查。「是」表示偏离单纯收取合同现金流量业务模式；全部「否」方可结论为以收取合同现金流量为目标（AC）。"
      style="margin-bottom: 12px"
    />
    <div class="questionnaire-list">
      <div
        v-for="item in bm.questionnaire.value"
        :key="item.id"
        class="questionnaire-item"
        :class="{ 'is-indent': item.indent }"
      >
        <div class="question-row">
          <span class="question-seq">{{ item.displaySeq || item.seq }}.</span>
          <span class="question-text">{{ item.question }}</span>
          <el-radio-group
            :model-value="item.answer"
            :disabled="props.isReadonly || item.id === 'q2'"
            size="small"
            class="question-radio"
            @update:model-value="(val: boolean | null) => bm.setAnswer(item.id, val as boolean | null)"
          >
            <el-radio :value="true">是</el-radio>
            <el-radio :value="false">否</el-radio>
          </el-radio-group>
          <el-tag v-if="item.id === 'q2'" size="small" type="info" effect="plain">由 2.1～2.3 自动汇总</el-tag>
        </div>
        <div class="explanation-row">
          <el-input
            :model-value="item.explanation"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="说明（选填）"
            :disabled="props.isReadonly"
            @update:model-value="(val: string) => bm.setExplanation(item.id, val)"
          />
        </div>
      </div>
    </div>

    <!-- 审计评价 -->
    <div class="audit-evaluation">
      <label class="field-label">审计评价</label>
      <el-input
        :model-value="bm.auditEvaluation.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请输入审计评价..."
        :disabled="props.isReadonly"
        @update:model-value="bm.setAuditEvaluation"
      />
    </div>

    <!-- 结论chip区域 -->
    <div class="conclusion-area">
      <span class="conclusion-label">结论：</span>
      <el-tag
        :color="bm.conclusionChip.value.color"
        :type="bm.conclusionChip.value.type"
        size="large"
        effect="dark"
        round
      >
        {{ bm.conclusionChip.value.label }}
      </el-tag>
    </div>

    <!-- 回答自洽提示 -->
    <el-alert
      v-for="(hint, idx) in bm.inconsistencyHints.value"
      :key="`inc-${idx}`"
      :title="hint"
      type="warning"
      show-icon
      :closable="false"
      class="cross-check-warning"
    />

    <!-- 跨组校验警告 -->
    <el-alert
      v-if="bm.crossCheckWarning.value"
      :title="bm.crossCheckWarning.value"
      type="warning"
      show-icon
      :closable="false"
      class="cross-check-warning"
    />

    <!-- ═══ (二) 将债权投资分拆为次级组合分别确定业务模式 ═══ -->
    <el-divider content-position="left">
      <span class="divider-title">(二) 将债权投资分拆为次级组合分别确定业务模式</span>
    </el-divider>

    <div class="sub-portfolio-toggle">
      <span class="field-label">适用性：</span>
      <el-radio-group
        :model-value="bm.hasSubPortfolios.value"
        :disabled="props.isReadonly"
        size="small"
        @update:model-value="(val: boolean) => bm.setHasSubPortfolios(val)"
      >
        <el-radio :value="true">是，需分拆为次级组合</el-radio>
        <el-radio :value="false">否，单一业务模式适用</el-radio>
      </el-radio-group>
    </div>

    <!-- 次级组合编辑区 -->
    <div v-if="bm.hasSubPortfolios.value" class="sub-portfolios-section">
      <div
        v-for="sp in bm.subPortfolios.value"
        :key="sp.id"
        class="sub-portfolio-card"
      >
        <el-card shadow="hover">
          <template #header>
            <div class="sp-card-header">
              <div class="sp-title-block">
                <el-input
                  :model-value="sp.name"
                  size="small"
                  class="sp-name-input"
                  :disabled="props.isReadonly"
                  placeholder="组合名称"
                  @change="(v: string) => bm.renameSubPortfolio(sp.id, v)"
                />
                <el-input
                  :model-value="sp.basis"
                  size="small"
                  class="sp-basis-input"
                  :disabled="props.isReadonly"
                  placeholder="组合依据（如：持有至到期组合 / 流动性管理组合）"
                  @change="(v: string) => bm.setSubBasis(sp.id, v)"
                />
              </div>
              <el-button
                v-if="!props.isReadonly"
                type="danger"
                size="small"
                text
                @click="bm.removeSubPortfolio(sp.id)"
              >
                删除
              </el-button>
            </div>
          </template>
          <!-- 重复否定筛查问卷 -->
          <div class="questionnaire-list">
            <div
              v-for="item in sp.questionnaire"
              :key="item.id"
              class="questionnaire-item"
              :class="{ 'is-indent': item.indent }"
            >
              <div class="question-row">
                <span class="question-seq">{{ item.displaySeq || item.seq }}.</span>
                <span class="question-text">{{ item.question }}</span>
                <el-radio-group
                  :model-value="item.answer"
                  :disabled="props.isReadonly || item.id === 'q2'"
                  size="small"
                  class="question-radio"
                  @update:model-value="(val: boolean | null) => bm.setSubAnswer(sp.id, item.id, val as boolean | null)"
                >
                  <el-radio :value="true">是</el-radio>
                  <el-radio :value="false">否</el-radio>
                </el-radio-group>
                <el-tag v-if="item.id === 'q2'" size="small" type="info" effect="plain">由 2.1～2.3 自动汇总</el-tag>
              </div>
              <div class="explanation-row">
                <el-input
                  :model-value="item.explanation"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 4 }"
                  placeholder="说明（选填）"
                  :disabled="props.isReadonly"
                  @update:model-value="(val: string) => bm.setSubExplanation(sp.id, item.id, val)"
                />
              </div>
            </div>
          </div>
          <!-- 次级组合结论chip -->
          <div class="conclusion-area sub-conclusion">
            <span class="conclusion-label">结论：</span>
            <el-tag
              :color="getChipStyle(sp.conclusion).color"
              :type="getChipStyle(sp.conclusion).type"
              size="default"
              effect="dark"
              round
            >
              {{ getChipStyle(sp.conclusion).label }}
            </el-tag>
          </div>
        </el-card>
      </div>

      <!-- 新增次级组合按钮 -->
      <el-button
        v-if="!props.isReadonly"
        type="primary"
        plain
        size="small"
        @click="bm.addSubPortfolio()"
      >
        + 新增次级组合
      </el-button>
    </div>

    <div v-if="!props.isReadonly" class="audit-ai-row">
      <el-button
        size="small"
        type="primary"
        plain
        :disabled="!aiAvailable"
        :loading="aiLoading"
        @click="fillAiConclusion"
      >
        🤖 AI生成结论
      </el-button>
    </div>
    <G4AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="bm.auditConclusion.value"
      note-placeholder="请输入审计说明..."
      conclusion-placeholder="请输入审计结论..."
      @update:note="saveAuditNote"
      @update:conclusion="bm.setAuditConclusion"
    />

    <!-- 编制提示 -->
    <details class="preparation-tips">
      <summary>编制提示</summary>
      <div class="tips-content">
        <p>1. 对齐 Excel G4-5：否定筛查问卷 + 自动结论（收取合同现金流量 / 收取+出售 / 其他业务模式）。</p>
        <p>2. 题2「交易性」由 2.1～2.3 自动汇总（与模板 E16 公式一致）；请填写子题并在「说明」中记录依据。</p>
        <p>3. 结论链路对齐模板 A23：当前出售 → 未来出售 → 交易性/FV；仅题3「公允价值管理」为是时按 CAS22 归入其他业务模式。</p>
        <p>4. 业务模式在组合层次确定，不取决于管理层对单笔工具的意图；次级组合需填写名称与组合依据。</p>
        <p>5. G4 科目通常对应 AC；若结论为 FVOCI/FVTPL，应考虑重分类至 G6/G1，并与 G4-6 SPPI 一并复核最终分类。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabBusinessModel.vue — G4-5 业务模式分析（完整实现）
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/ Task 5.2
 * Requirements: 2.1~2.9, 9.1~9.6, 9.11
 *
 * 方法论上下文(琥珀色左边线+浅黄背景) + 5道问卷(是/否radio + 说明textarea autosize)
 * + 审计评价 + 结论chip(动态变色) + 次级组合(ElMessageBox.prompt新增)
 * + 审计结论textarea(AI按钮) + 编制提示details折叠
 */
import { inject, computed, ref, watch } from 'vue'
import { ChatDotRound } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G4AuditTextCards from '../../g4-bond-investment-main/G4AuditTextCards.vue'
import G4SppiImportExportDropdown from '../G4SppiImportExportDropdown.vue'
import { useG4SppiFormData } from '@/composables/useG4SppiFormData'
import { useG4SppiBusinessModel, CONCLUSION_CHIP_MAP, type ConclusionChipStyle } from '@/composables/useG4SppiBusinessModel'
import type { BusinessModelResult } from '@/composables/useG4SppiFormulaEngine'
import { useG4SppiAiGenerate } from '../../composables/useG4SppiAiGenerate'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── 复核对话 inject ────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog')

function handleReview(sectionId: string): void {
  openReviewDialog?.(sectionId)
}

// ─── 数据层 ─────────────────────────────────────────────────────────────────
const formData = useG4SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// 加载数据
formData.loadAll()

// ─── 业务模式composable ─────────────────────────────────────────────────────
const bm = useG4SppiBusinessModel({
  allResponses: formData.allResponses,
  debouncedSave: formData.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

async function onImported(): Promise<void> {
  try {
    await formData.loadAll()
  } catch { /* ignore */ }
  bm.loadFromResponses()
}

const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG4SppiAiGenerate(wpIdRef)

async function fillAiConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'business-model-conclusion',
    bm.auditConclusion.value || '',
    {},
    'AI 审计结论',
  )
  if (text) bm.setAuditConclusion(text)
}

// ─── chip样式helper ─────────────────────────────────────────────────────────
function getChipStyle(conclusion: BusinessModelResult): ConclusionChipStyle {
  return CONCLUSION_CHIP_MAP[conclusion]
}

// ─── 审计说明（纯 textarea，无 AI；持久化 checklist_responses，conclusion:null） ──
const NOTE_KEY = 'G4-5-businessmodel-audit-note'
const auditNote = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  void formData.saveImmediate(NOTE_KEY, { conclusion: null, remark: val })
}
watch(
  () => formData.allResponses.value.get(NOTE_KEY)?.remark,
  (v) => { if (v != null) auditNote.value = v },
  { immediate: true },
)
</script>

<style scoped>
.g4-tab-business-model {
  font-size: var(--wp-font-size, 13px);
  padding: 8px 0;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.section-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

/* 方法论上下文：琥珀色左边线+浅黄背景 */
.methodology-context {
  border-left: 4px solid #E6A23C;
  background: #fdf6ec;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
  color: #856404;
}

.methodology-context p {
  margin: 0;
}

.divider-title {
  font-weight: 600;
  font-size: 14px;
}

/* 问卷列表 */
.questionnaire-list {
  margin-bottom: 16px;
}

.questionnaire-item.is-indent {
  margin-left: 24px;
  padding-left: 12px;
  border-left: 2px solid #e4e7ed;
}
.questionnaire-item {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}

.question-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.question-seq {
  font-weight: 600;
  color: #606266;
  min-width: 20px;
}

.question-text {
  flex: 1;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}

.question-radio {
  flex-shrink: 0;
}

.explanation-row {
  padding-left: 28px;
}

/* 审计评价 */
.audit-evaluation {
  margin-bottom: 16px;
}

.field-label {
  display: inline-block;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #606266;
  margin-bottom: 6px;
}

/* 结论区域 */
.conclusion-area {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
  margin-bottom: 12px;
}

.conclusion-area.sub-conclusion {
  margin-top: 12px;
  background: #f8f9fa;
}

.conclusion-label {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

/* 跨组校验警告 */
.cross-check-warning {
  margin-bottom: 16px;
}

/* 次级组合 */
.sub-portfolio-toggle {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.sub-portfolios-section {
  margin-bottom: 16px;
}

.sub-portfolio-card {
  margin-bottom: 12px;
}

.sp-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.sp-title-block {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sp-name-input {
  max-width: 320px;
}

.sp-basis-input {
  max-width: 480px;
}

.sp-name {
  font-weight: 600;
  font-size: 14px;
}

.audit-ai-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 编制提示 */
.preparation-tips {
  margin-top: 16px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
  color: #909399;
}

.preparation-tips summary {
  cursor: pointer;
  font-weight: 500;
  color: #606266;
}

.tips-content {
  margin-top: 8px;
  line-height: 1.8;
}

.tips-content p {
  margin: 0;
}
</style>
