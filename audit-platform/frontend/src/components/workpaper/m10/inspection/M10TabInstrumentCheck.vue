<template>
  <div class="m10-tab-instrument-check">
    <!-- ═══ 标题 + 按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M10-5 其他权益工具检查表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          科目4003·权益类贷方
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>其他权益工具检查表（M10-5）：</strong>
        核对其他权益工具条款一致性、发行/赎回授权、利息/股息准确性、CAS37分类一致性、列报正确性、披露充分性、明细合计核对。
        交叉引用M10-2明细表及M10-4负债与权益区分检查结论。每项检查设通过/异常/不适用状态。
      </div>
    </div>

    <!-- ═══ 检查项列表（每个section标题右侧AI按钮） ═══ -->
    <div class="check-items-list">
      <el-card
        v-for="item in instrumentCheck.checkItems.value"
        :key="item.index"
        shadow="never"
        class="check-item-card"
      >
        <template #header>
          <div class="card-header">
            <span class="check-item-title">{{ item.index }}. {{ item.description }}</span>
            <el-button size="small" @click="handleAI(item.sectionId)">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
          </div>
        </template>

        <!-- 检查方法 -->
        <div class="check-method">
          <span class="method-label">检查方法：</span>
          <span class="method-text">{{ item.method }}</span>
        </div>

        <!-- 状态切换 -->
        <div class="check-status-row">
          <span class="status-label">检查状态：</span>
          <el-radio-group
            :model-value="item.status"
            :disabled="isReadonly"
            size="small"
            @change="(val: any) => instrumentCheck.updateCheckStatus(item.index, val)"
          >
            <el-radio-button value="passed">
              <el-icon><CircleCheckFilled /></el-icon> 通过
            </el-radio-button>
            <el-radio-button value="failed">
              <el-icon><CircleCloseFilled /></el-icon> 异常
            </el-radio-button>
            <el-radio-button value="na">
              不适用
            </el-radio-button>
          </el-radio-group>
          <el-tag
            v-if="item.status === 'passed'"
            type="success"
            size="small"
            effect="plain"
          >无异常</el-tag>
          <el-tag
            v-else-if="item.status === 'failed'"
            type="danger"
            size="small"
            effect="plain"
          >存在异常</el-tag>
          <el-tag
            v-else-if="item.status === 'na'"
            type="info"
            size="small"
            effect="plain"
          >不适用</el-tag>
        </div>

        <!-- 交叉引用（如有） -->
        <div v-if="item.crossRef" class="cross-ref-row">
          <span class="crossref-label">交叉引用：</span>
          <GtIndexChip :value="item.crossRef" />
          <span v-if="item.crossRefValue !== null" class="crossref-value">
            值: {{ item.crossRefValue }}
          </span>
        </div>

        <!-- 审计师说明 -->
        <div class="auditor-note-row">
          <el-input
            :model-value="item.auditorNote"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :readonly="isReadonly"
            placeholder="审计师说明/工作描述..."
            @change="(val: string) => instrumentCheck.updateAuditorNote(item.index, val)"
          />
        </div>
      </el-card>
    </div>

    <!-- ═══ 完成率 ═══ -->
    <div class="completion-section">
      <el-progress
        :percentage="instrumentCheck.completionRate.value"
        :stroke-width="6"
        :format="(p: number) => `${p}% 已完成`"
      />
    </div>

    <!-- ═══ 审计结论区（el-card包裹） ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header">
          <span class="conclusion-title">审计结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>

      <div class="conclusion-fields">
        <!-- 总体结论 -->
        <div class="conclusion-field">
          <label class="field-label">总体结论</label>
          <el-input
            :model-value="instrumentCheck.conclusionData.value.overallConclusion"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            :readonly="isReadonly"
            placeholder="根据以上检查程序，对其他权益工具的总体审计结论..."
            @change="(val: string) => instrumentCheck.updateConclusion('overallConclusion', val)"
          />
        </div>

        <!-- 是否存在重大异常 -->
        <div class="conclusion-field">
          <label class="field-label">是否存在重大异常</label>
          <el-switch
            :model-value="instrumentCheck.conclusionData.value.hasMaterialIssue"
            :disabled="isReadonly"
            active-text="是"
            inactive-text="否"
            @change="(val: any) => instrumentCheck.updateConclusion('hasMaterialIssue', val)"
          />
        </div>

        <!-- 异常事项描述 -->
        <div v-if="instrumentCheck.conclusionData.value.hasMaterialIssue" class="conclusion-field">
          <label class="field-label">异常事项描述</label>
          <el-input
            :model-value="instrumentCheck.conclusionData.value.issueDescription"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :readonly="isReadonly"
            placeholder="描述发现的异常事项..."
            @change="(val: string) => instrumentCheck.updateConclusion('issueDescription', val)"
          />
        </div>

        <!-- 后续程序建议 -->
        <div v-if="instrumentCheck.conclusionData.value.hasMaterialIssue" class="conclusion-field">
          <label class="field-label">后续程序建议</label>
          <el-input
            :model-value="instrumentCheck.conclusionData.value.furtherProcedures"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :readonly="isReadonly"
            placeholder="建议执行的后续审计程序..."
            @change="(val: string) => instrumentCheck.updateConclusion('furtherProcedures', val)"
          />
        </div>
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m10-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>逐项核对其他权益工具（永续债/优先股）的关键条款</li>
        <li>确认CAS37分类结论与M10-4检查结果一致</li>
        <li>核对明细表M10-2合计与审定表M10-1一致</li>
        <li>检查利息/股息计提是否按合同约定的利率/股息率准确计算</li>
        <li>权益工具在权益列报，负债部分在负债列报</li>
        <li>附注需按CAS37要求充分披露分类依据和重要条款</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M10TabInstrumentCheck — M10-5 其他权益工具检查表
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
 * Task: 4.5
 * Requirements: 5.1-5.2
 *
 * 功能：
 * - 7项默认检查项，每项带状态切换（passed/failed/na）
 * - 每个section标题行右侧AI辅助按钮
 * - 交叉引用M10-2明细表数据（GtIndexChip展示）
 * - 审计结论区（el-card包裹）
 * - 使用 useM10InstrumentCheck composable
 */
import { computed, inject, onMounted } from 'vue'
import { MagicStick, Check, CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useM10FormData } from '../../composables/useM10FormData'
import { useM10InstrumentCheck } from '../../composables/useM10InstrumentCheck'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useM10FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── InstrumentCheck composable ──────────────────────────────────────────────

const instrumentCheck = useM10InstrumentCheck(formData)

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAI(_section: string) {
  // AI辅助钩子（Phase 6集成）
}

function handleReview() {
  openReviewDialog?.('M10-5-instrument-check', '其他权益工具检查表')
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreCheckData(): void {
  for (let i = 1; i <= instrumentCheck.checkItems.value.length; i++) {
    const resp = formData.allResponses.value.get(`M10-5-check-${i}-data`)
    if (resp?.remark) {
      try {
        const data = JSON.parse(resp.remark)
        const item = instrumentCheck.checkItems.value.find(c => c.index === i)
        if (item) {
          item.status = data.status || 'pending'
          item.conclusion = data.conclusion || ''
          item.auditorNote = data.auditorNote || ''
          item.refIndex = data.refIndex || ''
          item.remark = data.remark || ''
        }
      } catch { /* skip invalid */ }
    }
  }
  // 恢复结论
  const conclusionResp = formData.allResponses.value.get('M10-5-conclusion')
  if (conclusionResp?.remark) {
    try {
      const data = JSON.parse(conclusionResp.remark)
      instrumentCheck.conclusionData.value = { ...instrumentCheck.conclusionData.value, ...data }
    } catch { /* skip */ }
  }
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreCheckData()
})
</script>

<style scoped>
.m10-tab-instrument-check {
  padding: 12px;
  font-size: 13px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.section-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.equity-badge {
  font-weight: 600;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}

.methodology-text {
  font-size: 13px;
  color: #6b5900;
  line-height: 1.6;
}

/* ─── 检查项列表 ─── */
.check-items-list {
  margin-bottom: 16px;
}

.check-item-card {
  margin-bottom: 12px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.check-item-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.check-method {
  margin-bottom: 12px;
  font-size: 13px;
  color: #606266;
}

.method-label {
  font-weight: 500;
  color: #909399;
}

.method-text {
  color: #606266;
}

.check-status-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.status-label {
  font-size: 13px;
  font-weight: 500;
  color: #909399;
  white-space: nowrap;
}

.cross-ref-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 13px;
}

.crossref-label {
  color: #909399;
  font-weight: 500;
}

.crossref-value {
  color: #409eff;
  font-weight: 500;
}

.auditor-note-row {
  margin-top: 8px;
}

/* ─── 完成率 ─── */
.completion-section {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}

/* ─── 审计结论 ─── */
.conclusion-card {
  margin-bottom: 16px;
}

.conclusion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.conclusion-fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.conclusion-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  font-weight: 500;
  color: #606266;
}

/* ─── 编制提示 ─── */
.m10-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.m10-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.m10-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
