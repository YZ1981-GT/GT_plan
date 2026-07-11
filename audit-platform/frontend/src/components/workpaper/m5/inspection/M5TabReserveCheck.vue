<template>
  <div class="m5-tab-reserve-check">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M5-5 盈余公积检查表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          权益类·贷方余额
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>盈余公积检查要点：</strong>
        ①法定盈余公积按净利润（弥补以前年度亏损后）10%计提，累计达注册资本50%可不再计提。
        ②任意盈余公积计提须有股东大会决议。
        ③转增资本后法定盈余公积不得低于注册资本25%。
        ④弥补亏损须有决议且先用任意后用法定。
        ⑤核对M5-4计提检查表计提金额一致性及M5-2明细表勾稽。
      </div>
    </div>

    <!-- ═══ Section 1: 核对清单 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>核对清单</span>
          <div class="card-header-right">
            <el-button size="small" @click="handleAI('checklist')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <div class="checklist-section">
        <div v-for="(item, idx) in checklist" :key="idx" class="checklist-item">
          <span class="checklist-index">{{ idx + 1 }}.</span>
          <span class="checklist-text">{{ item.label }}</span>
          <el-radio-group
            v-if="!isReadonly"
            :model-value="item.passed"
            size="small"
            @change="(val: boolean | null) => updateChecklistItem(idx, val)"
          >
            <el-radio-button :value="true">通过</el-radio-button>
            <el-radio-button :value="false">不通过</el-radio-button>
          </el-radio-group>
          <el-tag
            v-else
            :type="item.passed === true ? 'success' : item.passed === false ? 'danger' : 'info'"
            size="small"
          >
            {{ item.passed === true ? '通过' : item.passed === false ? '不通过' : '待核' }}
          </el-tag>
        </div>
      </div>

      <!-- 不通过项备注 -->
      <div v-if="failedItems.length > 0" class="failed-notes">
        <el-divider content-position="left">不通过项说明</el-divider>
        <div v-for="fi in failedItems" :key="fi.idx" class="failed-note-item">
          <span class="failed-note-label">{{ fi.idx + 1 }}. {{ fi.label }}：</span>
          <el-input
            :model-value="fi.note"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            :disabled="isReadonly"
            placeholder="说明不通过原因..."
            @change="(val: string) => updateChecklistNote(fi.idx, val)"
          />
        </div>
      </div>
    </el-card>

    <!-- ═══ Section 2: 审计结论区 ═══ -->
    <el-card shadow="never" class="check-card conclusion-card">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <div class="card-header-right">
            <el-button size="small" @click="handleAI('conclusion')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <el-input
        :model-value="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="根据上述核对结果，填写盈余公积审计结论..."
        @change="(val: string) => setConclusion(val)"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>盈余公积（4101）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（计提增加） − 借方（转增/弥补减少）</li>
        <li><strong>法定盈余公积</strong>：净利润（弥补以前年度亏损后）× 10%，累计达注册资本50%时可不再计提</li>
        <li><strong>任意盈余公积</strong>：需股东大会决议，无固定比例限制</li>
        <li><strong>转增资本</strong>：转增后法定盈余公积余额不得低于注册资本25%</li>
        <li><strong>弥补亏损</strong>：先用任意盈余公积，后用法定盈余公积</li>
        <li>本期计提金额应与M5-4计提检查表结果一致</li>
        <li>本期明细应与M5-2明细表相互勾稽</li>
        <li>审定数应与试算表科目4101一致（TB回写）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M5TabReserveCheck — M5-5 盈余公积检查表（核对清单+结论区+AI辅助）
 *
 * Spec: .kiro/specs/m5-surplus-reserve/
 * Task: 4.5
 * Requirements: 5.1-5.2
 *
 * 功能：
 * - 核对清单：8项盈余公积相关检查项（el-radio-group 通过/不通过）
 * - 审计结论区（el-card包裹, textarea autosize + AI button）
 * - 每个文本section标题行右侧AI辅助按钮
 * - 复核按钮（inject openReviewDialog）
 * - 方法论上下文（琥珀色左边线）
 * - 编制提示 details 折叠底部
 *
 * 科目：4101 盈余公积（**贷方/权益类！**）
 * 核对关注：法定计提合规 / 任意计提决议 / 转增合规 / 弥补亏损决议 / M5-4/M5-2勾稽
 */
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM5FormData } from '../../composables/useM5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

interface ChecklistItem {
  label: string
  passed: boolean | null
  note: string
}

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>(
  'openReviewDialog',
  null,
)

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useM5FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 核对清单 ────────────────────────────────────────────────────────────────

const DEFAULT_CHECKLIST: ChecklistItem[] = [
  { label: '法定盈余公积计提是否符合公司法规定（净利润10%）', passed: null, note: '' },
  { label: '累计法定盈余公积是否达到注册资本50%', passed: null, note: '' },
  { label: '任意盈余公积计提是否有股东大会决议', passed: null, note: '' },
  { label: '盈余公积转增资本是否合规（转增后法定盈余公积≥注册资本25%）', passed: null, note: '' },
  { label: '盈余公积弥补亏损是否有决议', passed: null, note: '' },
  { label: '本期计提金额与M5-4计提检查表是否一致', passed: null, note: '' },
  { label: '本期明细与M5-2明细表是否一致', passed: null, note: '' },
  { label: '审定数与试算表(4101)是否一致', passed: null, note: '' },
]

const checklist = reactive<ChecklistItem[]>([...DEFAULT_CHECKLIST.map((c) => ({ ...c }))])
const conclusion = ref('')

// ─── Computed ────────────────────────────────────────────────────────────────

const failedItems = computed(() =>
  checklist
    .map((item, idx) => ({ ...item, idx }))
    .filter((item) => item.passed === false),
)

// ─── Actions ─────────────────────────────────────────────────────────────────

function updateChecklistItem(idx: number, val: boolean | null) {
  checklist[idx].passed = val
  _saveChecklist()
}

function updateChecklistNote(idx: number, val: string) {
  checklist[idx].note = val
  _saveChecklist()
}

function setConclusion(val: string) {
  conclusion.value = val
  formData.debouncedSave('M5-5-conclusion', { remark: val || null })
}

function _saveChecklist() {
  const data = checklist.map((item) => ({
    label: item.label,
    passed: item.passed,
    note: item.note,
  }))
  formData.saveField('M5-5-checklist-all', { remark: JSON.stringify(data) })
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAI(_section: string) {
  /* AI辅助待集成 */
}

function handleReview() {
  openReviewDialog?.('M5-5-reserve-check', '盈余公积检查表')
}

// ─── Restore ─────────────────────────────────────────────────────────────────

function _restoreData() {
  // 恢复清单
  const checklistData = formData.allResponses.value.get('M5-5-checklist-all')
  if (checklistData?.remark) {
    try {
      const parsed = JSON.parse(checklistData.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        for (let i = 0; i < checklist.length && i < parsed.length; i++) {
          checklist[i].passed = parsed[i].passed ?? null
          checklist[i].note = parsed[i].note ?? ''
        }
      }
    } catch { /* ignore */ }
  }

  // 恢复结论
  const conclusionData = formData.allResponses.value.get('M5-5-conclusion')
  if (conclusionData?.remark) conclusion.value = conclusionData.remark
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreData()
})
</script>

<style scoped>
.m5-tab-reserve-check {
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

/* ─── 方法论上下文（琥珀色） ──── */
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

/* ─── Check card ──── */
.check-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  color: #303133;
}

.card-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 核对清单 ──── */
.checklist-section {
  margin-bottom: 8px;
}

.checklist-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid #f2f6fc;
}

.checklist-item:last-child {
  border-bottom: none;
}

.checklist-index {
  font-weight: 600;
  color: #303133;
  min-width: 20px;
}

.checklist-text {
  flex: 1;
  color: #606266;
  line-height: 1.5;
}

/* ─── 不通过项说明 ──── */
.failed-notes {
  margin-top: 12px;
}

.failed-note-item {
  margin-bottom: 10px;
}

.failed-note-label {
  font-size: 12px;
  color: #f56c6c;
  font-weight: 500;
  display: block;
  margin-bottom: 4px;
}

/* ─── 审计结论 ──── */
.conclusion-card :deep(.el-card__body) {
  padding-top: 12px;
}

/* ─── 编制提示 ──── */
.m5-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.m5-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.m5-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
