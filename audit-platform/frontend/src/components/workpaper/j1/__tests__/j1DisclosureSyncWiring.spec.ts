/**
 * J1 披露 Tab 同步接线守卫 —— 锁死两个**只有浏览器实测才暴露**的缺陷
 *
 * 两者 vitest 单测与 `get_diagnostics` 都查不出（组件不挂载时不会执行到），
 * 故用**读 `.vue` 源码的正则契约**守住，成本低且不会漏。
 *
 * ## 缺陷 1（P0）：`useAuditContext()` 在 async 处理器里调用 → 同步全程失效
 *
 * `useAuditContext()` 内部用 `useRoute()`（`inject`）+ `onScopeDispose()`，
 * **必须在 setup 顶层同步调用**。历史实现写在 `syncToDisclosureNotes()` 里：
 *
 * ```ts
 * const { body } = buildJ1SyncPayload({ ..., year: useAuditContext().year.value })
 * ```
 *
 * 点击时 `inject` 拿不到 route → `route.params` 上 TypeError → 在 `http.post` 之前
 * 就抛错 → **零网络请求**，只弹「同步到附注失败，请重试」。
 * 2026-07-30 浏览器实测确认：该项目 `八、40` 的 `_last_sync_at` 一直是 NULL。
 *
 * ## 缺陷 2：手动同步成功后 `scheduleAutoSync(syncToDisclosureNotes)` = 调度自己
 *
 * 800ms 后重复发同一个 POST（自触发）。实测表现：一次成功同步后用户又收到一条
 * 莫名的「同步到附注失败」。自动同步只应由**数据变更**触发（增删行 / 从明细带入 / AI 写入）。
 *
 * spec: .kiro/specs/j1-disclosure-template-alignment/ Task 10.1（实测追加）
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const CORE = resolve(__dirname, '..', 'core')

const TABS = [
  { name: 'J1TabDisclosureListed.vue', section: '五、40' },
  { name: 'J1TabDisclosureSoe.vue', section: '八、40' },
] as const

function src(file: string): string {
  return readFileSync(resolve(CORE, file), 'utf-8')
}

/**
 * 去掉块注释与行注释。
 *
 * 🔴 必需：本文件的守卫注释本身会提到 `useAuditContext()` / `scheduleAutoSync`，
 * 被守卫的源码里也用注释解释「为什么不能这么写」——不去注释会把说明文字数成真实调用
 * （首版守卫即因此误报）。
 */
function stripComments(code: string): string {
  return code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

/** 取 `<script setup>` 内容（已去注释） */
function scriptBody(file: string): string {
  const m = src(file).match(/<script setup[^>]*>([\s\S]*?)<\/script>/)
  expect(m, `${file} 缺 <script setup>`).toBeTruthy()
  return stripComments(m![1])
}

/** 取某个函数体（按大括号配平截取，容忍嵌套） */
function functionBody(body: string, name: string): string {
  const start = body.search(new RegExp(`(async\\s+)?function\\s+${name}\\s*\\(`))
  expect(start, `未找到函数 ${name}`).toBeGreaterThanOrEqual(0)
  const open = body.indexOf('{', start)
  let depth = 0
  for (let i = open; i < body.length; i += 1) {
    if (body[i] === '{') depth += 1
    else if (body[i] === '}') {
      depth -= 1
      if (depth === 0) return body.slice(open, i + 1)
    }
  }
  throw new Error(`函数 ${name} 大括号不配平`)
}

describe('J1 披露 Tab 同步接线', () => {
  // ── 缺陷 1 ──────────────────────────────────────────────────────────
  it.each(TABS)('$name：useAuditContext() 只在 setup 顶层调用一次', ({ name }) => {
    const body = scriptBody(name)
    const calls = body.match(/useAuditContext\s*\(/g) ?? []
    // import 语句里的名字不带 `(`，所以这里只会数到真实调用
    expect(calls.length, 'useAuditContext 应恰好调用 1 次（setup 顶层）').toBe(1)
  })

  it.each(TABS)('$name：syncToDisclosureNotes 内不得调用 useAuditContext()', ({ name }) => {
    const fn = functionBody(scriptBody(name), 'syncToDisclosureNotes')
    expect(
      fn.includes('useAuditContext'),
      '在 async 处理器里调 useAuditContext() 会因 inject 失效抛 TypeError，' +
        '导致 http.post 从未发出（同步按钮与自动同步全程是死的）',
    ).toBe(false)
  })

  it.each(TABS)('$name：年度取自 setup 顶层解构出的 ref', ({ name }) => {
    const body = scriptBody(name)
    expect(body).toMatch(/const\s*\{\s*year:\s*auditYear\s*\}\s*=\s*useAuditContext\(\)/)
    expect(functionBody(body, 'syncToDisclosureNotes')).toContain('year: auditYear.value')
  })

  // ── 缺陷 2 ──────────────────────────────────────────────────────────
  it.each(TABS)('$name：syncToDisclosureNotes 内不得 scheduleAutoSync（自触发）', ({ name }) => {
    const fn = functionBody(scriptBody(name), 'syncToDisclosureNotes')
    expect(
      fn.includes('scheduleAutoSync'),
      '手动同步成功后再调度自己 → 800ms 后重复 POST，用户会收到莫名的失败提示',
    ).toBe(false)
  })

  it.each(TABS)('$name：自动同步仍由数据变更触发（未把功能整体删掉）', ({ name }) => {
    const body = scriptBody(name)
    const count = (body.match(/scheduleAutoSync\(/g) ?? []).length
    expect(count, '数据变更路径（增删行 / 从明细带入 / AI 写入）仍应触发自动同步').toBeGreaterThanOrEqual(3)
  })

  // ── 其它实测确认过的接线 ────────────────────────────────────────────
  it.each(TABS)('$name：同步按钮与跳转按钮标注正确章节号', ({ name, section }) => {
    const s = src(name)
    expect(s).toContain(`同步到附注（${section}）`)
    expect(s).toContain(`跳转回附注（${section}）`)
  })

  it.each(TABS)('$name：三张表全部走 J1MovementTable（无残留裸 el-table）', ({ name }) => {
    const s = src(name)
    const template = s.match(/<template>([\s\S]*?)\n<\/template>/)![1]
    expect((template.match(/<J1MovementTable/g) ?? []).length).toBe(3)
    expect(template.includes('<el-table'), '披露表模板不应再有裸 el-table').toBe(false)
  })

  it.each(TABS)('$name：挂了勾稽面板与复核触发器', ({ name }) => {
    const s = src(name)
    expect(s).toContain('<J1DisclosureConsistencyPanel')
    expect((s.match(/<GtReviewTrigger/g) ?? []).length).toBeGreaterThanOrEqual(3)
  })

  it.each(TABS)('$name：只读金额走平台单一真源 fmtAmount，不再本地实现 fmtN 逻辑', ({ name }) => {
    const body = scriptBody(name)
    expect(body).toContain('useDisplayPrefsStore')
    expect(body).toContain('displayPrefs.fmtAmount')
    // 历史实现 `if (!v) return '-'` 会把 0 显示成「-」
    expect(body.includes("return '-'")).toBe(false)
  })

  it('国企侧说明拆 3 段且取自 j1NoteSectionMap 单一真源', () => {
    const body = scriptBody('J1TabDisclosureSoe.vue')
    expect(body).toContain('J1_SOE_NOTE_FIELDS')
    expect(body).toContain("j1NoteKeys('soe')")
    expect(body.includes("noteKeys: ['soe']"), '不应再是笼统的单段 soe 键').toBe(false)
  })

  it('上市侧 noteKeys 也取自单一真源', () => {
    const body = scriptBody('J1TabDisclosureListed.vue')
    expect(body).toContain("j1NoteKeys('listed')")
    expect(body).toContain('J1_LISTED_NOTE_FIELDS')
  })

  it('上市侧辞退福利提示取源模板 R54 原文口径（非自造）', () => {
    const s = src('J1TabDisclosureListed.vue')
    expect(s).toContain('支付给职工以及为职工支付的现金')
    expect(
      s.includes('不得超过期初数加本期增加数之和'),
      '这是历史自造内容，源模板要求的是与现金流量表一致',
    ).toBe(false)
  })
})

/**
 * 只读金额格式化单一真源守卫（spec Task 16.1）
 *
 * 披露表的单元格实际由共用子组件渲染（`J1MovementTable` 三张变动表 /
 * `J1DisclosureConsistencyPanel` 勾稽明细），**两个 Tab 自身的 `fmtAmount` 断言覆盖不到它们**
 * —— 谁在子组件里重新写一个本地 `fmtN()`，Tab 侧守卫依然全绿。
 *
 * 平台铁律：金额格式单一真源 = `stores/displayPrefs.ts` 的 `fmtAmount()`
 * （千分符 + 小数位 + 单位偏好「元」+ localStorage 持久化）。
 * 本地实现的典型症状是 `if (!v) return '-'`（把 0 显示成「-」）与直接
 * `toLocaleString('zh-CN', { minimumFractionDigits: 2 })`（绕过单位偏好）。
 */
describe('J1 披露只读金额格式化', () => {
  /** 渲染只读金额的全部披露侧组件（两个 Tab + 两个共用子组件） */
  const AMOUNT_RENDERERS = [
    'J1TabDisclosureListed.vue',
    'J1TabDisclosureSoe.vue',
    'J1MovementTable.vue',
    'J1DisclosureConsistencyPanel.vue',
  ] as const

  it.each(AMOUNT_RENDERERS)('%s：只读金额走 displayPrefs.fmtAmount', (name) => {
    const body = scriptBody(name)
    expect(body, '未接平台 store').toContain('useDisplayPrefsStore')
    expect(body, '未调用单一真源 fmtAmount').toContain('displayPrefs.fmtAmount')
  })

  it.each(AMOUNT_RENDERERS)('%s：不得本地实现金额格式化', (name) => {
    const body = scriptBody(name)
    expect(
      body.includes('toLocaleString'),
      '直接 toLocaleString 会绕过「元/千元/万元」单位偏好与小数位偏好',
    ).toBe(false)
    expect(
      body.includes('minimumFractionDigits'),
      '小数位应由 displayPrefs.decimals 决定，不得在组件内写死',
    ).toBe(false)
    expect(
      body.includes("return '-'"),
      "本地 `if (!v) return '-'` 会把 0 显示成「-」（0 与「无数据」不可混同）",
    ).toBe(false)
  })

  it('两个 Tab 的 fmtN 只是 fmtAmount 的转发壳（非另一套实现）', () => {
    for (const name of ['J1TabDisclosureListed.vue', 'J1TabDisclosureSoe.vue']) {
      const fn = functionBody(scriptBody(name), 'fmtN')
      expect(fn, `${name} 的 fmtN 应直接转发 displayPrefs.fmtAmount`).toContain('displayPrefs.fmtAmount')
    }
  })

  it('自检：断言不空转（正则确实能抽到脚本体）', () => {
    for (const name of AMOUNT_RENDERERS) {
      expect(scriptBody(name).length, `${name} 脚本体为空说明正则失效`).toBeGreaterThan(200)
    }
  })
})

/**
 * 可编辑金额控件守卫（spec Task 16.3）
 *
 * 平台铁律（双证）：element-plus **2.13.6** 的 `el-input-number` 编译产物里
 * 不存在 `formatter`/`parser` prop（`es/components/input-number/**` 全文无此实现），
 * 挂 `:formatter` 是未知属性 = 空操作；浏览器实测输 1234567.5 显示 `1234567.50`
 * （**无千分符**），换 `el-input` 后才是 `1,234,567.50`。
 * → 可编辑金额一律用 `components/workpaper/shared/WpAmountInput.vue`
 * （失焦千分符 / 聚焦原始值 / 粘贴带逗号可解析 / 非法输入回退不写 NaN）。
 *
 * 🔴 为什么必须是"源码正则守卫"：批量替换极易漏 —— 同一组件里金额控件有多种写法
 * （单行 vs 多行属性、`v-model` vs `:model-value`+`@change`），正则只命中一部分；
 * 漏掉的那些**录入完全无反应且不触发自动同步**，而 `get_diagnostics` 与挂载型单测
 * 都查不出（2026-07-30 K3 实测踩中）。
 *
 * 反向边界同样重要：`WpAmountInput` **绝不能**套到利率 / 汇率 / 比例 / 笔数 /
 * 年度 / 月份 / 文本说明上。J1 披露侧的非金额可编辑字段有两类：
 * 项目名称（`el-input` 文本）与三段说明（`el-input type="textarea"`）。
 */
describe('J1 披露可编辑金额控件', () => {
  /** 披露侧全部渲染可编辑单元格的组件（两个 Tab + 共用子组件） */
  const DISCLOSURE_FILES = [
    'J1TabDisclosureListed.vue',
    'J1TabDisclosureSoe.vue',
    'J1MovementTable.vue',
    'J1DisclosureConsistencyPanel.vue',
  ] as const

  /**
   * 整份 SFC（含 template / style）去注释。
   *
   * 🔴 必需：被守卫的源码会在注释里写明「为什么不能用 el-input-number」，
   * 不去注释会把说明文字数成真实用法（本文件前半段同款坑）。
   */
  function sfcWithoutComments(file: string): string {
    return stripComments(src(file))
  }

  it.each(DISCLOSURE_FILES)('%s：0 处 el-input-number', (name) => {
    const code = sfcWithoutComments(name)
    const hits = code.match(/el-input-number/g) ?? []
    expect(
      hits.length,
      'el-input-number 在 EP 2.13.6 没有 formatter/parser，千分符从未生效；' +
        '可编辑金额必须换 WpAmountInput（含 <style> 里的残留选择器一并清理）',
    ).toBe(0)
  })

  it('J1MovementTable 的四个金额列走 WpAmountInput', () => {
    const code = sfcWithoutComments('J1MovementTable.vue')
    const template = code.match(/<template>([\s\S]*?)\n<\/template>/)![1]
    expect((template.match(/<WpAmountInput/g) ?? []).length, '金额单元格应恰好 1 处（四列共用同一模板）').toBe(1)
    // 保住持久化/自动同步接线：v-model 回写 + @change 冒泡 row-change
    expect(template).toMatch(/<WpAmountInput[\s\S]*?v-model="row\[col\.key\]"/)
    expect(template).toMatch(/<WpAmountInput[\s\S]*?@change="emit\('row-change', row\)"/)
    expect(sfcWithoutComments('J1MovementTable.vue')).toContain("import WpAmountInput from '../../shared/WpAmountInput.vue'")
  })

  it('反向边界：非金额字段不得改成 WpAmountInput', () => {
    // 项目名称是文本（`el-input` + v-model="row.label"）
    const movement = sfcWithoutComments('J1MovementTable.vue')
    expect(movement).toMatch(/<el-input\b[\s\S]*?v-model="row\.label"/)
    // 说明段是 textarea，且必须留在 el-input 上。
    // 两个 Tab 的写法不同（上市 3 处单行属性直写 / 国企 1 处多行属性 + v-for 遍历字段定义）
    // —— 正是"同一控件多种写法"的现场，所以正则要容忍换行、断言按渲染点而非段数。
    for (const tab of ['J1TabDisclosureListed.vue', 'J1TabDisclosureSoe.vue'] as const) {
      const code = sfcWithoutComments(tab)
      const textareas = code.match(/<el-input\s[^>]*?type="textarea"/gs) ?? []
      expect(textareas.length, `${tab} 说明段应为 el-input textarea`).toBeGreaterThanOrEqual(1)
      expect(code, `${tab} 说明段应绑 notes（非金额）`).toMatch(/type="textarea"[\s\S]{0,200}v-model="notes/)
      expect((code.match(/<WpAmountInput/g) ?? []).length, `${tab} 自身模板不直接渲染金额格`).toBe(0)
    }
  })

  it('自检：断言不空转（去注释后仍能读到 template）', () => {
    for (const name of DISCLOSURE_FILES) {
      const code = sfcWithoutComments(name)
      expect(code.length, `${name} 去注释后为空说明正则失效`).toBeGreaterThan(200)
      expect(code, `${name} 缺 template`).toContain('<template>')
    }
    // 反向自检：未处理注释时 J1MovementTable 的说明块本会命中 el-input-number
    expect(src('J1MovementTable.vue')).toContain('el-input-number')
  })
})
