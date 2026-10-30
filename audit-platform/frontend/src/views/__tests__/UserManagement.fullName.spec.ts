/**
 * UserManagement 全名展示与必填守卫
 *
 * 被守卫的行为：
 *  1. 「所属合伙人」下拉的 option label 用**全名**，全名缺失才回落登录名。
 *     —— 审计师认人名不认登录名，直接给 username 会把「邢子浩合伙人」显示成
 *     「xingzihao1」这类需要二次翻译的文案。
 *  2. 未命中候选集的兜底 option 仍是人类可读文案（不泄漏裸 UUID），
 *     且在「优先全名」口径下也成立（兜底项必须同时带 full_name）。
 *  3. 全名字段挂了 required 规则，且 DOM 上渲染出必填标记。
 *
 *  4. **全名为空时提交被拦住**：`saveUser()` 不会调到 `createUser`/`updateUser`。
 *
 * ℹ️ 2026-08-31 起本文件**可以**断言「必填真的拦住提交」。
 *    此前不行 —— vitest 下 el-form 的 `:rules` 校验恒通过，写那种判据必假绿
 *    （根因：element-plus 被外部化后走 Node 原生 ESM，而 async-validator 是纯 CJS
 *    包，`import AsyncValidator` 拿到 `{ default: Schema }` 对象，`new` 抛
 *    TypeError，异常被 FormItem/Form 的 catch 层层降级成 `{}` ⇒ 报告"通过"）。
 *    已由 spec `vitest-elform-validation-fidelity` 修复：`vitest.config.ts` 加
 *    `test.server.deps.inline: ['element-plus']`，让 Vite 转译 EP，与生产 build
 *    同一套 CJS→ESM 互操作逻辑。
 *    环境守卫：`src/__tests__/elFormValidationFidelity.spec.ts`（该配置被删则打红）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import UserManagement from '../UserManagement.vue'

let usersPayload: any[] = []

vi.mock('@/services/commonApi', () => ({
  listUsers: vi.fn(async () => usersPayload),
  createUser: vi.fn(async () => ({})),
  updateUser: vi.fn(async () => ({})),
  listDepartments: vi.fn(async () => []),
}))

/** 有全名的合伙人 —— 下拉里必须显示「张合伙人」而不是「partner_zhang」。 */
const PARTNER_NAMED = {
  id: 'p-1', username: 'partner_zhang', full_name: '张合伙人',
  email: 'z@example.com', role: 'partner', is_active: true,
}
/** 无全名的历史账号（V149 之前建的）—— 只能回落登录名。 */
const PARTNER_LEGACY = {
  id: 'p-2', username: 'partner_legacy', full_name: null,
  email: 'l@example.com', role: 'partner', is_active: true,
}

function mountPage() {
  return mount(UserManagement, {
    attachTo: document.body,
    global: {
      plugins: [ElementPlus],
      directives: { permission: {} },
      stubs: {
        GtPageHeader: { template: '<div><slot /></div>' },
        UserProjectRoleTree: true,
      },
    },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  usersPayload = [PARTNER_NAMED, PARTNER_LEGACY]
})

describe('UserManagement 全名展示与必填', () => {
  it('userLabel 优先全名、缺失回落登录名', async () => {
    const w = mountPage()
    await flushPromises()
    const vm = w.vm as any
    expect(vm.userLabel(PARTNER_NAMED)).toBe('张合伙人')
    expect(vm.userLabel(PARTNER_LEGACY)).toBe('partner_legacy')
    w.unmount()
  })

  it('合伙人下拉 DOM 里出现全名、不出现该账号的登录名', async () => {
    const w = mountPage()
    await flushPromises()
    const vm = w.vm as any
    vm.showCreate = true
    vm.form.role = 'manager' // 触发「所属合伙人」显示
    await flushPromises()

    // 只看下拉选项自身，避免把表格里的登录名列误计进来
    const opts = Array.from(document.querySelectorAll('.el-select-dropdown__item'))
      .map((n) => (n as HTMLElement).textContent?.trim())
    // 反向锚点：确认选项确实渲染出来了，否则下面的"不含登录名"是在测空集
    expect(opts.length).toBeGreaterThan(0)
    expect(opts).toContain('张合伙人')
    expect(opts).not.toContain('partner_zhang')
    // 无全名的合伙人回落登录名，仍然可选
    expect(opts).toContain('partner_legacy')
    w.unmount()
  })

  it('兜底 option 走真实展示口径也不泄漏裸 UUID', async () => {
    const w = mountPage()
    await flushPromises()
    const vm = w.vm as any
    vm.editUser({
      id: 'u-9', username: 'sub', full_name: '下属', email: 's@example.com',
      role: 'manager', parent_partner_id: 'p-invisible-uuid',
    })
    await flushPromises()

    const opt = vm.partnerOptions.find((o: any) => o.id === 'p-invisible-uuid')
    expect(opt).toBeTruthy()
    // 走的是真实展示口径 userLabel（读 full_name），而不是直接看 username
    expect(vm.userLabel(opt)).not.toBe('p-invisible-uuid')
    expect(vm.userLabel(opt)).toContain('不可见')
    w.unmount()
  })

  it('全名挂了 required 规则且 DOM 渲染出必填标记', async () => {
    const w = mountPage()
    await flushPromises()
    const vm = w.vm as any
    const fnRules = vm.userFormRules?.full_name || []
    expect(fnRules.some((r: any) => r.required === true)).toBe(true)

    vm.showCreate = true
    await flushPromises()
    const requiredLabels = Array.from(
      document.querySelectorAll('.el-form-item.is-required > .el-form-item__label'),
    ).map((n) => (n as HTMLElement).textContent?.trim())
    expect(requiredLabels).toContain('全名')
    w.unmount()
  })

  // ── 行为判据（Req 3.2）──
  // 依赖 vitest.config.ts 的 `server.deps.inline: ['element-plus']`。
  // 删掉那条配置 ⇒ el-form 校验恒通过 ⇒ 下面两条会打红。

  it('全名为空时提交被拦住：不调 createUser', async () => {
    const { createUser } = await import('@/services/commonApi')
    const w = mountPage()
    await flushPromises()
    const vm = w.vm as any

    vm.showCreate = true
    await flushPromises()

    // 除全名外都填好 —— 隔离出「全名」这唯一变量，
    // 否则别的字段缺失也会拦住提交，判据就测不到全名规则
    vm.form.username = 'newuser'
    vm.form.email = 'new@example.com'
    vm.form.password = 'secret123'
    vm.form.role = 'auditor'
    vm.form.full_name = ''
    await flushPromises()

    await vm.saveUser()
    await flushPromises()

    expect(
      (createUser as any).mock.calls.length,
      '全名为空却发出了创建请求 —— 必填没拦住。若 vitest.config.ts 的 ' +
        "server.deps.inline: ['element-plus'] 被删，校验会恒通过，参见 " +
        'src/__tests__/elFormValidationFidelity.spec.ts',
    ).toBe(0)

    w.unmount()
  })

  it('全名填上后提交放行：createUser 被调用（正向锚点）', async () => {
    // 成对判据 —— 缺这条，上一条在「什么都拦住」时也会绿
    const { createUser } = await import('@/services/commonApi')
    ;(createUser as any).mockClear()

    const w = mountPage()
    await flushPromises()
    const vm = w.vm as any

    vm.showCreate = true
    await flushPromises()
    vm.form.username = 'newuser'
    vm.form.email = 'new@example.com'
    vm.form.password = 'secret123'
    vm.form.role = 'auditor'
    vm.form.full_name = '新用户全名'
    await flushPromises()

    await vm.saveUser()
    await flushPromises()

    expect(
      (createUser as any).mock.calls.length,
      '全名已填却仍被拦住 —— 规则或校验链路有问题（不是环境失真）',
    ).toBe(1)
    expect((createUser as any).mock.calls[0][0]).toMatchObject({
      full_name: '新用户全名',
    })

    w.unmount()
  })

  /**
   * ⚠️ **已登记的口径差**：纯空白全名（`"   "`）能通过**前端**校验。
   *
   * 实证（2026-08-31，最小 async-validator 用例）：
   *   - `{ required: true }` 对 `"   "` → PASSED（它只判非空字符串）
   *   - `{ required: true } + { min: 2 }` 对 `"   "` → PASSED（长度 3 满足 min）
   *
   * 后端 `UserCreate/UserUpdate` 的 `full_name` **已收紧为 strip 后判长**
   * ⇒ 纯空白会被挡在 422，数据不会脏；但用户要多一次往返才看到错误。
   *
   * 两条可行修法（均已实证，都不污染表单数据）：
   *   a) `rules.required` 加 `transform: v => typeof v === 'string' ? v.trim() : v`
   *      （实测 `transform_mutatesSource === false`，源值不变）
   *   b) 加 async-validator 原生的 `whitespace: true`
   *      （实测对正常值不误伤）
   *
   * 🔴 **为何本次没修**：`rules.required` 是全仓共用生成器，
   *    **38 个文件 / 75 处调用**都会跟着变口径 —— 那是独立的一次收紧，
   *    不属于 spec `vitest-elform-validation-fidelity`（它只负责让 vitest 的
   *    校验真实生效）。擅自改会把一次环境修复混成一次全仓行为变更。
   *
   * 本判据故意断言**当前真实行为**而不是期望行为，理由同守卫文件：
   * 写死期望会变成一条挡住 CI 的红，写反了又会在修好后变成恒假判据。
   * ⇒ **修好 a) 或 b) 之后，把这条的 `toBe(1)` 改成 `toBe(0)` 并删掉本段说明。**
   */
  it('纯空白全名当前仍能通过前端校验（已登记的口径差，非环境失真）', async () => {
    const { createUser } = await import('@/services/commonApi')
    ;(createUser as any).mockClear()

    const w = mountPage()
    await flushPromises()
    const vm = w.vm as any

    vm.showCreate = true
    await flushPromises()
    vm.form.username = 'newuser2'
    vm.form.email = 'new2@example.com'
    vm.form.password = 'secret123'
    vm.form.role = 'auditor'
    vm.form.full_name = '   '
    await flushPromises()

    await vm.saveUser()
    await flushPromises()

    expect(
      (createUser as any).mock.calls.length,
      '纯空白全名的拦截行为变了 —— 若已给 rules.required 加上 trim/whitespace，' +
        '请把本条改为 toBe(0) 并删掉上方说明段',
    ).toBe(1)

    w.unmount()
  })
})
