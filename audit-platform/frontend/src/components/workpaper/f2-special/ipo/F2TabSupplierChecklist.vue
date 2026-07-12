<template>
  <div class="f2-supplier-checklist">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表核查主要供应商各审计程序的执行情况（工商核查、实地走访、函证等），确保采购交易真实、完整、与被审计单位有关（CAS 1141 舞弊 / CAS 1231 风险应对）。</p>
        <p>2. 每个核查项从下拉选择状态（已完成/进行中/未开始/不适用），完成度自动计算；逾期供应商行以橙色底纹提示。</p>
        <p>3. 关注新增、异常或集中度高的供应商，结合工商信息与资金流水核实其商业实质，警惕虚构采购与关联方非关联化。</p>
        <p>4. 可通过工具栏"AI 生成"辅助撰写核查说明，"💬"发起复核对话，"导入导出"批量维护供应商清单。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实主要供应商采购交易的真实性与完整性，确认各项核查程序已执行到位，识别未披露关联方及异常采购风险。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="sc.addRow()">+ 新增供应商</el-button>
        <el-input v-model="sc.searchQuery.value" size="small" placeholder="搜索供应商/负责人" clearable class="search" />
        <el-segmented v-model="checkPage" :options="checkPages" size="small" />
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-69"
          :disabled="isReadonly"
          ai-section="supplier-analysis"
          :existing-content="sc.auditNote.value"
          review-section="F2-69-checklist"
          @ai-filled="(t: string) => { sc.auditNote.value = t }"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-69" /></span>
        <el-tag size="small" type="info">共 {{ sc.filteredRows.value.length }} 行</el-tag>
      </div>
    </div>

    <!-- 进度概览 -->
    <div class="progress-cards">
      <span class="pcard done">已完成 {{ sc.progressSummary.value.done }}</span>
      <span class="pcard prog">进行中 {{ sc.progressSummary.value.inProgress }}</span>
      <span class="pcard todo">未开始 {{ sc.progressSummary.value.notStarted }}</span>
      <span class="pcard na">不适用 {{ sc.progressSummary.value.na }}</span>
    </div>

    <el-table
      :data="sc.filteredRows.value"
      border size="small" max-height="440"
      :row-class-name="({ row }) => row.isOverdue ? 'overdue-row' : ''"
    >
      <el-table-column label="供应商" width="130" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.supplierName" size="small"
            @change="(v: string) => sc.updateRow(row.id, { supplierName: v })" />
          <span v-else>{{ row.supplierName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="完成度" width="120" fixed class-name="auto-calc-col">
        <template #default="{ row }">
          <el-progress :percentage="Math.round(row.completionPct)" :stroke-width="8"
            :status="row.completionPct >= 100 ? 'success' : row.isOverdue ? 'exception' : undefined" />
        </template>
      </el-table-column>

      <el-table-column
        v-for="(label, i) in visibleChecks"
        :key="label"
        :label="label"
        width="100"
        align="center"
      >
        <template #default="{ row }">
          <el-select
            :model-value="row[visibleCheckKeys[i]]"
            size="small"
            :disabled="isReadonly"
            @change="(v: CheckItemStatus) => sc.updateCheck(row.id, visibleCheckKeys[i], v)"
          >
            <el-option v-for="s in sc.CHECK_STATUS_OPTIONS" :key="s" :label="shortStatus(s)" :value="s" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="负责人" width="85">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.owner" size="small"
            @change="(v: string) => sc.updateRow(row.id, { owner: v })" />
          <span v-else>{{ row.owner }}</span>
        </template>
      </el-table-column>
      <el-table-column label="完成日期" width="120">
        <template #default="{ row }">
          <el-date-picker v-if="!isReadonly" :model-value="row.completeDate" type="date" size="small"
            value-format="YYYY-MM-DD" style="width: 100%"
            @update:model-value="(v: string) => sc.updateRow(row.id, { completeDate: v ?? '' })" />
          <span v-else>{{ row.completeDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="快捷" width="100">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" link size="small" @click="sc.markAllChecks(row.id, '已完成')">全完成</el-button>
        </template>
      </el-table-column>
      <el-table-column label="" width="48" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="sc.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">核查进度说明</span>
        </div>
      </template>
      <el-input v-model="sc.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" :disabled="isReadonly"
        placeholder="记录供应商核查进度、发现的异常情况及处理说明…" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef } from 'vue'
import {
  useF2SupplierChecklist,
  type CheckItemStatus,
  type CheckItemKey,
} from '../../composables/useF2SupplierChecklist'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ wpId?: string; allResponses: Map<string, ChecklistResponse>; isReadonly: boolean }>()

const sc = useF2SupplierChecklist({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const checkPage = ref(0)
const checkPages = [
  { label: '核查项 1~5', value: 0 },
  { label: '核查项 6~10', value: 1 },
]

const visibleChecks = computed(() =>
  checkPage.value === 0
    ? sc.CHECK_ITEM_LABELS.slice(0, 5)
    : sc.CHECK_ITEM_LABELS.slice(5, 10),
)

const visibleCheckKeys = computed((): CheckItemKey[] =>
  checkPage.value === 0
    ? sc.CHECK_KEYS.slice(0, 5)
    : sc.CHECK_KEYS.slice(5, 10),
)

function shortStatus(s: CheckItemStatus): string {
  const map: Record<CheckItemStatus, string> = {
    '已完成': '完成', '进行中': '进行', '未开始': '未始', '不适用': 'N/A',
  }
  return map[s]
}
</script>

<style scoped>
.f2-supplier-checklist { padding: 12px 16px; font-size: var(--wp-font-size, 13px); }
.f2-supplier-checklist :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-supplier-checklist :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.search { width: 180px; }

/* 进度概览 */
.progress-cards { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
.pcard { font-size: 12px; padding: 4px 10px; border-radius: 6px; }
.pcard.done { background: #f0f9eb; color: #67c23a; }
.pcard.prog { background: #ecf5ff; color: #409eff; }
.pcard.todo { background: #fdf6ec; color: #e6a23c; }
.pcard.na { background: #f4f4f5; color: #909399; }

/* 表格 */
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.overdue-row) { background: #fdf6ec !important; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
