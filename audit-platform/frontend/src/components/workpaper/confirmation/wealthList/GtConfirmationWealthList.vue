<template>
  <div class="gt-confirmation-wealth-list">
    <!-- 旧格式降级只读 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-wealth-list__legacy">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需按新版录入请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <template v-else>
      <WealthListDashboard :metrics="data.metrics.value" />

      <WealthListGrid
        :rows="data.rows.value"
        :readonly="readonly"
        :is-dirty="data.isDirty.value"
        :get-row-quality-status="data.getRowQualityStatus"
        @add="data.addRow"
        @delete="data.deleteRows"
        @update="data.updateField"
        @save="handleSave"
        @import-excel="handleImportClick"
        @export-template="handleExportTemplate"
        @export-data="handleExportData"
        @jump-summary="handleJumpSummary"
      />

      <WealthListConclusion
        :audit-note="data.auditNote.value"
        :conclusion="data.conclusion.value"
        :readonly="readonly"
        :metrics="data.metrics.value"
        @update-note="handleNoteUpdate"
        @update-conclusion="handleConclusionUpdate"
      />
    </template>

    <input
      ref="importFileInput"
      type="file"
      accept=".xlsx,.xls,.csv"
      style="display:none"
      @change="handleImportFile"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * GtConfirmationWealthList — E0-6 理财产品发函记录表（componentType: confirmation-wealth-list）
 *
 * 形态对齐 D0 函证家族（宿主 + 看板 + 网格 + 审计说明结论），源模板真源见 wealthListTypes.ts。
 * 本表在 E0 内的位置：E0-3/E0-4/E0-5/E0-6 四张发函记录表之一，
 * 经「索引号 + 产品名称」两个键汇入 E0-1「发函金额（原币）」。
 */
import { ref, computed, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { exportMultiSheetData, parseFile } from '@/composables/useExcelIO'
import { useWealthListData } from './composables/useWealthListData'
import { WEALTH_LIST_COLUMN_SOURCE, type WealthProductRow } from './wealthListTypes'
import { navigateToCycleSheet } from '../coordination/navigateToCycleSheet'

import WealthListDashboard from './WealthListDashboard.vue'
import WealthListGrid from './WealthListGrid.vue'
import WealthListConclusion from './WealthListConclusion.vue'

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

// setup 顶层取 router：写进函数体会拿不到（setup 作用域 composable 铁律，
// 实测过写进函数体 → 跳转在发请求前就抛错、零网络请求且四层验证全绿）
const router = useRouter()

const htmlDataRef = computed(() => props.htmlData)
const isNewFormat = computed(
  () => !props.htmlData || !!props.htmlData?._format || Object.keys(props.htmlData || {}).length === 0,
)

const data = useWealthListData({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
  defaultCutoffDate: () => props.htmlData?.project_context?.cutoff_date,
})

function handleSave() {
  emit('save', data.buildPayload())
}

function handleNoteUpdate(field: string, value: string) {
  ;(data.auditNote.value as any)[field] = value
  data.isDirty.value = true
}

function handleConclusionUpdate(field: string, value: any) {
  ;(data.conclusion.value as any)[field] = value
  data.isDirty.value = true
}

function handleJumpSummary() {
  const cycleBase = (props.wpCode || 'E0').split('-')[0]
  void navigateToCycleSheet({
    router,
    projectId: props.projectId,
    targetWpCode: `${cycleBase}-1`,
  })
}

// ─── 导入导出（列名取自源模板列对照，单一真源） ──────────────────────────────

const importFileInput = ref<HTMLInputElement | null>(null)
const SOURCE_LABELS = WEALTH_LIST_COLUMN_SOURCE.map((c) => c.label)

function handleImportClick() {
  importFileInput.value?.click()
}

async function handleImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    // 走 useExcelIO 单一入口（B2 批）。原实现 `sheet_to_json(ws)` 对象模式 + 取第一个 sheet。
    //
    // 🔴 本文件是「示例行判定不能套默认值」的样本：模板示例行首列是 `'E0-6-1'`（索引号），
    // 不是 `'示例'` —— `parseFile` 默认 `skipExamplePrefix:'示例'` 检查首列，**命中不到它**。
    // 原实现也没有示例行跳过逻辑（示例行靠用户手删，且其 product_name 含「示例理财产品名称」
    // 会被当真实数据导入）。故显式传 `''` 保持原行为，不得"顺手修好"。
    //
    // requireFirstCell 保持默认 true：本表首列是「索引号」（必填，模板说明列为关键列），
    // 与 D05/reliability 的「序号可留空」不同 —— 逐文件核对的意义就在这里。
    const { rows: rawRows } = await parseFile(file, {
      sheetName: '',
      skipRows: 1,
      skipExamplePrefix: '',
    })
    if (!rawRows.length) {
      ElMessage.warning('Excel 文件为空或无法解析')
      return
    }
    const parsed: Partial<WealthProductRow>[] = []
    for (const raw of rawRows) {
      const hasValue = Object.values(raw).some((v) => v != null && String(v).trim() !== '')
      if (!hasValue) continue
      const row: Partial<WealthProductRow> = {}
      for (const col of WEALTH_LIST_COLUMN_SOURCE) {
        const v = raw[col.label]
        if (v == null || String(v).trim() === '') continue
        if (col.field === 'units_held' || col.field === 'net_value') {
          const n = Number(String(v).replace(/,/g, ''))
          if (Number.isFinite(n)) (row as any)[col.field] = n
        } else {
          ;(row as any)[col.field] = String(v).trim()
        }
      }
      if (Object.keys(row).length) parsed.push(row)
    }
    if (!parsed.length) {
      ElMessage.warning('未识别到有效数据，请确认列头包含「产品名称」「产品净值」等源模板列名')
      return
    }
    const added = data.importRows(parsed)
    if (added === 0) {
      ElMessage.info('导入的产品已全部存在（按「索引号 + 产品名称」判重），无新增')
    } else {
      ElMessage.success(`成功导入 ${added} 只理财产品`)
    }
  } catch (e: any) {
    ElMessage.error('导入失败：' + (e?.message || '文件格式错误'))
  } finally {
    if (importFileInput.value) importFileInput.value.value = ''
  }
}

const COL_WIDTHS = [
  { wch: 12 }, { wch: 13 }, { wch: 26 }, { wch: 26 }, { wch: 20 },
  { wch: 8 }, { wch: 14 }, { wch: 16 }, { wch: 12 }, { wch: 12 }, { wch: 30 },
]

async function handleExportTemplate() {
  try {
    const example = [
      'E0-6-1', '2025-12-31', '示例：招商银行XX分行 / 收件人张三（请删除本行）',
      '示例理财产品名称', '封闭式', '人民币', 1000000, 1012345.67, '2025-06-30', '2026-06-29', '否',
    ]
    const instructions = [
      ['E0-6 理财产品发函记录表 — 导入模板说明'],
      [''],
      ['【列名请勿修改】第一行列名与源模板逐字一致，改名会导致该列无法识别。'],
      ['【示例行请删除】第 2 行为示例。'],
      [''],
      ['【两个关键列 —— 缺一则 E0-1 汇总不到金额】'],
      ['  索引号：本表行级索引（对应 E0-1「询证函索引号」）'],
      ['  产品名称：对应 E0-1「账号/理财产品名称」——理财产品无账号，源模板用产品名称作键'],
      [''],
      ['【金额口径】'],
      ['  产品净值：总额口径，直接汇入 E0-1「发函金额（原币）」'],
      ['  持有份额：仅作询证函正文补充信息，不参与金额计算（不要填单位净值再相乘）'],
      [''],
      ['【枚举列】'],
      ['  产品类型（封闭式/开放式）：封闭式 / 开放式'],
      ['  是否被用于担保或存在其他使用限制：是 / 否'],
      [''],
      ['【判重规则】'],
      ['  按「索引号 + 产品名称」判重，两者都相同的行不会重复导入。'],
      [''],
      ['【注意】本表没有「是否函证」列——入表即视为已决定发函的对象。'],
    ]
    await exportMultiSheetData({
      sheets: [
        { sheetName: '理财产品发函记录', rows: [SOURCE_LABELS, example], colWidths: COL_WIDTHS },
        { sheetName: '填写说明', rows: instructions, colWidths: [{ wch: 78 }] },
      ],
      fileName: 'E0-6理财产品发函记录表_导入模板.xlsx',
      applyStyles: false,
      successMessage: false,
    })
    ElMessage.success('模板已导出')
  } catch (e: any) {
    ElMessage.error('生成模板失败：' + (e?.message || '未知错误'))
  }
}

async function handleExportData() {
  if (!data.rows.value.length) {
    ElMessage.warning('暂无数据可导出')
    return
  }
  try {
    const body = data.rows.value.map((r) =>
      WEALTH_LIST_COLUMN_SOURCE.map((c) => {
        const v = (r as any)[c.field]
        return v == null ? '' : v
      }),
    )
    await exportMultiSheetData({
      sheets: [
        { sheetName: '理财产品发函记录', rows: [SOURCE_LABELS, ...body], colWidths: COL_WIDTHS },
      ],
      fileName: 'E0-6理财产品发函记录表_数据导出.xlsx',
      applyStyles: false,
      successMessage: false,
    })
    ElMessage.success('数据已导出')
  } catch (e: any) {
    ElMessage.error('导出失败：' + (e?.message || '未知错误'))
  }
}

defineExpose({
  handleExportTemplate,
  handleExportData,
  handleImport: handleImportClick,
  handleImportClick,
  handleDownloadImportTemplate: handleExportTemplate,
})
</script>

<style scoped>
.gt-confirmation-wealth-list {
  padding: 8px 0;
  font-size: 13px;
}

.gt-confirmation-wealth-list__legacy {
  margin-bottom: 12px;
}
</style>
