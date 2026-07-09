<template>
  <div class="s5-timing">
    <!-- ═══ 方法论上下文（琥珀色左边线）— 不得提前确认警示 ═══ -->
    <div class="methodology-context warning-context">
      <p class="methodology-title">⚠️ 重要提示 — 不得提前确认债务重组收益</p>
      <p class="methodology-text">
        <strong>不得在破产重整或债务重组方案实施的重大不确定性消除前提前确认债务重组收益。</strong>
      </p>
      <p class="methodology-text">
        根据《企业会计准则第12号——债务重组》及相关应用指南，债务重组收益的确认应满足以下条件：
        (1) 债务重组协议已生效或法院裁定已生效；
        (2) 债务豁免条件已全部满足（如有）；
        (3) 不存在可撤销条款或撤销权已失效；
        (4) 破产重整中，法院已裁定批准重整计划且执行完毕。
        在上述重大不确定性消除之前，不得确认债务重组收益。
      </p>
    </div>

    <!-- ═══ 损益确认时点判断表 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>债务重组损益确认时点 S5-2</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s5-timing', '损益确认时点')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="timingRows"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="item" label="判断项目" min-width="260" />
        <el-table-column prop="date" label="日期" width="160" align="center">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly && row.hasDate"
              v-model="row.date"
              type="date"
              size="small"
              placeholder="选择日期"
              style="width: 140px"
              value-format="YYYY-MM-DD"
            />
            <span v-else-if="row.hasDate">{{ row.date || '—' }}</span>
            <span v-else class="not-applicable">N/A</span>
          </template>
        </el-table-column>
        <el-table-column prop="judgment" label="判断结果" width="160" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.judgment"
              size="small"
              placeholder="请选择"
              style="width: 130px"
              @change="handleTimingChange"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="N/A" value="N/A" />
            </el-select>
            <span v-else>{{ row.judgment || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="note" label="备注说明" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.note"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="补充说明"
            />
            <span v-else>{{ row.note || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 综合判断结论 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>综合判断</span>
          <div class="header-actions">
            <el-button
              size="small"
              @click="handleOpenReview('s5-timing-conclusion', '时点综合判断')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <!-- 判断结果 -->
      <div class="judgment-result" :class="judgmentResultClass">
        <span class="result-label">损益确认时点判断结果：</span>
        <el-tooltip
          :content="judgmentTooltip"
          placement="top"
        >
          <span class="formula-cell result-value">{{ judgmentResultText }}</span>
        </el-tooltip>
      </div>

      <!-- 提前确认风险警告 -->
      <div v-if="hasEarlyRecognitionRisk" class="early-recognition-warning">
        <el-alert
          title="存在提前确认风险"
          type="error"
          :closable="false"
          show-icon
        >
          <template #default>
            <p>
              根据上述判断，存在以下提前确认风险因素：
            </p>
            <ul class="risk-list">
              <li v-for="risk in riskFactors" :key="risk">{{ risk }}</li>
            </ul>
            <p class="risk-conclusion">
              建议：在上述重大不确定性消除前，不应确认债务重组收益。
            </p>
          </template>
        </el-alert>
      </div>
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
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
              @click="handleOpenReview('s5-timing-audit-conclusion', '审计结论')"
            >复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-if="!isReadonly"
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="根据上述时点判断，填写审计结论"
      />
      <div v-else class="conclusion-text">{{ auditConclusion || '—' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 逐项记录债务重组损益确认的关键时点和条件满足情况。</p>
      <p>2. 重点关注：协议是否已生效、豁免条件是否已满足、是否存在可撤销条款。</p>
      <p>3. 破产重整类：必须在法院裁定批准重整计划且执行完毕后方可确认收益。</p>
      <p>4. <strong>铁律：不得在重大不确定性消除前提前确认债务重组收益。</strong></p>
      <p>5. 如判断存在提前确认风险，应要求被审计单位转回已确认的收益或调整为或有事项处理。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S5TimingJudgmentSheet.vue — 债务重组损益确认时点 S5-2
 *
 * 功能：
 * - 记录审批日/协议生效日/债务豁免条件/是否可撤销/破产重整完成日等关键时点（Req 3.3）
 * - 提示不得在重大不确定性消除前提前确认收益（Req 3.4）— 琥珀色方法论上下文区块
 * - 综合判断损益确认时点是否恰当
 * - 风险因素自动汇总
 * - 审计结论 el-card + AI 按钮
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.2
 * Requirements: 3.3, 3.4
 */
import { ref, computed, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'

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

// ─── 时点判断行数据 ──────────────────────────────────────────────────────────

interface TimingRow {
  item: string
  date: string
  judgment: string // '是' | '否' | 'N/A'
  note: string
  hasDate: boolean
  /** 判断为"否"时是否构成提前确认风险 */
  riskWhenNo: boolean
  riskDescription: string
}

const timingRows = ref<TimingRow[]>([
  {
    item: '债务重组协议/方案是否已经各方审批通过',
    date: '',
    judgment: '',
    note: '',
    hasDate: true,
    riskWhenNo: true,
    riskDescription: '协议/方案尚未获得各方审批',
  },
  {
    item: '债务重组协议/方案是否已生效',
    date: '',
    judgment: '',
    note: '',
    hasDate: true,
    riskWhenNo: true,
    riskDescription: '协议/方案尚未生效',
  },
  {
    item: '债务豁免条件是否已全部满足（如有附条件豁免）',
    date: '',
    judgment: '',
    note: '',
    hasDate: false,
    riskWhenNo: true,
    riskDescription: '债务豁免条件尚未全部满足',
  },
  {
    item: '债务重组协议是否存在可撤销条款',
    date: '',
    judgment: '',
    note: '',
    hasDate: false,
    riskWhenNo: false, // 此项"是"才是风险
    riskDescription: '协议存在可撤销条款，撤销权尚未失效',
  },
  {
    item: '（如涉及破产重整）法院是否已裁定批准重整计划',
    date: '',
    judgment: '',
    note: '',
    hasDate: true,
    riskWhenNo: true,
    riskDescription: '破产重整计划尚未获法院裁定批准',
  },
  {
    item: '（如涉及破产重整）重整计划是否已执行完毕',
    date: '',
    judgment: '',
    note: '',
    hasDate: true,
    riskWhenNo: true,
    riskDescription: '破产重整计划尚未执行完毕',
  },
  {
    item: '是否存在其他影响损益确认的重大不确定性',
    date: '',
    judgment: '',
    note: '',
    hasDate: false,
    riskWhenNo: false, // 此项"是"才是风险
    riskDescription: '存在其他影响损益确认的重大不确定性',
  },
])

// ─── 提前确认风险判断 ────────────────────────────────────────────────────────

/** 是否存在提前确认风险 */
const hasEarlyRecognitionRisk = computed(() => riskFactors.value.length > 0)

/** 收集风险因素 */
const riskFactors = computed(() => {
  const factors: string[] = []
  for (const row of timingRows.value) {
    if (!row.judgment) continue

    // 对于"否"=风险的项（如协议未生效、条件未满足等）
    if (row.riskWhenNo && row.judgment === '否') {
      factors.push(row.riskDescription)
    }
    // 对于"是"=风险的项（如存在可撤销条款、存在重大不确定性）
    if (!row.riskWhenNo && row.judgment === '是') {
      factors.push(row.riskDescription)
    }
  }
  return factors
})

// ─── 综合判断结果 ────────────────────────────────────────────────────────────

const judgmentResultText = computed(() => {
  if (timingRows.value.every(r => !r.judgment)) return '待判断'
  if (hasEarlyRecognitionRisk.value) return '时点不恰当（存在提前确认风险）'
  return '时点恰当（可确认损益）'
})

const judgmentResultClass = computed(() => {
  if (timingRows.value.every(r => !r.judgment)) return ''
  return hasEarlyRecognitionRisk.value ? 'result-fail' : 'result-pass'
})

const judgmentTooltip = computed(() => {
  if (hasEarlyRecognitionRisk.value) {
    return '存在重大不确定性，不得提前确认债务重组收益'
  }
  return '各项条件均已满足，可以确认债务重组损益'
})

// ─── 时点变更处理 ────────────────────────────────────────────────────────────

function handleTimingChange() {
  // reactive 自动触发 computed 重算
}

// ─── 审计结论 ────────────────────────────────────────────────────────────────

const auditConclusion = ref('')

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiAssist() {
  // TODO: AI 辅助分析时点判断
}

function handleAiConclusion() {
  // TODO: AI 辅助生成审计结论
}
</script>

<style scoped>
.s5-timing {
  padding: 12px;
}

.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fdf6ec;
  border-left: 4px solid #e6a23c;
  border-radius: 4px;
}

.methodology-context.warning-context {
  background: #fef0f0;
  border-left-color: #f56c6c;
}

.methodology-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #f56c6c;
}

.methodology-text {
  margin: 0 0 6px;
  font-size: 12px;
  line-height: 1.7;
  color: #606266;
}

.methodology-text:last-child {
  margin-bottom: 0;
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

.not-applicable {
  color: #c0c4cc;
  font-style: italic;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.judgment-result {
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

.early-recognition-warning {
  margin-top: 16px;
}

.risk-list {
  margin: 8px 0;
  padding-left: 20px;
}

.risk-list li {
  line-height: 1.8;
}

.risk-conclusion {
  margin-top: 8px;
  font-weight: 600;
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
