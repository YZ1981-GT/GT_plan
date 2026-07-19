<template>
  <div class="g6-tab-stage-classification">
    <!-- 方法论上下文（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p><strong>ECL三阶段划分标准（CAS 22）：</strong></p>
      <ul>
        <li><strong>Stage1</strong>：信用风险自初始确认以来未显著增加（或具有较低信用风险），按12个月ECL计提减值</li>
        <li><strong>Stage2</strong>：信用风险显著增加但未发生信用减值，按整个存续期ECL计提</li>
        <li><strong>Stage3</strong>：已发生信用减值（出现8项可观察信息之一），按整个存续期ECL计提且利息按净额确认</li>
      </ul>
      <p class="methodology-note">其他债权投资(FVOCI)减值计入OCI，不减少账面价值，但ECL三阶段划分规则与摊余成本口径一致。</p>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实其他债权投资信用风险三阶段划分（Stage1/2/3）的合理性，验证企业阶段判定与审计判定的一致性，为 G6-12 减值准备测算提供阶段依据。"
      class="objective-alert"
    />

    <!-- 工具栏：索引 + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G6-11" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ stageLogic.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <!-- Section标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G6-11 其他债权投资三阶段划分</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleAddProject">
          + 新增投资项目
        </el-button>
        <el-button size="small" @click="stageLogic.expandAll()">全部展开</el-button>
        <el-button size="small" @click="stageLogic.collapseAll()">全部折叠</el-button>
        <el-button size="small" :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="fillAiConclusion">
          🤖 AI辅助
        </el-button>
        <el-button size="small" @click="openReview">💬复核</el-button>
      </div>
    </div>

    <!-- 无数据占位 -->
    <el-empty v-if="stageLogic.rows.value.length === 0" description="暂无投资项目，点击“新增投资项目”开始" />

    <!-- 主表格：行式汇总视图（虚拟滚动 max-height 61行阈值） -->
    <el-table
      v-else
      :data="stageLogic.rows.value"
      border
      size="small"
      class="stage-main-table"
      :max-height="tableMaxHeight"
      :row-class-name="getRowClassName"
      row-key="id"
      :expand-row-keys="Array.from(stageLogic.expandedRowIds.value)"
      @expand-change="handleExpandChange"
    >
      <!-- 展开行：逐项检查明细 -->
      <el-table-column type="expand">
        <template #default="scope">
          <div class="expand-detail">
            <!-- (一) 信用风险是否显著增加 -->
            <div class="check-section">
              <div class="check-section-title">(一) 信用风险是否显著增加（13项考虑因素）</div>
              <el-table :data="scope.row.sectionOneChecks" border size="small" class="check-detail-table">
                <el-table-column label="序号" width="50" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="考虑因素" prop="label" min-width="300" />
                <el-table-column label="判断" width="140" align="center">
                  <template #default="{ $index, row: item }">
                    <el-select
                      v-if="!isReadonly"
                      :model-value="item.value"
                      size="small"
                      style="width: 100%"
                      @change="(v: string) => stageLogic.updateCheckValue(scope.row.id, 'significantIncrease', $index, v as any)"
                    >
                      <el-option value="是" label="是" />
                      <el-option value="否" label="否" />
                      <el-option value="不适用" label="不适用" />
                    </el-select>
                    <span v-else>{{ item.value }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <!-- (二) 是否具有较低信用风险 -->
            <div class="check-section">
              <div class="check-section-title">(二) 是否具有较低信用风险（3项同时满足）</div>
              <el-table :data="scope.row.sectionTwoChecks" border size="small" class="check-detail-table">
                <el-table-column label="序号" width="50" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="满足条件" prop="label" min-width="300" />
                <el-table-column label="判断" width="140" align="center">
                  <template #default="{ $index, row: item }">
                    <el-select
                      v-if="!isReadonly"
                      :model-value="item.value"
                      size="small"
                      style="width: 100%"
                      @change="(v: string) => stageLogic.updateCheckValue(scope.row.id, 'lowCreditRisk', $index, v as any)"
                    >
                      <el-option value="是" label="是" />
                      <el-option value="否" label="否" />
                    </el-select>
                    <span v-else>{{ item.value }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <!-- (三) 已发生信用减值的评估 -->
            <div class="check-section">
              <div class="check-section-title">(三) 已发生信用减值的评估（8项可观察信息）</div>
              <el-table :data="scope.row.sectionThreeChecks" border size="small" class="check-detail-table">
                <el-table-column label="序号" width="50" align="center">
                  <template #default="{ $index }">{{ $index + 1 }}</template>
                </el-table-column>
                <el-table-column label="可观察信息" prop="label" min-width="300" />
                <el-table-column label="判断" width="140" align="center">
                  <template #default="{ $index, row: item }">
                    <el-select
                      v-if="!isReadonly"
                      :model-value="item.value"
                      size="small"
                      style="width: 100%"
                      @change="(v: string) => stageLogic.updateCheckValue(scope.row.id, 'creditImpairment', $index, v as any)"
                    >
                      <el-option value="是" label="是" />
                      <el-option value="否" label="否" />
                    </el-select>
                    <span v-else>{{ item.value }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </template>
      </el-table-column>

      <!-- 投资项目 -->
      <el-table-column label="投资项目" prop="investProject" min-width="140" fixed="left">
        <template #default="{ row }">
          <div class="project-name-cell">
            <span>{{ row.investProject }}</span>
            <el-button
              v-if="!isReadonly"
              size="small"
              type="danger"
              link
              class="delete-btn"
              @click.stop="handleRemoveRow(row.id, row.investProject)"
            >
              🗑️
            </el-button>
          </div>
        </template>
      </el-table-column>

      <!-- 信用风险显著增加判定(综合) -->
      <el-table-column label="显著增加" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.hasSignificantIncrease ? 'danger' : 'success'" size="small">
            {{ row.hasSignificantIncrease ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 较低信用风险(综合) -->
      <el-table-column label="低风险" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.hasLowCreditRisk ? 'success' : 'info'" size="small">
            {{ row.hasLowCreditRisk ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 已发生减值(综合) -->
      <el-table-column label="已减值" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.hasCreditImpairment ? 'danger' : 'success'" size="small">
            {{ row.hasCreditImpairment ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 企业划分阶段(下拉) -->
      <el-table-column label="企业阶段" width="120" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.companyStage"
            size="small"
            style="width: 100%"
            @change="(v: string) => stageLogic.updateCompanyStage(row.id, v as any)"
          >
            <el-option value="Stage1" label="Stage1" />
            <el-option value="Stage2" label="Stage2" />
            <el-option value="Stage3" label="Stage3" />
          </el-select>
          <span v-else>{{ row.companyStage }}</span>
        </template>
      </el-table-column>

      <!-- 审计判断阶段(下拉) -->
      <el-table-column label="审计阶段" width="120" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.auditStage"
            size="small"
            style="width: 100%"
            @change="(v: string) => stageLogic.updateAuditStage(row.id, v as any)"
          >
            <el-option value="Stage1" label="Stage1" />
            <el-option value="Stage2" label="Stage2" />
            <el-option value="Stage3" label="Stage3" />
          </el-select>
          <span v-else>{{ row.auditStage }}</span>
        </template>
      </el-table-column>

      <!-- 一致性(公式badge) -->
      <el-table-column label="一致性" width="100" align="center">
        <template #default="{ row }">
          <span v-if="row.isConsistent" class="badge-consistent">✓一致</span>
          <span v-else class="badge-inconsistent">✗不一致</span>
        </template>
      </el-table-column>

      <!-- 差异说明 -->
      <el-table-column label="差异说明" min-width="180">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly && !row.isConsistent"
            :model-value="row.discrepancyNote"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            size="small"
            placeholder="请填写差异说明（必填）"
            :class="{ 'required-field': !row.discrepancyNote }"
            @input="(v: string) => stageLogic.updateDiscrepancyNote(row.id, v)"
          />
          <el-input
            v-else-if="!isReadonly && row.isConsistent"
            :model-value="row.discrepancyNote"
            size="small"
            placeholder=""
            @input="(v: string) => stageLogic.updateDiscrepancyNote(row.id, v)"
          />
          <span v-else>{{ row.discrepancyNote || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 索引(GtIndexChip) -->
      <el-table-column label="索引" width="120" align="center">
        <template #default="{ row }">
          <GtIndexChip :value="row.indexRef" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部：汇总区 + 审计结论 + 编制提示 -->
    <div v-if="stageLogic.rows.value.length > 0" class="bottom-section">
      <!-- 汇总统计 -->
      <div class="summary-stats">
        <span class="summary-label">阶段统计：</span>
        <el-tag type="success" size="small">Stage1: {{ stageLogic.summary.value.stage1Count }}</el-tag>
        <el-tag type="warning" size="small">Stage2: {{ stageLogic.summary.value.stage2Count }}</el-tag>
        <el-tag type="danger" size="small">Stage3: {{ stageLogic.summary.value.stage3Count }}</el-tag>
        <el-tag
          :type="stageLogic.summary.value.inconsistentCount > 0 ? 'danger' : 'info'"
          size="small"
        >
          不一致: {{ stageLogic.summary.value.inconsistentCount }}
        </el-tag>
        <span class="summary-total">合计: {{ stageLogic.summary.value.total }} 项</span>
      </div>

      <!-- 审计结论 el-card + AI按钮 -->
      <el-card class="conclusion-card" shadow="never">
        <template #header>
          <div class="conclusion-header">
            <span>审计结论</span>
            <el-button size="small" :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="fillAiConclusion">
              🤖 AI辅助
            </el-button>
          </div>
        </template>
        <el-input
          v-model="stageLogic.conclusion.value"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="对三阶段划分合理性的综合评价..."
        />
      </el-card>

      <!-- 编制提示 details 折叠 -->
      <details class="guide-details">
        <summary>📋 编制提示</summary>
        <div class="guide-content">
          <p>1. 三阶段划分是确定ECL计提方法的关键步骤：Stage1→12个月ECL，Stage2/3→整个存续期ECL</p>
          <p>2. (一)信用风险显著增加：13项考虑因素中任一项为"是"，则该投资项目信用风险显著增加</p>
          <p>3. (二)较低信用风险：3项条件须全部满足（全部为"是"），方可适用较低信用风险豁免</p>
          <p>4. (三)已发生信用减值：8项可观察信息中任一项为"是"，则直接归入Stage3</p>
          <p>5. 判定优先级：Stage3（已减值）> Stage2（显著增加）> Stage1（未显著增加/低风险）</p>
          <p>6. 企业划分阶段与审计判断阶段不一致时，必须填写差异说明</p>
          <p>7. 展开投资项目行可查看该项目的逐项检查明细</p>
          <p>8. 其他债权投资虽以公允价值计量，但减值准备按摊余成本口径计算，阶段划分规则与G4一致</p>
        </div>
      </details>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="audit-note-header"><span>审计说明</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述执行的审计程序、三阶段划分测试情况与结果、拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabStageClassification.vue — G6-11 其他债权投资三阶段划分
 *
 * Spec: .kiro/specs/g6-other-bond-investment-ecl/ Task 5.2
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 6.5
 *
 * 功能：
 * - 列式转置结构：源模板投资项目为列，前端转换为行式交互视图
 * - 三区块检查：(一)信用风险显著增加(13项) / (二)较低信用风险(3项) / (三)已发生信用减值(8项)
 * - 行式汇总视图：投资项目|显著增加|较低信用风险|已发生减值|企业阶段|审计阶段|一致性|差异说明|索引
 * - 支持展开/折叠详情模式（展开显示逐项检查明细）
 * - 虚拟滚动（61行阈值 → max-height）
 * - 顶部方法论上下文（琥珀色左边线+浅黄背景）
 * - 底部汇总区 + 审计结论textarea + AI按钮(stage-conclusion) + 编制提示折叠
 * - 不一致行红色高亮 + 强制差异说明(textarea)
 * - 动态投资项目增删（ElMessageBox.prompt输入名称）
 * - GtIndexChip索引列
 * - 复核按钮（inject openReviewDialog）
 *
 * 使用 useG6EclStageClassification composable
 */
import { computed, inject, watch, onMounted, ref } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useG6EclStageClassification } from '@/composables/useG6EclStageClassification'
import { useG6EclFormData } from '../../composables/useG6EclFormData'
import { useG6EclAiGenerate } from '../../composables/useG6EclAiGenerate'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG6EclAiGenerate(wpIdRef)

// ─── 初始化 composable ───
const isReadonlyRef = computed(() => props.isReadonly)
const htmlDataRef = computed(() => props.htmlData)

const stageLogic = useG6EclStageClassification({
  htmlData: htmlDataRef,
  isReadonly: isReadonlyRef,
})

// ─── 审计说明（持久化 checklist_responses, conclusion:null） ───
const NOTE_KEY = 'G6-11-stage-classification-audit-note'
const CONCLUSION_KEY = 'G6-11-stage-classification-conclusion'
const auditNote = ref('')
const noteFormData = useG6EclFormData({
  wpId: wpIdRef,
  projectId: computed(() => props.projectId),
})
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  noteFormData.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}

watch(() => stageLogic.conclusion.value, (val) => {
  if (props.isReadonly) return
  noteFormData.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
})

// ─── 虚拟滚动：61行阈值 → 设置 max-height 约520px（~61×50px行高+表头） ───
const VIRTUAL_SCROLL_THRESHOLD = 61
const tableMaxHeight = computed(() => {
  return stageLogic.rows.value.length > VIRTUAL_SCROLL_THRESHOLD ? 520 : undefined
})

// ─── 从htmlData初始化数据 ───
onMounted(async () => {
  stageLogic.init(props.htmlData)
  await noteFormData.loadAll()
  const n = noteFormData.allResponses.value.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const conc = noteFormData.allResponses.value.get(CONCLUSION_KEY)
  if (conc?.remark) stageLogic.conclusion.value = conc.remark
})

watch(() => props.htmlData, (newData) => {
  if (newData && stageLogic.rows.value.length === 0) {
    stageLogic.init(newData)
  }
})

// ─── 展开行处理（el-table expand事件） ───
function handleExpandChange(row: any, expandedRows: any[]): void {
  stageLogic.expandedRowIds.value.clear()
  for (const r of expandedRows) {
    stageLogic.expandedRowIds.value.add(r.id)
  }
}

// ─── 行样式：不一致行红色高亮 ───
function getRowClassName({ row }: { row: any }): string {
  if (!row.isConsistent) return 'row-inconsistent'
  return ''
}

// ─── 新增投资项目（ElMessageBox.prompt输入名称） ───
async function handleAddProject(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入投资项目名称',
      '新增投资项目',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '项目名称不能为空',
        inputPlaceholder: '例如：XX公司债券',
      },
    )
    if (value?.trim()) {
      stageLogic.addRow(value.trim())
      ElMessage.success(`已新增投资项目"${value.trim()}"`)
    }
  } catch {
    // 用户取消
  }
}

// ─── 删除投资项目确认 ───
async function handleRemoveRow(rowId: string, projectName: string): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认删除投资项目"${projectName}"及其所有检查数据？`,
      '删除确认',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    stageLogic.removeRow(rowId)
    ElMessage.success(`已删除"${projectName}"`)
  } catch {
    // 用户取消
  }
}

// ─── 打开复核对话 ───
function openReview(): void {
  openReviewDialog('G6-11-stage-classification')
}

// ─── AI辅助生成审计结论（stage-conclusion） ───
async function fillAiConclusion(): Promise<void> {
  if (props.isReadonly) return
  const s = stageLogic.summary.value
  const text = await generateAndConfirm(
    'stage-conclusion',
    stageLogic.conclusion.value || '',
    {
      total: s.total,
      stage1Count: s.stage1Count,
      stage2Count: s.stage2Count,
      stage3Count: s.stage3Count,
      inconsistentCount: s.inconsistentCount,
    },
    'AI 审计结论',
  )
  if (text) stageLogic.conclusion.value = text
}
</script>

<style scoped>
.g6-tab-stage-classification {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景）─── */
.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.8;
}

.methodology-context p {
  margin: 0 0 4px;
}

.methodology-context ul {
  margin: 0;
  padding-left: 18px;
}

.methodology-context li {
  margin-bottom: 2px;
}

.methodology-note {
  margin-top: 6px;
  color: #92400e;
  font-style: italic;
}

/* ─── 审计目标 / 工具栏 ─── */
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

/* ─── 审计说明卡片 ─── */
.audit-note-card {
  margin-top: 16px;
}
.audit-note-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

/* ─── Section标题栏 ─── */
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ─── 主表格 ─── */
.stage-main-table {
  width: 100%;
  font-size: var(--wp-font-size, 13px);
}

/* 不一致行红色高亮 */
:deep(.row-inconsistent) {
  background-color: #fef0f0 !important;
}

:deep(.row-inconsistent:hover > td) {
  background-color: #fde8e8 !important;
}

/* ─── 投资项目名称单元格 ─── */
.project-name-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.delete-btn {
  opacity: 0;
  transition: opacity 0.2s;
}

.project-name-cell:hover .delete-btn {
  opacity: 1;
}

/* ─── 一致性badge ─── */
.badge-consistent {
  color: #67c23a;
  font-weight: 600;
  font-size: 12px;
}

.badge-inconsistent {
  color: #f56c6c;
  font-weight: 700;
  font-size: 12px;
}

/* ─── 差异说明必填提示 ─── */
.required-field :deep(.el-textarea__inner),
.required-field :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}

/* ─── 展开详情区 ─── */
.expand-detail {
  padding: 12px 24px;
  background: #fafafa;
}

.check-section {
  margin-bottom: 16px;
}

.check-section:last-child {
  margin-bottom: 0;
}

.check-section-title {
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid #409eff;
}

.check-detail-table {
  width: 100%;
  font-size: 12px;
}

/* ─── 底部区域 ─── */
.bottom-section {
  margin-top: 16px;
}

/* 汇总统计 */
.summary-stats {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 12px;
}

.summary-label {
  font-weight: 700;
  color: #606266;
}

.summary-total {
  margin-left: 8px;
  font-weight: 600;
  color: #303133;
}

/* 审计结论卡片 */
.conclusion-card {
  margin-top: 12px;
}

.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

/* 编制提示 */
.guide-details {
  margin-top: 16px;
}

.guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  font-weight: 600;
}

.guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.guide-content p {
  margin: 0;
}
</style>
