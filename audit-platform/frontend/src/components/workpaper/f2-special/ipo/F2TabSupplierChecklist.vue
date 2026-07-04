<template>
  <div class="f2-supplier-checklist">
    <header class="sheet-header">
      <div>
        <h3>供应商核查清单</h3>
        <span class="code">F2-69</span>
      </div>
      <div class="progress-cards">
        <span class="pcard done">已完成 {{ sc.progressSummary.value.done }}</span>
        <span class="pcard prog">进行中 {{ sc.progressSummary.value.inProgress }}</span>
        <span class="pcard todo">未开始 {{ sc.progressSummary.value.notStarted }}</span>
        <span class="pcard na">不适用 {{ sc.progressSummary.value.na }}</span>
      </div>
    </header>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="sc.addRow()">+ 新增供应商</el-button>
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
      <el-input v-model="sc.searchQuery.value" size="small" placeholder="搜索供应商/负责人" clearable class="search" />
      <el-segmented v-model="checkPage" :options="checkPages" size="small" />
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
      <el-table-column label="完成度" width="120" fixed>
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

    <footer class="footer">
      <h4>核查进度说明</h4>
      <el-input v-model="sc.auditNote.value" type="textarea" :rows="2" :disabled="isReadonly" />
    </footer>
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
.f2-supplier-checklist { padding: 12px 16px; font-size: 13px; background: linear-gradient(180deg, #f8fafc 0%, #fff 100px); border-radius: 8px; }
.sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.sheet-header h3 { margin: 0; font-size: 16px; display: inline; }
.code { font-size: 12px; color: #909399; margin-left: 8px; }
.progress-cards { display: flex; gap: 8px; flex-wrap: wrap; }
.pcard { font-size: 12px; padding: 4px 10px; border-radius: 6px; }
.pcard.done { background: #f0f9eb; color: #67c23a; }
.pcard.prog { background: #ecf5ff; color: #409eff; }
.pcard.todo { background: #fdf6ec; color: #e6a23c; }
.pcard.na { background: #f4f4f5; color: #909399; }
.toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
.search { width: 180px; }
:deep(.overdue-row) { background: #fdf6ec !important; }
.footer { margin-top: 14px; }
.footer h4 { margin: 0 0 8px; font-size: 13px; color: #606266; }
</style>
