/**
 * 模板普通属性里不许写 `${...}`（spec voucher-identity-writeback-and-audit-phase 任务 11 / 12）
 *
 * 缘由：`title="⚡ 抽凭引擎（科目 ${samplingAccountCode} 固定资产-增加）"` 是普通属性，页面原样显示字面量
 * `${samplingAccountCode}`；任务 11 / 12 在 D、F、G、H、I 循环的抽凭弹窗里改了 16 处，此前没有任何检查发现。
 * 判据走模板 AST：只看静态属性（type 6），指令（`:x` / `v-*` / `@x` / `#x`）的值是表达式，不在此列。
 */
import { describe, it, expect } from 'vitest'
import { parse } from 'vue/compiler-sfc'
import { relative, resolve } from 'node:path'
import { readSource, walkSourceFiles } from './_helpers/frontendSourceScan'

const SRC = resolve(__dirname, '..')
const NODE_ELEMENT = 1
const PROP_ATTRIBUTE = 6

export function staticInterpolations(source: string, filename: string): string[] {
  const { descriptor } = parse(source, { filename })
  const found: string[] = []
  const stack: any[] = descriptor.template?.ast ? [descriptor.template.ast] : []
  while (stack.length) {
    const node = stack.pop()
    if (node.type === NODE_ELEMENT) {
      for (const prop of node.props ?? []) {
        const value: string = prop.type === PROP_ATTRIBUTE ? (prop.value?.content ?? '') : ''
        if (value.includes('${')) found.push(`${filename}:${prop.loc.start.line} <${node.tag}> ${prop.name}="${value}"`)
      }
    }
    for (const child of node.children ?? []) stack.push(child)
  }
  return found
}

describe('模板普通属性不写 ${...}', () => {
  it('判据自检：普通属性里的插值报出，绑定属性 / 指令里的模板串不报', () => {
    const bad = '<template><el-dialog title="抽凭引擎（科目 ${code} 增加）" /></template>'
    expect(staticInterpolations(bad, 'Bad.vue')).toEqual(['Bad.vue:1 <el-dialog> title="抽凭引擎（科目 ${code} 增加）"'])
    const ok = '<template><el-dialog :title="`抽凭引擎（科目 ${code} 增加）`" v-if="k === `${a}:b`" /></template>'
    expect(staticInterpolations(ok, 'Ok.vue')).toEqual([])
  })

  it('src 下全部 .vue 没有这种写法', () => {
    const files = walkSourceFiles(SRC).filter(f => f.endsWith('.vue'))
    // 防空转：扫描范围失效（路径错 / 过滤过严）时不能恒绿
    expect(files.length).toBeGreaterThan(1000)
    expect(files.flatMap(f => staticInterpolations(readSource(f), relative(SRC, f)))).toEqual([])
  }, 120000)
})
