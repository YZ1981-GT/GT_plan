<script setup lang="ts">
/**
 * E1TabCashDetail.vue — E1-2 现金明细表
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.2
 *
 * 渲染：
 * - el-table 动态行：币种 | 期初余额 | 本期增加 | 本期减少 | 期末原币 | 汇率 |
 *   折算人民币 | 审计调整 | 审定人民币 | 备注
 * - 底部合计行(sticky bold)
 * - 动态行增删按钮
 * - 只读列灰色背景
 * - el-skeleton加载占位
 *
 * Requirements: 3.1-3.6
 */
import { ref, inject, toRef, onMounted, type Ref } from 'vue'
import {
  useE1CashDetail,
  type CashDetailRow,
} from '../composables/useE1CashDetail'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
}

const {
  rows,
  totalRow,
  isLoading,
  addRow,
  removeRow,
  updateCell,
} = useE1CashDetail(options)

// ─── 审计说明 / 审计结论 / 存放境外款项 ───────────────────────────────────────

const NOTE_KEY = 'E1-cash-audit-note'
const CONCLUSION_KEY = 'E1-cash-audit-conclusion'
const OVERSEAS_KEY = 'E1-cash-overseas-amount'
const auditNote = ref('')
const auditConclusion = ref('')
const overseasAmount = ref<number>(0)

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY, item)
  void props.saveImmediate([item])
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  void props.saveImmediate([item])
}

function saveOverseasAmount(val: number | undefined): void {
  if (props.isReadonly) return
  const amount = val ?? 0
  overseasAmount.value = amount
  const item = { item_id: OVERSEAS_KEY, conclusion: null, remark: String(amount) }
  props.allResponses.set(OVERSEAS_KEY, item)
  void props.saveImmediate([item])
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  // hydration done inside composable
  const noteResp = props.allResponses.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  const concResp = props.allResponses.get(CONCLUSION_KEY)
  if (concResp?.remark) auditConclusion.value = concResp.remark
  const overseasResp = props.allResponses.get(OVERSEAS_KEY)
  if (overseasResp?.remark) {
    const parsed = Number(overseasResp.remark)
    overseasAmount.value = Number.isFinite(parsed) ? parsed : 0
  }
})
</script>

<template>
  <div class="e1-tab-cash-detail">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本科目核算企业的库存现金。企业有内部周转使用备用金的，可以单独设置"备用金"科目。</p>
        <p>2. 若公司仅有一种币种的现金，可不填列本表（用盘点表代替）。</p>
        <p>3. 期初余额应与上年末审定数一致。</p>
        <p>4. 审计说明可以概述：（1）程序的测试情况、结果；（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。</p>
        <p>5. 审计结论可参考：A、未见异常。 B、除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。 C、由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。</p>
        <p class="calc-hint">计算说明：灰色底纹列（期末原币/折算人民币/审定人民币）为自动计算——期末原币=期初+增加-减少，折算人民币=期末原币×汇率；外币汇率采用资产负债表日中间价，人民币行汇率固定为1。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实库存现金期末余额的存在与准确，验证外币折算的恰当性，为 E1-1 审定表提供现金审定依据。"
      class="objective-alert"
    />

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <!-- 工具栏 -->
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <el-button v-if="!isReadonly" type="primary" size="small" @click="addRow">
              + 新增行
            </el-button>
          </div>
          <div class="toolbar-right">
            <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
            <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
          </div>
        </div>

        <el-table
          :data="rows"
          border
          stripe
          size="small"
          style="width: 100%"
          max-height="600"
        >
          <!-- 币种 -->
          <el-table-column label="币种" width="120">
            <template #default="{ row }">
              <el-input
                :model-value="row.currency"
                :disabled="isReadonly || row.id === 'fixed-rmb'"
                size="small"
                @change="(val: string) => updateCell(row.id, 'currency', val)"
              />
            </template>
          </el-table-column>

          <!-- 期初余额 -->
          <el-table-column label="期初余额" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.opening"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number | undefined) => updateCell(row.id, 'opening', val ?? 0)"
              />
            </template>
          </el-table-column>

          <!-- 本期增加 -->
          <el-table-column label="本期增加" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.increase"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number | undefined) => updateCell(row.id, 'increase', val ?? 0)"
              />
            </template>
          </el-table-column>

          <!-- 本期减少 -->
          <el-table-column label="本期减少" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.decrease"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number | undefined) => updateCell(row.id, 'decrease', val ?? 0)"
              />
            </template>
          </el-table-column>

          <!-- 期末原币 (readonly) -->
          <el-table-column label="期末原币" width="130" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="readonly-val">{{ displayPrefs.fmtAmount(row.endingFc) }}</span>
            </template>
          </el-table-column>

          <!-- 汇率 -->
          <el-table-column label="汇率" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.fxRate"
                :disabled="isReadonly || row.id === 'fixed-rmb'"
                :controls="false"
                :precision="4"
                size="small"
                @change="(val: number | undefined) => updateCell(row.id, 'fxRate', val ?? 0)"
              />
            </template>
          </el-table-column>

          <!-- 折算人民币 (readonly) -->
          <el-table-column label="折算人民币" width="140" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="readonly-val">{{ displayPrefs.fmtAmount(row.endingRmb) }}</span>
            </template>
          </el-table-column>

          <!-- 审计调整 -->
          <el-table-column label="审计调整" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.adjustment"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number | undefined) => updateCell(row.id, 'adjustment', val ?? 0)"
              />
            </template>
          </el-table-column>

          <!-- 审定人民币 (readonly) -->
          <el-table-column label="审定人民币" width="140" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="readonly-val">{{ displayPrefs.fmtAmount(row.auditedRmb) }}</span>
            </template>
          </el-table-column>

          <!-- 备注 -->
          <el-table-column label="备注" min-width="150">
            <template #default="{ row }">
              <el-input
                :model-value="row.note"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'note', val)"
              />
            </template>
          </el-table-column>

          <!-- 操作 -->
          <el-table-column v-if="!isReadonly" label="操作" width="70" fixed="right" align="center">
            <template #default="{ row }">
              <el-button
                v-if="row.id !== 'fixed-rmb'"
                type="danger"
                text
                size="small"
                @click="removeRow(row.id)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 合计行 -->
        <div class="total-row">
          <span class="total-label">合计</span>
          <span class="total-val">期初: {{ displayPrefs.fmtAmount(totalRow.opening) }}</span>
          <span class="total-val">增加: {{ displayPrefs.fmtAmount(totalRow.increase) }}</span>
          <span class="total-val">减少: {{ displayPrefs.fmtAmount(totalRow.decrease) }}</span>
          <span class="total-val">期末原币: {{ displayPrefs.fmtAmount(totalRow.endingFc) }}</span>
          <span class="total-val">折算人民币: {{ displayPrefs.fmtAmount(totalRow.endingRmb) }}</span>
          <span class="total-val">审定人民币: {{ displayPrefs.fmtAmount(totalRow.auditedRmb) }}</span>
        </div>

        <!-- 其中：存放在境外的款项总额 -->
        <div class="overseas-row">
          <span class="overseas-label">其中：存放在境外的款项总额（人民币）</span>
          <el-input-number
            :model-value="overseasAmount"
            :disabled="isReadonly"
            :controls="false"
            size="small"
            @change="saveOverseasAmount"
          />
        </div>

        <!-- 审计说明 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header"><span>审计说明</span></div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditNote"
            :disabled="isReadonly"
            :autosize="{ minRows: 5 }"
            placeholder="填写审计说明：可概述（1）程序的测试情况、结果；（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。"
            @change="(val: string) => saveAuditNote(val)"
          />
        </el-card>

        <!-- 审计结论 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header"><span>审计结论</span></div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditConclusion"
            :disabled="isReadonly"
            :autosize="{ minRows: 3 }"
            placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。"
            @change="(val: string) => saveAuditConclusion(val)"
          />
        </el-card>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-cash-detail {
  padding: 12px 0;
}
.e1-tab-cash-detail :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-cash-detail :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
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
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.readonly-val {
  color: #909399;
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 2px;
  display: inline-block;
  width: 100%;
  text-align: right;
}
.total-row {
  display: flex;
  gap: 16px;
  padding: 10px 12px;
  margin-top: 8px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  font-weight: 700;
  font-size: var(--wp-font-size, 13px);
  flex-wrap: wrap;
}
.total-label {
  color: #303133;
  min-width: 40px;
}
.total-val {
  color: #606266;
}
.calc-hint {
  margin-top: 6px;
  color: #909399;
  font-style: italic;
}
.overseas-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  margin-top: 8px;
  background: #fdf6ec;
  border: 1px solid #faecd8;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}
.overseas-label {
  color: #303133;
  font-weight: 500;
}
.audit-note-card {
  margin-top: 16px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
</style>
