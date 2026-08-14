<template>
  <div class="gt-confirmation-entity-verify">
    <!-- Legacy fallback -->
    <template v-if="isLegacyFormat">
      <div class="gt-confirmation-entity-verify__legacy-notice">
        <el-alert
          title="旧格式数据"
          description="当前数据非 entity-verify-v1 格式，以只读网格模式展示"
          type="info"
          show-icon
          :closable="false"
        />
      </div>
      <!-- GtGridSheet readonly fallback would render here -->
    </template>

    <!-- Modern entity-verify-v1 layout -->
    <template v-else>
      <!-- 顶部：Dashboard + 反舞弊 并排紧凑 -->
      <div class="gt-confirmation-entity-verify__top-bar">
        <EntityVerifyDashboard :metrics="progressMetrics" class="gt-confirmation-entity-verify__dashboard" />
        <div class="gt-confirmation-entity-verify__fraud-compact">
          <div class="gt-confirmation-entity-verify__fraud-header" @click="toggleFraudPanel">
            <span class="gt-confirmation-entity-verify__fraud-title">
              🛡️ 反舞弊筛查
              <el-badge v-if="totalFraudCount > 0" :value="totalFraudCount" />
            </span>
            <el-button size="small" type="warning" @click.stop="showScreeningDialog = true">
              一键筛查
            </el-button>
          </div>
          <transition name="el-collapse-transition">
            <EntityVerifyFraudPanel
              v-show="fraudExpanded"
              :row-flags="screeningResult.rowFlags"
              :cross-flags="screeningResult.crossFlags"
              :rows="rows"
            />
          </transition>
        </div>
      </div>

      <!-- 工具栏 + 视图切换 一行 -->
      <div class="gt-confirmation-entity-verify__toolbar">
        <div class="gt-confirmation-entity-verify__toolbar-left">
          <el-radio-group v-model="currentView" size="small">
            <el-radio-button value="list">列表视图</el-radio-button>
            <el-radio-button value="grid">全量表格</el-radio-button>
          </el-radio-group>
        </div>
      </div>

      <!-- List view: Master 上 + Detail 下 -->
      <div v-if="currentView === 'list'" class="gt-confirmation-entity-verify__list-view">
        <div class="gt-confirmation-entity-verify__master">
          <EntityVerifyMaster
            :rows="rows"
            :readonly="readonly"
            :selected-ids="selectedIds"
            @add="handleAdd"
            @delete="handleDelete"
            @save="handleSave"
            @import="handleImport"
            @export="handleExport"
            @export-data="handleExportData"
            @row-click="handleRowClick"
            @update:selected-ids="selectedIds = $event"
          />
        </div>
        <div class="gt-confirmation-entity-verify__detail">
          <EntityVerifyDetail
            :row="currentRow"
            :readonly="readonly"
            :dict-data="dictData"
            @update="handleFieldUpdate"
          />
        </div>
      </div>

      <!-- Grid view: 全量表格（可直接行内编辑） -->
      <div v-else class="gt-confirmation-entity-verify__grid-view">
        <div v-if="!readonly" class="gt-confirmation-entity-verify__grid-toolbar">
          <el-button type="primary" size="small" @click="handleAdd">+ 新增</el-button>
          <el-button type="success" size="small" @click="handleSave">保存</el-button>
          <el-button size="small" @click="handleImport">导入</el-button>
          <el-button size="small" @click="handleExportData">导出数据</el-button>
        </div>
        <el-table
          :data="rows"
          border
          size="small"
          :max-height="500"
          highlight-current-row
          style="width: 100%"
          class="gt-confirmation-entity-verify__full-table"
          table-layout="auto"
        >
          <el-table-column prop="seq" label="序号" min-width="45" align="center" />
          <el-table-column label="索引号" min-width="75">
            <template #default="{ row }">
              <el-input v-if="!readonly" v-model="row.confirm_index" size="small" placeholder="D0-" @change="markDirty" />
              <span v-else>{{ row.confirm_index }}</span>
            </template>
          </el-table-column>
          <el-table-column label="被询证单位" min-width="130">
            <template #default="{ row }">
              <el-input v-if="!readonly" v-model="row.entity_name" size="small" placeholder="单位名称" @change="markDirty" />
              <span v-else>{{ row.entity_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="科目" min-width="85">
            <template #default="{ row }">
              <el-select v-if="!readonly" v-model="row.account_type" size="small" placeholder="选择" filterable allow-create @change="markDirty">
                <el-option v-for="t in dictData.confirmation_account_type" :key="t" :value="t" :label="t" />
              </el-select>
              <span v-else>{{ row.account_type }}</span>
            </template>
          </el-table-column>
          <el-table-column label="企查查名称" min-width="130">
            <template #default="{ row }">
              <el-input v-if="!readonly" v-model="row.qcc_entity_name" size="small" placeholder="工商名称" @change="markDirty" />
              <span v-else>{{ row.qcc_entity_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="企查查地址" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!readonly" v-model="row.qcc_address" size="small" placeholder="注册地址" @change="markDirty" />
              <span v-else>{{ row.qcc_address }}</span>
            </template>
          </el-table-column>
          <el-table-column label="名称一致" min-width="75" align="center">
            <template #default="{ row }">
              <el-select v-if="!readonly" v-model="row.name_match" size="small" placeholder="—" @change="markDirty">
                <el-option value="consistent" label="一致" />
                <el-option value="inconsistent" label="不一致" />
                <el-option value="pending" label="待核实" />
              </el-select>
              <template v-else>
                <el-tag v-if="row.name_match === 'consistent'" type="success" size="small">一致</el-tag>
                <el-tag v-else-if="row.name_match === 'inconsistent'" type="danger" size="small">不一致</el-tag>
                <span v-else style="color:#909399;font-size:11px">待核实</span>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="地址一致" min-width="75" align="center">
            <template #default="{ row }">
              <el-select v-if="!readonly" v-model="row.address_match" size="small" placeholder="—" @change="markDirty">
                <el-option value="consistent" label="一致" />
                <el-option value="inconsistent" label="不一致" />
                <el-option value="pending" label="待核实" />
              </el-select>
              <template v-else>
                <el-tag v-if="row.address_match === 'consistent'" type="success" size="small">一致</el-tag>
                <el-tag v-else-if="row.address_match === 'inconsistent'" type="danger" size="small">不一致</el-tag>
                <span v-else style="color:#909399;font-size:11px">待核实</span>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="联系人" min-width="75">
            <template #default="{ row }">
              <el-input v-if="!readonly" v-model="row.contact_person" size="small" @change="markDirty" />
              <span v-else>{{ row.contact_person }}</span>
            </template>
          </el-table-column>
          <el-table-column label="电话" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!readonly" v-model="row.contact_phone" size="small" @change="markDirty" />
              <span v-else>{{ row.contact_phone }}</span>
            </template>
          </el-table-column>
          <el-table-column label="发函日期" min-width="95">
            <template #default="{ row }">
              <el-input v-if="!readonly" v-model="row.first_send_date" size="small" placeholder="YYYY-MM-DD" @change="markDirty" />
              <span v-else>{{ row.first_send_date }}</span>
            </template>
          </el-table-column>
          <el-table-column label="发函结果" min-width="75" align="center">
            <template #default="{ row }">
              <el-select v-if="!readonly" v-model="row.first_result" size="small" placeholder="—" @change="markDirty">
                <el-option value="送抵" label="送抵" />
                <el-option value="退回" label="退回" />
              </el-select>
              <template v-else>
                <el-tag v-if="row.first_result === '送抵'" type="success" size="small">送抵</el-tag>
                <el-tag v-else-if="row.first_result === '退回'" type="danger" size="small">退回</el-tag>
                <span v-else>—</span>
              </template>
            </template>
          </el-table-column>
          <el-table-column prop="row_status" label="状态" min-width="55" align="center">
            <template #default="{ row }">
              <span :style="{ color: row.row_status === 'fraud_flag' ? '#f56c6c' : row.row_status === 'suspect' ? '#e6a23c' : '#67c23a', fontWeight: 500, fontSize: '12px' }">
                {{ row.row_status === 'fraud_flag' ? '舞弊' : row.row_status === 'suspect' ? '疑似' : '正常' }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>

    <!-- 隐藏文件选择器 -->
    <input ref="importFileInput" type="file" accept=".xlsx,.xls,.csv" style="display:none" @change="handleImportFile" />

    <!-- 反舞弊筛查弹窗 -->
    <el-dialog v-model="showScreeningDialog" title="反舞弊筛查配置" width="680px" append-to-body>
      <!-- 步骤1：选择指标 -->
      <div v-if="screeningStep === 'config'">
        <p style="color:#606266;font-size:13px;margin:0 0 12px">
          请确认要执行的筛查指标。勾选后点击「执行筛查」，系统将对当前 {{ rows.length }} 条函证记录进行逐项比对。
        </p>

        <h4 style="margin:12px 0 8px;font-size:13px">📋 行内一致性检测（逐行比对）</h4>
        <el-table :data="screeningRuleConfig" border size="small" style="width:100%">
          <el-table-column width="50" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.enabled" />
            </template>
          </el-table-column>
          <el-table-column prop="label" label="指标名称" min-width="120" />
          <el-table-column prop="description" label="判断逻辑" min-width="200" />
          <el-table-column prop="source" label="数据来源" min-width="100" />
        </el-table>

        <h4 style="margin:16px 0 8px;font-size:13px">🔗 跨行红旗检测（整体分析）</h4>
        <el-table :data="screeningCrossConfig" border size="small" style="width:100%">
          <el-table-column width="50" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.enabled" />
            </template>
          </el-table-column>
          <el-table-column prop="label" label="指标名称" min-width="120" />
          <el-table-column prop="description" label="判断逻辑" min-width="200" />
          <el-table-column prop="relatedWp" label="关联底稿" min-width="100" />
        </el-table>
      </div>

      <!-- 步骤2：筛查结果 -->
      <div v-else class="gt-screening-result">
        <el-result
          :icon="screeningResultSummary.total > 0 ? 'warning' : 'success'"
          :title="screeningResultSummary.total > 0 ? `检出 ${screeningResultSummary.total} 项异常` : '未检出异常'"
          :sub-title="screeningResultSummary.total > 0 ? `行内异常 ${screeningResultSummary.rowCount} 条，跨行红旗 ${screeningResultSummary.crossCount} 项` : '所有启用指标均未触发，当前数据暂无舞弊迹象'"
        />

        <template v-if="screeningResultSummary.total > 0">
          <el-divider content-position="left">异常明细</el-divider>
          <el-table :data="screeningResultDetails" border size="small" style="width:100%" :max-height="260">
            <el-table-column prop="entity" label="单位" min-width="120" show-overflow-tooltip />
            <el-table-column prop="ruleLabel" label="触发指标" min-width="100" />
            <el-table-column prop="level" label="严重程度" min-width="70" align="center">
              <template #default="{ row }">
                <el-tag :type="row.level === '高' ? 'danger' : 'warning'" size="small">{{ row.level }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="suggestion" label="建议措施" min-width="160" show-overflow-tooltip />
          </el-table>
        </template>

        <el-alert
          v-if="screeningResultSummary.total > 0"
          type="info"
          :closable="false"
          show-icon
          style="margin-top:12px"
          title="后续处理"
          description="异常项已标记至对应行的「状态」列。高风险项建议记录至 D0-8 舞弊风险底稿，并在 B50 风险评估中汇总。"
        />
      </div>

      <template #footer>
        <template v-if="screeningStep === 'config'">
          <el-button @click="showScreeningDialog = false">取消</el-button>
          <el-button type="warning" @click="executeScreening">执行筛查</el-button>
        </template>
        <template v-else>
          <el-button @click="screeningStep = 'config'">返回配置</el-button>
          <el-button type="primary" @click="showScreeningDialog = false">确认关闭</el-button>
        </template>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { exportMultiSheetData, parseFile } from '@/composables/useExcelIO'
import type { EntityVerifyRow } from './entityVerifyTypes'
import { useEntityVerifyData } from './composables/useEntityVerifyData'
import { useFraudFlagDetect, type CrossRowFlag } from './composables/useFraudFlagDetect'
import { useViewMode } from './composables/useViewMode'
import EntityVerifyDashboard from './EntityVerifyDashboard.vue'
import EntityVerifyFraudPanel from './EntityVerifyFraudPanel.vue'
import EntityVerifyMaster from './EntityVerifyMaster.vue'
import EntityVerifyDetail from './EntityVerifyDetail.vue'

// ─── Props & Emits ────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId?: string
  projectId?: string
  wpCode?: string
  year?: string
  htmlData?: any
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// ─── Readonly computed ────────────────────────────────────────────────────────

const readonly = computed(() => props.readonly ?? false)

// ─── Legacy format check ──────────────────────────────────────────────────────

const isLegacyFormat = computed(() => {
  const data = props.htmlData
  return data && data._format !== 'entity-verify-v1'
})

// ─── Data composable ─────────────────────────────────────────────────────────

const {
  rows,
  isDirty,
  addRow,
  deleteRows,
  updateField,
  importRows,
  progressMetrics,
  buildPayload,
} = useEntityVerifyData({
  htmlData: () => props.htmlData,
  readonly: readonly.value,
})

// ─── Fraud detection ─────────────────────────────────────────────────────────

const { runScreening, deriveRowStatus } = useFraudFlagDetect(rows)

const screeningResult = reactive<{
  rowFlags: Map<string, string[]>
  crossFlags: CrossRowFlag[]
}>({
  rowFlags: new Map(),
  crossFlags: [],
})

const totalFraudCount = computed(() => {
  let count = 0
  for (const flags of screeningResult.rowFlags.values()) {
    count += flags.length
  }
  count += screeningResult.crossFlags.length
  return count
})

function handleRunScreening() {
  showScreeningDialog.value = true
  screeningStep.value = 'config'
}

// ─── View mode ───────────────────────────────────────────────────────────────

const { viewMode: currentView } = useViewMode('list')

// ─── UI state ────────────────────────────────────────────────────────────────

const selectedIds = ref<string[]>([])
const currentRow = ref<EntityVerifyRow | null>(null)
const fraudExpanded = ref(false)

function toggleFraudPanel() {
  fraudExpanded.value = !fraudExpanded.value
}

// ─── 筛查弹窗状态 ────────────────────────────────────────────────────────────

const showScreeningDialog = ref(false)
const screeningStep = ref<'config' | 'result'>('config')

const screeningRuleConfig = ref([
  { id: 'name_mismatch', label: '单位名称不一致', description: '被审计单位提供的名称 ≠ 企查查工商登记名称', source: 'D0-2 本表', enabled: true },
  { id: 'address_mismatch', label: '注册地址不一致', description: '被审计单位提供地址 ≠ 企查查注册地址', source: 'D0-2 本表', enabled: true },
  { id: 'contact_mismatch', label: '联系人不一致', description: '函证联系人 ≠ 工商公示联系人', source: 'D0-2 本表', enabled: true },
  { id: 'phone_mismatch', label: '联系电话不一致', description: '函证电话 ≠ 工商公示电话', source: 'D0-2 本表', enabled: true },
  { id: 'unreasonable_return', label: '退回原因不合理', description: '函证退回且原因标记为"不合理"', source: 'D0-2 发函记录', enabled: true },
])

const screeningCrossConfig = ref([
  { id: 'address_cluster', label: '地址聚类（壳公司）', description: '≥3家单位注册于同一地址，可能为关联方或壳公司', relatedWp: 'D0-8 舞弊风险', enabled: true },
  { id: 'phone_adjacent', label: '电话号段相邻', description: '不同单位电话尾号连续（差≤2），疑为同一人控制', relatedWp: 'D0-8 舞弊风险', enabled: true },
])

const screeningResultDetails = ref<Array<{ entity: string; ruleLabel: string; level: string; suggestion: string }>>([])
const screeningResultSummary = ref({ total: 0, rowCount: 0, crossCount: 0 })

function executeScreening() {
  // 执行筛查
  const result = runScreening()
  screeningResult.rowFlags = result.rowFlags
  screeningResult.crossFlags = result.crossFlags

  // 更新行状态
  const crossAffectedIds = new Set(result.crossFlags.flatMap((f) => f.affectedRowIds))
  for (const row of rows.value) {
    const flagCount = result.rowFlags.get(row._row_id!)?.length ?? 0
    const hasCross = crossAffectedIds.has(row._row_id!)
    row.row_status = deriveRowStatus(flagCount, hasCross)
    row.fraud_flags = result.rowFlags.get(row._row_id!) ?? []
  }

  // 构建结果明细
  const details: typeof screeningResultDetails.value = []

  // 行内异常
  const enabledRuleIds = new Set(screeningRuleConfig.value.filter(r => r.enabled).map(r => r.id))
  for (const [rowId, flags] of result.rowFlags) {
    const row = rows.value.find(r => r._row_id === rowId)
    const entityName = row?.entity_name || rowId
    for (const flagId of flags) {
      if (!enabledRuleIds.has(flagId)) continue
      const rule = screeningRuleConfig.value.find(r => r.id === flagId)
      details.push({
        entity: entityName,
        ruleLabel: rule?.label || flagId,
        level: flags.length >= 2 ? '高' : '中',
        suggestion: flagId === 'unreasonable_return' ? '重新确认地址后补发' : '与被审计单位确认信息准确性',
      })
    }
  }

  // 跨行异常
  const enabledCrossIds = new Set(screeningCrossConfig.value.filter(r => r.enabled).map(r => r.id))
  for (const flag of result.crossFlags) {
    if (!enabledCrossIds.has(flag.type)) continue
    details.push({
      entity: `涉及 ${flag.affectedRowIds.length} 家`,
      ruleLabel: flag.label,
      level: '高',
      suggestion: '记录至 D0-8，评估关联方及舞弊风险',
    })
  }

  screeningResultDetails.value = details
  screeningResultSummary.value = {
    total: details.length,
    rowCount: result.rowFlags.size,
    crossCount: result.crossFlags.length,
  }

  // 展开筛查面板
  fraudExpanded.value = true
  screeningStep.value = 'result'
}

// Dict data stub — in real usage loaded from project dict config
const dictData: Record<string, any[]> = {
  confirmation_account_type: [
    '应收账款', '合同负债', '其他应收款', '预付账款',
    '应付账款', '其他应付款', '短期借款', '长期借款',
    '银行存款', '定期存款', '理财产品', '其他货币资金', '其他',
  ],
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAdd() {
  const newRow = addRow()
  currentRow.value = newRow
}

function handleDelete() {
  deleteRows(selectedIds.value)
  selectedIds.value = []
  if (currentRow.value && !rows.value.find((r) => r._row_id === currentRow.value?._row_id)) {
    currentRow.value = null
  }
}

function handleSave() {
  const payload = buildPayload()
  emit('save', payload)
}

function handleImport() {
  importFileInput.value?.click()
}

async function handleExport() {
  try {
    // Sheet 1: 空白模板
    const headers = ['序号', '索引号', '被询证单位', '企查查名称', '企查查地址', '联系人', '联系电话', '科目']
    const exampleRow = ['1', 'D0-001', '示例公司（请删除）', '', '', '张三', '010-12345678', '应收账款']

    // Sheet 2: 填写说明
    const instructions = [
      ['D0-2 核实被函证单位信息 — 导入模板说明'],
      [''],
      ['【必填列】'],
      ['  被询证单位：被函证公司全称'],
      ['  科目：涉及的会计科目（应收账款/合同负债/银行存款等）'],
      [''],
      ['【选填列】'],
      ['  序号：自动生成（留空即可）'],
      ['  索引号：函证编号（如 D0-001），留空自动生成'],
      ['  企查查名称：工商登记名称（用于一致性比对）'],
      ['  企查查地址：工商注册地址'],
      ['  联系人：被询证单位联系人'],
      ['  联系电话：联系电话'],
      [''],
      ['【注意】'],
      ['  1. 第一行为表头请勿修改'],
      ['  2. 示例行（第2行）请删除'],
      ['  3. 导入后系统自动进行名称/地址一致性比对'],
    ]
    // 两个 sheet 均为纯 AOA；successMessage:false 因原实现不弹成功提示
    await exportMultiSheetData({
      sheets: [
        {
          sheetName: '核实清单',
          rows: [headers, exampleRow],
          colWidths: [
            { wch: 6 }, { wch: 10 }, { wch: 25 }, { wch: 25 }, { wch: 30 },
            { wch: 10 }, { wch: 14 }, { wch: 12 },
          ],
        },
        { sheetName: '填写说明', rows: instructions, colWidths: [{ wch: 60 }] },
      ],
      fileName: 'D0-2核实清单导入模板.xlsx',
      applyStyles: false,
      successMessage: false,
    })
  } catch (e: any) {
    ElMessage.error('生成模板失败：' + (e?.message || '未知错误'))
  }
}

async function handleExportData() {
  if (rows.value.length === 0) {
    ElMessage.warning('暂无数据可导出')
    return
  }
  try {
    const headers = ['序号', '索引号', '被询证单位', '科目', '企查查名称', '企查查地址', '名称一致', '地址一致', '发函结果', '状态']
    const data = rows.value.map(r => [
      r.seq ?? '',
      r.confirm_index ?? '',
      r.entity_name ?? '',
      r.account_type ?? '',
      r.qcc_entity_name ?? '',
      r.qcc_address ?? '',
      r.name_match === 'consistent' ? '一致' : r.name_match === 'inconsistent' ? '不一致' : '待核实',
      r.address_match === 'consistent' ? '一致' : r.address_match === 'inconsistent' ? '不一致' : '待核实',
      r.first_result ?? '',
      r.row_status === 'fraud_flag' ? '舞弊' : r.row_status === 'suspect' ? '疑似' : '正常',
    ])
    await exportMultiSheetData({
      sheets: [
        {
          sheetName: '核实数据',
          rows: [headers, ...data],
          colWidths: [
            { wch: 6 }, { wch: 10 }, { wch: 25 }, { wch: 12 }, { wch: 25 },
            { wch: 30 }, { wch: 8 }, { wch: 8 }, { wch: 8 }, { wch: 8 },
          ],
        },
      ],
      fileName: 'D0-2核实数据导出.xlsx',
      applyStyles: false,
      successMessage: false,
    })
  } catch (e: any) {
    ElMessage.error('导出失败：' + (e?.message || '未知错误'))
  }
}

const importFileInput = ref<HTMLInputElement | null>(null)

async function handleImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    // 走 useExcelIO 单一入口（B2 批）。
    // requireFirstCell:false —— 首列「序号」模板说明写「留空即可」；全空行由下方 hasValue 过滤。
    const { rows: rawRows } = await parseFile(file, {
      sheetName: '',
      skipRows: 1,
      skipExamplePrefix: '',
      requireFirstCell: false,
    })
    if (rawRows.length === 0) {
      ElMessage.warning('Excel 文件为空或无法解析')
      return
    }
    const colMap: Record<string, string[]> = {
      entity_name: ['被询证单位', '单位名称', '被函证单位', '客户名称'],
      account_type: ['科目', '科目类型'],
      confirm_index: ['索引号', '编号', '函证索引号'],
      qcc_entity_name: ['企查查名称', '工商名称', '登记名称'],
      qcc_address: ['企查查地址', '注册地址', '工商地址'],
      contact_person: ['联系人', '联系人姓名'],
      contact_phone: ['联系电话', '电话'],
    }
    const importData: Partial<EntityVerifyRow>[] = []
    for (const raw of rawRows) {
      const hasValue = Object.values(raw).some(v => v != null && String(v).trim() !== '')
      if (!hasValue) continue
      const row: Partial<EntityVerifyRow> = {}
      for (const [field, aliases] of Object.entries(colMap)) {
        for (const alias of aliases) {
          if (raw[alias] != null && String(raw[alias]).trim() !== '') {
            ;(row as any)[field] = String(raw[alias]).trim()
            break
          }
        }
      }
      if (row.entity_name) importData.push(row)
    }
    if (importData.length > 0) {
      importRows(importData)
      ElMessage.success(`成功导入 ${importData.length} 条记录`)
    } else {
      ElMessage.warning('未识别到有效数据，请检查列头是否包含：被询证单位')
    }
  } catch (e: any) {
    ElMessage.error('导入失败：' + (e?.message || '文件格式错误'))
  } finally {
    if (importFileInput.value) importFileInput.value.value = ''
  }
}

function handleRowClick(row: EntityVerifyRow) {
  currentRow.value = row
}

function handleFieldUpdate(field: string, value: any) {
  if (!currentRow.value?._row_id) return
  updateField(currentRow.value._row_id, field, value)
}

function markDirty() {
  isDirty.value = true
}

// 暴露给父组件通过 ref 调用（页面级工具栏转发）
defineExpose({
  handleExport,
  handleExportData,
  handleImport,
  handleImportClick: handleImport,
  handleDownloadImportTemplate: handleExport,
})
</script>

<style scoped>
.gt-confirmation-entity-verify {
  padding: 8px 12px;
}

.gt-confirmation-entity-verify__legacy-notice {
  margin-bottom: 16px;
}

/* 顶部：Dashboard + 反舞弊并排 */
.gt-confirmation-entity-verify__top-bar {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}

.gt-confirmation-entity-verify__dashboard {
  margin-bottom: 0;
}

.gt-confirmation-entity-verify__fraud-compact {
  background: #fafbfc;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 10px 12px;
}

.gt-confirmation-entity-verify__fraud-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
}

.gt-confirmation-entity-verify__fraud-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 工具栏 */
.gt-confirmation-entity-verify__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding: 6px 0;
  border-bottom: 1px solid #ebeef5;
}

.gt-confirmation-entity-verify__toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.gt-confirmation-entity-verify__list-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.gt-confirmation-entity-verify__master {
  width: 100%;
}

.gt-confirmation-entity-verify__detail {
  width: 100%;
}

.gt-confirmation-entity-verify__grid-view {
  width: 100%;
}

.gt-confirmation-entity-verify__grid-toolbar {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

/* 完整表格：表头文字折行 + 紧凑字号 */
.gt-confirmation-entity-verify__full-table :deep(.el-table__header th .cell) {
  white-space: normal;
  word-break: break-all;
  line-height: 1.3;
  font-size: 12px;
  padding: 4px 2px;
}

.gt-confirmation-entity-verify__full-table :deep(.el-table__body td .cell) {
  font-size: 12px;
  padding: 2px 4px;
}

@media (max-width: 1400px) {
  .gt-confirmation-entity-verify__top-bar {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1200px) {
  .gt-confirmation-entity-verify__list-view {
    gap: 8px;
  }
}
</style>
