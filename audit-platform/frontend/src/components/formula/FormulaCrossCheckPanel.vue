<!--
  表间审核规则面板（从 FormulaManagerDialog 拆出；优化建议 #1 面板拆分 Phase 2）。
  展示表间审核规则列表 + 执行结果 + 规则编辑弹窗 + 历史记录。
-->
<template>
  <div style="flex: 1;">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
      <span style="font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-text-primary);">{{ selectedPath }}</span>
      <div style="display: flex; gap: 6px;">
        <el-button size="small" @click="onRun" :loading="running">▶ 执行校验</el-button>
        <el-button size="small" type="primary" @click="onAdd">+ 新增规则</el-button>
      </div>
    </div>
    <el-alert
      v-if="execEmpty && !rules.length"
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
            语法：REPORT('行次','字段') 或 ROW('行次')。示例：REPORT('BS-002','期末')
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
          <el-input v-model="form.right_ref" placeholder="附注/底稿引用，如 NOTE('货币资金','合计') 或 WP('E1','E1-1','审定数')">
            <template #prepend>目标</template>
          </el-input>
          <div style="font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 4px;">
            语法：NOTE('章节','字段') / WP('底稿','sheet','坐标') / TB('科目','字段')
          </div>
        </el-form-item>
        <el-form-item label="说明（选填）">
          <el-input v-model="form.description" type="textarea" :autosize="{ minRows: 2 }" placeholder="描述该规则的业务含义" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="$emit('update:showDialog', false)">取消</el-button>
        <el-button type="primary" @click="onSave" :disabled="!form.label || !form.left_ref || !form.right_ref">确认保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import CrossCheckHistoryPanel from './panels/CrossCheckHistoryPanel.vue'

defineOptions({ name: 'FormulaCrossCheckPanel' })

defineProps<{
  selectedPath: string
  rules: any[]
  execEmpty: boolean
  running: boolean
  showDialog: boolean
  dialogTitle: string
  form: { label: string; left_ref: string; operator: string; right_ref: string; description: string }
  projectId: string
  year: number
  layerTagType: (layer: string) => string
  layerLabel: (layer: string) => string
}>()

const emit = defineEmits<{
  run: []
  add: []
  edit: [row: any, index: number]
  remove: [index: number]
  save: []
  'update:showDialog': [val: boolean]
}>()

const historyRef = defineModel<any>('historyRef')

function onRun() { emit('run') }
function onAdd() { emit('add') }
function onEdit(row: any, index: number) { emit('edit', row, index) }
function onRemove(index: number) { emit('remove', index) }
function onSave() { emit('save') }
</script>
