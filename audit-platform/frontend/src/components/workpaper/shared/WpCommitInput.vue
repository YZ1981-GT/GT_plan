<script setup lang="ts">
/**
 * WpCommitInput — 失焦 / 回车才提交的文本框（替代「el-input 只绑 :model-value + @change」）
 *
 * **为什么需要**：Element Plus 的 el-input 每次输入后都把原生值重置回 modelValue
 * （源码注释 ensure native input value is controlled）。父组件只听 `@change`、不回写
 * modelValue 时，打的每个字立即消失，失焦时 `@change` 拿到的也是旧值 ⇒ 这种写法的框
 * 根本输不进内容（2026-10-27 D2-7 矩阵视图浏览器实测 + 单测实证）。
 *
 * 行为：
 * - 输入中在组件内保管草稿并显示草稿；`change`（失焦 / 回车）时把草稿交给父组件
 * - 不在输入中时跟随父组件的值；父组件拒收（值没变）时，提交后回到父组件的值
 * - 其余属性 / 事件 / 插槽原样透传给 el-input（type="textarea"、size、disabled 等照旧）
 */
import { computed, nextTick, ref } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps<{ modelValue?: string | number | null }>()
const emit = defineEmits<{ (e: 'change', value: string): void }>()

const editing = ref(false)
const draft = ref('')
const outer = computed(() => (props.modelValue == null ? '' : String(props.modelValue)))
const shown = computed(() => (editing.value ? draft.value : outer.value))

function onInput(value: string): void {
  editing.value = true
  draft.value = value
}

/** 提交后等父组件处理完再回到父组件的值（拒收即还原，接收则两者相同） */
async function settle(): Promise<void> {
  await nextTick()
  editing.value = false
}

function onChange(value: string): void {
  emit('change', value)
  void settle()
}

/** 打了又删回原值时原生 change 不触发：失焦时草稿与父组件的值相同就直接回到跟随 */
function onBlur(): void {
  if (draft.value === outer.value) editing.value = false
}
</script>

<template>
  <el-input v-bind="$attrs" :model-value="shown" @update:model-value="onInput" @change="onChange" @blur="onBlur">
    <template v-for="(_, name) in $slots" #[name]="slotProps">
      <slot :name="name" v-bind="slotProps || {}" />
    </template>
  </el-input>
</template>
