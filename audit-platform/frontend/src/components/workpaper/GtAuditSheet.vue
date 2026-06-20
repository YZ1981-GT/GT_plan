<!--
  GtAuditSheet.vue — 审定表核心可编辑表格组件（Task 9）

  componentType=`audit-sheet`，由 htmlRendererRegistry 注册、GtWpRenderer 按
  componentType 分发到此组件。仅 class_code=`F-审定表` 的 sheet 生效（其余
  F/G 类仍走 univer/GtGridSheet）。

  设计参照合并工作底稿 NetAssetSheet：
    - el-table border size="small" 结构化可编辑表
    - 可编辑列：账项调整 / 重分类（el-input-number）、原因（el-input）
    - 只读列：期初未审 / 期初审定 / 本期未审（从 tb_values 填）
    - 自动计算列（审定数 / 变动额 / 变动率）紫色标识（ws-auto-cell 同款）
    - 项目列缩进渲染 + 分节行(isSection)/合计行(isComputed)样式区分

  本任务范围（Task 9）：核心渲染 + 编辑 + 自动计算。
  Task 10 已补：保存按钮 + 持久化分层（仅持久化用户编辑列，剥离 TB 实时值）。
  Task 11 已补：工具栏全屏（useFullscreen）/ 公式（emit open-formula）/
    还原（confirmDangerous → emit restore，父组件重拉模板默认行）。
    NOT in scope：导入导出(Task 16) / 新增删除行(Task 17)。上述功能在后续任务补齐，
    此处仅保留 toolbar 扩展点（具名插槽 #toolbar）。

  TB 取数合并：tb_values[row.id] → 行只读展示字段（opening_unadjusted/current_unadjusted/
    sys_aje/sys_rje），仅供 computed 使用，不写入 v-model（只有 adj_amount/reclass_amount/
    reason 三列绑 v-model 可编辑）。
  Task 14 已补：用户覆盖回退逻辑——审定数 = 本期未审 + (adj_amount ?? sys_aje ?? 0)
    + (reclass_amount ?? sys_rje ?? 0)。即用户未编辑调整数时用系统汇总 AJE/RJE 作参考值；
    用户填了（含显式 0）则覆盖。系统参考值通过 el-input-number placeholder 提示给用户。

  ─── cross-ref:updated 订阅契约 ──────────────────────────────────
  本组件**不直接订阅** eventBus 'cross-ref:updated' 事件。跨底稿引用变化由
  useWpRenderer.ts（GtWpRenderer 父组件持有）统一监听 + 重拉 renderConfig，
  本组件通过 props 接收最新 htmlData 自动更新（单一订阅入口避免内存泄漏）。
-->

<template>
  <div class="gt-audit-sheet" :class="{ 'gt-fullscreen': isFullscreen }">
    <!-- 工具栏（全屏/公式/还原/保存 + 后续行操作插槽扩展点） -->
    <div class="gas-toolbar">
      <div class="gas-toolbar__title">审定表</div>
      <div class="gas-toolbar__actions">
        <!-- 全屏：始终可用（含 readonly），label 随状态切换；复用 useFullscreen 全局 .gt-fullscreen 样式 -->
        <el-button
          size="small"
          class="gas-btn-fullscreen"
          @click="toggleFullscreen"
        >{{ isFullscreen ? '⬜ 退出全屏' : '⛶ 全屏' }}</el-button>
        <!-- 公式：打开公式编辑（后续接 FormulaEditDialog）；编辑动作 → readonly 禁用 -->
        <el-button
          size="small"
          class="gas-btn-formula"
          :disabled="readonly"
          @click="onOpenFormula"
        >ƒx 公式</el-button>
        <!-- 还原：confirm 后 emit restore，由父组件（useWpRenderer）重拉模板默认行；编辑动作 → readonly 禁用 -->
        <el-button
          size="small"
          class="gas-btn-restore"
          :disabled="readonly"
          @click="onRestore"
        >🔄 还原</el-button>
        <!-- 一键刷新：从四表库预填充数据 -->
        <el-button
          size="small"
          class="gas-btn-refresh"
          :disabled="readonly"
          @click="onRefreshFromLedger"
        >📊 一键刷新</el-button>
        <span class="gas-btn-sep"></span>
        <!-- 导入导出（Task 16，复用 useExcelIO）：
             导出模板=行项目名+列标题供离线填写（只读操作，readonly 仍可用）；
             导入 Excel=按行名匹配 → 预览弹窗（匹配/跳过数）→ 确认后仅写入可编辑列。-->
        <el-button
          size="small"
          class="gas-btn-export"
          @click="onExportTemplate"
        >📥 导出模板</el-button>
        <el-button
          size="small"
          class="gas-btn-export-data"
          @click="onExportData"
        >📥 导出数据</el-button>
        <el-button
          size="small"
          class="gas-btn-import"
          :disabled="readonly"
          @click="triggerImport"
        >📤 导入 Excel</el-button>
        <span class="gas-btn-sep"></span>
        <!-- 行操作（Task 17）：+新增行（尾部追加空行）/ 批量删除（多选选中的可编辑行）。
             合计行（isComputed）/分节行（isSection）不可选 → 不会被删除（保护汇总结构）。-->
        <el-button
          size="small"
          class="gas-btn-addrow"
          :disabled="readonly"
          @click="addRow"
        >➕ 新增行</el-button>
        <el-button
          type="danger"
          size="small"
          class="gas-btn-delrow"
          :disabled="readonly || !selectedRows.length"
          @click="batchDelete"
        >🗑 批量删除{{ selectedRows.length ? `（${selectedRows.length}）` : '' }}</el-button>
        <span class="gas-btn-sep"></span>
        <!-- 行操作扩展插槽（保留给后续自定义工具） -->
        <slot name="toolbar" :table-data="tableData" />
        <!-- 保存：组件自身能力，直接内置（非插槽）。仅 emit，落库由父组件链路完成。 -->
        <el-button
          type="primary"
          size="small"
          :disabled="readonly"
          @click="onSave"
        >💾 保存</el-button>
      </div>
    </div>

    <el-empty
      v-if="!tableData.length"
      :image-size="80"
      description="审定表暂无行数据，请等待模板初始化或手动新增行"
    />

    <el-table
      v-else
      ref="tableRef"
      :data="tableData"
      border
      size="small"
      class="gas-table gt-compact-table gt-tb-font-md"
      row-key="id"
      :header-cell-style="headerStyle"
      :row-class-name="rowClassName"
      @selection-change="onSelectionChange"
    >
      <!-- 多选列（Task 17）：仅可编辑行（非分节/非合计）可勾选；合计/分节行保护不可删 -->
      <el-table-column
        type="selection"
        width="40"
        align="center"
        fixed
        :selectable="isRowSelectable"
      />

      <!-- 序号 -->
      <el-table-column label="序号" width="56" align="center" fixed>
        <template #default="{ row, $index }">
          <span v-if="!row.isSection">{{ $index + 1 }}</span>
        </template>
      </el-table-column>

      <!-- 项目（缩进 + 粗体）；自定义新增行可编辑项目名 -->
      <el-table-column label="项目" min-width="200" fixed show-overflow-tooltip>
        <template #default="{ row }">
          <el-input
            v-if="row.isCustom && isEditableRow(row)"
            v-model="row.item"
            size="small"
            :disabled="readonly"
            placeholder="请输入项目名称"
            @change="(v: string) => onFieldChange(row, 'item', v)"
          />
          <span
            v-else
            :style="{
              paddingLeft: (row.indent || 0) * 12 + 'px',
              fontWeight: isBoldRow(row) ? 700 : 400,
            }"
          >{{ row.item }}</span>
        </template>
      </el-table-column>

      <!-- 期初未审（只读，TB；合计行汇总） -->
      <el-table-column v-if="!isDynamicColumns" label="期初未审" width="120" align="right">
        <template #default="{ row }">
          <span v-if="!row.isSection" class="gas-readonly-cell">{{ fmtNum(displayOpeningUnadjusted(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 期初审定（只读，computed = 期初未审 ?? 0） -->
      <el-table-column v-if="!isDynamicColumns" label="期初审定" width="120" align="right">
        <template #default="{ row }">
          <span v-if="!row.isSection" class="gas-readonly-cell">{{ fmtNum(openingAudited(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 本期未审（只读，TB；合计行汇总） -->
      <el-table-column v-if="!isDynamicColumns" label="本期未审" width="120" align="right">
        <template #default="{ row }">
          <span v-if="!row.isSection" class="gas-readonly-cell">{{ fmtNum(displayCurrentUnadjusted(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 账项调整（可编辑；合计行汇总只读） -->
      <el-table-column v-if="!isDynamicColumns" label="账项调整" width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isEditableRow(row)"
            v-model="row.adj_amount"
            size="small"
            :precision="2"
            :controls="false"
            :disabled="readonly"
            :placeholder="adjPlaceholder(row)"
            style="width: 100%"
            @change="(v: number | undefined) => onFieldChange(row, 'adj_amount', v)"
          />
          <span v-else-if="!row.isSection" class="gas-readonly-cell">{{ fmtNum(displayAdj(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 重分类（可编辑；合计行汇总只读） -->
      <el-table-column v-if="!isDynamicColumns" label="重分类" width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="isEditableRow(row)"
            v-model="row.reclass_amount"
            size="small"
            :precision="2"
            :controls="false"
            :disabled="readonly"
            :placeholder="reclassPlaceholder(row)"
            style="width: 100%"
            @change="(v: number | undefined) => onFieldChange(row, 'reclass_amount', v)"
          />
          <span v-else-if="!row.isSection" class="gas-readonly-cell">{{ fmtNum(displayReclass(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 审定数（自动计算，紫色） -->
      <el-table-column v-if="!isDynamicColumns" label="审定数" width="120" align="right">
        <template #default="{ row }">
          <span v-if="!row.isSection" class="gas-auto-cell">{{ fmtNum(auditedAmount(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 变动额（自动计算，紫色） -->
      <el-table-column v-if="!isDynamicColumns" label="变动额" width="120" align="right">
        <template #default="{ row }">
          <span v-if="!row.isSection" class="gas-auto-cell">{{ fmtNum(changeAmount(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 变动率（自动计算，紫色，百分比） -->
      <el-table-column v-if="!isDynamicColumns" label="变动率" width="100" align="right">
        <template #default="{ row }">
          <span v-if="!row.isSection" class="gas-auto-cell">{{ fmtRate(changeRate(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 原因分析（可编辑） -->
      <el-table-column v-if="!isDynamicColumns" label="原因" min-width="180">
        <template #default="{ row }">
          <el-input
            v-if="isEditableRow(row)"
            v-model="row.reason"
            size="small"
            :disabled="readonly"
            placeholder="原因分析"
            @change="(v: string) => onFieldChange(row, 'reason', v)"
          />
          <span v-else-if="!row.isSection" class="gas-readonly-cell">{{ row.reason || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 动态列（多列明细表，列分组折叠） -->
      <!-- 期初区折叠按钮（折叠时显示，点击展开） -->
      <el-table-column
        v-if="isDynamicColumns && columnGroups.opening.length && openingGroupCollapsed"
        width="36"
        align="center"
        class-name="gas-col-expand-btn"
      >
        <template #header>
          <span class="gas-col-group-toggle" title="展开期初区" @click.stop="openingGroupCollapsed = false">▶</span>
        </template>
        <template #default>
          <span class="gas-col-group-toggle-cell">⋯</span>
        </template>
      </el-table-column>

      <!-- 期初区列（展开时显示） -->
      <el-table-column
        v-for="col in (isDynamicColumns && !openingGroupCollapsed ? columnGroups.opening : [])"
        :key="col.key"
        :label="col.label"
        :width="110"
        align="right"
      >
        <template #header>
          <span>{{ col.label }}</span>
          <span
            v-if="col === columnGroups.opening[columnGroups.opening.length - 1]"
            class="gas-col-group-toggle"
            title="收起期初区"
            @click.stop="openingGroupCollapsed = true"
          > ◀</span>
        </template>
        <template #default="{ row }">
          <el-input-number
            v-if="isEditableRow(row)"
            v-model="row[col.key]"
            size="small"
            :precision="2"
            :controls="false"
            :disabled="readonly"
            placeholder="—"
            style="width: 100%"
            @change="(v: number | undefined) => onFieldChange(row, col.key, v)"
          />
          <span v-else-if="!row.isSection" class="gas-readonly-cell">{{ fmtNum(row[col.key]) }}</span>
        </template>
      </el-table-column>

      <!-- 本期变动区（始终展开，核心编辑区） -->
      <el-table-column
        v-for="col in (isDynamicColumns ? columnGroups.current : [])"
        :key="col.key"
        :label="col.label"
        :width="110"
        align="right"
      >
        <template #default="{ row }">
          <el-input-number
            v-if="isEditableRow(row)"
            v-model="row[col.key]"
            size="small"
            :precision="2"
            :controls="false"
            :disabled="readonly"
            placeholder="—"
            style="width: 100%"
            @change="(v: number | undefined) => onFieldChange(row, col.key, v)"
          />
          <span v-else-if="!row.isSection" class="gas-readonly-cell">{{ fmtNum(row[col.key]) }}</span>
        </template>
      </el-table-column>

      <!-- 期末区（始终展开，最终关注区） -->
      <el-table-column
        v-for="col in (isDynamicColumns ? columnGroups.closing : [])"
        :key="col.key"
        :label="col.label"
        :width="110"
        align="right"
      >
        <template #default="{ row }">
          <el-input-number
            v-if="isEditableRow(row)"
            v-model="row[col.key]"
            size="small"
            :precision="2"
            :controls="false"
            :disabled="readonly"
            placeholder="—"
            style="width: 100%"
            @change="(v: number | undefined) => onFieldChange(row, col.key, v)"
          />
          <span v-else-if="!row.isSection" class="gas-readonly-cell">{{ fmtNum(row[col.key]) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 / 审计结论区 -->
    <div v-if="tableData.length" class="gas-sections">
      <div class="gas-section">
        <div class="gas-section__title">
          <span class="gas-section__badge">审计说明</span>
        </div>
        <p class="gas-section__hint">对期末与期初变动较大的项目（如变动率超过 30%）说明主要原因；记录质押、贴现、背书等特殊事项及其对财务报表的影响。</p>
        <el-input
          v-model="auditSections.notes"
          type="textarea"
          :rows="4"
          :disabled="readonly"
          :autosize="{ minRows: 3, maxRows: 12 }"
          placeholder="示例：本期应收票据期末净值较期初增加 XX 万元，增幅 XX%，主要原因为……；期末已质押票据 XX 万元，用途为……"
          @change="(v: string) => onSectionChange('notes', v)"
        />
      </div>
      <div class="gas-section">
        <div class="gas-section__title">
          <span class="gas-section__badge gas-section__badge--conclusion">审计结论</span>
        </div>
        <p class="gas-section__hint">明确发表是否认可被审计单位在财务报表中列报的本科目金额，如存在差异需说明原因及影响。</p>
        <el-input
          v-model="auditSections.conclusion"
          type="textarea"
          :rows="3"
          :disabled="readonly"
          :autosize="{ minRows: 2, maxRows: 10 }"
          placeholder="示例：经审计，我们认可被审计单位列报的应收票据期末余额 XX 万元，该金额与审定数一致，不存在需要调整的事项。"
          @change="(v: string) => onSectionChange('conclusion', v)"
        />
      </div>
    </div>

    <!-- 隐藏文件选择器（导入 Excel 触发） -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display: none"
      @change="onFileSelected"
    />

    <!-- 导入预览弹窗：匹配/跳过统计 + 前 N 行预览，确认后仅写入可编辑列 -->
    <el-dialog
      v-model="importVisible"
      title="导入审定表数据"
      width="720px"
      append-to-body
      class="gas-import-dialog"
    >
      <el-alert type="warning" :closable="false" style="margin-bottom: 12px">
        <template #title>
          <span>请使用「导出模板」填写后再导入。系统读取<b>「审定表」</b>工作表，按<b>项目名</b>匹配行，仅写入「账项调整 / 重分类 / 原因」三列（其余列为只读/自动计算）。请勿修改 sheet 名称和项目列。</span>
        </template>
      </el-alert>
      <div v-if="importStats">
        <p class="gas-import-summary">
          解析结果：匹配
          <b class="gas-import-matched">{{ importStats.matched }}</b>
          行，跳过
          <b class="gas-import-skipped">{{ importStats.skipped }}</b>
          行
        </p>
        <el-table
          v-if="importPreviewRows.length"
          :data="importPreviewRows"
          border
          size="small"
          max-height="300"
        >
          <el-table-column prop="item" label="项目" min-width="180" show-overflow-tooltip />
          <el-table-column prop="adj_amount" label="账项调整" width="120" align="right">
            <template #default="{ row }">{{ fmtNum(row.adj_amount) }}</template>
          </el-table-column>
          <el-table-column prop="reclass_amount" label="重分类" width="120" align="right">
            <template #default="{ row }">{{ fmtNum(row.reclass_amount) }}</template>
          </el-table-column>
          <el-table-column prop="reason" label="原因" min-width="160">
            <template #default="{ row }">{{ row.reason || '—' }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="未匹配到可导入的行" :image-size="60" />
      </div>
      <el-empty v-else description="未解析到有效数据" :image-size="60" />
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!importStats?.matched"
          @click="confirmImport"
        >确认导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmDangerous } from '@/utils/confirm'
import { useFullscreen } from '@/composables/useFullscreen'
import { useAuditSheetColumns } from '@/composables/useAuditSheetColumns'
import { useAuditSheetSections } from '@/composables/useAuditSheetSections'
import { useAuditSheetTable } from '@/composables/useAuditSheetTable'
import type {
  AuditSheetSchema,
  AuditSheetRow,
  AuditSheetHtmlData,
} from '@/components/workpaper/auditSheetTypes'

// ─── Types（从 auditSheetTypes 抽出，re-export 保向后兼容导入路径） ───
export type {
  AuditSheetSchema,
  AuditSheetRow,
  AuditSheetTbValue,
  AuditSheetSections,
  AuditSheetColumnDef,
  AuditSheetHtmlData,
} from '@/components/workpaper/auditSheetTypes'

// ─── Props / Emits ───
const props = withDefaults(
  defineProps<{
    wpId: string
    sheetName: string
    schema: AuditSheetSchema
    htmlData: AuditSheetHtmlData
    readonly?: boolean
  }>(),
  {
    readonly: false,
  },
)

const emit = defineEmits<{
  save: [data: AuditSheetHtmlData]
  'field-change': [payload: { rowId: string; field: string; value: unknown }]
  /** 打开公式编辑（后续接 FormulaEditDialog）；payload 携带 sheetName 上下文 */
  'open-formula': [payload: { sheetName: string }]
  /** 还原为模板默认行：组件无 render-config 取数能力，由父组件（useWpRenderer）重拉 */
  restore: []
}>()

// ─── 全屏（复用 useFullscreen，绑定全局 .gt-fullscreen 样式 + ESC 退出）───
const { isFullscreen, toggleFullscreen } = useFullscreen()

// ─── 动态列分组 + 期初区折叠（composable：useAuditSheetColumns）───
const {
  isDynamicColumns,
  dynamicColumnDefs,
  openingGroupCollapsed,
  columnGroups,
} = useAuditSheetColumns({
  htmlData: () => props.htmlData,
})

// ─── 审计说明 / 审计结论区（composable：useAuditSheetSections）───
const {
  auditSections,
  buildSections,
  onSectionChange,
} = useAuditSheetSections({
  htmlData: () => props.htmlData,
  readonly: () => props.readonly,
})

// ─── 表格数据 + 自动计算 + 保存 + 导入导出 + 行操作（composable：useAuditSheetTable）───
// 铁律：emit 仍由主组件持有，composable 经 emitFieldChange / emitSave 回调通知。
const {
  tableData,
  buildTableData,
  isBoldRow,
  isEditableRow,
  detailRows,
  sumOverDetails,
  openingAudited,
  effectiveAdj,
  effectiveReclass,
  auditedAmount,
  changeAmount,
  changeRate,
  displayOpeningUnadjusted,
  displayCurrentUnadjusted,
  displayAdj,
  displayReclass,
  fmtNum,
  fmtRate,
  adjPlaceholder,
  reclassPlaceholder,
  onFieldChange,
  buildSavePayload,
  onSave,
  onRefreshFromLedger,
  EXPORT_COLUMNS,
  IMPORT_SHEET_NAME,
  fileInputRef,
  importVisible,
  importStats,
  importPreviewRows,
  importParsedMap,
  parseNum,
  onExportTemplate,
  onExportData,
  triggerImport,
  onFileSelected,
  confirmImport,
  tableRef,
  selectedRows,
  nextRowId,
  isRowSelectable,
  onSelectionChange,
  addRow,
  batchDelete,
} = useAuditSheetTable({
  wpId: () => props.wpId,
  sheetName: () => props.sheetName,
  htmlData: () => props.htmlData,
  readonly: () => props.readonly,
  isDynamicColumns,
  dynamicColumnDefs,
  auditSections,
  emitFieldChange: (payload) => emit('field-change', payload),
  emitSave: (data) => emit('save', data),
})

// ─── 初始构建 + htmlData 变化时重建（行为不变：构建表 + 重建说明结论区）───
buildTableData()
watch(() => props.htmlData, () => { buildTableData(); buildSections() }, { deep: true })

// ─── 工具栏：公式 / 还原 ───
/**
 * 公式按钮：emit open-formula 携带 sheetName 上下文。
 * 后续接 FormulaEditDialog（由父组件监听打开）。readonly 时不触发。
 */
function onOpenFormula() {
  if (props.readonly) return
  emit('open-formula', { sheetName: props.sheetName })
}

/**
 * 还原按钮：二次确认后 emit restore。
 * 本组件 props 驱动、无 render-config 取数能力，由父组件（useWpRenderer）
 * 重新从后端拉取模板默认行并经 htmlData 回流。readonly 时不触发。
 */
async function onRestore() {
  if (props.readonly) return
  try {
    await confirmDangerous('还原将丢弃当前编辑，恢复模板默认行，是否继续？', '还原确认')
  } catch {
    // 用户取消
    return
  }
  emit('restore')
  ElMessage.success('正在恢复模板默认行…')
}

// ─── 表格样式 ───
const headerStyle = {
  background: 'var(--gt-color-primary-bg)',
  color: 'var(--gt-color-primary)',
  fontSize: 'var(--gt-font-size-xs)',
  fontWeight: '600',
  padding: '4px 0',
}

function rowClassName({ row }: { row: AuditSheetRow }) {
  if (row.isSection) return 'gas-row-section'
  if (row.isComputed) return 'gas-row-computed'
  if (isBoldRow(row)) return 'gas-row-bold'
  return ''
}

// ─── 测试/父组件可访问的接口 ───
defineExpose({
  tableData,
  isFullscreen,
  toggleFullscreen,
  openingAudited,
  effectiveAdj,
  effectiveReclass,
  auditedAmount,
  changeAmount,
  changeRate,
  detailRows,
  sumOverDetails,
  displayOpeningUnadjusted,
  displayCurrentUnadjusted,
  displayAdj,
  displayReclass,
  adjPlaceholder,
  reclassPlaceholder,
  isBoldRow,
  isEditableRow,
  buildTableData,
  buildSavePayload,
  onSave,
  onOpenFormula,
  onRestore,
  // ─── 导入导出（Task 16）───
  onExportTemplate,
  triggerImport,
  onFileSelected,
  confirmImport,
  importVisible,
  importStats,
  importPreviewRows,
  importParsedMap,
  parseNum,
  EXPORT_COLUMNS,
  IMPORT_SHEET_NAME,
  // ─── 行操作（Task 17）───
  tableRef,
  selectedRows,
  isRowSelectable,
  onSelectionChange,
  addRow,
  batchDelete,
  nextRowId,
})
</script>

<style scoped>
.gt-audit-sheet {
  padding: 16px;
}

.gas-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  gap: 8px;
  flex-wrap: wrap;
}
.gas-toolbar__title {
  font-size: var(--gt-font-size-base);
  font-weight: 600;
  color: var(--gt-color-primary);
}
.gas-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 工具栏按钮分隔线（与 NetAssetSheet .ws-btn-sep 一致） */
.gas-btn-sep {
  width: 1px;
  height: 18px;
  background: var(--gt-color-border-light);
  margin: 0 2px;
  flex-shrink: 0;
}

/* 只读 TB / 派生展示值 */
.gas-readonly-cell {
  display: block;
  text-align: right;
  padding: 0 4px;
  color: var(--gt-color-text-regular);
  font-variant-numeric: tabular-nums;
}

/* 自动计算列（GT 紫，与 NetAssetSheet ws-auto-cell 一致） */
.gas-auto-cell {
  display: block;
  text-align: right;
  padding: 2px 8px;
  color: var(--gt-color-primary);
  font-weight: 500;
  font-size: var(--gt-font-size-xs);
  font-variant-numeric: tabular-nums;
}

/* 可编辑单元格内的数字右对齐 */
.gas-table :deep(.el-input__inner) {
  text-align: right;
}

/* 表头紫底 */
.gas-table :deep(.el-table__header-wrapper th) {
  background: var(--gt-color-primary-bg);
}

/* 分节行（一/二/三）：淡紫底 + 粗体 + 左侧紫色边线 */
.gas-table :deep(.gas-row-section td) {
  background: var(--gt-color-primary-bg) !important;
  font-weight: 700;
  border-bottom: 1px solid var(--gt-color-border-purple);
}

/* 合计行：粗体 + 双层上边框区分 */
.gas-table :deep(.gas-row-computed td) {
  font-weight: 700;
  background: var(--gt-color-bg-elevated) !important;
  border-top: 2px solid var(--gt-color-border-purple-mid);
}

/* 普通粗体行 */
.gas-table :deep(.gas-row-bold td) {
  font-weight: 600;
}

/* 行 hover 浅紫底 */
.gas-table :deep(.el-table__body tr:hover > td) {
  background: var(--gt-color-bg-purple-hover) !important;
}

/* 审计说明/结论区 */
.gas-sections { margin-top: 16px; display: flex; flex-direction: column; gap: 14px; }
.gas-section { border: 1px solid var(--gt-color-border-purple-light); border-radius: 6px; padding: 10px 12px; }
.gas-section__title { display: flex; align-items: center; gap: 8px; font-weight: 600; color: var(--gt-color-primary); margin-bottom: 8px; }
.gas-section__badge { padding: 1px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; color: #fff; background: var(--gt-color-primary); }
.gas-section__badge--conclusion { background: var(--gt-color-warning, #e6a23c); }
.gas-section__hint { font-size: 12px; color: var(--gt-color-text-secondary, #909399); margin: 0 0 8px 0; line-height: 1.5; }

/* 列分组折叠 */
.gas-col-group-toggle { cursor: pointer; font-size: 12px; color: var(--gt-color-primary); user-select: none; padding: 0 2px; }
.gas-col-group-toggle:hover { color: var(--gt-color-primary-dark, #3a1f5e); }
.gas-col-group-toggle-cell { color: var(--gt-color-text-placeholder, #c0c4cc); font-size: 11px; }
.gas-table :deep(.gas-col-expand-btn) { padding: 0 !important; min-width: 36px !important; }
</style>
