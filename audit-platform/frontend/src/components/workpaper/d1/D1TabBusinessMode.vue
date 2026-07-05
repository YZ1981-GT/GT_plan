<script setup lang="ts">
/**
 * D1TabBusinessMode.vue — 业务模式分析D1-6 HTML渲染
 *
 * Spec: .kiro/specs/d1-endorsement-discount/
 * Task: 8.1
 *
 * 渲染：
 * - 审计目标（只读 el-alert type=info）
 * - (一)业务模式及依据 el-table：组合名称 | 业务模式(el-select) | 具体依据(textarea) | 索引号(GtIndexChip) | 备注
 * - (二)分类判断 QA矩阵：4问题 × 3组合，每格 el-select(是/否)
 * - 判定结果行（业务模式，自动填充，蓝色背景）
 * - 列报项目行（自动填充，蓝色背景）
 * - 审计说明 / 审计结论（textarea + 🤖AI + 💬复核）
 * - 编制提示折叠区（<details> 蓝色左边线+浅蓝背景，5段）
 * - el-segmented 双模式切换头部
 *
 * Requirements: 1.1-1.6, 2.1-2.8, 3.1-3.5, 12.1, 16.1-16.6
 */
import { inject, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1BusinessMode, type BusinessModeRow } from '../composables/useD1BusinessMode'
import type { ChecklistItem, ChecklistResponse } from '../composables/useD1FormData'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtIndexChip from '../GtIndexChip.vue'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

// 复核对话（Task 19 预留）：仅当 provider 存在时展示 💬 按钮
const openReviewDialog = inject<any>('openReviewDialog', null)

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  basisRows,
  qaMatrix,
  businessModeResults,
  reportItemResults,
  auditNote,
  auditConclusion,
  updateBasisRow,
  updateQACell,
  saveAuditNote,
  saveAuditConclusion,
} = useD1BusinessMode({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items: ChecklistItem[]) => {
    try {
      await http.post(`/api/workpapers/${props.wpId}/checklist-responses/batch`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── 业务模式下拉选项（3选1） ─────────────────────────────────────────────────

const BUSINESS_MODE_OPTIONS = [
  '以收取合同现金流量为目标',
  '以收取合同现金流量和出售金融资产为目标',
  '其他',
]

// ─── QA 是/否 下拉选项 ────────────────────────────────────────────────────────

const YN_OPTIONS = [
  { label: '是', value: 'Y' as const },
  { label: '否', value: 'N' as const },
]

// ─── 编制提示 5 段 ────────────────────────────────────────────────────────────

const GUIDANCE_TEXTS = [
  '中国证监会《监管规则适用指引——会计类第1号》：企业应结合票据的信用等级、贴现/背书转让的频率与金额比重，判断应收票据应列报为"应收票据"还是"应收款项融资"，不得简单按票据种类"一刀切"分类。',
  'CAS 22《金融工具确认和计量》与 CAS 23《金融资产转移》：金融资产分类取决于企业管理金融资产的业务模式及金融资产合同现金流量特征；背书/贴现是否满足终止确认条件，应据其风险报酬转移程度判断。',
  'SPPI 现金流量特征测试：应收票据的合同现金流量应仅为对本金和以未偿付本金金额为基础的利息的支付（Solely Payments of Principal and Interest），通过测试方可按摊余成本或以公允价值计量且其变动计入其他综合收益计量。',
  '业务模式与列报分类对应关系：以收取合同现金流量为目标 → 列报"应收票据"（摊余成本）；以收取现金流量和出售为目标 → 列报"应收款项融资"（FVOCI）；其他（以出售为目标）→ 列报"交易性金融资产"（FVTPL）。',
  '评估业务模式应考虑的因素：管理层对该组合的持有意图、历史贴现/背书转让的实际频率与金额占比、票据到期兑付与提前变现的相对比重、以及相关内部报告与考核机制，需综合职业判断而非单一指标。',
]

// ─── Import/Export ───────────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdRef, 'D1-6')

// ─── Helpers ──────────────────────────────────────────────────────────────────

function onReview(sectionId: string) {
  if (openReviewDialog) openReviewDialog({ sectionId })
}

// 表格单元格右键 → 发起复核对话（Task 19.1 scaffolding）
function onCellContextMenu(row: BusinessModeRow, _column: any, _cell: any, event: MouseEvent) {
  event.preventDefault()
  if (openReviewDialog) openReviewDialog({ sectionId: 'D1-bm-cell', rowId: row.rowId })
}

function isEmptyResults(results: string[]): boolean {
  return results.every((r) => !r)
}
</script>

<template>
  <div class="d1-tab-business-mode">
      <div class="tab-header">
        <h4>业务模式分析 D1-6</h4>
        <GtReviewTrigger section-id="D1-business-mode-header" />
      </div>
      <!-- 审计目标 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="审计目标"
        description="了解公司应收票据的业务模式，判断其列报分类是否正确"
        class="audit-objective"
      />

      <!-- Toolbar -->
      <div class="table-toolbar">
        <el-button-group size="small">
          <el-button @click="onExportTemplate">导出模板</el-button>
          <el-button @click="onExportData">导出数据</el-button>
          <el-upload
            :show-file-list="false"
            accept=".xlsx"
            :before-upload="onImportFile"
            style="display:inline-block"
          >
            <el-button size="small">导入数据</el-button>
          </el-upload>
        </el-button-group>
      </div>

      <!-- (一)业务模式及依据 -->
      <div class="section-title">（一）业务模式及依据</div>
      <el-table :data="basisRows" border size="small" class="basis-table" @cell-contextmenu="onCellContextMenu">
        <!-- 组合名称 -->
        <el-table-column label="组合名称" width="180">
          <template #default="{ row }: { row: BusinessModeRow }">
            <div class="combo-name-cell">
              <span v-if="row.isFixed" class="lock-icon" title="固定行，不可删除">🔒</span>
              <span class="combo-name-text">{{ row.combinationName }}</span>
              <GtReviewDot row-prefix="D1-business-mode" :row-key="row.rowId" />
            </div>
          </template>
        </el-table-column>

        <!-- 业务模式 -->
        <el-table-column label="业务模式" min-width="240">
          <template #default="{ row }: { row: BusinessModeRow }">
            <el-select
              :model-value="row.businessMode"
              placeholder="请选择业务模式"
              clearable
              size="small"
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: string) => updateBasisRow(row.rowId, 'businessMode', v || '')"
            >
              <el-option
                v-for="opt in BUSINESS_MODE_OPTIONS"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </template>
        </el-table-column>

        <!-- 具体依据 -->
        <el-table-column label="具体依据" min-width="220">
          <template #default="{ row }: { row: BusinessModeRow }">
            <el-input
              type="textarea"
              :rows="2"
              :model-value="row.basis"
              placeholder="请输入具体依据..."
              :disabled="isReadonly"
              @change="(v: string) => updateBasisRow(row.rowId, 'basis', v || '')"
            />
          </template>
        </el-table-column>

        <!-- 索引号 -->
        <el-table-column label="索引号" width="160">
          <template #default="{ row }: { row: BusinessModeRow }">
            <!-- GtIndexChip 用于展示/跳转已填写的索引号；为空或可编辑时用 el-input 填写。
                 GtIndexChip 本身为只读跳转 chip，编辑走 el-input，填写后 chip 展示跳转能力。 -->
            <div class="index-cell">
              <el-input
                :model-value="row.indexRef"
                placeholder="如 D1-8"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateBasisRow(row.rowId, 'indexRef', v || '')"
              />
              <GtIndexChip
                v-if="row.indexRef"
                :value="row.indexRef"
                :context-project-id="projectId"
              />
            </div>
          </template>
        </el-table-column>

        <!-- 备注 -->
        <el-table-column label="备注" min-width="180">
          <template #default="{ row }: { row: BusinessModeRow }">
            <el-input
              type="textarea"
              :rows="2"
              :model-value="row.remark"
              placeholder="备注..."
              :disabled="isReadonly"
              @change="(v: string) => updateBasisRow(row.rowId, 'remark', v || '')"
            />
          </template>
        </el-table-column>
      </el-table>

      <!-- (二)分类判断 QA 矩阵 -->
      <div class="section-title">（二）分类判断</div>
      <table class="qa-matrix">
        <thead>
          <tr>
            <th class="qa-question-col">问题</th>
            <th v-for="col in qaMatrix.columns" :key="col">{{ col }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(q, qIdx) in qaMatrix.questions" :key="qIdx">
            <td class="qa-question-col">{{ q }}</td>
            <td v-for="(col, cIdx) in qaMatrix.columns" :key="cIdx" class="qa-cell">
              <el-select
                :model-value="qaMatrix.cells[qIdx][cIdx].answer"
                placeholder="—"
                clearable
                size="small"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: 'Y' | 'N' | '') => updateQACell(qIdx, cIdx, v || '')"
              >
                <el-option
                  v-for="opt in YN_OPTIONS"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </td>
          </tr>

          <!-- 判定结果行：业务模式 -->
          <tr class="result-row">
            <td class="qa-question-col result-label">业务模式（自动判定）</td>
            <td
              v-for="(res, i) in businessModeResults"
              :key="'bm-' + i"
              class="result-cell"
            >
              <span v-if="res">{{ res }}</span>
              <span v-else class="result-hint">请完成所有问题的回答</span>
            </td>
          </tr>

          <!-- 列报项目行 -->
          <tr class="result-row">
            <td class="qa-question-col result-label">列报项目（自动判定）</td>
            <td
              v-for="(res, i) in reportItemResults"
              :key="'ri-' + i"
              class="result-cell"
            >
              <span v-if="res">{{ res }}</span>
              <span v-else class="result-hint">请完成所有问题的回答</span>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="isEmptyResults(businessModeResults)" class="matrix-empty-hint">
        请完成所有问题的回答后，系统将自动判定业务模式与列报项目。
      </div>

      <!-- 审计说明 -->
      <div class="section-title">审计说明</div>
      <div class="note-section">
        <el-input
          type="textarea"
          :rows="4"
          :model-value="auditNote"
          placeholder="请输入审计说明..."
          :disabled="isReadonly"
          @change="(v: string) => saveAuditNote(v || '')"
        />
        <div class="note-actions">
          <el-tooltip content="AI生成（开发中）" placement="top">
            <el-button size="small" disabled>🤖 AI</el-button>
          </el-tooltip>
          <el-button
            v-if="openReviewDialog"
            size="small"
            @click="onReview('D1-bm-note')"
          >
            💬 复核
          </el-button>
        </div>
      </div>

      <!-- 审计结论 -->
      <div class="section-title">审计结论</div>
      <div class="note-section">
        <el-input
          type="textarea"
          :rows="4"
          :model-value="auditConclusion"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
          @change="(v: string) => saveAuditConclusion(v || '')"
        />
        <div class="note-actions">
          <el-tooltip content="AI生成（开发中）" placement="top">
            <el-button size="small" disabled>🤖 AI</el-button>
          </el-tooltip>
          <el-button
            v-if="openReviewDialog"
            size="small"
            @click="onReview('D1-bm-conclusion')"
          >
            💬 复核
          </el-button>
        </div>
      </div>

      <!-- 编制提示 -->
      <details class="guidance-fold">
        <summary>📋 编制提示</summary>
        <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
      </details>
  </div>
</template>

<style scoped>
.d1-tab-business-mode {
  padding: 12px;
}

.tab-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.tab-header h4 {
  margin: 0;
  font-size: 15px;
}

.mode-switcher {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.oo-disabled-hint {
  cursor: help;
  font-size: 14px;
}

.audit-objective {
  margin-bottom: 16px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 16px 0 10px;
}

/* 组合名称单元格 */
.combo-name-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.lock-icon {
  font-size: 12px;
  flex-shrink: 0;
}

.combo-name-text {
  font-weight: 600;
}

/* 索引号单元格 */
.index-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.index-cell .el-input {
  flex: 1;
}

/* QA 矩阵表格 */
.qa-matrix {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.qa-matrix th,
.qa-matrix td {
  border: 1px solid #ebeef5;
  padding: 8px 10px;
  text-align: center;
  vertical-align: middle;
}

.qa-matrix th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
}

.qa-question-col {
  text-align: left !important;
  min-width: 280px;
}

.qa-cell {
  width: 160px;
}

/* 自动判定结果行：蓝色背景 */
.result-row .result-cell {
  background: #ecf5ff;
  font-weight: 600;
  color: #303133;
}

.result-row .result-label {
  background: #ecf5ff;
  font-weight: 600;
}

.result-hint {
  color: #909399;
  font-weight: 400;
  font-size: 12px;
}

.matrix-empty-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

/* 审计说明/结论 */
.note-section {
  margin-bottom: 8px;
}

.note-actions {
  margin-top: 6px;
  display: flex;
  gap: 8px;
}

/* 编制提示折叠区 */
.guidance-fold {
  margin: 16px 0;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  padding: 10px 14px;
  border-radius: 0 4px 4px 0;
  font-size: 13px;
  color: #606266;
}

.guidance-fold summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}

.guidance-fold p {
  margin: 6px 0;
  line-height: 1.6;
}
</style>
