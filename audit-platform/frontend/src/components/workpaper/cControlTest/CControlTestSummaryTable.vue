<!--
  CControlTestSummaryTable.vue — C2~C15 控制测试汇总表（15 列）

  职责：
  - el-table 展示 15 列控制点清单
  - 命名下拉选项（认定/控制属性/控制频率/测试方法/是否识别偏差）
  - 动态增删控制点行（ElMessageBox.prompt 命名）
  - 样本规模建议 tooltip（useSampleSizeEngine）
  - 索引号列 GtIndexChip → ctrl-{m} 子页导航

  Spec: .kiro/specs/c-control-test-refresh/
  Task: 4.2
  Requirements: 2.1, 2.2, 2.3, 2.4, 3.3, 3.4
-->
<template>
  <div class="cct-summary-table">
    <!-- 视图头部：返回 + 标题 + 操作按钮 -->
    <div class="cct-view-header">
      <el-button text @click="$emit('navigate', 'directory')">
        <el-icon><ArrowLeft /></el-icon>
        返回目录
      </el-button>
      <span class="cct-view-title">{{ wpCode }} 控制测试汇总表</span>
      <div class="cct-view-actions" v-if="!readonly">
        <el-button type="primary" size="small" @click="handleAddControlPoint">
          <el-icon><Plus /></el-icon>
          新增控制点
        </el-button>
      </div>
    </div>

    <!-- 方法论上下文：样本规模区间（琥珀色左边线 + 浅黄背景） -->
    <div class="cct-methodology-context">
      <div class="cct-methodology-title">📐 样本规模区间参考（致同 2025 修订版）</div>
      <div class="cct-methodology-table">
        <span class="mth-item">每年1次→1</span>
        <span class="mth-item">每季1次→2</span>
        <span class="mth-item">每月1次→2~5</span>
        <span class="mth-item">每周1次→5~15</span>
        <span class="mth-item">每半月→10%~20%(最多40)</span>
        <span class="mth-item">每天1次→20~40</span>
        <span class="mth-item">每天多次→25~60</span>
      </div>
      <div class="cct-methodology-source">来源：致同控制测试样本量指引表（CAS1314/ISA530）</div>
    </div>

    <!-- 15 列汇总表 -->
    <el-table
      :data="rows"
      border
      stripe
      class="cct-table"
      :row-class-name="tableRowClassName"
      size="small"
    >
      <!-- 序号 -->
      <el-table-column type="index" label="#" width="40" align="center" fixed />

      <!-- 1. 子流程 -->
      <el-table-column label="子流程" prop="subProcess" min-width="100">
        <template #default="{ row, $index }">
          <el-input
            v-model="row.subProcess"
            :disabled="readonly"
            size="small"
            @input="(v: string) => onTextChange($index, 'subProcess', v)"
          />
        </template>
      </el-table-column>

      <!-- 2. 控制编号 -->
      <el-table-column label="控制编号" prop="controlId" min-width="100">
        <template #default="{ row, $index }">
          <el-input
            v-model="row.controlId"
            :disabled="readonly"
            size="small"
            @input="(v: string) => onTextChange($index, 'controlId', v)"
          />
        </template>
      </el-table-column>

      <!-- 3. 控制名称 -->
      <el-table-column label="控制名称" prop="controlName" min-width="120">
        <template #default="{ row, $index }">
          <el-input
            v-model="row.controlName"
            :disabled="readonly"
            size="small"
            @input="(v: string) => onTextChange($index, 'controlName', v)"
          />
        </template>
      </el-table-column>

      <!-- 4. 详细控制描述 -->
      <el-table-column label="详细控制描述" prop="description" min-width="200">
        <template #default="{ row, $index }">
          <el-input
            v-model="row.description"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :disabled="readonly"
            @input="(v: string) => onTextChange($index, 'description', v)"
          />
        </template>
      </el-table-column>

      <!-- 5. 受影响的交易、账户余额和披露 -->
      <el-table-column label="受影响交易/账户/披露" prop="affectedItems" min-width="150">
        <template #default="{ row, $index }">
          <el-input
            v-model="row.affectedItems"
            :disabled="readonly"
            size="small"
            @input="(v: string) => onTextChange($index, 'affectedItems', v)"
          />
        </template>
      </el-table-column>

      <!-- 6. 认定（多选） -->
      <el-table-column label="认定" prop="assertion" min-width="180">
        <template #default="{ row, $index }">
          <el-select
            :model-value="parseMulti(row.assertion)"
            multiple
            collapse-tags
            collapse-tags-tooltip
            :disabled="readonly"
            size="small"
            placeholder="选择认定"
            @change="(v: string[]) => onEnumChange($index, 'assertion', joinMulti(v))"
          >
            <el-option
              v-for="opt in ASSERTION_OPTIONS"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>
        </template>
      </el-table-column>

      <!-- 7. 控制属性 -->
      <el-table-column label="控制属性" prop="attribute" min-width="150">
        <template #default="{ row, $index }">
          <el-select
            v-model="row.attribute"
            :disabled="readonly"
            size="small"
            placeholder="选择属性"
            @change="(v: string) => onEnumChange($index, 'attribute', v)"
          >
            <el-option
              v-for="opt in ATTRIBUTE_OPTIONS"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>
        </template>
      </el-table-column>

      <!-- 8. 控制频率 -->
      <el-table-column label="控制频率" prop="frequency" min-width="130">
        <template #default="{ row, $index }">
          <el-select
            v-model="row.frequency"
            :disabled="readonly"
            size="small"
            placeholder="选择频率"
            @change="(v: string) => onEnumChange($index, 'frequency', v)"
          >
            <el-option
              v-for="opt in FREQUENCY_OPTIONS"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>
        </template>
      </el-table-column>

      <!-- 9. 与控制相关的风险 -->
      <el-table-column label="相关风险" prop="relatedRisk" min-width="90">
        <template #default="{ row, $index }">
          <el-select
            v-model="row.relatedRisk"
            :disabled="readonly"
            size="small"
            placeholder="风险"
            @change="(v: string) => onTextChange($index, 'relatedRisk', v)"
          >
            <el-option
              v-for="opt in RISK_OPTIONS"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>
        </template>
      </el-table-column>

      <!-- 10. 测试方法（多选） -->
      <el-table-column label="测试方法" prop="testMethod" min-width="200">
        <template #default="{ row, $index }">
          <el-select
            :model-value="parseMulti(row.testMethod)"
            multiple
            collapse-tags
            collapse-tags-tooltip
            :disabled="readonly"
            size="small"
            placeholder="选择方法"
            @change="(v: string[]) => onEnumChange($index, 'testMethod', joinMulti(v))"
          >
            <el-option
              v-for="opt in TEST_METHOD_OPTIONS"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>
        </template>
      </el-table-column>

      <!-- 11. 范围（样本量） + tooltip 建议 -->
      <el-table-column label="范围(样本量)" prop="sampleSize" min-width="140">
        <template #header>
          <el-tooltip
            content="基于致同2025样本规模区间表，按频率×次数建议最小样本量"
            placement="top"
            effect="light"
            :show-after="300"
          >
            <span class="cct-col-formula">范围(样本量) <el-icon class="cct-formula-icon"><InfoFilled /></el-icon></span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <el-tooltip
            :content="getSampleSizeTooltip(row)"
            placement="top"
            :disabled="!getSampleSizeTooltip(row)"
          >
            <el-input-number
              v-model="row.sampleSize"
              :disabled="readonly"
              :min="0"
              :controls="false"
              size="small"
              class="cct-sample-size-input"
              @change="(v: number | null) => onSampleSizeChange($index, v ?? null)"
            />
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 12. 是否识别出偏差 -->
      <el-table-column label="是否偏差" prop="hasDeviation" min-width="100">
        <template #default="{ row, $index }">
          <el-select
            v-model="row.hasDeviation"
            :disabled="readonly"
            size="small"
            placeholder="—"
            clearable
            @change="(v: string) => onEnumChange($index, 'hasDeviation', v)"
          >
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 13. 整改期间 -->
      <el-table-column label="整改期间" prop="remediation" min-width="100">
        <template #default="{ row, $index }">
          <el-input
            v-model="row.remediation"
            :disabled="readonly"
            size="small"
            @input="(v: string) => onTextChange($index, 'remediation', v)"
          />
        </template>
      </el-table-column>

      <!-- 14. 识别出的缺陷 -->
      <el-table-column label="识别出的缺陷" prop="defect" min-width="150">
        <template #default="{ row, $index }">
          <div class="cct-defect-cell">
            <el-input
              v-model="row.defect"
              :disabled="readonly"
              size="small"
              @input="(v: string) => onTextChange($index, 'defect', v)"
            />
            <GtIndexChip v-if="row.defect" :value="'A14'" :context="row.defect" class="cct-defect-chip" />
          </div>
        </template>
      </el-table-column>

      <!-- 15. 索引号 -->
      <el-table-column label="索引号" min-width="100" fixed="right">
        <template #default="{ $index }">
          <GtIndexChip
            :value="`${wpCode}-1-${$index + 1}`"
            @click.stop="$emit('navigate', `ctrl-${$index + 1}`)"
          />
        </template>
      </el-table-column>

      <!-- 操作列：删除 -->
      <el-table-column v-if="!readonly" label="操作" width="60" fixed="right" align="center">
        <template #default="{ $index }">
          <el-button
            type="danger"
            link
            size="small"
            @click="handleRemoveControlPoint($index)"
          >
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编制提示（底部折叠） -->
    <details class="cct-compilation-tips">
      <summary>编制提示 — 控制测试汇总表</summary>
      <div class="cct-tips-content">
        <p>• 按循环列示全部被测控制点，确保覆盖与认定层次重大错报风险相关的关键控制。</p>
        <p>• 「认定」「控制属性」「控制频率」「测试方法」从命名区域下拉选择，减少手工输入。</p>
        <p>• 「范围(样本量)」参照上方样本规模区间表确定；可根据职业判断适当增减。</p>
        <p>• 点击索引号列可快速跳转到对应控制测试子页(Cx-1-X)。</p>
        <p>• 「是否识别出偏差」由子页样本结果自动回填，也可手动覆盖。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { ArrowLeft, Plus, Delete, InfoFilled } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { suggestSampleSize } from '@/composables/useSampleSizeEngine'
import type { SummaryRow } from '@/composables/useCControlTestData'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpCode: string
  rows: SummaryRow[]
  readonly: boolean
  /** 更新汇总表文本字段 */
  updateSummaryText: (index: number, field: string, value: string) => void
  /** 更新汇总表枚举字段 */
  updateSummaryEnum: (index: number, field: string, value: string) => void
  /** 更新样本规模 */
  updateSummarySampleSize: (index: number, value: number | null) => void
  /** 添加控制点 */
  addControlPoint: (name: string) => void
  /** 删除控制点 */
  removeControlPoint: (index: number) => void
}>()

const emit = defineEmits<{
  (e: 'navigate', view: string): void
}>()

// ─── 命名区域下拉常量（源模板选项清单列表） ──────────────────────────────────

/** 认定选项（多选） */
const ASSERTION_OPTIONS = [
  '存在/发生',
  '完整性',
  '准确性/计价和分摊',
  '权利和义务',
  '截止',
  '分类',
  '列报',
]

/** 控制属性选项 */
const ATTRIBUTE_OPTIONS = [
  '人工的',
  '自动化的',
  '人工依赖信息系统控制',
]

/** 控制频率选项 */
const FREQUENCY_OPTIONS = [
  '每笔交易',
  '每天',
  '每周',
  '每半月',
  '每月',
  '每季度',
  '每年',
  '非常规/低运行频率',
  '其他',
]

/** 风险选项 */
const RISK_OPTIONS = ['高', '中', '低']

/** 测试方法选项（多选） */
const TEST_METHOD_OPTIONS = [
  '询问',
  '检查',
  '观察',
  '重新执行',
  '前期',
  '前推',
  '利用内部审计工作',
  '利用服务机构的审计报告',
]

// ─── 多选分隔处理（逗号分隔存储） ─────────────────────────────────────────────

function parseMulti(value: string): string[] {
  if (!value) return []
  return value.split(',').map(s => s.trim()).filter(Boolean)
}

function joinMulti(arr: string[]): string {
  return arr.join(',')
}

// ─── 样本规模建议 tooltip ─────────────────────────────────────────────────────

function getSampleSizeTooltip(row: SummaryRow): string {
  if (!row.frequency) return ''
  // 频率映射：el-select 的值需要映射到 useSampleSizeEngine 支持的频率关键字
  const freqMap: Record<string, string> = {
    '每笔交易': '每天多次',
    '每天': '每天',
    '每周': '每周',
    '每半月': '每半月',
    '每月': '每月',
    '每季度': '每季度',
    '每年': '每年',
    '非常规/低运行频率': '每年',
    '其他': '',
  }
  const mappedFreq = freqMap[row.frequency] || ''
  if (!mappedFreq) return ''

  // 根据频率推导默认总次数
  const defaultCounts: Record<string, number> = {
    '每天多次': 500,
    '每天': 250,
    '每周': 52,
    '每半月': 24,
    '每月': 12,
    '每季度': 4,
    '每年': 1,
  }
  const totalCount = defaultCounts[mappedFreq] || 0
  if (totalCount <= 0) return ''

  const result = suggestSampleSize(mappedFreq, totalCount)
  if (result.min === 0 && result.max === 0) return result.note || ''

  let tip = `建议样本量：${result.min}`
  if (result.max !== result.min) tip += `~${result.max}`
  tip += '（基于致同2025样本规模区间表，按频率×次数建议）'
  return tip
}

// ─── 字段变更处理 ─────────────────────────────────────────────────────────────

function onTextChange(index: number, field: string, value: string) {
  props.updateSummaryText(index, field, value)
}

function onEnumChange(index: number, field: string, value: string) {
  props.updateSummaryEnum(index, field, value)
}

function onSampleSizeChange(index: number, value: number | null) {
  props.updateSummarySampleSize(index, value)
}

// ─── 动态增删 ────────────────────────────────────────────────────────────────

async function handleAddControlPoint() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入控制点名称',
      '新增控制点',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '控制点名称不能为空',
      },
    )
    if (value?.trim()) {
      props.addControlPoint(value.trim())
    }
  } catch {
    // 用户取消
  }
}

function handleRemoveControlPoint(index: number) {
  ElMessageBox.confirm(
    `确认删除第 ${index + 1} 行控制点？此操作不可恢复。`,
    '删除确认',
    { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
  ).then(() => {
    props.removeControlPoint(index)
    ElMessage.success('已删除')
  }).catch(() => {})
}

// ─── 表格样式 ────────────────────────────────────────────────────────────────

function tableRowClassName({ rowIndex }: { row: SummaryRow; rowIndex: number }): string {
  return rowIndex % 2 === 0 ? '' : 'stripe-row'
}
</script>

<style scoped>
.cct-summary-table {
  font-size: 13px;
}

.cct-view-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.cct-view-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  flex: 1;
}

.cct-view-actions {
  display: flex;
  gap: 8px;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景 — 设计铁律） ─── */
.cct-methodology-context {
  border-left: 3px solid #f59e0b;
  background: #fffbeb;
  padding: 12px 16px;
  margin: 8px 0 16px;
  font-size: 13px;
  border-radius: 0 6px 6px 0;
}

.cct-methodology-bar {
  display: none; /* 改用 border-left 实现 */
}

.cct-methodology-content {
  flex: 1;
}

.cct-methodology-title {
  font-weight: 500;
  color: #92400e;
  margin-bottom: 8px;
  font-size: 13px;
}

.cct-methodology-table {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
}

.mth-item {
  font-size: 12px;
  color: #78350f;
  background: #fef3c7;
  padding: 2px 8px;
  border-radius: 3px;
}

/* ─── 表格 13px 铁律 ─── */
.cct-table {
  font-size: 13px;
}

.cct-table :deep(.el-table__header th) {
  font-size: 12px;
  font-weight: 600;
  background: #f9fafb;
}

.cct-table :deep(.el-table__body td) {
  font-size: 13px;
}

.cct-table :deep(.el-input__inner),
.cct-table :deep(.el-textarea__inner) {
  font-size: 13px;
}

.cct-table :deep(.el-select) {
  width: 100%;
}

.cct-methodology-source {
  margin-top: 8px;
  font-size: 11px;
  color: #a16207;
  font-style: italic;
}

.cct-sample-size-input {
  width: 100%;
}

.cct-sample-size-input :deep(.el-input__inner) {
  text-align: left;
}

/* ─── 公式列 tooltip 样式（虚线下划线+cursor:help） ─── */
.cct-col-formula {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-bottom: 1px dashed #9ca3af;
  cursor: help;
  font-size: 12px;
  font-weight: 600;
}

.cct-formula-icon {
  font-size: 12px;
  color: #9ca3af;
}

/* ─── 缺陷列 ─── */
.cct-defect-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.cct-defect-chip {
  flex-shrink: 0;
}

/* ─── 编制提示 details 折叠 ─── */
.cct-compilation-tips {
  margin-top: 16px;
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
</style>
