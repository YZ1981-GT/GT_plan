<template>
  <el-card shadow="never" class="section-card">
    <template #header>
      <div class="section-header">
        <span class="section-title">{{ title }}</span>
        <el-button
          v-if="isDynamic && !isReadonly"
          size="small"
          type="primary"
          plain
          @click="$emit('add-row')"
        >
          + 新增行
        </el-button>
      </div>
    </template>

    <el-table
      :data="rows"
      border
      size="small"
      style="font-size: 13px; --el-table-font-size: 13px"
      max-height="500"
      :row-class-name="rowClassName"
    >
      <!-- 序号 -->
      <el-table-column prop="seq" label="序号" width="50" align="center" fixed />
      <!-- 项目名称 -->
      <el-table-column label="项目名称" min-width="160" fixed>
        <template #default="{ row }">
          <span :style="{ paddingLeft: row.indent * 16 + 'px' }">
            <template v-if="(isDynamic || row.isSubItem) && !isReadonly">
              <el-input
                :model-value="row.label"
                size="small"
                placeholder="填写项目名称"
                @change="(v: string) => $emit('update-cell', row.id, 'label', v)"
              />
            </template>
            <template v-else>{{ row.label }}</template>
          </span>
        </template>
      </el-table-column>

      <!-- 未审数段 -->
      <el-table-column label="未审数" align="center">
        <el-table-column label="期初数" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.unadjBegin"
              :controls="false"
              size="small"
              style="width:90px"
              @change="(v: number) => $emit('update-cell', row.id, 'unadjBegin', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.unadjBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.unadjIncrease"
              :controls="false"
              size="small"
              style="width:90px"
              @change="(v: number) => $emit('update-cell', row.id, 'unadjIncrease', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.unadjIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.unadjDecrease"
              :controls="false"
              size="small"
              style="width:90px"
              @change="(v: number) => $emit('update-cell', row.id, 'unadjDecrease', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.unadjDecrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末数" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="期末=期初+增加-减少">{{ fmtNum(row.unadjEnd) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 期初调整段 -->
      <el-table-column label="期初调整" align="center">
        <el-table-column label="账项调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.openingAdj"
              :controls="false"
              size="small"
              style="width:90px"
              @change="(v: number) => $emit('update-cell', row.id, 'openingAdj', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.openingAdj) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 账项调整段 -->
      <el-table-column label="账项调整" align="center">
        <el-table-column label="本期增加" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.ajeIncrease"
              :controls="false"
              size="small"
              style="width:90px"
              @change="(v: number) => $emit('update-cell', row.id, 'ajeIncrease', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.ajeIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.ajeDecrease"
              :controls="false"
              size="small"
              style="width:90px"
              @change="(v: number) => $emit('update-cell', row.id, 'ajeDecrease', v ?? 0)"
            />
            <span v-else>{{ fmtNum(row.ajeDecrease) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 审定数段 -->
      <el-table-column label="审定数" align="center">
        <el-table-column label="期初数" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="审定期初=未审期初+期初调整">{{ fmtNum(row.auditedBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="审定增加=未审增加+账项增加">{{ fmtNum(row.auditedIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="审定减少=未审减少+账项减少">{{ fmtNum(row.auditedDecrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末数" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="审定期末=审定期初+审定增加-审定减少">{{ fmtNum(row.auditedEnd) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column label="备注" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            placeholder=""
            @change="(v: string) => $emit('update-cell', row.id, 'remark', v)"
          />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列(动态行) -->
      <el-table-column v-if="isDynamic && !isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="$emit('remove-row', row.id)">
            删
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="total-row">
      <span class="total-label">合计</span>
      <span class="total-cell">未审期末: <b>{{ fmtNum(totalRow.unadjEnd) }}</b></span>
      <span class="total-cell">审定期末: <b>{{ fmtNum(totalRow.auditedEnd) }}</b></span>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import type { J1DetailRow } from '@/composables/workpaper/j1/useJ1Detail'

defineProps<{
  title: string
  rows: J1DetailRow[]
  totalRow: J1DetailRow
  isDynamic: boolean
  isReadonly: boolean
  sectionKey: string
}>()

defineEmits<{
  'update-cell': [rowId: string, field: keyof J1DetailRow, value: number | string]
  'add-row': []
  'remove-row': [rowId: string]
}>()

function fmtNum(val: number): string {
  if (val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClassName({ row }: { row: J1DetailRow }): string {
  if (row.isSubItem) return 'sub-item-row'
  return ''
}
</script>

<style scoped>
.section-card { margin-bottom: 12px; }
:deep(.section-card .el-card__header) { padding: 8px 12px; }
:deep(.section-card .el-card__body) { padding: 12px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-weight: 600; font-size: 14px; }
:deep(.el-table) { font-size: 13px !important; }
:deep(.el-table th), :deep(.el-table td) { font-size: 13px !important; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.sub-item-row) { color: #606266; }
.total-row {
  display: flex; align-items: center; gap: 24px;
  padding: 8px 12px; margin-top: 8px;
  background: #fafafa; border-radius: 4px; font-size: 13px;
}
.total-label { font-weight: 600; min-width: 40px; }
.total-cell b { color: #409eff; }
</style>
