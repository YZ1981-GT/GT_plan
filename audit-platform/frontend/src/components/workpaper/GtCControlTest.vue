<template>
  <div class="c-control-test" :class="{ 'is-readonly': state.isReadonly.value }">
    <!-- 已复核横幅 -->
    <div v-if="state.isReviewed.value" class="reviewed-banner">
      <el-icon><CircleCheckFilled /></el-icon>
      <span>已复核 — {{ state.reviewInfo.value?.reviewer }} {{ state.reviewInfo.value?.date }}</span>
    </div>

    <!-- 主 Tab -->
    <el-tabs v-model="activeTab" class="main-tabs">
      <el-tab-pane label="控制测试" name="main">
        <!-- 顶部设置栏 -->
        <div class="top-bar">
          <div class="cycle-info">
            <span class="cycle-name">{{ state.cycleName.value }}</span>
            <span class="wp-code-badge">{{ wpCode }}</span>
          </div>
          <div class="tolerable-rate-setting">
            <span>可容忍偏差率：</span>
            <el-input-number
              v-model="tolerableRatePercent"
              :min="0" :max="50" :step="1"
              :disabled="state.isReadonly.value"
              size="small"
              @change="onTolerableRateChange"
            />
            <span>%</span>
          </div>
          <div class="card-controls no-print">
            <el-button size="small" @click="state.expandAll()">全部展开</el-button>
            <el-button size="small" @click="state.collapseAll()">全部收起</el-button>
          </div>
        </div>

        <!-- B23 引用面板 -->
        <div class="b23-reference-panel">
          <div class="panel-header">
            <span class="panel-title">B23 控制点引用</span>
            <el-tag
              v-if="state.b23ControlPoints.value.length === 0"
              type="warning" size="small"
            >B23 尚未录入该循环控制点</el-tag>
            <el-button
              v-if="!state.isReadonly.value"
              class="no-print" size="small" type="primary" plain
              @click="state.addControlPoint()"
            >+ 新增控制点</el-button>
          </div>
          <div v-if="state.b23ControlPoints.value.length > 0" class="b23-list">
            <div v-for="bp in state.b23ControlPoints.value" :key="bp.controlId" class="b23-item">
              <span class="b23-id">{{ bp.controlId }}</span>
              <span class="b23-objective">{{ bp.objective }}</span>
            </div>
          </div>
        </div>

        <!-- 控制点卡片列表 -->
        <div class="control-points-list">
          <div
            v-for="cp in state.controlPoints.value"
            :key="cp.index"
            class="control-point-card"
            :style="{ borderLeftColor: getCardColor(cp.conclusion) }"
          >
            <!-- 卡片标题栏 -->
            <div class="card-header" @click="state.toggleCard(cp.index)">
              <div class="header-left">
                <span class="ctrl-index">{{ cp.index }}</span>
                <span class="ctrl-objective">{{ cp.objective || '(未命名控制点)' }}</span>
              </div>
              <div class="header-right">
                <el-tag v-if="cp.conclusion" :color="getCardBg(cp.conclusion)" size="small" effect="plain">
                  {{ cp.conclusion }}
                </el-tag>
                <span v-if="cp.deviationStats.deviationRate !== null" class="deviation-badge"
                  :class="{ exceed: cp.deviationStats.exceedsTolerable }"
                >
                  偏差率 {{ (cp.deviationStats.deviationRate * 100).toFixed(1) }}%
                </span>
                <el-icon class="expand-icon no-print">
                  <ArrowDown v-if="!expandedCards.has(cp.index)" />
                  <ArrowUp v-else />
                </el-icon>
              </div>
            </div>

            <!-- 卡片展开内容 -->
            <div v-show="expandedCards.has(cp.index)" class="card-body">
              <!-- 控制目标编辑 -->
              <div class="field-row">
                <label>控制目标</label>
                <el-input
                  :model-value="cp.objective"
                  :disabled="state.isReadonly.value"
                  placeholder="输入控制目标描述"
                  @input="(val: string) => onObjectiveChange(cp.index, val)"
                />
              </div>

              <!-- 测试方法多选 -->
              <div class="field-row">
                <label>测试方法</label>
                <el-checkbox-group
                  :model-value="cp.testMethods"
                  :disabled="state.isReadonly.value"
                  @change="(val: TestMethod[]) => state.setTestMethods(cp.index, val)"
                >
                  <el-checkbox label="询问" value="询问" />
                  <el-checkbox label="观察" value="观察" />
                  <el-checkbox label="检查" value="检查" />
                  <el-checkbox label="重新执行" value="重新执行" />
                </el-checkbox-group>
                <div v-if="cp.testMethods.includes('重新执行')" class="method-tip">
                  重新执行需逐笔记录执行过程
                </div>
              </div>

              <!-- 样本管理区域 -->
              <div class="samples-section">
                <div class="samples-header">
                  <span class="samples-count">样本量: {{ cp.samples.length }} 笔</span>
                  <div v-if="!state.isReadonly.value" class="samples-actions no-print">
                    <el-button size="small" @click="onAddSample(cp.index)">+ 添加样本</el-button>
                    <el-button size="small" @click="showBatchDialog(cp.index)">批量添加</el-button>
                  </div>
                </div>

                <div v-if="cp.samples.length === 0" class="empty-samples">
                  请添加测试样本
                </div>

                <div v-else class="samples-list">
                  <div
                    v-for="sample in cp.samples" :key="sample.index"
                    class="sample-row"
                    :class="{ 'deviation-highlight': sample.result === '偏差' }"
                  >
                    <span class="sample-index">{{ sample.index }}</span>
                    <el-input
                      :model-value="sample.voucherNo"
                      :disabled="state.isReadonly.value"
                      size="small" placeholder="凭证号"
                      class="sample-field"
                      @input="(val: string) => onSampleFieldChange(cp.index, sample.index, 'voucher', val)"
                    />
                    <el-input
                      :model-value="sample.date"
                      :disabled="state.isReadonly.value"
                      size="small" placeholder="日期"
                      class="sample-field"
                      @input="(val: string) => onSampleFieldChange(cp.index, sample.index, 'date', val)"
                    />
                    <el-input
                      :model-value="sample.amount"
                      :disabled="state.isReadonly.value"
                      size="small" placeholder="金额"
                      class="sample-field"
                      @input="(val: string) => onSampleFieldChange(cp.index, sample.index, 'amount', val)"
                    />
                    <el-radio-group
                      :model-value="sample.result"
                      :disabled="state.isReadonly.value"
                      size="small"
                      @change="(val: SampleResult) => state.setSampleResult(cp.index, sample.index, val)"
                    >
                      <el-radio-button value="有效">有效</el-radio-button>
                      <el-radio-button value="偏差">偏差</el-radio-button>
                      <el-radio-button value="不适用">不适用</el-radio-button>
                    </el-radio-group>
                    <el-button
                      v-if="!state.isReadonly.value"
                      class="no-print" size="small" type="danger" plain
                      @click="state.removeSample(cp.index, sample.index)"
                    >删除</el-button>
                    <!-- 偏差描述 -->
                    <div v-if="sample.result === '偏差'" class="deviation-desc-row">
                      <el-input
                        :model-value="sample.deviationDesc"
                        :disabled="state.isReadonly.value"
                        type="textarea" :rows="2"
                        placeholder="描述偏差情况"
                        @input="(val: string) => onDeviationDescChange(cp.index, sample.index, val)"
                      />
                    </div>
                  </div>
                </div>
              </div>

              <!-- 偏差统计 -->
              <div class="deviation-stats">
                <template v-if="cp.deviationStats.effectiveSamples === 0 && cp.samples.length > 0">
                  <span class="no-effective">无有效样本，无法计算偏差率</span>
                </template>
                <template v-else-if="cp.deviationStats.deviationRate !== null">
                  <span>偏差数: {{ cp.deviationStats.deviationCount }}</span>
                  <span> / 有效样本: {{ cp.deviationStats.effectiveSamples }}</span>
                  <span> = </span>
                  <span
                    class="rate-value"
                    :class="{ exceed: cp.deviationStats.exceedsTolerable }"
                  >{{ (cp.deviationStats.deviationRate * 100).toFixed(1) }}%</span>
                  <span v-if="cp.deviationStats.exceedsTolerable" class="exceed-warning">
                    超出可容忍偏差率
                  </span>
                </template>
              </div>

              <!-- 控制点结论 -->
              <div class="point-conclusion-section">
                <label>控制点结论</label>
                <div v-if="cp.suggestedConclusion" class="suggestion-tip">
                  系统建议: {{ cp.suggestedConclusion }}
                </div>
                <el-radio-group
                  :model-value="cp.conclusion"
                  :disabled="state.isReadonly.value"
                  @change="(val: ControlPointConclusion) => onPointConclusionChange(cp.index, val)"
                >
                  <el-radio value="控制有效运行">控制有效运行</el-radio>
                  <el-radio value="控制存在偏差但可接受">控制存在偏差但可接受</el-radio>
                  <el-radio value="控制无效">控制无效</el-radio>
                </el-radio-group>
                <div v-if="cp.conclusionOverridden" class="override-badge">
                  已手动调整 — {{ cp.overrideReason }}
                </div>
              </div>

              <!-- 删除控制点 -->
              <div v-if="!state.isReadonly.value" class="card-footer no-print">
                <el-button size="small" type="danger" plain @click="state.removeControlPoint(cp.index)">
                  删除此控制点
                </el-button>
              </div>
            </div>
          </div>
        </div>

        <!-- 循环级整体结论 -->
        <div class="cycle-conclusion-section">
          <h3>循环级整体结论</h3>
          <div v-if="state.suggestCycleConclusion.value" class="suggestion-tip">
            系统建议: {{ state.suggestCycleConclusion.value }}
          </div>
          <el-radio-group
            :model-value="state.cycleConclusion.value"
            :disabled="state.isReadonly.value"
            @change="onCycleConclusionChange"
          >
            <el-radio value="全部有效">全部有效</el-radio>
            <el-radio value="部分偏差">部分偏差</el-radio>
            <el-radio value="控制失效">控制失效</el-radio>
          </el-radio-group>
          <div v-if="state.isCycleConclusionOverridden.value" class="override-badge">
            已手动调整
          </div>
        </div>

        <!-- 联动面板 -->
        <div class="linkage-panel">
          <h4>关联底稿</h4>
          <div class="linkage-chips">
            <el-tag type="info" class="ref-chip">B23 {{ state.linkageInfo.value.b23WpCode }} (P{{ state.linkageInfo.value.b23ProcessNum }})</el-tag>
            <el-tag type="info" class="ref-chip">B50 风险评估</el-tag>
            <el-tag
              :type="state.linkageInfo.value.needsExtendedProcedures ? 'danger' : 'info'"
              class="ref-chip"
            >
              {{ state.linkageInfo.value.targetCycleCode }} {{ state.linkageInfo.value.targetCycleName }}
            </el-tag>
          </div>
          <div v-if="state.linkageInfo.value.needsExtendedProcedures" class="extended-warning">
            ⚠️ 控制失效 — 需扩大实质性程序范围
          </div>
        </div>

        <!-- 复核签字区域 -->
        <div class="review-section">
          <h4>现场经理复核</h4>
          <div v-if="state.pendingItems.value.length > 0" class="pending-list">
            <p>待完成事项：</p>
            <ul>
              <li v-for="(item, idx) in state.pendingItems.value" :key="idx">{{ item }}</li>
            </ul>
          </div>
          <el-button
            v-if="!state.isReadonly.value"
            type="primary"
            :disabled="!state.canReview.value"
            class="no-print"
            @click="onReview"
          >签字复核</el-button>
          <el-button
            v-if="state.isReviewed.value && !externalReadonly"
            type="warning" plain
            class="no-print"
            @click="showAmendDialog = true"
          >启动修改</el-button>
        </div>
      </el-tab-pane>

      <!-- 证据明细 Tab -->
      <el-tab-pane label="证据明细" name="evidence">
        <div class="evidence-tab">
          <p class="evidence-placeholder">暂无证据明细底稿（{{ wpCode }}-2）</p>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 批量添加对话框 -->
    <el-dialog v-model="batchDialogVisible" title="批量添加样本" width="400px">
      <el-form>
        <el-form-item label="起始凭证号">
          <el-input v-model="batchStart" placeholder="如: 001" />
        </el-form-item>
        <el-form-item label="截止凭证号">
          <el-input v-model="batchEnd" placeholder="如: 010" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onBatchAdd">确定</el-button>
      </template>
    </el-dialog>

    <!-- 覆盖理由对话框 -->
    <el-dialog v-model="overrideDialogVisible" title="调整理由" width="400px">
      <el-input v-model="overrideReason" type="textarea" :rows="3" placeholder="请填写手动调整理由" />
      <template #footer>
        <el-button @click="overrideDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!overrideReason.trim()" @click="confirmOverride">确定</el-button>
      </template>
    </el-dialog>

    <!-- 修改原因对话框 -->
    <el-dialog v-model="showAmendDialog" title="启动修改" width="400px">
      <el-input v-model="amendReason" type="textarea" :rows="3" placeholder="请填写修改原因" />
      <template #footer>
        <el-button @click="showAmendDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!amendReason.trim()" @click="onAmend">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted, onBeforeUnmount } from 'vue'
import { ArrowDown, ArrowUp, CircleCheckFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useCControlTestData } from './composables/useCControlTestData'
import {
  useCControlTest,
  CONTROL_TEST_COLORS,
  type TestMethod,
  type SampleResult,
  type ControlPointConclusion,
  type CycleConclusion,
} from './composables/useCControlTest'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode: string
  year: number
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── Derived ─────────────────────────────────────────────────────────────────

const cycleNum = computed(() => parseInt(props.wpCode.replace(/^C/i, ''), 10) || 2)
const externalReadonly = computed(() => props.readonly ?? false)
const wpIdRef = toRef(props, 'wpId')
const wpCodeRef = toRef(props, 'wpCode')

// ─── Composables ─────────────────────────────────────────────────────────────

const { allResponses, loading, saving, loadAll, saveImmediate, saveDebouncedText, flushPendingSave, getField, setFieldImmediate } =
  useCControlTestData(wpIdRef, cycleNum)

const state = useCControlTest(allResponses, cycleNum, wpCodeRef, saveImmediate, externalReadonly)

// ─── Local UI State ──────────────────────────────────────────────────────────

const activeTab = ref('main')
const expandedCards = state.expandedCards
const batchDialogVisible = ref(false)
const batchCtrlIndex = ref(1)
const batchStart = ref('')
const batchEnd = ref('')
const overrideDialogVisible = ref(false)
const overrideReason = ref('')
const overrideTarget = ref<{ type: 'point' | 'cycle'; index: number; conclusion: string }>({ type: 'point', index: 0, conclusion: '' })
const showAmendDialog = ref(false)
const amendReason = ref('')

const tolerableRatePercent = computed({
  get: () => Math.round(state.tolerableDeviationRate.value * 100),
  set: () => { /* handled by onTolerableRateChange */ },
})

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadAll()
  await state.loadB23Reference()
  // Expand first card if any exist
  if (state.controlPoints.value.length > 0) {
    state.expandedCards.value = new Set([1])
  }
})

onBeforeUnmount(() => {
  flushPendingSave()
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function getCardColor(conclusion: ControlPointConclusion | null): string {
  if (!conclusion) return '#d9d9d9'
  return CONTROL_TEST_COLORS[conclusion]?.color || '#d9d9d9'
}

function getCardBg(conclusion: ControlPointConclusion | null): string {
  if (!conclusion) return '#fafafa'
  return CONTROL_TEST_COLORS[conclusion]?.bg || '#fafafa'
}

function onTolerableRateChange(val: number | undefined): void {
  if (val === undefined) return
  state.setTolerableRate(val / 100)
}

function onObjectiveChange(ctrlIndex: number, val: string): void {
  const itemId = `C${cycleNum.value}-ctrl-${ctrlIndex}-objective`
  const item = { item_id: itemId, conclusion: null, remark: val, wp_ref: null }
  allResponses.value.set(itemId, item)
  saveDebouncedText(item)
}

function onSampleFieldChange(ctrlIndex: number, sampleIndex: number, field: string, val: string): void {
  const itemId = `C${cycleNum.value}-ctrl-${ctrlIndex}-sample-${sampleIndex}-${field}`
  const item = { item_id: itemId, conclusion: null, remark: val, wp_ref: null }
  allResponses.value.set(itemId, item)
  saveDebouncedText(item)
}

function onDeviationDescChange(ctrlIndex: number, sampleIndex: number, val: string): void {
  const itemId = `C${cycleNum.value}-ctrl-${ctrlIndex}-sample-${sampleIndex}-deviation`
  const item = { item_id: itemId, conclusion: null, remark: val, wp_ref: null }
  allResponses.value.set(itemId, item)
  saveDebouncedText(item)
}

function onAddSample(ctrlIndex: number): void {
  state.addSample(ctrlIndex, {})
}

function showBatchDialog(ctrlIndex: number): void {
  batchCtrlIndex.value = ctrlIndex
  batchStart.value = ''
  batchEnd.value = ''
  batchDialogVisible.value = true
}

function onBatchAdd(): void {
  state.addBatchSamples(batchCtrlIndex.value, { startVoucherNo: batchStart.value, endVoucherNo: batchEnd.value })
  batchDialogVisible.value = false
}

function onPointConclusionChange(ctrlIndex: number, val: ControlPointConclusion): void {
  const suggested = state.suggestPointConclusion(ctrlIndex).value
  if (suggested !== null && val !== suggested) {
    // Need override reason
    overrideTarget.value = { type: 'point', index: ctrlIndex, conclusion: val }
    overrideReason.value = ''
    overrideDialogVisible.value = true
  } else {
    state.setPointConclusion(ctrlIndex, val)
  }
}

function onCycleConclusionChange(val: CycleConclusion): void {
  const suggested = state.suggestCycleConclusion.value
  if (suggested !== null && val !== suggested) {
    overrideTarget.value = { type: 'cycle', index: 0, conclusion: val }
    overrideReason.value = ''
    overrideDialogVisible.value = true
  } else {
    state.setCycleConclusion(val)
    emit('save')
  }
}

function confirmOverride(): void {
  if (!overrideReason.value.trim()) {
    ElMessage.warning('需填写调整理由')
    return
  }
  if (overrideTarget.value.type === 'point') {
    state.setPointConclusion(overrideTarget.value.index, overrideTarget.value.conclusion as ControlPointConclusion, overrideReason.value)
  } else {
    state.setCycleConclusion(overrideTarget.value.conclusion as CycleConclusion, overrideReason.value)
    emit('save')
  }
  overrideDialogVisible.value = false
}

async function onReview(): Promise<void> {
  await state.doReview()
  emit('completed')
}

async function onAmend(): Promise<void> {
  if (!amendReason.value.trim()) {
    ElMessage.warning('请填写修改原因')
    return
  }
  await state.startAmendment(amendReason.value)
  showAmendDialog.value = false
  amendReason.value = ''
}
</script>

<style scoped>
.c-control-test {
  padding: 16px;
  max-width: 1200px;
  margin: 0 auto;
}
.c-control-test.is-readonly {
  pointer-events: auto;
}
.reviewed-banner {
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 4px;
  padding: 8px 16px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #52c41a;
  font-weight: 500;
}
.top-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.cycle-info {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cycle-name {
  font-size: 16px;
  font-weight: 600;
}
.wp-code-badge {
  background: #e6f7ff;
  color: #1890ff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}
.tolerable-rate-setting {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
}
.card-controls {
  margin-left: auto;
}
.b23-reference-panel {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
}
.panel-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.panel-title {
  font-weight: 500;
  font-size: 14px;
}
.b23-list {
  margin-top: 8px;
}
.b23-item {
  display: flex;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}
.b23-id {
  color: #1890ff;
  font-weight: 500;
}
.control-points-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 24px;
}
.control-point-card {
  border: 1px solid #f0f0f0;
  border-left: 4px solid #d9d9d9;
  border-radius: 8px;
  overflow: hidden;
  transition: border-left-color 0.3s;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  background: #fafafa;
}
.card-header:hover {
  background: #f5f5f5;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.ctrl-index {
  background: #1890ff;
  color: #fff;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
}
.ctrl-objective {
  font-size: 14px;
  color: #333;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.deviation-badge {
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f6ffed;
  color: #52c41a;
}
.deviation-badge.exceed {
  background: #fff2f0;
  color: #ff4d4f;
}
.card-body {
  padding: 16px;
  border-top: 1px solid #f0f0f0;
}
.field-row {
  margin-bottom: 16px;
}
.field-row label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  color: #666;
}
.method-tip {
  color: #faad14;
  font-size: 12px;
  margin-top: 4px;
}
.samples-section {
  margin-bottom: 16px;
}
.samples-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.samples-count {
  font-size: 13px;
  font-weight: 500;
  color: #666;
}
.empty-samples {
  color: #bfbfbf;
  font-size: 13px;
  text-align: center;
  padding: 24px;
  border: 1px dashed #d9d9d9;
  border-radius: 4px;
}
.samples-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sample-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border-radius: 4px;
  background: #fafafa;
  flex-wrap: wrap;
}
.sample-row.deviation-highlight {
  background: #fff2f0;
}
.sample-index {
  font-size: 12px;
  color: #999;
  width: 20px;
}
.sample-field {
  width: 100px;
}
.deviation-desc-row {
  width: 100%;
  margin-top: 8px;
  padding-left: 28px;
}
.deviation-stats {
  margin-bottom: 16px;
  font-size: 13px;
  color: #666;
}
.rate-value {
  font-weight: 600;
  color: #52c41a;
}
.rate-value.exceed {
  color: #ff4d4f;
}
.exceed-warning {
  color: #ff4d4f;
  font-weight: 500;
  margin-left: 8px;
}
.no-effective {
  color: #bfbfbf;
}
.point-conclusion-section {
  margin-bottom: 16px;
}
.point-conclusion-section label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  color: #666;
}
.suggestion-tip {
  font-size: 12px;
  color: #1890ff;
  margin-bottom: 8px;
}
.override-badge {
  margin-top: 8px;
  font-size: 12px;
  color: #faad14;
  background: #fffbe6;
  padding: 4px 8px;
  border-radius: 4px;
  display: inline-block;
}
.card-footer {
  border-top: 1px solid #f0f0f0;
  padding-top: 12px;
}
.cycle-conclusion-section {
  background: #f9f9f9;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.cycle-conclusion-section h3 {
  margin: 0 0 12px;
  font-size: 15px;
}
.linkage-panel {
  margin-bottom: 16px;
}
.linkage-panel h4 {
  margin: 0 0 8px;
  font-size: 14px;
}
.linkage-chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.ref-chip {
  cursor: pointer;
}
.extended-warning {
  margin-top: 8px;
  color: #ff4d4f;
  font-size: 13px;
  font-weight: 500;
}
.review-section {
  border-top: 1px solid #f0f0f0;
  padding-top: 16px;
}
.review-section h4 {
  margin: 0 0 8px;
  font-size: 14px;
}
.pending-list {
  margin-bottom: 12px;
  font-size: 13px;
  color: #666;
}
.pending-list ul {
  margin: 4px 0;
  padding-left: 20px;
}
.evidence-tab {
  padding: 24px;
  text-align: center;
}
.evidence-placeholder {
  color: #bfbfbf;
  font-size: 14px;
}

/* Print styles */
@media print {
  .no-print {
    display: none !important;
  }
  .card-body {
    display: block !important;
  }
  .control-point-card {
    break-inside: avoid;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .c-control-test {
    padding: 0;
  }
  .deviation-badge,
  .reviewed-banner,
  .sample-row.deviation-highlight {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
}
</style>
