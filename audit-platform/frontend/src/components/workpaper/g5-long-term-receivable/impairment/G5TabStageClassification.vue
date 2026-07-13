<!--
  G5TabStageClassification.vue — G5-9 长期应收款三阶段划分

  列式转置→行式交互视图（同G4-9方案）
  行式：债务人|显著增加|低风险|已减值|企业阶段|审计阶段|一致|差异说明|索引
  - determineStage规则计算审计判断阶段
  - 不一致红色高亮+强制差异说明
  - 展开/折叠详情（逐项检查明细）
  - 底部汇总（S1/S2/S3数量/不一致数）
  - 动态债务人增删（ElMessageBox.prompt输入名称）

  Spec: .kiro/specs/g5-long-term-receivable/ Task 11.1
  Requirements: 12.1~12.10
-->
<template>
  <div class="g5-tab-stage-classification">
    <!-- 方法论上下文（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p><strong>ECL三阶段划分标准（长期应收款）：</strong></p>
      <ul>
        <li><strong>Stage1</strong>：信用风险自初始确认以来未显著增加（或具有较低信用风险），按12个月ECL计提减值</li>
        <li><strong>Stage2</strong>：信用风险显著增加但未发生信用减值，按整个存续期ECL计提</li>
        <li><strong>Stage3</strong>：已发生信用减值（出现8项可观察信息之一），按整个存续期ECL计提且利息按净额确认</li>
      </ul>
    </div>

    <!-- Section标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G5-9 长期应收款三阶段划分</h3>
      <div class="head-actions tab-toolbar">
        <el-button size="small" :disabled="isReadonly" @click="handleAddDebtor">
          + 新增债务人
        </el-button>
        <el-button size="small" @click="stageLogic.expandAll()">全部展开</el-button>
        <el-button size="small" @click="stageLogic.collapseAll()">全部折叠</el-button>
        <el-button size="small" @click="openReview">💬复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：对各长期应收款债务人执行 ECL 三阶段划分，比对企业划分与审计判断的一致性，识别信用风险显著增加及已减值情形。
    </el-alert>

    <!-- 无数据占位 -->
    <el-empty v-if="stageLogic.rows.value.length === 0" description="暂无债务人，点击“新增债务人”开始" />

    <!-- 主表格：行式汇总视图 -->
    <el-table
      v-else
      :data="stageLogic.rows.value"
      border
      size="small"
      class="stage-main-table"
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

      <!-- 债务人 -->
      <el-table-column label="债务人" prop="debtor" min-width="140" fixed="left">
        <template #default="{ row }">
          <div class="debtor-name-cell">
            <span>{{ row.debtor }}</span>
            <el-button
              v-if="!isReadonly"
              size="small"
              type="danger"
              link
              class="delete-btn"
              @click.stop="handleRemoveRow(row.id, row.debtor)"
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

      <!-- 审计阶段(下拉) -->
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
            v-if="!isReadonly"
            :model-value="row.discrepancyNote"
            size="small"
            :placeholder="row.isConsistent ? '' : '请填写差异说明（必填）'"
            :class="{ 'required-field': !row.isConsistent && !row.discrepancyNote }"
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

      <!-- 审计说明 el-card -->
      <el-card class="audit-note-card" shadow="never">
        <template #header><div class="card-header"><span>审计说明</span></div></template>
        <el-input
          :model-value="auditNote"
          type="textarea"
          :autosize="{ minRows: 5 }"
          :disabled="isReadonly"
          placeholder="填写审计说明：可概述三阶段划分依据、企业与审计判断差异、信用风险显著增加/已减值识别情况。"
          @change="(val: string) => saveAuditNote(val)"
        />
      </el-card>

      <!-- 审计结论 el-card + AI按钮 -->
      <el-card class="conclusion-card" shadow="never">
        <template #header>
          <div class="conclusion-header">
            <span>审计结论</span>
            <el-button size="small" :disabled="isReadonly" @click="fillAiConclusion">
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
      <details class="g5-guide-details">
        <summary>📋 编制提示</summary>
        <div class="g5-guide-content">
          <p>1. 三阶段划分是确定ECL计提方法的关键步骤：Stage1→12个月ECL，Stage2/3→整个存续期ECL</p>
          <p>2. (一)信用风险显著增加：13项考虑因素中任一项为"是"，则该债务人信用风险显著增加</p>
          <p>3. (二)较低信用风险：3项条件须全部满足（全部为"是"），方可适用较低信用风险豁免</p>
          <p>4. (三)已发生信用减值：8项可观察信息中任一项为"是"，则直接归入Stage3</p>
          <p>5. 判定优先级：Stage3（已减值）> Stage2（显著增加且非低风险）> Stage1（未显著增加/低风险豁免）</p>
          <p>6. 企业划分阶段与审计判断阶段不一致时，必须填写差异说明</p>
          <p>7. 展开债务人行可查看该债务人的逐项检查明细</p>
          <p>8. 长期应收款常见Stage2升级信号：逾期超30天、债务人经营困难、担保物贬值</p>
        </div>
      </details>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * G5TabStageClassification.vue — G5-9 长期应收款三阶段划分
 *
 * 功能：
 * - 列式转置结构：源模板债务人为列，前端转换为行式交互视图
 * - 三区块检查：(一)信用风险显著增加(13项) / (二)较低信用风险(3项) / (三)已发生信用减值(8项)
 * - 行式汇总视图：债务人|显著增加|较低信用风险|已发生减值|企业阶段|审计阶段|一致性|差异说明|索引
 * - 支持展开/折叠详情模式（展开显示逐项检查明细）
 * - 不一致行红色高亮 + 强制差异说明
 * - 动态债务人增删（ElMessageBox.prompt输入名称）
 *
 * 使用 useG5StageClassification composable
 */
import { ref, computed, inject, toRef, watch, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useG5StageClassification } from '../../composables/useG5StageClassification'
import { useG5LonRecFormData } from '../../composables/useG5LonRecFormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── 审计说明（持久化 checklist_responses，item_id 前缀 G5-）───
const g5Notes = useG5LonRecFormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const G5_NOTE_KEY = 'G5-9-audit-note'
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}
onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
})

// ─── 初始化 composable ───
const isReadonlyRef = computed(() => props.isReadonly)
const htmlDataRef = computed(() => props.htmlData)

const stageLogic = useG5StageClassification({
  htmlData: htmlDataRef,
  isReadonly: isReadonlyRef,
})

// ─── 从htmlData初始化数据 ───
onMounted(() => {
  stageLogic.init(props.htmlData)
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

// ─── 新增债务人（ElMessageBox.prompt输入名称） ───
async function handleAddDebtor(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入债务人名称',
      '新增债务人',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '债务人名称不能为空',
        inputPlaceholder: '例如：XX公司',
      },
    )
    if (value?.trim()) {
      stageLogic.addRow(value.trim())
      ElMessage.success(`已新增债务人"${value.trim()}"`)
    }
  } catch {
    // 用户取消
  }
}

// ─── 删除债务人确认 ───
async function handleRemoveRow(rowId: string, debtorName: string): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认删除债务人"${debtorName}"及其所有检查数据？`,
      '删除确认',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    stageLogic.removeRow(rowId)
    ElMessage.success(`已删除"${debtorName}"`)
  } catch {
    // 用户取消
  }
}

// ─── 打开复核对话 ───
function openReview(): void {
  openReviewDialog('G5-9-stage-classification')
}

// ─── AI辅助生成审计结论 ───
function fillAiConclusion(): void {
  if (props.isReadonly) return
  const s = stageLogic.summary.value
  const draft =
    `经对${s.total}个长期应收款债务人进行信用风险评估和三阶段划分检查，其中` +
    `Stage1（未显著增加）${s.stage1Count}项、` +
    `Stage2（显著增加）${s.stage2Count}项、` +
    `Stage3（已减值）${s.stage3Count}项。` +
    (s.inconsistentCount === 0
      ? '企业划分阶段与审计判断阶段全部一致，三阶段划分合理。'
      : `企业划分阶段与审计判断阶段存在${s.inconsistentCount}项不一致，需关注差异原因。`)
  stageLogic.conclusion.value = stageLogic.conclusion.value
    ? `${stageLogic.conclusion.value}\n${draft}`
    : draft
}

// ─── 暴露序列化接口供父组件保存使用 ───
defineExpose({
  toJSON: () => stageLogic.toSaveData(),
})
</script>

<style scoped>
.g5-tab-stage-classification {
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

.audit-objective {
  margin-bottom: 12px;
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

/* ─── 债务人名称单元格 ─── */
.debtor-name-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.delete-btn {
  opacity: 0;
  transition: opacity 0.2s;
}

.debtor-name-cell:hover .delete-btn {
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

/* 审计说明卡片 */
.audit-note-card {
  margin-top: 12px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
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
.g5-guide-details {
  margin-top: 16px;
}

.g5-guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  font-weight: 600;
}

.g5-guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.g5-guide-content p {
  margin: 0;
}
</style>
