<template>
  <div class="c24-anomaly-account">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="methodology-bar" />
      <p>C24-4 异常账户测试：提取分录中所有操作用户，统计编制/过账/审核数量，与人员清单核对，识别异常账户。</p>
    </div>

    <!-- 异常账户结果表 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">异常账户分析</span>
        <div class="section-actions">
          <el-dropdown v-if="!isReadonly && rows.length > 0" trigger="click" @command="handleImportExport">
            <el-button size="small">导入导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="template">导出模板</el-dropdown-item>
                <el-dropdown-item command="export">导出数据</el-dropdown-item>
                <el-dropdown-item command="import" divided>导入数据</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <input ref="fileInputRef" type="file" accept=".xlsx,.xls,.csv" style="display:none" @change="onFileSelected" />
        </div>
      </div>
      <el-alert v-if="!hasData" type="info" :closable="false" show-icon style="margin-bottom: 12px;">
        尚未导入分录数据，请先导入会计分录。
      </el-alert>

      <el-table v-if="rows.length > 0" :data="rows" border size="small" class="c24-table" max-height="500">
        <el-table-column label="操作用户" prop="user" width="100" show-overflow-tooltip />
        <el-table-column label="用户岗位" min-width="100">
          <template #default="{ row, $index }">
            <el-input :model-value="row.role" :disabled="isReadonly" size="small" placeholder="岗位" @input="onRowChange($index, 'role', $event)" />
          </template>
        </el-table-column>
        <el-table-column label="编制数" width="90" align="center">
          <template #header>
            <el-tooltip content="该用户作为制单人/编制人的分录数量" placement="top"><span>编制数</span></el-tooltip>
          </template>
          <template #default="{ row }"><span class="formula-cell" title="来源：分录统计(preparer)">{{ row.prepareCount }}</span></template>
        </el-table-column>
        <el-table-column label="过账数" width="90" align="center">
          <template #header>
            <el-tooltip content="该用户作为过账人的分录数量" placement="top"><span>过账数</span></el-tooltip>
          </template>
          <template #default="{ row }"><span class="formula-cell" title="来源：分录统计(poster)">{{ row.postCount }}</span></template>
        </el-table-column>
        <el-table-column label="审核数" width="90" align="center">
          <template #header>
            <el-tooltip content="该用户作为审核人的分录数量" placement="top"><span>审核数</span></el-tooltip>
          </template>
          <template #default="{ row }"><span class="formula-cell" title="来源：分录统计(reviewer)">{{ row.reviewCount }}</span></template>
        </el-table-column>
        <el-table-column label="在清单中" width="90" align="center">
          <template #header>
            <el-tooltip content="是否在C23人员清单中登记" placement="top"><span>在清单中</span></el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tag :type="row.inList ? 'success' : 'warning'" size="small">{{ row.inList ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="110" align="center">
          <template #header>
            <el-tooltip content="审计人员判断该操作用户是否存在异常" placement="top"><span>是否异常</span></el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-select :model-value="row.abnormal" :disabled="isReadonly" size="small" placeholder="请判断" @change="onRowChange($index, 'abnormal', $event)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="异常说明" min-width="160" show-overflow-tooltip>
          <template #default="{ row, $index }">
            <el-input :model-value="row.note" :disabled="isReadonly" size="small" placeholder="异常说明" @input="onRowChange($index, 'note', $event)" />
          </template>
        </el-table-column>
        <el-table-column label="结论" width="130">
          <template #default="{ row, $index }">
            <el-select :model-value="row.conclusion" :disabled="isReadonly" size="small" placeholder="结论" @change="onRowChange($index, 'conclusion', $event)">
              <el-option label="正常" value="正常" />
              <el-option label="异常-已解释" value="异常-已解释" />
              <el-option label="异常-错报" value="异常-错报" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="120" show-overflow-tooltip>
          <template #default="{ row, $index }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
            <el-input
              v-else
              :model-value="row.indexRef || ''"
              :disabled="isReadonly"
              size="small"
              placeholder="索引号"
              @input="onRowChange($index, 'indexRef', $event)"
            />
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 测试结论 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">测试结论</span>
        <el-button v-if="!isReadonly" size="small" @click="$emit('ai-suggest', 'C24-4-conclusion')">AI 辅助</el-button>
      </div>
      <el-input
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :model-value="conclusion"
        :disabled="isReadonly"
        placeholder="请填写异常账户测试结论"
        @input="$emit('update:conclusion', $event)"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { exportMultiSheetData, readSheetObjects } from '@/composables/useExcelIO'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

export interface AccountRow {
  user: string
  role: string
  prepareCount: number
  postCount: number
  reviewCount: number
  inList: boolean
  abnormal: string
  note: string
  conclusion: string
  indexRef?: string
}

const props = defineProps<{
  rows: AccountRow[]
  hasData: boolean
  conclusion: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'update:conclusion', val: string): void
  (e: 'update:row', index: number, field: string, value: string): void
  (e: 'ai-suggest', fieldId: string): void
}>()

const fileInputRef = ref<HTMLInputElement | null>(null)

function onRowChange(index: number, field: string, value: string) {
  emit('update:row', index, field, value)
}

// ─── 导入导出 ─────────────────────────────────────────────────────────────────

function handleImportExport(command: string) {
  if (command === 'template') exportTemplate()
  else if (command === 'export') exportToExcel()
  else if (command === 'import') fileInputRef.value?.click()
}

/** 导出空白模板（含编制说明） */
async function exportTemplate() {

  // Sheet1: 编制说明
  const guideData = [
    ['C24-4 异常账户测试 — 导入模板编制说明'],
    [''],
    ['一、用途'],
    ['本模板用于批量填写操作用户的岗位信息、异常判断及说明。'],
    ['导出模板 → 离线填写 → 导入回系统，系统按"操作用户"列自动匹配回填。'],
    [''],
    ['二、填写规则'],
    ['列名', '是否必填', '填写说明'],
    ['操作用户', '系统生成', '由系统自动提取，不可修改。导入时按此列匹配。'],
    ['用户岗位', '建议填写', '该用户在被审计单位的岗位/职务，如：会计主管、出纳、财务经理等。'],
    ['编制数', '系统计算', '该用户作为制单人（preparer）的分录条数，不可修改。'],
    ['过账数', '系统计算', '该用户作为过账人的分录条数，不可修改。'],
    ['审核数', '系统计算', '该用户作为审核人的分录条数，不可修改。'],
    ['在清单中', '系统判断', '是否在 C23 人员清单中登记，不可修改。'],
    ['是否异常', '必填', '审计判断：填"是"或"否"。不在清单中/职责不相容/非工作时间大量操作 → 异常。'],
    ['异常说明', '异常时填写', '对异常情况的具体描述，如"该用户不在授权人员清单中"。'],
    ['结论', '必填', '填写："正常" / "异常-已解释" / "异常-错报"。'],
    ['索引号', '选填', '关联底稿索引号，如 A13（错报汇总）。'],
    [''],
    ['三、异常判断标准参考'],
    ['1. 操作用户不在经授权的人员清单中 → 异常'],
    ['2. 同一人员同时担任编制和审核（职责不相容） → 异常'],
    ['3. 非财务人员进行会计分录操作 → 异常'],
    ['4. 已离职人员仍有操作记录 → 异常'],
    ['5. 系统账户/共享账户操作量异常大 → 需关注'],
    [''],
    ['四、注意事项'],
    ['- 导入时仅回填"用户岗位/是否异常/异常说明/结论/索引号"五列，统计列由系统计算不覆盖。'],
    ['- "操作用户"列为匹配键，不要修改或删除。'],
    ['- 如导入的用户名与系统中不完全一致则无法匹配，请确保名称相同。'],
  ]


  // Sheet2: 数据模板（带当前用户列表，可编辑列为空）
  const headers = ['操作用户', '用户岗位', '编制数', '过账数', '审核数', '在清单中', '是否异常', '异常说明', '结论', '索引号']
  const data = props.rows.map(r => [
    r.user, '', r.prepareCount, r.postCount, r.reviewCount,
    r.inList ? '是' : '否', '', '', '', '',
  ])
  // 走 useExcelIO 单一入口（B7 批）。本文件原本是全库**唯一的静态 import**
  // （`import * as XLSX from 'xlsx'`），会把 xlsx 打进主包；收敛后变成入口内的动态
  // import，顺带修掉这个体积问题。
  await exportMultiSheetData({
    sheets: [
      { sheetName: '编制说明', rows: guideData, colWidths: [{ wch: 16 }, { wch: 14 }, { wch: 60 }] },
      {
        sheetName: 'C24-4异常账户',
        rows: [headers, ...data],
        colWidths: headers.map((h, i) => ({ wch: Math.max(h.length * 2, ...(data.map(r => String(r[i] ?? '').length)), 10) })),
      },
    ],
    fileName: `C24-4_异常账户_导入模板.xlsx`,
    applyStyles: false,
    successMessage: false,
  })
  ElMessage.success('模板导出成功，请参照"编制说明"sheet填写后导入')
}

/** 导出当前账户列表为 Excel */
async function exportToExcel() {
  const headers = ['操作用户', '用户岗位', '编制数', '过账数', '审核数', '在清单中', '是否异常', '异常说明', '结论', '索引号']
  const data = props.rows.map(r => [
    r.user, r.role, r.prepareCount, r.postCount, r.reviewCount,
    r.inList ? '是' : '否', r.abnormal, r.note, r.conclusion, r.indexRef || '',
  ])
  await exportMultiSheetData({
    sheets: [{
      sheetName: 'C24-4异常账户',
      rows: [headers, ...data],
      // 列宽自适应（原样保留：按表头与数据的最大字符数算）
      colWidths: headers.map((h, i) => ({ wch: Math.max(h.length * 2, ...(data.map(r => String(r[i] ?? '').length)), 8) })),
    }],
    fileName: `C24-4_异常账户分析_${new Date().toISOString().slice(0, 10)}.xlsx`,
    applyStyles: false,
    successMessage: false,
  })
  ElMessage.success('导出成功')
}

/** 导入 Excel 回填用户编辑字段（岗位/异常/说明/结论/索引号） */
async function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''

  try {
    // 走 useExcelIO 单一入口（B7 批）。原先取第一个 sheet + sheet_to_json 对象模式无选项。
    const { rows: jsonRows } = await readSheetObjects<Record<string, any>>(file)

    if (jsonRows.length === 0) {
      ElMessage.warning('导入文件为空')
      return
    }

    // 按"操作用户"匹配回填
    let matched = 0
    for (const importRow of jsonRows) {
      const user = String(importRow['操作用户'] || '').trim()
      if (!user) continue
      const idx = props.rows.findIndex(r => r.user === user)
      if (idx < 0) continue

      // 回填可编辑字段
      if (importRow['用户岗位'] != null) emit('update:row', idx, 'role', String(importRow['用户岗位']))
      if (importRow['是否异常'] != null) emit('update:row', idx, 'abnormal', String(importRow['是否异常']))
      if (importRow['异常说明'] != null) emit('update:row', idx, 'note', String(importRow['异常说明']))
      if (importRow['结论'] != null) emit('update:row', idx, 'conclusion', String(importRow['结论']))
      if (importRow['索引号'] != null) emit('update:row', idx, 'indexRef', String(importRow['索引号']))
      matched++
    }

    if (matched > 0) {
      ElMessage.success(`成功匹配并导入 ${matched} 个用户的信息`)
    } else {
      ElMessage.warning('未匹配到任何用户（请确认"操作用户"列与当前列表一致）')
    }
  } catch (err: any) {
    ElMessage.error('导入失败：' + (err?.message || '文件解析错误'))
  }
}
</script>

<style scoped>
.c24-anomaly-account { font-size: var(--wp-font-size, 13px); }
.methodology-context { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; margin-bottom: 16px; background: #fffbf0; border-radius: 4px; }
.methodology-bar { width: 3px; min-height: 20px; align-self: stretch; background: #e6a23c; border-radius: 2px; flex-shrink: 0; }
.methodology-context p { margin: 0; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.c24-section { margin-bottom: 20px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.section-actions { display: flex; gap: 8px; align-items: center; }
.section-title { font-weight: 600; font-size: 14px; color: #303133; }
.c24-table { font-size: var(--wp-font-size, 13px); }
.c24-table :deep(.el-table__header th),
.c24-table :deep(.el-table__body td),
.c24-table :deep(.cell) { font-size: var(--wp-font-size, 13px); }
.c24-table :deep(.el-table__header th .cell) { white-space: nowrap; overflow: visible; text-overflow: unset; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; color: #409eff; }
</style>
