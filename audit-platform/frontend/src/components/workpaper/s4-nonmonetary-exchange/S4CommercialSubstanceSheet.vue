<template>
  <div class="s4-substance">
    <!-- ═══ 方法论上下文（琥珀色左边线） ═══ -->
    <div class="methodology-context">
      <p class="methodology-title">准则依据</p>
      <p class="methodology-text">
        根据《企业会计准则第7号——非货币性资产交换》，非货币性资产交换同时满足下列条件的，应当以公允价值为基础计量：
        (1) 该项交换具有商业实质；(2) 换入资产或换出资产的公允价值能够可靠计量。
        商业实质的判断：换入资产的未来现金流量在风险、时间和金额方面与换出资产<strong>显著不同</strong>。
      </p>
    </div>

    <!-- ═══ 第一部分：准则适用性判断（6项排除） ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>一、准则适用性判断</span>
          <div class="header-actions">
            <el-button
              size="small"
              @click="handleOpenReview('s4-applicability', '准则适用性判断')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <p class="section-desc">
        以下6项排除情形，若全部为「不属于」则适用非货币性资产交换准则。
        <el-tooltip content="=IF(AND(B8=&quot;不属于&quot;,...,G8=&quot;不属于&quot;),&quot;是&quot;,&quot;否&quot;)" placement="top">
          <span class="formula-hint">（IF 公式）</span>
        </el-tooltip>
      </p>

      <el-table
        :data="exclusionRows"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="description" label="排除情形" min-width="400" />
        <el-table-column prop="judgment" label="判断" width="140" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              v-model="row.judgment"
              size="small"
              placeholder="请选择"
              style="width: 110px"
              @change="handleExclusionChange($index)"
            >
              <el-option label="不属于" value="不属于" />
              <el-option label="属于" value="属于" />
            </el-select>
            <span v-else>{{ row.judgment || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 适用性结论 -->
      <div class="judgment-result" :class="{ 'result-pass': isApplicable, 'result-fail': !isApplicable }">
        <span class="result-label">准则适用性判断结果：</span>
        <el-tooltip
          content="6项排除全为「不属于」→ 适用准则（是）；任一为「属于」→ 不适用（否）"
          placement="top"
        >
          <span class="formula-cell result-value">
            {{ isApplicable ? '适用（是）' : '不适用（否）' }}
          </span>
        </el-tooltip>
      </div>
    </el-card>

    <!-- ═══ 第二部分：商业实质判断 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>二、商业实质判断</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiSubstance"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s4-substance', '商业实质判断')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="substanceRows"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="criterion" label="判断标准" min-width="400" />
        <el-table-column prop="answer" label="判断" width="140" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.answer"
              size="small"
              placeholder="请选择"
              style="width: 110px"
              @change="handleSubstanceChange"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.answer || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 商业实质结论 -->
      <div class="judgment-result" :class="{ 'result-pass': hasCommercialSubstance, 'result-fail': !hasCommercialSubstance }">
        <span class="result-label">商业实质判断结果：</span>
        <el-tooltip
          content="未来现金流量在风险/时间/金额方面显著不同 → 具有商业实质"
          placement="top"
        >
          <span class="formula-cell result-value">
            {{ hasCommercialSubstance ? '具有商业实质' : '不具有商业实质' }}
          </span>
        </el-tooltip>
      </div>
    </el-card>

    <!-- ═══ 审计说明/结论 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>审计结论</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiConclusion"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s4-substance-conclusion', '商业实质审计结论')"
            >复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-if="!isReadonly"
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="根据上述判断，填写商业实质审计结论"
      />
      <div v-else class="conclusion-text">{{ auditConclusion || '—' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 准则适用性判断：6项排除情形逐一判断。若存在任一「属于」项，则不适用非货币性资产交换准则。</p>
      <p>2. 商业实质判断：核心标准为未来现金流量的风险、时间和金额是否<strong>显著不同</strong>。</p>
      <p>3. 两项判断均采用 IF 逻辑公式，结果自动计算。</p>
      <p>4. 如不具有商业实质或公允价值不能可靠计量，应以账面价值为基础计量。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S4CommercialSubstanceSheet.vue — 商业实质的判断 S4-2
 *
 * 功能：
 * - 6项排除情形判断（准则适用性）— judgeApplicable
 * - 商业实质判断（现金流量显著不同）— judgeCommercialSubstance
 * - IF 逻辑公式驱动结论
 * - 公式结果虚线下划线 + tooltip 显示公式来源
 * - 审计结论 el-card + AI
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.1
 * Requirements: 2.1, 2.3, 2.4
 */
import { ref, computed, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { judgeApplicable, judgeCommercialSubstance } from '../composables/useS4FormulaEngine'
import type { CommercialSubstanceInput } from '../composables/useS4FormulaEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── 复核对话 ────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog')

function handleOpenReview(sectionId: string, label: string) {
  openReviewDialog?.(sectionId, label)
}

// ─── 6项排除情形 ─────────────────────────────────────────────────────────────

interface ExclusionRow {
  description: string
  judgment: string // '属于' | '不属于'
}

const exclusionRows = ref<ExclusionRow[]>([
  { description: '与所有者或所有者以非所有者身份进行的交易（如股东投入/分配）', judgment: '不属于' },
  { description: '企业合并中取得资产或承担负债的交易', judgment: '不属于' },
  { description: '不涉及资产交换的交易（如偿还债务）', judgment: '不属于' },
  { description: '以权益性证券取得或出售商品/劳务的交易', judgment: '不属于' },
  { description: '非互惠转让（如捐赠、政府补助）', judgment: '不属于' },
  { description: '涉及货币性资产比例≥25%的交易', judgment: '不属于' },
])

// ─── 商业实质判断 ────────────────────────────────────────────────────────────

interface SubstanceRow {
  criterion: string
  answer: string // '是' | '否'
}

const substanceRows = ref<SubstanceRow[]>([
  { criterion: '换入资产的未来现金流量在风险、时间和金额方面与换出资产显著不同', answer: '是' },
])

// ─── 使用 useS4FormulaEngine IF 判断逻辑 ────────────────────────────────────

/** 构造引擎输入 */
const engineInput = computed<CommercialSubstanceInput>(() => ({
  exclusions: exclusionRows.value.map(r => r.judgment === '属于'),
  cashflowDifferent: substanceRows.value[0]?.answer === '是',
}))

/** 准则适用性结果 */
const isApplicable = computed(() => judgeApplicable(engineInput.value))

/** 商业实质结果 */
const hasCommercialSubstance = computed(() => judgeCommercialSubstance(engineInput.value))

// ─── 排除情形变更 ────────────────────────────────────────────────────────────

function handleExclusionChange(_index: number) {
  // reactive 自动触发 computed 重算
}

function handleSubstanceChange() {
  // reactive 自动触发 computed 重算
}

// ─── 审计结论 ────────────────────────────────────────────────────────────────

const auditConclusion = ref('')

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiSubstance() {
  // TODO: AI 辅助分析商业实质
}

function handleAiConclusion() {
  // TODO: AI 辅助生成审计结论
}
</script>

<style scoped>
.s4-substance {
  padding: 12px;
}

.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fdf6ec;
  border-left: 4px solid #e6a23c;
  border-radius: 4px;
}

.methodology-title {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: #e6a23c;
}

.methodology-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  color: #606266;
}

.audit-section {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.section-desc {
  margin: 0 0 12px;
  font-size: 12px;
  color: #909399;
}

.formula-hint {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #409eff;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.judgment-result {
  margin-top: 16px;
  padding: 12px 16px;
  border-radius: 4px;
  font-size: 14px;
}

.result-pass {
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
}

.result-fail {
  background: #fef0f0;
  border: 1px solid #fde2e2;
}

.result-label {
  color: #606266;
  margin-right: 8px;
}

.result-value {
  font-weight: 600;
}

.result-pass .result-value {
  color: #67c23a;
}

.result-fail .result-value {
  color: #f56c6c;
}

.conclusion-text {
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.6;
  color: #303133;
}

.edit-hints {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}

.edit-hints summary {
  cursor: pointer;
  user-select: none;
}

.edit-hints p {
  margin: 4px 0;
  line-height: 1.5;
}
</style>
