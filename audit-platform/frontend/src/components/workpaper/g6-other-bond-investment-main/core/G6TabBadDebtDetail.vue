<template>
  <div class="g6-bad-debt" data-testid="g6-bad-debt">
    <div class="section-head">
      <h3 class="sheet-title">G6-3 坏账准备明细表</h3>
      <div class="head-actions">
        <span class="chip-wrap"><GtIndexChip value="wp:G6-3" :context-project-id="props.projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G6-1" :context-project-id="props.projectId" /></span>
        <el-tag size="small" type="info">明细 {{ detail.leaves.value.length }} 行</el-tag>
        <el-tag size="small" type="success">期末审定 {{ fmt(detail.totalClosingAudited.value) }}</el-tag>
        <el-dropdown trigger="click" size="small" @command="handleDropdownCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="opt in dropdownOptions"
                :key="opt.command"
                :command="opt.command"
                :disabled="opt.disabled"
              >{{ opt.label }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G6-3-bad-debt')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认其他债权投资坏账准备的存在、完整与计价；验证期初→本期增减→期末滚动态及单项/组合划分，期末审定与 G6-1 减值准备勾稽。"
      style="margin-bottom: 12px"
    />

    <div class="methodology-context">
      <p class="methodology-title">滚动态公式（对齐 Excel G6-3）：</p>
      <p>期初审定 = 期初未审 + 期初账项调整</p>
      <p>期末未审 = 期初未审 + 计提 + 其他增加 − 转回 − 转销 − 其他减少</p>
      <p>期末审定 = 期末未审 + 期末账项调整</p>
      <p>ECL 损失率测算见 G6-12；本表聚焦坏账准备滚动与列报勾稽。</p>
    </div>

    <div class="toolbar-row">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="detail.addRow('individual')">
        + 新增单项（其中）
      </el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="detail.addRow('portfolio')">
        + 新增组合（其中）
      </el-button>
      <el-button size="small" type="warning" plain :disabled="isReadonly" @click="onWriteback">
        回写 G6-1 减值
      </el-button>
    </div>

    <el-table
      :data="detail.displayRows.value"
      border
      size="small"
      max-height="560"
      :row-class-name="rowClassName"
      style="width: 100%"
    >
      <el-table-column label="项目" min-width="180" fixed>
        <template #default="{ row }">
          <span v-if="row.kind !== 'leaf'" class="label-strong">{{ row.item }}</span>
          <el-input
            v-else
            :model-value="row.item"
            size="small"
            :disabled="isReadonly"
            :placeholder="row.category === 'individual' ? '债务人/项目' : '组合名称'"
            @change="(v: string) => detail.updateCell(row.id, 'item', v)"
          />
        </template>
      </el-table-column>

      <el-table-column label="期初数" align="center">
        <el-table-column label="未审数" width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.editable && !isReadonly"
              :model-value="row.openingUnadjusted"
              size="small"
              class="amt-input"
              @change="(v: number) => detail.updateCell(row.id, 'openingUnadjusted', v ?? 0)"
            />
            <span v-else>{{ fmt(row.openingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.editable && !isReadonly"
              :model-value="row.openingAdjustment"
              size="small"
              class="amt-input"
              @change="(v: number) => detail.updateCell(row.id, 'openingAdjustment', v ?? 0)"
            />
            <span v-else>{{ fmt(row.openingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期初审定 = 未审 + 调整">{{ fmt(row.openingAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期增加" align="center">
        <el-table-column label="计提" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.editable && !isReadonly"
              :model-value="row.provisionIncrease"
              size="small"
              class="amt-input"
              @change="(v: number) => detail.updateCell(row.id, 'provisionIncrease', v ?? 0)"
            />
            <span v-else>{{ fmt(row.provisionIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="其他增加" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.otherIncrease"
              size="small"
              :controls="false"
              class="amt-input"
              @change="(v: number) => detail.updateCell(row.id, 'otherIncrease', v ?? 0)"
            />
            <span v-else>{{ fmt(row.otherIncrease) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期减少" align="center">
        <el-table-column label="转回" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.reversal"
              size="small"
              :controls="false"
              class="amt-input"
              @change="(v: number) => detail.updateCell(row.id, 'reversal', v ?? 0)"
            />
            <span v-else>{{ fmt(row.reversal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转销" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.writeOff"
              size="small"
              :controls="false"
              class="amt-input"
              @change="(v: number) => detail.updateCell(row.id, 'writeOff', v ?? 0)"
            />
            <span v-else>{{ fmt(row.writeOff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="其他减少" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.otherDecrease"
              size="small"
              :controls="false"
              class="amt-input"
              @change="(v: number) => detail.updateCell(row.id, 'otherDecrease', v ?? 0)"
            />
            <span v-else>{{ fmt(row.otherDecrease) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="期末数" align="center">
        <el-table-column label="未审数" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末未审 = 期初未审 + 增加 − 减少">{{ fmt(row.closingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.editable && !isReadonly"
              :model-value="row.closingAdjustment"
              size="small"
              class="amt-input"
              @change="(v: number) => detail.updateCell(row.id, 'closingAdjustment', v ?? 0)"
            />
            <span v-else>{{ fmt(row.closingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="110" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'total-strong': row.kind === 'total' }"
              title="期末审定 = 期末未审 + 账项调整"
            >{{ fmt(row.closingAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="单独计提减值、转回或转销原因" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="row.editable && !isReadonly"
            :model-value="row.reason"
            size="small"
            @change="(v: string) => detail.updateCell(row.id, 'reason', v)"
          />
          <span v-else>{{ row.reason || '' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm v-if="row.kind === 'leaf'" title="确认删除？" @confirm="detail.removeRow(row.id)">
            <template #reference>
              <el-icon class="delete-icon"><Delete /></el-icon>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <G6AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      :note="detail.auditNote.value"
      :conclusion="detail.auditConclusion.value"
      @update:note="(v: string) => { detail.auditNote.value = v }"
      @update:conclusion="(v: string) => { detail.auditConclusion.value = v }"
      note-ai-section="baddebt-note"
      conclusion-ai-section="baddebt-conclusion"
      :related-context="{
        行数: detail.leaves.value.length,
        单项期末未审: detail.individualClosingUnadjusted.value,
        组合期末未审: detail.portfolioClosingUnadjusted.value,
        合计期末未审: detail.totalClosingUnadjusted.value,
        单项期末审定: detail.individualClosingAudited.value,
        组合期末审定: detail.portfolioClosingAudited.value,
        合计期末审定: detail.totalClosingAudited.value,
      }"
      note-placeholder="填写审计说明：坏账准备滚动态测试、单项/组合划分、转回转销原因及与 G6-1 勾稽情况。"
      note-hint="ECL 损失率细节可索引 G6-12；本表侧重滚动与列报。"
      conclusion-placeholder="A、未见异常。B、除上述调整外其余未见异常。C、存在重大未调整事项，不可确认。"
      conclusion-hint="按 A/B/C 口径评价坏账准备充分性。"
    />

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>结构对齐 Excel：按单项评估计提 / 信用风险组合计提 / 合计。</li>
        <li>期末未审 = 期初未审 + 计提 + 其他增加 − 转回 − 转销 − 其他减少。</li>
        <li>单独计提的减值、转回或转销须在「原因」列说明。</li>
        <li>「回写 G6-1 减值」将单项/组合期末未审写入审定表减值准备对应行（不含期末调整，避免双重叠加）。</li>
        <li>损失率/Stage 测算请在 ECL 组 G6-11~G6-13 完成。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G6TabBadDebtDetail.vue — 对齐 Excel《坏账准备明细表G6-3》滚动态
 */
import { ref, computed, toRef, inject, watch } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useG6BadDebtDetail, type G6BadDebtDisplayRow } from '../../composables/useG6BadDebtDetail'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import {
  useG6MainImportExport,
  type G6MainImportableSheet,
} from '../../composables/useG6MainImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import G6AuditTextCards from '../G6AuditTextCards.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses?: Map<string, ChecklistResponse>
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const isReadonly = computed(() => props.isReadonly)

const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
watch(
  () => props.allResponses,
  (source) => {
    if (!source) return
    allResponses.value = source
  },
  { immediate: true, deep: true },
)

const detail = useG6BadDebtDetail({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses,
  isReadonly,
  htmlData: toRef(props, 'htmlData'),
})

watch(
  () => props.allResponses?.size,
  () => detail.reload(),
  { immediate: true },
)

function rowClassName({ row }: { row: G6BadDebtDisplayRow }): string {
  if (row.kind === 'section_header') return 'row-section'
  if (row.kind === 'subtotal') return 'row-subtotal'
  if (row.kind === 'total') return 'row-total'
  return ''
}

function fmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function onWriteback(): void {
  detail.writebackToAdjudication()
  ElMessage.success(
    `已回写减值期末未审：单项 ${fmt(detail.individualClosingUnadjusted.value)} / 组合 ${fmt(detail.portfolioClosingUnadjusted.value)}`,
  )
}

const ie = useG6MainImportExport({
  wpId: computed(() => props.wpId),
  onImported: () => {
    detail.reload()
    emit('imported')
  },
})
const dropdownOptions = computed(() => ie.getDropdownOptions('G6-3'))

async function handleDropdownCommand(command: string) {
  const [action, sheet] = command.split(':') as [string, G6MainImportableSheet]
  if (action === 'export-template') await ie.exportTemplate(sheet)
  else if (action === 'export-data') await ie.exportData(sheet)
  else if (action === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls'
    input.onchange = async (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) await ie.importData(sheet, file)
    }
    input.click()
  }
}
</script>

<style scoped>
.g6-bad-debt { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.methodology-context {
  border-left: 4px solid #d97706; background: #fffbeb;
  padding: 10px 14px; margin-bottom: 12px; border-radius: 0 4px 4px 0;
  font-size: 12px; line-height: 1.7; color: #92400e;
}
.methodology-title { font-weight: 600; margin: 0 0 4px; color: #78350f; }
.methodology-context p { margin: 2px 0; }
.toolbar-row { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.label-strong { font-weight: 700; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.total-strong { font-weight: 700; color: #06723a; }
.amt-input { width: 100%; }
.amt-input :deep(.el-input__inner) { text-align: right; }
.delete-icon { cursor: pointer; color: #f56c6c; }
:deep(.row-section) { background: #ecf5ff !important; font-weight: 700; }
:deep(.row-subtotal) { background: #f0f9eb !important; font-weight: 600; }
:deep(.row-total) { background: #fdf6ec !important; font-weight: 700; }
.prep-hint {
  margin-top: 12px; padding: 8px 12px;
  background: #f5f7fa; border-radius: 4px; font-size: 12px; color: #606266;
}
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; }
</style>
