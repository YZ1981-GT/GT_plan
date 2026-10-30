/**
 * RoleDataScopeManager.spec.ts — dept-role-data-permission Task 11.4
 *
 * ═══════════════════════════════════════════════════════════════════
 * 判据分四层，每层拦不同的缺陷形态
 * ═══════════════════════════════════════════════════════════════════
 * A. **接线**（最先写的一层）—— 组件必须被 `SystemSettings.vue` 真正引用。
 *    本 spec 存在的直接原因：11.2 的组件写完后**零接线**，静态扫才发现
 *    `SystemSettings.vue` 对它 0 引用 ⇒ 无渲染宿主 = 死代码。
 *    「组件文件存在」不等于「能力已交付」，必须查唯一消费方。
 * B. **data_scope 联动**（tasks.md 点名要求）—— 选 2 才出现项目多选，
 *    切走要清空。
 * C. **语义正确性** —— scope≠2 提交时显式传 `[]`（清空关联）；
 *    "只改名"不得带上 project_ids（否则抹掉项目配置）。
 * D. **跨端一致性** —— 前端的 `SEED_SCOPE` 镜像必须与后端
 *    `_SEED_SCOPE_BY_ENUM_ROLE` 逐项相同，否则「未绑定时显示什么范围」会骗人。
 *
 * ⚠️ B/C/D 都在组件内部，**拦不住 A** —— 组件可以自己测得很好却压根没被挂载。
 *    反之 A 拦不住 B/C/D。四层缺一不可。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// ─── mock 掉网络层 ─────────────────────────────────────────────────
const mockListRoles = vi.fn()
const mockCreateRole = vi.fn()
const mockUpdateRole = vi.fn()
const mockDeleteRole = vi.fn()
const mockGetRoleProjects = vi.fn()
const mockGetUserRoles = vi.fn()
const mockAssignUserRoles = vi.fn()
const mockListProjects = vi.fn()
const mockListUsers = vi.fn()

vi.mock('@/services/systemRoleApi', async (importOriginal) => {
  // 🔴 **保留真实的 DATA_SCOPE_OPTIONS / dataScopeLabel**（只 mock 网络函数）。
  //    全量替换会让"下拉里有哪些选项""标签文案对不对"这类判据变成在测 mock
  //    自己 —— 组件真把选项写错也照样绿。
  const actual = await importOriginal<typeof import('@/services/systemRoleApi')>()
  return {
    ...actual,
    listRoles: (...a: any[]) => mockListRoles(...a),
    createRole: (...a: any[]) => mockCreateRole(...a),
    updateRole: (...a: any[]) => mockUpdateRole(...a),
    deleteRole: (...a: any[]) => mockDeleteRole(...a),
    getRoleProjects: (...a: any[]) => mockGetRoleProjects(...a),
    getUserRoles: (...a: any[]) => mockGetUserRoles(...a),
    assignUserRoles: (...a: any[]) => mockAssignUserRoles(...a),
  }
})

vi.mock('@/services/commonApi', () => ({
  listProjects: (...a: any[]) => mockListProjects(...a),
  listUsers: (...a: any[]) => mockListUsers(...a),
}))

vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

const mockConfirm = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: (...a: any[]) => mockConfirm(...a) },
}))

import RoleDataScopeManager from '../RoleDataScopeManager.vue'
import UserRoleBindingPanel from '../UserRoleBindingPanel.vue'
import { DATA_SCOPE_OPTIONS, dataScopeLabel } from '@/services/systemRoleApi'

const STUBS = {
  'el-input': true, 'el-button': true, 'el-icon': true, 'el-empty': true,
  'el-tag': true, 'el-table': true, 'el-table-column': true,
  'el-dialog': true, 'el-form': true, 'el-form-item': true,
  'el-select': true, 'el-option': true, 'el-card': true,
  'el-radio-group': true, 'el-radio': true,
}

/**
 * 需要看到弹窗内部结构时用这套 stub。
 *
 * 🔴 `stubs: { 'el-dialog': true }` 生成的是**自闭合** stub，**插槽内容不渲染**
 *    ⇒ 弹窗里的整个表单都不在 DOM 里，任何"数元素个数"的判据都恒为 0
 *    （= 假绿，因为期望 0 的那一半会被蒙对）。要断言弹窗内部就必须给
 *    `el-dialog` / `el-form` / `el-form-item` 换成带 `<slot/>` 的 stub。
 */
const DIALOG_OPEN_STUBS = {
  ...STUBS,
  'el-dialog': { template: '<div class="dlg"><slot /><slot name="footer" /></div>' },
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { template: '<div class="fi"><slot /></div>' },
}

const ROLES = [
  { id: 1, name: '全部数据角色', role_key: 'all_scope', data_scope: 1, status: '0' },
  { id: 2, name: '自定义项目角色', role_key: 'cus_scope', data_scope: 2, status: '0' },
  { id: 3, name: '仅本人角色', role_key: 'self_scope', data_scope: 5, status: '0' },
]
const PROJECTS = [
  { id: 'p1', name: '项目甲', client_name: '甲公司' },
  { id: 'p2', name: '项目乙', client_name: '乙公司' },
]

beforeEach(() => {
  vi.clearAllMocks()
  mockListRoles.mockResolvedValue(ROLES)
  mockListProjects.mockResolvedValue(PROJECTS)
  mockGetRoleProjects.mockResolvedValue(['p1'])
  mockListUsers.mockResolvedValue([])
  mockGetUserRoles.mockResolvedValue([])
  mockConfirm.mockResolvedValue(true)
})

function mountRole() {
  return mount(RoleDataScopeManager, { global: { stubs: STUBS } })
}

// ═══════════════════════════════════════════════════════════════════
// A 层：接线 —— 组件必须有渲染宿主
// ═══════════════════════════════════════════════════════════════════

describe('A. 接线（组件必须有真实渲染宿主）', () => {
  /**
   * ⚠️ **2026-08-31 宿主更正**（顺手修既有欠账，非本 spec 范围）：
   *
   *    本层原先查的是 `views/SystemSettings.vue`，但那两个 Tab 已由
   *    spec `nav-grouping-and-permission-center`（Req 6.3）**迁往
   *    `views/PermissionCenter.vue`** —— `SystemSettings.vue` 里现在只剩一句
   *    注释说明迁走了，其 `activeTab` 联合类型是 `'basic' | 'enum-dict' | 'logs'`。
   *
   *    ⇒ 本层 4 条判据在 HEAD 上**已经是红的**（基线对照实测：HEAD 5 红 /
   *      当前 4 红，这 4 条两侧相同）。那次迁移改了宿主却没改守卫，
   *      守卫从此锁着一个不存在的接线 —— 属**锁旧口径**，须翻转指向真宿主。
   *
   *    本 spec（data-scope-participant-visibility）只改 B/D 层，与 A 层无关；
   *    但既然改到了同一文件、且修复只是换个路径，就一并修掉而不是留着长期红。
   */
  const HOST = resolve(__dirname, '../../../views/PermissionCenter.vue')
  const src = readFileSync(HOST, 'utf-8')

  it.each([
    ['RoleDataScopeManager', 'role-scope'],
    ['UserRoleBindingPanel', 'user-roles'],
  ])('%s 被 import、在模板里渲染、且 Tab name 为 %s', (comp, tabName) => {
    expect(src).toContain(`import ${comp} from '@/components/system/${comp}.vue'`)
    // 三要素：import + 模板标签 + Tab 承载
    expect(src).toContain(`<${comp} `)
    expect(src).toContain(`name="${tabName}"`)
    // 宿主用懒加载标记而非 `activeTab === '<tab>'` 直接判等
    expect(src).toContain(`loaded['${tabName}']`)
  })

  it('TabKey 联合类型必须包含两个 Tab（否则 tsc 报错）', () => {
    // ⚠️ 模板里的类型错误**不会**阻止 dev server 渲染 ⇒ 本地看着正常、CI 的
    //    tsc 却红。这条把类型与 Tab name 绑在一起。
    // ⚠️ 宿主用的是 `type TabKey = ...` 具名类型，不是 `ref<...>` 内联联合。
    const m = src.match(/type TabKey = ([^\n]+)/)
    expect(m, 'TabKey 类型声明找不到了').toBeTruthy()
    const union = m![1]
    for (const t of ['role-scope', 'user-roles']) {
      expect(union, `TabKey 联合类型漏了 '${t}'`).toContain(`'${t}'`)
    }
  })

  it('权限管理中心整体只对 admin 可见（路由级守卫，不是 Tab 级 v-if）', () => {
    // 🔴 原判据要求每个 Tab 带 `v-if="isAdmin"` —— 那是旧宿主
    //    `SystemSettings.vue` 的形态（它是所有人都能进的页面，故需逐 Tab 控制）。
    //    新宿主 `PermissionCenter.vue` 是**整页**只给 admin，权限在**路由**上，
    //    Tab 内不再重复判断。照搬旧断言会要求一个不该存在的冗余判断。
    //
    //    ⇒ 改为断言路由配置里该页带了 admin 守卫。这仍然锁住了原意图
    //      （"数据权限管理不得对非 admin 可见"），只是锁在正确的层。
    // 当前项目按域拆分路由（domains/system.ts），参考仓直接在 index.ts 内联。
    // 两个文件都搜：PermissionCenter 路由 + admin 限定。
    const candidates = [
      resolve(__dirname, '../../../router/index.ts'),
      resolve(__dirname, '../../../router/domains/system.ts'),
    ]
    let idx = -1
    let around = ''
    for (const file of candidates) {
      const routerSrc = readFileSync(file, 'utf-8')
      const i = routerSrc.indexOf('PermissionCenter')
      if (i > -1) {
        idx = i
        around = routerSrc.slice(Math.max(0, i - 600), i + 600)
        break
      }
    }
    expect(idx, '路由表里找不到 PermissionCenter').toBeGreaterThan(-1)

    expect(
      /admin/i.test(around),
      '权限管理中心的路由记录附近没有任何 admin 限定 ⇒ 非 admin 可能进入',
    ).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════
// B 层：data_scope 下拉联动项目多选显隐（tasks.md 点名）
// ═══════════════════════════════════════════════════════════════════

describe('B. data_scope 联动项目多选', () => {
  it('下拉有 1/2/6/5 四个选项且按范围从宽到窄排（3/4 已废弃，不得出现）', () => {
    // ⚠️ **2026-08-31 判据翻转**（spec `data-scope-participant-visibility`）：
    //    原断言为 `toEqual([1, 2, 5])`。新增档位 6「我参与的项目」后必然打红 ——
    //    那是**预期**，此处按新口径翻转，而不是放宽成 `toContain`。
    //
    //    顺序 `1,2,6,5` 不是数值升序，而是对齐后端权限序
    //    `PRIORITY_ORDER = {1:0, 2:1, 6:2, 5:3}`：scope=5 的结果恒为 scope=6
    //    结果的子集（`created_by` 是项目级五来源之一）⇒ 6 比 5 宽。
    //    按数值排会让管理员以为"5 比 6 宽"而配错权限。
    expect(DATA_SCOPE_OPTIONS.map((o) => o.value)).toEqual([1, 2, 6, 5])
  })

  it('scope=6 时不显示项目多选（只有 scope=2 才需要勾项目）', async () => {
    // 新档位的联动判据：6 的可见范围由成员关系推导，不需要手工勾项目。
    // 若漏了这条，把 `v-if` 写成 `data_scope !== 5` 之类也能让 B 层其余用例通过。
    const w = mount(RoleDataScopeManager, { global: { stubs: DIALOG_OPEN_STUBS } })
    await flushPromises()
    const vm = w.vm as any
    vm.dialogVisible = true

    const multiSelects = () =>
      w.findAll('el-select-stub')
        .filter((n) => n.attributes('multiple') !== undefined)

    vm.form.data_scope = 6
    await w.vm.$nextTick()
    expect(multiSelects().length, 'scope=6 时不应出现项目多选').toBe(0)

    // 对照：切到 2 必须出现（证明上一条不是"整棵表单没渲染"）
    vm.form.data_scope = 2
    await w.vm.$nextTick()
    expect(multiSelects().length, 'scope=2 时应出现项目多选').toBe(1)
  })

  it('选 2 之外的范围时不显示项目多选；选 2 时显示', async () => {
    // ⚠️ 两个坑（初版连踩）：
    //  ①**不能用 `w.html()` 查文本** —— `el-form-item` 被 stub 成自闭合标签后
    //    label 属性与插槽内容都不进 DOM ⇒ 查「可见项目」恒 false，两个方向的
    //    断言必有一个被蒙对。
    //  ②**`el-dialog` 被默认 stub 时其插槽内容压根不渲染** ⇒ 表单整个不在
    //    DOM 里，数 el-select 恒为 0。必须用带 `<slot/>` 的自定义 stub，
    //    并且**真的把弹窗打开**（dialogVisible=true），否则测的是空树。
    const w = mount(RoleDataScopeManager, { global: { stubs: DIALOG_OPEN_STUBS } })
    await flushPromises()
    const vm = w.vm as any
    vm.dialogVisible = true

    const multiSelects = () =>
      w.findAll('el-select-stub')
        .filter((n) => n.attributes('multiple') !== undefined)

    vm.form.data_scope = 5
    await w.vm.$nextTick()
    expect(multiSelects().length, 'scope=5 时不应出现项目多选').toBe(0)

    vm.form.data_scope = 2
    await w.vm.$nextTick()
    expect(multiSelects().length, 'scope=2 时应出现项目多选').toBe(1)

    // 切回去必须消失（只测单向会漏掉"显示后不再隐藏"）
    vm.form.data_scope = 1
    await w.vm.$nextTick()
    expect(multiSelects().length, 'scope 切回 1 后项目多选应消失').toBe(0)
  })

  it('反向自检：弹窗打开且 scope=2 时，DOM 里确实存在表单（防上一条测空树）', async () => {
    // 没有这条，`multiSelects().length === 0` 可能只是因为整棵表单没渲染 ——
    // 那样"scope=5 时为 0"会被蒙对，而"scope=2 时为 1"才暴露问题。
    const w = mount(RoleDataScopeManager, { global: { stubs: DIALOG_OPEN_STUBS } })
    await flushPromises()
    const vm = w.vm as any
    vm.dialogVisible = true
    vm.form.data_scope = 2
    await w.vm.$nextTick()
    // 表单里至少有：角色名称/标识两个 input + 范围下拉 + 项目多选
    expect(w.findAll('el-select-stub').length).toBeGreaterThanOrEqual(2)
  })

  it('切到 data_scope=2 才去拉项目列表（不在挂载时就拉）', async () => {
    const w = mountRole()
    await flushPromises()
    expect(mockListProjects).not.toHaveBeenCalled()

    ;(w.vm as any).form.data_scope = 2
    await flushPromises()
    expect(mockListProjects).toHaveBeenCalled()
  })

  it('项目选项的 label 优先取 client_name（审计场景按被审计单位识别）', async () => {
    // 同上：stub 掉的 el-option 不渲染 label 文本 ⇒ 断言组件内部映射结果。
    const w = mountRole()
    await flushPromises()
    const vm = w.vm as any
    vm.form.data_scope = 2
    await flushPromises()

    const opts = vm.projectOptions as Array<{ id: string; label: string }>
    expect(opts.map((o) => o.id)).toEqual(['p1', 'p2'])
    expect(opts.map((o) => o.label)).toEqual(['甲公司', '乙公司'])
  })

  it('client_name 缺失时回退 name，两者都缺才用 id（不显示空白）', async () => {
    mockListProjects.mockResolvedValueOnce([
      { id: 'p3', name: '只有名称', client_name: null },
      { id: 'p4', name: null, client_name: null },
    ])
    const w = mountRole()
    await flushPromises()
    const vm = w.vm as any
    vm.form.data_scope = 2
    await flushPromises()
    expect((vm.projectOptions as any[]).map((o) => o.label)).toEqual([
      '只有名称', 'p4',
    ])
  })
})

// ═══════════════════════════════════════════════════════════════════
// C 层：提交语义 —— 清空 vs 不改
// ═══════════════════════════════════════════════════════════════════

describe('C. 提交语义（清空 vs 不改，这两者混淆会静默越权/丢配置）', () => {
  it('新建 scope=5 时 project_ids 传空数组（不带脏数据进库）', async () => {
    mockCreateRole.mockResolvedValue(ROLES[2])
    const w = mountRole()
    await flushPromises()
    const vm = w.vm as any
    vm.form = {
      name: '新角色', role_key: 'nr', data_scope: 5,
      status: '0', project_ids: ['p1'],  // 故意留着脏值
    }
    await vm.onSubmit()
    await flushPromises()

    const payload = mockCreateRole.mock.calls[0][0]
    expect(payload.project_ids).toEqual([])
  })

  it('编辑时把 scope 从 2 改成 5 ⇒ 必须显式传 [] 清空关联', async () => {
    mockUpdateRole.mockResolvedValue(ROLES[2])
    const w = mountRole()
    await flushPromises()
    const vm = w.vm as any

    await vm.openEdit(ROLES[1])   // scope=2，已关联 p1
    await flushPromises()
    vm.form.data_scope = 5
    await vm.onSubmit()
    await flushPromises()

    const payload = mockUpdateRole.mock.calls[0][1]
    expect(payload.project_ids).toEqual([])
  })

  it('🔴 只改角色名（scope 仍为 2、项目未动）⇒ 不得带 project_ids', async () => {
    // 带上就等于"用当前表单值覆盖"，一旦表单值加载失败就把项目配置抹掉。
    mockUpdateRole.mockResolvedValue(ROLES[1])
    const w = mountRole()
    await flushPromises()
    const vm = w.vm as any

    await vm.openEdit(ROLES[1])
    await flushPromises()
    vm.form.name = '改个名字'
    await vm.onSubmit()
    await flushPromises()

    const payload = mockUpdateRole.mock.calls[0][1]
    expect(payload).not.toHaveProperty('project_ids')
    expect(payload.name).toBe('改个名字')
  })

  it('改动过项目勾选 ⇒ 必须带 project_ids', async () => {
    mockUpdateRole.mockResolvedValue(ROLES[1])
    const w = mountRole()
    await flushPromises()
    const vm = w.vm as any

    await vm.openEdit(ROLES[1])
    await flushPromises()
    vm.form.project_ids = ['p1', 'p2']
    await vm.onSubmit()
    await flushPromises()

    expect(mockUpdateRole.mock.calls[0][1].project_ids).toEqual(['p1', 'p2'])
  })

  it('projectIdsChanged 与顺序无关（避免仅顺序不同就误判为改动）', async () => {
    const w = mountRole()
    await flushPromises()
    const vm = w.vm as any
    await vm.openEdit({ ...ROLES[1] })
    await flushPromises()
    // 加载到的是 ['p1']
    vm.form.project_ids = ['p1']
    expect(vm.projectIdsChanged()).toBe(false)
    vm.form.project_ids = ['p2', 'p1']
    expect(vm.projectIdsChanged()).toBe(true)
  })

  it('scope=2 但一个项目都没勾 ⇒ 弹确认（合法但需用户确认是有意的）', async () => {
    mockCreateRole.mockResolvedValue(ROLES[1])
    const w = mountRole()
    await flushPromises()
    const vm = w.vm as any
    vm.form = {
      name: 'x', role_key: 'x', data_scope: 2, status: '0', project_ids: [],
    }
    await vm.onSubmit()
    await flushPromises()
    expect(mockConfirm).toHaveBeenCalled()
  })

  it('确认框点取消 ⇒ 不发请求', async () => {
    mockConfirm.mockRejectedValue(new Error('cancel'))
    const w = mountRole()
    await flushPromises()
    const vm = w.vm as any
    vm.form = {
      name: 'x', role_key: 'x', data_scope: 2, status: '0', project_ids: [],
    }
    await vm.onSubmit()
    await flushPromises()
    expect(mockCreateRole).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════
// D 层：跨端一致性 + 文案
// ═══════════════════════════════════════════════════════════════════

describe('D. 跨端一致性（镜像常量会漂移，必须钉住）', () => {
  it('🔴 前端 SEED_SCOPE 必须与后端 _SEED_SCOPE_BY_ENUM_ROLE 逐项相同', () => {
    // 后端真源：backend/app/services/login_user_service.py
    // 漂移的后果不是报错，而是「未绑定角色时界面显示的范围」与实际生效的不一致
    // —— 管理员据此做判断就会配错权限。
    const backend = readFileSync(
      resolve(__dirname, '../../../../../../backend/app/services/login_user_service.py'),
      'utf-8',
    )
    const block = backend.match(
      /_SEED_SCOPE_BY_ENUM_ROLE: dict\[str, int\] = \{([\s\S]*?)^\}/m,
    )
    expect(block, '后端 _SEED_SCOPE_BY_ENUM_ROLE 定义找不到了').toBeTruthy()

    // ⚠️ **2026-08-31 扩容**（spec `data-scope-participant-visibility`）：
    //    原正则只解析 `DATA_SCOPE_ALL|DATA_SCOPE_SELF` 两个常量名。后端引入
    //    `DATA_SCOPE_PARTICIPANT`（manager/site_lead）后，那两行**匹配不到**
    //    ⇒ parsed 少两项 ⇒ 与前端 8 项的 SEED_SCOPE 比对失败。
    //
    // 🔴 **刻意不改成 `\w+` 泛匹配后不校验值**：那样"后端写了个不存在的常量"
    //    也会通过（映射表查不到就得到 undefined，比对时两边都是 undefined 反而相等）。
    //    这里维护一张**显式**的常量名→数值表，新增档位时必须来这里登记 ——
    //    打红一次，比静默漂移好。
    const SCOPE_CONST_VALUES: Record<string, number> = {
      DATA_SCOPE_ALL: 1,
      DATA_SCOPE_CUSTOM: 2,
      DATA_SCOPE_PARTICIPANT: 6,
      DATA_SCOPE_SELF: 5,
    }
    const parsed: Record<string, number> = {}
    const unknownConsts: string[] = []
    for (const m of block![1].matchAll(/"(\w+)":\s*(DATA_SCOPE_\w+)/g)) {
      const value = SCOPE_CONST_VALUES[m[2]]
      if (value === undefined) {
        unknownConsts.push(m[2])
        continue
      }
      parsed[m[1]] = value
    }
    // 🔴 后端出现本表未登记的常量名 ⇒ 立即打红（而不是静默忽略那一行）
    expect(
      unknownConsts,
      `后端 seed 表用了本守卫未登记的常量：${unknownConsts.join(', ')} —— ` +
        '请在 SCOPE_CONST_VALUES 里补上它的数值，否则跨端比对会漏掉这些角色',
    ).toEqual([])
    expect(Object.keys(parsed).length, '后端 seed 表解析为空').toBeGreaterThan(0)
    // 反向自证：解析出的条数必须等于后端字面量里的键数（证明没有静默漏行）
    const backendKeyCount = [...block![1].matchAll(/"(\w+)":/g)].length
    expect(
      Object.keys(parsed).length,
      '解析出的条数少于后端字面量的键数 ⇒ 有行被静默跳过',
    ).toBe(backendKeyCount)

    const panel = readFileSync(
      resolve(__dirname, '../UserRoleBindingPanel.vue'), 'utf-8',
    )
    const feBlock = panel.match(/const SEED_SCOPE: Record<string, number> = \{([\s\S]*?)\}/)
    expect(feBlock, '前端 SEED_SCOPE 定义找不到了').toBeTruthy()
    const fe: Record<string, number> = {}
    for (const m of feBlock![1].matchAll(/(\w+):\s*(\d+)/g)) {
      fe[m[1]] = Number(m[2])
    }
    expect(fe).toEqual(parsed)
  })

  it('dataScopeLabel 对脏值返回带原值的提示（不返回空串）', () => {
    // 静默空白会让人以为"没配"，实际是配了个非法值（库里可能有历史 3/4）
    expect(dataScopeLabel(3)).toContain('3')
    expect(dataScopeLabel(4)).toContain('4')
    expect(dataScopeLabel(3)).not.toBe('')
  })

  it('四个合法值的标签是中文且互不相同（UI 全中文化）', () => {
    // ⚠️ 2026-08-31 由「三个」翻转为「四个」（新增 6「我参与的项目」）
    const labels = [1, 2, 6, 5].map(dataScopeLabel)
    expect(new Set(labels).size).toBe(4)
    for (const l of labels) {
      expect(l).toMatch(/[\u4e00-\u9fa5]/)
    }
  })

  it('scope=6 的标签明确区别于 scope=5（两者极易混淆）', () => {
    // 光"互不相同"不够 —— 若把 6 标成「仅本人数据（参与）」这类含混文案，
    // 管理员仍会配错。这条要求 6 的文案含"参与"、5 的文案含"本人"。
    expect(dataScopeLabel(6)).toContain('参与')
    expect(dataScopeLabel(5)).toContain('本人')
    expect(dataScopeLabel(6)).not.toContain('仅本人')
  })

  it('库里的脏 data_scope 在编辑时落到合法值（不让 el-select 回显裸数字）', async () => {
    const w = mountRole()
    await flushPromises()
    const vm = w.vm as any
    await vm.openEdit({
      id: 9, name: '脏角色', role_key: 'dirty', data_scope: 3, status: '0',
    })
    await flushPromises()
    // ⚠️ 2026-08-31 合法值集合由 [1,2,5] 扩为 [1,2,6,5]
    expect([1, 2, 6, 5]).toContain(vm.form.data_scope)
  })
})

// ═══════════════════════════════════════════════════════════════════
// UserRoleBindingPanel：清空语义与生效范围
// ═══════════════════════════════════════════════════════════════════

describe('E. UserRoleBindingPanel', () => {
  function mountPanel() {
    return mount(UserRoleBindingPanel, { global: { stubs: STUBS } })
  }

  const USERS = [
    { id: 'u1', username: 'test_auditor', full_name: '张三', email: 'a@x', role: 'auditor' },
    { id: 'u2', username: 'admin', full_name: null, email: 'b@x', role: 'admin' },
  ]

  beforeEach(() => {
    mockListUsers.mockResolvedValue(USERS)
  })

  it('挂载时同时拉账号与角色', async () => {
    mountPanel()
    await flushPromises()
    expect(mockListUsers).toHaveBeenCalled()
    expect(mockListRoles).toHaveBeenCalled()
  })

  it('多角色取范围最大者（argmin，不是相加）', async () => {
    const w = mountPanel()
    await flushPromises()
    const vm = w.vm as any
    await vm.onSelectUser(USERS[0])
    await flushPromises()

    vm.picked = [3]           // scope=5
    await w.vm.$nextTick()
    expect(vm.effectiveScope).toBe(5)

    vm.picked = [3, 1]        // scope=5 + scope=1 ⇒ 取 1
    await w.vm.$nextTick()
    expect(vm.effectiveScope).toBe(1)
  })

  it('未绑定任何角色 ⇒ 回落到系统角色的 seed 范围（不是"无权限"）', async () => {
    const w = mountPanel()
    await flushPromises()
    const vm = w.vm as any

    // ⚠️ 2026-09-14 翻转：auditor 的 seed 原为 5「仅本人」，
    //    V163（spec visibility）已改为 6「我参与的项目」（auditor/qc/eqcr 三角色
    //    从不是项目创建人，scope=5 下最终可见集恒空 ⇒ 收到委派通知却没项目）。
    //    旧断言锁的是 V163 之前的口径，属「判据落后于迁移」。
    await vm.onSelectUser(USERS[0])   // auditor ⇒ seed 6（V163）
    await flushPromises()
    vm.picked = []
    await w.vm.$nextTick()
    expect(vm.effectiveScope).toBe(6)

    await vm.onSelectUser(USERS[1])   // admin ⇒ seed 1
    await flushPromises()
    vm.picked = []
    await w.vm.$nextTick()
    expect(vm.effectiveScope).toBe(1)
  })

  it('🔴 界面文案不得把"清空绑定"说成"移除权限"', () => {
    const src = readFileSync(
      resolve(__dirname, '../UserRoleBindingPanel.vue'), 'utf-8',
    )
    // role_ids=[] 是合法操作，此后按 users.role 的 seed 角色定权限。
    // 说成"移除权限"会让管理员以为该账号什么都看不到，从而不敢用这个操作。
    expect(src).not.toContain('移除权限')
    expect(src).toContain('清空自定义角色')
    // 且必须写清回落到哪
    expect(src).toContain('回落')
  })

  it('从有绑定改成空 ⇒ 弹确认；确认后按 [] 提交', async () => {
    mockGetUserRoles.mockResolvedValue([
      { id: 1, name: '全部数据角色', role_key: 'all_scope', data_scope: 1 },
    ])
    mockAssignUserRoles.mockResolvedValue([])
    const w = mountPanel()
    await flushPromises()
    const vm = w.vm as any
    await vm.onSelectUser(USERS[0])
    await flushPromises()
    expect(vm.original).toEqual([1])

    vm.picked = []
    await vm.onSave()
    await flushPromises()

    expect(mockConfirm).toHaveBeenCalled()
    expect(mockAssignUserRoles).toHaveBeenCalledWith('u1', [])
  })

  it('清空确认点取消 ⇒ 不发请求', async () => {
    mockGetUserRoles.mockResolvedValue([
      { id: 1, name: '全部数据角色', role_key: 'all_scope', data_scope: 1 },
    ])
    mockConfirm.mockRejectedValue(new Error('cancel'))
    const w = mountPanel()
    await flushPromises()
    const vm = w.vm as any
    await vm.onSelectUser(USERS[0])
    await flushPromises()
    vm.picked = []
    await vm.onSave()
    await flushPromises()
    expect(mockAssignUserRoles).not.toHaveBeenCalled()
  })

  it('从空改成有绑定 ⇒ 不弹确认（只有"清空"才需要）', async () => {
    mockGetUserRoles.mockResolvedValue([])
    mockAssignUserRoles.mockResolvedValue([1])
    const w = mountPanel()
    await flushPromises()
    const vm = w.vm as any
    await vm.onSelectUser(USERS[0])
    await flushPromises()
    vm.picked = [1]
    await vm.onSave()
    await flushPromises()
    expect(mockConfirm).not.toHaveBeenCalled()
    expect(mockAssignUserRoles).toHaveBeenCalledWith('u1', [1])
  })

  it('changed 与顺序无关', async () => {
    mockGetUserRoles.mockResolvedValue([
      { id: 1, name: 'a', role_key: 'a', data_scope: 1 },
      { id: 3, name: 'c', role_key: 'c', data_scope: 5 },
    ])
    const w = mountPanel()
    await flushPromises()
    const vm = w.vm as any
    await vm.onSelectUser(USERS[0])
    await flushPromises()

    vm.picked = [3, 1]
    await w.vm.$nextTick()
    expect(vm.changed).toBe(false)

    vm.picked = [1]
    await w.vm.$nextTick()
    expect(vm.changed).toBe(true)
  })

  it('不绑 users 列表里不存在的字段（is_active 不在 /api/users/ 返回值里）', () => {
    const src = readFileSync(
      resolve(__dirname, '../UserRoleBindingPanel.vue'), 'utf-8',
    )
    // Vue 绑不存在的字段是静默渲染空串，四层检查都查不出 ⇒ 只能靠这条钉住。
    // 端点实际返回：id/username/full_name/email/role/parent_partner_id/dept_id
    expect(src).not.toMatch(/row\.is_active|\bu\.is_active/)
  })
})
