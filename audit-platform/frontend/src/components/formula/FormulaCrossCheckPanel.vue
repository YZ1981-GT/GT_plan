<!--
  表间审核规则面板（从 FormulaManagerDialog 拆出；优化建议 #1 面板拆分 Phase 2）。
  展示表间审核规则列表 + 执行结果 + 规则编辑弹窗 + 历史记录。
-->
<template>
  <div style="flex: 1;">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
      <span style="font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-text-primary);">{{ selectedPath }}</span>
      <div style="display: flex; gap: 6px;">
        <!-- spec formula-governance-coverage-closure R3：平台各处校对规则的只读目录 -->
        <el-button size="small" data-testid="cc-open-catalog" @click="catalogVisible = true">全平台校对规则目录</el-button>
        <el-button size="small" @click="onRun" :loading="running">▶ 执行校验</el-button>
        <el-button size="small" type="primary" @click="onAdd">+ 新增规则</el-button>
      </div>
    </div>
    <!-- spec formula-governance-coverage-closure R4：内置报表勾稽的问题清单 / 提醒（与树上 ✅/❌ 同一次执行） -->
    <div v-if="issueRun" data-testid="cc-issue-run" style="margin-bottom: 10px;">
      <el-alert v-if="issueRun.failed" type="warning" :closable="false" show-icon title="内置报表勾稽执行失败">
        <span>{{ issueRun.error }}</span>
        <el-button size="small" link type="primary" :loading="execLoading" data-testid="cc-issue-retry"
          style="margin-left: 8px;" @click="$emit('refresh-exec')">重试</el-button>
      </el-alert>
      <GtFormulaIssuePanel v-else-if="issueRun.executed" :issues="issueRun.issues" :outcomes="issueRun.outcomes"
        :last-computed-at="issueRun.lastComputedAt" :loading="execLoading" @refresh="$emit('refresh-exec')" />
      <el-alert v-else-if="!execLoading" type="info" :closable="false" show-icon title="内置报表勾稽无结果">
        <span>本项目当前年度还没有已生成的报表数据，内置勾稽没有可执行的结论。</span>
        <el-button size="small" link type="primary" data-testid="cc-issue-rerun" style="margin-left: 8px;"
          @click="$emit('refresh-exec')">重新执行</el-button>
      </el-alert>
      <el-alert v-if="issueRun.hints.length" type="info" :closable="false" show-icon title="提醒"
        data-testid="cc-issue-hints" style="margin-top: 8px;">
        <div v-for="(h, i) in issueRun.hints" :key="i">{{ h }}</div>
      </el-alert>
    </div>
    <el-alert
      v-if="execEmpty && !rules.length && !issueRun"
      type="info" :closable="false" show-icon title="无结果"
      description="本项目当前年度表间审核执行结果为空，且该节点尚无自定义规则。可点「+ 新增规则」添加后执行校验。"
      style="margin-bottom: 10px;" />
    <el-table :data="rules" size="small" border style="width: 100%;" max-height="calc(100vh - 300px)"
      :header-cell-style="{ background: '#edf3f9', fontSize: '12px', whiteSpace: 'nowrap' }">
      <el-table-column type="index" label="#" width="50" />
      <el-table-column label="来源" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.layer" size="small" effect="plain" :type="layerTagType(row.layer)">{{ layerLabel(row.layer) || row.layer }}</el-tag>
          <el-tag v-if="row.pending" size="small" type="danger" effect="plain">待确认</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="规则名称" min-width="200">
        <template #default="{ row }">
          <span style="font-size: var(--gt-font-size-xs);">{{ row.label }}</span>
        </template>
      </el-table-column>
      <el-table-column label="左侧（源）" min-width="180">
        <template #default="{ row }">
          <code style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary);">{{ row.left_ref || '—' }}</code>
          <div v-if="row._leftVal != null" style="font-size: 10px; color: var(--gt-color-text-tertiary);">= {{ row._leftVal }}</div>
        </template>
      </el-table-column>
      <el-table-column label="关系" width="60" align="center">
        <template #default="{ row }">
          <span v-if="row._checked && row._pass" style="font-size: var(--gt-font-size-sm); color: var(--gt-color-success);">✅</span>
          <span v-else-if="row._checked && !row._pass" style="font-size: var(--gt-font-size-sm); color: var(--gt-color-danger);">❌</span>
          <span v-else style="font-size: var(--gt-font-size-sm);">=</span>
        </template>
      </el-table-column>
      <el-table-column label="右侧（目标）" min-width="180">
        <template #default="{ row }">
          <code style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary);">{{ row.right_ref || '—' }}</code>
          <div v-if="row._rightVal != null" style="font-size: 10px; color: var(--gt-color-text-tertiary);">= {{ row._rightVal }}</div>
        </template>
      </el-table-column>
      <el-table-column label="差额" width="100" align="right">
        <template #default="{ row }">
          <span v-if="row._checked" :style="{ fontSize: '11px', fontWeight: 600, color: row._pass ? 'var(--gt-color-success)' : 'var(--gt-color-danger)' }">
            {{ row._diff != null ? row._diff.toFixed(2) : '—' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center">
        <template #default="{ row, $index }">
          <div style="display: flex; gap: 4px; justify-content: center;">
            <el-button size="small" link type="primary" @click="onEdit(row, $index)">编辑</el-button>
            <el-button size="small" link style="color: var(--gt-color-text-tertiary);" @click="onRemove($index)">删除</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
    <div style="margin-top: 8px; text-align: right; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">
      {{ rules.length }} 条规则
    </div>

    <CrossCheckHistoryPanel ref="historyRef" :project-id="projectId" :year="year" />

    <!-- 规则编辑弹窗 -->
    <el-dialog :model-value="showDialog" @update:model-value="$emit('update:showDialog', $event)"
      :title="dialogTitle" width="640px" append-to-body destroy-on-close>
      <el-form :model="form" label-width="100px" label-position="top" style="padding: 0 10px;">
        <el-form-item label="规则名称" required>
          <el-input v-model="form.label" placeholder="如：BS货币资金 = 附注货币资金合计" />
        </el-form-item>
        <el-form-item label="左侧（源）" required>
          <el-input v-model="form.left_ref" placeholder="报表行次引用，如 REPORT('BS-002','期末')">
            <template #prepend>源</template>
          </el-input>
          <div style="font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 4px;">
            语法：REPORT('行次','字段') 或 ROW('行次') 或 PREV('科目','字段')。示例：REPORT('BS-002','期末')
          </div>
          <!-- spec: formula-management-deep-optimization P2-9 — 快捷按钮 -->
          <div style="display: flex; gap: 4px; margin-top: 4px; flex-wrap: wrap;">
            <el-button size="small" @click="form.left_ref += &quot;ROW('')&quot;">ROW</el-button>
            <el-button size="small" @click="form.left_ref += &quot;REPORT('','')&quot;">REPORT</el-button>
            <el-button size="small" @click="form.left_ref += &quot;TB('','')&quot;">TB</el-button>
            <el-button size="small" @click="form.left_ref += &quot;PREV('','期末余额')&quot;">PREV</el-button>
            <el-button size="small" @click="form.left_ref += &quot;SUM_TB('','')&quot;">SUM_TB</el-button>
          </div>
        </el-form-item>
        <el-form-item label="关系运算符">
          <el-select v-model="form.operator" style="width: 120px;">
            <el-option label="=" value="=" />
            <el-option label="≤" value="<=" />
            <el-option label="≥" value=">=" />
          </el-select>
        </el-form-item>
        <el-form-item label="右侧（目标）" required>
          <el-input v-model="form.right_ref" placeholder="附注/底稿引用，如 NOTE('五、1','合计','期末') 或 WP('E1','E1-1','审定数')">
            <template #prepend>目标</template>
          </el-input>
          <div style="font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 4px;">
            语法：NOTE('章节编号','行','列') / WP('底稿','sheet','坐标') / TB('科目','字段') / AUX('科目','维度','字段') / PREV('科目','字段')。
            NOTE 第一参是附注章节编号（如「五、1」），写标题取不到数
          </div>
          <!-- spec: formula-management-deep-optimization P2-9 — 快捷按钮 -->
          <div style="display: flex; gap: 4px; margin-top: 4px; flex-wrap: wrap;">
            <el-button size="small" @click="form.right_ref += &quot;NOTE('','合计')&quot;">NOTE</el-button>
            <el-button size="small" @click="form.right_ref += &quot;WP('','','')&quot;">WP</el-button>
            <el-button size="small" @click="form.right_ref += &quot;TB('','')&quot;">TB</el-button>
            <el-button size="small" @click="form.right_ref += &quot;AUX('','','期末余额')&quot;">AUX</el-button>
            <el-button size="small" @click="form.right_ref += &quot;PREV('','期末余额')&quot;">PREV</el-button>
          </div>
        </el-form-item>
        <el-form-item label="说明（选填）">
          <el-input v-model="form.description" type="textarea" :autosize="{ minRows: 2 }" placeholder="描述该规则的业务含义" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div style="display: flex; align-items: center; gap: 8px;">
          <!-- spec formula-governance-coverage-closure R3：表间审核预置（cross_check_preset_rules.json）选用后可改 -->
          <el-select v-model="presetPick" size="small" filterable clearable placeholder="从预置选用（填入后可改）"
            style="width: 260px;" :loading="presetLoading" data-testid="cc-preset"
            @visible-change="onPresetOpen" @change="applyPreset">
            <el-option v-for="p in presets" :key="p.id" :label="p.label" :value="p.id" />
          </el-select>
          <span style="flex: 1;" />
          <el-button @click="$emit('update:showDialog', false)">取消</el-button>
          <el-button type="primary" @click="onSave" :disabled="!form.label || !form.left_ref || !form.right_ref">确认保存</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="catalogVisible" title="全平台校对规则目录" width="1100px" append-to-body destroy-on-close>
      <FormulaCheckCatalog v-if="catalogVisible" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { formulaSettingsApi } from '@/services/formulaSettingsApi'
import { showFormulaError, type CheckRule } from '@/composables/formula/useFormulaSettings'
import CrossCheckHistoryPanel from './panels/CrossCheckHistoryPanel.vue'
import FormulaCheckCatalog from './settings/FormulaCheckCatalog.vue'
import GtFormulaIssuePanel from './GtFormulaIssuePanel.vue'
import type { FormulaIssueRun } from './formulaIssueHint'

defineOptions({ name: 'FormulaCrossCheckPanel' })

const props = withDefaults(defineProps<{
  selectedPath: string
  rules: any[]
  execEmpty: boolean
  running: boolean
  showDialog: boolean
  dialogTitle: string
  form: { label: string; left_ref: string; operator: string; right_ref: string; description: string }
  projectId: string
  /** 审计年度；项目没填为 null / 未传 ⇒ 审核历史不加载 */
  year?: number | null
  layerTagType: (layer: string) => string
  layerLabel: (layer: string) => string
  /** 当前节点该显示的内置勾稽产出；null = 本节点与内置勾稽无关（formulaIssueHint.issueRunForNode） */
  issueRun?: FormulaIssueRun | null
  execLoading?: boolean
}>(), { issueRun: null, execLoading: false })

const emit = defineEmits<{
  run: []
  add: []
  edit: [row: any, index: number]
  remove: [index: number]
  save: []
  'update:showDialog': [val: boolean]
  /** 重新执行内置勾稽 */
  'refresh-exec': []
}>()

const historyRef = defineModel<any>('historyRef')

function onRun() { emit('run') }
function onAdd() { emit('add') }
function onEdit(row: any, index: number) { emit('edit', row, index) }
function onRemove(index: number) { emit('remove', index) }
function onSave() { emit('save') }

// ── 全平台校对规则目录 / 从预置选用（spec formula-governance-coverage-closure R3） ──
const catalogVisible = ref(false)
const presets = ref<CheckRule[]>([])
const presetLoading = ref(false)
const presetPick = ref('')
const OPERATORS = ['=', '<=', '>=']

async function onPresetOpen(open: boolean): Promise<void> {
  if (!open || presets.value.length || presetLoading.value) return
  presetLoading.value = true
  try {
    presets.value = (await formulaSettingsApi.checkRules({ source: 'cross_check_preset' }))?.sources?.[0]?.rules || []
  } catch (e) {
    showFormulaError(e, '加载表间审核预置失败')
  } finally {
    presetLoading.value = false
  }
}

/** 预置填进编辑表单（与快捷按钮同样直接改表单对象），保存前仍可改 */
function applyPreset(id: string): void {
  const f = presets.value.find((p) => p.id === id)?.fields
  if (!f) return
  Object.assign(props.form, {
    label: String(f.label || ''), left_ref: String(f.left_ref || ''),
    operator: OPERATORS.includes(f.operator) ? f.operator : '=',
    right_ref: String(f.right_ref || ''), description: String(f.description || ''),
  })
  presetPick.value = ''
}
</script>
