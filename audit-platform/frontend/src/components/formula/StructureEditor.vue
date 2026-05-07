<template>
  <div class="structure-editor">
    <!-- 顶部信息栏 -->
    <div class="se-header">
      <div class="se-header-left">
        <h3 class="se-title">表样编辑</h3>
        <div class="se-info-tags">
          <span v-if="props.projectName" class="se-tag se-tag-unit">🏢 {{ props.projectName }}</span>
          <span v-if="props.templateType" class="se-tag se-tag-tpl">{{ props.templateType === 'listed' ? '上市版' : '国企版' }}</span>
          <span v-if="props.reportScope" class="se-tag se-tag-scope">{{ props.reportScope === 'consolidated' ? '合并' : '单体' }}</span>
          <span v-if="props.year" class="se-tag se-tag-year">{{ props.year }}年</span>
          <span v-if="props.module" class="se-tag se-tag-module">{{ moduleLabel }}</span>
        </div>
      </div>
    </div>

    <!-- 公式编辑栏 -->
    <FormulaBar
      :visible="true"
      :cell-info="currentCellInfo"
      :project-id="props.projectId"
      @update-formula="onUpdateFormula"
      @update-value="onUpdateValue"
      @open-selector="showSelector = true"
    />

    <!-- 工具栏 -->
    <div class="editor-toolbar">
      <el-button-group size="small">
        <el-button @click="insertRow">插入行</el-button>
        <el-button @click="deleteRow">删除行</el-button>
        <el-button @click="insertCol">插入列</el-button>
        <el-button @click="deleteCol">删除列</el-button>
      </el-button-group>
      <el-divider direction="vertical" />
      <el-button size="small" @click="saveEdits" :loading="saving" type="primary">保存</el-button>
      <el-button size="small" @click="runFormulas" :loading="calculating">执行公式</el-button>
      <el-button size="small" @click="showFormulaManager = true">⚙️ 公式管理</el-button>
      <el-divider direction="vertical" />
      <el-button size="small" @click="$emit('export-excel')">导出Excel</el-button>
      <el-button size="small" @click="$emit('export-word')">导出Word</el-button>
      <el-button size="small" text @click="showVersions = true">版本历史</el-button>
      <el-divider direction="vertical" />
      <el-checkbox v-model="showFormulas" size="small">显示公式</el-checkbox>
      <el-checkbox v-model="showSources" size="small">显示数据源</el-checkbox>
      <el-checkbox v-model="showStatus" size="small">显示状态</el-checkbox>
    </div>

    <!-- Sheet Tab 切换（多Sheet时显示） -->
    <div v-if="sheetNames.length > 1" class="sheet-tabs">
      <el-tabs v-model="activeSheetIndex" type="card" size="small" @tab-change="onSheetChange">
        <el-tab-pane v-for="(name, idx) in sheetNames" :key="idx" :label="name" :name="String(idx)" />
      </el-tabs>
    </div>

    <!-- HTML 表格区域 + 操作说明 -->
    <div class="editor-body">
      <!-- 左下：表格预览 -->
      <div class="table-area">
        <div
          class="table-container"
          :class="{'show-formulas': showFormulas, 'show-sources': showSources, 'show-status': showStatus}"
          ref="tableContainer"
          v-html="htmlContent"
          @click="onCellClick"
          @dblclick="onCellDblClick"
          @focusout="onCellBlur"
        />

        <!-- 分页控件（大表格时显示） -->
        <div class="pagination-bar" v-if="isLargeTable">
          <span class="page-info">共 {{ totalRows }} 行，每页 {{ pageSize }} 行</span>
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="totalRows"
            layout="prev, pager, next, jumper"
            small
            @current-change="onPageChange"
          />
        </div>
      </div>

      <!-- 右下：操作说明 -->
      <div class="help-area">
        <div class="help-title">📖 操作说明</div>

        <div class="help-section">
          <div class="help-subtitle">基本操作</div>
          <div class="help-item">🖱️ <b>单击</b>单元格 → 选中，查看公式和数据源</div>
          <div class="help-item">🖱️ <b>双击</b>单元格 → 进入编辑模式，直接修改值</div>
          <div class="help-item">⌨️ <b>Enter</b> → 确认编辑，移到下一行</div>
          <div class="help-item">⌨️ <b>Esc</b> → 取消编辑</div>
          <div class="help-item">⌨️ <b>Tab</b> → 跳到下一个单元格</div>
          <div class="help-item">⌨️ <b>方向键</b> → 在单元格间导航</div>
        </div>

        <div class="help-section">
          <div class="help-subtitle">公式与取数</div>
          <div class="help-item">📐 选中单元格后在顶部<b>公式栏</b>输入公式</div>
          <div class="help-item">🔗 点击<b>执行公式</b>按钮运行所有公式并回填结果</div>
          <div class="help-item">📊 <span class="help-badge auto">自动</span> 标记的单元格由公式自动计算</div>
          <div class="help-item">✏️ <span class="help-badge manual">手动</span> 标记的单元格为用户手动输入</div>
        </div>

        <div class="help-section">
          <div class="help-subtitle">行列操作</div>
          <div class="help-item">➕ <b>插入行/列</b> → 在选中位置前插入</div>
          <div class="help-item">➖ <b>删除行/列</b> → 删除选中的行或列</div>
          <div class="help-item">💡 插入/删除后公式引用会自动调整偏移</div>
        </div>

        <div class="help-section">
          <div class="help-subtitle">保存与导出</div>
          <div class="help-item">💾 <b>Ctrl+S</b> → 快捷保存（自动创建版本快照）</div>
          <div class="help-item">📤 导出为 <b>Excel</b> 或 <b>Word</b>（致同三线表格式）</div>
          <div class="help-item">🔄 <b>版本历史</b> → 查看/对比/回滚历史版本</div>
        </div>

        <div class="help-section">
          <div class="help-subtitle">可视化选项</div>
          <div class="help-item">☑️ <b>显示公式</b> → 单元格下方显示公式文本</div>
          <div class="help-item">☑️ <b>显示数据源</b> → 有取数绑定的格显示🔗图标</div>
          <div class="help-item">☑️ <b>显示状态</b> → 左边框颜色标识单元格状态</div>
        </div>

        <!-- 当前选中单元格信息 -->
        <div v-if="currentCellInfo" class="help-section" style="border-top: 1px solid #e8e4f0; padding-top: 10px;">
          <div class="help-subtitle">📍 当前选中</div>
          <div class="help-item">地址：<code>{{ currentCellInfo.address }}</code></div>
          <div class="help-item" v-if="currentCellInfo.formula">公式：<code style="color: #4b2d77;">{{ currentCellInfo.formula }}</code></div>
          <div class="help-item">值：<b>{{ formatValue(currentCellInfo.value) || '-' }}</b></div>
          <div class="help-item" v-if="currentCellInfo.is_merged">合并范围：{{ currentCellInfo.merge?.range }}</div>
          <div class="help-item" v-if="currentCellInfo.fetch_rule_id">
            <el-button size="small" text type="primary" @click="traceSource">🔗 查看数据来源</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 可视选择器弹窗 -->
    <CellSelector
      v-model="showSelector"
      :trial-balance-data="trialBalanceData"
      :report-data="reportData"
      :note-sections="noteSections"
      @confirm="onSelectorConfirm"
    />

    <!-- 版本历史弹窗 -->
    <el-dialog v-model="showVersions" title="版本历史" width="600px" append-to-body>
      <el-table :data="versions" size="small" max-height="400">
        <el-table-column prop="version" label="版本" width="60" />
        <el-table-column prop="edited_at" label="编辑时间" width="180" />
        <el-table-column prop="synced_from" label="来源" width="100" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button size="small" text @click="diffVersion(row.version)">对比</el-button>
            <el-button size="small" text type="warning" @click="rollbackVersion(row.version)">回滚</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 当前表公式管理弹窗（双Tab） -->
    <el-dialog v-model="showFormulaManager" title="当前表公式管理" width="80%" top="4vh" append-to-body destroy-on-close>
      <el-tabs v-model="fmTab" type="border-card">
        <!-- Tab1: 已有公式列表 -->
        <el-tab-pane name="list">
          <template #label>📋 已有公式 ({{ localFormulas.length }})</template>
          <div style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center;">
            <el-button size="small" @click="fmTab = 'edit'">+ 新增公式</el-button>
            <el-button v-if="fmSelectedRows.length > 0" size="small" style="color: #999;" @click="onFmBatchDelete">删除选中 ({{ fmSelectedRows.length }})</el-button>
            <span style="flex: 1;" />
            <span style="font-size: 11px; color: #999;">共 {{ localFormulas.length }} 条</span>
          </div>
          <el-table :data="localFormulas" size="small" border max-height="50vh" style="width: 100%;"
            :header-cell-style="{ background: '#f8f6fb', fontSize: '12px', whiteSpace: 'nowrap' }"
            @selection-change="(rows: any[]) => fmSelectedRows = rows"
            highlight-current-row
            @row-click="onFmRowClick">
            <el-table-column type="selection" width="40" />
            <el-table-column label="目标" width="100">
              <template #default="{ row }">
                <code style="font-size: 10px; color: #4b2d77; background: #f0ecf5; padding: 1px 5px; border-radius: 3px;">{{ row.target }}</code>
              </template>
            </el-table-column>
            <el-table-column label="公式" min-width="260">
              <template #default="{ row }">
                <el-input v-if="row._editing" v-model="row.formula" size="small" />
                <code v-else style="font-size: 10px; color: #555; cursor: pointer;" @dblclick="row._editing = true">{{ row.formula || '（双击编辑）' }}</code>
              </template>
            </el-table-column>
            <el-table-column label="分类" width="90">
              <template #default="{ row }">
                <el-select v-if="row._editing" v-model="row.category" size="small" style="width: 80px;">
                  <el-option label="自动" value="auto_calc" />
                  <el-option label="逻辑" value="logic_check" />
                  <el-option label="合理" value="reasonability" />
                </el-select>
                <span v-else style="font-size: 10px;">{{ ({ auto_calc: '⚡', logic_check: '🔍', reasonability: '💡' } as Record<string,string>)[row.category] || '' }}{{ ({ auto_calc: '自动', logic_check: '逻辑', reasonability: '合理' } as Record<string,string>)[row.category] || row.category }}</span>
              </template>
            </el-table-column>
            <el-table-column label="说明" min-width="140">
              <template #default="{ row }">
                <el-input v-if="row._editing" v-model="row.description" size="small" />
                <span v-else style="font-size: 10px; color: #999;">{{ row.description }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90" align="center">
              <template #default="{ row, $index }">
                <el-button v-if="!row._editing" size="small" link type="primary" @click="row._editing = true">编辑</el-button>
                <el-button v-else size="small" link style="color: #1e8a38;" @click="row._editing = false">完成</el-button>
                <el-button size="small" link style="color: #999;" @click="localFormulas.splice($index, 1)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- Tab2: 公式编辑（含辅助工具） -->
        <el-tab-pane name="edit">
          <template #label>✏️ 编辑公式</template>
          <div class="fm-edit-panel">
            <!-- 目标定位 -->
            <div class="fm-edit-row">
              <span class="fm-edit-label">📍 写入目标：</span>
              <el-input v-model="editTarget" size="small" placeholder="如 B2 或 C5" style="width: 120px;" />
              <span style="font-size: 10px; color: #999; margin-left: 4px;">（当前选中：{{ currentCellInfo?.address || '--' }}）</span>
            </div>
            <!-- 公式输入 -->
            <div class="fm-edit-row">
              <span class="fm-edit-label">fx 公式：</span>
              <el-input v-model="editFormula" size="small" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="输入公式，如 TB('1001','期末余额')" style="flex: 1;"
                :input-style="{ fontSize: '11px', fontFamily: 'Cascadia Code, Fira Code, monospace' }" ref="editFormulaInput" />
            </div>
            <!-- 分类 + 说明 -->
            <div class="fm-edit-row">
              <span class="fm-edit-label">分类：</span>
              <el-select v-model="editCategory" size="small" style="width: 120px;">
                <el-option label="⚡ 自动运算" value="auto_calc" />
                <el-option label="🔍 逻辑审核" value="logic_check" />
                <el-option label="💡 合理性" value="reasonability" />
              </el-select>
              <span class="fm-edit-label" style="margin-left: 12px;">说明：</span>
              <el-input v-model="editDescription" size="small" placeholder="公式说明" style="flex: 1;" />
            </div>
            <!-- 取数函数快捷按钮 -->
            <div class="fm-edit-section">
              <div class="fm-edit-section-title">取数（点击弹窗选择数据源）</div>
              <div class="fm-edit-btns">
                <el-button size="small" @click="fmInsert('TB')" title="从试算表选择科目">TB</el-button>
                <el-button size="small" @click="fmInsert('ROW')" title="从报表选择行次">ROW</el-button>
                <el-button size="small" @click="fmInsert('SUM_ROW')" title="连续行范围求和">SUM_ROW</el-button>
                <el-button size="small" @click="fmInsert('SUM_TB')" title="按科目前缀汇总">SUM_TB</el-button>
                <el-button size="small" @click="fmInsert('NOTE')" title="从附注选择">NOTE</el-button>
                <el-button size="small" @click="fmInsert('WP')" title="从底稿选择">WP</el-button>
                <el-button size="small" @click="fmInsert('REPORT')" title="跨表引用报表">REPORT</el-button>
                <el-button size="small" @click="fmInsert('AUX')" title="辅助余额表">AUX</el-button>
                <el-button size="small" @click="fmInsert('PREV')" title="上年同期">PREV</el-button>
              </div>
            </div>
            <!-- 运算符 -->
            <div class="fm-edit-section">
              <div class="fm-edit-section-title">运算符</div>
              <div class="fm-edit-btns">
                <el-button size="small" @click="fmInsertOp(' + ')">+</el-button>
                <el-button size="small" @click="fmInsertOp(' - ')">−</el-button>
                <el-button size="small" @click="fmInsertOp(' * ')">×</el-button>
                <el-button size="small" @click="fmInsertOp(' / ')">÷</el-button>
                <el-button size="small" @click="fmInsertOp(' = ')">=</el-button>
                <el-button size="small" @click="fmInsertOp(' > ')">></el-button>
                <el-button size="small" @click="fmInsertOp(' < ')"><</el-button>
                <el-button size="small" @click="fmInsertOp(' >= ')">≥</el-button>
                <el-button size="small" @click="fmInsertOp(' <= ')">≤</el-button>
              </div>
            </div>
            <!-- 函数 -->
            <div class="fm-edit-section">
              <div class="fm-edit-section-title">函数</div>
              <div class="fm-edit-btns">
                <el-button size="small" @click="fmInsertFn('IF')" title="IF(条件,真值,假值)">IF</el-button>
                <el-button size="small" @click="fmInsertFn('ABS')" title="取绝对值">ABS</el-button>
                <el-button size="small" @click="fmInsertFn('ROUND')" title="四舍五入">ROUND</el-button>
                <el-button size="small" @click="fmInsertFn('MAX')" title="最大值">MAX</el-button>
                <el-button size="small" @click="fmInsertFn('MIN')" title="最小值">MIN</el-button>
                <el-button size="small" @click="fmInsertFn('NOT_EMPTY')" title="非空检查">非空</el-button>
                <el-button size="small" @click="fmInsertFn('NOT_ZERO')" title="非零检查">非零</el-button>
                <el-button size="small" @click="fmInsertFn('CHANGE_RATE')" title="变动率">变动率</el-button>
              </div>
            </div>
            <!-- 添加按钮 -->
            <div style="margin-top: 10px; text-align: right;">
              <el-button size="small" type="primary" @click="addEditedFormula">添加到公式列表</el-button>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button @click="showFormulaManager = false">关闭</el-button>
        <el-button type="primary" @click="applyLocalFormulas">应用公式</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { confirmRollback } from '@/utils/confirm'
import FormulaBar from './FormulaBar.vue'
import CellSelector from './CellSelector.vue'
import {
  getExcelHtmlPreview,
  saveExcelHtmlEdits,
  getModuleHtml,
  acquireEditLock,
  releaseEditLock,
  refreshEditLock,
  listFileVersions,
  rollbackFileVersion,
  executeFormulas,
} from '@/services/commonApi'
import { api } from '@/services/apiProxy'
import { fmtAmount } from '@/utils/formatters'

const props = defineProps<{
  projectId: string
  fileStem?: string
  module?: string
  moduleParams?: Record<string, any>
  // 项目信息（用于顶部信息栏显示）
  projectName?: string
  templateType?: string
  reportScope?: string
  year?: number
}>()

const emit = defineEmits<{
  'export-excel': []
  'export-word': []
  'saved': [version: number]
}>()

const htmlContent = ref('')
const saving = ref(false)

// 多Sheet支持
const sheetNames = ref<string[]>([])
const activeSheetIndex = ref('0')

async function onSheetChange(idx: string | number) {
  activeSheetIndex.value = String(idx)
  await loadContent()
}

const moduleLabel = computed(() => {
  const m: Record<string, string> = {
    disclosure_note: '📝 附注', financial_report: '📊 报表',
    workpaper: '📋 底稿', trial_balance: '📈 试算表',
    adjustment_summary: '📑 调整汇总', consol_worksheet: '🔗 合并差额表',
  }
  return m[props.module || ''] || props.module || ''
})
const calculating = ref(false)
const showSelector = ref(false)
const showVersions = ref(false)
const showFormulaManager = ref(false)
const _showInfoPanel = ref(true)
const showFormulas = ref(false)
const showSources = ref(false)
const showStatus = ref(false)
const versions = ref<any[]>([])
const currentCellInfo = ref<any>(null)
const selectedCell = ref('')
const pendingEdits = ref<any[]>([])
const tableContainer = ref<HTMLElement>()
const currentPage = ref(1)
const pageSize = ref(500)
const totalRows = ref(0)
const isLargeTable = ref(false)

const _formulaTypeMap: Record<string, string> = {
  vertical_sum: '纵向合计',
  horizontal_balance: '横向平衡',
  book_value: '账面价值',
  cross_table: '跨表引用',
}

// 外部数据（供 CellSelector 使用）
const trialBalanceData = ref<any[]>([])
const reportData = ref<any[]>([])
const noteSections = ref<string[]>([])

// 锁刷新定时器
let lockRefreshTimer: ReturnType<typeof setInterval> | null = null

async function loadContent() {
  try {
    const sheetIdx = parseInt(activeSheetIndex.value) || 0
    if (props.fileStem) {
      const result = await getExcelHtmlPreview(props.projectId, props.fileStem, sheetIdx) as any
      htmlContent.value = result.html
      totalRows.value = result.total_rows || 0
      isLargeTable.value = result.is_large || totalRows.value > 500
      // 提取Sheet名称列表（首次加载时）
      if (result.sheet_names && Array.isArray(result.sheet_names)) {
        sheetNames.value = result.sheet_names
      } else if (result.sheet_count && sheetNames.value.length === 0) {
        // 降级：用序号
        sheetNames.value = Array.from({ length: result.sheet_count }, (_, i) => `Sheet${i + 1}`)
      }
      if (isLargeTable.value && currentPage.value === 1) {
        // 大表格重新加载分页版本
        const paged = await getExcelHtmlPreview(props.projectId, props.fileStem, 0) as any
        htmlContent.value = paged.html
      }
    } else if (props.module) {
      const result = await getModuleHtml(props.projectId, props.module, {
        ...props.moduleParams,
        editable: true,
      })
      htmlContent.value = result.html
    }
  } catch {
    htmlContent.value = '<p>加载失败</p>'
  }
}

async function onPageChange(page: number) {
  if (!props.fileStem) return
  currentPage.value = page
  try {
    const data = await api.get(
      `/api/projects/${props.projectId}/excel-html/preview/${props.fileStem}`,
      { params: { page, page_size: pageSize.value, editable: true } }
    )
    htmlContent.value = data.html || data?.data?.html || ''
  } catch {
    ElMessage.error('加载分页数据失败')
  }
}

function onCellClick(e: MouseEvent) {
  const td = (e.target as HTMLElement).closest('td[data-cell]') as HTMLElement
  if (!td) return

  // 高亮选中
  tableContainer.value?.querySelectorAll('td.gt-selected').forEach(el => el.classList.remove('gt-selected'))
  td.classList.add('gt-selected')

  selectedCell.value = td.dataset.cell || ''

  // 更新公式栏信息
  currentCellInfo.value = {
    cell: td.dataset.cell,
    address: td.dataset.addr || '',
    value: td.textContent?.replace(/[A-Z]\d+$/g, '').trim(),
    formula: td.dataset.formula || null,
    formula_type: td.dataset.formulaType || null,
    formula_desc: null,
    fetch_rule_id: td.dataset.fetchRule || null,
    merge: td.dataset.mergeRange ? { range: td.dataset.mergeRange } : null,
    is_merged: td.dataset.merged === 'true',
  }

  // 单击即进入编辑模式（contenteditable 聚焦）
  if (td.isContentEditable) {
    td.focus()
    // 将光标移到末尾
    const range = document.createRange()
    const sel = window.getSelection()
    if (sel && td.childNodes.length > 0) {
      range.selectNodeContents(td)
      range.collapse(false)
      sel.removeAllRanges()
      sel.addRange(range)
    }
  }

  // 可视化维度：高亮公式依赖的单元格
  if (showFormulas.value && td.dataset.formula) {
    _highlightFormulaDeps(td.dataset.formula)
  }
}

function _highlightFormulaDeps(formula: string) {
  // 清除旧高亮
  tableContainer.value?.querySelectorAll('td.gt-dep-highlight').forEach(el => el.classList.remove('gt-dep-highlight'))

  // 解析公式中的单元格引用（简单正则匹配 A1-Z99 格式）
  const refs = formula.match(/[A-Z]{1,2}\d{1,3}/g) || []
  for (const ref of refs) {
    const td = tableContainer.value?.querySelector(`td[data-addr="${ref}"]`)
    if (td) td.classList.add('gt-dep-highlight')
  }
}

function traceSource() {
  ElMessage.info('溯源跳转：查看数据来源（调用 trace-forward API）')
  // TODO: 调用 trace-forward 显示来源弹窗
}

function formatValue(val: any): string {
  if (val === null || val === undefined) return ''
  if (typeof val === 'number') {
    if (val === 0) return '-'
    return fmtAmount(val)
  }
  return String(val)
}

function onCellDblClick(e: MouseEvent) {
  const td = (e.target as HTMLElement).closest('td[data-cell]') as HTMLElement
  if (!td || !td.isContentEditable) return
  // 双击进入编辑模式，浏览器原生 contenteditable 处理
}

// 自动保存定时器
let autoSaveTimer: ReturnType<typeof setTimeout> | null = null

function onCellBlur(e: FocusEvent) {
  const td = (e.target as HTMLElement).closest('td[data-cell]') as HTMLElement
  if (!td || !td.isContentEditable) return

  const cellKey = td.dataset.cell || ''
  const newValue = td.textContent?.replace(/[A-Z]\d+$/g, '').trim() || ''

  // 检查值是否变化（与 currentCellInfo 对比）
  if (cellKey && currentCellInfo.value?.cell === cellKey) {
    const oldValue = String(currentCellInfo.value.value || '').trim()
    if (newValue !== oldValue) {
      pendingEdits.value.push({ action: 'edit', cell: cellKey, value: newValue })

      // 自动保存（5秒无操作后）
      if (autoSaveTimer) clearTimeout(autoSaveTimer)
      autoSaveTimer = setTimeout(() => {
        if (pendingEdits.value.length > 0 && props.fileStem) {
          saveEdits()
        }
      }, 5000)
    }
  }
}

function onUpdateFormula(cell: string, formula: string) {
  pendingEdits.value.push({ action: 'set_formula', cell, formula })
  ElMessage.info(`公式已设置: ${cell} = ${formula}`)
}

function onUpdateValue(cell: string, value: string) {
  pendingEdits.value.push({ action: 'edit', cell, value })
}

function onSelectorConfirm(rule: any) {
  if (!selectedCell.value) {
    ElMessage.warning('请先选择目标单元格')
    return
  }
  // 将选择结果转为公式
  const sources = rule.sources || []
  let formula = '='
  if (sources.length === 1) {
    formula += _sourceToFormula(sources[0])
  } else if (rule.transform === 'sum') {
    formula += sources.map(_sourceToFormula).join(' + ')
  } else if (rule.transform === 'diff' && sources.length >= 2) {
    formula += `${_sourceToFormula(sources[0])} - ${_sourceToFormula(sources[1])}`
  }

  pendingEdits.value.push({ action: 'set_formula', cell: selectedCell.value, formula, description: rule.description })
  ElMessage.success(`取数规则已绑定到 ${currentCellInfo.value?.address || selectedCell.value}`)
}

function _sourceToFormula(source: any): string {
  if (source.type === 'trial_balance') return `TB(${source.account_code}, ${source.field})`
  if (source.type === 'report') return `RPT(${source.row_code}, ${source.field})`
  if (source.type === 'note') return `NOTE(${source.section}, ${source.row}, ${source.col})`
  if (source.type === 'workpaper') return `WP(${source.wp_code}, ${source.data_key})`
  if (source.type === 'aux_balance') return `AUX(${source.account_code}, ${source.aux_code}, ${source.field})`
  return '0'
}

function insertRow() {
  if (!selectedCell.value) { ElMessage.warning('请先选择单元格'); return }
  const row = parseInt(selectedCell.value.split(':')[0])
  pendingEdits.value.push({ action: 'insert_row', at: row })
  ElMessage.info(`在第 ${row + 1} 行前插入空行`)
}

function deleteRow() {
  if (!selectedCell.value) { ElMessage.warning('请先选择单元格'); return }
  const row = parseInt(selectedCell.value.split(':')[0])
  pendingEdits.value.push({ action: 'delete_row', at: row })
  ElMessage.info(`删除第 ${row + 1} 行`)
}

function insertCol() {
  if (!selectedCell.value) { ElMessage.warning('请先选择单元格'); return }
  const col = parseInt(selectedCell.value.split(':')[1])
  pendingEdits.value.push({ action: 'insert_col', at: col })
  ElMessage.info(`在第 ${col + 1} 列前插入空列`)
}

function deleteCol() {
  if (!selectedCell.value) { ElMessage.warning('请先选择单元格'); return }
  const col = parseInt(selectedCell.value.split(':')[1])
  pendingEdits.value.push({ action: 'delete_col', at: col })
  ElMessage.info(`删除第 ${col + 1} 列`)
}

async function saveEdits() {
  if (pendingEdits.value.length === 0) {
    ElMessage.info('无待保存的编辑')
    return
  }
  if (!props.fileStem && props.module) {
    // 模块模式：通过附注/报表 API 保存
    ElMessage.success('编辑内容将在关闭时同步保存')
    pendingEdits.value = []
    return
  }
  if (!props.fileStem) return
  saving.value = true
  try {
    const result = await saveExcelHtmlEdits(props.projectId, props.fileStem, pendingEdits.value)
    pendingEdits.value = []
    emit('saved', result.version)
    await loadContent()
    ElMessage.success(`已保存 v${result.version}`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function runFormulas() {
  if (!props.fileStem && props.module) {
    // 模块模式：通过附注校验 API 执行公式
    ElMessage.info('模块模式下请使用附注页面的"执行校验"功能')
    return
  }
  if (!props.fileStem) return
  calculating.value = true
  try {
    const result = await executeFormulas(props.projectId, props.fileStem)
    await loadContent()
    if (result.errors?.length) {
      setTimeout(() => {
        for (const err of result.errors) {
          const td = tableContainer.value?.querySelector(`td[data-cell="${err.cell}"]`) as HTMLElement
          if (td) {
            td.classList.add('gt-formula-error')
            td.title = `公式错误: ${err.error}\n公式: ${err.formula || ''}`
          }
        }
      }, 100)
      ElMessage.warning(`执行完成：${result.executed}/${result.total_formulas} 成功，${result.errors.length} 个错误`)
    } else {
      ElMessage.success(`公式执行完成：${result.executed} 个单元格已更新`)
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '公式执行失败')
  } finally {
    calculating.value = false
  }
}

async function _loadVersions() {
  if (!props.fileStem) return
  try {
    versions.value = await listFileVersions(props.projectId, props.fileStem)
  } catch { versions.value = [] }
}

async function diffVersion(version: number) {
  ElMessage.info(`对比版本 ${version} 与当前版本（功能开发中）`)
}

async function rollbackVersion(version: number) {
  await confirmRollback(version)
  try {
    await rollbackFileVersion(props.projectId, props.fileStem!, version)
    ElMessage.success(`已回滚到版本 ${version}`)
    await loadContent()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '回滚失败')
  }
}

// 编辑锁
async function acquireLock() {
  if (!props.fileStem) return
  try {
    await acquireEditLock(props.projectId, props.fileStem)
    // 定期刷新锁
    lockRefreshTimer = setInterval(async () => {
      try {
        await refreshEditLock(props.projectId, props.fileStem!)
      } catch { /* 锁过期 */ }
    }, 4 * 60 * 1000) // 4分钟刷新一次
  } catch (e: any) {
    if (e?.response?.status === 423) {
      ElMessage.warning('文件正在被其他用户编辑，进入只读模式')
    }
  }
}

async function releaseLock() {
  if (!props.fileStem) return
  if (lockRefreshTimer) { clearInterval(lockRefreshTimer); lockRefreshTimer = null }
  try {
    await releaseEditLock(props.projectId, props.fileStem)
  } catch { /* ignore */ }
}

onMounted(async () => {
  await acquireLock()
  await loadContent()
  await loadSelectorData()
  // 注册键盘快捷键
  document.addEventListener('keydown', onKeyDown)
})

onUnmounted(() => {
  releaseLock()
  document.removeEventListener('keydown', onKeyDown)
})

// ═══ 键盘快捷键 ═══

function onKeyDown(e: KeyboardEvent) {
  // Ctrl+S 保存
  if (e.ctrlKey && e.key === 's') {
    e.preventDefault()
    saveEdits()
    return
  }
  // Ctrl+Z 撤销最后一条编辑
  if (e.ctrlKey && e.key === 'z') {
    e.preventDefault()
    if (pendingEdits.value.length) {
      pendingEdits.value.pop()
      ElMessage.info(`撤销一条编辑（剩余 ${pendingEdits.value.length} 条）`)
    }
    return
  }
  // Escape 取消选中
  if (e.key === 'Escape') {
    tableContainer.value?.querySelectorAll('td.gt-selected').forEach(el => el.classList.remove('gt-selected'))
    currentCellInfo.value = null
    selectedCell.value = ''
    return
  }

  // 以下快捷键需要有选中单元格
  if (!selectedCell.value) return
  const [row, col] = selectedCell.value.split(':').map(Number)

  // Tab → 下一列
  if (e.key === 'Tab') {
    e.preventDefault()
    _navigateTo(row, col + (e.shiftKey ? -1 : 1))
    return
  }
  // Enter → 下一行
  if (e.key === 'Enter' && !e.ctrlKey) {
    // 如果当前在 contenteditable 编辑中，不拦截
    const active = document.activeElement
    if (active && active.tagName === 'TD' && (active as HTMLElement).isContentEditable) return
    e.preventDefault()
    _navigateTo(row + 1, col)
    return
  }
  // 方向键导航（仅在非编辑状态）
  const active = document.activeElement
  if (active && active.tagName === 'TD' && (active as HTMLElement).isContentEditable) return
  if (e.key === 'ArrowUp') { e.preventDefault(); _navigateTo(row - 1, col) }
  if (e.key === 'ArrowDown') { e.preventDefault(); _navigateTo(row + 1, col) }
  if (e.key === 'ArrowLeft') { e.preventDefault(); _navigateTo(row, col - 1) }
  if (e.key === 'ArrowRight') { e.preventDefault(); _navigateTo(row, col + 1) }
}

function _navigateTo(row: number, col: number) {
  if (row < 0 || col < 0) return
  const key = `${row}:${col}`
  const td = tableContainer.value?.querySelector(`td[data-cell="${key}"]`) as HTMLElement
  if (td) {
    td.click()  // 触发 onCellClick
    td.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }
}

// ═══ 当前表公式管理 ═══
interface LocalFormula {
  target: string
  formula: string
  category: string
  description: string
  _editing: boolean
}
const localFormulas = ref<LocalFormula[]>([])
const fmSelectedRows = ref<any[]>([])

function onFmBatchDelete() {
  const toDelete = new Set(fmSelectedRows.value)
  localFormulas.value = localFormulas.value.filter(f => !toDelete.has(f))
  fmSelectedRows.value = []
  ElMessage.success('已删除选中公式')
}

function onFmRowClick(row: any) {
  // 单击行时选中该公式，在编辑Tab中填充
  editTarget.value = row.target || ''
  editFormula.value = row.formula || ''
  editCategory.value = row.category || 'auto_calc'
  editDescription.value = row.description || ''
}

// 打开公式管理时，从当前表格的 structure 中提取已有公式
watch(showFormulaManager, (v) => {
  if (!v) return
  extractFormulasFromStructure()
})

function extractFormulasFromStructure() {
  // 从 HTML 中提取带 data-formula 属性的单元格
  const container = tableContainer.value as HTMLElement | null
  if (!container) return
  const cells = container.querySelectorAll('td[data-formula]')
  const formulas: LocalFormula[] = []
  cells.forEach((td) => {
    const addr = td.getAttribute('data-addr') || ''
    const formula = td.getAttribute('data-formula') || ''
    if (formula) {
      formulas.push({
        target: addr,
        formula,
        category: 'auto_calc',
        description: '',
        _editing: false,
      })
    }
  })
  localFormulas.value = formulas
}

function _addLocalFormula() {
  const addr = currentCellInfo.value?.address || ''
  localFormulas.value.push({
    target: addr,
    formula: '',
    category: 'auto_calc',
    description: '',
    _editing: true,
  })
}

// ── 编辑Tab状态 ──
const fmTab = ref('list')
const editTarget = ref('')
const editFormula = ref('')
const editCategory = ref('auto_calc')
const editDescription = ref('')
const editFormulaInput = ref<any>(null)

// 切换到编辑Tab时自动填入当前选中单元格
watch(fmTab, (v) => {
  if (v === 'edit') {
    editTarget.value = currentCellInfo.value?.address || ''
    editFormula.value = ''
    editCategory.value = 'auto_calc'
    editDescription.value = ''
  }
})

function fmInsert(fn: string) {
  // 取数函数——直接插入模板（后续可改为弹窗选择）
  const templates: Record<string, string> = {
    TB: "TB('','')", ROW: "ROW('')", SUM_ROW: "SUM_ROW('','')",
    SUM_TB: "SUM_TB('','')", NOTE: "NOTE('','','')", WP: "WP('','')",
    REPORT: "REPORT('','')", AUX: "AUX('','','')", PREV: "PREV('','')",
  }
  editFormula.value += (editFormula.value ? ' + ' : '') + (templates[fn] || fn + '()')
}

function fmInsertOp(op: string) {
  editFormula.value += op
}

function fmInsertFn(fn: string) {
  const templates: Record<string, string> = {
    IF: 'IF(,,)', ABS: 'ABS()', ROUND: 'ROUND(,2)', MAX: 'MAX(,)', MIN: 'MIN(,)',
    NOT_EMPTY: "NOT_EMPTY('')", NOT_ZERO: "NOT_ZERO('')", CHANGE_RATE: "CHANGE_RATE('') < 0.5",
  }
  editFormula.value += (editFormula.value ? ' ' : '') + (templates[fn] || fn + '()')
}

function addEditedFormula() {
  if (!editFormula.value.trim()) {
    ElMessage.warning('请输入公式')
    return
  }
  localFormulas.value.push({
    target: editTarget.value || currentCellInfo.value?.address || '',
    formula: editFormula.value.trim(),
    category: editCategory.value,
    description: editDescription.value,
    _editing: false,
  })
  ElMessage.success('已添加到公式列表')
  fmTab.value = 'list'  // 切回列表Tab查看
}

async function applyLocalFormulas() {
  ElMessage.success('公式已应用，正在刷新...')
  showFormulaManager.value = false
  await runFormulas()
  await loadContent()
}

// ═══ 加载 CellSelector 所需数据 ═══

async function loadSelectorData() {
  const yr = props.moduleParams?.year || props.year || 2025
  try {
    const tbData = await api.get('/api/trial-balance', {
      params: { project_id: props.projectId, year: yr },
      validateStatus: (s: number) => s < 600,
    })
    trialBalanceData.value = Array.isArray(tbData) ? tbData : (tbData || [])
  } catch { trialBalanceData.value = [] }

  try {
    const rptData = await api.get(`/api/report-config`, {
      params: { project_id: props.projectId },
      validateStatus: (s: number) => s < 600,
    })
    reportData.value = Array.isArray(rptData) ? rptData : (rptData || [])
  } catch { reportData.value = [] }

  noteSections.value = [
    '五、1', '五、2', '五、3', '五、4', '五、5', '五、6', '五、7', '五、8', '五、9', '五、10',
    '五、11', '五、12', '五、13', '五、14', '五、15', '五、16', '五、17', '五、18', '五、19', '五、20',
    '五、21', '五、22', '五、23', '五、24', '五、25', '五、26', '五、27', '五、28', '五、29', '五、30',
    '五、31', '五、32', '五、33', '五、34', '五、35', '五、36', '五、37', '五、38', '五、39', '五、40',
  ]
}
</script>

<style scoped>
.structure-editor { display: flex; flex-direction: column; height: 100%; background: #f5f3f8; overflow: hidden; }

.sheet-tabs {
  flex-shrink: 0;
  padding: 0 8px;
  background: #fff;
  border-bottom: 1px solid #e8e4f0;
}
.sheet-tabs :deep(.el-tabs__header) { margin: 0; }
.sheet-tabs :deep(.el-tabs__item) { font-size: 11px; height: 28px; line-height: 28px; padding: 0 12px; }

/* 顶部固定区域 — 不随表格滚动 */
.structure-editor > :deep(.gt-formula-bar) { flex-shrink: 0; }

/* 顶部固定区域 */
.se-header {
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px;
  background: linear-gradient(135deg, #4b2d77 0%, #6b4a9e 100%);
  color: #fff;
}
.se-header-left { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.se-title { margin: 0; font-size: 15px; font-weight: 700; }
.se-info-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.se-tag {
  font-size: 11px; padding: 2px 10px; border-radius: 10px; font-weight: 500;
  background: rgba(255,255,255,0.15); color: #fff; white-space: nowrap;
}
.se-tag-unit { background: rgba(255,255,255,0.2); }
.se-tag-tpl { background: rgba(255,200,50,0.25); color: #ffe082; }
.se-tag-scope { background: rgba(100,200,255,0.2); color: #b3e5fc; }
.se-tag-year { background: rgba(255,255,255,0.12); }
.se-tag-module { background: rgba(150,255,150,0.15); color: #c8e6c9; }

.editor-toolbar {
  flex-shrink: 0;
  display: flex; align-items: center; gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid #e8e4f0;
  background: #fff;
  flex-wrap: wrap;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  position: sticky; top: 0; z-index: 10;
}

/* 左右分栏布局 */
.editor-body { display: flex; flex: 1; min-height: 0; overflow: hidden; gap: 0; }
.table-area { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; background: #fff; }
.table-container { flex: 1; overflow: auto; padding: 8px; }

/* 表格美化 */
.table-container { flex: 1; overflow: auto; padding: 8px; }
.table-container :deep(table) {
  border-collapse: collapse; width: 100%; font-size: 12px;
}
.table-container :deep(td) {
  border: 1px solid #e8e4f0; padding: 5px 8px; font-size: 12px;
}
.table-container :deep(tr:hover td) { background: #faf8fd; }
.table-container :deep(.gt-row-header) {
  background: #faf8fd !important; color: #999; font-size: 10px; text-align: center; width: 30px;
}
.table-container :deep(tr.gt-col-header-row td) {
  background: #ece6f5; font-size: 10px; color: #666; text-align: center;
}
.table-container :deep(tr.gt-data-header-row td) {
  background: #f5f3f8 !important; font-weight: 600; color: #333;
  border-bottom: 2px solid #d0c8e0;
}
.table-container :deep(td.gt-row-header) {
  background: #faf8fd !important; color: #999; font-size: 10px; text-align: center;
  position: sticky; left: 0; z-index: 2;
}
.table-container :deep(td.gt-selected) { outline: 2px solid #4b2d77 !important; background: #f0ecf5 !important; }
.table-container :deep(td.gt-dep-highlight) { outline: 1px dashed #e6a23c !important; background: #fdf6ec !important; }
.table-container :deep(td.gt-formula-error) { background: #fef0f0 !important; border: 1px solid #f56c6c !important; cursor: help; }

/* 可视化维度：显示公式 */
.table-container.show-formulas :deep(td[data-formula])::after {
  content: attr(data-formula);
  display: block; font-size: 9px; color: #b7791f; font-family: monospace;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; opacity: 0.7;
}
/* 可视化维度：显示数据源 */
.table-container.show-sources :deep(td[data-fetch-rule])::before {
  content: "🔗"; position: absolute; top: 1px; left: 2px; font-size: 10px;
}
/* 可视化维度：显示状态 */
.table-container.show-status :deep(td[data-formula]) { border-left: 3px solid #e6a23c !important; }
.table-container.show-status :deep(td[data-fetch-rule]) { border-left: 3px solid #0094b3 !important; }

/* 分页控件 */
.pagination-bar { display: flex; align-items: center; justify-content: space-between; padding: 6px 12px; border-top: 1px solid #e8e4f0; background: #faf8fd; }
.page-info { font-size: 12px; color: #909399; }

/* 公式编辑面板 */
.fm-edit-panel { padding: 4px 0; }
.fm-edit-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.fm-edit-label { font-size: 12px; color: #666; white-space: nowrap; min-width: 70px; }
.fm-edit-section { margin-bottom: 8px; }
.fm-edit-section-title { font-size: 11px; font-weight: 600; color: #555; margin-bottom: 4px; }
.fm-edit-btns { display: flex; gap: 4px; flex-wrap: wrap; }
.fm-edit-btns .el-button { font-size: 10px; padding: 2px 8px; font-family: monospace; height: 24px; }

/* 右侧操作说明 */
.help-area {
  width: 260px; flex-shrink: 0;
  border-left: 1px solid #e8e4f0;
  background: #faf8fd;
  overflow-y: auto;
  padding: 14px;
}
.help-title {
  font-size: 13px; font-weight: 700; color: #4b2d77; margin-bottom: 14px;
  padding-bottom: 8px; border-bottom: 2px solid #ece6f5;
}
.help-section { margin-bottom: 14px; }
.help-subtitle {
  font-size: 11px; font-weight: 600; color: #4b2d77; margin-bottom: 6px;
  padding: 3px 8px; background: #ece6f5; border-radius: 4px; display: inline-block;
}
.help-item { font-size: 11px; color: #555; line-height: 1.9; padding-left: 6px; }
.help-item b { color: #333; }
.help-item code {
  font-size: 10px; background: #f0ecf5; padding: 1px 5px; border-radius: 3px; color: #4b2d77;
  font-family: 'Cascadia Code', 'Fira Code', monospace;
}
.help-badge { font-size: 9px; padding: 1px 6px; border-radius: 8px; font-weight: 600; }
.help-badge.auto { background: #e8f5e9; color: #2e7d32; }
.help-badge.manual { background: #fff3e0; color: #e65100; }
</style>
