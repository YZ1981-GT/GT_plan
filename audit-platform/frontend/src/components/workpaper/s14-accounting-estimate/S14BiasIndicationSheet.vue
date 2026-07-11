<template>
  <div class="s14-bias">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        评价管理层在作出会计估计时是否存在偏向的迹象（如假设/方法的系统性倾向、临近报告日的有利调整、选择性使用信息），并评估偏向迹象的累积影响是否导致财务报表整体的重大错报（CAS 1321）。
      </div>
    </el-alert>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S14-4 管理层偏向的迹象</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s14-4-bias', '管理层偏向的迹象')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <!-- 方法论上下文（琥珀色左边线） -->
      <div class="methodology-context">
        <p>《中国注册会计师审计准则第1321号》第21条：注册会计师应当评价管理层在作出会计估计时是否存在偏向的迹象。管理层偏向的迹象本身并不构成错报，但可能影响注册会计师对会计估计是否合理的评价。</p>
      </div>

      <el-table
        :data="biasItems"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="indicator" label="偏向迹象指标" min-width="320">
          <template #default="{ row }">
            <span>{{ row.indicator }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="exists" label="是否存在" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.exists"
              size="small"
              placeholder="—"
              style="width: 80px"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不确定" value="不确定" />
            </el-select>
            <span v-else>{{ row.exists || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="evidence" label="审计证据/说明" min-width="260">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.evidence"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              size="small"
              placeholder="填写支持判断的审计证据或说明"
            />
            <span v-else class="wrap-text">{{ row.evidence || '—' }}</span>
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
        placeholder="填写关于管理层偏向迹象的评价结论"
      />
      <div v-else class="conclusion-text">{{ auditConclusion || '—' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 回顾性分析：上期估计与实际结果的差异是否存在系统性方向。</p>
      <p>2. 管理层选择的假设和方法是否始终偏向乐观或悲观。</p>
      <p>3. 管理层是否在本期变更了会计估计方法，且变更导致了有利的结果。</p>
      <p>4. 管理层使用的点估计是否总是处于合理区间的一端。</p>
      <p>5. 如发现偏向迹象，评估其累积影响是否导致财务报表整体的重大错报。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S14BiasIndicationSheet.vue — S14-4 管理层偏向的迹象
 *
 * 功能：
 * - 展示 S14-4 管理层偏向评价表（24×11 checklist 格式）
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

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

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

// ─── 偏向评价项目（实际从 render-config 加载，此为骨架数据） ─────────────────

const biasItems = ref([
  {
    indicator: '管理层对上期会计估计作出了变更，且变更导致了对管理层有利的结果（如增加利润或改善财务比率）。',
    exists: '',
    evidence: '',
    ref: '',
  },
  {
    indicator: '管理层选择的点估计始终处于合理估计区间的同一端（如始终选择乐观端）。',
    exists: '',
    evidence: '',
    ref: '',
  },
  {
    indicator: '管理层在可选的估计方法中，选择了产生有利结果的方法。',
    exists: '',
    evidence: '',
    ref: '',
  },
  {
    indicator: '管理层使用的重大假设与市场参与者或行业惯例不一致，且偏差方向对管理层有利。',
    exists: '',
    evidence: '',
    ref: '',
  },
  {
    indicator: '管理层的会计估计在每个报告期末均偏向同一方向（回顾性分析揭示的系统性偏差）。',
    exists: '',
    evidence: '',
    ref: 'B40',
  },
  {
    indicator: '管理层在接近报告日时对会计估计作出重大调整，且调整方向对其有利。',
    exists: '',
    evidence: '',
    ref: '',
  },
  {
    indicator: '管理层选择性地使用支持其估计结论的信息，而忽视或不当加权与之矛盾的信息。',
    exists: '',
    evidence: '',
    ref: '',
  },
  {
    indicator: '当存在多个可能的估计结果时，管理层未合理解释为何选择了特定的点估计。',
    exists: '',
    evidence: '',
    ref: '',
  },
])

// ─── 审计结论 ────────────────────────────────────────────────────────────────

const auditConclusion = ref('')

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiAssist() {
  // TODO: 调用 AI 辅助
}

function handleAiConclusion() {
  // TODO: 调用 AI 辅助生成审计结论
}
</script>

<style scoped>
.s14-bias {
  padding: 12px;
}

.audit-objective {
  margin-bottom: 12px;
}

.audit-objective-text {
  font-size: 13px;
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
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

.wrap-text {
  white-space: pre-wrap;
  font-size: 13px;
}

.conclusion-card {
  margin-top: 16px;
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
