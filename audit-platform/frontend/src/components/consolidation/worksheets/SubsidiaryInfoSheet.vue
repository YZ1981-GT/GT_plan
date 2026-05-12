<template>
  <div ref="sheetRef" class="ws-sheet" :class="{ 'gt-fullscreen': isFullscreen }">
    <div class="ws-sheet-header">
      <h3>子企业基本信息表</h3>
      <div class="ws-sheet-actions">
        <el-tooltip :content="isFullscreen ? '退出全屏' : '全屏编辑'" placement="top">
          <el-button size="small" @click="toggleFullscreen">
            {{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}
          </el-button>
        </el-tooltip>
        <span class="ws-btn-sep"></span>
        <el-button size="small" @click="$emit('open-formula', 'consol_info')">ƒx 公式</el-button>
        <span class="ws-btn-sep"></span>
        <el-button size="small" @click="exportTemplate">📥 导出模板</el-button>
        <el-button size="small" @click="exportData">📤 导出数据</el-button>
        <el-button size="small" @click="triggerImport">📤 导入Excel</el-button>
        <span class="ws-btn-sep"></span>
        <el-button size="small" type="primary" @click="addRow">+ 新增子企业</el-button>
        <el-button size="small" type="danger" :disabled="!selectedRows.length" @click="batchDelete">
          删除{{ selectedRows.length ? `(${selectedRows.length})` : '' }}
        </el-button>
        <span class="ws-btn-sep"></span>
        <el-button size="small" @click="$emit('save', rows)">💾 保存</el-button>
      </div>
    </div>
    <div class="ws-tip" v-show="!isFullscreen">
      <el-icon :size="14" style="color:#e6a23c;flex-shrink:0;margin-top:1px"><WarningFilled /></el-icon>
      <span>填写"持股比例变动"为<b>是</b>并设置<b>变动次数（1~3）</b>后，将自动弹出对应的股比变动明细表。核算科目决定投资明细归属哪张表。支持导出模板填写后导入，导入时自动读取<b>"数据填写"</b>工作表，请勿修改sheet名称。</span>
    </div>

    <el-table ref="tableRef" :data="rows" border size="small" class="ws-table"
      :max-height="isFullscreen ? 'calc(100vh - 80px)' : 'calc(100vh - 280px)'"
      :header-cell-style="headerStyle" :cell-style="cellStyle"
      @selection-change="onSelectionChange">
      <!-- 多选 -->
      <el-table-column type="selection" width="36" fixed align="center" />
      <!-- 序号 -->
      <el-table-column type="index" label="序号" width="50" fixed align="center" class-name="ws-col-index" />

      <!-- 企业名称 -->
      <el-table-column prop="company_name" label="子企业名称" min-width="160" fixed>
        <template #default="{ row }">
          <el-input v-model="row.company_name" size="small" placeholder="输入企业名称" />
        </template>
      </el-table-column>

      <!-- 企业代码 -->
      <el-table-column prop="company_code" label="企业代码" width="100">
        <template #default="{ row }">
          <el-input v-model="row.company_code" size="small" />
        </template>
      </el-table-column>

      <!-- 上级单位代码 -->
      <el-table-column prop="parent_code" label="上级单位代码" width="120">
        <template #header>
          <span>上级单位代码<br/><small style="color:#999">（构建树形）</small></span>
        </template>
        <template #default="{ row }">
          <div @click.stop @mousedown.stop>
            <el-select v-model="row.parent_code" size="small" style="width:100%" placeholder="选择上级" filterable clearable>
              <el-option v-for="c in getOtherCompaniesWithCode(row)" :key="c.code" :label="`${c.name} (${c.code})`" :value="c.code" />
            </el-select>
          </div>
        </template>
      </el-table-column>

      <!-- 最终控制方 -->
      <el-table-column prop="ultimate_controller" label="最终控制方" width="130">
        <template #default="{ row }">
          <el-input v-model="row.ultimate_controller" size="small" placeholder="如 集团公司" />
        </template>
      </el-table-column>

      <!-- 最终控制方代码 -->
      <el-table-column prop="ultimate_controller_code" label="控制方代码" width="100">
        <template #default="{ row }">
          <el-input v-model="row.ultimate_controller_code" size="small" placeholder="如 ROOT" />
        </template>
      </el-table-column>

      <!-- 核算科目 -->
      <el-table-column prop="account_subject" label="核算科目" width="140">
        <template #header>
          <span>核算科目<br/><small style="color:#999">（长投、可供、交易性等）</small></span>
        </template>
        <template #default="{ row }">
          <div @click.stop @mousedown.stop>
            <el-select v-model="row.account_subject" size="small" style="width:100%" placeholder="请选择">
              <el-option v-for="o in accountSubjectOptions" :key="o" :label="o" :value="o" />
            </el-select>
          </div>
        </template>
      </el-table-column>

      <!-- 核算方式 -->
      <el-table-column prop="accounting_method" label="核算方式" width="100">
        <template #header>
          <span>核算方式<br/><small style="color:#999">（成本法、权益法）</small></span>
        </template>
        <template #default="{ row }">
          <div @click.stop @mousedown.stop>
            <el-select v-model="row.accounting_method" size="small" style="width:100%" placeholder="请选择">
              <el-option v-for="o in accountingMethodOptions" :key="o" :label="o" :value="o" />
            </el-select>
          </div>
        </template>
      </el-table-column>

      <!-- 持股类型 -->
      <el-table-column prop="holding_type" label="持股类型" width="90" align="center">
        <template #header>
          <span>持股类型<br/><small style="color:#999">（直接/间接）</small></span>
        </template>
        <template #default="{ row }">
          <div @click.stop @mousedown.stop>
            <el-select v-model="row.holding_type" size="small" style="width:100%" placeholder="请选择">
              <el-option label="直接" value="直接" />
              <el-option label="间接" value="间接" />
            </el-select>
          </div>
        </template>
      </el-table-column>

      <!-- 间接持股方 -->
      <el-table-column prop="indirect_holder" label="间接持股方" width="130">
        <template #header>
          <span>间接持股方<br/><small style="color:#999">（通过谁持有）</small></span>
        </template>
        <template #default="{ row }">
          <div v-if="row.holding_type === '间接'" @click.stop @mousedown.stop>
            <el-select v-model="row.indirect_holder" size="small" style="width:100%" placeholder="选择持股方" filterable>
              <el-option v-for="c in getOtherCompanies(row)" :key="c" :label="c" :value="c" />
            </el-select>
          </div>
          <span v-else style="color:#ccc;font-size:11px">—</span>
        </template>
      </el-table-column>

      <!-- 持股比例变动 -->
      <el-table-column label="持股比例变动情况" align="center">
        <el-table-column prop="share_changed" label="是否变动" width="90" align="center">
          <template #header>
            <el-tooltip content="选择'是'后可设置变动次数，触发股比变动明细表弹窗" placement="top">
              <span style="cursor:help;border-bottom:1px dashed #999">是否变动</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <div @click.stop @mousedown.stop>
              <el-select v-model="row.share_changed" size="small" style="width:100%"
                @change="onShareChangedUpdate(row)">
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="change_times" label="变动次数" width="90" align="center">
          <template #header>
            <el-tooltip content="设置1~3次，将弹出对应的股比变动明细表" placement="top">
              <span style="cursor:help;border-bottom:1px dashed #999">变动次数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <div @click.stop @mousedown.stop>
              <el-select v-model="row.change_times" size="small" style="width:100%" placeholder="次数"
                :disabled="row.share_changed !== '是'" @change="onChangeTimesUpdate(row)">
                <el-option :label="'1次'" :value="1" />
                <el-option :label="'2次'" :value="2" />
                <el-option :label="'3次'" :value="3" />
              </el-select>
            </div>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 当期新增 -->
      <el-table-column label="当期新增" align="center">
        <el-table-column prop="acquisition_date" label="购买日" width="120">
          <template #default="{ row }">
            <el-date-picker v-model="row.acquisition_date" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%" />
          </template>
        </el-table-column>
        <el-table-column prop="merge_type" label="合并类型" width="90" align="center">
          <template #default="{ row }">
            <div @click.stop @mousedown.stop>
              <el-select v-model="row.merge_type" size="small" style="width:100%" clearable>
                <el-option label="同控" value="同控" />
                <el-option label="非同控" value="非同控" />
              </el-select>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="first_consol_date" label="首次合并日" width="120">
          <template #default="{ row }">
            <el-date-picker v-model="row.first_consol_date" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:100%" />
          </template>
        </el-table-column>

        <!-- 涉及合并 -->
        <el-table-column label="涉及合并" align="center">
          <el-table-column label="非同一控制首次合并" align="center">
            <el-table-column prop="non_common_cost" label="投资成本" width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-model="row.non_common_cost" size="small" :precision="2" :controls="false" style="width:100%" />
              </template>
            </el-table-column>
            <el-table-column prop="non_common_ratio" label="持股比例" width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-model="row.non_common_ratio" size="small" :precision="2" :controls="false" style="width:100%">
                  <template #suffix>%</template>
                </el-input-number>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="同一控制首次合并" align="center">
            <el-table-column prop="common_cost" label="投资成本" width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-model="row.common_cost" size="small" :precision="2" :controls="false" style="width:100%" />
              </template>
            </el-table-column>
            <el-table-column prop="common_ratio" label="持股比例" width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-model="row.common_ratio" size="small" :precision="2" :controls="false" style="width:100%" />
              </template>
            </el-table-column>
          </el-table-column>
        </el-table-column>

        <!-- 不涉及合并 -->
        <el-table-column label="不涉及合并" align="center">
          <el-table-column prop="no_consol_cost" label="投资成本" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.no_consol_cost" size="small" :precision="2" :controls="false" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="no_consol_ratio" label="持股比例" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.no_consol_ratio" size="small" :precision="2" :controls="false" style="width:100%" />
            </template>
          </el-table-column>
        </el-table-column>
      </el-table-column>

      <!-- 当期减少 -->
      <el-table-column label="当期减少" align="center">
        <el-table-column label="合并范围内投资情况" align="center">
          <el-table-column prop="disposal_date" label="首次出表日" width="120">
            <template #default="{ row }">
              <el-date-picker v-model="row.disposal_date" type="date" size="small"
                value-format="YYYY-MM-DD" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="disposal_amount" label="投资减少金额" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.disposal_amount" size="small" :precision="2" :controls="false" style="width:100%" />
            </template>
          </el-table-column>
          <el-table-column prop="disposal_ratio" label="持股比例" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.disposal_ratio" size="small" :precision="2" :controls="false" style="width:100%" />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="出表日前减持" align="center">
          <el-table-column prop="pre_disposal_reduce" label="是否有减持" width="80" align="center">
            <template #default="{ row }">
              <div @click.stop @mousedown.stop>
                <el-select v-model="row.pre_disposal_reduce" size="small" style="width:100%" clearable>
                  <el-option label="是" value="是" />
                  <el-option label="否" value="否" />
                </el-select>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="pre_disposal_times" label="减持次数" width="80" align="center">
            <template #default="{ row }">
              <el-input-number v-model="row.pre_disposal_times" size="small" :min="0" :controls="false" style="width:100%" />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="出表日后减持" align="center">
          <el-table-column prop="post_disposal_reduce" label="是否有减持" width="80" align="center">
            <template #default="{ row }">
              <div @click.stop @mousedown.stop>
                <el-select v-model="row.post_disposal_reduce" size="small" style="width:100%" clearable>
                  <el-option label="是" value="是" />
                  <el-option label="否" value="否" />
                </el-select>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="post_disposal_times" label="减持次数" width="80" align="center">
            <template #default="{ row }">
              <el-input-number v-model="row.post_disposal_times" size="small" :min="0" :controls="false" style="width:100%" />
            </template>
          </el-table-column>
        </el-table-column>
      </el-table-column>

    </el-table>

    <!-- 通用导入预览弹窗 -->
    <ExcelImportPreviewDialog
      ref="importDialogRef"
      v-model:visible="importDialogVisible"
      title="导入子企业信息"
      :expected-columns="EXPECTED_IMPORT_COLS"
      sheet-name="数据填写"
      :skip-rows="3"
      skip-example-prefix="示例"
      :alert-text="importAlertText"
      :allow-error-rows="true"
      @confirm="onImportConfirm"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { confirmBatch } from '@/utils/confirm'
import { useFullscreen } from '@/composables/useFullscreen'
import { fmtAmount, fmtPercent } from '@/utils/formatters'
import { useExcelIO } from '@/composables/useExcelIO'
import ExcelImportPreviewDialog from '@/components/common/ExcelImportPreviewDialog.vue'

interface SubsidiaryInfoRow {
  company_name: string
  company_code: string
  parent_code: string
  ultimate_controller: string
  ultimate_controller_code: string
  account_subject: string
  accounting_method: string
  holding_type: string
  indirect_holder: string
  share_changed: string
  change_times: number
  acquisition_date: string
  merge_type: string
  first_consol_date: string
  non_common_cost: number | null
  non_common_ratio: number | null
  common_cost: number | null
  common_ratio: number | null
  no_consol_cost: number | null
  no_consol_ratio: number | null
  disposal_date: string
  disposal_amount: number | null
  disposal_ratio: number | null
  pre_disposal_reduce: string
  pre_disposal_times: number | null
  post_disposal_reduce: string
  post_disposal_times: number | null
}

const props = defineProps<{
  modelValue: SubsidiaryInfoRow[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: SubsidiaryInfoRow[]): void
  (e: 'save', v: SubsidiaryInfoRow[]): void
  (e: 'open-share-change', row: SubsidiaryInfoRow, times: number): void
  (e: 'open-formula', sheetKey: string): void
}>()

const rows = ref<SubsidiaryInfoRow[]>([...props.modelValue])

// 防止 watch 循环：只在外部真正变化时同步
let internalUpdate = false
watch(() => props.modelValue, (v) => {
  if (!internalUpdate) {
    rows.value = v
  }
}, { deep: true })
watch(rows, (v) => {
  internalUpdate = true
  emit('update:modelValue', v)
  nextTick(() => { internalUpdate = false })
}, { deep: true })

const accountSubjectOptions = ['长期股权投资', '可供出售金融资产', '交易性金融资产', '其他权益工具投资', '其他非流动金融资产', '其他非流动资产']
const accountingMethodOptions = ['成本法', '权益法', '公允价值']

// 间接持股方下拉选项：排除当前行自己的企业名
function getOtherCompanies(currentRow: SubsidiaryInfoRow): string[] {
  return rows.value
    .filter(r => r.company_name && r.company_name !== currentRow.company_name)
    .map(r => r.company_name)
    .filter((v, i, a) => a.indexOf(v) === i) // 去重
}

// 上级单位下拉选项：排除当前行自己
function getOtherCompaniesWithCode(currentRow: SubsidiaryInfoRow): { name: string; code: string }[] {
  return rows.value
    .filter(r => r.company_name && r.company_code && r.company_code !== currentRow.company_code)
    .map(r => ({ name: r.company_name, code: r.company_code }))
    .filter((v, i, a) => a.findIndex(x => x.code === v.code) === i) // 去重
}

function createEmptyRow(): SubsidiaryInfoRow {
  return {
    company_name: '', company_code: '', parent_code: '',
    ultimate_controller: '', ultimate_controller_code: '',
    account_subject: '',
    accounting_method: '', holding_type: '直接', indirect_holder: '', share_changed: '否', change_times: 0,
    acquisition_date: '', merge_type: '', first_consol_date: '',
    non_common_cost: null, non_common_ratio: null,
    common_cost: null, common_ratio: null,
    no_consol_cost: null, no_consol_ratio: null,
    disposal_date: '', disposal_amount: null, disposal_ratio: null,
    pre_disposal_reduce: '', pre_disposal_times: null,
    post_disposal_reduce: '', post_disposal_times: null,
  }
}

function addRow() { rows.value.push(createEmptyRow()) }
function _removeRow(idx: number) { rows.value.splice(idx, 1) }

const tableRef = ref<any>(null)
const selectedRows = ref<SubsidiaryInfoRow[]>([])

function onSelectionChange(selection: SubsidiaryInfoRow[]) {
  selectedRows.value = selection
}

async function batchDelete() {
  if (!selectedRows.value.length) return
  try {
    await confirmBatch('删除', selectedRows.value.length)
    const toDelete = new Set(selectedRows.value)
    rows.value = rows.value.filter(r => !toDelete.has(r))
    selectedRows.value = []
  } catch { /* cancelled */ }
}

function onChangeTimesUpdate(row: SubsidiaryInfoRow) {
  if (row.share_changed === '是' && row.change_times > 0 && row.company_name) {
    emit('open-share-change', row, row.change_times)
  }
}

function onShareChangedUpdate(row: SubsidiaryInfoRow) {
  if (row.share_changed !== '是') {
    row.change_times = 0
  }
}

// ─── 导出模板 / 导入 Excel ────────────────────────────────────────────────────
const importDialogRef = ref<InstanceType<typeof ExcelImportPreviewDialog> | null>(null)
const importDialogVisible = ref(false)

// 模板列定义 — 简短表头 + 说明分开
const TEMPLATE_COLS = [
  { key: 'company_name', header: '子企业名称', note: '必填，合并范围内的子企业全称', example: '重庆XX有限公司' },
  { key: 'company_code', header: '企业代码', note: '必填，企业唯一编码', example: 'CQ001' },
  { key: 'parent_code', header: '上级单位代码', note: '选填，上级单位的企业代码，用于构建树形层级', example: 'ROOT' },
  { key: 'ultimate_controller', header: '最终控制方', note: '选填，最终控制方名称', example: '重庆医药集团' },
  { key: 'ultimate_controller_code', header: '控制方代码', note: '选填，最终控制方企业代码', example: 'ROOT' },
  { key: 'account_subject', header: '核算科目', note: '必填，可选值：长期股权投资/可供出售金融资产/交易性金融资产/其他权益工具投资/其他非流动金融资产/其他非流动资产', example: '长期股权投资' },
  { key: 'accounting_method', header: '核算方式', note: '必填，可选值：成本法/权益法/公允价值', example: '成本法' },
  { key: 'holding_type', header: '持股类型', note: '必填，可选值：直接/间接', example: '直接' },
  { key: 'indirect_holder', header: '间接持股方', note: '间接持股时填写，通过哪家企业间接持有', example: '' },
  { key: 'share_changed', header: '是否变动', note: '必填，填"是"或"否"', example: '否' },
  { key: 'change_times', header: '变动次数', note: '持股比例变动次数，1/2/3。仅"是否变动"为"是"时填写', example: '' },
  { key: 'acquisition_date', header: '购买日', note: '当期新增时填写，格式 YYYY-MM-DD', example: '' },
  { key: 'merge_type', header: '合并类型', note: '当期新增时填写，可选值：同控/非同控', example: '' },
  { key: 'first_consol_date', header: '首次合并日', note: '当期新增时填写，格式 YYYY-MM-DD', example: '' },
  { key: 'non_common_cost', header: '非同控-投资成本', note: '非同一控制下首次合并的投资成本金额', example: '' },
  { key: 'non_common_ratio', header: '非同控-持股比例', note: '非同一控制下首次合并的持股比例（%）', example: '51' },
  { key: 'common_cost', header: '同控-投资成本', note: '同一控制下首次合并的投资成本金额', example: '' },
  { key: 'common_ratio', header: '同控-持股比例', note: '同一控制下首次合并的持股比例（%）', example: '' },
  { key: 'no_consol_cost', header: '不涉及合并-投资成本', note: '不涉及合并的投资成本金额', example: '' },
  { key: 'no_consol_ratio', header: '不涉及合并-持股比例', note: '不涉及合并的持股比例（%）', example: '' },
  { key: 'disposal_date', header: '首次出表日', note: '当期减少时填写，格式 YYYY-MM-DD', example: '' },
  { key: 'disposal_amount', header: '投资减少金额', note: '当期减少的投资金额', example: '' },
  { key: 'disposal_ratio', header: '处置-持股比例', note: '处置后的持股比例（%）', example: '' },
]

// 导入时期望的列名（用于列映射校验）
const EXPECTED_IMPORT_COLS = TEMPLATE_COLS.map(c => c.header)

// 导入提示文字
const importAlertText = '请使用\u201c导出模板\u201d下载的模板填写数据。系统将自动读取<b>\u201c数据填写\u201d</b>工作表（请勿修改sheet名称），数据从第4行开始。导入将<b>追加</b>到现有数据后面，示例行自动跳过。'

const { exportTemplate: _exportTemplate, exportData: _exportData } = useExcelIO()

async function exportTemplate() {
  const existing = rows.value.filter(r => r.company_name).map(r =>
    TEMPLATE_COLS.map(c => (r as any)[c.key] ?? '')
  )
  await _exportTemplate({
    columns: TEMPLATE_COLS,
    fileName: '合并范围子企业基本信息表_模板.xlsx',
    includeInstructions: true,
    instructionTitle: '合并范围内的子企业基本信息表 — 填写说明',
    instructionRows: [
      ['核算科目、核算方式、是否变动、合并类型等字段请严格按可选值填写'],
      ['日期格式统一为 YYYY-MM-DD（如 2025-06-30）'],
      ['持股比例填数字（如51表示51%），不要带%号'],
    ],
    categoryRow: [
      '基本信息', '', '', '', '', '', '', '', '持股比例变动', '', '当期新增', '', '',
      '涉及合并-非同控', '', '涉及合并-同控', '', '不涉及合并', '',
      '当期减少', '', '',
    ],
    categoryMerges: [
      { s: { r: 0, c: 0 }, e: { r: 0, c: 8 } },
      { s: { r: 0, c: 9 }, e: { r: 0, c: 10 } },
      { s: { r: 0, c: 11 }, e: { r: 0, c: 13 } },
      { s: { r: 0, c: 14 }, e: { r: 0, c: 15 } },
      { s: { r: 0, c: 16 }, e: { r: 0, c: 17 } },
      { s: { r: 0, c: 18 }, e: { r: 0, c: 19 } },
      { s: { r: 0, c: 20 }, e: { r: 0, c: 22 } },
    ],
    existingData: existing.length > 0 ? existing : undefined,
    exampleRows: [
      ['示例公司A', 'A001', 'ROOT', '集团公司', 'ROOT', '长期股权投资', '成本法', '直接', '', '否', '', '', '', '', '', '', '', '', '', '', '', '', ''],
      ['示例公司A', 'A001', 'ROOT', '集团公司', 'ROOT', '长期股权投资', '权益法', '间接', '公司B', '否', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ],
  })
}

async function exportData() {
  await _exportData({
    data: rows.value.filter(r => r.company_name),
    columns: TEMPLATE_COLS,
    sheetName: '基本信息表',
    fileName: '基本信息表_数据.xlsx',
  })
}

function triggerImport() {
  importDialogRef.value?.selectFile()
}

/** 导入确认回调：将通用弹窗返回的 Record 数组转为 SubsidiaryInfoRow 并追加 */
function onImportConfirm(data: Record<string, any>[]) {
  const parsed: SubsidiaryInfoRow[] = data.map(r => ({
    company_name: String(r['子企业名称'] ?? '').trim(),
    company_code: String(r['企业代码'] ?? '').trim(),
    parent_code: String(r['上级单位代码'] ?? '').trim(),
    ultimate_controller: String(r['最终控制方'] ?? '').trim(),
    ultimate_controller_code: String(r['控制方代码'] ?? '').trim(),
    account_subject: String(r['核算科目'] ?? '').trim(),
    accounting_method: String(r['核算方式'] ?? '').trim(),
    holding_type: String(r['持股类型'] ?? '直接').trim(),
    indirect_holder: String(r['间接持股方'] ?? '').trim(),
    share_changed: String(r['是否变动'] ?? '否').trim(),
    change_times: Number(r['变动次数']) || 0,
    acquisition_date: String(r['购买日'] ?? '').trim(),
    merge_type: String(r['合并类型'] ?? '').trim(),
    first_consol_date: String(r['首次合并日'] ?? '').trim(),
    non_common_cost: r['非同控-投资成本'] != null ? Number(r['非同控-投资成本']) : null,
    non_common_ratio: r['非同控-持股比例'] != null ? Number(r['非同控-持股比例']) : null,
    common_cost: r['同控-投资成本'] != null ? Number(r['同控-投资成本']) : null,
    common_ratio: r['同控-持股比例'] != null ? Number(r['同控-持股比例']) : null,
    no_consol_cost: r['不涉及合并-投资成本'] != null ? Number(r['不涉及合并-投资成本']) : null,
    no_consol_ratio: r['不涉及合并-持股比例'] != null ? Number(r['不涉及合并-持股比例']) : null,
    disposal_date: String(r['首次出表日'] ?? '').trim(),
    disposal_amount: r['投资减少金额'] != null ? Number(r['投资减少金额']) : null,
    disposal_ratio: r['处置-持股比例'] != null ? Number(r['处置-持股比例']) : null,
    pre_disposal_reduce: '',
    pre_disposal_times: null,
    post_disposal_reduce: '',
    post_disposal_times: null,
  }))

  // 追加到现有数据（去掉空行）
  const nonEmpty = rows.value.filter(r => r.company_name)
  rows.value = [...nonEmpty, ...parsed]
  ElMessage.success(`已导入 ${parsed.length} 条数据`)
}

const headerStyle = { background: '#f0edf5', fontSize: '12px', color: '#333', padding: '2px 0' }
const cellStyle = { padding: '2px 4px', fontSize: '12px' }

// ─── 全屏 ─────────────────────────────────────────────────────────────────────
const sheetRef = ref<HTMLElement | null>(null)
const { isFullscreen, toggleFullscreen } = useFullscreen()
</script>

<style scoped>
.ws-sheet { padding: 0; position: relative; }
.ws-sheet-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; padding: 4px 0; flex-wrap: wrap; gap: 6px;
}
.ws-sheet-header h3 { margin: 0; font-size: 14px; color: #333; white-space: nowrap; }
.ws-sheet-actions { display: flex; gap: 8px; }
.ws-tip {
  display: flex; align-items: flex-start; gap: 6px; padding: 6px 10px; margin-bottom: 10px;
  background: #fdf6ec; border-radius: 6px; font-size: 12px; color: #8a6d3b; line-height: 1.5;
  border: 1px solid #faecd8;
}
.ws-tip b { color: #e6a23c; }
.ws-table :deep(.el-input__inner) { text-align: right; }
.ws-table :deep(.el-input-number) { width: 100%; }
.ws-table :deep(.el-input-number .el-input__inner) { text-align: right; }
.ws-table :deep(.el-table__body .ws-col-index .cell) { white-space: nowrap; }
.ws-btn-sep { width: 1px; height: 18px; background: #ddd; margin: 0 2px; flex-shrink: 0; }
</style>
