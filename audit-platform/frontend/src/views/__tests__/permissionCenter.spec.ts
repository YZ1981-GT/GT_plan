/**
 * 权限管理中心 —— wave 4 E 层接线判据 + Tab 行为（Task 5.3）
 *
 * spec: .kiro/specs/nav-grouping-and-permission-center
 * Validates: Requirements 5.1、5.2、5.3、5.4、5.5、5.6、5.7、5.8、5.9、7.4、7.5
 *
 * ## 为什么 E 层判据必须落在渲染结果上（Requirement 7.4）
 *
 * 本仓踩过「组件写完但零接线」：`RoleDataScopeManager.vue` 落盘后
 * `SystemSettings.vue` 对它 0 引用 ⇒ 文件存在、类型正确、单测能过，
 * 而用户永远看不到。故「PermissionCenter 挂载了三个子组件」这条**不能**
 * 用 grep 符号名代替 —— 符号出现在 import 行、却被模板漏掉照样是死代码。
 *
 * 本文件对三个子组件各注入一个**带唯一 data-testid 的替身**，断言
 * 它们真出现在 DOM 里。任一 import 或模板使用被删 ⇒ 对应 testid 消失 ⇒ 红。
 *
 * 但**只有**渲染断言也不够：替身是按模块路径注入的，若把 import 改指到
 * 另一个同名组件，替身仍会渲染（渲染断言蒙对）。故另加一组**源码断言**
 * 锁死三个 import 的目标路径 —— 两组判据抓的是不同缺陷：
 *   - 渲染断言：接没接（模板漏用）
 *   - 源码断言：接对没接对（指向本仓不存在的参考仓路径）
 *
 * ## el-tabs / el-tab-pane 的 stub（Requirement 7.5）
 *
 * 绝不能 stub 成 `true`：默认插槽不渲染 ⇒ 三个子组件全不挂载 ⇒
 * 「数子组件个数」恒为 0。而本文件恰好有一半判据期望的就是 0
 * （未激活 Tab 不挂载），那一半会被**蒙对**，另一半红了还会被误当成
 * 「懒加载写对了」。故用带 `<slot/>` 的自定义 stub，并配一条反向自检
 * 断言 DOM 内确实存在预期内容。
 *
 * ### 两个 stub 的刻意设计（勿按"更像真 el-tabs"去改）
 *
 * `el-tab-pane` 的 stub **无条件渲染插槽**（不按激活态裁剪）。真 el-tabs
 * 只渲染激活 pane，若 stub 照此实现，那么「未激活 Tab 的子组件不挂载」
 * 就会由 stub 自己保证 —— 把生产代码里的 `v-if="loaded[...]"` 整条删掉
 * 判据依然全绿（空转）。让 stub 无条件渲染后，DOM 里子组件的有无**只由
 * `loaded` 决定**，懒加载判据才真的在测生产代码。
 *
 * `el-tabs` 的 stub 通过 provide 下发 `switchTo`，pane stub 渲染一个可点
 * 的表头按钮 —— Tab 切换走的是「点击 → emit update:modelValue → v-model」
 * 这条真实链路，不写 VTU 内部 state。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { nextTick, defineComponent, h, provide, inject, reactive } from 'vue'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// ── 替身：全部放 vi.hoisted（vi.mock 工厂被提升到文件顶部，不能引用顶层变量）──
const hoisted = vi.hoisted(() => ({
  /**
   * `route` 必须是 reactive 的：`PermissionCenter` 里有一条
   * `watch(() => route.query.tab)`（外部带 `?tab=` 跳进来时同步激活态）。
   * 普通对象改 `query` 不触发依赖 ⇒ 那条 watch 永不执行 ⇒ 判据会把
   * 「同步逻辑压根没跑」误报成「实现写错了」。
   * （vi.hoisted 里不能用顶层 import，故用 globalThis 上的 Vue 也不行，
   *  改为在 mock 工厂内 await import('vue') 后再包 reactive —— 见下方。）
   */
  route: { path: '/settings/permissions', query: {} as Record<string, unknown> } as any,
  replace: vi.fn(),
  push: vi.fn(),
}))

/**
 * 只替换 `useRoute` / `useRouter` 两个 composable，其余导出**保留原样**。
 *
 * 不能整体替换：本文件下方要 `import('@/router')` 拿真实路由表做装配后断言，
 * 而 `router/index.ts` 顶层就在调 `createRouter` / `createWebHistory`。
 * 整体 mock 会让它报 `No "createRouter" export is defined on the "vue-router" mock`
 * —— 那是**判据自己坏了**，不是路由写错了，极易误判。
 */
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  const { reactive: vueReactive } = await import('vue')
  hoisted.route = vueReactive(hoisted.route)
  return {
    ...actual,
    useRoute: () => hoisted.route,
    useRouter: () => ({ replace: hoisted.replace, push: hoisted.push }),
  }
})

/**
 * 三个子组件替身。各自带唯一 `data-testid`，E 层断言即数这三个 testid。
 *
 * 必须替身而非真组件：三者合计 1476 行，`onMounted` 各自发请求
 * （`listUsers` / `listProjects` / 角色列表），真挂载会把本文件变成
 * 在测那三个组件而不是在测 PermissionCenter 的接线。
 */
vi.mock('@/views/UserManagement.vue', () => ({
  default: {
    name: 'UserManagementStub',
    render: () => h('div', { 'data-testid': 'stub-user-management' }, '账号权限内容'),
  },
}))
vi.mock('@/components/system/RoleDataScopeManager.vue', () => ({
  default: {
    name: 'RoleDataScopeManagerStub',
    render: () => h('div', { 'data-testid': 'stub-role-scope' }, '角色与数据权限内容'),
  },
}))
vi.mock('@/components/system/UserRoleBindingPanel.vue', () => ({
  default: {
    name: 'UserRoleBindingPanelStub',
    render: () => h('div', { 'data-testid': 'stub-user-roles' }, '账号角色绑定内容'),
  },
}))

// ── el-tabs / el-tab-pane 的带 slot stub ──────────────────────────────────
const TABS_CTX = Symbol('tabs-ctx')

interface TabsCtx {
  current: { value: unknown }
  switchTo: (name: string) => void
}

const ElTabsStub = defineComponent({
  name: 'ElTabsStub',
  props: { modelValue: { type: String, default: '' } },
  emits: ['update:modelValue'],
  setup(props, { emit, slots }) {
    // current 用 reactive 包一层，pane stub 才能跟着 modelValue 变化重渲染
    const state = reactive({ value: props.modelValue as unknown })
    provide<TabsCtx>(TABS_CTX, {
      current: state,
      switchTo: (name: string) => emit('update:modelValue', name),
    })
    return () => {
      state.value = props.modelValue
      return h('div', { class: 'el-tabs-stub', 'data-active': String(props.modelValue) }, slots.default?.())
    }
  },
})

const ElTabPaneStub = defineComponent({
  name: 'ElTabPaneStub',
  props: { label: { type: String, default: '' }, name: { type: String, default: '' } },
  setup(props, { slots }) {
    const ctx = inject<TabsCtx | null>(TABS_CTX, null)
    return () =>
      h('div', { class: 'el-tab-pane-stub', 'data-pane': props.name }, [
        // 表头按钮：点击走 emit update:modelValue → v-model 的真实链路
        h(
          'button',
          {
            class: 'pane-header',
            'data-pane-header': props.name,
            'data-pane-active': String(ctx?.current.value === props.name),
            onClick: () => ctx?.switchTo(props.name),
          },
          props.label,
        ),
        // ⚠️ 无条件渲染插槽（见文件头注释）：让子组件的有无只由 loaded 决定
        h('div', { class: 'pane-body' }, slots.default?.()),
      ])
  },
})

const STUBS = { 'el-tabs': ElTabsStub, 'el-tab-pane': ElTabPaneStub }

const PERM_CENTER = resolve(__dirname, '../PermissionCenter.vue')
const LAYOUT = resolve(__dirname, '../../layouts/ThreeColumnLayout.vue')
const ROUTER_SRC = resolve(__dirname, '../../router/index.ts')

/**
 * 剥掉 HTML 注释与 JS 行/块注释，只留下真实代码。
 *
 * 「某路径不出现在文件里」这类否定断言必须先剥注释 —— 文件头写了
 * 「参考仓用 X、本仓改用 Y」的对照说明，X 就实实在在出现在文件里，
 * 否定断言会被注释打红（本文件实测踩到过一次）。
 */
function stripVueComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')   // HTML 注释
    .replace(/\/\*[\s\S]*?\*\//g, '')  // JS 块注释
    .replace(/^\s*\/\/.*$/gm, '')      // JS 行注释（整行）
}

/** 三个子组件替身的 testid ↔ Tab name 对应表（判据一律从本表派生）。 */
const TAB_CHILDREN = [
  { tab: 'users', testid: 'stub-user-management', label: '账号权限' },
  { tab: 'role-scope', testid: 'stub-role-scope', label: '角色与数据权限' },
  { tab: 'user-roles', testid: 'stub-user-roles', label: '账号角色绑定' },
] as const

/**
 * 就地重置 `route.query`（**不换对象**）。
 *
 * `hoisted.route` 被 reactive 包过，组件持有的是那个代理的引用；
 * 整个替换 `route.query` 也会断开组件里 `watch(() => route.query.tab)`
 * 对旧对象的追踪链，于是「外部改 query」类判据会静默不触发。
 */
function resetQuery(next: Record<string, unknown> = {}): void {
  const q = hoisted.route.query
  for (const k of Object.keys(q)) delete q[k]
  Object.assign(q, next)
}

async function mountCenter(query: Record<string, unknown> = {}): Promise<{
  wrapper: VueWrapper<any>
  vm: any
}> {
  resetQuery(query)
  const mod = await import('@/views/PermissionCenter.vue')
  const wrapper = mount(mod.default, { global: { stubs: STUBS } })
  await flushPromises()
  await nextTick()

  // 反向自检（Requirement 7.5）：DOM 真渲染出三个 pane 且有可读文字，
  // 不是一棵被 stub 掏空的空树。缺这条时「数子组件恒为 0」会被当成
  // 「懒加载生效」蒙过去。
  expect(
    wrapper.findAll('.el-tab-pane-stub').length,
    '三个 el-tab-pane 未渲染（stub 掏空了插槽，后续所有计数判据都不可信）',
  ).toBe(3)
  expect(wrapper.text(), 'Tab 表头文字未渲染').toContain('账号权限')

  return { wrapper, vm: wrapper.vm }
}

const testidCount = (w: VueWrapper<any>, id: string) =>
  w.findAll(`[data-testid="${id}"]`).length

const mountedTestids = (w: VueWrapper<any>) =>
  TAB_CHILDREN.filter(c => testidCount(w, c.testid) > 0).map(c => c.tab)

async function clickTab(w: VueWrapper<any>, name: string): Promise<void> {
  await w.find(`[data-pane-header="${name}"]`).trigger('click')
  await nextTick()
}

beforeEach(() => {
  hoisted.replace.mockClear()
  hoisted.push.mockClear()
  resetQuery()
})

// ════════════════════════════════════════════════════════════════════════════
// E 层：接线（Requirement 5.1、5.2、7.4）
// ════════════════════════════════════════════════════════════════════════════

describe('E 层接线 — PermissionCenter 真挂载三个子组件（Req 5.1/5.2/7.4）', () => {
  it('三个 Tab 全激活过后，三个子组件替身都出现在 DOM 里', async () => {
    const { wrapper } = await mountCenter()

    // 逐个切过去（生产路径：点表头）
    for (const c of TAB_CHILDREN) await clickTab(wrapper, c.tab)

    for (const c of TAB_CHILDREN) {
      expect(
        testidCount(wrapper, c.testid),
        `${c.tab} Tab 的子组件未挂载（import 或模板使用被删？）`,
      ).toBe(1)
    }
    expect(mountedTestids(wrapper)).toEqual(['users', 'role-scope', 'user-roles'])
  })

  it('渲染出三个 Tab 且 name / label 与需求一致', async () => {
    const { wrapper } = await mountCenter()

    const panes = wrapper.findAll('.el-tab-pane-stub')
    expect(panes.map(p => p.attributes('data-pane'))).toEqual(
      TAB_CHILDREN.map(c => c.tab),
    )
    expect(panes.map(p => p.find('.pane-header').text())).toEqual(
      TAB_CHILDREN.map(c => c.label),
    )
  })

  it('每个子组件恰挂载 1 份（不是同一组件被重复挂三次）', async () => {
    const { wrapper } = await mountCenter()
    for (const c of TAB_CHILDREN) await clickTab(wrapper, c.tab)

    // 若三个 pane 误用了同一个组件，某个 testid 会是 3、另两个是 0
    const counts = TAB_CHILDREN.map(c => testidCount(wrapper, c.testid))
    expect(counts).toEqual([1, 1, 1])
  })

  it('源码断言：三个 import 指向本仓真实路径（不是参考仓的 RoleManagement/UserRoleManagement）', () => {
    const src = readFileSync(PERM_CENTER, 'utf-8')

    // 渲染断言按模块路径注入替身 ⇒ 改指到另一个同名组件时渲染仍绿，
    // 这条专抓「接错文件」。
    expect(src).toContain("import UserManagement from '@/views/UserManagement.vue'")
    expect(src).toContain(
      "import RoleDataScopeManager from '@/components/system/RoleDataScopeManager.vue'",
    )
    expect(src).toContain(
      "import UserRoleBindingPanel from '@/components/system/UserRoleBindingPanel.vue'",
    )

    // 参考仓那两个路径在本仓不存在，照抄必编译失败。
    // ⚠️ 必须先剥注释：`PermissionCenter.vue` 的文件头注释里有一张
    // 「参考仓 → 本仓」对照表，原文就含这两个路径 ⇒ 直接对全文
    // `not.toContain` 会被自己的注释打红（实测踩到）。
    const code = stripVueComments(src)
    expect(code).not.toContain('@/views/RoleManagement.vue')
    expect(code).not.toContain('@/views/UserRoleManagement.vue')
    // 反向自检：剥注释没把 import 一起剥掉（否则上面两条恒成立=空转）
    expect(code).toContain('RoleDataScopeManager.vue')
  })
})

// ════════════════════════════════════════════════════════════════════════════
// Tab 行为：初始激活 / 非法回退（Requirement 5.3、5.4）
// ════════════════════════════════════════════════════════════════════════════

describe('Tab 初始化 — ?tab= 直达与非法回退（Req 5.3/5.4）', () => {
  it.each(TAB_CHILDREN.map(c => c.tab))(
    '合法 ?tab=%s ⇒ 初始激活该 Tab 且只挂载它的子组件',
    async (tab) => {
      const { wrapper, vm } = await mountCenter({ tab })

      expect(vm.activeTab).toBe(tab)
      expect(wrapper.find('.el-tabs-stub').attributes('data-active')).toBe(tab)
      // 只有该 Tab 的子组件在 DOM 里（同时验了初始激活与懒加载）
      expect(mountedTestids(wrapper)).toEqual([tab])
    },
  )

  it.each([
    ['xxx', '未知字符串'],
    ['roles', '参考仓的旧 Tab 名（本仓叫 role-scope）'],
    ['USERS', '大小写不符'],
    ['', '空串'],
  ])('非法 ?tab=%s（%s）⇒ 回退 users 且不报错', async (tab) => {
    const { wrapper, vm } = await mountCenter({ tab })

    expect(vm.activeTab).toBe('users')
    expect(mountedTestids(wrapper)).toEqual(['users'])
  })

  it.each([
    ['缺 tab 参数', {}],
    ['tab=undefined', { tab: undefined }],
    ['tab 为数组（?tab=a&tab=b）', { tab: ['users', 'user-roles'] }],
    ['tab 为数字', { tab: 1 }],
  ])('%s ⇒ 回退 users 不抛异常', async (_desc, query) => {
    const { vm } = await mountCenter(query as Record<string, unknown>)
    expect(vm.activeTab).toBe('users')
  })

  it('非法 tab 下不会因回退而写 query（初始不该产生一次回写）', async () => {
    const spy = vi.spyOn(window.history, 'replaceState')
    await mountCenter({ tab: 'xxx' })
    // 初始化只解析不回写；回写只发生在用户切 Tab 时（见下一个 describe）
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })
})

// ════════════════════════════════════════════════════════════════════════════
// Tab 切换回写 query（Requirement 5.5）
// ════════════════════════════════════════════════════════════════════════════

describe('Tab 切换 — history.replaceState 回写 ?tab=（Req 5.5）', () => {
  let replaceStateSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    // 复位地址栏（真实 API）后再装 spy：防止各用例互相污染。
    window.history.replaceState({}, '', '/settings/permissions')
    // 不 mock 掉本体（要让它真改 window.location），仅记录调用。
    replaceStateSpy = vi.spyOn(window.history, 'replaceState')
    // vitest 对同一方法重复 spyOn 会复用同一 spy（累计旧调用），必须清空。
    replaceStateSpy.mockClear()
  })
  afterEach(() => {
    replaceStateSpy.mockRestore()
  })

  // 从最后一次 replaceState 调用（null, '', url）里解析地址。
  const lastUrl = () => new URL(replaceStateSpy.mock.calls.at(-1)?.[2] as string)

  it('切到 role-scope ⇒ 回写 ?tab=role-scope（不经 Vue Router，防整页重挂载）', async () => {
    const { wrapper, vm } = await mountCenter()

    await clickTab(wrapper, 'role-scope')

    expect(vm.activeTab).toBe('role-scope')
    expect(replaceStateSpy).toHaveBeenCalledTimes(1)
    expect(lastUrl().searchParams.get('tab')).toBe('role-scope')
  })

  it.each(TAB_CHILDREN.map(c => c.tab).filter(t => t !== 'users'))(
    '切到 %s ⇒ 回写的 query.tab 正是该 Tab',
    async (tab) => {
      const { wrapper } = await mountCenter()
      await clickTab(wrapper, tab)

      expect(lastUrl().searchParams.get('tab')).toBe(tab)
    },
  )

  it('回写保留 query 里的其他参数（不把别人的 query 冲掉）', async () => {
    // 先让地址栏带 keep=me（真实 pushState，未被 spy）；组件读 window.location
    window.history.pushState({}, '', '/settings/permissions?keep=me')
    const { wrapper } = await mountCenter({ keep: 'me' })

    await clickTab(wrapper, 'user-roles')

    expect(lastUrl().searchParams.get('keep')).toBe('me')
    expect(lastUrl().searchParams.get('tab')).toBe('user-roles')
  })

  it('点当前已激活的 Tab ⇒ 不重复回写（防回环刷 history）', async () => {
    const { wrapper } = await mountCenter({ tab: 'role-scope' })
    // 用增量而非「整个 spy 0 次」：vi.spyOn 对同一方法跨用例会复用 spy、
    // mock.calls 会带上前几个用例的调用，绝对值断言恒红（实测踩到）。
    const before = replaceStateSpy.mock.calls.length

    await clickTab(wrapper, 'role-scope')

    expect(replaceStateSpy.mock.calls.length).toBe(before)
  })

  it('外部改 route.query.tab ⇒ 激活态跟着同步', async () => {
    const { wrapper, vm } = await mountCenter({ tab: 'users' })

    // 模拟从别处带 ?tab= 跳进来（watch(() => route.query.tab) 那条）。
    // ⚠️ 只能改 query 的属性，不能整个换掉 hoisted.route —— 组件持有的是
    // mount 时那个 reactive 代理的引用，换对象后它监听的还是旧那个。
    hoisted.route.query.tab = 'user-roles'
    await nextTick()
    await nextTick()

    expect(vm.activeTab).toBe('user-roles')
    expect(testidCount(wrapper, 'stub-user-roles')).toBe(1)
  })

  it('外部把 query.tab 改成非法值 ⇒ 回退 users', async () => {
    const { vm } = await mountCenter({ tab: 'user-roles' })

    hoisted.route.query.tab = 'not-a-tab'
    await nextTick()
    await nextTick()

    expect(vm.activeTab).toBe('users')
  })
})

// ════════════════════════════════════════════════════════════════════════════
// 懒加载（Requirement 5.6）
// ════════════════════════════════════════════════════════════════════════════

describe('懒加载 — 未激活过的 Tab 其子组件不挂载（Req 5.6）', () => {
  it('初始只挂载 users 的子组件，另两个不在 DOM 里', async () => {
    const { wrapper, vm } = await mountCenter()

    expect(mountedTestids(wrapper)).toEqual(['users'])
    expect(testidCount(wrapper, 'stub-role-scope')).toBe(0)
    expect(testidCount(wrapper, 'stub-user-roles')).toBe(0)
    expect(vm.loaded).toEqual({
      'users': true,
      'role-scope': false,
      'user-roles': false,
    })
  })

  it('切到 role-scope 后它才挂载，user-roles 仍不挂载', async () => {
    const { wrapper } = await mountCenter()

    await clickTab(wrapper, 'role-scope')

    expect(mountedTestids(wrapper)).toEqual(['users', 'role-scope'])
    expect(testidCount(wrapper, 'stub-user-roles')).toBe(0)
  })

  it('已挂载的 Tab 切走后不卸载（切回来不重新请求）', async () => {
    const { wrapper } = await mountCenter()

    await clickTab(wrapper, 'user-roles')
    expect(testidCount(wrapper, 'stub-user-roles')).toBe(1)

    await clickTab(wrapper, 'users')
    // user-roles 已加载过 ⇒ 仍在 DOM 里
    expect(testidCount(wrapper, 'stub-user-roles')).toBe(1)
    expect(mountedTestids(wrapper)).toEqual(['users', 'user-roles'])
  })

  it('带 ?tab=user-roles 直达 ⇒ 只挂载它，users 不挂载', async () => {
    const { wrapper } = await mountCenter({ tab: 'user-roles' })

    // 这条同时防「loaded 初值写成三个都 true」——那样 users 也会在 DOM 里
    expect(mountedTestids(wrapper)).toEqual(['user-roles'])
  })
})

// ════════════════════════════════════════════════════════════════════════════
// 菜单侧（Requirement 5.9）
// ════════════════════════════════════════════════════════════════════════════

describe('菜单侧 — 权限管理项指向 /settings/permissions 且仅 admin 可见（Req 5.9）', () => {
  const layoutSrc = readFileSync(LAYOUT, 'utf-8')

  it('NAV_GROUPS 里存在 key=permissions 的项', () => {
    expect(layoutSrc).toContain("key: 'permissions'")
  })

  it('该项 path 为 /settings/permissions 且 roles 为 [admin]', () => {
    // 取 key: 'permissions' 所在的那一行（NAV_GROUPS 每项单行声明）
    const line = layoutSrc
      .split('\n')
      .find(l => l.includes("key: 'permissions'"))
    expect(line, "找不到 key: 'permissions' 的声明行").toBeTruthy()

    expect(line).toContain("path: '/settings/permissions'")
    expect(line).toContain("roles: ['admin']")
    expect(line).toContain("label: '权限管理'")
  })

  it('旧的 users 菜单项已被取代（不再有指向 /settings/users 的菜单项）', () => {
    // 更名为 permissions 后，菜单里不该再出现旧路径，否则两个入口并存
    expect(layoutSrc).not.toContain("path: '/settings/users'")
  })
})

// ════════════════════════════════════════════════════════════════════════════
// 路由侧（Requirement 5.7、5.8）—— 用真实 router 对象而非解析源码
// ════════════════════════════════════════════════════════════════════════════

describe('路由侧 — 真实 router 对象断言（Req 5.7/5.8）', () => {
  /**
   * 刻意 import 真实 router 而不解析源码：源码里写了一条路由，不等于它
   * 被接进某个 `children` 数组（写在了错误的层级/被注释掉的块里，解析源码
   * 照样能匹配到）。`router.getRoutes()` 给的是**装配后**的结果，且 path
   * 已是父子拼接后的完整路径。
   */
  async function getRoutes(): Promise<any[]> {
    const mod = await import('@/router')
    return (mod.default as any).getRoutes()
  }

  it('反向自检：router 真装配出了路由表', async () => {
    const routes = await getRoutes()
    expect(routes.length).toBeGreaterThan(50)
    // 拿一条与本 spec 无关的既有路由做锚，证明读到的是真实路由表
    expect(routes.map(r => r.name)).toContain('SystemSettings')
  })

  it('settings/permissions 已注册，完整路径为 /settings/permissions', async () => {
    const routes = await getRoutes()
    const pc = routes.find(r => r.name === 'PermissionCenter')

    expect(pc, 'PermissionCenter 路由未注册（写了但没接进 children？）').toBeTruthy()
    expect(pc.path).toBe('/settings/permissions')
    expect(pc.components?.default, '未挂组件').toBeTruthy()
  })

  it('settings/permissions 的 meta.permission 为 admin', async () => {
    const routes = await getRoutes()
    const pc = routes.find(r => r.name === 'PermissionCenter')

    expect(pc.meta?.permission).toBe('admin')
  })

  it('菜单项 path 与已注册路由完整路径一致（防死菜单）', async () => {
    const routes = await getRoutes()
    const paths = new Set(routes.map(r => r.path))

    // 菜单声明的是 /settings/permissions，router 装配后也必须恰是它。
    // 本仓操作日志的完整路径比参考仓多 `admin/` 前缀，照抄那边的 path
    // 就会得到点不开的死菜单 —— 这条守的正是同类问题。
    expect(paths.has('/settings/permissions')).toBe(true)
  })

  it('settings/users 是 redirect 到 PermissionCenter 且带 tab=users', async () => {
    const routes = await getRoutes()
    const um = routes.find(r => r.name === 'UserManagement')

    expect(um, 'settings/users 路由不见了（旧书签会 404）').toBeTruthy()
    expect(um.path).toBe('/settings/users')
    expect(um.redirect, 'settings/users 未配 redirect').toBeTruthy()
    expect(um.redirect).toEqual({ name: 'PermissionCenter', query: { tab: 'users' } })
    // redirect 路由不该再自己挂组件（否则两个宿主并存）
    expect(um.components?.default).toBeFalsy()
  })

  it('redirect 目标名与 PermissionCenter 路由的 name 对得上（防写错名字静默失效）', async () => {
    const routes = await getRoutes()
    const um = routes.find(r => r.name === 'UserManagement')
    const target = (um.redirect as any).name

    expect(routes.map(r => r.name)).toContain(target)
    expect(routes.find(r => r.name === target).path).toBe('/settings/permissions')
  })

  it('源码里 settings/users 已不再直接挂 UserManagement.vue 组件', () => {
    // 当前项目按域拆分路由（domains/system.ts），参考仓直接在 index.ts 内联。
    // 两个文件都搜：settings/users 路由块必须存在且只 redirect、不再挂组件。
    const candidates = [
      ROUTER_SRC,
      resolve(__dirname, '../../router/domains/system.ts'),
    ]
    let block: RegExpMatchArray | null = null
    for (const file of candidates) {
      const src = readFileSync(file, 'utf-8')
      block = src.match(/path: 'settings\/users',[\s\S]{0,220}?\n\s{8}\},/)
      if (block) break
    }

    expect(block, "找不到 settings/users 路由块").toBeTruthy()
    expect(block![0]).toContain('redirect:')
    expect(block![0]).not.toContain("import('@/views/UserManagement.vue')")
  })
})
