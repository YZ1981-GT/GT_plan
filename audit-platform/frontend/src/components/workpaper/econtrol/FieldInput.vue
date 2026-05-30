<!--
  FieldInput.vue — 字段输入控件（原 GtEControlTest.vue 内联 defineComponent 抽出）

  根据 field.type 选择合适的输入控件。
  使用 render function (h) 形态解决 <component :is="ElSelect"> 无法注入子节点 <el-option> 的限制。
  被 single / evaluation_step 两个子模式共用。
-->

<script lang="ts">
import { defineComponent, h } from 'vue'
import { ElInput, ElInputNumber, ElSelect, ElOption } from 'element-plus'
import type { FieldDef } from '../GtEControlTest.types'

export default defineComponent({
  name: 'FieldInput',
  props: {
    field: { type: Object as () => FieldDef, required: true },
    modelValue: { type: null, default: undefined },
    readonly: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  setup(p, { emit: localEmit }) {
    return () => {
      const f = p.field
      const onUpdate = (v: any) => localEmit('update:modelValue', v)
      const common: Record<string, any> = {
        modelValue: p.modelValue,
        'onUpdate:modelValue': onUpdate,
        disabled: p.readonly,
        size: 'default',
        placeholder: f.label,
      }

      if (f.type === 'enum') {
        return h(
          ElSelect,
          { ...common, clearable: true },
          {
            default: () => (f.enum || []).map(opt =>
              h(ElOption, { key: opt, label: opt, value: opt })
            ),
          }
        )
      }

      if (f.type === 'multi_enum') {
        return h(
          ElSelect,
          {
            ...common,
            multiple: true,
            collapseTags: true,
            collapseTagsTooltip: true,
            modelValue: Array.isArray(p.modelValue) ? p.modelValue : [],
          },
          {
            default: () => (f.enum || []).map(opt =>
              h(ElOption, { key: opt, label: opt, value: opt })
            ),
          }
        )
      }

      if (f.type === 'number') {
        return h(ElInputNumber, {
          ...common,
          min: f.min ?? 0,
          max: f.max,
          controlsPosition: 'right',
        })
      }

      if (f.type === 'textarea') {
        return h(ElInput, {
          ...common,
          type: 'textarea',
          rows: 3,
          maxlength: f.max_length,
          showWordLimit: !!f.max_length,
        })
      }

      if (f.type === 'attachment_list') {
        return h(ElInput, {
          ...common,
          type: 'textarea',
          rows: 2,
          placeholder: '附件列表（暂以文本占位）',
        })
      }

      // text 默认
      return h(ElInput, {
        ...common,
        type: 'text',
        clearable: true,
        maxlength: f.max_length,
        showWordLimit: !!f.max_length,
      })
    }
  },
})
</script>
