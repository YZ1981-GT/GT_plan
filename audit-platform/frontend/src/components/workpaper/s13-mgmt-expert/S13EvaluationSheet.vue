<template>
  <div class="s13-evaluation">
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
              @click="handleOpenReview(`s13-eval-${sheetKey}`, title)"
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
              @click="handleOpenReview(`s13-eval-${sheetKey}-conclusion`, '结论')"
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
 * S13EvaluationSheet.vue — S13 评价类子表通用组件
 *
 * 复用于 S13-1/S13-2/S13-3/S13-3-1 四个评价 checklist 类型子表。
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
    'S13-1': '评价管理层的专家是否具有实现管理层目的所必需的胜任能力、专业素质和客观性，尤其关注其客观性可能受被审计单位控制或影响的情形。',
    'S13-2': '了解管理层的专家的工作性质、范围、目标、假设、方法和数据来源，为评价其工作结果的适当性奠定基础。',
    'S13-3': '评价管理层的专家工作结果的适当性，包括源数据的相关性与可靠性、假设和方法的合理性，以及结论与其他审计证据的一致性。',
    'S13-3-1': '获取并审阅管理层的专家出具的报告，评价其发现事项、结论和建议是否充分支持财务报表相关认定。',
  }
  return objMap[props.sheetKey] || '评价管理层的专家编制信息作为审计证据的可靠性与适当性。'
})

// ─── 方法论上下文 ────────────────────────────────────────────────────────────

const methodologyContext = computed(() => {
  const contextMap: Record<string, string> = {
    'S13-1': '《中国注册会计师审计准则第1322号》：注册会计师应当评价管理层的专家是否具有实现管理层目的所必需的胜任能力、专业素质和客观性。管理层的专家的客观性可能受到被审计单位控制的影响。',
    'S13-2': '注册会计师应当在必要时通过以下方式了解管理层的专家的工作：与管理层或专家讨论；审阅专家的报告或备忘录；了解专家使用的假设和方法。',
    'S13-3': '注册会计师应当考虑管理层的专家工作结果的适当性，包括：评价源数据的相关性和可靠性；评价假设和方法的合理性；评价工作结果是否与其他审计证据一致。',
    'S13-3-1': '注册会计师应当获取并审阅管理层的专家出具的报告，评价报告中的发现事项、结论和建议是否与审计相关。',
  }
  return contextMap[props.sheetKey] || ''
})

// ─── 评价行数据（基于 sheetKey 生成骨架） ────────────────────────────────────

const evaluationRows = ref(getInitialRows(props.sheetKey))

function getInitialRows(key: string) {
  const rowsMap: Record<string, Array<{ category: string; criterion: string; result: string; remark: string; ref: string }>> = {
    'S13-1': [
      { category: '胜任能力', criterion: '管理层的专家是否具有相关学历和专业资格', result: '', remark: '', ref: '' },
      { category: '胜任能力', criterion: '管理层的专家是否具有与相关事项匹配的执业经验', result: '', remark: '', ref: '' },
      { category: '胜任能力', criterion: '管理层的专家在类似事项上的历史业绩记录', result: '', remark: '', ref: '' },
      { category: '专业素质', criterion: '管理层的专家是否遵守相关职业道德要求', result: '', remark: '', ref: '' },
      { category: '专业素质', criterion: '管理层的专家是否遵守适用的执业准则或行业标准', result: '', remark: '', ref: '' },
      { category: '客观性', criterion: '管理层的专家是否受被审计单位管理层控制或影响', result: '', remark: '', ref: '' },
      { category: '客观性', criterion: '管理层的专家与被审计单位之间是否存在利益关系或雇佣关系', result: '', remark: '', ref: '' },
      { category: '客观性', criterion: '管理层的专家的薪酬是否取决于特定结果', result: '', remark: '', ref: '' },
    ],
    'S13-2': [
      { category: '工作性质', criterion: '管理层的专家工作涉及哪些财务报表领域（如估值/精算/法律）', result: '', remark: '', ref: '' },
      { category: '工作范围', criterion: '专家工作的范围和限制是否明确', result: '', remark: '', ref: '' },
      { category: '工作范围', criterion: '专家工作结果将如何用于编制财务报表', result: '', remark: '', ref: '' },
      { category: '假设', criterion: '专家工作所依据的假设和前提条件', result: '', remark: '', ref: '' },
      { category: '假设', criterion: '假设是否由管理层指定或由专家独立确定', result: '', remark: '', ref: '' },
      { category: '方法', criterion: '专家使用的方法是否得到该领域普遍认可', result: '', remark: '', ref: '' },
      { category: '方法', criterion: '专家是否考虑了替代方法及其选择理由', result: '', remark: '', ref: '' },
      { category: '数据来源', criterion: '专家使用的源数据来源及其可靠性', result: '', remark: '', ref: '' },
      { category: '时间基准', criterion: '专家工作的估值日/计量日是否与报告日匹配', result: '', remark: '', ref: '' },
    ],
    'S13-3': [
      { category: '假设合理性', criterion: '管理层的专家使用的假设是否合理并适用于具体情况', result: '', remark: '', ref: '' },
      { category: '假设合理性', criterion: '关键假设是否与可观察的市场数据或行业数据一致', result: '', remark: '', ref: '' },
      { category: '方法适当性', criterion: '所用方法是否适合相关事项的特征', result: '', remark: '', ref: '' },
      { category: '方法适当性', criterion: '方法的应用是否与会计准则的计量要求一致', result: '', remark: '', ref: '' },
      { category: '数据可靠性', criterion: '源数据是否相关、完整和准确', result: '', remark: '', ref: '' },
      { category: '数据可靠性', criterion: '源数据与被审计单位会计记录及其他证据是否一致', result: '', remark: '', ref: '' },
      { category: '结论一致性', criterion: '专家结论是否与其他审计证据一致', result: '', remark: '', ref: '' },
      { category: '结论一致性', criterion: '如存在不一致，原因是否已充分调查', result: '', remark: '', ref: '' },
      { category: '总体评价', criterion: '综合以上因素，管理层的专家工作结果是否可接受', result: '', remark: '', ref: 'S13-3-1' },
    ],
    'S13-3-1': [
      { category: '报告完整性', criterion: '管理层专家报告是否包含结论/意见、范围、所用假设和方法', result: '', remark: '', ref: '' },
      { category: '报告完整性', criterion: '报告是否列示重要的限制条件和前提条件', result: '', remark: '', ref: '' },
      { category: '报告完整性', criterion: '报告是否注明使用的数据来源', result: '', remark: '', ref: '' },
      { category: '结论明确性', criterion: '报告的结论/意见是否明确且便于理解', result: '', remark: '', ref: '' },
      { category: '结论明确性', criterion: '结论中是否有保留意见或重要强调事项', result: '', remark: '', ref: '' },
      { category: '报告使用', criterion: '报告目的是否与管理层编制财务报表的需要一致', result: '', remark: '', ref: '' },
      { category: '报告使用', criterion: '报告日期与财务报告期间是否匹配', result: '', remark: '', ref: '' },
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
    'S13-1': [
      '管理层的专家的客观性评价尤为重要——因其受管理层聘用或委托，可能缺乏独立性。',
      '关注专家薪酬是否与特定估值结果挂钩。',
      '如客观性存在重大疑虑，考虑是否需要利用注册会计师的专家（S12）。',
    ],
    'S13-2': [
      '通过审阅专家报告、与管理层讨论等方式了解专家工作。',
      '特别关注假设是由管理层指定还是专家独立确定。',
      '了解数据来源及其可靠性。',
    ],
    'S13-3': [
      '重点评价假设合理性、方法适当性和数据可靠性。',
      '如结论与其他审计证据不一致，需追加程序。',
      '参见 S13-3-1 专家报告及 S13-3-2/3-3/3-4 分领域详细评价。',
    ],
    'S13-3-1': [
      '审阅管理层专家报告原件，核查完整性。',
      '关注保留意见或限制条件对审计结论的影响。',
      '评价报告的使用范围是否与财务报告目的一致。',
    ],
  }
  return hintsMap[props.sheetKey] || ['请根据实际情况填写评价内容。']
})

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiAssist() {
  // TODO: 调用 AI 辅助
}

function handleAiConclusion() {
  // TODO: 调用 AI 辅助生成结论
}
</script>

<style scoped>
.s13-evaluation {
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
