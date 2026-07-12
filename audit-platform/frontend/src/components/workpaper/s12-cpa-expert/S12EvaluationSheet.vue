<template>
  <div class="s12-evaluation">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">{{ auditObjective }}</div>
    </el-alert>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>{{ sheetKey }} {{ title }}</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview(`s12-eval-${sheetKey}`, title)"
            >复核</el-button>
          </div>
        </div>
      </template>

      <!-- 方法论上下文（琥珀色左边线） -->
      <div v-if="methodologyContext" class="methodology-context">
        <p>{{ methodologyContext }}</p>
      </div>

      <el-table
        :data="evaluationRows"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="category" label="评价项目" width="140">
          <template #default="{ row }">
            <span>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="criterion" label="评价内容/标准" min-width="320">
          <template #default="{ row }">
            <span>{{ row.criterion }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="result" label="评价结果" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.result"
              size="small"
              placeholder="—"
              style="width: 100px"
              @change="saveRows"
            >
              <el-option label="满意" value="满意" />
              <el-option label="基本满意" value="基本满意" />
              <el-option label="不满意" value="不满意" />
              <el-option label="N/A" value="N/A" />
            </el-select>
            <span v-else>{{ row.result || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="说明/依据" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="填写说明或依据"
              @change="saveRows"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ref" label="索引号" width="90" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.ref" :value="row.ref" />
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-section conclusion-card">
      <template #header>
        <div class="section-header">
          <span>结论</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiConclusion"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview(`s12-eval-${sheetKey}-conclusion`, '结论')"
            >复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-if="!isReadonly"
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写评价结论"
        @change="saveConclusion"
      />
      <div v-else class="conclusion-text">{{ conclusion || '—' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p v-for="(hint, idx) in hints" :key="idx">{{ idx + 1 }}. {{ hint }}</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S12EvaluationSheet.vue — S12 评价类子表通用组件
 *
 * 复用于 S12-1/S12-1-1/S12-2/S12-3/S12-3-1 五个评价 checklist 类型子表。
 * 通过 sheetKey 和 title 区分不同 sheet。
 *
 * 功能：
 * - checklist 格式的评价表（评价项目/内容/结果/说明）
 * - 方法论上下文（琥珀色块）
 * - 结论区 el-card + AI 按钮
 * - GtIndexChip 跨底稿引用
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.3
 * Requirements: 4.1, 4.2
 */
import { ref, computed, inject } from 'vue'
import { defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useSExpertPersist } from '../composables/useSExpertPersist'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  sheetKey: string
  title: string
  /** 主入口透传的持久化快照（已解包纯 Map） */
  allResponses?: Map<string, any>
}>()

// ─── 复核对话 ────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog')

function handleOpenReview(sectionId: string, label: string) {
  openReviewDialog?.(sectionId, label)
}

// ─── 审计目标 ────────────────────────────────────────────────────────────────

const auditObjective = computed(() => {
  const objMap: Record<string, string> = {
    'S12-1': '评价注册会计师的专家是否具有实现审计目的所必需的胜任能力、专业素质和客观性。',
    'S12-1-1': '识别并评价可能影响专家客观性的利益关系、雇佣关系及其他威胁，并评估已采取防范措施的有效性。',
    'S12-2': '充分了解专家的专长领域，确认其专业知识与审计目标中相关事项相匹配，以确定专家工作能否实现审计目的。',
    'S12-3': '评价专家工作结果的恰当性，包括假设和方法的适当性、源数据的相关性和完整性、结论与其他审计证据的一致性。',
    'S12-3-1': '获取并审阅专家出具的报告，评价报告内容是否充分、明确且能支持其结论。',
  }
  return objMap[props.sheetKey] || '评价注册会计师的专家工作，为相关审计事项获取充分、适当的审计证据。'
})

// ─── 方法论上下文 ────────────────────────────────────────────────────────────

const methodologyContext = computed(() => {
  const contextMap: Record<string, string> = {
    'S12-1': '《中国注册会计师审计准则第1421号》第8条：注册会计师应当评价专家是否具有实现审计目的所必需的胜任能力、专业素质和客观性。',
    'S12-1-1': '如果专家与被审计单位存在利益关系，或者存在其他可能影响其客观性的情形，注册会计师应当评价其对审计工作的影响程度。',
    'S12-2': '注册会计师应当充分了解专家的专长领域，以便能够确定专家的工作是否足以实现审计目的。',
    'S12-3': '注册会计师应当评价专家工作结果的恰当性，包括：假设和方法是否适合具体情况；源数据是否相关和完整；结论是否与审计证据一致。',
    'S12-3-1': '注册会计师应当获取并审阅专家的报告，评价报告内容是否充分支持其结论。',
  }
  return contextMap[props.sheetKey] || ''
})

// ─── 评价行数据（基于 sheetKey 生成骨架） ────────────────────────────────────

const evaluationRows = ref(getInitialRows(props.sheetKey))

function getInitialRows(key: string) {
  const rowsMap: Record<string, Array<{ category: string; criterion: string; result: string; remark: string; ref: string }>> = {
    'S12-1': [
      { category: '胜任能力', criterion: '专家是否具有相关学历和专业资格（如评估师资格、精算师资格等）', result: '', remark: '', ref: '' },
      { category: '胜任能力', criterion: '专家是否具有与审计相关事项匹配的执业经验', result: '', remark: '', ref: '' },
      { category: '专业素质', criterion: '专家是否遵守相关职业道德要求和执业准则', result: '', remark: '', ref: '' },
      { category: '专业素质', criterion: '专家在类似项目中的历史工作质量', result: '', remark: '', ref: '' },
      { category: '客观性', criterion: '专家与被审计单位之间是否存在利益关系', result: '', remark: '', ref: 'S12-1-1' },
      { category: '客观性', criterion: '专家是否受被审计单位管理层的不当影响', result: '', remark: '', ref: 'S12-1-1' },
    ],
    'S12-1-1': [
      { category: '利益关系', criterion: '专家（或其近亲属）是否持有被审计单位的股份或其他经济利益', result: '', remark: '', ref: '' },
      { category: '利益关系', criterion: '专家是否同时向被审计单位提供咨询或其他服务', result: '', remark: '', ref: '' },
      { category: '雇佣关系', criterion: '专家是否曾为被审计单位的雇员或董事', result: '', remark: '', ref: '' },
      { category: '雇佣关系', criterion: '专家的薪酬是否取决于审计结果或被审计单位的财务表现', result: '', remark: '', ref: '' },
      { category: '其他威胁', criterion: '是否存在密切关系威胁（长期合作、私人关系等）', result: '', remark: '', ref: '' },
      { category: '其他威胁', criterion: '是否存在外在压力威胁（管理层施压、时间限制等）', result: '', remark: '', ref: '' },
      { category: '防范措施', criterion: '针对已识别威胁，是否已采取适当防范措施', result: '', remark: '', ref: '' },
    ],
    'S12-2': [
      { category: '专长领域', criterion: '专家的专业领域是否与所需评价的事项相关（如评估/精算/工程/法律）', result: '', remark: '', ref: '' },
      { category: '专长领域', criterion: '专家在特定行业或专门领域的知识深度', result: '', remark: '', ref: '' },
      { category: '方法论', criterion: '专家使用的方法、模型是否得到该领域的普遍认可', result: '', remark: '', ref: '' },
      { category: '方法论', criterion: '专家是否了解相关会计准则对估值/计量的要求', result: '', remark: '', ref: '' },
      { category: '数据来源', criterion: '专家所使用的数据来源是否可靠且与审计目标一致', result: '', remark: '', ref: '' },
    ],
    'S12-3': [
      { category: '假设和方法', criterion: '专家采用的假设是否合理并适用于具体情况', result: '', remark: '', ref: '' },
      { category: '假设和方法', criterion: '专家使用的方法是否适当（如收益法/市场法/成本法选择依据）', result: '', remark: '', ref: '' },
      { category: '源数据', criterion: '专家工作所依据的源数据是否相关、完整和准确', result: '', remark: '', ref: '' },
      { category: '源数据', criterion: '源数据与被审计单位会计记录及其他审计证据是否一致', result: '', remark: '', ref: '' },
      { category: '结论一致性', criterion: '专家的工作结论是否与其他审计证据一致', result: '', remark: '', ref: '' },
      { category: '结论一致性', criterion: '如存在不一致，是否已充分调查并取得解释', result: '', remark: '', ref: '' },
      { category: '总体评价', criterion: '综合以上因素，专家工作结果是否可用作审计证据', result: '', remark: '', ref: 'S12-3-1' },
    ],
    'S12-3-1': [
      { category: '报告完整性', criterion: '专家报告是否包含结论/意见、范围说明和所用假设', result: '', remark: '', ref: '' },
      { category: '报告完整性', criterion: '报告是否注明使用的方法和模型', result: '', remark: '', ref: '' },
      { category: '报告完整性', criterion: '报告是否列示重要的限制条件和前提条件', result: '', remark: '', ref: '' },
      { category: '结论明确性', criterion: '专家的结论/意见是否明确且便于理解', result: '', remark: '', ref: '' },
      { category: '结论明确性', criterion: '结论中是否有保留意见或强调事项', result: '', remark: '', ref: '' },
      { category: '报告使用', criterion: '报告目的是否与审计目的一致', result: '', remark: '', ref: '' },
    ],
  }
  return rowsMap[key] || []
}

// ─── 结论 ────────────────────────────────────────────────────────────────────

const conclusion = ref('')

// ─── 持久化接线（load + save，item_id 按 sheetKey） ──────────────────────────

const rowsId = `${props.sheetKey}-rows`
const conclusionId = `${props.sheetKey}-conclusion`

const { seedOnMount, save } = useSExpertPersist(() => props.allResponses)
seedOnMount([
  { itemId: rowsId, ref: evaluationRows },
  { itemId: conclusionId, ref: conclusion },
])

function saveRows(): void {
  save(rowsId, evaluationRows.value)
}

function saveConclusion(): void {
  save(conclusionId, conclusion.value)
}

// ─── 编制提示 ────────────────────────────────────────────────────────────────

const hints = computed(() => {
  const hintsMap: Record<string, string[]> = {
    'S12-1': [
      '根据 ISA 620/CAS 1421，评价专家的胜任能力、专业素质和客观性。',
      '胜任能力应关注学历、资格证书、执业年限和相关经验。',
      '客观性评价详细内容请参见 S12-1-1。',
    ],
    'S12-1-1': [
      '逐项评价可能影响专家客观性的威胁因素。',
      '如存在重大威胁且无法有效防范，应考虑不利用该专家的工作。',
      '记录防范措施的具体内容和效果。',
    ],
    'S12-2': [
      '确认专家的专长领域与审计所需的专业知识匹配。',
      '了解专家采用的方法论是否被该领域普遍接受。',
      '如有疑虑，考虑咨询其他专家或扩大审计程序范围。',
    ],
    'S12-3': [
      '重点关注假设的合理性、方法的适当性和源数据的可靠性。',
      '评价专家结论与其他审计证据的一致性。',
      '如结论不一致，应追加程序或获取进一步解释。',
    ],
    'S12-3-1': [
      '获取专家报告原件，核查报告的完整性和准确性。',
      '关注报告中的保留意见或限制条件对审计结论的影响。',
      '评价报告的使用范围是否适当。',
    ],
  }
  return hintsMap[props.sheetKey] || ['请根据实际情况填写评价内容。']
})

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiAssist() {
  // TODO: 调用 AI 辅助生成评价说明
}

function handleAiConclusion() {
  // TODO: 调用 AI 辅助生成评价结论
}
</script>

<style scoped>
.s12-evaluation {
  padding: 12px;
}

.audit-objective {
  margin-bottom: 12px;
}

.audit-objective-text {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
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

.methodology-context {
  margin-bottom: 12px;
  padding: 10px 14px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
}

.conclusion-card {
  margin-top: 16px;
}

.conclusion-text {
  white-space: pre-wrap;
  font-size: var(--wp-font-size, 13px);
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
