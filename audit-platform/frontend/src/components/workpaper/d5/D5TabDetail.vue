<template>
<div class="d5-detail">
  <!-- 双模式切换 -->
  <div class="mode-toolbar">
    <el-segmented v-model="viewMode" :options="modeOptions" size="small" />
  </div>

  <template v-if="viewMode === 'structured'">
    <!-- 工具栏 -->
    <div class="detail-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">
        添加明细行
      </el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromD1">
        从D1导入(出售模式票据)
      </el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromD2">
        从D2导入(出售模式账款)
      </el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromAuxBalance">
        从余额表导入
      </el-button>
      <el-button size="small" :disabled="true">导出空模板</el-button>
      <el-button size="small" :disabled="true">导入数据</el-button>
    </div>

    <!-- 明细表主体 -->
    <el-table
      :data="displayRows"
      size="small"
      border
      stripe
      :max-height="rows.length > 30 ? 600 : undefined"
      style="width: 100%"
    >
      <!-- A: 类别 (固定) -->
      <el-table-column label="类别" width="120" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-label">{{ row.category }}</span>
          </template>
          <el-select
            v-else-if="!isReadonly"
            :model-value="row.category"
            size="small"
            placeholder="选择类别"
            @change="(val: string) => updateCell(row.rowId, 'category', val)"
          >
            <el-option label="应收票据" value="应收票据" />
            <el-option label="应收账款" value="应收账款" />
          </el-select>
          <span v-else>
            {{ row.category }}
            <GtIndexChip v-if="row.category === '应收票据'" wp-code="D1-6" label="D1-6" />
            <GtIndexChip v-if="row.category === '应收账款'" wp-code="D2-13" label="D2-13" />
          </span>
        </template>
      </el-table-column>

      <!-- B: 明细项目 (固定) -->
      <el-table-column label="明细项目" width="140" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-label">{{ row.itemName || '' }}</span>
          </template>
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.itemName"
            size="small"
            @change="(val: string) => updateCell(row.rowId, 'itemName', val)"
          />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>

      <!-- C: 期初未审 -->
      <el-table-column label="期初未审" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.priorUnadjusted) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.priorUnadjusted"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'priorUnadjusted', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.priorUnadjusted) }}</span>
        </template>
      </el-table-column>

      <!-- D: 期初AJE -->
      <el-table-column label="期初AJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.priorAje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.priorAje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'priorAje', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.priorAje) }}</span>
        </template>
      </el-table-column>

      <!-- E: 期初RJE -->
      <el-table-column label="期初RJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.priorRje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.priorRje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'priorRje', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.priorRje) }}</span>
        </template>
      </el-table-column>

      <!-- F: 期初审定 (自动) -->
      <el-table-column label="期初审定" width="110" align="right">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.priorAudited) }}</span>
        </template>
      </el-table-column>

      <!-- G: OCI减值准备余额 -->
      <el-table-column label="OCI减值" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.ociImpairment) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.ociImpairment"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'ociImpairment', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.ociImpairment) }}</span>
        </template>
      </el-table-column>

      <!-- H: 本期增加 -->
      <el-table-column label="本期增加" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.periodIncrease) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.periodIncrease"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'periodIncrease', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.periodIncrease) }}</span>
        </template>
      </el-table-column>

      <!-- I: 本期减少 -->
      <el-table-column label="本期减少" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.periodDecrease) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.periodDecrease"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'periodDecrease', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.periodDecrease) }}</span>
        </template>
      </el-table-column>

      <!-- J: 期末余额 (自动) -->
      <el-table-column label="期末余额" width="110" align="right">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.endBalance) }}</span>
        </template>
      </el-table-column>

      <!-- K: 被审计单位重分类 -->
      <el-table-column label="重分类" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.entityReclass) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.entityReclass"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'entityReclass', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.entityReclass) }}</span>
        </template>
      </el-table-column>

      <!-- L: 期末未审余额 (自动) -->
      <el-table-column label="期末未审" width="110" align="right">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.endUnadjusted) }}</span>
        </template>
      </el-table-column>

      <!-- M: 期末账项调整 -->
      <el-table-column label="期末AJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.endAje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.endAje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'endAje', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.endAje) }}</span>
        </template>
      </el-table-column>

      <!-- N: 期末重分类调整 -->
      <el-table-column label="期末RJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.endRje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.endRje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'endRje', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.endRje) }}</span>
        </template>
      </el-table-column>

      <!-- O: 期末审定余额 (自动) -->
      <el-table-column label="期末审定" width="110" align="right">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.endAudited) }}</span>
        </template>
      </el-table-column>

      <!-- P: 期末OCI减值 -->
      <el-table-column label="期末OCI减值" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.endOciImpairment) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.endOciImpairment"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'endOciImpairment', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.endOciImpairment) }}</span>
        </template>
      </el-table-column>

      <!-- Q: 备注 -->
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            :model-value="row.remark"
            size="small"
            @change="(val: string) => updateCell(row.rowId, 'remark', val)"
          />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            type="danger"
            text
            size="small"
            @click="removeRow(row.rowId)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明区域 -->
    <div class="audit-notes-section">
      <h4>审计说明</h4>
      <el-input
        v-model="auditExplanation"
        type="textarea"
        :rows="3"
        :disabled="isReadonly"
        placeholder="对明细表本期变动的分析说明..."
      />
      <div class="note-actions">
        <el-button size="small" :disabled="true">🤖AI</el-button>
        <el-button size="small" @click="openReview('D5-detail-note')">💬 复核</el-button>
      </div>
    </div>
  </template>

  <!-- OnlyOffice占位 -->
  <div v-else class="onlyoffice-placeholder">
    <el-empty description="在线编辑模式（OnlyOffice）" />
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D5TabDetail.vue — D5-2 明细表
 *
 * el-table 横向滚动17列，固定前2列（类别/明细项目）
 * 自动计算列灰底不可编辑（F/J/L/O）
 * 按类别小计行 + 总合计行
 * 超30行虚拟滚动（max-height限制）
 *
 * Task: 14.1
 * Requirements: 4.1-4.9, 5.1-5.7, 10.9
 */
import { ref, computed, inject, watch, type Ref } from 'vue'
import { useD5Detail } from '../composables/useD5Detail'
import type { ChecklistResponse } from '../composables/useD5FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── Mode ────────────────────────────────────────────────────────────────────

const viewMode = ref('structured')
const modeOptions = [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  rows,
  subtotalByCategory,
  totalRow,
  addRow,
  removeRow,
  updateCell,
  importFromD1,
  importFromD2,
  importFromAuxBalance,
} = useD5Detail({
  allResponses: props.allResponses,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

// ─── Audit Notes ─────────────────────────────────────────────────────────────

const auditExplanation = ref('')

watch(
  () => props.allResponses.value.get('D5-2-note-explanation')?.remark,
  (val) => { auditExplanation.value = val || '' },
  { immediate: true },
)

watch(auditExplanation, (val) => {
  props.debouncedSave('D5-2-note-explanation', { remark: val })
})

// ─── Display Rows (含小计行+合计行) ──────────────────────────────────────────

interface DisplayRow {
  rowId: string
  category: string
  itemName: string
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number
  ociImpairment: number
  periodIncrease: number
  periodDecrease: number
  endBalance: number
  entityReclass: number
  endUnadjusted: number
  endAje: number
  endRje: number
  endAudited: number
  endOciImpairment: number
  remark: string
  _isSubtotal?: boolean
  _isTotal?: boolean
}

const displayRows = computed<DisplayRow[]>(() => {
  const result: DisplayRow[] = []
  // 按类别分组：先显示应收票据行及其小计，再显示应收账款行及其小计
  const categories = ['应收票据', '应收账款']

  for (const cat of categories) {
    const catRows = rows.value.filter(r => r.category === cat)
    if (catRows.length > 0) {
      result.push(...catRows.map(r => ({ ...r } as DisplayRow)))
      // 类别小计行
      const sub = subtotalByCategory.value[cat]
      if (sub) {
        result.push({
          ...sub,
          rowId: `__subtotal-${cat}__`,
          category: `${cat}小计`,
          itemName: '',
          _isSubtotal: true,
        } as DisplayRow)
      }
    }
  }

  // 未分类行
  const uncategorized = rows.value.filter(r => !categories.includes(r.category))
  if (uncategorized.length > 0) {
    result.push(...uncategorized.map(r => ({ ...r } as DisplayRow)))
  }

  // 总合计行
  result.push({
    ...totalRow.value,
    rowId: '__total__',
    category: '合计',
    itemName: '',
    _isTotal: true,
  } as DisplayRow)

  return result
})

// ─── Formatting Helpers ──────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function openReview(sectionId: string) {
  openReviewDialog(sectionId)
}
</script>

<style scoped>
.d5-detail {
  padding: 16px;
}

.mode-toolbar {
  margin-bottom: 12px;
}

.detail-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.auto-calc {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 2px;
  color: #909399;
}

.subtotal-label {
  font-weight: 700;
}

.subtotal-amount {
  font-weight: 700;
}

.audit-notes-section {
  margin-top: 20px;
}

.audit-notes-section h4 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
}

.note-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.onlyoffice-placeholder {
  padding: 40px 0;
}
</style>
