/**
 * useFormSubmit — 统一表单提交校验拦截 composable（V3 Req 3.2）
 *
 * 解决问题：业务视图各自手写 `formRef.value?.validate(...)` + 异常处理，
 * 模板易漏掉校验或重复 catch 模板。本 composable 提供：
 *   1. await formRef.validate() 失败时直接 short-circuit（不抛异常给调用方）
 *   2. submitting 响应式 ref 屏蔽重复点击
 *   3. validate 通过后再调用业务 action（async）
 *
 * 用法：
 *   const formRef = ref<FormInstance>()
 *   const { submit, submitting } = useFormSubmit(formRef)
 *
 *   async function onSave() {
 *     await submit(async () => {
 *       await api.post('/api/...', { ... })
 *     })
 *   }
 *
 *   <el-button :loading="submitting" @click="onSave">保存</el-button>
 */
import { ref, type Ref } from 'vue'
import type { FormInstance } from 'element-plus'

export interface UseFormSubmitReturn {
  /** 是否正在提交（响应式，可绑定 :loading/:disabled） */
  submitting: Ref<boolean>
  /**
   * 校验通过后执行 action。
   * 校验失败 → short-circuit 返回 false，不抛异常。
   * action 抛异常 → submitting 重置后向上抛出（供调用方 handleApiError）。
   */
  submit: (action: () => Promise<unknown>) => Promise<boolean>
}

export function useFormSubmit(
  formRef: Ref<FormInstance | undefined | null>,
): UseFormSubmitReturn {
  const submitting = ref(false)

  async function submit(action: () => Promise<unknown>): Promise<boolean> {
    if (submitting.value) return false // 防止重复点击

    // el-form.validate 失败时返回 rejected promise（含字段错误）；
    // 我们用 .catch 转 false 实现 short-circuit。
    const valid = await formRef.value
      ?.validate()
      .then(() => true)
      .catch(() => false)

    if (!valid) return false

    submitting.value = true
    try {
      await action()
      return true
    } finally {
      submitting.value = false
    }
  }

  return { submitting, submit }
}
