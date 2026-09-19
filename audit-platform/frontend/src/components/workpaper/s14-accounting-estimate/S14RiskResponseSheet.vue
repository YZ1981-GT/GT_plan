<template>
  <div class="s14-risk-response">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        针对评估的会计估计重大错报风险实施进一步审计程序：检验管理层作出估计的过程、必要时作出独立点/区间估计、评价截止日后事项，评价管理层估计的合理性或确定是否存在错报，并评价披露的充分性（CAS 1321）。
      </div>
    </el-alert>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S14-3 应对评估的重大错报风险（会计估计相关）</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s14-3-risk-response', '应对重大错报风险')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <!-- 方法论上下文（琥珀色左边线） -->
      <div class="methodology-context">
        <p>《中国注册会计师审计准则第1321号》第18条：注册会计师应当根据评估的重大错报风险，实施进一步审计程序以获取充分、适当的审计证据。应对措施包括：检验管理层作出会计估计的过程、利用独立作出的点估计或区间估计、评价截止日后事项等。</p>
      </div>

      <el-table
        :data="riskItems"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="riskArea" label="应对领域" width="160">
          <template #default="{ row }">
            <span class="category-text">{{ row.riskArea }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="procedure" label="审计程序" min-width="280">
          <template #default="{ row }">
            <span>{{ row.procedure }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="applicable" label="是否适用" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.applicable"
              size="small"
              placeholder="—"
              style="width: 80px"
              @change="saveRows"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="N/A" value="N/A" />
            </el-select>
            <span v-else>{{ row.applicable || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="result" label="执行结果" min-width="220">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.result"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              size="small"
              placeholder="填写执行结果"
              @change="saveRows"
            />
            <span v-else class="wrap-text">{{ row.result || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="评价结论" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.conclusion"
              size="small"
              placeholder="—"
              style="width: 100px"
              @change="saveRows"
            >
              <el-option label="满意" value="满意" />
              <el-option label="有保留" value="有保留" />
              <el-option label="不满意" value="不满意" />
            </el-select>
            <span v-else>{{ row.conclusion || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ref" label="索引" width="100" align="center">
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
          <span>审计结论</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiConclusion"
            >AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-if="!isReadonly"
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写关于应对会计估计重大错报风险的审计结论"
        @change="saveConclusion"
      />
      <div v-else class="conclusion-text">{{ auditConclusion || '—' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 根据评估的风险水平确定进一步审计程序的性质、时间安排和范围。</p>
      <p>2. 可选择以下一种或多种应对方式：检验管理层作出估计的过程、利用审计师独立作出的估计、评价截止日后事项。</p>
      <p>3. 对于特别风险，需要获取充分适当审计证据以评价管理层假设的合理性。</p>
      <p>4. 考虑是否需要利用注册会计师的专家的工作。</p>
      <p>5. 评价会计估计的合理性，或确定是否存在错报。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S14RiskResponseSheet.vue — S14-3 应对评估的重大错报风险（会计估计相关）
 *
 * 功能：
 * - 展示 S14-3 风险应对程序表（73×11 checklist 格式）
 * - 方法论上下文区块（琥珀色左边线）
 * - GtIndexChip 跨底稿引用
 * - 审计结论区 el-card + AI 按钮
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.4
 * Requirements: 5.1
 */
import { ref, inject } from 'vue'
import { defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useSExpertPersist } from '../composables/useSExpertPersist'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  /** 主入口透传的持久化快照（已解包纯 Map） */
  allResponses?: Map<string, any>
}>()

// ─── 复核对话 ────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog')

function handleOpenReview(sectionId: string, label: string) {
  openReviewDialog?.(sectionId, label)
}

// ─── 风险应对项目（骨架数据，seed 时从 responses 覆盖） ─────────────────

const riskItems = ref([
  {
    riskArea: '检验管理层过程',
    procedure: '检验管理层用于作出会计估计的方法是否适当，以及假设是否合理。',
    applicable: '是',
    result: '',
    conclusion: '',
    ref: '',
  },
  {
    riskArea: '检验管理层过程',
    procedure: '测试管理层用于作出会计估计的数据的完整性、相关性和准确性。',
    applicable: '是',
    result: '',
    conclusion: '',
    ref: '',
  },
  {
    riskArea: '检验管理层过程',
    procedure: '评估管理层使用的假设是否彼此一致，是否与相关行业惯例和经济环境一致。',
    applicable: '是',
    result: '',
    conclusion: '',
    ref: 'B22',
  },
  {
    riskArea: '独立估计',
    procedure: '是否需要利用独立作出的点估计或区间估计，以评价管理层的点估计是否合理？',
    applicable: '',
    result: '',
    conclusion: '',
    ref: '',
  },
  {
    riskArea: '独立估计',
    procedure: '如独立估计存在差异，分析差异原因并确定是否存在错报。',
    applicable: '',
    result: '',
    conclusion: '',
    ref: '',
  },
  {
    riskArea: '截止日后事项',
    procedure: '确定截至审计报告日发生的事项是否为会计估计提供了审计证据。',
    applicable: '是',
    result: '',
    conclusion: '',
    ref: 'B40',
  },
  {
    riskArea: '特别风险',
    procedure: '对具有高度估计不确定性的会计估计（特别风险），评价估计不确定性的程度。',
    applicable: '是',
    result: '',
    conclusion: '',
    ref: 'B10',
  },
  {
    riskArea: '特别风险',
    procedure: '获取充分适当审计证据，评价管理层对特别风险相关假设的合理性。',
    applicable: '是',
    result: '',
    conclusion: '',
    ref: '',
  },
  {
    riskArea: '披露充分性',
    procedure: '评价与会计估计相关的披露是否充分（包括估计不确定性的披露）。',
    applicable: '是',
    result: '',
    conclusion: '',
    ref: '',
  },
  {
    riskArea: '整体评价',
    procedure: '基于所获取的审计证据，形成关于会计估计在财务报表中是否合理的结论。',
    applicable: '是',
    result: '',
    conclusion: '',
    ref: '',
  },
])

// ─── 审计结论 ────────────────────────────────────────────────────────────────

const auditConclusion = ref('')

// ─── 持久化接线（load + save） ────────────────────────────────────────────────

const ROWS_ID = 'S14-3-rows'
const CONCLUSION_ID = 'S14-3-conclusion'

const { seedOnMount, save } = useSExpertPersist(() => props.allResponses)
seedOnMount([
  { itemId: ROWS_ID, ref: riskItems },
  { itemId: CONCLUSION_ID, ref: auditConclusion },
])

function saveRows(): void {
  save(ROWS_ID, riskItems.value)
}

function saveConclusion(): void {
  save(CONCLUSION_ID, auditConclusion.value)
}

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiAssist() {
  // TODO: 调用 AI 辅助
}

function handleAiConclusion() {
  // TODO: 调用 AI 辅助生成审计结论
}
</script>

<style scoped>
.s14-risk-response {
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
  margin-bottom: 16px;
  padding: 12px 16px;
  border-left: 4px solid #e6a23c;
  background-color: #fdf6ec;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
  color: #606266;
}

.category-text {
  font-size: 12px;
  color: #606266;
}

.wrap-text {
  white-space: pre-wrap;
  font-size: var(--wp-font-size, 13px);
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
