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
      class="gas-table"
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
      <el-table-column label="期初未审" width="120" align="right">
        <template #default="{ row }">
          <span v-if="!row.isSection" class="gas-readonly-cell">{{ fmtNum(displayOpeningUnadjusted(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 期初审定（只读，computed = 期初未审 ?? 0） -->
      <el-table-column label="期初审定" width="120" align="right">
        <template #default="{ row }">
          <span v-if="!row.isSection" class="gas-readonly-cell">{{ fmtNum(openingAudited(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 本期未审（只读，TB；合计行汇总） -->
      <el-table-column label="本期未审" width="120" align="right">
        <template #default="{ row }">
          <span v-if="!row.isSection" class="gas-readonly-cell">{{ fmtNum(displayCurrentUnadjusted(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 账项调整（可编辑；合计行汇总只读） -->
      <el-table-column label="账项调整" width="130" align="right">
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
      <el-table-column label="重分类" width="130" align="right">
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
      <el-table-column label="审定数" width="120" align="right">
        <template #default="{ row }">
          <span v-if="!row.isSection" class="gas-auto-cell">{{ fmtNum(auditedAmount(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 变动额（自动计算，紫色） -->
      <el-table-column label="变动额" width="120" align="right">
        <template #default="{ row }">
          <span v-if="!row.isSection" class="gas-auto-cell">{{ fmtNum(changeAmount(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 变动率（自动计算，紫色，百分比） -->
      <el-table-column label="变动率" width="100" align="right">
        <template #default="{ row }">
          <span v-if="!row.isSection" class="gas-auto-cell">{{ fmtRate(changeRate(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 原因分析（可编辑） -->
      <el-table-column label="原因" min-width="180">
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
    </el-table>

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
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmDangerous } from '@/utils/confirm'
import { useFullscreen } from '@/composables/useFullscreen'
import { useExcelIO, type ExcelColumn } from '@/composables/useExcelIO'

// ─── Types ───
export interface AuditSheetSchema {
  [key: string]: any
}

/**
 * 审定表行（结构化）
 * - 持久化部分：item/indent/bold/isSection/isComputed/account_code +
 *   用户编辑列 adj_amount/reclass_amount/reason
 * - 运行时合并（不持久化）：TB 实时取数 opening_unadjusted/current_unadjusted/sys_aje/sys_rje
 */
export interface AuditSheetRow {
  id: string
  item: string
  indent?: number
  bold?: boolean
  isComputed?: boolean
  isSection?: boolean
  /** 用户自定义新增行（Task 17）：项目名可编辑，持久化完整数据 */
  isCustom?: boolean
  account_code?: string | null
  // ─── 用户编辑列（持久化）───
  adj_amount?: number | null
  reclass_amount?: number | null
  reason?: string
  // ─── TB 实时值（运行时合并，不持久化）───
  opening_unadjusted?: number | null
  current_unadjusted?: number | null
  sys_aje?: number | null
  sys_rje?: number | null
  [key: string]: any
}

/** TB 实时取数值（运行时合并，不持久化） */
export interface AuditSheetTbValue {
  opening_unadjusted?: number | null
  current_unadjusted?: number | null
  sys_aje?: number | null
  sys_rje?: number | null
}

export interface AuditSheetHtmlData {
  audit_rows?: AuditSheetRow[]
  tb_values?: Record<string, AuditSheetTbValue>
  [key: string]: any
}

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

// ─── 响应式表数据 ───
const tableData = ref<AuditSheetRow[]>([])

/**
 * 从 htmlData 构建 tableData：
 *   audit_rows 的浅拷贝 + 合并对应的 tb_values[row.id] 只读展示字段。
 *
 * 简单合并版本（Task 9）：直接把 tb_values 的 TB 字段挂到行上供 computed 使用。
 * 完整的 adj_amount ?? sys_aje ?? 0 回退逻辑在 Task 14 细化，这里保持干净。
 */
function buildTableData() {
  const rows = Array.isArray(props.htmlData?.audit_rows) ? props.htmlData.audit_rows : []
  const tbValues = props.htmlData?.tb_values || {}
  tableData.value = rows.map((row) => {
    const tb = tbValues[row.id] || {}
    return {
      ...row,
      indent: row.indent ?? 0,
      isCustom: row.isCustom ?? false,
      adj_amount: row.adj_amount ?? null,
      reclass_amount: row.reclass_amount ?? null,
      reason: row.reason ?? '',
      // 合并 TB 只读展示字段（行内已有值优先，避免覆盖测试/持久化注入）
      opening_unadjusted: row.opening_unadjusted ?? tb.opening_unadjusted ?? null,
      current_unadjusted: row.current_unadjusted ?? tb.current_unadjusted ?? null,
      sys_aje: row.sys_aje ?? tb.sys_aje ?? null,
      sys_rje: row.sys_rje ?? tb.sys_rje ?? null,
    }
  })
}

buildTableData()
watch(() => props.htmlData, () => buildTableData(), { deep: true })

// ─── 行类型判定 ───
/** 分节行/合计行/标记 bold 的行加粗 */
function isBoldRow(row: AuditSheetRow): boolean {
  return !!(row.bold || row.isSection || row.isComputed)
}

/** 可编辑行：非分节行、非合计行（合计行由 computed 汇总，不可编辑） */
function isEditableRow(row: AuditSheetRow): boolean {
  return !row.isSection && !row.isComputed
}

// ─── 数值工具 ───
function num(v: unknown): number {
  if (v == null || v === '') return 0
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── 自动计算（per row）───
/**
 * 明细行集合（非分节、非合计）——合计行（isComputed）汇总的来源。
 * isEditableRow 同义（分节/合计行不可编辑也不参与被汇总）。
 */
function detailRows(): AuditSheetRow[] {
  return tableData.value.filter((r) => !r.isSection && !r.isComputed)
}

/** 对所有明细行套用 accessor 求和（合计行汇总用）。 */
function sumOverDetails(accessor: (row: AuditSheetRow) => number): number {
  return detailRows().reduce((acc, r) => acc + num(accessor(r)), 0)
}

/**
 * 期初审定 = 期初未审 ?? 0（简单方案；Task 14 增强跨年审定取值）。
 * 合计行（isComputed）→ 汇总所有明细行的期初审定（Task 17）。
 */
function openingAudited(row: AuditSheetRow): number {
  if (row.isComputed) return sumOverDetails((r) => openingAudited(r))
  return num(row.opening_unadjusted)
}

/**
 * 有效账项调整值（Task 14 用户覆盖回退逻辑）：
 *   用户编辑值优先，未编辑（null/undefined）时回退系统汇总 AJE（sys_aje），仍无则 0。
 * 用 ?? 链而非 ||：保证「用户显式填 0」覆盖系统值（0 不是 nullish，不会回退到 sys_aje）。
 *   - adj_amount === null/undefined → 用 sys_aje
 *   - adj_amount === 0（用户显式填 0）→ 用 0（不回退）
 *   - sys_aje === null/undefined → 用 0
 */
function effectiveAdj(row: AuditSheetRow): number {
  return row.adj_amount ?? row.sys_aje ?? 0
}

/** 有效重分类调整值：同 effectiveAdj，回退系统汇总 RJE（sys_rje）。 */
function effectiveReclass(row: AuditSheetRow): number {
  return row.reclass_amount ?? row.sys_rje ?? 0
}

/**
 * 审定数 = 本期未审 + 有效账项调整 + 有效重分类
 *   有效调整 = 用户编辑值 ?? 系统汇总值 ?? 0（Task 14）
 * 注意：不能用 num() 预先归一 adj_amount/sys_aje——num 把 null 归 0 会丢失
 *   「未编辑」与「显式填 0」的区别，破坏 ?? 回退语义。必须先走 ?? 链再用 num 兜底。
 * 合计行（isComputed）→ 汇总所有明细行的审定数（Task 17）。
 */
function auditedAmount(row: AuditSheetRow): number {
  if (row.isComputed) return sumOverDetails((r) => auditedAmount(r))
  return num(row.current_unadjusted) + num(effectiveAdj(row)) + num(effectiveReclass(row))
}

/** 变动额 = 审定数 - 期初审定 */
function changeAmount(row: AuditSheetRow): number {
  return auditedAmount(row) - openingAudited(row)
}

/** 变动率 = 变动额 ÷ 期初审定（期初审定为 0 时返回 null，显示 —） */
function changeRate(row: AuditSheetRow): number | null {
  const base = openingAudited(row)
  if (base === 0) return null
  return changeAmount(row) / base
}

// ─── 列展示值（合计行 Task 17 汇总，明细行取本行原值）───
/**
 * 合计行（isComputed）的列展示对明细行求和；其余行返回原值（可能 null → 显示 —）。
 * 注意：账项调整/重分类汇总用 effectiveAdj/effectiveReclass（含系统 AJE/RJE 回退），
 * 与 auditedAmount 的汇总口径一致，保证合计行「审定数 = 本期未审 + 调整 + 重分类」成立。
 */
function displayOpeningUnadjusted(row: AuditSheetRow): number | null {
  if (row.isComputed) return sumOverDetails((r) => num(r.opening_unadjusted))
  return row.opening_unadjusted ?? null
}

function displayCurrentUnadjusted(row: AuditSheetRow): number | null {
  if (row.isComputed) return sumOverDetails((r) => num(r.current_unadjusted))
  return row.current_unadjusted ?? null
}

function displayAdj(row: AuditSheetRow): number | null {
  if (row.isComputed) return sumOverDetails((r) => effectiveAdj(r))
  return row.adj_amount ?? null
}

function displayReclass(row: AuditSheetRow): number | null {
  if (row.isComputed) return sumOverDetails((r) => effectiveReclass(r))
  return row.reclass_amount ?? null
}

// ─── 显示格式化 ───
/** 千分位 + 会计风格：null/undefined 显示 —（0 正常显示） */
function fmtNum(v: number | null | undefined): string {
  if (v == null || (typeof v === 'number' && Number.isNaN(v))) return '—'
  const n = typeof v === 'number' ? v : Number(v)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 变动率百分比：null 显示 — */
function fmtRate(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  return (Number(v) * 100).toFixed(2) + '%'
}

// ─── 系统参考值提示（Task 14）───
/**
 * 账项调整 el-input-number 的 placeholder：用户未填时显示系统汇总 AJE 作参考。
 *   - 有 sys_aje（含 0）→ 显示该值（用户可见正在被回退使用的系统参考值）
 *   - 无 sys_aje → 显示 '—'
 * 说明：placeholder 仅提示，不写入 v-model；实际回退由 effectiveAdj 的 ?? 链完成。
 */
function adjPlaceholder(row: AuditSheetRow): string {
  return row.sys_aje == null ? '—' : fmtNum(row.sys_aje)
}

/** 重分类 el-input-number 的 placeholder：用户未填时显示系统汇总 RJE 作参考。 */
function reclassPlaceholder(row: AuditSheetRow): string {
  return row.sys_rje == null ? '—' : fmtNum(row.sys_rje)
}

// ─── 编辑事件 ───
function onFieldChange(row: AuditSheetRow, field: string, value: unknown) {
  if (props.readonly) return
  // el-input-number 清空时回传 undefined，统一归一为 null
  const normalized = value === undefined ? null : value
  ;(row as Record<string, unknown>)[field] = normalized
  emit('field-change', { rowId: row.id, field, value: normalized })
}

// ─── 保存（持久化分层）───
/**
 * 仅持久化的行结构字段（保存时保留）。
 * 显式 **剔除** TB 实时值（opening_unadjusted/current_unadjusted/sys_aje/sys_rje）
 * 与任何 computed/transient 字段——下次加载时由后端重新从 trial_balance 查。
 */
const PERSISTED_ROW_KEYS = [
  // 行结构
  'id',
  'item',
  'indent',
  'bold',
  'isSection',
  'isComputed',
  'isCustom',
  'account_code',
  // 用户编辑列
  'adj_amount',
  'reclass_amount',
  'reason',
] as const

/**
 * 构建保存载荷：把 tableData 映射为「剥离 TB 实时值」的 audit_rows。
 *
 * 返回的对象即写入 parsed_data.html_data[sheet_name] 的内容（design Req 4.2）。
 * 注意：不含 sheet_name——GtWpRenderer.onSave 会用 activeSheetName 包装成
 * SavePayload（避免子组件持有过期 sheet_name）；也不含 tb_values（TB 加载时重查）。
 */
function buildSavePayload(): AuditSheetHtmlData {
  const auditRows: AuditSheetRow[] = tableData.value.map((row) => {
    const stripped: Record<string, unknown> = {}
    for (const key of PERSISTED_ROW_KEYS) {
      if (row[key] !== undefined) stripped[key] = row[key]
    }
    return stripped as AuditSheetRow
  })
  return { audit_rows: auditRows }
}

/** 保存：emit 剥离后的 audit_rows，落库（POST /save）由父组件链路完成。 */
function onSave() {
  if (props.readonly) return
  emit('save', buildSavePayload())
}

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

// ─── 导入导出（Task 16，复用 useExcelIO）───────────────────────────────────
const { exportTemplate: _exportTemplate, onFileSelected: _onFileSelected } = useExcelIO()

/** 导入用 sheet 名（导出模板与解析都用同一名，保证按名匹配） */
const IMPORT_SHEET_NAME = '审定表'

/** 导出模板/数据时的列定义（行项目名 + 列标题）。
 *  项目列承载行名（导入按此匹配），数值列即三个可编辑列 + 参考性的未审/审定列。
 *  注意：导入仅写回可编辑列（账项调整/重分类/原因），其余列导出仅供离线查看。 */
const EXPORT_COLUMNS: ExcelColumn[] = [
  { key: 'seq', header: '序号', width: 6 },
  { key: 'item', header: '项目', width: 28, note: '请勿修改，系统按项目名匹配导入' },
  { key: 'opening_unadjusted', header: '期初未审数', width: 14 },
  { key: 'opening_audited', header: '期初审定数', width: 14 },
  { key: 'current_unadjusted', header: '本期未审数', width: 14 },
  { key: 'adj_amount', header: '账项调整', width: 14, note: '可填写' },
  { key: 'reclass_amount', header: '重分类调整', width: 14, note: '可填写' },
  { key: 'audited_amount', header: '审定数', width: 14 },
  { key: 'reason', header: '原因分析', width: 24, note: '可填写' },
]

/** 文件选择器 ref */
const fileInputRef = ref<HTMLInputElement | null>(null)

/** 导入预览弹窗状态 */
const importVisible = ref(false)
const importStats = ref<{ matched: number; skipped: number } | null>(null)
const importPreviewRows = ref<Array<{ item: string; adj_amount: number | null; reclass_amount: number | null; reason: string }>>([])
/** 项目名 → 解析出的可编辑列值，确认导入时按行名写回 */
const importParsedMap = ref<Map<string, { adj_amount: number | null; reclass_amount: number | null; reason: string }>>(new Map())

/** 解析数值：空/非法 → null（保留 0），用于导入单元格 */
function parseNum(v: unknown): number | null {
  if (v == null || v === '') return null
  const n = typeof v === 'number' ? v : Number(String(v).replace(/,/g, ''))
  return Number.isFinite(n) ? n : null
}

/**
 * 导出模板：生成 xlsx（行项目名 + 列标题）供离线填写。
 * 复用 useExcelIO.exportTemplate——把当前 tableData 作为现有数据行写入（含 TB 实时值与
 * computed 派生列供查看），项目名在第 2 列，导入时按此匹配。
 * 只读操作，readonly 下仍可用。
 */
async function onExportTemplate() {
  const existingData: any[][] = tableData.value.map((row, idx) => [
    row.isSection ? '' : String(idx + 1),
    row.item ?? '',
    row.opening_unadjusted ?? '',
    row.isSection ? '' : openingAudited(row),
    row.current_unadjusted ?? '',
    row.adj_amount ?? '',
    row.reclass_amount ?? '',
    row.isSection ? '' : auditedAmount(row),
    row.reason ?? '',
  ])
  await _exportTemplate({
    columns: EXPORT_COLUMNS,
    sheetName: IMPORT_SHEET_NAME,
    fileName: `审定表_${props.sheetName || '模板'}.xlsx`,
    existingData,
    includeNoteRow: false,
    includeInstructions: true,
    instructionTitle: '审定表 — 填写说明',
    instructionRows: [
      ['1. 在「审定表」工作表填写，不要修改 sheet 名称'],
      ['2. 「项目」列文字不要修改，系统按项目名匹配导入'],
      ['3. 仅「账项调整 / 重分类调整 / 原因分析」三列会被导入，其余列为只读/自动计算'],
      ['4. 金额填数字，不要带逗号或货币符号'],
    ],
  })
}

/** 触发隐藏文件选择器 */
function triggerImport() {
  if (props.readonly) return
  fileInputRef.value?.click()
}

/**
 * 文件选择 → 解析 → 构建匹配预览。
 * 按行名（项目列）匹配 tableData 中可编辑行（非分节/非合计），匹配成功累加 matched，
 * 否则 skipped。解析结果暂存 importParsedMap，确认后才写回（confirmImport）。
 */
async function onFileSelected(e: Event) {
  if (props.readonly) return
  await _onFileSelected(
    e,
    (result) => {
      const parsed = new Map<string, { adj_amount: number | null; reclass_amount: number | null; reason: string }>()
      let matched = 0
      let skipped = 0
      // headers 顺序与 EXPORT_COLUMNS 一致：[序号, 项目, 期初未审, 期初审定, 本期未审, 账项调整, 重分类调整, 审定数, 原因分析]
      const H = result.headers
      const col = (label: string) => H.find((h) => h === label) || ''
      const itemKey = col('项目')
      const adjKey = col('账项调整')
      const reclassKey = col('重分类调整')
      const reasonKey = col('原因分析')
      for (const r of result.rows) {
        const itemName = String(r[itemKey] ?? '').trim()
        if (!itemName) {
          skipped++
          continue
        }
        const target = tableData.value.find((row) => row.item === itemName)
        if (!target || !isEditableRow(target)) {
          skipped++
          continue
        }
        parsed.set(itemName, {
          adj_amount: parseNum(r[adjKey]),
          reclass_amount: parseNum(r[reclassKey]),
          reason: String(r[reasonKey] ?? '').trim(),
        })
        matched++
      }
      importParsedMap.value = parsed
      importStats.value = { matched, skipped }
      importPreviewRows.value = Array.from(parsed.entries())
        .slice(0, 10)
        .map(([item, v]) => ({ item, ...v }))
      importVisible.value = true
    },
    { sheetName: IMPORT_SHEET_NAME, skipRows: 1 },
  )
}

/**
 * 确认导入：按行名把解析值写回 tableData 的可编辑列（仅 adj_amount/reclass_amount/reason）。
 * 不触碰 TB 只读列与 computed 列。写回后逐行 emit field-change（与手动编辑一致），
 * 不自动保存——用户仍需点「保存」落库。
 */
function confirmImport() {
  if (props.readonly) return
  let count = 0
  for (const row of tableData.value) {
    if (!isEditableRow(row)) continue
    const entry = importParsedMap.value.get(row.item)
    if (!entry) continue
    row.adj_amount = entry.adj_amount
    row.reclass_amount = entry.reclass_amount
    row.reason = entry.reason
    emit('field-change', { rowId: row.id, field: 'adj_amount', value: entry.adj_amount })
    emit('field-change', { rowId: row.id, field: 'reclass_amount', value: entry.reclass_amount })
    emit('field-change', { rowId: row.id, field: 'reason', value: entry.reason })
    count++
  }
  importVisible.value = false
  importStats.value = null
  importParsedMap.value = new Map()
  importPreviewRows.value = []
  ElMessage.success(`已导入 ${count} 行数据，请点击「保存」生效`)
}

// ─── 行操作（Task 17：新增行 / 多选 / 批量删除）──────────────────────────
/** el-table 实例 ref（批量删除后清空勾选用） */
const tableRef = ref<any>(null)

/** 当前多选选中的行（仅可编辑行可被选中，见 isRowSelectable） */
const selectedRows = ref<AuditSheetRow[]>([])

/** 自增计数器：保证新增行 id 唯一，避免与现有 row-{n} 及多次新增冲突 */
let rowSeq = 0

/**
 * 生成唯一行 id：row-custom-{timestamp}-{seq}。
 * 用 timestamp + 自增 seq 双保险——同一毫秒内连续新增也不会撞 id。
 * 前缀 custom 与模板行 row-{n} 区分，便于排查。
 */
function nextRowId(): string {
  rowSeq += 1
  return `row-custom-${Date.now()}-${rowSeq}`
}

/** 多选可选性：仅可编辑行（非分节、非合计）可勾选——保护汇总/分节结构不被删 */
function isRowSelectable(row: AuditSheetRow): boolean {
  return isEditableRow(row)
}

/** el-table selection-change 回调：同步选中行集合 */
function onSelectionChange(rows: AuditSheetRow[]) {
  selectedRows.value = Array.isArray(rows) ? rows : []
}

/**
 * 新增行（Req 6.1）：在表格尾部追加一个空的可编辑自定义行。
 * - isCustom=true → 项目名可编辑、保存时持久化完整数据（区别于 TB 来源行）
 * - 不带 account_code（无 TB 取数），未审列显示 —，用户手填调整/原因
 * readonly 时不生效。
 */
function addRow() {
  if (props.readonly) return
  const row: AuditSheetRow = {
    id: nextRowId(),
    item: '',
    indent: 1,
    bold: false,
    isSection: false,
    isComputed: false,
    isCustom: true,
    account_code: null,
    adj_amount: null,
    reclass_amount: null,
    reason: '',
    opening_unadjusted: null,
    current_unadjusted: null,
    sys_aje: null,
    sys_rje: null,
  }
  tableData.value.push(row)
}

/**
 * 批量删除（Req 6.2）：删除当前选中的可编辑行（合计/分节行不可选 → 不会被删）。
 * 二次确认（confirmDangerous）→ 按 id 集合过滤 tableData → 清空勾选。
 * 删除仅改内存 tableData，用户仍需点「保存」落库。readonly / 无选中时不生效。
 */
async function batchDelete() {
  if (props.readonly) return
  if (!selectedRows.value.length) return
  try {
    await confirmDangerous(
      `确定删除选中的 ${selectedRows.value.length} 行？删除后需点击「保存」生效。`,
      '批量删除确认',
    )
  } catch {
    // 用户取消
    return
  }
  const removeIds = new Set(selectedRows.value.map((r) => r.id))
  const before = tableData.value.length
  tableData.value = tableData.value.filter((r) => !removeIds.has(r.id))
  const removed = before - tableData.value.length
  selectedRows.value = []
  // 清空 el-table 内部勾选状态（避免残留高亮）
  tableRef.value?.clearSelection?.()
  ElMessage.success(`已删除 ${removed} 行，请点击「保存」生效`)
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
</style>
