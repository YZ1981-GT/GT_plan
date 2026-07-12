<script setup lang="ts">
/**
 * E1TabCertificateCount.vue — E1-9 存单盘点
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.8
 *
 * - Uses useE1CashCount composable with variant='cert'
 * - Dynamic rows: 存单编号 | 开户银行 | 存单类型 | 存入日 | 到期日 | 金额 | 利率 | 盘点结果
 *
 * Requirements: 7.3
 */
import { inject, toRef, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useE1CashCount, type CertCountRow } from '../composables/useE1CashCount'
import { useE1ImportExport } from '../composables/useE1ImportExport'
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

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions & { variant: 'cert' } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  variant: 'cert',
}

const {
  rows,
  isLoading,
  addRow,
  removeRow,
  updateCell,
} = useE1CashCount(options)

// ─── 导入导出（E1-9） ─────────────────────────────────────────────────────────

const sheetCode = computed(() => 'E1-9')
const { exportTemplate, exportData, importData, isImporting } = useE1ImportExport({
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  sheet: sheetCode as unknown as Ref<string>,
})

async function handleImport(file: File): Promise<boolean> {
  const res = await importData(file)
  if (res.success) {
    ElMessage.success(res.message || '导入成功')
    await reloadWorkpaperData?.()
  } else {
    ElMessage.warning(res.message || '导入失败')
  }
  return false
}

function asCert(row: any): CertCountRow { return row }
</script>

<template>
  <div class="e1-tab-certificate-count">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 检查大额存单/定期存单原件，核对存单编号、金额、存入日、到期日与利率是否与账面一致。</p>
        <p>2. 关注存单是否存在质押、冻结、担保等权利受限情形，受限部分应单独披露。</p>
        <p>3. 盘点结果为"未见"的存单应追查原因，必要时执行银行函证程序。</p>
        <p>4. 核对存单是否已完整登记入账并在货币资金/其他货币资金审定表中恰当列示。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实大额存单/定期存款的存在性与权利归属，确认账实相符且无未披露的权利受限。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate()">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData()">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx,.xls"
                  :before-upload="handleImport"
                  :disabled="isImporting"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <el-table :data="rows" border stripe size="small" max-height="500" style="width: 100%">
          <el-table-column label="存单编号" width="130">
            <template #default="{ row }">
              <el-input
                :model-value="asCert(row).certNo"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'certNo', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="开户银行" width="140">
            <template #default="{ row }">
              <el-input
                :model-value="asCert(row).bank"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'bank', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="存单类型" width="110">
            <template #default="{ row }">
              <el-input
                :model-value="asCert(row).certType"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'certType', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="存入日" width="130">
            <template #default="{ row }">
              <el-date-picker
                :model-value="asCert(row).depositDate"
                :disabled="isReadonly"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, 'depositDate', val || '')"
              />
            </template>
          </el-table-column>
          <el-table-column label="到期日" width="130">
            <template #default="{ row }">
              <el-date-picker
                :model-value="asCert(row).maturityDate"
                :disabled="isReadonly"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, 'maturityDate', val || '')"
              />
            </template>
          </el-table-column>
          <el-table-column label="金额" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="asCert(row).amount"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number) => updateCell(row.id, 'amount', val ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column label="利率(%)" width="100" align="center">
            <template #default="{ row }">
              <el-input-number
                :model-value="asCert(row).interestRate"
                :disabled="isReadonly"
                :controls="false"
                :precision="4"
                size="small"
                @change="(val: number) => updateCell(row.id, 'interestRate', val ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column label="盘点结果" width="110" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="asCert(row).result"
                :disabled="isReadonly"
                size="small"
                placeholder="选择"
                @change="(val: string) => updateCell(row.id, 'result', val)"
              >
                <el-option label="已见" value="已见" />
                <el-option label="未见" value="未见" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="!isReadonly"
                type="danger"
                text
                size="small"
                @click="removeRow(row.id)"
              >删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-certificate-count {
  padding: 12px 0;
}
.e1-tab-certificate-count :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-certificate-count :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
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

/* 工具栏 */
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
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }
</style>
