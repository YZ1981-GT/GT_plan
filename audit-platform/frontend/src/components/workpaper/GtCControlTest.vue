<template>
  <div class="c-control-test" :class="{ 'is-readonly': readonly }">
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- ═══════════════════════════════════════════════════════════════════
           判断当前 sheetName 是否为偏差评价 (Cx-2)
           如果是 → 直接渲染决策树（不显示汇总表）
           如果否 → 渲染 L0 汇总表主控台
           ═══════════════════════════════════════════════════════════════════ -->

      <!-- ═══ Cx-2 偏差评价独立视图（sheetName 包含 "-2"） ═══ -->
      <div v-if="isDeviationSheet" class="cct-deviation-standalone">
        <!-- 顶部信息 -->
        <div class="cct-header">
          <div class="cct-header-title">
            <span class="cct-cycle-badge">{{ wpCode }}</span>
            <span class="cct-cycle-name">{{ cycleName }} — 评价控制偏差</span>
          </div>
          <div class="cct-project-info">
            <span class="cct-info-item">客户：{{ clientName || '—' }}</span>
            <span class="cct-info-item">会计期间：{{ year }}年度</span>
          </div>
        </div>

        <!-- 双模式切换 (结构化视图 ↔ 在线编辑) -->
        <div class="cct-mode-bar">
          <el-segmented v-model="deviationViewMode" :options="deviationModeOptions" size="small" />
        </div>

        <!-- 结构化视图 -->
        <template v-if="deviationViewMode === 'structured'">
          <!-- 蓝色渐变引导区 -->
          <div class="cct-guidance-area">
            <div class="cct-guidance-header">
              <el-icon><InfoFilled /></el-icon>
              <span>偏差评价决策树 — 6步推导控制有效性</span>
            </div>
            <div class="cct-guidance-steps">
              <div class="step-item"><span class="step-num">①</span><span class="step-text">判断是否偏差</span></div>
              <div class="step-item"><span class="step-num">②</span><span class="step-text">确定偏差性质</span></div>
              <div class="step-item"><span class="step-num">③</span><span class="step-text">确定应对措施</span></div>
              <div class="step-item"><span class="step-num">④</span><span class="step-text">扩大样本验证</span></div>
              <div class="step-item"><span class="step-num">⑤</span><span class="step-text">缺陷评价(A14)</span></div>
              <div class="step-item"><span class="step-num">⑥</span><span class="step-text">设计缺陷判断</span></div>
            </div>
          </div>

          <!-- 决策树组件（直接渲染，非弹窗） -->
          <CControlTestDecisionTree
            :wp-code="wpCode"
            :dev-index="activeDeviationIndex"
            :dev-state="activeDeviationState"
            :control-name="activeDeviationControlName"
            :control-names="allControlNames"
            :control-count="state.summaryRows.length"
            :readonly="isReadonly"
            :update-deviation-step="updateDeviationStep"
            :writeback-defect="writebackDefect"
            :build-defect-summary="buildDefectSummary"
            :exception-desc="activeExceptionDesc"
            :update-exception-desc="updateExceptionDesc"
            @navigate="handleDeviationNavigateStandalone"
            @change-dev-index="handleChangeDevIndex"
          />
        </template>

        <!-- 在线编辑 (OnlyOffice) -->
        <template v-else>
          <div class="cct-oo-container">
            <GtOnlyOfficeSheet
              v-if="wpId"
              :wp-id="wpId"
              :project-id="projectId"
              :sheet-name="sheetName || ''"
              :readonly="isReadonly"
            />
          </div>
        </template>
      </div>

      <!-- ═══ L0 Main Console — 汇总表模式（非偏差评价sheet） ═══ -->
      <template v-else>

      <!-- 顶部项目信息 + 循环上下文 -->
      <div class="cct-header">
        <div class="cct-header-title">
          <span class="cct-cycle-badge">{{ wpCode }}</span>
          <span class="cct-cycle-name">{{ cycleName }}控制测试</span>
        </div>
        <div class="cct-project-info">
          <span class="cct-info-item">客户：{{ clientName || '—' }}</span>
          <span class="cct-info-item">会计期间：{{ year }}年度</span>
        </div>
        <!-- B23/B50 快捷跳转 Chips -->
        <div class="cct-linkage-chips">
          <span class="cct-linkage-label">关联底稿：</span>
          <GtIndexChip value="B23" :context="b23Context" />
          <GtIndexChip value="B50" :context="b50Context" />
        </div>
      </div>

      <!-- 蓝色渐变引导区 (4步) -->
      <div class="cct-guidance-area">
        <div class="cct-guidance-header">
          <el-icon><InfoFilled /></el-icon>
          <span>操作流程引导</span>
        </div>
        <div class="cct-guidance-steps">
          <div class="step-item">
            <span class="step-num">①</span>
            <span class="step-text">目录汇总</span>
          </div>
          <div class="step-item">
            <span class="step-num">②</span>
            <span class="step-text">控制清单</span>
          </div>
          <div class="step-item">
            <span class="step-num">③</span>
            <span class="step-text">逐控制抽样</span>
          </div>
          <div class="step-item">
            <span class="step-num">④</span>
            <span class="step-text">偏差评价</span>
          </div>
        </div>
      </div>

      <!-- 15列控制测试汇总表（始终可见） -->
      <CControlTestSummaryTable
        :wp-code="wpCode"
        :rows="state.summaryRows"
        :readonly="isReadonly"
        :update-summary-text="updateSummaryText"
        :update-summary-enum="updateSummaryEnum"
        :update-summary-sample-size="updateSummarySampleSize"
        :add-control-point="addControlPoint"
        :remove-control-point="removeControlPoint"
        @navigate="handleSummaryNavigate"
        @add-request="openEditControlDialog(null)"
      />

      <!-- 循环整体结论 -->
      <el-card shadow="never" class="cct-cycle-conclusion-card">
        <template #header>
          <span class="cct-section-title">循环整体结论</span>
        </template>
        <div class="cct-conclusion-body">
          <el-select
            v-model="cycleConclusion"
            :disabled="isReadonly"
            placeholder="选择结论"
            style="width: 240px;"
          >
            <el-option label="控制有效" value="控制有效" />
            <el-option label="控制部分有效" value="控制部分有效" />
            <el-option label="控制无效" value="控制无效" />
          </el-select>
          <div v-if="hasSomeDeviation" class="cct-deviation-warning">
            <el-icon><WarningFilled /></el-icon>
            <span>存在识别出偏差的控制点，请确认整体结论</span>
          </div>
        </div>
      </el-card>

      <!-- 编制提示（底部折叠） -->
      <details class="cct-compilation-tips">
        <summary>编制提示</summary>
        <div class="cct-tips-content">
          <p>1. 控制测试旨在验证内部控制在审计期间运行的有效性。</p>
          <p>2. 汇总表需按循环列示所有被测控制点，确保覆盖认定层次重大风险所涉及的关键控制。</p>
          <p>3. 样本规模参照致同 2025 修订版样本规模区间表确定（频率×次数→最小样本量），可根据职业判断调整。</p>
          <p>4. 抽样结果中标记为「偏差」的项目，需在 Cx-2 偏差评价决策树中进一步分析其性质并推导结论。</p>
          <p>5. 如决策树推导至「控制缺陷」，应联动 A14 内控缺陷评价底稿进行缺陷等级评价。</p>
          <p>6. 循环整体结论变更时通过 EventBus 通知 B50 更新控制风险评估。</p>
        </div>
      </details>

      <!-- 右下角浮动按钮：新增控制点 -->
      <div v-if="!isReadonly" class="cct-fab-container">
        <el-button type="primary" circle size="large" class="cct-fab-btn" @click="handleFabAdd">
          <el-icon><Plus /></el-icon>
        </el-button>
      </div>
      </template><!-- end inner v-else (L0 汇总表模式) -->
    </template><!-- end outer v-else (loading完成) -->

    <!-- ═══════════════════════════════════════════════════════════════════
         L0.5 新增/编辑控制点 Dialog (70% width)
         ═══════════════════════════════════════════════════════════════════ -->
    <el-dialog
      v-model="editControlDialogVisible"
      :title="editControlDialogTitle"
      width="70%"
      :close-on-click-modal="false"
      append-to-body
      class="cct-edit-dialog"
    >
      <!-- 编制提示（琥珀色块，供用户参考 + AI system context） -->
      <div class="cct-edit-tips">
        <div class="cct-edit-tips-title">📋 编制提示</div>
        <ul class="cct-edit-tips-list">
          <li>从 B23 识别的本循环关键流程中选择被测控制，确保覆盖认定层次重大错报风险</li>
          <li>控制频率决定最小样本量：每年→1，每季→2，每月→2~5，每周→5~15，每天→20~40</li>
          <li>认定须选择与该控制直接相关的财务报表认定（完整性/存在/准确性等）</li>
          <li>详细描述应包含：谁执行、什么频率、做什么、产生什么证据、如何复核</li>
          <li>上传参考资料（制度/访谈记录/流程图）可辅助AI生成更准确的控制描述</li>
        </ul>
      </div>

      <!-- 主体：左侧表单 + 右侧附件上传 -->
      <div class="cct-edit-body">
        <!-- 左侧表单区 -->
        <div class="cct-edit-form-area">
          <el-form label-position="top" class="cct-edit-form">
            <!-- Row 1: 子流程 + 控制编号 + 控制名称 -->
            <div class="cct-edit-form-grid">
              <el-form-item label="子流程">
                <el-input v-model="editForm.subProcess" :placeholder="cyclePlaceholders.subProcess" />
              </el-form-item>
              <el-form-item label="控制编号">
                <el-input v-model="editForm.controlId" :placeholder="cyclePlaceholders.controlId" />
              </el-form-item>
              <el-form-item label="控制名称" class="cct-edit-form-wide">
                <el-input v-model="editForm.controlName" placeholder="控制名称（必填）" />
              </el-form-item>
            </div>

            <!-- 详细控制描述 (AI参考编制提示+附件) -->
            <el-form-item label="详细控制描述">
              <div class="cct-field-with-ai">
                <el-input v-model="editForm.description" type="textarea" :autosize="{minRows:3,maxRows:8}" placeholder="描述控制活动的具体内容（AI可根据上传的参考资料自动生成）" />
                <el-button size="small" type="primary" plain class="cct-ai-btn" :loading="aiGenerating" @click="handleAiGenerateDescription">
                  <el-icon><MagicStick /></el-icon> AI
                </el-button>
              </div>
              <div v-if="editAttachments.length > 0" class="cct-ai-context-hint">
                <el-icon><InfoFilled /></el-icon>
                AI将参考已上传的 {{ editAttachments.length }} 份资料生成描述
              </div>
            </el-form-item>

            <!-- Row 2: 受影响交易 + 认定(多选) -->
            <div class="cct-edit-form-grid">
              <el-form-item label="受影响的交易、账户余额和披露" class="cct-edit-form-wide">
                <el-input v-model="editForm.affectedItems" :placeholder="cyclePlaceholders.affectedItems" />
              </el-form-item>
              <el-form-item label="认定">
                <el-select v-model="editForm.assertion" multiple collapse-tags placeholder="选择认定">
                  <el-option v-for="o in ASSERTION_OPTIONS" :key="o" :label="o" :value="o" />
                </el-select>
              </el-form-item>
            </div>

            <!-- Row 3: 控制属性 + 控制频率 + 风险 -->
            <div class="cct-edit-form-grid">
              <el-form-item label="控制属性">
                <el-select v-model="editForm.attribute" placeholder="选择属性">
                  <el-option v-for="o in ATTRIBUTE_OPTIONS" :key="o" :label="o" :value="o" />
                </el-select>
              </el-form-item>
              <el-form-item label="控制频率">
                <el-select v-model="editForm.frequency" placeholder="选择频率">
                  <el-option v-for="o in FREQUENCY_OPTIONS" :key="o" :label="o" :value="o" />
                </el-select>
              </el-form-item>
              <el-form-item label="与控制相关的风险">
                <el-select v-model="editForm.relatedRisk" placeholder="风险等级">
                  <el-option v-for="o in RISK_OPTIONS" :key="o" :label="o" :value="o" />
                </el-select>
              </el-form-item>
            </div>

            <!-- Row 4: 测试方法(多选) + 样本量 -->
            <div class="cct-edit-form-grid">
              <el-form-item label="测试方法" class="cct-edit-form-wide">
                <el-select v-model="editForm.testMethod" multiple collapse-tags placeholder="选择方法">
                  <el-option v-for="o in TEST_METHOD_OPTIONS" :key="o" :label="o" :value="o" />
                </el-select>
              </el-form-item>
              <el-form-item label="范围（样本量）">
                <el-input-number v-model="editForm.sampleSize" :min="0" :controls="false" placeholder="样本量" />
                <div v-if="editSampleSizeHint" class="cct-sample-hint">{{ editSampleSizeHint }}</div>
              </el-form-item>
            </div>
          </el-form>
        </div>

        <!-- 右侧附件上传区 -->
        <div class="cct-edit-attach-area">
          <div class="cct-edit-attach-title">📎 参考资料</div>
          <div class="cct-edit-attach-desc">上传制度文档、访谈记录、流程图等，OCR识别后供AI调用生成控制描述</div>
          <el-upload
            :file-list="editAttachments"
            :auto-upload="false"
            :on-change="handleEditAttachChange"
            :on-remove="handleEditAttachRemove"
            accept=".pdf,.docx,.doc,.png,.jpg,.jpeg,.tif,.tiff"
            :limit="5"
            class="cct-edit-upload"
          >
            <el-tooltip
              content="上传内控手册、流程图、访谈记录、制度文件等，OCR识别后AI可据此生成更准确的控制描述"
              placement="top"
              :show-after="300"
            >
              <el-button size="small" type="primary" plain>
                <el-icon><Upload /></el-icon> 上传文件
              </el-button>
            </el-tooltip>
            <template #tip>
              <div class="cct-upload-tip">支持 PDF/Word/图片，最多5份</div>
            </template>
          </el-upload>
          <!-- 已识别内容预览 -->
          <div v-if="editOcrTexts.length > 0" class="cct-ocr-preview">
            <div class="cct-ocr-preview-title">已识别内容：</div>
            <div v-for="(txt, ti) in editOcrTexts" :key="ti" class="cct-ocr-preview-item">
              <span class="cct-ocr-filename">{{ editAttachments[ti]?.name || `文件${ti+1}` }}</span>
              <span class="cct-ocr-snippet">{{ txt.slice(0, 80) }}{{ txt.length > 80 ? '...' : '' }}</span>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="editControlDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEditControlPoint">保存</el-button>
      </template>
    </el-dialog>

    <!-- ═══════════════════════════════════════════════════════════════════
         L1 Control Detail Dialog (80% width)
         ═══════════════════════════════════════════════════════════════════ -->
    <el-dialog
      v-model="controlDialogVisible"
      :title="controlDialogTitle"
      width="80%"
      :close-on-click-modal="false"
      :close-on-press-escape="true"
      destroy-on-close
      append-to-body
      class="cct-l1-dialog"
    >
      <CControlTestSubPage
        v-if="controlDialogVisible"
        :wp-id="wpId"
        :project-id="projectId"
        :wp-code="wpCode"
        :page-index="activeControlIndex"
        :page="activeControlPage"
        :control-name="activeControlName"
        :readonly="isReadonly"
        :update-ctrl-page-text="updateCtrlPageText"
        :update-ctrl-page-enum="updateCtrlPageEnum"
        :update-ctrl-page-sample-size="updateCtrlPageSampleSize"
        :add-sample="addSample"
        :remove-sample="removeSample"
        :update-sample-description="updateSampleDescription"
        :update-sample-result="updateSampleResult"
        :update-summary-deviation="handleDeviationBackfill"
        @navigate="handleSubPageNavigate"
      />
      <template #footer>
        <div class="cct-dialog-footer">
          <el-button @click="controlDialogVisible = false">关闭</el-button>
          <el-button
            v-if="activeControlHasDeviation"
            type="warning"
            @click="openDeviationFromControl"
          >
            进入偏差评价 →
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- ═══════════════════════════════════════════════════════════════════
         L2 Deviation Decision Tree Dialog (65% width, nested)
         ═══════════════════════════════════════════════════════════════════ -->
    <el-dialog
      v-model="deviationDialogVisible"
      :title="deviationDialogTitle"
      width="65%"
      :close-on-click-modal="false"
      :close-on-press-escape="true"
      destroy-on-close
      append-to-body
      class="cct-l2-dialog"
    >
      <CControlTestDecisionTree
        v-if="deviationDialogVisible"
        :wp-code="wpCode"
        :dev-index="activeDeviationIndex"
        :dev-state="activeDeviationState"
        :control-name="activeDeviationControlName"
        :control-names="allControlNames"
        :control-count="state.summaryRows.length"
        :readonly="isReadonly"
        :update-deviation-step="updateDeviationStep"
        :writeback-defect="writebackDefect"
        :build-defect-summary="buildDefectSummary"
        :exception-desc="activeExceptionDesc"
        :update-exception-desc="updateExceptionDesc"
        @navigate="handleDeviationNavigate"
        @change-dev-index="handleChangeDevIndex"
      />
      <template #footer>
        <div class="cct-dialog-footer">
          <el-button @click="deviationDialogVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted, onBeforeUnmount } from 'vue'
import { InfoFilled, Plus, WarningFilled, MagicStick, Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/project'
import { useCControlTestData } from '@/composables/useCControlTestData'
import { createEmptyState, type DecisionTreeState } from '@/composables/useDeviationDecisionTree'
import { CYCLE_CONFIG } from './composables/useCControlTest'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import GtOnlyOfficeSheet from '@/components/workpaper/GtOnlyOfficeSheet.vue'
import CControlTestSummaryTable from './cControlTest/CControlTestSummaryTable.vue'
import CControlTestSubPage from './cControlTest/CControlTestSubPage.vue'
import CControlTestDecisionTree from './cControlTest/CControlTestDecisionTree.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode: string
  year: number
  readonly?: boolean
  sheetName?: string
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── Derived ─────────────────────────────────────────────────────────────────

const cycleNum = computed(() => parseInt(props.wpCode.replace(/^C/i, ''), 10) || 2)
/** 检测当前 sheetName 是否为偏差评价表 (Cx-2) */
const isDeviationSheet = computed(() => {
  const sn = props.sheetName || ''
  // 匹配 "C2-2评价控制偏差" / "C14-2评价控制偏差" / 含 "-2" 的偏差sheet
  return /C\d+-2/i.test(sn) || /评价控制偏差/.test(sn)
})
const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')
const wpCodeRef = toRef(props, 'wpCode')
const isReadonly = computed(() => props.readonly ?? false)

const cycleName = computed(() => {
  const config = CYCLE_CONFIG[cycleNum.value]
  return config?.name || `循环${cycleNum.value}`
})

/** B23 流程编号（用于 GtIndexChip context） */
const b23Context = computed(() => {
  const config = CYCLE_CONFIG[cycleNum.value]
  if (!config) return ''
  return `${config.name} — 流程${config.b23ProcessNum}`
})

/** B50 上下文（用于 GtIndexChip context） */
const b50Context = computed(() => {
  const config = CYCLE_CONFIG[cycleNum.value]
  if (!config) return ''
  return `${config.name} — 控制风险评估`
})

// ─── Project Info ────────────────────────────────────────────────────────────

const projectStore = useProjectStore()
const clientName = computed(() => projectStore.clientName || '')

// ─── Data Composable ─────────────────────────────────────────────────────────

const { state, loading, selfLoad, flushPendingSaves,
  updateSummaryText, updateSummaryEnum, updateSummarySampleSize,
  addControlPoint, removeControlPoint,
  updateCtrlPageText, updateCtrlPageEnum, updateCtrlPageSampleSize,
  addSample, removeSample, updateSampleDescription, updateSampleResult,
  updateDeviationStep, writebackDefect, buildDefectSummary } =
  useCControlTestData(wpIdRef, projectIdRef, wpCodeRef, isReadonly)

// ─── Dialog State ────────────────────────────────────────────────────────────

/** L1 控制测试详情弹窗 */
const controlDialogVisible = ref(false)
const activeControlIndex = ref(0)

/** L2 偏差评价弹窗 */
const deviationDialogVisible = ref(false)
const activeDeviationIndex = ref(0)

/** 循环整体结论 */
const cycleConclusion = ref<string>('')

/** Cx-2 偏差评价双模式切换 */
const deviationViewMode = ref<'structured' | 'online-edit'>('structured')
const deviationModeOptions = [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'online-edit' },
]

// ─── L0 → L1: Control Page helpers ──────────────────────────────────────────

/** 当前 L1 控制测试子页数据 */
const activeControlPage = computed(() => {
  const idx = activeControlIndex.value
  if (idx >= 0 && idx < state.value.controlPages.length) {
    return state.value.controlPages[idx]
  }
  return { attribute: '', frequency: '', relatedRisk: '', testMethod: '',
    testProcedure: '', populationDef: '', populationSource: '',
    sampleSize: null, samplingMethod: '', samplingProcess: '',
    deviationDef: '', samples: [] }
})

/** 当前 L1 控制点名称 */
const activeControlName = computed(() => {
  const idx = activeControlIndex.value
  if (idx >= 0 && idx < state.value.summaryRows.length) {
    return state.value.summaryRows[idx].controlName || ''
  }
  return ''
})

/** 当前 L1 控制点是否有偏差 */
const activeControlHasDeviation = computed(() => {
  const idx = activeControlIndex.value
  if (idx >= 0 && idx < state.value.summaryRows.length) {
    return state.value.summaryRows[idx].hasDeviation === '是'
  }
  return false
})

/** L1 Dialog 标题 */
const controlDialogTitle = computed(() => {
  const idx = activeControlIndex.value + 1
  const name = activeControlName.value
  return `${props.wpCode}-1-${idx} ${name || '控制测试'} — 控制测试详情`
})

// ─── L1 → L2: Deviation helpers ─────────────────────────────────────────────

/** 当前 L2 偏差评价状态 */
const activeDeviationState = computed<DecisionTreeState>(() => {
  const idx = activeDeviationIndex.value
  if (idx >= 0 && idx < state.value.deviationStates.length) {
    return state.value.deviationStates[idx]
  }
  return createEmptyState()
})

/** 当前 L2 偏差评价控制点名称 */
const activeDeviationControlName = computed(() => {
  const idx = activeDeviationIndex.value
  if (idx >= 0 && idx < state.value.summaryRows.length) {
    return state.value.summaryRows[idx].controlName || ''
  }
  return ''
})

/** L2 Dialog 标题 */
const deviationDialogTitle = computed(() => {
  const idx = activeDeviationIndex.value + 1
  const name = activeDeviationControlName.value
  return `${props.wpCode}-2 评价控制偏差 — 控制点${idx}: ${name || ''}`
})

/** 全部控制点名称列表 */
const allControlNames = computed(() => {
  return state.value.summaryRows.map(r => r.controlName || '')
})

/** 是否有任意控制点存在偏差 */
const hasSomeDeviation = computed(() => {
  return state.value.summaryRows.some(r => r.hasDeviation === '是')
})

// ─── 控制例外描述 (持久化) ───────────────────────────────────────────────────

/** 当前选中控制点的例外描述 */
const activeExceptionDesc = computed(() => {
  const idx = activeDeviationIndex.value
  if (idx >= 0 && idx < state.value.deviationStates.length) {
    return (state.value.deviationStates[idx] as any)?.exceptionDesc || ''
  }
  return ''
})

/** 更新控制点的例外描述（持久化到 checklist_responses） */
function updateExceptionDesc(devIndex: number, desc: string) {
  if (isReadonly.value) return
  // 利用 updateDeviationStep 来保存例外描述（复用 deviation 持久化通道）
  updateDeviationStep(devIndex, 'exceptionDesc', desc)
}

// ─── Navigation Handlers ─────────────────────────────────────────────────────

/**
 * 汇总表 @navigate 事件处理
 * - `ctrl-{m}` → 打开 L1 Dialog
 * - `directory` → 忽略（L0 始终可见）
 */
function handleSummaryNavigate(view: string) {
  const ctrlMatch = view.match(/^ctrl-(\d+)$/)
  if (ctrlMatch) {
    const idx = parseInt(ctrlMatch[1], 10) - 1
    openControlDialog(idx)
    return
  }
  // 'directory' 等其他事件在 L0 模式下忽略
}

/**
 * 子页 @navigate 事件处理
 * - `summary` / `directory` → 关闭 L1 Dialog
 * - `deviation-{m}` → 打开 L2 Dialog
 */
function handleSubPageNavigate(view: string) {
  if (view === 'summary' || view === 'directory') {
    controlDialogVisible.value = false
    return
  }
  const devMatch = view.match(/^deviation-(\d+)$/)
  if (devMatch) {
    const idx = parseInt(devMatch[1], 10) - 1
    openDeviationDialog(idx)
    return
  }
}

/**
 * 偏差评价 @navigate 事件处理
 * - `summary` / `directory` → 关闭 L2 Dialog
 */
function handleDeviationNavigate(view: string) {
  if (view === 'summary' || view === 'directory') {
    deviationDialogVisible.value = false
    return
  }
}

/** 切换偏差评价的控制点索引 */
function handleChangeDevIndex(index: number) {
  activeDeviationIndex.value = index
}

/** 独立偏差评价视图的导航处理（不关闭弹窗，因为没有弹窗） */
function handleDeviationNavigateStandalone(_view: string) {
  // 独立视图模式下 navigate 事件忽略（已经在页面上，无需切换）
}

// ─── Dialog Openers ──────────────────────────────────────────────────────────

/** 打开 L1 控制测试详情 Dialog */
function openControlDialog(index: number) {
  activeControlIndex.value = index
  controlDialogVisible.value = true
}

/** 打开 L2 偏差评价 Dialog */
function openDeviationDialog(index: number) {
  activeDeviationIndex.value = index
  deviationDialogVisible.value = true
}

/** 从 L1 的 "进入偏差评价" 按钮打开 L2 */
function openDeviationFromControl() {
  openDeviationDialog(activeControlIndex.value)
}

// ─── Deviation Backfill ──────────────────────────────────────────────────────

/** 偏差回填汇总表 */
function handleDeviationBackfill(pageIndex: number, hasDeviation: '是' | '否') {
  if (isReadonly.value) return
  if (pageIndex >= 0 && pageIndex < state.value.summaryRows.length) {
    updateSummaryEnum(pageIndex, 'hasDeviation', hasDeviation)
  }
}

// ─── Edit Control Point Dialog (L0.5) ────────────────────────────────────────

/** 命名区域下拉常量 */
const ASSERTION_OPTIONS = ['存在/发生', '完整性', '准确性/计价和分摊', '权利和义务', '截止', '分类', '列报']
const ATTRIBUTE_OPTIONS = ['人工的', '自动化的', '人工依赖信息系统控制']
const FREQUENCY_OPTIONS = ['每笔交易', '每天', '每周', '每半月', '每月', '每季度', '每年', '非常规/低运行频率', '其他']
const RISK_OPTIONS = ['高', '中', '低']
const TEST_METHOD_OPTIONS = ['询问', '检查', '观察', '重新执行', '前期', '前推', '利用内部审计工作', '利用服务机构的审计报告']

interface EditFormData {
  subProcess: string
  controlId: string
  controlName: string
  description: string
  affectedItems: string
  assertion: string[]
  attribute: string
  frequency: string
  relatedRisk: string
  testMethod: string[]
  sampleSize: number | null
  hasDeviation: string
  remediation: string
  defect: string
}

function createEmptyEditForm(): EditFormData {
  return {
    subProcess: '', controlId: '', controlName: '', description: '',
    affectedItems: '', assertion: [], attribute: '', frequency: '',
    relatedRisk: '', testMethod: [], sampleSize: null, hasDeviation: '',
    remediation: '', defect: '',
  }
}

const editControlDialogVisible = ref(false)
const editControlIndex = ref<number | null>(null) // null = new, number = edit existing
const editForm = ref<EditFormData>(createEmptyEditForm())

const editControlDialogTitle = computed(() =>
  editControlIndex.value === null ? '新增控制点' : `编辑控制点 — ${editForm.value.controlName || ''}`,
)

/** 各循环对应的placeholder示例（动态按wpCode区分） */
const cyclePlaceholders = computed(() => {
  const placeholders: Record<number, { subProcess: string; controlId: string; affectedItems: string }> = {
    2:  { subProcess: '如：销售订单处理', controlId: '如：SO-001', affectedItems: '如：销售收入、应收账款' },
    3:  { subProcess: '如：现金收付流程', controlId: '如：CM-001', affectedItems: '如：货币资金、银行存款' },
    4:  { subProcess: '如：采购订单审批', controlId: '如：PO-001', affectedItems: '如：应付账款、采购成本' },
    5:  { subProcess: '如：投资决策审批', controlId: '如：INV-001', affectedItems: '如：长期股权投资、投资收益' },
    6:  { subProcess: '如：固定资产购置', controlId: '如：FA-001', affectedItems: '如：固定资产、累计折旧' },
    7:  { subProcess: '如：工程项目立项', controlId: '如：CIP-001', affectedItems: '如：在建工程、工程物资' },
    8:  { subProcess: '如：无形资产确认', controlId: '如：IA-001', affectedItems: '如：无形资产、长期待摊费用' },
    9:  { subProcess: '如：研发立项审批', controlId: '如：RD-001', affectedItems: '如：研发费用、开发支出' },
    10: { subProcess: '如：薪酬计提发放', controlId: '如：HR-001', affectedItems: '如：应付职工薪酬、管理费用' },
    11: { subProcess: '如：费用报销审批', controlId: '如：ADM-001', affectedItems: '如：管理费用、其他应收款' },
    12: { subProcess: '如：纳税申报', controlId: '如：TAX-001', affectedItems: '如：应交税费、税金及附加' },
    13: { subProcess: '如：借款合同管理', controlId: '如：DEBT-001', affectedItems: '如：短期借款、应付利息' },
    14: { subProcess: '如：租赁合同签订', controlId: '如：LEASE-001', affectedItems: '如：使用权资产、租赁负债' },
    15: { subProcess: '如：关联交易审批', controlId: '如：RP-001', affectedItems: '如：关联方应收/应付、关联交易' },
  }
  return placeholders[cycleNum.value] || placeholders[2]
})

/** 样本量提示（基于频率） */
const editSampleSizeHint = computed(() => {
  const freq = editForm.value.frequency
  if (!freq) return ''
  const hints: Record<string, string> = {
    '每年': '建议: 1',
    '每季度': '建议: 2',
    '每月': '建议: 2~5',
    '每周': '建议: 5~15',
    '每半月': '建议: 10%~20%(最多40)',
    '每天': '建议: 20~40',
    '每笔交易': '建议: 25~60',
  }
  return hints[freq] || ''
})

/** 打开编辑控制点 Dialog */
function openEditControlDialog(index: number | null) {
  // 重置附件和OCR状态
  editAttachments.value = []
  editOcrTexts.value = []

  if (index !== null && index >= 0 && index < state.value.summaryRows.length) {
    // Edit existing
    const row = state.value.summaryRows[index]
    editForm.value = {
      subProcess: row.subProcess || '',
      controlId: row.controlId || '',
      controlName: row.controlName || '',
      description: row.description || '',
      affectedItems: row.affectedItems || '',
      assertion: row.assertion ? row.assertion.split(',').map(s => s.trim()).filter(Boolean) : [],
      attribute: row.attribute || '',
      frequency: row.frequency || '',
      relatedRisk: row.relatedRisk || '',
      testMethod: row.testMethod ? row.testMethod.split(',').map(s => s.trim()).filter(Boolean) : [],
      sampleSize: row.sampleSize ?? null,
      hasDeviation: row.hasDeviation || '',
      remediation: row.remediation || '',
      defect: row.defect || '',
    }
    editControlIndex.value = index
  } else {
    // New
    editForm.value = createEmptyEditForm()
    editControlIndex.value = null
  }
  editControlDialogVisible.value = true
}

/** 保存编辑控制点 */
function saveEditControlPoint() {
  const form = editForm.value
  if (!form.controlName?.trim()) {
    ElMessage.warning('控制名称不能为空')
    return
  }

  if (editControlIndex.value === null) {
    // New: add row then update all fields
    addControlPoint(form.controlName.trim())
    const idx = state.value.summaryRows.length - 1
    applyEditFormToRow(idx, form)
  } else {
    // Edit existing: update all fields
    applyEditFormToRow(editControlIndex.value, form)
  }

  editControlDialogVisible.value = false
  ElMessage.success(editControlIndex.value === null ? '控制点已添加' : '控制点已更新')
}

/** 将表单数据写入指定行 */
function applyEditFormToRow(idx: number, form: EditFormData) {
  // Text fields
  const textFields = ['subProcess', 'controlId', 'controlName', 'description', 'affectedItems', 'remediation', 'defect'] as const
  for (const key of textFields) {
    if (form[key]) updateSummaryText(idx, key, form[key])
  }
  // Enum fields (multi-select stored as comma-separated)
  if (form.assertion.length) updateSummaryEnum(idx, 'assertion', form.assertion.join(','))
  if (form.testMethod.length) updateSummaryEnum(idx, 'testMethod', form.testMethod.join(','))
  // Single enum fields
  if (form.attribute) updateSummaryEnum(idx, 'attribute', form.attribute)
  if (form.frequency) updateSummaryEnum(idx, 'frequency', form.frequency)
  if (form.relatedRisk) updateSummaryText(idx, 'relatedRisk', form.relatedRisk)
  if (form.hasDeviation) updateSummaryEnum(idx, 'hasDeviation', form.hasDeviation)
  // Sample size
  if (form.sampleSize !== null) updateSummarySampleSize(idx, form.sampleSize)
}

// ─── 附件上传 + OCR + AI 生成 ────────────────────────────────────────────────

import http from '@/utils/http'

interface EditAttachFile {
  name: string
  raw?: File
  uid?: number
}

const editAttachments = ref<EditAttachFile[]>([])
const editOcrTexts = ref<string[]>([])
const aiGenerating = ref(false)

function handleEditAttachChange(file: any) {
  // el-upload on-change callback
  const raw = file.raw || file
  if (!raw) return
  editAttachments.value.push({ name: raw.name || file.name, raw, uid: file.uid })
  // 自动OCR识别
  doOcrForAttach(editAttachments.value.length - 1, raw)
}

function handleEditAttachRemove(file: any) {
  const idx = editAttachments.value.findIndex(f => f.uid === file.uid || f.name === file.name)
  if (idx >= 0) {
    editAttachments.value.splice(idx, 1)
    editOcrTexts.value.splice(idx, 1)
  }
}

/** OCR识别单个附件 */
async function doOcrForAttach(index: number, rawFile: File): Promise<void> {
  const formData = new FormData()
  formData.append('file', rawFile)
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const fields = (res?.data?.data ?? res?.data)?.extracted_fields || {}
    const text = fields.full_text || fields.summary || fields.content || Object.values(fields).join('\n') || ''
    // 确保 editOcrTexts 与 editAttachments 索引对齐
    while (editOcrTexts.value.length <= index) editOcrTexts.value.push('')
    editOcrTexts.value[index] = String(text).slice(0, 2000) // 截断防过长
  } catch {
    // OCR失败静默处理，附件已保留
    while (editOcrTexts.value.length <= index) editOcrTexts.value.push('')
    editOcrTexts.value[index] = ''
  }
}

/** AI生成控制描述（参考编制提示 + 已填字段 + 附件OCR文本） */
async function handleAiGenerateDescription(): Promise<void> {
  if (aiGenerating.value) return
  aiGenerating.value = true
  try {
    const form = editForm.value
    // 构建context
    const context: Record<string, string> = {}
    if (form.subProcess) context['子流程'] = form.subProcess
    if (form.controlName) context['控制名称'] = form.controlName
    if (form.controlId) context['控制编号'] = form.controlId
    if (form.attribute) context['控制属性'] = form.attribute
    if (form.frequency) context['控制频率'] = form.frequency
    if (form.affectedItems) context['受影响交易'] = form.affectedItems
    if (form.assertion.length) context['认定'] = form.assertion.join('、')
    if (form.testMethod.length) context['测试方法'] = form.testMethod.join('、')

    // 附件OCR文本作为参考资料
    const ocrMaterial = editOcrTexts.value.filter(t => t.trim()).join('\n---\n')
    if (ocrMaterial) context['参考资料（OCR识别）'] = ocrMaterial.slice(0, 3000)

    // 编制提示作为system指令的一部分
    const systemHint = '请根据以下信息，生成一段专业的内部控制活动描述（100~200字），需包含：谁执行、什么频率、做什么、产生什么证据、如何复核。'

    const res = await http.post(
      `/api/workpapers/${props.wpId}/ai/generate-text`,
      {
        prompt: systemHint,
        context,
        existingContent: form.description || '',
        section: 'control-description',
      },
      { _silent: true } as any,
    )
    const generated = res?.data?.data?.content || res?.data?.content || res?.data?.text || ''
    if (generated) {
      editForm.value.description = generated
      ElMessage.success('AI已生成控制描述')
    } else {
      ElMessage.info('AI未返回内容，请手动填写')
    }
  } catch {
    ElMessage.warning('AI服务暂不可用，请手动填写')
  } finally {
    aiGenerating.value = false
  }
}

// ─── FAB: 新增控制点 ────────────────────────────────────────────────────────

function handleFabAdd() {
  openEditControlDialog(null)
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await selfLoad()
})

onBeforeUnmount(() => {
  flushPendingSaves()
})
</script>

<style scoped>
.c-control-test {
  padding: 16px;
  max-width: 1200px;
  margin: 0 auto;
  font-size: 13px;
  position: relative;
}

.c-control-test.is-readonly {
  pointer-events: auto;
}

.loading-container {
  padding: 24px;
}

/* ─── Header ─── */
.cct-header {
  margin-bottom: 16px;
}

.cct-header-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.cct-cycle-badge {
  background: #e6f7ff;
  color: #1890ff;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
}

.cct-cycle-name {
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.cct-project-info {
  display: flex;
  gap: 24px;
  color: #6b7280;
  font-size: 13px;
}

.cct-info-item {
  display: inline-flex;
  align-items: center;
}

/* ─── Linkage Chips (B23/B50) ─── */
.cct-linkage-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.cct-linkage-label {
  font-size: 12px;
  color: #9ca3af;
}

/* ─── Guidance Area ─── */
.cct-guidance-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6eaf8 100%);
  border: 1px solid #b3d9f2;
  border-radius: 8px;
  padding: 14px 20px;
  margin-bottom: 20px;
}

.cct-guidance-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #1a73e8;
  margin-bottom: 10px;
  font-size: 13px;
}

.cct-guidance-steps {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 24px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #374151;
}

.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #1a73e8;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}

.step-text {
  font-size: 13px;
}

/* ─── Cycle Conclusion Card ─── */
.cct-cycle-conclusion-card {
  margin-top: 20px;
}

.cct-cycle-conclusion-card :deep(.el-card__header) {
  padding: 12px 20px;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.cct-section-title {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}

.cct-conclusion-body {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.cct-deviation-warning {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #d97706;
  font-size: 13px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  padding: 6px 12px;
  border-radius: 4px;
}

.cct-deviation-warning .el-icon {
  color: #f59e0b;
}

/* ─── FAB (Floating Action Button) ─── */
.cct-fab-container {
  position: fixed;
  bottom: 32px;
  right: 32px;
  z-index: 100;
}

/* ─── Mode Bar (Cx-2 双模式) ─── */
.cct-mode-bar {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
}

/* ─── OO Container ─── */
.cct-oo-container {
  min-height: 600px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.cct-fab-btn {
  width: 48px;
  height: 48px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

/* ─── L1/L2 Dialog 样式 ─── */
.cct-l1-dialog :deep(.el-dialog__header) {
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
  margin-right: 0;
}

.cct-l1-dialog :deep(.el-dialog__body) {
  padding: 16px 20px;
  max-height: 70vh;
  overflow-y: auto;
}

.cct-l1-dialog :deep(.el-dialog__footer) {
  padding: 12px 20px;
  border-top: 1px solid #e5e7eb;
}

.cct-l2-dialog :deep(.el-dialog__header) {
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
  margin-right: 0;
}

.cct-l2-dialog :deep(.el-dialog__body) {
  padding: 16px 20px;
  max-height: 65vh;
  overflow-y: auto;
}

.cct-l2-dialog :deep(.el-dialog__footer) {
  padding: 12px 20px;
  border-top: 1px solid #e5e7eb;
}

.cct-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* ─── Readonly 铁律：全局禁止编辑 ─── */
.c-control-test.is-readonly :deep(.el-input__inner),
.c-control-test.is-readonly :deep(.el-textarea__inner),
.c-control-test.is-readonly :deep(.el-select .el-input__inner),
.c-control-test.is-readonly :deep(.el-input-number) {
  cursor: not-allowed;
}

/* readonly 隐藏增删操作按钮（保留导航按钮） */
.c-control-test.is-readonly :deep(.cct-view-actions) {
  display: none;
}

/* ─── 编制提示 <details> 折叠 ─── */
.cct-compilation-tips {
  margin-top: 24px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  overflow: hidden;
}

.cct-compilation-tips summary {
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 500;
  color: #6b7280;
  background: #f9fafb;
  cursor: pointer;
  user-select: none;
}

.cct-compilation-tips summary:hover {
  background: #f3f4f6;
}

.cct-compilation-tips[open] summary {
  border-bottom: 1px solid #e5e7eb;
}

.cct-tips-content {
  padding: 12px 16px;
  font-size: 12px;
  color: #4b5563;
  line-height: 1.8;
}

.cct-tips-content p {
  margin: 0 0 4px;
}

/* ─── L0.5 Edit Control Dialog ─── */
.cct-edit-dialog :deep(.el-dialog__header) {
  padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb;
  margin-right: 0;
}

.cct-edit-dialog :deep(.el-dialog__body) {
  padding: 20px 24px;
  max-height: 70vh;
  overflow-y: auto;
}

.cct-edit-dialog :deep(.el-dialog__footer) {
  padding: 12px 20px;
  border-top: 1px solid #e5e7eb;
}

.cct-edit-form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0 16px;
}

.cct-edit-form-grid .cct-edit-form-wide {
  grid-column: span 2;
}

.cct-edit-form :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
}

.cct-edit-form :deep(.el-select) {
  width: 100%;
}

.cct-field-with-ai {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  width: 100%;
}

.cct-field-with-ai .el-input {
  flex: 1;
}

.cct-ai-btn {
  flex-shrink: 0;
  margin-top: 4px;
}

.cct-sample-hint {
  font-size: 12px;
  color: #f59e0b;
  margin-top: 4px;
}

/* ─── 编制提示（琥珀色块） ─── */
.cct-edit-tips {
  border-left: 3px solid #f59e0b;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 0 6px 6px 0;
}

.cct-edit-tips-title {
  font-weight: 600;
  font-size: 13px;
  color: #92400e;
  margin-bottom: 6px;
}

.cct-edit-tips-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: #78350f;
  line-height: 1.8;
}

.cct-edit-tips-list li {
  margin-bottom: 2px;
}

/* ─── 主体布局：左表单 + 右附件 ─── */
.cct-edit-body {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

.cct-edit-form-area {
  flex: 1 1 auto;
  min-width: 0;
}

.cct-edit-attach-area {
  flex: 0 0 220px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 14px;
}

.cct-edit-attach-title {
  font-weight: 600;
  font-size: 13px;
  color: #374151;
  margin-bottom: 6px;
}

.cct-edit-attach-desc {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 10px;
  line-height: 1.5;
}

.cct-edit-upload :deep(.el-upload-list) {
  margin-top: 8px;
}

.cct-upload-tip {
  font-size: 11px;
  color: #9ca3af;
  margin-top: 4px;
}

.cct-ai-context-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #2563eb;
  margin-top: 4px;
}

/* ─── OCR预览 ─── */
.cct-ocr-preview {
  margin-top: 12px;
  border-top: 1px dashed #e5e7eb;
  padding-top: 8px;
}

.cct-ocr-preview-title {
  font-size: 11px;
  color: #6b7280;
  font-weight: 500;
  margin-bottom: 4px;
}

.cct-ocr-preview-item {
  font-size: 11px;
  color: #4b5563;
  margin-bottom: 4px;
  line-height: 1.4;
}

.cct-ocr-filename {
  font-weight: 500;
  color: #1f2937;
  display: block;
}

.cct-ocr-snippet {
  color: #6b7280;
  font-style: italic;
}

/* ─── Print ─── */
@media print {
  .cct-guidance-area {
    display: none;
  }
  .cct-compilation-tips {
    display: none;
  }
  .cct-fab-container {
    display: none;
  }
}
</style>
