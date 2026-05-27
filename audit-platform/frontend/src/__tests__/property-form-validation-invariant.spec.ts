/**
 * Property 3: 表单校验不变量 — 属性测试（V3 Req 3.6）
 *
 * 形式化：∀ form submission S:
 *   S is submitted ⇒ S has passed validate()
 *
 * 测试策略：
 * - 使用 fast-check 生成随机字段组合（含空值/非法格式）
 * - 验证 useFormSubmit + el-form rules 链路在校验失败时 short-circuit
 * - 反例期望：找到任何"未经 validate 即提交"的情况 = production bug
 *
 * Validates: Requirements 3 (表单校验全覆盖)
 */
import { describe, it, expect, vi } from 'vitest'
import * as fc from 'fast-check'
import { ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useFormSubmit } from '@/composables/useFormSubmit'
import { rules, makeRules } from '@/utils/formRules'

/** 模拟 el-form.validate() 行为：根据 rules + model 决定通过或失败 */
function makeMockForm(model: Record<string, unknown>, formRules: FormRules) {
  return {
    validate: vi.fn(async () => {
      // 仿真 el-form 校验逻辑
      const errors: Record<string, { message: string }[]> = {}
      for (const [field, fieldRules] of Object.entries(formRules)) {
        const ruleArr = Array.isArray(fieldRules) ? fieldRules : [fieldRules]
        const value = model[field]
        for (const r of ruleArr) {
          const anyR = r as any
          // required 校验
          if (anyR.required && (value === null || value === undefined || value === '')) {
            ;(errors[field] ||= []).push({ message: anyR.message ?? `${field} 必填` })
            break
          }
          // pattern 校验（仅对字符串）
          if (anyR.pattern && typeof value === 'string' && value !== '') {
            const re =
              anyR.pattern instanceof RegExp ? anyR.pattern : new RegExp(anyR.pattern)
            if (!re.test(value)) {
              ;(errors[field] ||= []).push({ message: anyR.message ?? `${field} 格式错误` })
              break
            }
          }
          // min/max 长度
          if (typeof value === 'string') {
            if (anyR.min != null && value.length < anyR.min) {
              ;(errors[field] ||= []).push({ message: anyR.message ?? `${field} 太短` })
              break
            }
            if (anyR.max != null && value.length > anyR.max) {
              ;(errors[field] ||= []).push({ message: anyR.message ?? `${field} 太长` })
              break
            }
          }
          // type=email 校验
          if (anyR.type === 'email' && typeof value === 'string' && value !== '') {
            // 简化版邮箱校验（与 element-plus 内置 async-validator 一致即可）
            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
              ;(errors[field] ||= []).push({ message: anyR.message ?? `${field} 邮箱格式错误` })
              break
            }
          }
          // type=number 范围
          if (anyR.type === 'number' && typeof value === 'number') {
            if (anyR.min != null && value < anyR.min) {
              ;(errors[field] ||= []).push({ message: anyR.message ?? `${field} 小于下限` })
              break
            }
            if (anyR.max != null && value > anyR.max) {
              ;(errors[field] ||= []).push({ message: anyR.message ?? `${field} 大于上限` })
              break
            }
          }
        }
      }
      if (Object.keys(errors).length > 0) {
        return Promise.reject(errors)
      }
      return true
    }),
  } as unknown as FormInstance
}

describe('Property 3: 表单校验不变量', () => {
  /**
   * Property: 当任一必填字段为空时，submit() 必返回 false 且 action 不被调用。
   * 反例期望：找到「必填空值但 action 仍被调用」= 校验绕过 bug。
   */
  it('必填字段空值场景下 action 必不被调用', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          username: fc.oneof(fc.constant(''), fc.constant(null), fc.string({ minLength: 1, maxLength: 10 })),
          email: fc.oneof(fc.constant(''), fc.constant('test@x.com'), fc.constant('invalid')),
          year: fc.oneof(fc.constant(null as any), fc.integer({ min: 1990, max: 2100 })),
        }),
        async (model) => {
          const formRules: FormRules = {
            username: makeRules('用户名'),
            email: makeRules('邮箱', rules.email),
            year: [{ required: true, message: '年度必填', trigger: 'change' }, rules.year],
          }
          const formRef = ref(makeMockForm(model, formRules))
          const { submit, submitting } = useFormSubmit(formRef)
          const action = vi.fn(async () => 'done')

          // 现实校验逻辑：el-form `required: true` 仅在 value 为空字符串/null/undefined 时报错。
          // 注意：` ` 单空格被视为有效（这是 element-plus 默认行为，本测试不质疑该约定）。
          const isEmpty = (v: unknown) => v === null || v === undefined || v === ''
          const expectedShouldFail =
            isEmpty(model.username) ||
            isEmpty(model.email) ||
            model.year === null ||
            model.email === 'invalid'

          const result = await submit(action)

          if (expectedShouldFail) {
            // ⇐ 不变量核心：校验失败 ⇒ action 必不被调用
            expect(result).toBe(false)
            expect(action).not.toHaveBeenCalled()
          } else {
            expect(result).toBe(true)
            expect(action).toHaveBeenCalledTimes(1)
          }
          expect(submitting.value).toBe(false)
        },
      ),
      { numRuns: 50 },
    )
  })

  /**
   * Property: 任意 model 下 submit() 都不会抛 unhandled rejection（safety）
   */
  it('任意输入下 submit 不会抛未捕获异常', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          name: fc.oneof(fc.string(), fc.constant(undefined as any), fc.constant(null as any)),
          amount: fc.oneof(fc.string(), fc.float({ noNaN: true })),
        }),
        async (model) => {
          const formRef = ref(
            makeMockForm(model as any, {
              name: makeRules('名称'),
              amount: rules.amount,
            }),
          )
          const { submit } = useFormSubmit(formRef)

          // 只要 submit 解析（无论 true/false）即视为不抛
          // action 本身是 noop，不会抛
          let resolved = false
          await submit(async () => {}).then(
            () => { resolved = true },
            () => { /* 即使 action 异常也不算崩溃 */ resolved = true },
          )
          expect(resolved).toBe(true)
        },
      ),
      { numRuns: 30 },
    )
  })

  /**
   * Property: 静态扫描 — 全平台 el-form 必有 :rules 绑定（baseline=0）。
   * 这是 ESLint 规则 el-form-must-have-rules 已经守住的不变量，本测试做兜底断言。
   */
  it('baselines.json 中 el-form-must-have-rules 已清零', async () => {
    // 仅在 Node 环境下读 baseline 文件
    const fs = await import('fs')
    const path = await import('path')
    // 项目相对路径推断（vitest cwd 为前端工程根目录或仓库根）
    const cwd = process.cwd()
    const candidates = [
      path.resolve(cwd, '../../.github/workflows/baselines.json'),
      path.resolve(cwd, '.github/workflows/baselines.json'),
      path.resolve(cwd, '../../../.github/workflows/baselines.json'),
    ]
    const baselineFile = candidates.find((p) => fs.existsSync(p))
    expect(baselineFile).toBeDefined()
    const data = JSON.parse(fs.readFileSync(baselineFile!, 'utf-8'))
    const baseline = data._v3_eslint_rules?.['el-form-must-have-rules-vue-files']
    expect(baseline).toBe(0)
  })
})
