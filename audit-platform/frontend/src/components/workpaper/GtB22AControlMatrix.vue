<script setup lang="ts">
/**
 * GtB22AControlMatrix — B22A 内部控制了解程序表
 *
 * 6-Tab 统一界面：
 *   Tab 1: 控制环境
 *   Tab 2: 风险评估过程
 *   Tab 3: 信息系统与沟通
 *   Tab 4: 控制活动 + IT 子区
 *   Tab 5: 监督
 *   Tab 6: 控制矩阵汇总
 *
 * Spec: .kiro/specs/b22a-control-matrix/
 * Tasks: 3.1 ~ 3.13, 4.1
 */
import { ref, computed, watch, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useB22AFormData, type ChecklistItem } from './composables/useB22AFormData'
import {
  useB22AControlMatrix,
  CONCLUSIONS,
  UNDERSTANDING_METHODS,
  SCORE_COLOR_MAP,
  IT_SUB_PANELS,
  COSO_TABS,
  type TabNumber,
  type ElementScore,
  type ITSubPanel,
  type ITDependency,
  type Conclusion,
  type UnderstandingMethod,
} from './composables/useB22AControlMatrix'
import { useB22AReview } from './composables/useB22AReview'
import { eventBus } from '@/utils/eventBus'

// ─── Props / Emits (Task 3.1) ────────────────────────────────────────────────

interface Props {
  wpId: string
  projectId: string
  wpCode: string
  year: number
  readonly?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── Composables 初始化 (Task 3.1) ──────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const externalReadonly = toRef(props, 'readonly')

const {
  allResponses,
  loading,
  saving,
  loadAll,
  loadPriorYear,
  saveImmediate,
  saveDebouncedText,
} = useB22AFormData(wpIdRef)

const {
  getCheckItems,
  addCheckItem,
  removeCheckItem,
  setConclusion,
  setUnderstandingMethod,
  overrideElementScore,
  isScoreOverridden,
  getEffectiveScore,
  itDependency,
  setITDependency,
  itgcConclusion,
  isITGCInvalid,
  deficiencyList,
  elementStats,
  overallConclusion,
  completedElementCount,
  tabStatus,
  priorYearData,
  markNoChange,
  controlEnvWeakWarning,
  itControlWeakWarning,
  initialize,
} = useB22AControlMatrix(allResponses, saveImmediate)

const {
  isReviewed,
  isReadonly,
  canReview,
  pendingItems,
  reviewInfo,
  doReview,
  startAmendment,
} = useB22AReview(
  wpIdRef,
  allResponses,
  completedElementCount,
  overallConclusion,
  externalReadonly as any,
  saveImmediate
)

// ─── Tab 状态 (Task 3.2) ─────────────────────────────────────────────────────

const activeTab = ref('Tab_1')

function tabStatusIcon(tab: TabNumber): string {
  const status = tabStatus(tab)
  switch (status) {
    case 'complete': return '✅'
    case 'partial': return '🔶'
    case 'empty': return '⬜'
  }
}

const overallProgress = computed(() => `${completedElementCount.value}/5`)

// ─── Check Item 表格操作 (Task 3.3) ─────────────────────────────────────────

function handleAddCheckItem(tab: TabNumber, subPanel?: ITSubPanel) {
  if (isReadonly.value) return
  addCheckItem(tab, subPanel)
}

async function handleRemoveCheckItem(tab: TabNumber, index: number, subPanel?: ITSubPanel) {
  if (isReadonly.value) return
  try {
    await ElMessageBox.confirm(`确认删除第 ${index} 行检查项？`, '删除确认', { type: 'warning' })
  } catch { return }
  removeCheckItem(tab, index, subPanel)
}

function handleConclusionChange(tab: TabNumber, index: number, value: string, subPanel?: ITSubPanel) {
  if (isReadonly.value) return
  setConclusion(tab, index, value as Conclusion, subPanel)
  emitConclusionChange()
}

function handleMethodChange(tab: TabNumber, index: number, values: string[], subPanel?: ITSubPanel) {
  if (isReadonly.value) return
  setUnderstandingMethod(tab, index, values as UnderstandingMethod[], subPanel)
}

function handleTextFieldChange(tab: TabNumber, index: number, field: 'point' | 'desc' | 'ref', value: string, subPanel?: ITSubPanel) {
  if (isReadonly.value) return
  const prefix = subPanel ? `B22A-T${tab}-IT-${subPanel}` : `B22A-T${tab}-item`
  const itemId = `${prefix}-${index}-${field}`
  const item: ChecklistItem = { item_id: itemId, conclusion: null, remark: value, wp_ref: null }
  allResponses.value.set(itemId, item)
  saveDebouncedText(item)
}

// ─── Tab 4 IT 子区 (Task 3.4) ────────────────────────────────────────────────

const itCollapseActive = ref<string[]>([])

const IT_REQUIRED_MAP: Record<ITDependency, { expanded: boolean; required: boolean; hint: string }> = {
  '高': { expanded: true, required: true, hint: '' },
  '中': { expanded: true, required: false, hint: '可选择性执行' },
  '低': { expanded: false, required: false, hint: '可简化执行' },
}

function handleITDependencyChange(level: string) {
  if (isReadonly.value) return
  setITDependency(level as ITDependency)
  if (IT_REQUIRED_MAP[level as ITDependency].expanded) {
    itCollapseActive.value = IT_SUB_PANELS.map(p => p.key)
  } else {
    itCollapseActive.value = []
  }
  emitITChange()
}

// ─── Summary Tab (Task 3.5) ──────────────────────────────────────────────────

const ELEMENT_SCORE_OPTIONS: ElementScore[] = ['有效', '部分有效', '无效']

function getScoreStyle(score: ElementScore | null) {
  if (!score) return { backgroundColor: '#F9FAFB', color: '#374151' }
  const c = SCORE_COLOR_MAP[score]
  return { backgroundColor: c.bg, color: c.text }
}

function handleOverallConclusionChange(value: string) {
  if (isReadonly.value) return
  overallConclusion.value = value as ElementScore
  const item: ChecklistItem = {
    item_id: 'B22A-SUM-overall',
    conclusion: value,
    remark: null,
    wp_ref: null,
  }
  allResponses.value.set(item.item_id, item)
  saveImmediate([item])
  emitConclusionChange()
}

function handleSummaryNoteChange(value: string) {
  if (isReadonly.value) return
  const item: ChecklistItem = { item_id: 'B22A-SUM-note', conclusion: null, remark: value, wp_ref: null }
  allResponses.value.set(item.item_id, item)
  saveDebouncedText(item)
}

const summaryNote = computed(() => allResponses.value.get('B22A-SUM-note')?.remark || '')

// ─── Element_Score 手动覆盖 (Task 3.7) ──────────────────────────────────────

const overrideDialogVisible = ref(false)
const overrideTab = ref<TabNumber>(1)
const overrideScore = ref<ElementScore>('有效')
const overrideReason = ref('')

function showOverrideDialog(tab: TabNumber) {
  if (isReadonly.value) return
  overrideTab.value = tab
  overrideScore.value = getEffectiveScore(tab) || '有效'
  overrideReason.value = ''
  overrideDialogVisible.value = true
}

function submitOverride() {
  if (!overrideReason.value.trim()) {
    ElMessage.warning('需填写调整理由')
    return
  }
  overrideElementScore(overrideTab.value, overrideScore.value, overrideReason.value)
  overrideDialogVisible.value = false
  emitConclusionChange()
}

// ─── Manager Review (Task 3.8) ───────────────────────────────────────────────

async function handleReview() {
  if (!canReview.value || isReadonly.value) return
  try {
    await ElMessageBox.confirm('确认签字复核？复核后全部内容将锁定为只读。', '现场经理复核', { type: 'info' })
  } catch { return }
  await doReview()
  emit('save')
  emit('completed')
}

// ─── Amendment (Task 3.9) ────────────────────────────────────────────────────

const amendmentDialogVisible = ref(false)
const amendmentReason = ref('')

function showAmendmentDialog() {
  amendmentReason.value = ''
  amendmentDialogVisible.value = true
}

async function submitAmendment() {
  if (!amendmentReason.value.trim()) {
    ElMessage.warning('请填写修改原因')
    return
  }
  try {
    await startAmendment(amendmentReason.value)
    amendmentDialogVisible.value = false
    ElMessage.success('已重置复核，可继续编辑')
  } catch (e: any) {
    ElMessage.error(e.message || '操作失败')
  }
}

// ─── EventBus (Task 3.10) ────────────────────────────────────────────────────

function emitConclusionChange() {
  try {
    const elementScores: Record<number, ElementScore | null> = {}
    for (const t of COSO_TABS) {
      elementScores[t.tab] = getEffectiveScore(t.tab)
    }
    ;(eventBus as any).emit('control:conclusion-changed', {
      elementScores,
      itDependency: itDependency.value,
      itgcConclusion: itgcConclusion.value,
      overallConclusion: overallConclusion.value,
    })
  } catch (e) {
    console.warn('[B22A] EventBus control:conclusion-changed emit failed:', e)
  }
}

function emitITChange() {
  try {
    ;(eventBus as any).emit('control:it-conclusion-changed', {
      itDependency: itDependency.value,
      itgcConclusion: itgcConclusion.value,
    })
  } catch (e) {
    console.warn('[B22A] EventBus control:it-conclusion-changed emit failed:', e)
  }
}

function emitDeficiencyChange() {
  try {
    ;(eventBus as any).emit('control:deficiency-changed', {
      total: deficiencyList.value.length,
      deficiencies: deficiencyList.value,
    })
  } catch (e) {
    console.warn('[B22A] EventBus control:deficiency-changed emit failed:', e)
  }
}

// ─── Prior Year (Task 3.11) ──────────────────────────────────────────────────

const priorYearLoading = ref(false)

async function handleLoadPriorYear() {
  if (isReadonly.value) return
  const priorWpId = `${props.wpId}-prior`
  priorYearLoading.value = true
  try {
    await loadPriorYear(priorWpId)
    ElMessage.success('上年数据加载完成')
  } catch {
    ElMessage.warning('上年数据加载失败')
  } finally {
    priorYearLoading.value = false
  }
}

function handleMarkNoChange(tab: TabNumber, index: number, subPanel?: ITSubPanel) {
  if (isReadonly.value) return
  markNoChange(tab, index, '当前用户', subPanel)
}

// ─── Element note (per tab) ──────────────────────────────────────────────────

function getTabNote(tab: TabNumber): string {
  return allResponses.value.get(`B22A-T${tab}-note`)?.remark || ''
}

function handleTabNoteChange(tab: TabNumber, value: string) {
  if (isReadonly.value) return
  const item: ChecklistItem = { item_id: `B22A-T${tab}-note`, conclusion: null, remark: value, wp_ref: null }
  allResponses.value.set(item.item_id, item)
  saveDebouncedText(item)
}

// ─── Lifecycle (Task 3.1) ────────────────────────────────────────────────────

onMounted(async () => {
  await loadAll()
  initialize()
})

// Watch isReviewed → emit completed
watch(isReviewed, (val) => {
  if (val) emit('completed')
})

// Watch saving → emit save
watch(saving, (isSaving, wasSaving) => {
  if (wasSaving && !isSaving) {
    emit('save')
  }
})

// Watch deficiency list → emit change
watch(deficiencyList, () => {
  emitDeficiencyChange()
}, { deep: true })
</script>

<template>
  <div class="gt-b22a-control-matrix" :class="{ 'is-readonly': isReadonly }">
    <!-- 控制环境薄弱警告横幅 (Task 3.12) -->
    <div v-if="controlEnvWeakWarning" class="warning-banner warning-banner--red">
      ⚠️ 控制环境薄弱——建议提高整体风险评估
      <span class="ref-chip">📎 跳转 B50</span>
    </div>

    <!-- IT 控制薄弱警告 (Task 3.12) -->
    <div v-if="itControlWeakWarning" class="warning-banner warning-banner--orange">
      ⚠️ IT通用控制(ITGC)无效——IT依赖程度高，IT应用控制可靠性受影响
    </div>

    <!-- 已复核横幅 (Task 3.8) -->
    <div v-if="isReviewed" class="review-banner">
      <span>✅ 已复核</span>
      <span v-if="reviewInfo">（{{ reviewInfo.reviewer }} / {{ reviewInfo.date }}）</span>
      <el-button v-if="!externalReadonly" size="small" type="warning" @click="showAmendmentDialog">
        修改（Amendment）
      </el-button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-mask">加载中...</div>

    <!-- 6-Tab 容器 (Task 3.2) -->
    <el-tabs v-model="activeTab" type="border-card" class="b22a-tabs">
      <!-- 进度指示 -->
      <div class="tab-progress">完成进度: {{ overallProgress }}</div>

      <!-- ═══ Tab 1~5: COSO 五要素 ═══ -->
      <el-tab-pane
        v-for="cosoTab in COSO_TABS"
        :key="cosoTab.tab"
        :label="`${tabStatusIcon(cosoTab.tab)} ${cosoTab.label}`"
        :name="`Tab_${cosoTab.tab}`"
      >
        <div class="tab-content">
          <div class="tab-header">
            <h3>{{ cosoTab.label }}</h3>
            <div class="tab-header-actions">
              <!-- 续审：加载上年数据 (Task 3.11) -->
              <el-button
                v-if="!isReadonly"
                size="small"
                :loading="priorYearLoading"
                @click="handleLoadPriorYear"
              >
                加载上年数据
              </el-button>
              <el-button v-if="!isReadonly" type="primary" size="small" @click="handleAddCheckItem(cosoTab.tab)">
                + 新增检查项
              </el-button>
            </div>
          </div>

          <!-- 检查项表格 (Task 3.3) -->
          <el-table :data="getCheckItems(cosoTab.tab)" border size="small" class="check-item-table">
            <el-table-column label="序号" width="60" align="center">
              <template #default="{ row }">{{ row.index }}</template>
            </el-table-column>
            <el-table-column label="控制要点" min-width="160">
              <template #default="{ row }">
                <el-input
                  :model-value="row.controlPoint"
                  :disabled="isReadonly"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  placeholder="控制要点..."
                  @update:model-value="(v: string) => handleTextFieldChange(cosoTab.tab, row.index, 'point', v)"
                />
                <!-- 上年结论灰色提示 (Task 3.11) -->
                <span v-if="row.priorYearConclusion" class="prior-year-hint">
                  上年: {{ row.priorYearConclusion }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="控制活动描述" min-width="180">
              <template #default="{ row }">
                <el-input
                  :model-value="row.description"
                  :disabled="isReadonly"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  placeholder="描述控制活动..."
                  @update:model-value="(v: string) => handleTextFieldChange(cosoTab.tab, row.index, 'desc', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="了解方法" width="200">
              <template #default="{ row }">
                <el-checkbox-group
                  :model-value="row.methods"
                  :disabled="isReadonly"
                  @update:model-value="(v: string[]) => handleMethodChange(cosoTab.tab, row.index, v)"
                >
                  <el-checkbox v-for="m in UNDERSTANDING_METHODS" :key="m" :label="m" :value="m" />
                </el-checkbox-group>
              </template>
            </el-table-column>
            <el-table-column label="结论" width="130">
              <template #default="{ row }">
                <el-select
                  :model-value="row.conclusion || ''"
                  :disabled="isReadonly"
                  placeholder="选择结论"
                  :class="{ 'deficiency-select': row.isDeficiency }"
                  @update:model-value="(v: string) => handleConclusionChange(cosoTab.tab, row.index, v)"
                >
                  <el-option v-for="c in CONCLUSIONS" :key="c" :label="c" :value="c" />
                </el-select>
                <span v-if="row.isDeficiency" class="deficiency-badge">缺陷</span>
              </template>
            </el-table-column>
            <el-table-column label="参考引用" width="120">
              <template #default="{ row }">
                <el-input
                  :model-value="row.reference"
                  :disabled="isReadonly"
                  placeholder="索引..."
                  @update:model-value="(v: string) => handleTextFieldChange(cosoTab.tab, row.index, 'ref', v)"
                />
              </template>
            </el-table-column>

            <el-table-column label="操作" width="120" align="center">
              <template #default="{ row }">
                <!-- 本年无变化 (Task 3.11) -->
                <el-button
                  v-if="!isReadonly && row.priorYearConclusion && !row.noChangeConfirmed"
                  size="small"
                  link
                  @click="handleMarkNoChange(cosoTab.tab, row.index)"
                >
                  本年无变化
                </el-button>
                <span v-if="row.noChangeConfirmed" class="no-change-tag">
                  ✓ 无变化 ({{ row.noChangeConfirmer }})
                </span>
                <el-button
                  v-if="!isReadonly && !row.isPreset"
                  type="danger"
                  size="small"
                  link
                  @click="handleRemoveCheckItem(cosoTab.tab, row.index)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- Tab 4 IT 子区 (Task 3.4) -->
          <div v-if="cosoTab.tab === 4" class="it-subsection">
            <div class="it-header">
              <h4>IT 控制子区</h4>
              <div class="it-dependency-selector">
                <span>IT依赖程度：</span>
                <el-select
                  :model-value="itDependency"
                  :disabled="isReadonly"
                  size="small"
                  style="width: 100px"
                  @update:model-value="handleITDependencyChange"
                >
                  <el-option label="高" value="高" />
                  <el-option label="中" value="中" />
                  <el-option label="低" value="低" />
                </el-select>
                <span v-if="IT_REQUIRED_MAP[itDependency].hint" class="it-hint">
                  {{ IT_REQUIRED_MAP[itDependency].hint }}
                </span>
              </div>
            </div>

            <!-- ITGC 无效警告 (Task 3.4) -->
            <div v-if="isITGCInvalid" class="warning-banner warning-banner--orange" style="margin: 8px 0">
              ⚠️ ITGC 结论为"无效"——IT应用控制可靠性受到影响
            </div>

            <!-- IT 手风琴 6 面板 (Task 3.4) -->
            <el-collapse v-model="itCollapseActive">
              <el-collapse-item
                v-for="panel in IT_SUB_PANELS"
                :key="panel.key"
                :name="panel.key"
                :title="`${panel.label}${IT_REQUIRED_MAP[itDependency].required ? ' *' : ''}`"
              >
                <div class="it-panel-content">
                  <div class="it-panel-toolbar">
                    <el-button
                      v-if="!isReadonly"
                      type="primary"
                      size="small"
                      @click="handleAddCheckItem(4, panel.key)"
                    >
                      + 新增检查项
                    </el-button>
                  </div>

                  <el-table :data="getCheckItems(4, panel.key)" border size="small" class="check-item-table">
                    <el-table-column label="序号" width="60" align="center">
                      <template #default="{ row }">{{ row.index }}</template>
                    </el-table-column>
                    <el-table-column label="控制要点" min-width="140">
                      <template #default="{ row }">
                        <el-input
                          :model-value="row.controlPoint"
                          :disabled="isReadonly"
                          type="textarea"
                          :autosize="{ minRows: 1, maxRows: 3 }"
                          placeholder="控制要点..."
                          @update:model-value="(v: string) => handleTextFieldChange(4, row.index, 'point', v, panel.key)"
                        />
                        <span v-if="row.priorYearConclusion" class="prior-year-hint">
                          上年: {{ row.priorYearConclusion }}
                        </span>
                      </template>
                    </el-table-column>
                    <el-table-column label="描述" min-width="160">
                      <template #default="{ row }">
                        <el-input
                          :model-value="row.description"
                          :disabled="isReadonly"
                          type="textarea"
                          :autosize="{ minRows: 1, maxRows: 3 }"
                          placeholder="描述..."
                          @update:model-value="(v: string) => handleTextFieldChange(4, row.index, 'desc', v, panel.key)"
                        />
                      </template>
                    </el-table-column>
                    <el-table-column label="了解方法" width="180">
                      <template #default="{ row }">
                        <el-checkbox-group
                          :model-value="row.methods"
                          :disabled="isReadonly"
                          @update:model-value="(v: string[]) => handleMethodChange(4, row.index, v, panel.key)"
                        >
                          <el-checkbox v-for="m in UNDERSTANDING_METHODS" :key="m" :label="m" :value="m" />
                        </el-checkbox-group>
                      </template>
                    </el-table-column>
                    <el-table-column label="结论" width="130">
                      <template #default="{ row }">
                        <el-select
                          :model-value="row.conclusion || ''"
                          :disabled="isReadonly"
                          placeholder="选择"
                          :class="{ 'deficiency-select': row.isDeficiency }"
                          @update:model-value="(v: string) => handleConclusionChange(4, row.index, v, panel.key)"
                        >
                          <el-option v-for="c in CONCLUSIONS" :key="c" :label="c" :value="c" />
                        </el-select>
                        <span v-if="row.isDeficiency" class="deficiency-badge">缺陷</span>
                      </template>
                    </el-table-column>
                    <el-table-column label="引用" width="100">
                      <template #default="{ row }">
                        <el-input
                          :model-value="row.reference"
                          :disabled="isReadonly"
                          placeholder="索引"
                          @update:model-value="(v: string) => handleTextFieldChange(4, row.index, 'ref', v, panel.key)"
                        />
                      </template>
                    </el-table-column>
                    <el-table-column label="操作" width="100" align="center">
                      <template #default="{ row }">
                        <el-button
                          v-if="!isReadonly && !row.isPreset"
                          type="danger"
                          size="small"
                          link
                          @click="handleRemoveCheckItem(4, row.index, panel.key)"
                        >
                          删除
                        </el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>

          <!-- 底部：审计说明 + 要素整体结论 (Task 3.3) -->
          <div class="tab-footer">
            <div class="tab-note-section">
              <label>审计说明：</label>
              <el-input
                :model-value="getTabNote(cosoTab.tab)"
                :disabled="isReadonly"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 5 }"
                placeholder="审计说明..."
                @update:model-value="(v: string) => handleTabNoteChange(cosoTab.tab, v)"
              />
            </div>
            <div class="tab-score-section">
              <label>要素整体结论：</label>
              <span
                class="score-display"
                :style="getScoreStyle(getEffectiveScore(cosoTab.tab))"
              >
                {{ getEffectiveScore(cosoTab.tab) || '未计算' }}
              </span>
              <span v-if="isScoreOverridden(cosoTab.tab)" class="override-badge">已手动调整</span>
              <el-button
                v-if="!isReadonly"
                size="small"
                link
                @click="showOverrideDialog(cosoTab.tab)"
              >
                手动调整
              </el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- ═══ Summary Tab: 控制矩阵汇总 (Task 3.5) ═══ -->
      <el-tab-pane label="📊 控制矩阵汇总" name="Tab_Summary">
        <div class="tab-content summary-tab">
          <!-- 控制环境薄弱横幅 (Task 3.12) -->
          <div v-if="controlEnvWeakWarning" class="warning-banner warning-banner--red" style="margin-bottom: 12px">
            ⚠️ 控制环境薄弱——建议提高整体风险评估
            <span class="ref-chip">📎 跳转 B50</span>
          </div>

          <!-- IT 控制薄弱警告 (Task 3.12) -->
          <div v-if="itControlWeakWarning" class="warning-banner warning-banner--orange" style="margin-bottom: 12px">
            ⚠️ IT通用控制(ITGC)无效——IT依赖程度高，应用控制可靠性受影响
          </div>

          <h3>交叉汇总矩阵</h3>

          <!-- 交叉矩阵 (Task 3.5) -->
          <div class="summary-matrix">
            <table class="matrix-table">
              <thead>
                <tr>
                  <th>检查维度</th>
                  <th v-for="t in COSO_TABS" :key="t.tab">{{ t.label }}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td class="dim-label">要素评价</td>
                  <td
                    v-for="t in COSO_TABS"
                    :key="t.tab"
                    :style="getScoreStyle(getEffectiveScore(t.tab))"
                    class="score-cell"
                  >
                    {{ getEffectiveScore(t.tab) || '—' }}
                  </td>
                </tr>
                <tr>
                  <td class="dim-label">有效项</td>
                  <td v-for="t in COSO_TABS" :key="t.tab">{{ elementStats[t.tab]?.effective ?? 0 }}</td>
                </tr>
                <tr>
                  <td class="dim-label">缺陷项</td>
                  <td v-for="t in COSO_TABS" :key="t.tab" :class="{ 'has-deficiency': (elementStats[t.tab]?.deficient ?? 0) > 0 }">
                    {{ elementStats[t.tab]?.deficient ?? 0 }}
                  </td>
                </tr>
                <tr>
                  <td class="dim-label">不适用</td>
                  <td v-for="t in COSO_TABS" :key="t.tab">{{ elementStats[t.tab]?.notApplicable ?? 0 }}</td>
                </tr>
                <tr>
                  <td class="dim-label">未完成</td>
                  <td v-for="t in COSO_TABS" :key="t.tab" :class="{ 'has-incomplete': (elementStats[t.tab]?.incomplete ?? 0) > 0 }">
                    {{ elementStats[t.tab]?.incomplete ?? 0 }}
                  </td>
                </tr>
                <tr>
                  <td class="dim-label">总计</td>
                  <td v-for="t in COSO_TABS" :key="t.tab">{{ elementStats[t.tab]?.total ?? 0 }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 任一要素无效警告 (Task 3.5) -->
          <div
            v-if="COSO_TABS.some(t => getEffectiveScore(t.tab) === '无效')"
            class="warning-banner warning-banner--red"
            style="margin-top: 12px"
          >
            ⚠️ 存在要素评价为"无效"——请关注对整体控制风险的影响
          </div>

          <!-- 缺陷清单 (Task 3.6) -->
          <div class="deficiency-section">
            <h4>控制缺陷汇总 ({{ deficiencyList.length }} 项)</h4>
            <div v-if="deficiencyList.length === 0" class="empty-state">
              暂无控制缺陷
            </div>
            <el-table v-else :data="deficiencyList" border size="small">
              <el-table-column label="序号" width="60" align="center">
                <template #default="{ $index }">{{ $index + 1 }}</template>
              </el-table-column>
              <el-table-column label="来源要素" width="160" prop="elementName" />
              <el-table-column label="控制要点" min-width="200" prop="controlPoint" />
              <el-table-column label="缺陷类型" width="100">
                <template #default="{ row }">
                  <span class="deficiency-type-tag" :class="row.deficiencyType === '设计无效' ? 'tag-design' : 'tag-implement'">
                    {{ row.deficiencyType }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="引用" width="80" align="center">
                <template #default="{ row }">
                  <span class="ref-chip">📎 B22B</span>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 整体结论 (Task 3.5) -->
          <div class="overall-conclusion-section">
            <h4>企业层面控制整体结论</h4>
            <div class="overall-row">
              <el-select
                :model-value="overallConclusion || ''"
                :disabled="isReadonly"
                placeholder="选择整体结论"
                @update:model-value="handleOverallConclusionChange"
              >
                <el-option v-for="s in ELEMENT_SCORE_OPTIONS" :key="s" :label="s" :value="s" />
              </el-select>
              <span
                v-if="overallConclusion"
                class="score-display"
                :style="getScoreStyle(overallConclusion)"
              >
                {{ overallConclusion }}
              </span>
            </div>
            <div class="overall-note">
              <label>整体说明：</label>
              <el-input
                :model-value="summaryNote"
                :disabled="isReadonly"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 5 }"
                placeholder="整体结论说明..."
                @update:model-value="handleSummaryNoteChange"
              />
            </div>
          </div>

          <!-- 现场经理复核区 (Task 3.8) -->
          <div class="review-section">
            <h4>现场经理复核</h4>
            <div v-if="!isReviewed">
              <!-- 待完成事项 -->
              <div v-if="pendingItems.length > 0" class="pending-items">
                <p class="pending-title">⚠️ 以下事项需完成后方可签字：</p>
                <ul>
                  <li v-for="item in pendingItems" :key="item">{{ item }}</li>
                </ul>
              </div>
              <el-button
                type="primary"
                :disabled="!canReview || isReadonly"
                @click="handleReview"
              >
                现场经理签字复核
              </el-button>
            </div>
            <div v-else class="reviewed-info">
              <span>✅ 已完成复核</span>
              <span v-if="reviewInfo">— {{ reviewInfo.reviewer }} / {{ reviewInfo.date }}</span>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- ═══ Element_Score 手动覆盖对话框 (Task 3.7) ═══ -->
    <el-dialog v-model="overrideDialogVisible" title="手动调整要素评价" width="450px" append-to-body>
      <div class="override-form">
        <p>自动计算结果将被覆盖，需填写调整理由。</p>
        <div class="override-field">
          <label>调整后评价：</label>
          <el-select v-model="overrideScore">
            <el-option v-for="s in ELEMENT_SCORE_OPTIONS" :key="s" :label="s" :value="s" />
          </el-select>
        </div>
        <div class="override-field">
          <label>调整理由：</label>
          <el-input
            v-model="overrideReason"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            placeholder="填写调整理由（必填）..."
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="overrideDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitOverride">确认调整</el-button>
      </template>
    </el-dialog>

    <!-- ═══ Amendment 对话框 (Task 3.9) ═══ -->
    <el-dialog v-model="amendmentDialogVisible" title="修改内控评价（Amendment）" width="500px" append-to-body>
      <div class="amendment-form">
        <p>已复核的内控评价需重新修改时，请填写修改原因：</p>
        <el-input
          v-model="amendmentReason"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="填写修改原因..."
        />
        <p class="amendment-note">提交后复核状态将重置，修改完成后需重新现场经理签字。</p>
      </div>
      <template #footer>
        <el-button @click="amendmentDialogVisible = false">取消</el-button>
        <el-button type="warning" @click="submitAmendment">确认修改</el-button>
      </template>
    </el-dialog>

    <!-- Saving indicator -->
    <div v-if="saving" class="saving-indicator">保存中...</div>
  </div>
</template>

<style scoped>
/* ═══ 基础布局 (Task 3.13) ═══ */
.gt-b22a-control-matrix {
  position: relative;
  padding: 16px;
  min-width: 768px;
}

.loading-mask {
  text-align: center;
  padding: 40px;
  color: #6B7280;
}

.saving-indicator {
  position: fixed;
  bottom: 16px;
  right: 16px;
  background: #3B82F6;
  color: white;
  padding: 6px 12px;
  border-radius: 4px;
  font-size: 12px;
  z-index: 1000;
}

/* ═══ 警告横幅 (Task 3.12) ═══ */
.warning-banner {
  border-radius: 6px;
  padding: 10px 16px;
  margin-bottom: 12px;
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  display: flex;
  align-items: center;
  gap: 12px;
}

.warning-banner--red {
  background: #FEE2E2;
  border: 1px solid #DC2626;
  color: #DC2626;
}

.warning-banner--orange {
  background: #FEF3C7;
  border: 1px solid #D97706;
  color: #92400E;
}

/* ═══ 已复核横幅 (Task 3.8) ═══ */
.review-banner {
  background: #D1FAE5;
  border: 1px solid #059669;
  border-radius: 6px;
  padding: 10px 16px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  color: #059669;
  font-weight: 600;
}

/* ═══ Tabs ═══ */
.b22a-tabs {
  margin-bottom: 16px;
}

.tab-progress {
  position: absolute;
  top: 8px;
  right: 16px;
  font-size: 12px;
  color: #6B7280;
}

.tab-content {
  padding: 12px 0;
}

.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.tab-header h3 {
  margin: 0;
  font-size: 16px;
}

.tab-header-actions {
  display: flex;
  gap: 8px;
}

/* ═══ 检查项表格 (Task 3.3) ═══ */
.check-item-table {
  margin-bottom: 12px;
}

.deficiency-select :deep(.el-input__wrapper) {
  border-color: #DC2626 !important;
  box-shadow: 0 0 0 1px #DC2626 inset !important;
}

.deficiency-badge {
  display: inline-block;
  background: #FEE2E2;
  color: #DC2626;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
  margin-top: 2px;
}

.prior-year-hint {
  display: block;
  font-size: 11px;
  color: #9CA3AF;
  font-style: italic;
  margin-top: 2px;
}

.no-change-tag {
  font-size: 11px;
  color: #059669;
  display: block;
  margin-bottom: 4px;
}

.ref-chip {
  display: inline-block;
  background: #EFF6FF;
  border: 1px solid #93C5FD;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 11px;
  color: #2563EB;
  cursor: pointer;
}

/* ═══ Tab 4 IT 子区 (Task 3.4) ═══ */
.it-subsection {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 2px solid #E5E7EB;
}

.it-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.it-header h4 {
  margin: 0;
  font-size: 15px;
}

.it-dependency-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
}

.it-hint {
  color: #D97706;
  font-size: 12px;
  font-weight: 600;
}

.it-panel-content {
  padding: 8px 0;
}

.it-panel-toolbar {
  margin-bottom: 8px;
}

/* ═══ Tab 底部区域 (Task 3.3) ═══ */
.tab-footer {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #E5E7EB;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tab-note-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tab-note-section label,
.tab-score-section label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: #374151;
}

.tab-score-section {
  display: flex;
  align-items: center;
  gap: 12px;
}

.score-display {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 4px;
  font-weight: 700;
  font-size: var(--wp-font-size, 13px);
}

.override-badge {
  background: #DBEAFE;
  color: #1D4ED8;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 600;
}

/* ═══ Summary Tab (Task 3.5) ═══ */
.summary-tab h3,
.summary-tab h4 {
  margin: 16px 0 8px;
  font-size: 15px;
}

.summary-matrix {
  overflow-x: auto;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
}

.matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--wp-font-size, 13px);
}

.matrix-table th,
.matrix-table td {
  padding: 10px 12px;
  border: 1px solid #E5E7EB;
  text-align: center;
}

.matrix-table th {
  background: #F3F4F6;
  font-weight: 700;
  font-size: 12px;
}

.matrix-table .dim-label {
  text-align: left;
  font-weight: 600;
  background: #F9FAFB;
  min-width: 80px;
}

.score-cell {
  font-weight: 700;
}

.has-deficiency {
  color: #DC2626;
  font-weight: 700;
}

.has-incomplete {
  color: #D97706;
  font-weight: 700;
}

/* ═══ 缺陷清单 (Task 3.6) ═══ */
.deficiency-section {
  margin-top: 20px;
}

.deficiency-type-tag {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
}

.tag-design {
  background: #FEE2E2;
  color: #DC2626;
}

.tag-implement {
  background: #FEF3C7;
  color: #D97706;
}

.empty-state {
  text-align: center;
  padding: 24px;
  color: #6B7280;
}

/* ═══ 整体结论 (Task 3.5) ═══ */
.overall-conclusion-section {
  margin-top: 20px;
  padding: 16px;
  background: #F9FAFB;
  border-radius: 6px;
  border: 1px solid #E5E7EB;
}

.overall-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.overall-note {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.overall-note label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: #374151;
}

/* ═══ 复核区 (Task 3.8) ═══ */
.review-section {
  margin-top: 20px;
  padding: 16px;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  background: #FAFAFA;
}

.review-section h4 {
  margin: 0 0 12px;
  font-size: 15px;
}

.pending-items {
  margin-bottom: 12px;
}

.pending-title {
  color: #D97706;
  font-weight: 600;
  margin-bottom: 4px;
}

.pending-items ul {
  margin: 0;
  padding-left: 20px;
  font-size: var(--wp-font-size, 13px);
  color: #6B7280;
}

.reviewed-info {
  color: #059669;
  font-weight: 600;
}

/* ═══ 对话框 (Task 3.7 / 3.9) ═══ */
.override-form,
.amendment-form {
  font-size: var(--wp-font-size, 13px);
}

.override-form p,
.amendment-form p {
  margin: 8px 0;
}

.override-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.override-field label {
  font-size: 12px;
  font-weight: 600;
}

.amendment-note {
  font-size: 12px;
  color: #6B7280;
  font-style: italic;
}

/* ═══ 只读模式 (Task 3.9) ═══ */
.is-readonly .check-item-table :deep(.el-input__wrapper),
.is-readonly .check-item-table :deep(.el-textarea__inner) {
  cursor: default;
}

/* ═══ 响应式布局 (Task 3.13) ═══ */
@media (min-width: 1024px) {
  .summary-matrix {
    overflow-x: visible;
  }
}

@media (max-width: 1023px) and (min-width: 768px) {
  .gt-b22a-control-matrix {
    overflow-x: auto;
  }
  .summary-matrix {
    overflow-x: auto;
  }
  .matrix-table {
    min-width: 700px;
  }
}

/* ═══ 打印样式 (Task 4.1) ═══ */
@media print {
  .gt-b22a-control-matrix {
    padding: 0;
  }

  /* 隐藏交互控件 */
  .tab-header-actions,
  .it-panel-toolbar,
  .it-dependency-selector,
  .review-section .el-button,
  .saving-indicator,
  .warning-banner .ref-chip,
  .tab-progress,
  .el-button,
  .el-select,
  .el-checkbox,
  .el-input,
  .el-textarea {
    display: none !important;
  }

  /* A4 横版 */
  @page {
    size: A4 landscape;
    margin: 10mm;
  }

  /* 保持颜色 */
  .score-display,
  .score-cell,
  .deficiency-badge,
  .deficiency-type-tag,
  .review-banner,
  .warning-banner,
  .matrix-table th,
  .matrix-table td {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
    color-adjust: exact !important;
  }

  /* 矩阵满宽 */
  .summary-matrix {
    overflow: visible;
    border: 1px solid #000;
  }

  .matrix-table {
    min-width: unset;
    width: 100%;
  }

  /* 显示数据文本替代输入框 */
  .check-item-table :deep(.el-input__inner),
  .check-item-table :deep(.el-textarea__inner) {
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    background: transparent !important;
  }
}
</style>
