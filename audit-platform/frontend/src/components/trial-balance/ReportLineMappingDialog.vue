<template>
  <el-dialog
    v-model="visible"
    title="映射规则 — 余额表科目 → 报表项目"
    width="960px"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <!-- 顶部操作栏 -->
    <div class="rlm-toolbar">
      <el-button type="primary" size="small" :loading="presetLoading" @click="onPreset">
        🎯 一键预设
      </el-button>
      <el-button size="small" :loading="aiLoading" @click="onAiSuggest">
        🤖 AI 建议
      </el-button>
      <el-button size="small" @click="showRefDialog = true">
        📋 参照其他单位
      </el-button>
      <el-button size="small" :loading="confirmAllLoading" @click="onBatchConfirm" :disabled="!unconfirmedIds.length">
        ✅ 全部确认 ({{ unconfirmedIds.length }})
      </el-button>
      <el-button size="small" @click="onExportTemplate">
        📥 导出模板
      </el-button>
      <el-upload
        :show-file-list="false"
        accept=".xlsx,.xls,.csv"
        :before-upload="onImportTemplate"
        style="display: inline-block"
      >
        <el-button size="small">📤 导入模板</el-button>
      </el-upload>
      <span style="flex:1" />
      <el-select v-model="filterType" size="small" placeholder="筛选" clearable style="width: 140px">
        <el-option label="全部" value="" />
        <el-option label="资产负债表" value="balance_sheet" />
        <el-option label="利润表" value="income_statement" />
        <el-option label="⚠ 未映射" value="__unmatched__" />
      </el-select>
    </div>

    <!-- 统一映射表格 -->
    <el-table
      :data="displayRows"
      v-loading="loading"
      border
      max-height="500"
      style="width: 100%; margin-top: 12px"
      size="small"
      :row-class-name="rowClassName"
    >
      <el-table-column label="科目编码" width="110">
        <template #default="{ row }">
          <span class="rlm-code">{{ row.account_code }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" min-width="150">
        <template #default="{ row }">
          <span :class="{ 'rlm-unmatched-name': !row.mapped }">{{ row.account_name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="→" width="36" align="center">
        <template #default><span style="color:#c0c4cc">→</span></template>
      </el-table-column>
      <el-table-column label="报表项目" min-width="220">
        <template #default="{ row }">
          <div v-if="row.mapped && !row._editing" style="display:flex;align-items:center;gap:4px">
            <el-tag size="small" type="info" style="flex-shrink:0">{{ row.report_line_code }}</el-tag>
            <span style="font-weight:500">{{ row.report_line_name }}</span>
            <el-button link size="small" style="margin-left:auto;color:#909399" @click="row._editing = true">✏️</el-button>
          </div>
          <el-select
            v-else
            v-model="row._selectedLine"
            size="small"
            filterable
            placeholder="选择报表项目"
            style="width:100%"
            @change="onManualMap(row)"
          >
            <el-option-group v-for="group in reportLineGroups" :key="group.label" :label="group.label">
              <el-option
                v-for="line in group.items"
                :key="line.code"
                :label="`${line.code} ${line.name}`"
                :value="line.code"
              />
            </el-option-group>
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="报表类型" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.report_type" size="small" :type="reportTypeTag(row.report_type)">{{ reportTypeLabel(row.report_type) }}</el-tag>
          <span v-else style="color:#c0c4cc">—</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="76" align="center">
        <template #default="{ row }">
          <el-tag v-if="!row.mapped" type="danger" size="small">未映射</el-tag>
          <el-tag v-else-if="row.is_confirmed" type="success" size="small">已确认</el-tag>
          <el-tag v-else type="warning" size="small">待确认</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90" align="center">
        <template #default="{ row }">
          <el-button v-if="row.mapped && !row.is_confirmed" link type="primary" size="small" @click="onConfirm(row)">确认</el-button>
          <el-button v-if="row.mapped" link type="danger" size="small" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部统计 -->
    <div class="rlm-footer">
      <span>一级科目共 <b>{{ allLevel1Accounts.length }}</b> 个</span>
      <span style="margin-left:16px;color:#67c23a">✓ 已映射 {{ matchedCount }}</span>
      <span style="margin-left:16px;color:#f56c6c;font-weight:600">✗ 未映射 {{ unmatchedCount }}</span>
      <span style="margin-left:16px;color:#909399">已确认 {{ confirmedCount }}</span>
    </div>

    <!-- 参照其他单位弹窗 -->
    <el-dialog v-model="showRefDialog" title="参照其他单位映射" width="480px" append-to-body>
      <el-form label-width="100px">
        <el-form-item label="来源单位">
          <el-select v-model="refSourceCode" filterable placeholder="选择已有映射的单位" style="width:100%">
            <el-option v-for="p in projectOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <div style="font-size:12px;color:#909399;line-height:1.6">
            将选中单位的映射规则复制到当前项目。已有映射不会被覆盖，仅补充缺失的映射关系。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRefDialog = false">取消</el-button>
        <el-button type="primary" :loading="refLoading" :disabled="!refSourceCode" @click="onReferenceCopy">复制映射</el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { reportLineMapping } from '@/services/apiPaths'
import { useProjectStore } from '@/stores/project'
import { handleApiError } from '@/utils/errorHandler'

const props = defineProps<{ modelValue: boolean; projectId: string; accountRows?: any[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()
const projectStore = useProjectStore()

const visible = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })

// ─── 状态 ───
const mappings = ref<any[]>([])
const reportLineOptions = ref<any[]>([])
const loading = ref(false)
const filterType = ref('')
const presetLoading = ref(false)
const aiLoading = ref(false)
const confirmAllLoading = ref(false)
const showRefDialog = ref(false)
const refSourceCode = ref('')
const refLoading = ref(false)
const projectOptions = computed(() => projectStore.projectOptions)

// 报表行次分组（供下拉选择）
const reportLineGroups = computed(() => {
  const bs = reportLineOptions.value.filter(l => l.report_type === 'balance_sheet')
  const is = reportLineOptions.value.filter(l => l.report_type === 'income_statement')
  const groups: { label: string; items: { code: string; name: string }[] }[] = []
  if (bs.length) groups.push({ label: '资产负债表', items: bs.map(l => ({ code: l.report_line_code, name: l.report_line_name })) })
  if (is.length) groups.push({ label: '利润表', items: is.map(l => ({ code: l.report_line_code, name: l.report_line_name })) })
  return groups
})

// ─── 从试算表提取所有一级科目（前4位去重） ───
const allLevel1Accounts = computed(() => {
  if (!props.accountRows?.length) return []
  const seen = new Map<string, string>()
  for (const row of props.accountRows) {
    const code = row.standard_account_code || ''
    const name = row.account_name || ''
    if (!code) continue
    const level1 = code.length >= 4 ? code.slice(0, 4) : code
    if (!seen.has(level1)) seen.set(level1, name)
  }
  return Array.from(seen.entries())
    .map(([code, name]) => ({ code, name }))
    .sort((a, b) => a.code.localeCompare(b.code))
})

// ─── 合并展示（一级科目 LEFT JOIN 映射） ───
const mergedRows = computed(() => {
  const mappingByCode = new Map<string, any>()
  for (const m of mappings.value) {
    const code = (m.standard_account_code || '').slice(0, 4)
    if (!mappingByCode.has(code)) mappingByCode.set(code, m)
  }
  const rows: any[] = []
  const usedCodes = new Set<string>()
  for (const acct of allLevel1Accounts.value) {
    usedCodes.add(acct.code)
    const m = mappingByCode.get(acct.code)
    rows.push({
      account_code: acct.code,
      account_name: acct.name,
      mapped: !!m,
      id: m?.id || null,
      report_line_code: m?.report_line_code || '',
      report_line_name: m?.report_line_name || '',
      report_type: m?.report_type || '',
      is_confirmed: m?.is_confirmed || false,
    })
  }
  // 补充映射表中有但试算表没有的
  for (const m of mappings.value) {
    const code = (m.standard_account_code || '').slice(0, 4)
    if (!usedCodes.has(code)) {
      usedCodes.add(code)
      rows.push({
        account_code: code, account_name: code, mapped: true,
        id: m.id, report_line_code: m.report_line_code,
        report_line_name: m.report_line_name, report_type: m.report_type,
        is_confirmed: m.is_confirmed,
      })
    }
  }
  return rows
})

// ─── 筛选 + 统计 ───
const displayRows = computed(() => {
  if (!filterType.value) return mergedRows.value
  if (filterType.value === '__unmatched__') return mergedRows.value.filter(r => !r.mapped)
  return mergedRows.value.filter(r => r.report_type === filterType.value)
})
const matchedCount = computed(() => mergedRows.value.filter(r => r.mapped).length)
const unmatchedCount = computed(() => mergedRows.value.filter(r => !r.mapped).length)
const confirmedCount = computed(() => mappings.value.filter(m => m.is_confirmed).length)
const unconfirmedIds = computed(() => mappings.value.filter(m => !m.is_confirmed).map(m => m.id))

function rowClassName({ row }: { row: any }) { return row.mapped ? '' : 'rlm-row-unmatched' }

// ─── 加载 ───
async function loadMappings() {
  if (!props.projectId) return
  loading.value = true
  try {
    const [mapData, linesData] = await Promise.all([
      api.get(reportLineMapping.list(props.projectId)),
      api.get(`/api/projects/${props.projectId}/report-line-mapping/report-lines`).catch(() => []),
    ])
    mappings.value = Array.isArray(mapData) ? mapData : []
    // 报表行次选项：始终用完整标准行次（确保未分配利润等不遗漏）
    // 后端返回的只是已用过的子集，不能作为可选全集
    reportLineOptions.value = _buildDefaultReportLines()
  } catch (e) { handleApiError(e, '加载映射规则') }
  finally { loading.value = false }
}
watch(visible, (v) => { if (v && props.projectId) { loadMappings(); projectStore.loadProjectOptions() } })

// 预设标准报表行次（当后端无数据时的兜底）
function _buildDefaultReportLines() {
  return [
    { report_line_code: 'BS001', report_line_name: '货币资金', report_type: 'balance_sheet' },
    { report_line_code: 'BS002', report_line_name: '交易性金融资产', report_type: 'balance_sheet' },
    { report_line_code: 'BS003', report_line_name: '应收票据', report_type: 'balance_sheet' },
    { report_line_code: 'BS004', report_line_name: '应收账款', report_type: 'balance_sheet' },
    { report_line_code: 'BS005', report_line_name: '预付款项', report_type: 'balance_sheet' },
    { report_line_code: 'BS006', report_line_name: '应收利息', report_type: 'balance_sheet' },
    { report_line_code: 'BS007', report_line_name: '应收股利', report_type: 'balance_sheet' },
    { report_line_code: 'BS008', report_line_name: '其他应收款', report_type: 'balance_sheet' },
    { report_line_code: 'BS009', report_line_name: '存货', report_type: 'balance_sheet' },
    { report_line_code: 'BS010', report_line_name: '持有待售资产', report_type: 'balance_sheet' },
    { report_line_code: 'BS011', report_line_name: '长期股权投资', report_type: 'balance_sheet' },
    { report_line_code: 'BS012', report_line_name: '固定资产', report_type: 'balance_sheet' },
    { report_line_code: 'BS013', report_line_name: '无形资产', report_type: 'balance_sheet' },
    { report_line_code: 'BS014', report_line_name: '长期待摊费用', report_type: 'balance_sheet' },
    { report_line_code: 'BS015', report_line_name: '在建工程', report_type: 'balance_sheet' },
    { report_line_code: 'BS016', report_line_name: '开发支出', report_type: 'balance_sheet' },
    { report_line_code: 'BS017', report_line_name: '商誉', report_type: 'balance_sheet' },
    { report_line_code: 'BS022', report_line_name: '递延所得税资产', report_type: 'balance_sheet' },
    { report_line_code: 'BS101', report_line_name: '短期借款', report_type: 'balance_sheet' },
    { report_line_code: 'BS102', report_line_name: '应付票据', report_type: 'balance_sheet' },
    { report_line_code: 'BS103', report_line_name: '应付账款', report_type: 'balance_sheet' },
    { report_line_code: 'BS104', report_line_name: '预收款项', report_type: 'balance_sheet' },
    { report_line_code: 'BS105', report_line_name: '应付职工薪酬', report_type: 'balance_sheet' },
    { report_line_code: 'BS106', report_line_name: '应交税费', report_type: 'balance_sheet' },
    { report_line_code: 'BS107', report_line_name: '其他应付款', report_type: 'balance_sheet' },
    { report_line_code: 'BS108', report_line_name: '长期借款', report_type: 'balance_sheet' },
    { report_line_code: 'BS109', report_line_name: '应付债券', report_type: 'balance_sheet' },
    { report_line_code: 'BS110', report_line_name: '长期应付款', report_type: 'balance_sheet' },
    { report_line_code: 'BS115', report_line_name: '预计负债', report_type: 'balance_sheet' },
    { report_line_code: 'BS116', report_line_name: '递延所得税负债', report_type: 'balance_sheet' },
    { report_line_code: 'BS201', report_line_name: '实收资本（股本）', report_type: 'balance_sheet' },
    { report_line_code: 'BS202', report_line_name: '资本公积', report_type: 'balance_sheet' },
    { report_line_code: 'BS203', report_line_name: '盈余公积', report_type: 'balance_sheet' },
    { report_line_code: 'BS204', report_line_name: '未分配利润', report_type: 'balance_sheet' },
    { report_line_code: 'BS205', report_line_name: '其他综合收益', report_type: 'balance_sheet' },
    { report_line_code: 'BS206', report_line_name: '库存股', report_type: 'balance_sheet' },
    { report_line_code: 'BS207', report_line_name: '专项储备', report_type: 'balance_sheet' },
    { report_line_code: 'BS209', report_line_name: '其他权益工具', report_type: 'balance_sheet' },
    { report_line_code: 'IS001', report_line_name: '营业收入', report_type: 'income_statement' },
    { report_line_code: 'IS002', report_line_name: '营业成本', report_type: 'income_statement' },
    { report_line_code: 'IS003', report_line_name: '税金及附加', report_type: 'income_statement' },
    { report_line_code: 'IS004', report_line_name: '销售费用', report_type: 'income_statement' },
    { report_line_code: 'IS005', report_line_name: '管理费用', report_type: 'income_statement' },
    { report_line_code: 'IS006', report_line_name: '研发费用', report_type: 'income_statement' },
    { report_line_code: 'IS007', report_line_name: '财务费用', report_type: 'income_statement' },
    { report_line_code: 'IS008', report_line_name: '资产减值损失', report_type: 'income_statement' },
    { report_line_code: 'IS009', report_line_name: '信用减值损失', report_type: 'income_statement' },
    { report_line_code: 'IS010', report_line_name: '资产处置收益', report_type: 'income_statement' },
    { report_line_code: 'IS011', report_line_name: '其他收益', report_type: 'income_statement' },
    { report_line_code: 'IS012', report_line_name: '投资收益', report_type: 'income_statement' },
    { report_line_code: 'IS013', report_line_name: '公允价值变动收益', report_type: 'income_statement' },
    { report_line_code: 'IS014', report_line_name: '营业外收入', report_type: 'income_statement' },
    { report_line_code: 'IS015', report_line_name: '营业外支出', report_type: 'income_statement' },
    { report_line_code: 'IS016', report_line_name: '所得税费用', report_type: 'income_statement' },
  ]
}

// ─── 一键预设（生成 + 自动确认） ───
async function onPreset() {
  if (!props.projectId) { ElMessage.warning('请先选择项目'); return }
  presetLoading.value = true
  try {
    await api.post(reportLineMapping.aiSuggest(props.projectId))
    await loadMappings()
    const toConfirm = mappings.value.filter(m => !m.is_confirmed).map(m => m.id)
    if (toConfirm.length) {
      await api.post(reportLineMapping.batchConfirm(props.projectId), { mapping_ids: toConfirm })
      await loadMappings()
    }
    ElMessage.success(`预设完成（已映射 ${matchedCount.value}，未映射 ${unmatchedCount.value}）`)
  } catch (e) { handleApiError(e, '一键预设') }
  finally { presetLoading.value = false }
}

// ─── AI 建议 ───
async function onAiSuggest() {
  aiLoading.value = true
  try {
    await api.post(reportLineMapping.aiSuggest(props.projectId))
    ElMessage.success('AI 建议已生成')
    await loadMappings()
  } catch (e) { handleApiError(e, 'AI 建议') }
  finally { aiLoading.value = false }
}

// ─── 批量确认 ───
async function onBatchConfirm() {
  confirmAllLoading.value = true
  try {
    await api.post(reportLineMapping.batchConfirm(props.projectId), { mapping_ids: unconfirmedIds.value })
    ElMessage.success(`已确认 ${unconfirmedIds.value.length} 条`)
    await loadMappings()
  } catch (e) { handleApiError(e, '批量确认') }
  finally { confirmAllLoading.value = false }
}

// ─── 单条确认 ───
async function onConfirm(row: any) {
  if (!row.id) return
  try {
    await api.put(reportLineMapping.confirm(props.projectId, row.id))
    row.is_confirmed = true
    ElMessage.success('已确认')
  } catch (e) { handleApiError(e, '确认映射') }
}

// ─── 手动映射（未映射科目选择报表项目后创建映射） ───
async function onManualMap(row: any) {
  const selectedCode = row._selectedLine
  if (!selectedCode || !props.projectId) return
  const lineInfo = reportLineOptions.value.find((l: any) => l.report_line_code === selectedCode)
  if (!lineInfo) return
  try {
    await api.post(`/api/projects/${props.projectId}/report-line-mapping/manual`, {
      standard_account_code: row.account_code,
      report_type: lineInfo.report_type,
      report_line_code: lineInfo.report_line_code,
      report_line_name: lineInfo.report_line_name,
    })
    ElMessage.success(`已映射：${row.account_name} → ${lineInfo.report_line_name}`)
    row._editing = false
    await loadMappings()
  } catch (e) {
    handleApiError(e, '手动映射')
  }
}

// ─── 删除 ───
async function onDelete(row: any) {
  if (!row.id) return
  try {
    await api.delete(reportLineMapping.detail(props.projectId, row.id))
    mappings.value = mappings.value.filter(m => m.id !== row.id)
    ElMessage.success('已删除')
  } catch (e) { handleApiError(e, '删除映射') }
}

// ─── 参照复制 ───
async function onReferenceCopy() {
  refLoading.value = true
  try {
    const result: any = await api.post(reportLineMapping.referenceCopy(props.projectId), { source_company_code: refSourceCode.value })
    ElMessage.success(`已复制 ${result?.copied_count ?? 0} 条映射`)
    showRefDialog.value = false
    await loadMappings()
  } catch (e) { handleApiError(e, '参照复制') }
  finally { refLoading.value = false }
}

// ─── 导出映射模板（Excel，含必填标注 + 预设库 sheet） ───
function onExportTemplate() {
  import('xlsx').then(XLSX => {
    const wb = XLSX.utils.book_new()

    // Sheet 1：映射规则（当前数据）
    const data = mergedRows.value.map(r => ({
      '*科目编码（必填）': r.account_code,
      '科目名称': r.account_name,
      '*报表行次编码（必填）': r.report_line_code || '',
      '*报表行次名称（必填）': r.report_line_name || '',
      '*报表类型（必填）': r.report_type ? reportTypeLabel(r.report_type) : '',
      '状态': r.mapped ? (r.is_confirmed ? '已确认' : '待确认') : '⚠未映射-请填写',
    }))
    const ws = XLSX.utils.json_to_sheet(data)
    ws['!cols'] = [{ wch: 18 }, { wch: 20 }, { wch: 20 }, { wch: 22 }, { wch: 18 }, { wch: 16 }]
    XLSX.utils.book_append_sheet(wb, ws, '映射规则')

    // Sheet 2：预设库（所有可选的报表行次，供用户复制粘贴）
    const presetData = reportLineOptions.value.map((l: any) => ({
      '报表行次编码': l.report_line_code,
      '报表行次名称': l.report_line_name,
      '报表类型': reportTypeLabel(l.report_type),
    }))
    const ws2 = XLSX.utils.json_to_sheet(presetData)
    ws2['!cols'] = [{ wch: 16 }, { wch: 24 }, { wch: 14 }]
    XLSX.utils.book_append_sheet(wb, ws2, '可选报表行次（预设库）')

    // Sheet 3：填写说明
    const instructions = [
      { '说明': '【填写规则】' },
      { '说明': '1. 带 * 号的列为必填项' },
      { '说明': '2. "科目编码"为余额表中的一级科目编码（4位）' },
      { '说明': '3. "报表行次编码"和"报表行次名称"请从"可选报表行次"sheet中选择' },
      { '说明': '4. "报表类型"可选值：资产负债表 / 利润表' },
      { '说明': '5. 已有映射的行无需修改，只需补充"⚠未映射"的行' },
      { '说明': '6. 编辑完成后保存，回到系统点击"导入模板"上传即可' },
      { '说明': '' },
      { '说明': '【注意事项】' },
      { '说明': '- 导入时已存在的映射不会被覆盖' },
      { '说明': '- 如需修改已有映射，请先在系统中删除再导入' },
      { '说明': '- 同一科目编码只能映射到一个报表行次' },
    ]
    const ws3 = XLSX.utils.json_to_sheet(instructions)
    ws3['!cols'] = [{ wch: 60 }]
    XLSX.utils.book_append_sheet(wb, ws3, '填写说明')

    XLSX.writeFile(wb, `映射规则模板_${props.projectId.slice(0, 8)}.xlsx`)
    ElMessage.success('已导出映射模板（含预设库和填写说明）')
  })
}

// ─── 导入映射模板（Excel） ───
function onImportTemplate(file: File) {
  import('xlsx').then(async XLSX => {
    const buf = await file.arrayBuffer()
    const wb = XLSX.read(buf)
    const ws = wb.Sheets[wb.SheetNames[0]]
    const rows: any[] = XLSX.utils.sheet_to_json(ws)

    if (!rows.length) {
      ElMessage.warning('文件为空')
      return
    }

    // 解析并批量创建映射（兼容带*号和不带*号的列名）
    const typeMap: Record<string, string> = { '资产负债表': 'balance_sheet', '利润表': 'income_statement', '现金流量表': 'cash_flow', '权益变动表': 'equity_change' }
    let created = 0
    let skipped = 0
    for (const row of rows) {
      const code = String(row['*科目编码（必填）'] || row['科目编码'] || '').trim()
      const lineCode = String(row['*报表行次编码（必填）'] || row['报表行次编码'] || '').trim()
      const lineName = String(row['*报表行次名称（必填）'] || row['报表行次名称'] || '').trim()
      const typeStr = String(row['*报表类型（必填）'] || row['报表类型'] || '').trim()
      if (!code || !lineCode || !lineName) { skipped++; continue }

      const reportType = typeMap[typeStr] || 'balance_sheet'
      try {
        const res: any = await api.post(`/api/projects/${props.projectId}/report-line-mapping/manual`, {
          standard_account_code: code,
          report_type: reportType,
          report_line_code: lineCode,
          report_line_name: lineName,
        })
        if (res?.created) created++
        else skipped++
      } catch { skipped++ }
    }
    ElMessage.success(`导入完成：新增 ${created} 条，跳过 ${skipped} 条（已存在或无效）`)
    await loadMappings()
  })
  return false
}

// ─── 辅助 ───
function reportTypeLabel(t: string) {
  return ({ balance_sheet: '资产负债表', income_statement: '利润表', cash_flow: '现金流量表', equity_change: '权益变动表' } as any)[t] || t || '—'
}
function reportTypeTag(t: string) {
  return ({ balance_sheet: '', income_statement: 'success', cash_flow: 'warning', equity_change: 'info' } as any)[t] || 'info'
}
</script>

<style scoped>
.rlm-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rlm-footer { margin-top: 12px; font-size: 12px; color: #606266; }
.rlm-code { font-family: 'Arial Narrow', Arial, sans-serif; font-variant-numeric: tabular-nums; }

/* 未映射行高亮（红色左边框 + 浅红背景） */
:deep(.rlm-row-unmatched) { background: #fef0f0 !important; }
:deep(.rlm-row-unmatched td:first-child) { border-left: 3px solid #f56c6c !important; }
.rlm-unmatched-name { color: #f56c6c; font-weight: 600; }
.rlm-unmatched-label { color: #f56c6c; font-size: 11px; font-style: italic; }

/* 表格字号 */
:deep(.el-table) { font-size: 12px; }
:deep(.el-table th .cell), :deep(.el-table td .cell) { font-size: 12px; }
</style>
