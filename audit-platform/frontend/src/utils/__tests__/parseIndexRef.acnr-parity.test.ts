/**
 * parseIndexRef ACNR 契约（parity）测试 — task 15.2 / Req 13.3
 *
 * 断言两个索引解析器在 11 个命名空间上「分类等价」：
 *   - 权威文法：services/acnr/resolveUri.ts::parseIndexRef（canonical，返回 {namespace,target}）
 *   - display 层：utils/parseIndexRef.ts::parseIndexRef（超集，返回 {ns,layer,target,...}）
 *
 * 等价性定义：对同一个 canonical `<ns>:<target>` 输入，
 *   utilsResult.ns === acnrResult.namespace  且  utilsResult.target === acnrResult.target
 *
 * 该测试守卫两文法不漂移（例如某侧新增/删除命名空间、target 提取规则不一致）。
 *
 * Validates: Requirements 13.3
 */

import { describe, it, expect } from 'vitest'
import {
  parseIndexRef as utilsParseIndexRef,
  isValidNamespace,
  NAMESPACE_LAYER_MAP,
  type Namespace,
} from '../parseIndexRef'
import { parseIndexRef as acnrParseIndexRef } from '@/services/acnr/resolveUri'

/** ACNR 规范的 11 个命名空间（canonical 大小写形式，与 resolveUri.ts 的 RE_INDEX_REF 一致） */
const CANONICAL_NAMESPACES: Namespace[] = [
  'wp',
  'sheet',
  'cell',
  'TB',
  'Note',
  'Adj',
  'Att',
  'EQCR',
  'Calc',
  'Sample',
  'Confirm',
]

/**
 * 每个命名空间的代表性 target（含中文、cell 引用、编码、UUID 等真实形态），
 * 覆盖两解析器在 target 提取上的边界。
 */
const TARGET_BY_NAMESPACE: Record<Namespace, string> = {
  wp: 'D2',
  sheet: 'D2-1',
  cell: 'D2-1!B23',
  TB: '1122',
  Note: '五-1-1',
  Adj: 'AJE-001',
  Att: 'UUID-123',
  EQCR: 'RID',
  Calc: 'depreciation',
  Sample: 'F2-VAL',
  Confirm: 'D0-001',
}

describe('parseIndexRef ACNR parity — 11 命名空间分类等价', () => {
  it('两解析器覆盖完全相同的 11 个命名空间集合', () => {
    // 数量一致
    expect(CANONICAL_NAMESPACES).toHaveLength(11)

    // utils 侧承认全部 11 个命名空间
    for (const ns of CANONICAL_NAMESPACES) {
      expect(isValidNamespace(ns)).toBe(true)
    }

    // ACNR 侧承认全部 11 个命名空间（strict 语法可解析）
    for (const ns of CANONICAL_NAMESPACES) {
      const acnr = acnrParseIndexRef(`${ns}:x`)
      expect(acnr).not.toBeNull()
      expect(acnr?.namespace).toBe(ns)
    }
  })

  it.each(CANONICAL_NAMESPACES)('命名空间 %s：ns/target 提取等价', (ns) => {
    const target = TARGET_BY_NAMESPACE[ns]
    const input = `${ns}:${target}`

    const acnr = acnrParseIndexRef(input)
    const utils = utilsParseIndexRef(input)

    // 两侧都能解析
    expect(acnr).not.toBeNull()
    expect(utils).not.toBeNull()

    // 分类等价：命名空间一致
    expect(utils?.ns).toBe(acnr?.namespace)
    // target 提取等价
    expect(utils?.target).toBe(acnr?.target)
  })

  it('utils layer 分类与 canonical 命名空间自洽（cell→1, sheet→2, wp→3, module→4）', () => {
    for (const ns of CANONICAL_NAMESPACES) {
      const utils = utilsParseIndexRef(`${ns}:${TARGET_BY_NAMESPACE[ns]}`)
      expect(utils?.layer).toBe(NAMESPACE_LAYER_MAP[ns])
    }
  })

  it('非法命名空间：两解析器一致返回 null', () => {
    for (const bad of ['invalid:target', 'foo:bar', 'xyz:1', 'index:D2']) {
      expect(acnrParseIndexRef(bad)).toBeNull()
      expect(utilsParseIndexRef(bad)).toBeNull()
    }
  })

  it('空输入：两解析器一致返回 null', () => {
    expect(acnrParseIndexRef('')).toBeNull()
    expect(utilsParseIndexRef('')).toBeNull()
  })

  it('中文 target 提取等价（Note 域）', () => {
    const input = 'Note:五、(1)货币资金'
    const acnr = acnrParseIndexRef(input)
    const utils = utilsParseIndexRef(input)
    expect(utils?.ns).toBe(acnr?.namespace)
    expect(utils?.target).toBe(acnr?.target)
    expect(utils?.target).toBe('五、(1)货币资金')
  })
})
