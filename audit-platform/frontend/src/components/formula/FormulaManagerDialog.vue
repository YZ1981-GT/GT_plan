<template>
  <el-dialog
    v-model="visible"
    title="公式管理中心"
    width="95%"
    top="2vh"
    append-to-body
    destroy-on-close
  >
    <div class="gt-fm-container">
      <!-- 左侧：树形导航 -->
      <div class="gt-fm-sidebar">
        <div class="gt-fm-sidebar-title">数据源</div>
        <el-tree
          :data="treeData"
          :props="{ label: 'label', children: 'children' }"
          node-key="key"
          highlight-current
          :default-expanded-keys="[]"
          :expand-on-click-node="false"
          draggable
          :allow-drop="allowTreeDrop"
          @node-click="onTreeNodeClick"
          class="gt-fm-tree"
        >
          <template #default="{ node, data }">
            <span class="gt-fm-tree-node">
              <span>{{ data.icon }} {{ node.label }}</span>
              <el-badge v-if="data.count" :value="data.count" type="info" :max="999" />
            </span>
          </template>
        </el-tree>
      </div>

      <!-- 右侧：公式配置 -->
      <div class="gt-fm-main">
        <!-- 当前选中的路径 + 模板类型切换 -->
        <div class="gt-fm-breadcrumb">
          <div style="display: flex; align-items: center; gap: 8px;">
            <el-select v-model="fmTemplateType" size="small" style="width: 100px;" @change="onFmTemplateChange">
              <el-option label="国企版" value="soe" />
              <el-option label="上市版" value="listed" />
            </el-select>
            <span style="color: #ccc;">|</span>
            <span style="color: #999; font-size: 12px;">{{ selectedPath }}</span>
          </div>
          <div style="display: flex; gap: 6px; align-items: center;">
            <el-button size="small" @click="showFormulaDashboard = true">📊 公式看板</el-button>
            <SharedTemplatePicker
              config-type="formula_config"
              :project-id="projectId"
              :get-config-data="getFormulaConfigData"
              @applied="onTemplateApplied"
            />
            <el-button size="small" @click="onImportPresetFormulas" :loading="loadingData">📥 导入预设</el-button>
            <el-button size="small" @click="showFormulaImport = true">📥 Excel导入</el-button>
            <el-button size="small" @click="onAddFormulaRow">+ 新增公式</el-button>
            <el-button size="small" @click="onSaveAllFormulas" :loading="applying">💾 保存</el-button>
            <el-button size="small" type="primary" @click="onApplyFormulas" :loading="applying">⚡ 应用自动运算</el-button>
          </div>
        </div>

        <!-- 分类 Tab -->
        <el-tabs v-model="activeCategory" size="small" style="margin-bottom: 8px;">
          <el-tab-pane name="all">
            <template #label>全部 ({{ currentRows.length }})</template>
          </el-tab-pane>
          <el-tab-pane name="auto_calc">
            <template #label>⚡ 自动运算 ({{ categoryCounts.auto_calc }})</template>
          </el-tab-pane>
          <el-tab-pane name="logic_check">
            <template #label>🔍 逻辑审核 ({{ categoryCounts.logic_check }})</template>
          </el-tab-pane>
          <el-tab-pane name="reasonability">
            <template #label>💡 提示合理性 ({{ categoryCounts.reasonability }})</template>
          </el-tab-pane>
          <el-tab-pane name="no_formula">
            <template #label>⬜ 未配置 ({{ currentRows.length - currentRows.filter(r => r.formula).length }})</template>
          </el-tab-pane>
        </el-tabs>

        <!-- 批量操作栏 -->
        <div v-if="selectedRows.length > 0 && !isCrossCheckMode" class="gt-fm-batch-bar">
          <span style="font-size: 12px; color: #666;">已选 <b>{{ selectedRows.length }}</b> 条</span>
          <el-button size="small" @click="onBatchApplyCategory('auto_calc')">⚡ 标记为自动运算</el-button>
          <el-button size="small" @click="onBatchApplyCategory('logic_check')">🔍 标记为逻辑审核</el-button>
          <el-button size="small" @click="onBatchApplyCategory('reasonability')">💡 标记为合理性</el-button>
          <el-button size="small" style="color: #999;" @click="onBatchClearFormula">清除公式</el-button>
          <el-button size="small" style="color: #999;" @click="selectedRows = []">取消选择</el-button>
        </div>

        <!-- 公式表格（报表/附注/底稿） -->
        <el-table v-if="!isCrossCheckMode" ref="formulaTableRef" :data="filteredRows" size="small" border max-height="calc(100vh - 300px)" style="width: 100%"
          :header-cell-style="{ background: '#f8f6fb', fontSize: '12px', whiteSpace: 'nowrap' }"
          :row-class-name="getRowClassName"
          @selection-change="onSelectionChange"
          @row-click="onRowClick"
          highlight-current-row>
          <el-table-column type="selection" width="40" />
          <el-table-column prop="row_code" label="行次" width="90">
            <template #default="{ row }">
              <span style="font-size: 11px; color: #999; white-space: nowrap;">{{ row.row_code }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="row_name" label="项目" min-width="180" show-overflow-tooltip />
          <el-table-column label="公式" min-width="260">
            <template #default="{ row }">
              <el-input v-if="editingId === row.id" v-model="editFormula" size="small" placeholder="如 TB('1001','期末余额') 或 ROW('BS-001')+ROW('BS-002')" />
              <code v-else-if="row.formula" @dblclick="startEdit(row)" style="font-size: 11px; color: #555; word-break: break-all; cursor: pointer;" :title="'双击编辑公式'">{{ row.formula }}</code>
              <span v-else @click="startEdit(row)" style="color: #bbb; cursor: pointer; font-size: 11px; border: 1px dashed #ddd; padding: 2px 8px; border-radius: 4px;" title="点击添加公式">
                + 点击添加公式
              </span>
            </template>
          </el-table-column>
          <el-table-column label="分类" width="110" align="center">
            <template #default="{ row }">
              <el-select v-if="editingId === row.id" v-model="editCategory" size="small" style="width: 95px">
                <el-option label="自动运算" value="auto_calc" />
                <el-option label="逻辑审核" value="logic_check" />
                <el-option label="合理性" value="reasonability" />
              </el-select>
              <el-tag v-else :type="categoryTagType(row.formula_category)" size="small">
                {{ categoryLabel(row.formula_category) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">
              <el-input v-if="editingId === row.id" v-model="editDescription" size="small" />
              <span v-else style="font-size: 12px; color: #888">{{ row.formula_description || '' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="来源" width="70" align="center">
            <template #default="{ row }">
              <span v-if="isPresetFormula(row)" style="font-size: 10px; color: #4b2d77; background: #f0ecf5; padding: 1px 6px; border-radius: 3px;">预设</span>
              <span v-else-if="row.formula" style="font-size: 10px; color: #999;">自定义</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80" align="center">
            <template #default="{ row }">
              <el-button v-if="editingId !== row.id" size="small" link type="primary" @click.stop="startEdit(row)">编辑</el-button>
              <el-button v-else size="small" link @click.stop="saveEdit(row)" style="color: #1e8a38;">保存</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="gt-fm-footer">
          <span style="font-size: 11px; color: #999;">共 {{ currentRows.length }} 行，{{ currentRows.filter(r => r.formula).length }} 个公式</span>
        </div>

        <!-- 表间审核模式 -->
        <div v-if="isCrossCheckMode" style="flex: 1;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <span style="font-size: 13px; font-weight: 600; color: #333;">{{ selectedPath }}</span>
            <el-button size="small" type="primary" @click="onAddCrossRule">+ 新增规则</el-button>
          </div>
          <el-table :data="crossCheckRulesForCurrent" size="small" border style="width: 100%;"
            max-height="calc(100vh - 300px)"
            :header-cell-style="{ background: '#f8f6fb', fontSize: '12px', whiteSpace: 'nowrap' }">
            <el-table-column type="index" label="#" width="50" />
            <el-table-column label="规则名称" min-width="200">
              <template #default="{ row }">
                <el-input v-if="row._editing" v-model="row.label" size="small" />
                <span v-else style="font-size: 12px;">{{ row.label }}</span>
              </template>
            </el-table-column>
            <el-table-column label="左侧（源）" min-width="180">
              <template #default="{ row }">
                <el-input v-if="row._editing" v-model="row.left_ref" size="small" placeholder="如 BS-002 或 NOTE('货币资金','合计')" />
                <code v-else style="font-size: 11px; color: #666;">{{ row.left_ref || '—' }}</code>
              </template>
            </el-table-column>
            <el-table-column label="关系" width="60" align="center">
              <template #default><span style="font-size: 14px;">=</span></template>
            </el-table-column>
            <el-table-column label="右侧（目标）" min-width="180">
              <template #default="{ row }">
                <el-input v-if="row._editing" v-model="row.right_ref" size="small" placeholder="如 E1-1.审定数 或 NOTE('货币资金','期末')" />
                <code v-else style="font-size: 11px; color: #666;">{{ row.right_ref || '—' }}</code>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" align="center">
              <template #default="{ row, $index }">
                <div style="display: flex; gap: 4px; justify-content: center;">
                  <el-button v-if="!row._editing" size="small" link type="primary" @click="row._editing = true">编辑</el-button>
                  <el-button v-if="row._editing" size="small" link type="success" @click="row._editing = false">完成</el-button>
                  <el-button size="small" link style="color: #999;" @click="onRemoveCrossRule($index)">删除</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
          <div style="margin-top: 8px; text-align: right; font-size: 11px; color: #999;">
            {{ crossCheckRulesForCurrent.length }} 条规则
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>

    <!-- 公式看板弹窗 -->
    <el-dialog
      v-model="showFormulaDashboard"
      title="📊 公式看板 — 全局审核公式总览"
      width="90%"
      top="3vh"
      append-to-body
      destroy-on-close
    >
      <div style="margin-bottom: 10px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
        <el-input v-model="dashboardSearch" size="small" placeholder="搜索公式/行次/说明..." clearable style="width: 240px;" />
        <el-select v-model="dashboardGroupBy" size="small" style="width: 140px;">
          <el-option label="按报表类型" value="report_type" />
          <el-option label="按公式分类" value="category" />
          <el-option label="按数据源" value="source" />
          <el-option label="全部平铺" value="flat" />
        </el-select>
        <el-select v-model="dashboardFilterCategory" size="small" style="width: 120px;" clearable placeholder="筛选分类">
          <el-option label="自动运算" value="auto_calc" />
          <el-option label="逻辑审核" value="logic_check" />
          <el-option label="合理性" value="reasonability" />
        </el-select>
        <span style="font-size: 11px; color: #999; margin-left: auto;">
          共 {{ dashboardFilteredRows.length }} 条公式
        </span>
      </div>

      <!-- 分组展示 -->
      <div v-if="dashboardGroupBy !== 'flat'" style="max-height: 65vh; overflow-y: auto;">
        <div v-for="group in dashboardGroupedData" :key="group.key" style="margin-bottom: 12px;">
          <div class="gt-fm-dash-group-title" @click="group._open = !group._open">
            {{ group._open ? '▼' : '▶' }} {{ group.label }}
            <span style="font-size: 10px; color: #999; margin-left: 6px;">{{ group.rows.length }} 条</span>
          </div>
          <el-table v-show="group._open" :data="group.rows" size="small" border style="width: 100%;"
            :header-cell-style="{ background: '#f8f6fb', fontSize: '11px', whiteSpace: 'nowrap' }">
            <el-table-column prop="row_code" label="行次" width="90" />
            <el-table-column prop="row_name" label="项目" min-width="150" show-overflow-tooltip />
            <el-table-column prop="formula" label="公式" min-width="240" show-overflow-tooltip>
              <template #default="{ row }">
                <code style="font-size: 10px; color: #555;">{{ row.formula }}</code>
              </template>
            </el-table-column>
            <el-table-column label="分类" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="categoryTagType(row.formula_category)" size="small">{{ categoryLabel(row.formula_category) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="formula_description" label="说明" min-width="140" show-overflow-tooltip />
            <el-table-column label="来源" width="80" align="center">
              <template #default="{ row }">
                <span style="font-size: 10px; color: #999;">{{ row._source_type || '报表' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="60" align="center">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="onDashboardEdit(row)">编辑</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <!-- 平铺展示 -->
      <el-table v-else :data="dashboardFilteredRows" size="small" border max-height="65vh" style="width: 100%;"
        :header-cell-style="{ background: '#f8f6fb', fontSize: '11px', whiteSpace: 'nowrap' }">
        <el-table-column prop="row_code" label="行次" width="90" />
        <el-table-column prop="row_name" label="项目" min-width="150" show-overflow-tooltip />
        <el-table-column prop="formula" label="公式" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <code style="font-size: 10px; color: #555;">{{ row.formula }}</code>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="categoryTagType(row.formula_category)" size="small">{{ categoryLabel(row.formula_category) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="formula_description" label="说明" min-width="140" show-overflow-tooltip />
        <el-table-column prop="_report_type_label" label="报表" width="100" />
        <el-table-column label="操作" width="60" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="onDashboardEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="showFormulaDashboard = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 公式编辑弹窗 -->
    <FormulaEditDialog
      v-model="showFormulaEdit"
      :row="editingRow"
      :source-rows="currentRows"
      :applicable-standard="`${fmTemplateType}_standalone`"
      @save="onFormulaEditSave"
    />

    <!-- 统一导入弹窗 -->
    <UnifiedImportDialog
      v-model="showFormulaImport"
      import-type="formula"
      :project-id="props.projectId"
      :year="props.year"
      @imported="onFormulaFileImported"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import FormulaEditDialog from './FormulaEditDialog.vue'
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'

const props = defineProps<{
  modelValue: boolean
  rows: any[]
  projectId?: string
  year?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'saved': []
  'applied': []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// ── 树形导航数据 ──
const selectedNodeKey = ref('report_balance_sheet')
const selectedPath = ref('报表 > 资产负债表')
const fmTemplateType = ref('soe')

function onFmTemplateChange() {
  // 切换模板类型后清空缓存，重新加载
  allRowsMap.value = {}
  noteTreeLoaded.value = false
  noteTreeChildren.value = []
  loadNoteTree()
  loadRowsForNode(selectedNodeKey.value)
}

function allowTreeDrop(draggingNode: any, dropNode: any, type: string) {
  return draggingNode.parent === dropNode.parent && type !== 'inner'
}

// ── 动态附注树（从实际模板加载） ──
const noteTreeChildren = ref<any[]>([])
const noteTreeLoaded = ref(false)

async function loadNoteTree() {
  if (noteTreeLoaded.value) return
  try {
    const { data } = await http.get(`/api/note-templates/${fmTemplateType.value}`, {
      validateStatus: (s: number) => s < 600,
    })
    const sections = data?.data ?? data ?? []
    if (!Array.isArray(sections) || !sections.length) return

    // 按章节分组构建树
    const chapterMap: Record<string, { label: string; children: any[] }> = {}
    const chapterOrder = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']

    for (const sec of sections) {
      const title = sec.section_title || sec.title || ''
      const sectionId = sec.section_id || sec.note_section || ''
      // 提取章节编号（如 "五、1" → 章="五"）
      const chapterMatch = sectionId.match(/^([一二三四五六七八九十]+)/)
      const chapter = chapterMatch ? chapterMatch[1] : '其他'

      if (!chapterMap[chapter]) {
        const chapterLabels: Record<string, string> = {
          '一': '一、公司概况', '二': '二、编制基础', '三': '三、会计政策',
          '四': '四、税项', '五': '五、报表科目注释', '六': '六、其他',
          '七': '七、关联方', '八': '八、或有事项', '九': '九、承诺',
          '十': '十、日后事项',
        }
        chapterMap[chapter] = {
          label: chapterLabels[chapter] || `${chapter}、其他`,
          children: [],
        }
      }
      chapterMap[chapter].children.push({
        key: `note_${sectionId.replace(/[、，。\s]/g, '_')}`,
        label: title.length > 20 ? title.slice(0, 20) + '...' : title,
        icon: '',
        _sectionTitle: title,
        _sectionId: sectionId,
        _tableCount: sec.tables?.length || 0,
        count: sec.check_presets ? Object.keys(sec.check_presets).length : 0,
      })
    }

    // 按章节顺序排列
    const result: any[] = []
    for (const ch of chapterOrder) {
      if (chapterMap[ch]) {
        result.push({
          key: `note_chapter_${ch}`,
          label: chapterMap[ch].label,
          icon: '',
          children: chapterMap[ch].children,
        })
      }
    }
    if (chapterMap['其他']) {
      result.push({
        key: 'note_chapter_other',
        label: '其他',
        icon: '',
        children: chapterMap['其他'].children,
      })
    }
    noteTreeChildren.value = result
    noteTreeLoaded.value = true
  } catch { /* ignore, fallback to static tree */ }
}

// 静态附注树（降级用）
const staticNoteTree = [
  { key: 'note_current_asset', label: '流动资产', icon: '', children: [
    { key: 'note_cash', label: '货币资金', icon: '', _sectionTitle: '货币资金' },
    { key: 'note_ar', label: '应收账款', icon: '', _sectionTitle: '应收账款' },
    { key: 'note_other_recv', label: '其他应收款', icon: '', _sectionTitle: '其他应收款' },
    { key: 'note_inventory', label: '存货', icon: '', _sectionTitle: '存货' },
  ]},
  { key: 'note_noncurrent_asset', label: '长期资产', icon: '', children: [
    { key: 'note_fixed_asset', label: '固定资产', icon: '', _sectionTitle: '固定资产' },
    { key: 'note_intangible', label: '无形资产', icon: '', _sectionTitle: '无形资产' },
    { key: 'note_lt_equity', label: '长期股权投资', icon: '', _sectionTitle: '长期股权投资' },
  ]},
  { key: 'note_liability', label: '负债', icon: '', children: [
    { key: 'note_ap', label: '应付账款', icon: '', _sectionTitle: '应付账款' },
    { key: 'note_employee_pay', label: '应付职工薪酬', icon: '', _sectionTitle: '应付职工薪酬' },
  ]},
  { key: 'note_income_expense', label: '损益类', icon: '', children: [
    { key: 'note_revenue', label: '营业收入/成本', icon: '', _sectionTitle: '营业收入' },
    { key: 'note_finance_exp', label: '财务费用', icon: '', _sectionTitle: '财务费用' },
  ]},
]

const treeData = computed(() => [
  {
    key: 'report', label: '报表', icon: '📊', children: [
      { key: 'report_balance_sheet', label: '资产负债表', icon: '', count: countFormulas('balance_sheet') },
      { key: 'report_income_statement', label: '利润表', icon: '', count: countFormulas('income_statement') },
      { key: 'report_cash_flow_statement', label: '现金流量表', icon: '', count: countFormulas('cash_flow_statement') },
      { key: 'report_equity_statement', label: '权益变动表', icon: '', count: countFormulas('equity_statement') },
      { key: 'report_cash_flow_supplement', label: '现金流附表', icon: '', count: countFormulas('cash_flow_supplement') },
      { key: 'report_impairment_provision', label: '资产减值准备表', icon: '', count: countFormulas('impairment_provision') },
    ],
  },
  {
    key: 'note', label: '附注', icon: '📝',
    children: noteTreeChildren.value.length ? noteTreeChildren.value : staticNoteTree,
  },
  {
    key: 'workpaper', label: '底稿', icon: '📋', children: [
      { key: 'wp_d', label: 'D 销售循环', icon: '', children: [
        { key: 'wp_d_ar', label: '应收账款', icon: '', children: [
          { key: 'wp_d2_1', label: 'D2-1 审定表', icon: '' },
          { key: 'wp_d2_2', label: 'D2-2 明细表', icon: '' },
          { key: 'wp_d2_3', label: 'D2-3 坏账准备', icon: '' },
        ]},
        { key: 'wp_d_revenue', label: '营业收入', icon: '', children: [
          { key: 'wp_d1_1', label: 'D1-1 审定表', icon: '' },
          { key: 'wp_d1_2', label: 'D1-2 收入明细', icon: '' },
        ]},
      ]},
      { key: 'wp_e', label: 'E 货币资金', icon: '', children: [
        { key: 'wp_e_cash', label: '货币资金', icon: '', children: [
          { key: 'wp_e1_1', label: 'E1-1 审定表', icon: '' },
          { key: 'wp_e1_2', label: 'E1-2 现金明细', icon: '' },
          { key: 'wp_e1_3', label: 'E1-3 银行存款', icon: '' },
        ]},
      ]},
      { key: 'wp_f', label: 'F 采购循环', icon: '', children: [
        { key: 'wp_f_ap', label: '应付账款', icon: '', children: [
          { key: 'wp_f1_1', label: 'F1-1 审定表', icon: '' },
        ]},
        { key: 'wp_f_prepay', label: '预付款项', icon: '', children: [
          { key: 'wp_f2_1', label: 'F2-1 审定表', icon: '' },
        ]},
      ]},
      { key: 'wp_g', label: 'G 生产循环', icon: '', children: [
        { key: 'wp_g_inv', label: '存货', icon: '', children: [
          { key: 'wp_g1_1', label: 'G1-1 审定表', icon: '' },
        ]},
      ]},
      { key: 'wp_h', label: 'H 固定资产', icon: '', children: [
        { key: 'wp_h_fa', label: '固定资产', icon: '', children: [
          { key: 'wp_h1_1', label: 'H1-1 审定表', icon: '' },
          { key: 'wp_h1_2', label: 'H1-2 明细表', icon: '' },
          { key: 'wp_h1_12', label: 'H1-12 折旧测算', icon: '' },
        ]},
        { key: 'wp_h_cip', label: '在建工程', icon: '', children: [
          { key: 'wp_h2_1', label: 'H2-1 审定表', icon: '' },
        ]},
      ]},
      { key: 'wp_i', label: 'I 无形资产', icon: '', children: [
        { key: 'wp_i_ia', label: '无形资产', icon: '', children: [
          { key: 'wp_i1_1', label: 'I1-1 审定表', icon: '' },
        ]},
      ]},
      { key: 'wp_j', label: 'J 投资循环', icon: '', children: [
        { key: 'wp_j_lte', label: '长期股权投资', icon: '', children: [
          { key: 'wp_j1_1', label: 'J1-1 审定表', icon: '' },
          { key: 'wp_j1_2', label: 'J1-2 明细表', icon: '' },
        ]},
      ]},
      { key: 'wp_k', label: 'K 筹资循环', icon: '', children: [
        { key: 'wp_k_borrow', label: '借款', icon: '', children: [
          { key: 'wp_k1_1', label: 'K1-1 短期借款审定表', icon: '' },
          { key: 'wp_k2_1', label: 'K2-1 长期借款审定表', icon: '' },
        ]},
      ]},
      { key: 'wp_l', label: 'L 人力循环', icon: '', children: [
        { key: 'wp_l_salary', label: '应付职工薪酬', icon: '', children: [
          { key: 'wp_l1_1', label: 'L1-1 审定表', icon: '' },
        ]},
      ]},
      { key: 'wp_m', label: 'M 权益循环', icon: '', children: [
        { key: 'wp_m_equity', label: '所有者权益', icon: '', children: [
          { key: 'wp_m1_1', label: 'M1-1 审定表', icon: '' },
        ]},
      ]},
    ],
  },
  {
    key: 'cross_check', label: '表间审核', icon: '🔗', children: [
      { key: 'cross_report_note', label: '报表 ↔ 附注', icon: '🔄', children: crossCheckItems.value.report_note },
      { key: 'cross_report_wp', label: '报表 ↔ 底稿', icon: '🔄', children: crossCheckItems.value.report_wp },
      { key: 'cross_note_wp', label: '附注 ↔ 底稿', icon: '🔄', children: crossCheckItems.value.note_wp },
    ],
  },
])

function countFormulas(reportType: string): number {
  return (allRowsMap.value[reportType] || []).filter(r => r.formula).length
}

// ── 表间审核自定义规则 ──
const crossCheckItems = ref<Record<string, any[]>>({
  report_note: [
    { key: 'cross_rn_1', label: 'BS货币资金 = 附注货币资金合计', icon: '📌' },
    { key: 'cross_rn_2', label: 'BS应收账款 = 附注应收账款合计', icon: '📌' },
    { key: 'cross_rn_3', label: 'IS营业收入 = 附注营业收入合计', icon: '📌' },
  ],
  report_wp: [
    { key: 'cross_rw_1', label: 'BS货币资金 = E1-1审定数', icon: '📌' },
    { key: 'cross_rw_2', label: 'BS应收账款 = D2-1审定数', icon: '📌' },
  ],
  note_wp: [
    { key: 'cross_nw_1', label: '附注货币资金 = E1-1审定数', icon: '📌' },
  ],
})

// ── 数据加载 ──
const allRowsMap = ref<Record<string, any[]>>({})
const loadingData = ref(false)
const showFormulaImport = ref(false)
const notePresetFormulas = ref<any[]>([])

async function loadRowsForNode(nodeKey: string) {
  if (nodeKey.startsWith('report_')) {
    const reportType = nodeKey.replace('report_', '')
    const cacheKey = `${fmTemplateType.value}_${reportType}`
    if (allRowsMap.value[cacheKey]) {
      allRowsMap.value[reportType] = allRowsMap.value[cacheKey]
      return
    }
    loadingData.value = true
    try {
      const standard = `${fmTemplateType.value}_standalone`
      const { data } = await http.get('/api/report-config', {
        params: { report_type: reportType, applicable_standard: standard },
        validateStatus: (s: number) => s < 600,
      })
      const rows = data?.data ?? data ?? []
      allRowsMap.value[reportType] = rows
      allRowsMap.value[cacheKey] = rows
    } catch { /* ignore */ }
    finally { loadingData.value = false }
  }
}

// 初始加载当前报表的数据
watch(visible, async (v) => {
  if (v) {
    // 加载动态附注树
    loadNoteTree()
    // 用传入的 rows 作为当前报表的数据
    if (props.rows?.length) {
      const firstCode = props.rows[0]?.row_code || ''
      let rt = 'balance_sheet'
      if (firstCode.startsWith('IS-')) rt = 'income_statement'
      else if (firstCode.startsWith('CFS-')) rt = 'cash_flow_statement'
      else if (firstCode.startsWith('EQ-')) rt = 'equity_statement'
      else if (firstCode.startsWith('CFSS-')) rt = 'cash_flow_supplement'
      else if (firstCode.startsWith('IMP-')) rt = 'impairment_provision'
      allRowsMap.value[rt] = props.rows
      selectedNodeKey.value = `report_${rt}`
    }
  }
})

function onTreeNodeClick(data: any) {
  if (!data.children || data.children.length === 0) {
    selectedNodeKey.value = data.key
    // 构建路径
    if (data.key.startsWith('report_')) {
      selectedPath.value = `报表 > ${data.label}`
    } else if (data.key.startsWith('note_')) {
      selectedPath.value = `附注 > ${data._sectionTitle || data.label}`
      // 自动加载附注预设公式（如果还没加载）
      if (!notePresetFormulas.value.length) {
        onImportPresetFormulas()
      }
    } else if (data.key.startsWith('wp_')) {
      selectedPath.value = `底稿 > ${data.label}`
    } else if (data.key.startsWith('cross_')) {
      selectedPath.value = `表间审核 > ${data.label}`
    }
    loadRowsForNode(data.key)
  }
}

// ── 当前显示的行 ──
const currentRows = computed(() => {
  if (selectedNodeKey.value.startsWith('report_')) {
    const rt = selectedNodeKey.value.replace('report_', '')
    return allRowsMap.value[rt] || []
  }
  // 附注节点：显示该章节的预设公式
  if (selectedNodeKey.value.startsWith('note_') && notePresetFormulas.value.length) {
    // 从树节点获取 _sectionTitle
    const nodeKey = selectedNodeKey.value
    let targetTitle = ''

    // 在动态树中查找
    for (const chapter of noteTreeChildren.value) {
      for (const child of (chapter.children || [])) {
        if (child.key === nodeKey) {
          targetTitle = child._sectionTitle || child.label
          break
        }
      }
      if (targetTitle) break
    }
    // 降级到静态树
    if (!targetTitle) {
      for (const group of staticNoteTree) {
        for (const child of (group.children || [])) {
          if (child.key === nodeKey) {
            targetTitle = (child as any)._sectionTitle || child.label
            break
          }
        }
        if (targetTitle) break
      }
    }

    if (targetTitle) {
      return notePresetFormulas.value
        .filter(f => (f.section_title || '').includes(targetTitle))
        .map((f, i) => ({
          id: `note_preset_${i}`,
          row_code: f.note_section,
          row_name: f.section_title,
          formula: f.formula,
          formula_category: f.category,
          formula_description: f.description,
          formula_source: f.source,
        }))
    }
    // 大类节点：显示全部
    return notePresetFormulas.value.map((f, i) => ({
      id: `note_preset_${i}`,
      row_code: f.note_section,
      row_name: f.section_title,
      formula: f.formula,
      formula_category: f.category,
      formula_description: f.description,
      formula_source: f.source,
    }))
  }
  return []
})

const isCrossCheckMode = computed(() => selectedNodeKey.value.startsWith('cross_'))

// 表间审核规则
const crossCheckRulesMap = ref<Record<string, any[]>>({
  cross_report_note: [
    { label: 'BS货币资金 = 附注货币资金合计', left_ref: "REPORT('BS-002','期末')", right_ref: "NOTE('货币资金','合计','期末')", _editing: false },
    { label: 'BS应收账款 = 附注应收账款合计', left_ref: "REPORT('BS-008','期末')", right_ref: "NOTE('应收账款','合计','期末')", _editing: false },
    { label: 'IS营业收入 = 附注营业收入合计', left_ref: "REPORT('IS-002','本期')", right_ref: "NOTE('营业收入','合计','本期')", _editing: false },
  ],
  cross_report_wp: [
    { label: 'BS货币资金 = E1-1审定数', left_ref: "REPORT('BS-002','期末')", right_ref: "WP('E1-1','审定数')", _editing: false },
    { label: 'BS应收账款 = D2-1审定数', left_ref: "REPORT('BS-008','期末')", right_ref: "WP('D2-1','审定数')", _editing: false },
  ],
  cross_note_wp: [
    { label: '附注货币资金 = E1-1审定数', left_ref: "NOTE('货币资金','合计','期末')", right_ref: "WP('E1-1','审定数')", _editing: false },
  ],
})

const crossCheckRulesForCurrent = computed(() => {
  const key = selectedNodeKey.value
  return crossCheckRulesMap.value[key] || []
})

function onAddCrossRule() {
  const key = selectedNodeKey.value
  if (!crossCheckRulesMap.value[key]) crossCheckRulesMap.value[key] = []
  crossCheckRulesMap.value[key].push({
    label: '新规则',
    left_ref: '',
    right_ref: '',
    _editing: true,
  })
}

function onRemoveCrossRule(index: number) {
  const key = selectedNodeKey.value
  crossCheckRulesMap.value[key]?.splice(index, 1)
}

// ── 分类筛选 ──
const activeCategory = ref('all')

const filteredRows = computed(() => {
  const rows = currentRows.value
  if (activeCategory.value === 'all') return rows
  if (activeCategory.value === 'no_formula') return rows.filter(r => !r.formula)
  return rows.filter(r => r.formula && r.formula_category === activeCategory.value)
})

const categoryCounts = computed(() => ({
  auto_calc: currentRows.value.filter(r => r.formula && r.formula_category === 'auto_calc').length,
  logic_check: currentRows.value.filter(r => r.formula && r.formula_category === 'logic_check').length,
  reasonability: currentRows.value.filter(r => r.formula && r.formula_category === 'reasonability').length,
}))

// ── 选择 ──
const selectedRows = ref<any[]>([])
const formulaTableRef = ref<any>(null)

function onSelectionChange(rows: any[]) {
  selectedRows.value = rows
}

function onRowClick(_row: any) {
  // 单击行时高亮，不自动打开编辑
}

function getRowClassName({ row }: { row: any }) {
  if (row.formula && row.formula_category === 'auto_calc') return 'gt-fm-row-auto'
  if (row.formula && row.formula_category === 'logic_check') return 'gt-fm-row-logic'
  if (row.formula && row.formula_category === 'reasonability') return 'gt-fm-row-reason'
  if (!row.formula) return 'gt-fm-row-empty'
  return ''
}

function isPresetFormula(row: any): boolean {
  const src = row.formula_source || ''
  return src.startsWith('check_presets.') || src === '试算表审定数' || src === '报表行次引用'
}

function onBatchApplyCategory(cat: string) {
  for (const row of selectedRows.value) {
    row.formula_category = cat
  }
  ElMessage.success(`已将 ${selectedRows.value.length} 条标记为 ${categoryLabel(cat)}`)
}

function onBatchClearFormula() {
  for (const row of selectedRows.value) {
    row.formula = ''
    row.formula_category = ''
    row.formula_description = ''
  }
  ElMessage.success(`已清除 ${selectedRows.value.length} 条公式`)
  selectedRows.value = []
}

// ── 编辑 ──
const editingId = ref<string | null>(null)
const editFormula = ref('')
const editCategory = ref('auto_calc')
const editDescription = ref('')
const applying = ref(false)

// 公式编辑弹窗
const showFormulaEdit = ref(false)
const editingRow = ref<any>(null)

function startEdit(row: any) {
  editingRow.value = row
  showFormulaEdit.value = true
}

async function onFormulaEditSave(data: { formula: string; category: string; description: string }) {
  const row = editingRow.value
  if (!row) return

  row.formula = data.formula
  row.formula_category = data.category
  row.formula_description = data.description

  if (row._isNew) {
    // 新增公式行——添加到当前列表并尝试保存到后端
    if (data.formula) {
      const rows = currentRows.value
      row.row_number = rows.length + 1
      rows.push(row)

      if (selectedNodeKey.value.startsWith('report_')) {
        const reportType = selectedNodeKey.value.replace('report_', '')
        try {
          const { data: saved } = await http.post('/api/report-config', {
            report_type: reportType,
            applicable_standard: `${fmTemplateType.value}_standalone`,
            row_number: row.row_number,
            row_code: row.row_code,
            row_name: row.row_name,
            formula: data.formula,
            formula_category: data.category,
            formula_description: data.description,
          }, { validateStatus: (s: number) => s < 600 })
          if (saved?.id) row.id = saved.id
          row._isNew = false
          ElMessage.success('新公式已保存')
          emit('saved')
        } catch {
          ElMessage.warning('公式已添加到列表，保存到后端失败')
        }
      }
    }
    return
  }

  // 已有行——更新到后端
  if (row.id) {
    try {
      await http.put(`/api/report-config/${row.id}`, {
        formula: data.formula || null,
        formula_category: data.category,
        formula_description: data.description,
      })
      ElMessage.success('公式已保存')
      emit('saved')
    } catch {
      ElMessage.error('保存失败')
    }
  }
}

async function saveEdit(row: any) {
  // 兼容行内编辑（保留）
  if (!row.id) return
  try {
    await http.put(`/api/report-config/${row.id}`, {
      formula: editFormula.value || null,
      formula_category: editCategory.value,
      formula_description: editDescription.value,
    })
    row.formula = editFormula.value
    row.formula_category = editCategory.value
    row.formula_description = editDescription.value
    editingId.value = null
    ElMessage.success('公式已保存')
    emit('saved')
  } catch {
    ElMessage.error('保存失败')
  }
}

function categoryTagType(cat: string | null) {
  if (cat === 'auto_calc') return 'primary'
  if (cat === 'logic_check') return 'warning'
  if (cat === 'reasonability') return 'info'
  return ''
}

function categoryLabel(cat: string | null) {
  if (cat === 'auto_calc') return '自动运算'
  if (cat === 'logic_check') return '逻辑审核'
  if (cat === 'reasonability') return '合理性'
  return '未分类'
}

async function onApplyFormulas() {
  if (!props.projectId || !props.year) {
    ElMessage.warning('缺少项目信息')
    return
  }
  applying.value = true
  try {
    await http.post('/api/reports/generate', { project_id: props.projectId, year: props.year })
    ElMessage.success('自动运算公式已应用，报表数据已刷新')
    emit('applied')
  } catch (e: any) {
    ElMessage.error('应用失败: ' + (e?.message || ''))
  } finally {
    applying.value = false
  }
}

function onFormulaFileImported() {
  showFormulaImport.value = false
  loadFormulas()
}

async function onImportPresetFormulas() {
  loadingData.value = true

  // 报表类：从 report_config 加载
  if (selectedNodeKey.value.startsWith('report_')) {
    const reportType = selectedNodeKey.value.replace('report_', '')
    try {
      const standard = `${fmTemplateType.value}_standalone`
      const { data } = await http.get('/api/report-config', {
        params: { report_type: reportType, applicable_standard: standard },
        validateStatus: (s: number) => s < 600,
      })
      const rows = data?.data ?? data ?? []
      allRowsMap.value[reportType] = rows
      const formulaCount = rows.filter((r: any) => r.formula).length
      ElMessage.success(`已导入 ${rows.length} 行，其中 ${formulaCount} 个预设公式`)
    } catch { ElMessage.error('导入失败') }
    finally { loadingData.value = false }
    return
  }

  // 附注类 / 表间审核：从附注校验预设公式加载
  if (selectedNodeKey.value.startsWith('note_') || selectedNodeKey.value.startsWith('cross_')) {
    try {
      const { data } = await http.get(`/api/note-templates/preset-formulas/${fmTemplateType.value}`, {
        validateStatus: (s: number) => s < 600,
      })
      const presets = data?.data ?? data ?? []
      notePresetFormulas.value = presets
      ElMessage.success(`已加载 ${presets.length} 条附注校验预设公式（${fmTemplateType.value === 'soe' ? '国企版' : '上市版'}）`)
    } catch { ElMessage.error('加载附注预设公式失败') }
    finally { loadingData.value = false }
    return
  }

  loadingData.value = false
  ElMessage.info('当前节点暂无预设公式')
}

// ── 共享模板 ──
function getFormulaConfigData(): Record<string, any> {
  // 收集当前所有已配置公式的行
  const formulaRows: any[] = []
  for (const [key, rows] of Object.entries(allRowsMap.value)) {
    if (key.includes('_')) continue
    for (const r of (rows as any[])) {
      if (r.formula) {
        formulaRows.push({
          row_code: r.row_code,
          row_name: r.row_name,
          formula: r.formula,
          formula_category: r.formula_category,
          formula_description: r.formula_description,
          report_type: key,
        })
      }
    }
  }
  return { formulas: formulaRows, template_type: fmTemplateType.value }
}

function onTemplateApplied(data: Record<string, any>) {
  // 将引用的模板公式应用到当前配置
  const formulas = data?.formulas || []
  if (!formulas.length) {
    ElMessage.warning('模板中无公式数据')
    return
  }
  let applied = 0
  for (const f of formulas) {
    const rt = f.report_type
    const rows = allRowsMap.value[rt]
    if (!rows) continue
    const target = (rows as any[]).find((r: any) => r.row_code === f.row_code)
    if (target && !target.formula) {
      target.formula = f.formula
      target.formula_category = f.formula_category
      target.formula_description = f.formula_description
      applied++
    }
  }
  ElMessage.success(`已引用 ${applied} 条公式（已有公式的行不覆盖）`)
}

function onAddFormulaRow() {
  // 打开公式编辑弹窗，不绑定具体行——用户自由编辑
  editingRow.value = {
    id: null,
    row_code: `CUSTOM-${(currentRows.value?.length || 0) + 1}`,
    row_name: '自定义公式',
    formula: '',
    formula_category: 'logic_check',
    formula_description: '',
    _isNew: true,
  }
  showFormulaEdit.value = true
}

async function onSaveAllFormulas() {
  const rows = currentRows.value.filter(r => r.formula)
  if (!rows.length) {
    ElMessage.warning('无公式可保存')
    return
  }
  applying.value = true
  let saved = 0
  try {
    for (const row of rows) {
      if (row._isNew && row.formula) {
        // 新增
        const reportType = selectedNodeKey.value.replace('report_', '')
        await http.post('/api/report-config', {
          report_type: reportType,
          applicable_standard: `${fmTemplateType.value}_standalone`,
          row_number: row.row_number || 0,
          row_code: row.row_code,
          row_name: row.row_name,
          formula: row.formula,
          formula_category: row.formula_category,
          formula_description: row.formula_description,
        }, { validateStatus: (s: number) => s < 600 })
        row._isNew = false
        saved++
      } else if (row.id) {
        // 更新
        await http.put(`/api/report-config/${row.id}`, {
          formula: row.formula,
          formula_category: row.formula_category,
          formula_description: row.formula_description,
        })
        saved++
      }
    }
    ElMessage.success(`已保存 ${saved} 个公式`)
    emit('saved')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    applying.value = false
  }
}

// ── 公式看板 ──
const showFormulaDashboard = ref(false)
const dashboardSearch = ref('')
const dashboardGroupBy = ref('report_type')
const dashboardFilterCategory = ref('')

const REPORT_TYPE_LABELS: Record<string, string> = {
  balance_sheet: '资产负债表', income_statement: '利润表',
  cash_flow_statement: '现金流量表', equity_statement: '权益变动表',
  cash_flow_supplement: '现金流附表', impairment_provision: '资产减值准备表',
}

// 收集所有已加载报表的公式行
const allFormulaRows = computed(() => {
  const result: any[] = []
  for (const [key, rows] of Object.entries(allRowsMap.value)) {
    if (key.includes('_')) continue // 跳过缓存 key（如 soe_balance_sheet）
    const rtLabel = REPORT_TYPE_LABELS[key] || key
    for (const r of (rows as any[])) {
      if (r.formula) {
        result.push({ ...r, _report_type: key, _report_type_label: rtLabel, _source_type: '报表' })
      }
    }
  }
  return result
})

const dashboardFilteredRows = computed(() => {
  let rows = allFormulaRows.value
  if (dashboardFilterCategory.value) {
    rows = rows.filter(r => r.formula_category === dashboardFilterCategory.value)
  }
  const kw = dashboardSearch.value.toLowerCase()
  if (kw) {
    rows = rows.filter(r =>
      (r.row_code || '').toLowerCase().includes(kw) ||
      (r.row_name || '').toLowerCase().includes(kw) ||
      (r.formula || '').toLowerCase().includes(kw) ||
      (r.formula_description || '').toLowerCase().includes(kw)
    )
  }
  return rows
})

const dashboardGroupedData = computed(() => {
  const rows = dashboardFilteredRows.value
  const groups: Record<string, { key: string; label: string; rows: any[]; _open: boolean }> = {}

  for (const r of rows) {
    let gKey = '', gLabel = ''
    if (dashboardGroupBy.value === 'report_type') {
      gKey = r._report_type || 'unknown'
      gLabel = r._report_type_label || gKey
    } else if (dashboardGroupBy.value === 'category') {
      gKey = r.formula_category || 'none'
      gLabel = categoryLabel(r.formula_category)
    } else if (dashboardGroupBy.value === 'source') {
      // 按公式中引用的数据源分组
      const formula = r.formula || ''
      if (formula.includes('TB(') || formula.includes('SUM_TB(')) gKey = 'tb'
      else if (formula.includes('NOTE(')) gKey = 'note'
      else if (formula.includes('WP(')) gKey = 'wp'
      else if (formula.includes('ROW(') || formula.includes('SUM_ROW(')) gKey = 'row'
      else gKey = 'other'
      const sourceLabels: Record<string, string> = { tb: '📈 试算表', note: '📝 附注', wp: '📋 底稿', row: '📊 报表行次', other: '其他' }
      gLabel = sourceLabels[gKey] || gKey
    }
    if (!groups[gKey]) groups[gKey] = { key: gKey, label: gLabel, rows: [], _open: true }
    groups[gKey].rows.push(r)
  }
  return Object.values(groups)
})

function onDashboardEdit(row: any) {
  editingRow.value = row
  showFormulaEdit.value = true
}

// 看板打开时自动加载所有报表的公式
watch(showFormulaDashboard, async (v) => {
  if (!v) return
  const standard = `${fmTemplateType.value}_standalone`
  const types = ['balance_sheet', 'income_statement', 'cash_flow_statement', 'equity_statement', 'cash_flow_supplement', 'impairment_provision']
  for (const rt of types) {
    if (allRowsMap.value[rt]?.length) continue
    try {
      const { data } = await http.get('/api/report-config', {
        params: { report_type: rt, applicable_standard: standard },
        validateStatus: (s: number) => s < 600,
      })
      allRowsMap.value[rt] = data?.data ?? data ?? []
    } catch { /* skip */ }
  }
})
</script>

<style scoped>
.gt-fm-container {
  display: flex;
  gap: 12px;
  height: calc(100vh - 180px);
  min-height: 500px;
}
.gt-fm-sidebar {
  width: 220px;
  flex-shrink: 0;
  border: 1px solid #e8e4f0;
  border-radius: 8px;
  overflow-y: auto;
  background: #faf8fd;
}
.gt-fm-sidebar-title {
  padding: 10px 14px 6px;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 1px;
}
.gt-fm-tree {
  background: transparent;
  --el-tree-node-hover-bg-color: #f0ecf5;
}
.gt-fm-tree :deep(.el-tree-node__content) {
  height: 30px;
  font-size: 12px;
}
.gt-fm-tree :deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: #ece6f5;
  font-weight: 600;
}
.gt-fm-tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
}
.gt-fm-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.gt-fm-breadcrumb {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.gt-fm-footer {
  margin-top: 8px;
  text-align: right;
}
.gt-fm-batch-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: linear-gradient(135deg, #f5f0ff 0%, #ece6f5 100%);
  border: 1px solid #d8cfe8;
  border-radius: 6px;
  margin-bottom: 6px;
}
/* 行样式 */
:deep(.gt-fm-row-auto) { background: #fafff8 !important; }
:deep(.gt-fm-row-logic) { background: #fffdf5 !important; }
:deep(.gt-fm-row-reason) { background: #f8fbff !important; }
:deep(.gt-fm-row-empty) { opacity: 0.7; }
:deep(.el-table__row:hover .gt-fm-row-auto),
:deep(.el-table__row:hover .gt-fm-row-logic),
:deep(.el-table__row:hover .gt-fm-row-reason) {
  background: #f0ecf5 !important;
}
.gt-fm-dash-group-title {
  font-size: 13px;
  font-weight: 600;
  color: #444;
  padding: 8px 10px;
  background: #faf8fd;
  border: 1px solid #e8e4f0;
  border-radius: 6px;
  margin-bottom: 4px;
  cursor: pointer;
  user-select: none;
  transition: background 0.12s;
}
.gt-fm-dash-group-title:hover {
  background: #f0ecf5;
}
</style>
