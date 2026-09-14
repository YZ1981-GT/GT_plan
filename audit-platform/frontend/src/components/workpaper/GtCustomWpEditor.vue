<!--
  GtCustomWpEditor.vue — 自定义底稿编辑视图（componentType=custom）

  spec: custom-workpaper-dual-mode-formula-and-batch Wave 3 Task 9

  ## 架构口径：xlsx 权威 + 单向投影
  自定义底稿是**自由网格**，HTML 侧与 OnlyOffice 侧编的是同一批单元格，故不能照抄
  标准循环底稿「两侧各存一份、切回靠 reloadAll 重拉」的范式（那些底稿 HTML 侧是
  结构化表单，与 xlsx 网格编的不是同一批东西，两侧不共享数据也不会打架）。

  本组件的双模式约定：
    - HTML 侧编辑 → `PUT /custom-cells`（先写 xlsx，再刷投影）
    - OO 侧编辑   → WOPI 直编 xlsx 本体
    - **切回 HTML 时必须 `POST /custom-refresh-projection`** —— 这是「OO 改动能被
      HTML 侧看见」的唯一通路（平台既有双模式无 xlsx→html_data 反向同步）。

  🔴 用参数化工厂 `createDualMode`（取值 `'html' | 'onlyoffice'`），**禁用
     `useD1DualMode`** —— 它的取值是 `'html' | 'oo'`，与其余 40+ 处不统一，
     选错会与既有 localStorage 持久化值冲突。
  🔴 `el-segmented` 用 `:model-value` + `@change`，**禁用 `v-model`** ——
     v-model 会先改值，使 `switchMode` 的 `if (target === currentMode.value) return`
     守卫短路，模式切换的副作用（刷投影）永不执行。
-->
<template>
  <div class="gt-custom-wp">
    <div class="gt-custom-wp__toolbar">
      <el-segmented
        v-if="dualMode.isOoAvailable.value"
        class="gt-custom-wp__mode"
        :model-value="dualMode.currentMode.value"
        :options="MODE_OPTIONS"
        size="small"
        :disabled="dualMode.checking.value || refreshing"
        @change="dualMode.onModeChange"
      />
      <el-button
        type="primary"
        size="small"
        :disabled="!wpGenerated"
        @click="openFormulaDialog"
      >
        公式
      </el-button>
      <el-button size="small" :disabled="!wpGenerated" @click="openFormulaList">
        公式清单
      </el-button>
      <span v-if="!wpGenerated" class="gt-custom-wp__hint">底稿未生成，无法编辑公式</span>
      <span v-else-if="refreshing" class="gt-custom-wp__hint">正在从底稿文件刷新内容…</span>
      <span v-else-if="dualMode.isOoMode.value" class="gt-custom-wp__hint">
        在线编辑模式下的改动会在切回「表格视图」时同步显示
      </span>
    </div>

    <GtOnlyOfficeSheet
      v-if="dualMode.isOoMode.value"
      :wp-id="wpId"
      :sheet-name="sheetName"
      :project-id="projectId"
      :readonly="readonly"
      @fallback="onOoFallback"
    />
    <GtCustomGridSheet
      v-else
      :wp-id="wpId"
      :sheet-name="sheetName"
      :html-data="effectiveHtmlData"
      :formula-cells="formulaCells"
      :highlight-cell="highlightCell"
      :readonly="readonly"
      @select-cell="onSelectCell"
      @saved="onCellsSaved"
    />

    <!-- 公式清单抽屉（Task 14）-->
    <el-drawer
      v-model="showFormulaList"
      title="公式清单"
      size="46%"
      :append-to-body="true"
    >
      <div v-loading="formulaListLoading">
        <!-- 🔴 清单为空显示 el-empty 而非空表格（空表格看不出是"没有"还是"加载失败"）-->
        <el-empty
          v-if="!formulaListLoading && formulaList.length === 0"
          description="该底稿尚未设置公式。点击工具栏「公式」按钮为某个单元格添加取数公式。"
        />
        <el-table v-else :data="formulaList" size="small" style="width: 100%">
          <el-table-column label="目标格" width="92">
            <template #default="{ row }">
              <el-link type="primary" :underline="false" @click="locateFormulaCell(row)">
                {{ row.target_cell }}
              </el-link>
            </template>
          </el-table-column>
          <el-table-column prop="expression" label="表达式" min-width="200" show-overflow-tooltip />
          <el-table-column label="类型" width="104">
            <template #default="{ row }">
              <el-tag size="small" type="info">{{ formulaTypeLabel(row.formula_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="最后计算" width="160">
            <template #default="{ row }">
              <span class="gt-custom-wp__hint">{{ row.last_computed_at || '尚未计算' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="72" align="right">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="removeFormula(row)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>

    <!-- 选址列表为空时给出可操作提示，不给空列表（R5.2）-->
    <el-empty
      v-if="wpGenerated && !hasPickableCells"
      class="gt-custom-wp__empty-pick"
      description="底稿暂无内容，请先在网格中录入或切换在线编辑"
    />

    <FormulaEditDialog
      v-model="showFormulaDialog"
      :row="formulaDialogRow"
      :project-id="projectId"
      :year="year"
      :wp-context="wpContext"
      @save="onFormulaSave"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import apiPaths from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import GtCustomGridSheet from '@/components/workpaper/custom/GtCustomGridSheet.vue'
import GtOnlyOfficeSheet from '@/components/workpaper/GtOnlyOfficeSheet.vue'
import FormulaEditDialog from '@/components/formula/FormulaEditDialog.vue'
import { createDualMode } from '@/components/workpaper/composables/factories/createDualMode'
import {
  buildFormulaCellOptions,
  normalizeCellRef,
  type FormulaListItem,
} from '@/components/workpaper/custom/customWpCellEdit'
// 🔴 类型中文标签复用单一真源，禁在本组件另建第二份标签表
import { FORMULA_TYPE_LABEL } from '@/components/workpaper/composables/formulaEngineInventory'

export interface WpFormulaContext {
  wpId: string
  wpCode: string
  sheetName: string
  projectId: string
  year: number
  cells: Array<{ cell: string; label: string }>
}

const emit = defineEmits<{
  'formula-saved': []
}>()

const props = defineProps<{
  wpId: string
  sheetName: string
  schema?: Record<string, unknown>
  htmlData?: Record<string, unknown>
  readonly?: boolean
  wpGenerated?: boolean
  projectId?: string
  year?: number
  wpCode?: string
}>()

const MODE_OPTIONS = [
  { label: '表格视图', value: 'html' },
  { label: '在线编辑', value: 'onlyoffice' },
]

// ─── 投影本地覆盖 ─────────────────────────────────────────────────────────────
// 切回 HTML 时从 xlsx 重投影拿到的最新网格；未刷新过则用 props 下发的投影。
const refreshedGrid = ref<Record<string, unknown> | null>(null)
const refreshing = ref(false)

const effectiveHtmlData = computed<Record<string, unknown> | undefined>(
  () => refreshedGrid.value ?? props.htmlData
)

/**
 * 从 xlsx 重投影。
 *
 * 🔴 失败必须 `ElMessage.error` 且**不清空既有投影** —— 静默失败会让用户以为
 *    「OO 里改的东西丢了」，而清空则比不刷新更糟（本来还看得见旧内容）。
 */
async function refreshProjection(): Promise<void> {
  if (!props.wpGenerated) return
  refreshing.value = true
  try {
    const res = (await api.post(
      apiPaths.workpapers.customRefreshProjection(props.wpId),
      { sheet_name: props.sheetName }
    )) as { grid?: Record<string, unknown> }
    if (res?.grid) refreshedGrid.value = res.grid
  } catch (e) {
    handleApiError(e, '从底稿文件刷新内容失败')
  } finally {
    refreshing.value = false
  }
}

const dualMode = createDualMode({
  persistKey: `custom-wp-mode-${props.wpId}`,
  onSwitchToHtml: refreshProjection,
})

function onOoFallback() {
  void dualMode.switchMode('html')
}

/** 格编辑保存成功后，端点已回传重投影后的网格，直接采用（省一次请求） */
function onCellsSaved(grid: Record<string, unknown>) {
  if (grid) refreshedGrid.value = grid
}

// ─── 公式 ─────────────────────────────────────────────────────────────────────
const showFormulaDialog = ref(false)
const formulaDialogRow = ref<Record<string, string>>({})
/** 用户在网格里点选的目标格，作为公式对话框的默认目标 */
const selectedCell = ref<string>('')

function onSelectCell(ref_: string) {
  selectedCell.value = ref_
}

/**
 * 该 sheet 上已有公式的格 → `{ 'B5': "TB('1001','期末余额')" }`。
 * 公式格在网格里**只读**（悬停展示表达式），由 `GtCustomGridSheet` 消费。
 *
 * 🔴 **真源是 `wp_formula` 表（`formulaList`），不是 xlsx 的 `formula` 键**
 *    （2026-08-08 浏览器实测抓出，Task 26）：自定义底稿的公式求值结果是
 *    **双写 xlsx 与投影的「值」**（`write_cells_to_xlsx` 写 `ws[ref] = 求值结果`），
 *    xlsx 里存的是 `0` / `1234.56` 这类数字，**没有** `=TB(...)` 公式字符串。
 *    故只按 `cells[*].formula` 派生会**恒为空** ⇒ 公式格既不显示 `ƒ` 标记、
 *    也不被 `canEdit` 判为只读 ⇒ 审计师可双击改写公式格，改完在下次求值时被
 *    静默覆盖（数据丢失且无提示）。
 *    `cells[*].formula` 仍作补充来源保留：将来若改为往 xlsx 写真公式，两侧并存也正确。
 */
const formulaCells = computed<Record<string, string>>(() => {
  const out: Record<string, string> = {}
  // 来源①：wp_formula 表（权威）——只取本 sheet 的记录
  for (const item of formulaList.value) {
    if (!item?.target_cell) continue
    if (item.sheet_name && item.sheet_name !== props.sheetName) continue
    out[String(item.target_cell).toUpperCase()] = String(item.expression ?? '')
  }
  // 来源②：xlsx 单元格自带的公式字符串（当前不产生，留作兼容）
  const cells = effectiveHtmlData.value?.cells as Record<string, unknown> | undefined
  if (cells && typeof cells === 'object') {
    for (const [key, raw] of Object.entries(cells)) {
      if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue
      const f = (raw as Record<string, unknown>).formula
      if (typeof f === 'string' && f) out[key.toUpperCase()] = f
    }
  }
  return out
})

const wpContext = computed<WpFormulaContext | undefined>(() => {
  if (!props.projectId) return undefined
  const cells = effectiveHtmlData.value?.cells as Record<string, unknown> | undefined
  // 🔴 语义标签派生：直接用 `A1`/`B2` 当 label 会让选址列表毫无语义，
  //    审计师无法判断该格是什么项目（违反「审计 UI 必须有逻辑追溯能力」）。
  //    派生优先级：本格自带 label/name > 同行首列文本 > 同列首行文本 > 纯引用兜底。
  const cellList = buildFormulaCellOptions(cells)
  return {
    wpId: props.wpId,
    wpCode: props.wpCode || '',
    sheetName: props.sheetName,
    projectId: props.projectId,
    year: props.year ?? new Date().getFullYear(),
    cells: cellList,
  }
})

/** 选址列表是否非空（空时给 el-empty 提示而不是空列表） */
const hasPickableCells = computed(() => (wpContext.value?.cells.length ?? 0) > 0)

// ─── 公式清单抽屉（Task 14）─────────────────────────────────────────────────
/** 从清单点击定位时高亮的目标格 */
const highlightCell = ref<string>('')
const showFormulaList = ref(false)
const formulaList = ref<FormulaListItem[]>([])
const formulaListLoading = ref(false)

/** 类型中文标签复用单一真源，禁在本组件另建标签表 */
function formulaTypeLabel(t: string): string {
  return FORMULA_TYPE_LABEL[t as keyof typeof FORMULA_TYPE_LABEL] ?? t
}

/**
 * 拉取公式清单（静默）。
 *
 * 🔴 抽屉与网格**共用**这一份数据：网格靠它判定哪些格是公式格（只读 + `ƒ` 标记），
 *    故必须在挂载时就拉一次，不能只在打开抽屉时拉 —— 否则用户不点「公式清单」，
 *    公式格就一直是可编辑态（Task 26 实测缺陷）。
 * 静默失败：清单只驱动展示与只读标记，拉不到时不该弹错打断编辑；
 * 打开抽屉那条路径另有 `handleApiError` 提示。
 */
async function fetchFormulaList(): Promise<boolean> {
  try {
    // 🔴 响应键是 `items` 不是 `formulas`（后端 list_formulas 实证）——
    //    读错键会恒空且被 catch 吞掉，表现为「明明有公式但清单是空的」。
    const res = (await api.get(apiPaths.workpapers.formulas(props.wpId))) as {
      items?: FormulaListItem[]
    }
    formulaList.value = Array.isArray(res?.items) ? res.items : []
    return true
  } catch {
    formulaList.value = []
    return false
  }
}

async function openFormulaList() {
  showFormulaList.value = true
  formulaListLoading.value = true
  try {
    const ok = await fetchFormulaList()
    if (!ok) handleApiError(new Error('加载公式清单失败'), '加载公式清单失败')
  } finally {
    formulaListLoading.value = false
  }
}

async function removeFormula(row: FormulaListItem) {
  try {
    await ElMessageBox.confirm(
      `确定删除 ${row.target_cell} 的公式？该格的求值结果会被一并清除，之后可手工填写。`,
      '删除公式',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return // 用户取消
  }
  try {
    const res = (await api.delete(
      apiPaths.workpapers.formulaDetail(props.wpId, row.id)
    )) as { cell_clear_failed?: boolean }
    // 🔴 如实反映「定义已删但残留值清理失败」——静默成功会让用户以为该格已干净
    if (res?.cell_clear_failed) {
      ElMessage.warning('公式已删除，但该格残留值清理失败，请检查底稿文件')
    } else {
      ElMessage.success('公式已删除')
    }
    await openFormulaList()
    await refreshProjection()
    emit('formula-saved')
  } catch (e) {
    handleApiError(e, '删除公式失败')
  }
}

/** 点击清单某条 → 在网格中定位并高亮该目标格 */
function locateFormulaCell(row: FormulaListItem) {
  if (!row.target_cell) return
  highlightCell.value = row.target_cell
  selectedCell.value = row.target_cell
  showFormulaList.value = false
}

function openFormulaDialog() {
  if (!props.wpGenerated) {
    ElMessage.warning('底稿未生成，无法编辑公式')
    return
  }
  formulaDialogRow.value = {
    row_code: `CUSTOM:${props.wpId}:${props.sheetName}`,
    row_name: props.sheetName,
    target_cell: selectedCell.value,
  }
  showFormulaDialog.value = true
}

async function onFormulaSave(payload: {
  formula: string
  category: string
  description: string
  target_cell?: string
}) {
  if (!payload.formula?.trim()) {
    ElMessage.warning('公式表达式不能为空')
    return
  }
  // 🔴 目标格解析走共享纯函数（与后端 `parse_cell_ref` 同语义，守卫交叉锁死），
  //    不要在这里手写正则 —— 两处各写一份必漂移。
  const raw = (payload.target_cell || selectedCell.value || '').trim()
  const targetCell = normalizeCellRef(raw.replace(/^.*!/, ''))
  if (!targetCell) {
    ElMessage.warning('请先选择目标单元格（如 B5）')
    return
  }
  if (!props.projectId) {
    ElMessage.error('缺少项目上下文，无法保存公式')
    return
  }
  try {
    const res = (await api.put(apiPaths.workpapers.formulas(props.wpId), {
      sheet_name: props.sheetName,
      target_cell: targetCell,
      expression: payload.formula,
      year: props.year ?? new Date().getFullYear(),
      template_type: 'soe',
      category: payload.category,
      description: payload.description,
    })) as { evaluated_value?: string; eval_warnings?: string[] }
    if (res?.eval_warnings?.length) {
      ElMessage.warning(`公式已保存（部分引用求值告警: ${res.eval_warnings.length}）`)
    } else if (res?.evaluated_value != null && res.evaluated_value !== '') {
      // 🔴 求值结果必须让用户看见 —— 只读 eval_warnings 会让「保存成功但格里没值」
      //    与「求值为空」无法区分（改造前即如此）。
      ElMessage.success(`公式已保存，${targetCell} = ${res.evaluated_value}`)
    } else {
      ElMessage.success('公式已保存')
    }
    // 公式求值结果由后端写入 xlsx 与投影，需重投影才能在网格里看到
    await refreshProjection()
    // 🔴 必须同步刷新公式清单 —— `formulaCells` 由它派生，不刷新则新加的公式格
    //    在网格里仍是可编辑态（无 ƒ 标记、双击能改），用户改完会被下次求值覆盖。
    await fetchFormulaList()
    emit('formula-saved')
  } catch (e) {
    handleApiError(e, '保存公式失败')
  }
}

// 🔴 挂载即拉公式清单：`formulaCells` 由它派生，不拉则**已存在**的公式格在网格里
//    仍是可编辑态（无 ƒ 标记 / 双击能改 / 无来源 tooltip），用户手工改写后会被
//    下次求值静默覆盖 = 数据丢失。静默失败（不打断底稿打开），只是公式格退化为
//    普通格，与「清单加载失败」同态。
onMounted(() => {
  if (props.wpGenerated) void fetchFormulaList()
})
</script>

<style scoped>
.gt-custom-wp__toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  padding: 6px 0;
}
.gt-custom-wp__mode {
  margin-right: 4px;
}
.gt-custom-wp__hint {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}
:deep(.gt-custom-wp__toolbar .el-button--primary) {
  --el-button-bg-color: var(--gt-color-primary, #4b2d77);
  --el-button-border-color: var(--gt-color-primary, #4b2d77);
}
</style>
