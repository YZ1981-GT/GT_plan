<template>
  <div class="f5-other-cost">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表列示其他业务成本各项目本期/上期未审、账项调整、重分类及审定；审定=未审+账项+重分类。</p>
        <p>2. 结构比=该行审定÷合计审定；变动额=本期审定−上期审定；变动率绝对值≥30% 标黄。</p>
        <p>3. 预置 7 项常见其他业务成本科目，可增删扩展行；固定行清空金额时保留项目名称。</p>
        <p>4. 税金及附加（除增值税外）应记入「税金及附加」，不在本表列示。合计应与 F5-1 其他业务成本核对。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实其他业务成本的存在、完整与准确，验证结转口径恰当，识别异常波动项目。"
      class="objective-alert"
    />

    <el-alert
      v-if="other.significantChanges.value.length"
      type="warning"
      :closable="false"
      class="change-alert"
      :title="`审定变动率绝对值≥${threshold}% 的项目：${other.significantChanges.value.map((r) => r.item || '（未命名）').join('、')}`"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="promptAddRow">+ 项目</el-button>
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown
          v-if="ieCtx"
          :wp-id="wpId"
          :api-prefix="ieCtx.apiPrefix"
          :sheet="ieCtx.sheet"
          :disabled="isReadonly"
          @imported="$emit('imported')"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F5-1" :context-project-id="projectIdStr" /></span>
        <el-tag size="small" type="info">共 {{ other.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <F5SheetAttachments
      v-if="projectId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F5-3"
      label="其他业务成本附件"
    />

    <el-table
      :data="tableData"
      size="small"
      border
      stripe
      :row-class-name="rowClass"
      max-height="520"
    >
      <el-table-column label="项目" min-width="200" fixed>
        <template #default="{ row }">
          <template v-if="row.__type === 'data'">
            <el-input
              v-if="!isReadonly && !row.isFixed"
              :model-value="row.item"
              size="small"
              @change="(v: string) => other.updateCell(row.id, 'item', v)"
            />
            <span v-else>{{ row.item }}</span>
          </template>
          <strong v-else>合计</strong>
        </template>
      </el-table-column>

      <el-table-column label="本期数" align="center">
        <el-table-column label="本期未审数" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.currentUnaudited"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => other.updateCell(row.id, 'currentUnaudited', v ?? 0)"
            />
            <span v-else>{{ fmt(row.currentUnaudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.currentAje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => other.updateCell(row.id, 'currentAje', v ?? 0)"
            />
            <span v-else>{{ fmt(row.currentAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.currentRje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => other.updateCell(row.id, 'currentRje', v ?? 0)"
            />
            <span v-else>{{ fmt(row.currentRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="f5-formula" title="未审 + 账项 + 重分类">{{ fmt(row.currentAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结构比" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="f5-formula" title="本期审定 / 合计本期审定">{{ pct(row.currentStructureRatio) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="上期数" align="center">
        <el-table-column label="上期未审数" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.priorUnaudited"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => other.updateCell(row.id, 'priorUnaudited', v ?? 0)"
            />
            <span v-else>{{ fmt(row.priorUnaudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.priorAje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => other.updateCell(row.id, 'priorAje', v ?? 0)"
            />
            <span v-else>{{ fmt(row.priorAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.priorRje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => other.updateCell(row.id, 'priorRje', v ?? 0)"
            />
            <span v-else>{{ fmt(row.priorRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="f5-formula" title="上期未审 + 账项 + 重分类">{{ fmt(row.priorAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结构比" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="f5-formula" title="上期审定 / 合计上期审定">{{ pct(row.priorStructureRatio) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期数比上期数增加(减少)" align="center">
        <el-table-column label="变动额" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="f5-formula" title="本期审定 − 上期审定">{{ fmt(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span
              class="f5-formula"
              :class="{ 'is-warn': isRateWarn(row.changeRate) }"
              title="变动额 / 上期审定（上期审定=0且有增加→100%）"
            >{{ pct(row.changeRate) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="row.__type === 'data' && !isReadonly"
            :model-value="row.remark"
            size="small"
            @change="(v: string) => other.updateCell(row.id, 'remark', v)"
          />
          <span v-else-if="row.__type === 'data'">{{ row.remark }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="72" fixed="right">
        <template #default="{ row }">
          <el-popconfirm
            v-if="row.__type === 'data'"
            :title="row.isFixed ? '清空该固定行金额？' : '确认删除？'"
            @confirm="other.removeRow(row.id)"
          >
            <template #reference>
              <el-button size="small" type="danger" link>
                {{ row.isFixed ? '清空' : '删除' }}
              </el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">三、审计说明</span>
          <div class="opinion-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="generateAiNote"
            >🤖 AI生成说明</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReview">复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="other.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="说明其他业务成本构成、与对应折旧/存货等底稿勾稽、重大变动原因等…"
        @change="other.saveAuditNote"
      />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">四、审计结论</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="generateAiConclusion"
          >🤖 AI生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="other.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合评价其他业务成本列报是否公允（A/B/C口径）…"
        @change="other.saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * F5TabOtherCost — F5-3 其他业务成本明细表
 * 源表：本期/上期未审·调整·审定·结构比 + 变动额/率 + 固定项目 + AI说明结论
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  useF5OtherCost,
  F5_OTHER_COST_CHANGE_RATE_THRESHOLD,
} from '../composables/useF5OtherCost'
import { useF5AiGenerate } from '../composables/useF5AiGenerate'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import F5SheetAttachments from './F5SheetAttachments.vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

defineEmits<{ imported: [] }>()

const props = withDefaults(defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
}>(), {
  projectId: '',
})

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const other = useF5OtherCost({
  allResponses: allResponsesRef,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF5AiGenerate(wpIdRef)

const threshold = F5_OTHER_COST_CHANGE_RATE_THRESHOLD
const projectIdStr = computed(() => props.projectId)
const ieCtx = computed(() =>
  isImportExportSheet('f5', 'F5-3') ? resolveImportExportSheet('f5', 'F5-3') : null,
)

const tableData = computed(() => {
  const rows: any[] = other.rows.value.map((r) => ({ __type: 'data', ...r }))
  const total = other.totalRow.value
  rows.push({
    __type: 'total',
    id: '__total',
    item: '合计',
    isFixed: true,
    ...total,
    remark: '',
  })
  return rows
})

function rowClass({ row }: { row: any }): string {
  if (row.__type === 'total') return 'f5-row-total'
  if (other.isRowHighlighted(row)) return 'f5-row-warn'
  return ''
}

function isRateWarn(rate: number | 'N/A' | null | undefined): boolean {
  return typeof rate === 'number' && Math.abs(rate) >= threshold
}

async function promptAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入成本项目名称', '新增项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '项目名称不能为空',
    })
    if (value) other.addRow(value.trim())
  } catch { /* 取消 */ }
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  if (Math.abs(v) < 0.005) return '-'
  const formatted = Math.abs(v).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return v < 0 ? `(${formatted})` : formatted
}

function pct(v: number | 'N/A' | null | undefined): string {
  if (v == null || v === 'N/A') return 'N/A'
  return `${Number(v).toFixed(2)}%`
}

function openReview() {
  openReviewDialog?.('F5-3-conclusion')
}

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F5-3',
    accountHint: '其他业务成本',
    threshold,
    significantChanges: other.significantChanges.value.map((r) => ({
      item: r.item,
      currentAudited: r.currentAudited,
      priorAudited: r.priorAudited,
      changeAmount: r.changeAmount,
      changeRate: r.changeRate,
      currentStructureRatio: r.currentStructureRatio,
    })),
    total: other.totalRow.value,
    items: other.rows.value
      .filter((r) => r.item.trim() || r.currentAudited || r.priorAudited)
      .map((r) => ({
        item: r.item,
        currentUnaudited: r.currentUnaudited,
        currentAudited: r.currentAudited,
        priorUnaudited: r.priorUnaudited,
        priorAudited: r.priorAudited,
        changeAmount: r.changeAmount,
        changeRate: r.changeRate,
        currentStructureRatio: r.currentStructureRatio,
        priorStructureRatio: r.priorStructureRatio,
        remark: r.remark,
      })),
  }
}

async function generateAiNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'other-cost-note',
    other.auditNote.value,
    aiContext(),
    'AI 生成 · F5-3审计说明',
  )
  if (text) other.saveAuditNote(text)
}

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'other-cost-conclusion',
    other.auditConclusion.value,
    aiContext(),
    'AI 生成 · F5-3审计结论',
  )
  if (text) other.saveAuditConclusion(text)
}
</script>

<style scoped>
.f5-other-cost { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f5-other-cost :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f5-other-cost :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #315a8a;
  background: #eef4fa;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 600; color: #315a8a; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.65; }
.guidance-content p { margin: 3px 0; }
.objective-alert, .change-alert { margin-bottom: 12px; }

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.f5-formula { border-bottom: 1px dashed #909399; cursor: help; }
.f5-formula.is-warn { color: #e6a23c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.f5-row-total) { background: #f0f5fa !important; font-weight: 600; }
:deep(.f5-row-warn) { background: #fdf6ec !important; }

.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
