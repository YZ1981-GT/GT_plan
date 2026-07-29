<template>
  <div class="gt-confirmation-reliability">
    <!-- 旧格式降级 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-reliability__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：reliability-v1 -->
    <template v-else>
      <!-- 看板 -->
      <ReliabilityDashboard :metrics="data.metrics.value" />

      <!-- 可靠性验证网格 -->
      <ReliabilityGrid
        :rows="data.rows.value"
        :readonly="readonly"
        :is-dirty="data.isDirty.value"
        :is-verification-disabled="data.isVerificationDisabled"
        :get-row-quality-status="data.getRowQualityStatus"
        @add="handleAdd"
        @delete="handleDelete"
        @save="handleSave"
        @update="handleUpdate"
        @import-d01="handleImportD01"
        @import-excel="handleImportExcel"
        @export-template="handleExportExcel"
        @export-data="handleExportData"
        @jump-d01="handleJumpD01"
      />

      <!-- 审计说明 + 结论 -->
      <ReliabilityConclusion
        :audit-note="data.auditNote.value"
        :conclusion="data.conclusion.value"
        :readonly="readonly"
        :total-count="data.metrics.value.total_count"
        :verified-count="data.metrics.value.verified_count"
        :reliable-count="data.metrics.value.reliable_count"
        :partial-count="data.metrics.value.partial_count"
        :unreliable-count="data.metrics.value.unreliable_count"
        :original-returned-count="data.metrics.value.original_returned_count"
        @update-note="handleAuditNoteUpdate"
        @update-conclusion="handleConclusionUpdate"
      />
    </template>

    <!-- 隐藏文件选择器 -->
    <input ref="importFileInput" type="file" accept=".xlsx,.xls,.csv" style="display:none" @change="handleImportFile" />

    <!-- D0-1 带入确认弹窗 -->
    <el-dialog v-model="showD01Dialog" title="从 D0-1 带入电子回函" width="520px" append-to-body>
      <div style="font-size:13px;line-height:1.8;color:#606266">
        <p style="margin:0 0 12px"><strong>操作说明：</strong></p>
        <ol style="padding-left:20px;margin:0 0 16px">
          <li>系统将从 D0-1 函证汇总表中筛选<strong>回函方式为「传真」或「电子邮件」</strong>的函证对象</li>
          <li>自动带入：函证索引号、被询证单位名称、回函方式、回函日期</li>
          <li>为每条电子回函创建可靠性验证记录（需逐行完成身份确认+邮箱验证）</li>
          <li>已存在相同索引号的行不会重复导入</li>
        </ol>
        <el-alert type="warning" :closable="false" show-icon style="margin-bottom:0">
          <template #title>验证要点提醒</template>
          <ul style="margin:4px 0 0;padding-left:16px;font-size:12px">
            <li>私人邮箱（163/qq/gmail）发出的回函应判定为<strong>不可靠</strong></li>
            <li>需确认发件人身份——是否为被函证单位有权回复人员</li>
            <li>不可靠的判定将自动触发 D0-8 舞弊风险评价（第7条）</li>
          </ul>
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="showD01Dialog = false">取消</el-button>
        <el-button type="primary" @click="confirmImportD01">确认带入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { useReliabilityData } from './composables/useReliabilityData'
import { mapSummaryToReliabilityRow } from './composables/mapD01ReliabilityRow'
import { filterSummaryRows, defaultElectronicReplyFilter } from '../coordination/importFromSummary'
import type { ReliabilityRow } from './reliabilityTypes'

import ReliabilityDashboard from './ReliabilityDashboard.vue'
import ReliabilityGrid from './ReliabilityGrid.vue'
import ReliabilityConclusion from './ReliabilityConclusion.vue'

const GtGridSheet = defineAsyncComponent(() => import('../../GtGridSheet.vue'))

const props = defineProps<{
  htmlData: any
  readonly: boolean
  wpId?: string
  projectId?: string
  wpCode?: string
  year?: string
}>()

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// ─── 格式检测 ────────────────────────────────────────────────────────────────

const htmlDataRef = computed(() => props.htmlData)
const isNewFormat = computed(() => !props.htmlData || !!props.htmlData?._format || Object.keys(props.htmlData || {}).length === 0)

// ─── 数据核心 ────────────────────────────────────────────────────────────────

const data = useReliabilityData({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleAdd() {
  data.addRow()
}

function handleDelete(ids: string[]) {
  data.deleteRows(ids)
}

function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
}

function handleUpdate(rowId: string, field: string, value: any) {
  data.updateField(rowId, field, value)
}

const showD01Dialog = ref(false)
const importD01Loading = ref(false)
const importFileInput = ref<HTMLInputElement | null>(null)

function handleImportD01() {
  showD01Dialog.value = true
}

function confirmImportD01() {
  showD01Dialog.value = false
  if (!props.projectId) {
    ElMessage.warning('缺少项目上下文，无法带入')
    return
  }
  if (importD01Loading.value) return
  importD01Loading.value = true
  // 循环码派生：D0-7→D0-1 优先; 回退 D0（整册含 confirmation-v1 sheet）
  const cycleBase = (props.wpCode || '').split('-')[0]
  const summaryCode = cycleBase + '-1'

  const doImport = async () => {
    let res = await filterSummaryRows(props.projectId!, summaryCode, defaultElectronicReplyFilter)
    // 回退：X0-1 不存在时尝试父底稿 X0
    if (!res) {
      res = await filterSummaryRows(props.projectId!, cycleBase, defaultElectronicReplyFilter)
    }
    if (!res) {
      ElMessage.warning(`未找到 ${summaryCode} 或 ${cycleBase} 函证结果汇总底稿`)
      return
    }
    if (res.rows.length === 0) {
      ElMessage.info(`${summaryCode} 暂无电子回函（传真/电子邮件）行`)
      return
    }
    // 按 confirm_index 去重
    const existingIndexes = new Set(
      data.rows.value.map((r: any) => r.confirm_index).filter(Boolean) as string[]
    )
    const mapped = res.rows
      .filter((r) => !r.confirm_index || !existingIndexes.has(r.confirm_index))
      .map(mapSummaryToReliabilityRow)
    if (mapped.length === 0) {
      ElMessage.info('电子回函行已全部存在，无需重复带入')
      return
    }
    data.importRows(mapped)
    ElMessage.success(`已从汇总表带入 ${mapped.length} 条电子回函记录`)
  }

  doImport()
    .catch((e: any) => {
      console.warn('[GtConfirmationReliability] 从 D0-1 带入失败:', e)
      ElMessage.error('带入失败：' + (e?.message || '网络错误'))
    })
    .finally(() => { importD01Loading.value = false })
}

function handleImportExcel() {
  importFileInput.value?.click()
}

async function handleImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const { read, utils } = await import('xlsx')
    const buf = await file.arrayBuffer()
    const wb = read(buf, { type: 'array' })
    const ws = wb.Sheets[wb.SheetNames[0]]
    const rawRows: Record<string, any>[] = utils.sheet_to_json(ws)
    if (rawRows.length === 0) {
      ElMessage.warning('Excel 文件为空或无法解析')
      return
    }
    const colMap: Record<string, string[]> = {
      confirm_index: ['索引号', '函证索引号', '编号'],
      entity_name: ['被询证单位', '单位名称', '公司名称', '被函证单位'],
      reply_method: ['回函方式', '回函途径'],
      reply_date: ['回函日期', '收函日期'],
    }
    const importData: Partial<ReliabilityRow>[] = []
    const existingIndexes = new Set(data.rows.value.map(r => r.confirm_index).filter(Boolean))
    for (const raw of rawRows) {
      const hasValue = Object.values(raw).some(v => v != null && String(v).trim() !== '')
      if (!hasValue) continue
      const row: Partial<ReliabilityRow> = {}
      for (const [field, aliases] of Object.entries(colMap)) {
        for (const alias of aliases) {
          if (raw[alias] != null && String(raw[alias]).trim() !== '') {
            ;(row as any)[field] = String(raw[alias]).trim()
            break
          }
        }
      }
      // 去重
      if (row.confirm_index && existingIndexes.has(row.confirm_index)) continue
      if (row.entity_name || row.confirm_index) {
        importData.push({ ...row, _source: 'import' })
        if (row.confirm_index) existingIndexes.add(row.confirm_index)
      }
    }
    if (importData.length > 0) {
      data.importRows(importData)
      ElMessage.success(`成功导入 ${importData.length} 条记录`)
    } else {
      ElMessage.warning('未识别到有效数据，请检查列头是否包含：被询证单位 或 索引号')
    }
  } catch (e: any) {
    ElMessage.error('导入失败：' + (e?.message || '文件格式错误'))
  } finally {
    if (importFileInput.value) importFileInput.value.value = ''
  }
}

async function handleExportExcel() {
  try {
    const { utils, writeFileXLSX } = await import('xlsx')
    const wb = utils.book_new()

    // Sheet 1: 导入模板
    const headers = ['序号', '索引号', '被询证单位', '回函方式', '回函日期', '寄回原件', '身份已确认', '身份确认方式', '邮箱已验证', '邮箱域名', '已致电', '电话来源', '可靠性结论', '备注']
    const exampleRow = ['1', 'D0-001', '示例公司（请删除）', '电子邮件', '2026-01-15', '否', '', '', '', '', '', '', '', '']
    const ws = utils.aoa_to_sheet([headers, exampleRow])
    ws['!cols'] = [
      { wch: 6 }, { wch: 10 }, { wch: 25 }, { wch: 10 }, { wch: 12 },
      { wch: 8 }, { wch: 10 }, { wch: 12 }, { wch: 10 }, { wch: 14 },
      { wch: 8 }, { wch: 10 }, { wch: 14 }, { wch: 20 },
    ]
    utils.book_append_sheet(wb, ws, '可靠性验证')

    // Sheet 2: 填写说明
    const instructions = [
      ['D0-7 回函可靠性验证 — 导入模板说明'],
      [''],
      ['【适用范围】'],
      ['  仅针对回函方式为"传真"或"电子邮件"的函证（原件寄回无需验证）'],
      [''],
      ['【必填列】'],
      ['  被询证单位：公司全称'],
      ['  回函方式：传真 / 电子邮件'],
      [''],
      ['【选填列】'],
      ['  序号：自动生成（留空即可）'],
      ['  索引号：函证编号（如 D0-001），用于跨底稿追溯'],
      ['  回函日期：格式 YYYY-MM-DD'],
      ['  寄回原件：是/否（填"是"则后续验证列自动灰掉）'],
      [''],
      ['【验证列（寄回原件=否时需填）】'],
      ['  身份已确认：是/否（注1：确认发件人为被函证单位有权回复人员）'],
      ['  身份确认方式：电话确认/邮件确认/见面确认/系统确认'],
      ['  邮箱已验证：是/否（注2：确认邮箱域名与官方域名一致）'],
      ['  邮箱域名：如 @company.com（私人邮箱如163/qq不可靠）'],
      ['  已致电：是/否'],
      ['  电话来源：工商/官网/独立来源'],
      [''],
      ['【结论列】'],
      ['  可靠性结论：可靠 / 部分可靠需补充 / 不可靠'],
      ['  备注：补充说明'],
      [''],
      ['【注意事项】'],
      ['  1. 第一行为表头请勿修改'],
      ['  2. 示例行（第2行）请删除'],
      ['  3. 已存在相同索引号的行不会重复导入'],
      ['  4. 私人邮箱（163/qq/gmail）发出的回函应判定为不可靠'],
      ['  5. 不可靠的行将自动触发舞弊信号收集（D0-8第7条）'],
    ]
    const instrSheet = utils.aoa_to_sheet(instructions)
    instrSheet['!cols'] = [{ wch: 70 }]
    utils.book_append_sheet(wb, instrSheet, '填写说明')

    writeFileXLSX(wb, 'D0-7回函可靠性验证_导入模板.xlsx')
    ElMessage.success('模板已导出')
  } catch (e: any) {
    ElMessage.error('生成模板失败：' + (e?.message || '未知错误'))
  }
}

async function handleExportData() {
  if (data.rows.value.length === 0) {
    ElMessage.warning('暂无数据可导出')
    return
  }
  try {
    const { utils, writeFileXLSX } = await import('xlsx')
    const headers = ['序号', '索引号', '被询证单位', '回函方式', '回函日期', '寄回原件', '身份已确认', '身份确认方式', '邮箱已验证', '邮箱域名', '已致电', '电话来源', '可靠性结论', '备注']
    const rows = data.rows.value.map(r => [
      r.seq ?? '',
      r.confirm_index ?? '',
      r.entity_name ?? '',
      r.reply_method ?? '',
      r.reply_date ?? '',
      r.original_returned ?? '',
      r.identity_verified ? '是' : r.identity_verified === false ? '否' : '',
      r.identity_method ?? '',
      r.email_verified ? '是' : r.email_verified === false ? '否' : '',
      r.email_domain ?? '',
      r.phone_called ? '是' : r.phone_called === false ? '否' : '',
      r.phone_source ?? '',
      r.conclusion_status ?? '',
      r.reliability_note ?? '',
    ])
    const ws = utils.aoa_to_sheet([headers, ...rows])
    ws['!cols'] = [
      { wch: 6 }, { wch: 10 }, { wch: 25 }, { wch: 10 }, { wch: 12 },
      { wch: 8 }, { wch: 10 }, { wch: 12 }, { wch: 10 }, { wch: 14 },
      { wch: 8 }, { wch: 10 }, { wch: 14 }, { wch: 20 },
    ]
    const wb = utils.book_new()
    utils.book_append_sheet(wb, ws, '可靠性验证数据')
    writeFileXLSX(wb, 'D0-7回函可靠性验证_数据导出.xlsx')
    ElMessage.success('数据已导出')
  } catch (e: any) {
    ElMessage.error('导出失败：' + (e?.message || '未知错误'))
  }
}

function handleJumpD01(confirmIndex: string) {
  // TODO: 跨底稿跳转 D0-1
  console.log('[GtConfirmationReliability] 跳转 D0-1:', confirmIndex)
}

function handleAuditNoteUpdate(field: string, value: string) {
  ;(data.auditNote.value as any)[field] = value
  data.isDirty.value = true
}

function handleConclusionUpdate(field: string, value: any) {
  ;(data.conclusion.value as any)[field] = value
  data.isDirty.value = true
}

// 暴露给父组件通过 ref 调用（页面级工具栏转发）
defineExpose({
  handleExportTemplate: handleExportExcel,
  handleExportData,
  handleImport: handleImportExcel,
  handleImportClick: handleImportExcel,
  handleDownloadImportTemplate: handleExportExcel,
})
</script>

<style scoped>
.gt-confirmation-reliability {
  padding: 8px 0;
}

.gt-confirmation-reliability__legacy-notice {
  margin-bottom: 12px;
}
</style>
