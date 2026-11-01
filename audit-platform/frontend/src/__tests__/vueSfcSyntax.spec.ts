/**
 * 全仓 .vue 单文件组件语法守卫（模板属性名 + script 可解析）
 *
 * 缘由（2026-09-29 实测，均为批量改线脚本 / 注释写法造成，且都绕过了现有检查）：
 *  1. 模板：`<GtEntrySyncCapabilityNotice … />` 被插进多行开标签 `<el-segmented` / `<el-tooltip`
 *     的**属性区中间**（5 个 A 类底稿组件整页渲染失败）。Vue 编译器不报错 —— 新分词器把
 *     `<GtEntrySyncCapabilityNotice` 当成属性名收下，只有运行时 `setAttribute` 抛
 *     `InvalidCharacterError`。同一判据还扫出老缺陷：属性值里的中文说明用了半角双引号，
 *     把属性提前截断（ManagementLetterPanel 的结转说明一直只显示前半句）。
 *  2. script：`import { …, toRef, toRef } from 'vue'`（重复绑定，5 个）、
 *     `import { useXxx }` 与下一条 import 粘连（9 个 M 类底稿）、块注释里写 `/rows/*` + `/rowUuid`
 *     让星号斜杠提前闭合注释（B60 工时面板，已在 HEAD）—— 都是 SyntaxError，`vite build` 必失败，
 *     懒加载组件在 dev 下只有打开那一页才报错，所以长期无人发现。
 *
 *  3. 模板：改线把 `<GtOnlyOfficeSheet v-else-if="ooReady">` 换成 `<template v-else>…</template>`，
 *     其后原有的 `<div v-else>`（生成失败提示）随即悬空 ⇒ 模板编译错误（A171 / A177）。
 *
 * 判据：
 *  - SFC 块级解析无错误（孤立 `</script>`、重复块 …）；
 *  - 模板 AST 中每个**静态属性**名都是合法 HTML 属性名（不含空白、引号、`<`、`>`、`/`、`=`）；
 *    指令（`v-*` / `:` / `@` / `#`）的名字由编译器解析，不在此列；
 *  - `compileTemplate` 无错误（悬空 v-else、未闭合标签、非法指令表达式 …）；
 *  - 每个 `<script>` / `<script setup>` 块都能被 babel 解析（与 @vitejs/plugin-vue 同一解析器）；
 *  - **`.ts` 模块同样解析**，且没有写在非 async 函数里的 await（见 `awaitOutsideAsyncProblems`）。
 * 不查「用了 vue API 却没 import」：应用里由 unplugin-auto-import 注入，只有 vitest 环境会缺。
 *
 *  4. 2026-10-31：把剪贴板调用换成 `await copyText(…)` / `await copyRichText(…)` 时没给函数加 async（18 个文件
 *     22 处），另有 5 个 `.ts` 被批量替换弄坏模板字面量（`return newUuid()}-${…}\``）。本判据原先两头都漏：
 *     解析脚本块时开着 `allowAwaitOutsideFunction`（为了放行 `<script setup>` 顶层 await，顺带放过了同步函数里的
 *     await），而 `.ts` 根本不在扫描范围 —— 附注编辑器 / 试算表 / 合并入口 / 合并附注 Tab / 查账穿透整页打不开。
 */
import { describe, it, expect } from 'vitest'
import { babelParse, compileTemplate, parse } from 'vue/compiler-sfc'
import { relative, resolve } from 'node:path'
import { readSource, walkSourceFiles } from './_helpers/frontendSourceScan'

const SRC = resolve(__dirname, '..')

/**
 * 非 async 函数体里的 `await`（spec note-table-structure-formula-pull-closure；2026-10-31 实测 18 个文件 22 处，
 * 整份 SFC / 模块编译失败 ⇒ 附注编辑器、试算表、合并入口、合并附注 Tab、查账穿透全部打不开）。
 *
 * 为什么原来的 `babelParse` 抓不到：解析脚本块时传了 `allowAwaitOutsideFunction: true`（`<script setup>` 顶层
 * await 是合法的，不传会把合法写法判成坏的），这个开关同时也放过了「同步函数里 await」。所以解析照旧要开着它，
 * 再走一遍 AST 判定：每个 AwaitExpression 的最近一层函数必须是 async（顶层 await 仍放行）。
 */
function awaitOutsideAsyncProblems(ast: any, filename: string, startLine: number): string[] {
  const found: string[] = []
  const FUNCTION_TYPES = new Set([
    'FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression', 'ObjectMethod', 'ClassMethod',
    'ClassPrivateMethod',
  ])
  const walk = (node: any, asyncDepth: number, inFunction: boolean): void => {
    if (!node || typeof node !== 'object') return
    if (Array.isArray(node)) {
      for (const item of node) walk(item, asyncDepth, inFunction)
      return
    }
    if (typeof node.type !== 'string') return
    if (node.type === 'AwaitExpression' && inFunction && asyncDepth === 0) {
      found.push(`${filename}:${startLine + (node.loc?.start.line ?? 1) - 1} await 写在非 async 函数里`
        + '（整份文件编译失败）')
    }
    const isFunction = FUNCTION_TYPES.has(node.type)
    const nextAsync = isFunction ? (node.async ? 1 : 0) : asyncDepth
    const nextInFunction = inFunction || isFunction
    for (const key of Object.keys(node)) {
      if (key === 'loc' || key === 'leadingComments' || key === 'trailingComments') continue
      walk(node[key], nextAsync, nextInFunction)
    }
  }
  walk(ast.program ?? ast, 0, false)
  return found
}

/** 一个脚本 / 模块的语法问题：解析失败 + 非 async 函数里的 await。``.ts`` 与 SFC 脚本块共用。 */
export function scriptSyntaxProblems(code: string, filename: string, ts: boolean, startLine = 1): string[] {
  let ast: any
  try {
    ast = babelParse(code, {
      sourceType: 'module',
      plugins: ts ? ['typescript'] : [],
      allowAwaitOutsideFunction: true,  // `<script setup>` 顶层 await 合法；函数内的由下面逐个判
    })
  } catch (e: any) {
    const line = startLine + (e?.loc?.line ?? 1) - 1
    return [`${filename}:${line} script 无法解析：${String(e?.message ?? e).split('\n')[0]}`]
  }
  return awaitOutsideAsyncProblems(ast, filename, startLine)
}
/** HTML「属性名」状态里遇到这些字符即为非法（DOM setAttribute 同样拒绝） */
const INVALID_ATTR_CHAR = /[\s"'<>/=]/
const NODE_ELEMENT = 1
const PROP_ATTRIBUTE = 6

export function sfcSyntaxProblems(source: string, filename: string): string[] {
  const { descriptor, errors } = parse(source, { filename })
  const found: string[] = errors.map((e) => `${filename} SFC 解析错误：${e.message}`)

  const stack: any[] = descriptor.template?.ast ? [descriptor.template.ast] : []
  while (stack.length) {
    const node = stack.pop()
    if (node.type === NODE_ELEMENT) {
      for (const prop of node.props ?? []) {
        if (prop.type === PROP_ATTRIBUTE && INVALID_ATTR_CHAR.test(prop.name)) {
          found.push(`${filename}:${prop.loc.start.line} <${node.tag}> 非法属性名 ${JSON.stringify(prop.name)}`)
        }
      }
    }
    for (const child of node.children ?? []) stack.push(child)
  }

  // 模板编译错误（悬空 v-else / 未闭合标签 / 非法指令表达式 …）只有 compileTemplate 才报
  if (descriptor.template) {
    const compiled = compileTemplate({
      source: descriptor.template.content,
      filename,
      id: 'sfc-syntax-guard',
      compilerOptions: { isTS: descriptor.scriptSetup?.lang === 'ts' || descriptor.script?.lang === 'ts' },
    })
    for (const err of compiled.errors) {
      const msg = typeof err === 'string' ? err : err.message
      const rel = typeof err === 'string' ? 1 : (err.loc?.start.line ?? 1)
      found.push(`${filename}:${descriptor.template.loc.start.line + rel - 1} 模板编译错误：${msg.split('\n')[0]}`)
    }
  }

  for (const block of [descriptor.script, descriptor.scriptSetup]) {
    if (!block) continue
    const ts = block.lang === 'ts' || block.lang === 'tsx'
    found.push(...scriptSyntaxProblems(block.content, filename, ts, block.loc.start.line))
  }
  return found
}

describe('vue 单文件组件语法', () => {
  it('判据识别全部已知坏形态（变异自检：否则全仓扫描为空也可能是判据失效）', () => {
    const cases: Record<string, string> = {
      tagInsideTag: `<template><div>
  <el-segmented
  <GtEntrySyncCapabilityNotice entry-id="x" />
    v-model="mode"
  />
</div></template>`,
      halfWidthQuotes: `<template><el-alert description="只结转状态不为"已解决"的事项" /></template>`,
      duplicateImport: `<script setup lang="ts">\nimport { ref, toRef, toRef } from 'vue'\n</script>`,
      gluedImports: `<script setup lang="ts">\nimport { useA }\nimport B from './B.vue' from './useA'\n</script>`,
      commentClosedEarly: `<script setup lang="ts">\n/**\n * 指针 \`/rows/*/rowUuid\`\n */\nconst a = 1\n</script>`,
      // 2026-10-31：把 `navigator.clipboard.writeText(x)` 换成 `await copyText(x)` 时没给函数加 async
      awaitInSyncFunction: `<script setup lang="ts">\nfunction onCopy() {\n  await copyText('x')\n}\n</script>`,
      // 改线把 `<X v-else-if="ooReady">` 换成 `<template v-else>…</template>`，后面的 `v-else` 就悬空了
      danglingElse: `<template><div>
  <p v-if="a">1</p>
  <template v-else><span>2</span></template>
  <p v-else>3</p>
</div></template>`,
    }
    for (const [name, source] of Object.entries(cases)) {
      expect(sfcSyntaxProblems(source, `${name}.vue`), name).not.toEqual([])
    }
    const ok = `<template><el-segmented v-model="mode" size="small" /><GtEntrySyncCapabilityNotice entry-id="x" /></template>
<script setup lang="ts">
/** 指针 \`/rows/*\\/rowUuid\` */
import { ref, toRef } from 'vue'
import B from './B.vue'
const mode = ref('a')
// script setup 顶层 await 合法；async 函数 / 异步箭头函数里的 await 也合法
const data = await Promise.resolve(1)
async function load() { await Promise.resolve(data) }
const save = async () => { await load() }
</script>`
    expect(sfcSyntaxProblems(ok, 'Ok.vue')).toEqual([])
  })

  it('判据识别 .ts 模块里的坏形态（原先只扫 .vue，5 个 .ts 的语法错误长期无人看见）', () => {
    expect(scriptSyntaxProblems("function f() { await g() }\n", 'bad.ts', true)).toHaveLength(1)
    // 模板字面量被批量替换弄坏（`return newUuid()}-${...}\``）
    expect(scriptSyntaxProblems('function id() {\n  return newUuid()}-${x}`\n}\n', 'broken.ts', true)).toHaveLength(1)
    expect(scriptSyntaxProblems(
      'async function f() { await g() }\nconst h = async () => { await f() }\nfunction s() { return 1 }\n',
      'ok.ts', true)).toEqual([])
    // 非 async 外层 + 内层 async：内层的 await 合法，不能误报
    expect(scriptSyntaxProblems('function outer() {\n  void (async () => { await g() })()\n}\n', 'nested.ts', true))
      .toEqual([])
  })

  it('src 下全部 .ts 可解析、且没有写在非 async 函数里的 await', () => {
    const files = walkSourceFiles(SRC).filter((f) => /\.tsx?$/.test(f))
    expect(files.length).toBeGreaterThan(500)  // 防空转：范围失效时不许恒绿
    const problems = files.flatMap((f) => scriptSyntaxProblems(readSource(f), relative(SRC, f), true))
    expect(problems).toEqual([])
  }, 120000)

  it('src 下全部 .vue 通过（模板属性名合法 + script 可解析）', () => {
    const files = walkSourceFiles(SRC).filter((f) => f.endsWith('.vue'))
    // 防空转：扫描范围失效（路径错 / 过滤过严）时不能恒绿
    expect(files.length).toBeGreaterThan(1000)
    const problems = files.flatMap((f) => sfcSyntaxProblems(readSource(f), relative(SRC, f)))
    expect(problems).toEqual([])
  }, 120000)
})
