/**
 * stubs.ts — GtDForm 子组件测试共享 Element Plus stub 集合
 *
 * 复盘改进 #1/#2（2026-05-30）：消除各 spec 文件重复定义 + 补齐缺失 stub
 * （el-select/el-option/el-input-number 之前缺失导致 Vue warn）。
 *
 * 用法：
 *   import { elementPlusStubs } from './stubs'
 *   mount(Comp, { global: { stubs: elementPlusStubs } })
 *
 * 设计原则：
 * - 超集：覆盖 Review / Confirmation / Paragraph 三组件模板全部 el-* 组件
 * - 行为最小但完整：input 系列正确 emit update:modelValue + change，
 *   供 v-model 与 @change 测试钩子工作
 * - el-empty 的 description 用独立标签渲染（不放 slot 内，避免 slot 覆盖）
 */

// ─── 表单容器 ────────────────────────────────────────────────────────────────

const formStubs = {
  'el-form': {
    template: '<form class="el-form"><slot /></form>',
    props: ['model', 'labelPosition', 'disabled'],
  },
  'el-form-item': {
    template: '<div class="el-form-item" :data-label="label"><slot /></div>',
    props: ['label', 'required'],
  },
}

// ─── 输入控件 ────────────────────────────────────────────────────────────────

const inputStubs = {
  'el-input': {
    template:
      '<textarea v-if="type === \'textarea\'" class="el-input" :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" @change="$emit(\'change\', $event.target.value)" @blur="$emit(\'blur\')"></textarea>' +
      '<input v-else class="el-input" :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" @change="$emit(\'change\', $event.target.value)" @blur="$emit(\'blur\')" />',
    props: ['modelValue', 'type', 'rows', 'placeholder', 'maxlength', 'showWordLimit', 'disabled', 'size', 'readonly'],
    emits: ['update:modelValue', 'change', 'blur'],
  },
  'el-input-number': {
    template:
      '<input class="el-input-number" type="number" :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', Number($event.target.value))" @change="$emit(\'change\', Number($event.target.value))" />',
    props: ['modelValue', 'disabled', 'min', 'max', 'precision', 'controlsPosition', 'size'],
    emits: ['update:modelValue', 'change'],
  },
  'el-select': {
    template:
      '<select class="el-select" :disabled="disabled" @change="$emit(\'update:modelValue\', $event.target.value); $emit(\'change\', $event.target.value)"><slot /></select>',
    props: ['modelValue', 'disabled', 'clearable', 'placeholder', 'size'],
    emits: ['update:modelValue', 'change'],
  },
  'el-option': {
    template: '<option class="el-option" :value="value">{{ label }}</option>',
    props: ['label', 'value'],
  },
  'el-date-picker': {
    template:
      '<input class="el-date-picker" :value="modelValue" :disabled="disabled" @change="$emit(\'update:modelValue\', $event.target.value); $emit(\'change\', $event.target.value)" />',
    props: ['modelValue', 'disabled', 'type', 'format', 'valueFormat', 'placeholder', 'size'],
    emits: ['update:modelValue', 'change'],
  },
  'el-radio-group': {
    template: '<div class="el-radio-group" :class="{ \'is-disabled\': disabled }"><slot /></div>',
    props: ['modelValue', 'disabled', 'size'],
    emits: ['update:modelValue', 'change'],
  },
  'el-radio': {
    template: '<label class="el-radio" :data-value="value"><slot /></label>',
    props: ['value'],
  },
  'el-checkbox': {
    template:
      '<label class="el-checkbox" @click="$emit(\'update:modelValue\', !modelValue); $emit(\'change\', !modelValue)"><slot /></label>',
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue', 'change'],
  },
}

// ─── 展示容器 ────────────────────────────────────────────────────────────────

const displayStubs = {
  'el-icon': { template: '<i class="el-icon"><slot /></i>' },
  'el-tooltip': {
    template: '<div class="el-tooltip"><slot /><slot name="content" /></div>',
    props: ['content', 'placement', 'showAfter', 'popperClass'],
  },
  'el-button': {
    template:
      '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'icon', 'link', 'text', 'loading'],
    emits: ['click'],
  },
  'el-tag': {
    template: '<span class="el-tag" :data-type="type" :data-effect="effect"><slot /></span>',
    props: ['type', 'size', 'effect'],
  },
  'el-link': {
    template: '<a class="el-link" @click="$emit(\'click\')"><slot /></a>',
    props: ['type', 'underline'],
    emits: ['click'],
  },
  'el-empty': {
    template: '<div class="el-empty"><div class="el-empty__description">{{ description }}</div></div>',
    props: ['imageSize', 'description'],
  },
  'el-collapse': {
    template: '<div class="el-collapse"><slot /></div>',
    props: ['modelValue'],
    emits: ['update:modelValue'],
  },
  'el-collapse-item': {
    template: '<div class="el-collapse-item" :data-name="name" :data-title="title"><slot /></div>',
    props: ['name', 'title'],
  },
  'el-steps': {
    template: '<div class="el-steps"><slot /></div>',
    props: ['active', 'processStatus', 'finishStatus', 'alignCenter', 'simple'],
  },
  'el-step': {
    template: '<div class="el-step" :data-title="title" @click="$emit(\'click\')"><slot /></div>',
    props: ['title', 'description', 'status', 'icon'],
    emits: ['click'],
  },
  'el-timeline': {
    template: '<div class="el-timeline"><slot /></div>',
  },
  'el-timeline-item': {
    template: '<div class="el-timeline-item"><slot /></div>',
    props: ['timestamp', 'type', 'placement'],
  },
  'el-table': {
    template: '<table class="el-table"><slot /></table>',
    props: ['data', 'border', 'size', 'emptyText'],
  },
  'el-table-column': {
    template: '<col class="el-table-column" />',
    props: ['label', 'minWidth', 'width', 'resizable', 'fixed'],
  },
}

// ─── 图标 ────────────────────────────────────────────────────────────────────

const iconStubs = {
  InfoFilled: { template: '<span class="info-filled" />' },
  EditPen: { template: '<span class="edit-pen" />' },
  RefreshLeft: { template: '<span class="refresh-left" />' },
  User: { template: '<span class="user-icon" />' },
  Clock: { template: '<span class="clock-icon" />' },
  Right: { template: '<span class="right-icon" />' },
  CircleCheck: { template: '<span class="circle-check" />' },
  CircleCheckFilled: { template: '<span class="circle-check-filled" />' },
  WarningFilled: { template: '<span class="warning-filled" />' },
  CircleCloseFilled: { template: '<span class="circle-close-filled" />' },
  Document: { template: '<span class="document-icon" />' },
}

// ─── 导出超集 ────────────────────────────────────────────────────────────────

export const elementPlusStubs: Record<string, any> = {
  ...formStubs,
  ...inputStubs,
  ...displayStubs,
  ...iconStubs,
}
