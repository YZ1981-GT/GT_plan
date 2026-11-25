/**
 * 模块级常量字面量解析（x3 探针的键解析底座）。
 *
 * 从 x3KeyProbe.ts 抽出的伴生模块：该文件已超过 1500 行门禁，新增能力不再往里加。
 * 零内部依赖（只用字符串与正则），x3KeyProbe 反向 import 并 re-export，外部调用方不变。
 */

/** 别名链最大深度（`const A = B; const B = C; const C = '字面量'` 共 3 跳）。 */
const MAX_CONST_ALIAS_HOPS = 4

/**
 * 取模块级 `const NAME = '字面量'`（同时兼容 `export const`）。
 *
 * 🔴 支持**标识符别名链** `const NAME = OTHER`（再解析 OTHER）：K13 把单一真源键导出为
 * `export const K13_ADJ_ITEM_KEY = 'K13-3-adj-entries'` 供真双向桥共用，composable 内再
 * `const ITEM_KEY = K13_ADJ_ITEM_KEY` 取别名（`d97ff2f0d`，2026-10-01）。只认字面量赋值
 * 会让别名后的写入点（`debouncedSave(ITEM_KEY, { remark })`）键解析为 null ⇒ 实测 0 列，
 * 把「重构出单一真源」误判成「找不到写入列」。
 *
 * 判据没有放宽：别名链最终**必须落到一个字面量**，否则仍返回 null；深度上限 + 访问集
 * 防环（`const A = B; const B = A` 不会死循环）。
 */
export function resolveConstLiteral(src: string, name: string): string | null {
  const seen = new Set<string>()
  let cur = name
  for (let hop = 0; hop <= MAX_CONST_ALIAS_HOPS; hop += 1) {
    if (seen.has(cur)) return null
    seen.add(cur)
    const decl = `(?:export\\s+)?(?:const|let|var)\\s+${cur.replace(/[$]/g, '\\$')}\\s*=\\s*`
    const lit = src.match(new RegExp(`${decl}['"\`]([^'"\`]*)['"\`]`))
    if (lit) return lit[1]
    const alias = src.match(new RegExp(`${decl}([A-Za-z_$][\\w$]*)\\s*(?:[;\\n]|$)`))
    if (!alias) return null
    cur = alias[1]
  }
  return null
}
