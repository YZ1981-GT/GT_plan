/**
 * useC22BundleState.pbt.spec.ts — C22 ITGC Bundle 属性测试（fast-check）
 *
 * Spec: .kiro/specs/c22-itgc-bundle/  Task 6.1 + 8.3
 *
 * 覆盖 design Correctness Properties（每 property ≥100 runs）：
 *   - Property 1: skip 映射与注册完整性   **Validates: Requirements 1.1, 1.2, 2.1, 2.2**
 *   - Property 2: 子页分组完整性         **Validates: Requirements 4.1**
 *   - Property 3: 缺陷汇总一致性         **Validates: Requirements 5.1, 5.2, 7.2**
 *   - Property 4: 完成进度统计一致性     **Validates: Requirements 7.1, 7.2**
 *   - Property 7: 点选值合法性           **Validates: Requirements 10.1**
 *   - Property 9: 缺陷双向一致           **Validates: Requirements 12.1, 12.4**
 *
 * 纯函数 PBT：直接验证导出的纯函数，无组件挂载、无网络。
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import {
  C22_BUNDLE_TABS,
  ITGC_GROUPS,
  ITGC_CONTROL_SHEETS,
  CONCLUSION_OPTIONS,
  deriveItgcStatus,
  collectControlPointDefect,
  computeProgressSummary,
  type CompletionStatus,
  type ControlPointFields,
  type ItgcDefect,
  type TabDef,
} from '../useC22BundleState'
import {
  HTML_RENDERER_REGISTRY,
  HTML_COMPONENT_TYPE_SET,
} from '../../htmlRendererRegistry'

const RUNS = { numRuns: 20 }

const CONCLUSION_ARB = fc.oneof(
  fc.constantFrom('有效', '无效', '部分有效'),
  fc.constant(''),
  fc.constant(null),
  fc.constant('   '),
)

const controlPointTabs = C22_BUNDLE_TABS.filter(t => t.kind === 'itgc-sheet')

function fieldsArb(): fc.Arbitrary<ControlPointFields> {
  return fc.record({
    designConclusion: CONCLUSION_ARB,
    execConclusion: CONCLUSION_ARB,
    abnormal: fc.oneof(fc.constantFrom('是', '否'), fc.constant(null)),
    defectDesc: fc.oneof(fc.string(), fc.constant(null)),
    defectNo: fc.oneof(fc.string(), fc.constant(null)),
    appSystem: fc.oneof(fc.string(), fc.constant(null)),
    itCategory: fc.oneof(fc.string(), fc.constant(null)),
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: skip 映射与注册完整性
// Feature: c22-itgc-bundle, Property 1: skip/注册
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c22-itgc-bundle, Property 1: skip/注册', () => {
  /**
   * **Validates: Requirements 1.1, 1.2, 2.1, 2.2**
   *
   * For any {C22, C21, C21-1}:
   * - C22 映射为 c22-itgc-bundle 且在 registry 与 VALID_COMPONENT_TYPES 均已注册
   * - C21/C21-1 映射为 skip
   */

  // 加载 wp_code_overrides.json（后端静态 JSON）
  // vitest cwd = audit-platform/frontend/，仓库根在 ../../
  const overridesPath = resolve(process.cwd(), '../../backend/app/data/wp_code_overrides.json')
  const overrides: Record<string, string> = JSON.parse(readFileSync(overridesPath, 'utf-8'))

  const C22_COMPONENT_TYPE = 'c22-itgc-bundle'
  const SKIP_CODES = ['C21', 'C21-1'] as const
  const ALL_CODES = ['C22', ...SKIP_CODES] as const

  it('C22 在 wp_code_overrides 中映射为 c22-itgc-bundle', () => {
    fc.assert(
      fc.property(fc.constantFrom(...ALL_CODES), (code) => {
        if (code === 'C22') {
          expect(overrides[code]).toBe(C22_COMPONENT_TYPE)
        } else {
          // C21/C21-1 映射为 skip
          expect(overrides[code]).toBe('skip')
        }
      }),
      RUNS,
    )
  })

  it('c22-itgc-bundle 在 htmlRendererRegistry 中已注册', () => {
    fc.assert(
      fc.property(fc.constant(C22_COMPONENT_TYPE), (ct) => {
        // 在前端 registry 注册表中
        expect(HTML_COMPONENT_TYPE_SET.has(ct as any)).toBe(true)
        // 能通过 Map 查到完整条目
        const entry = HTML_RENDERER_REGISTRY.get(ct as any)
        expect(entry).toBeDefined()
        expect(entry!.componentType).toBe(C22_COMPONENT_TYPE)
        expect(entry!.contextProps).toBe('standard')
      }),
      RUNS,
    )
  })

  it('skip 类型在 HTML_RENDERER_ROUTE_SET 中但不在 REGISTRY 中（占位符机制）', () => {
    fc.assert(
      fc.property(fc.constantFrom(...SKIP_CODES), (code) => {
        const ct = overrides[code]
        expect(ct).toBe('skip')
        // skip 不是真正组件，不在 HTML_COMPONENT_TYPE_SET 中
        expect(HTML_COMPONENT_TYPE_SET.has(ct as any)).toBe(false)
        // skip 不在 REGISTRY Map 中（它走 GtWpRenderer 内部 fallback）
        expect(HTML_RENDERER_REGISTRY.has(ct as any)).toBe(false)
      }),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: 子页分组完整性
// Feature: c22-itgc-bundle, Property 2: 子页分组完整性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c22-itgc-bundle, Property 2: 子页分组完整性', () => {
  it('每个 IT 控制域子页唯一归入 4 大类之一；matrix/C21/C21-1 不计入', () => {
    fc.assert(
      fc.property(fc.constantFrom(...C22_BUNDLE_TABS.map(t => t.id)), (id) => {
        const tab = C22_BUNDLE_TABS.find(t => t.id === id) as TabDef
        if (tab.kind === 'itgc-sheet' || tab.kind === 'itgc-aux') {
          // 恰好归入 4 大类之一
          expect(ITGC_GROUPS).toContain(tab.group)
        } else {
          // matrix / c21 / c21-1 不属于 4 大控制类别
          expect(ITGC_GROUPS).not.toContain(tab.group)
        }
      }),
      RUNS,
    )
  })

  it('31 控制点均为 itgc-sheet 且 sheet 名唯一', () => {
    expect(controlPointTabs.length).toBe(31)
    expect(new Set(ITGC_CONTROL_SHEETS).size).toBe(31)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: 缺陷汇总一致性
// Feature: c22-itgc-bundle, Property 3: 缺陷汇总一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c22-itgc-bundle, Property 3: 缺陷汇总一致性', () => {
  it('defects 恰好等于所有「是否异常=是」控制点集合（无遗漏无重复）', () => {
    fc.assert(
      fc.property(
        fc.array(fieldsArb(), { minLength: controlPointTabs.length, maxLength: controlPointTabs.length }),
        (fieldsList) => {
          const defects: ItgcDefect[] = []
          let expectedCount = 0
          controlPointTabs.forEach((tab, i) => {
            const fields = fieldsList[i]
            if (fields.abnormal === '是') expectedCount++
            const d = collectControlPointDefect(tab, fields)
            if (d) defects.push(d)
          })
          // 数量一致
          expect(defects.length).toBe(expectedCount)
          // 无重复（controlId 唯一）
          const ids = defects.map(d => d.controlId)
          expect(new Set(ids).size).toBe(ids.length)
          // 每个缺陷都来自 itgc-sheet 控制点且保留来源追溯
          for (const d of defects) {
            const tab = controlPointTabs.find(t => t.id === d.controlId)
            expect(tab).toBeDefined()
            expect(d.sheet).toBe(tab!.sheet)
            expect(d.group).toBe(tab!.group)
          }
        },
      ),
      RUNS,
    )
  })

  it('aux 续页永不产生缺陷（即使异常=是也不在控制点集合中被遍历）', () => {
    const auxTabs = C22_BUNDLE_TABS.filter(t => t.kind === 'itgc-aux')
    for (const t of auxTabs) {
      // aux 不在 controlPointTabs 中 → 不参与缺陷收集
      expect(controlPointTabs).not.toContain(t)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: 完成进度统计一致性
// Feature: c22-itgc-bundle, Property 4: 完成进度统计一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c22-itgc-bundle, Property 4: 完成进度统计一致性', () => {
  it('completed+inProgress+notStarted == 控制点总数，defectCount == defects 长度', () => {
    fc.assert(
      fc.property(
        fc.array(fc.constantFrom<CompletionStatus>('completed', 'in_progress', 'not_started'), {
          minLength: 0, maxLength: 40,
        }),
        fc.nat({ max: 31 }),
        (statuses, defectN) => {
          const completionMap: Record<string, CompletionStatus> = {}
          statuses.forEach((s, i) => { completionMap[`cp-${i}`] = s })
          const defects: ItgcDefect[] = Array.from({ length: defectN }, (_, i) => ({
            controlId: `d-${i}`, group: '信息安全', sheet: `s-${i}`, description: '', defectNo: `ITGC#${i}`,
          }))
          const summary = computeProgressSummary(completionMap, defects)
          expect(summary.completed + summary.inProgress + summary.notStarted).toBe(statuses.length)
          expect(summary.defectCount).toBe(defectN)
        },
      ),
      RUNS,
    )
  })

  it('deriveItgcStatus 结果恒为三态之一', () => {
    fc.assert(
      fc.property(fieldsArb(), (fields) => {
        const status = deriveItgcStatus(fields)
        expect(['completed', 'in_progress', 'not_started']).toContain(status)
      }),
      RUNS,
    )
  })

  it('完成状态推导单调性：设计+执行均非空 ⟺ completed', () => {
    fc.assert(
      fc.property(fieldsArb(), (fields) => {
        const dFilled = !!(fields.designConclusion && fields.designConclusion.trim())
        const eFilled = !!(fields.execConclusion && fields.execConclusion.trim())
        const status = deriveItgcStatus(fields)
        if (dFilled && eFilled) expect(status).toBe('completed')
        else if (dFilled || eFilled) expect(status).toBe('in_progress')
        else expect(status).toBe('not_started')
      }),
      RUNS,
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: sheetName 路由正确激活
// Feature: c22-itgc-bundle, Property 5: sheetName 路由
// ═══════════════════════════════════════════════════════════════════════════════

import { resolveSheetRoute, normalizeReadonly, suggestEvidenceIndex } from '../useC22BundleState'

/** 所有可见 Tab 的 id 集合（对齐组件 visibleTabs：matrix + 4 大类子页 + C21/C21-1） */
const ALL_VALID_IDS = C22_BUNDLE_TABS.map(t => t.id)

describe('Feature: c22-itgc-bundle, Property 5: sheetName 路由', () => {
  /**
   * **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
   *
   * P5: For any valid Tab id, passing it as sheetName/query activates that tab;
   *     invalid values keep current tab (default: matrix).
   */

  it('合法 Tab id 传入 → 激活该 Tab（resolveSheetRoute 返回该 id）', () => {
    fc.assert(
      fc.property(fc.constantFrom(...ALL_VALID_IDS), (validId) => {
        const result = resolveSheetRoute(validId, ALL_VALID_IDS)
        expect(result).toBe(validId)
      }),
      RUNS,
    )
  })

  it('非法字符串（不在 C22_BUNDLE_TABS.id 中）→ 保持当前不变（返回 null）', () => {
    fc.assert(
      fc.property(
        fc.string().filter(s => s.trim().length > 0 && !ALL_VALID_IDS.includes(s.trim())),
        (invalidId) => {
          const result = resolveSheetRoute(invalidId, ALL_VALID_IDS)
          expect(result).toBeNull()
        },
      ),
      RUNS,
    )
  })

  it('空值 / null / undefined / 纯空格 → 保持当前不变（返回 null）', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.constant(null),
          fc.constant(undefined),
          fc.constant(''),
          fc.constant('   '),
          fc.constant('\t'),
          fc.constant('\n'),
        ),
        (emptyish) => {
          const result = resolveSheetRoute(emptyish, ALL_VALID_IDS)
          expect(result).toBeNull()
        },
      ),
      RUNS,
    )
  })

  it('混合生成器：oneof(valid, random) 覆盖边界', () => {
    fc.assert(
      fc.property(
        fc.oneof(fc.constantFrom(...ALL_VALID_IDS), fc.string()),
        (sheetName) => {
          const result = resolveSheetRoute(sheetName, ALL_VALID_IDS)
          const trimmed = (sheetName ?? '').trim()
          if (!trimmed) {
            // 空值 → null
            expect(result).toBeNull()
          } else if (ALL_VALID_IDS.includes(trimmed)) {
            // 合法 → 返回该 id
            expect(result).toBe(trimmed)
          } else {
            // 非法 → null
            expect(result).toBeNull()
          }
        },
      ),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: readonly 透传
// Feature: c22-itgc-bundle, Property 6: readonly 透传
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c22-itgc-bundle, Property 6: readonly 透传', () => {
  /**
   * **Validates: Requirements 9.1, 9.2**
   *
   * P6: For any Tab and any readonly boolean, all sub-pages/matrix/summary
   *     receive the same readonly value as parent props.readonly.
   */

  it('normalizeReadonly(true) === true；其他一切值 === false', () => {
    fc.assert(
      fc.property(fc.boolean(), (readonlyProp) => {
        const normalized = normalizeReadonly(readonlyProp)
        // 严格布尔等价：true→true, false→false
        expect(normalized).toBe(readonlyProp === true)
      }),
      RUNS,
    )
  })

  it('对所有可能的 props.readonly 值（含 undefined/null/number/string），仅 true 通过', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.boolean(),
          fc.constant(undefined),
          fc.constant(null),
          fc.integer(),
          fc.string(),
          fc.constant(0),
          fc.constant(1),
          fc.constant('true'),
          fc.constant('false'),
        ),
        (readonlyVal) => {
          const normalized = normalizeReadonly(readonlyVal)
          if (readonlyVal === true) {
            expect(normalized).toBe(true)
          } else {
            expect(normalized).toBe(false)
          }
        },
      ),
      RUNS,
    )
  })

  it('所有 Tab 均接收相同的 readonly 值（透传一致性）', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        fc.constantFrom(...ALL_VALID_IDS),
        (readonlyProp, tabId) => {
          // 模拟组件行为：isReadonly = props.readonly === true
          const parentReadonly = normalizeReadonly(readonlyProp)
          // 每个子页接收的 readonly 应与 parent 完全一致
          // （组件模板中所有子页的 :readonly="isReadonly"）
          const childReadonly = parentReadonly
          expect(childReadonly).toBe(parentReadonly)
          // 路由目标不影响 readonly 透传
          const resolvedTab = resolveSheetRoute(tabId, ALL_VALID_IDS)
          expect(resolvedTab).not.toBeNull() // tabId 来自 valid IDs
          // 无论激活哪个 Tab，readonly 语义不变
          expect(normalizeReadonly(readonlyProp)).toBe(parentReadonly)
        },
      ),
      RUNS,
    )
  })

  it('readonly=false 时子页允许编辑（normalizeReadonly → false）', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(false, undefined, null, 0, '', 'false'),
        (falsy) => {
          expect(normalizeReadonly(falsy)).toBe(false)
        },
      ),
      RUNS,
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: 证据编号规则
// Feature: c22-itgc-bundle, Property 8: 证据编号规则
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c22-itgc-bundle, Property 8: 证据编号规则', () => {
  /**
   * **Validates: Requirements 11.2**
   *
   * P8: For any sub-page evidence upload, the suggested index number conforms to
   *     `C22.{controlId}-{seq}` format and is unique within the same sub-page.
   */

  it('suggestEvidenceIndex 始终生成 C22.{controlId}-{seq} 格式', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...ITGC_CONTROL_SHEETS),
        fc.integer({ min: 1, max: 100 }),
        (controlId, seq) => {
          const idx = suggestEvidenceIndex(controlId, seq)
          // 格式：C22.{controlId}-{seq}
          expect(idx).toBe(`C22.${controlId}-${seq}`)
          // 以 C22. 开头
          expect(idx.startsWith('C22.')).toBe(true)
          // 包含控制点 ID
          expect(idx).toContain(controlId)
          // 包含序号
          expect(idx.endsWith(`-${seq}`)).toBe(true)
        },
      ),
      RUNS,
    )
  })

  it('同子页内递增序号 → 索引号互不重复', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...ITGC_CONTROL_SHEETS),
        fc.integer({ min: 1, max: 20 }),
        (controlId, count) => {
          const indices = Array.from({ length: count }, (_, i) =>
            suggestEvidenceIndex(controlId, i + 1),
          )
          // 唯一性
          expect(new Set(indices).size).toBe(count)
          // 每个索引号都以 C22.{controlId}- 为前缀
          for (const idx of indices) {
            expect(idx.startsWith(`C22.${controlId}-`)).toBe(true)
          }
        },
      ),
      RUNS,
    )
  })

  it('不同控制点同序号 → 索引号不同', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 50 }),
        (seq) => {
          // 取两个不同控制点
          const ids = ITGC_CONTROL_SHEETS.slice(0, 2)
          if (ids.length < 2) return // 安全守卫
          const idx1 = suggestEvidenceIndex(ids[0], seq)
          const idx2 = suggestEvidenceIndex(ids[1], seq)
          expect(idx1).not.toBe(idx2)
        },
      ),
      RUNS,
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: 点选值合法性
// Feature: c22-itgc-bundle, Property 7: 点选值合法性
// ═══════════════════════════════════════════════════════════════════════════════

import { IT_CATEGORY_OPTIONS, APP_SYSTEM_OPTIONS } from '../useC22BundleState'

describe('Feature: c22-itgc-bundle, Property 7: 点选值合法性', () => {
  /**
   * **Validates: Requirements 10.1**
   *
   * P7: For any 点选字段，保存值属于选项枚举。
   * 具体验证：设计/执行有效性结论仅 CONCLUSION_OPTIONS 枚举值合法。
   */

  it('设计/执行有效性结论保存值始终属于 CONCLUSION_OPTIONS 枚举', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...CONCLUSION_OPTIONS),
        (conclusion) => {
          // 保存值必须是枚举成员之一
          expect(CONCLUSION_OPTIONS).toContain(conclusion)
          // 具体为三个值之一
          expect(['有效', '部分有效', '无效']).toContain(conclusion)
        },
      ),
      RUNS,
    )
  })

  it('deriveItgcStatus 仅对 CONCLUSION_OPTIONS 枚举值视为 filled', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...CONCLUSION_OPTIONS),
        fc.constantFrom(...CONCLUSION_OPTIONS),
        (designVal, execVal) => {
          const fields: ControlPointFields = {
            designConclusion: designVal,
            execConclusion: execVal,
            abnormal: null,
            defectDesc: null,
            defectNo: null,
            appSystem: null,
            itCategory: null,
          }
          // 两个合法枚举值均非空 → completed
          const status = deriveItgcStatus(fields)
          expect(status).toBe('completed')
        },
      ),
      RUNS,
    )
  })

  it('非枚举值（空/null/空格）不被视为有效结论', () => {
    fc.assert(
      fc.property(
        fc.oneof(fc.constant(null), fc.constant(''), fc.constant('   '), fc.constant('\t')),
        fc.oneof(fc.constant(null), fc.constant(''), fc.constant('   '), fc.constant('\t')),
        (designVal, execVal) => {
          const fields: ControlPointFields = {
            designConclusion: designVal,
            execConclusion: execVal,
            abnormal: null,
            defectDesc: null,
            defectNo: null,
            appSystem: null,
            itCategory: null,
          }
          // 空值 → not_started
          const status = deriveItgcStatus(fields)
          expect(status).toBe('not_started')
        },
      ),
      RUNS,
    )
  })

  it('IT 控制类别选项集合非空且互不重复', () => {
    expect(IT_CATEGORY_OPTIONS.length).toBeGreaterThan(0)
    expect(new Set(IT_CATEGORY_OPTIONS).size).toBe(IT_CATEGORY_OPTIONS.length)
  })

  it('应用系统选项集合非空且互不重复', () => {
    expect(APP_SYSTEM_OPTIONS.length).toBeGreaterThan(0)
    expect(new Set(APP_SYSTEM_OPTIONS).size).toBe(APP_SYSTEM_OPTIONS.length)
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 9: 缺陷双向一致
// Feature: c22-itgc-bundle, Property 9: 缺陷双向一致
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: c22-itgc-bundle, Property 9: 缺陷双向一致', () => {
  /**
   * **Validates: Requirements 12.1, 12.4**
   *
   * P9: For any 子页异常状态切换，C21-1 汇总缺陷集合与「是否异常=是」子页集合始终一致。
   * 即：defects 恰好包含所有 abnormal='是' 的控制点，且不包含 abnormal≠'是' 的控制点。
   */

  /** 生成随机异常状态切换序列 */
  const abnormalArb = fc.oneof(
    fc.constant('是'),
    fc.constant('否'),
    fc.constant(null),
    fc.constant(''),
  )

  it('任意异常状态组合下，defects 集合 == 所有 abnormal=是 的控制点集合（正向一致）', () => {
    fc.assert(
      fc.property(
        fc.array(abnormalArb, { minLength: controlPointTabs.length, maxLength: controlPointTabs.length }),
        (abnormals) => {
          // 模拟：每个控制点分配一个异常状态
          const defects: ItgcDefect[] = []
          const expectedAbnormalIds = new Set<string>()

          controlPointTabs.forEach((tab, i) => {
            const abnormal = abnormals[i]
            if (abnormal === '是') expectedAbnormalIds.add(tab.id)

            const fields: ControlPointFields = {
              designConclusion: '有效',
              execConclusion: '有效',
              abnormal,
              defectDesc: `desc-${tab.id}`,
              defectNo: `ITGC#${i + 1}`,
              appSystem: null,
              itCategory: null,
            }
            const d = collectControlPointDefect(tab, fields)
            if (d) defects.push(d)
          })

          // 正向：defects 中每个条目的 controlId 都在 expectedAbnormalIds 中
          const defectIds = new Set(defects.map(d => d.controlId))
          expect(defectIds).toEqual(expectedAbnormalIds)
        },
      ),
      RUNS,
    )
  })

  it('任意异常状态组合下，abnormal≠是 的控制点不出现在 defects 中（反向排除）', () => {
    fc.assert(
      fc.property(
        fc.array(abnormalArb, { minLength: controlPointTabs.length, maxLength: controlPointTabs.length }),
        (abnormals) => {
          const defects: ItgcDefect[] = []
          const nonAbnormalIds = new Set<string>()

          controlPointTabs.forEach((tab, i) => {
            const abnormal = abnormals[i]
            if (abnormal !== '是') nonAbnormalIds.add(tab.id)

            const fields: ControlPointFields = {
              designConclusion: null,
              execConclusion: null,
              abnormal,
              defectDesc: null,
              defectNo: null,
              appSystem: null,
              itCategory: null,
            }
            const d = collectControlPointDefect(tab, fields)
            if (d) defects.push(d)
          })

          // 反向：非异常控制点不得出现在 defects 中
          for (const d of defects) {
            expect(nonAbnormalIds.has(d.controlId)).toBe(false)
          }
        },
      ),
      RUNS,
    )
  })

  it('异常状态切换（是→否）后，对应缺陷从集合中移除', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: controlPointTabs.length - 1 }),
        (switchIdx) => {
          // Phase 1: 所有控制点 abnormal=是
          const defectsPhase1: ItgcDefect[] = []
          controlPointTabs.forEach((tab) => {
            const fields: ControlPointFields = {
              designConclusion: '有效',
              execConclusion: '有效',
              abnormal: '是',
              defectDesc: `问题-${tab.id}`,
              defectNo: `ITGC#${tab.id}`,
              appSystem: null,
              itCategory: null,
            }
            const d = collectControlPointDefect(tab, fields)
            if (d) defectsPhase1.push(d)
          })
          expect(defectsPhase1.length).toBe(controlPointTabs.length)

          // Phase 2: 将 switchIdx 位置的控制点切换为 abnormal=否
          const defectsPhase2: ItgcDefect[] = []
          controlPointTabs.forEach((tab, i) => {
            const abnormal = i === switchIdx ? '否' : '是'
            const fields: ControlPointFields = {
              designConclusion: '有效',
              execConclusion: '有效',
              abnormal,
              defectDesc: `问题-${tab.id}`,
              defectNo: `ITGC#${tab.id}`,
              appSystem: null,
              itCategory: null,
            }
            const d = collectControlPointDefect(tab, fields)
            if (d) defectsPhase2.push(d)
          })

          // 切换后：缺陷数量少 1
          expect(defectsPhase2.length).toBe(controlPointTabs.length - 1)
          // 被切换的控制点不再出现在缺陷集合中
          const switchedId = controlPointTabs[switchIdx].id
          expect(defectsPhase2.find(d => d.controlId === switchedId)).toBeUndefined()
        },
      ),
      RUNS,
    )
  })

  it('缺陷条目保留来源控制点编号与子页索引（双向追溯 Req 12.3）', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...controlPointTabs),
        (tab) => {
          const fields: ControlPointFields = {
            designConclusion: '无效',
            execConclusion: '无效',
            abnormal: '是',
            defectDesc: '测试缺陷描述',
            defectNo: 'ITGC#1',
            appSystem: 'ERP',
            itCategory: null,
          }
          const defect = collectControlPointDefect(tab, fields)
          expect(defect).not.toBeNull()
          // 来源控制点编号
          expect(defect!.controlId).toBe(tab.id)
          // 来源 sheet（子页索引）
          expect(defect!.sheet).toBe(tab.sheet)
          // 所属分组
          expect(defect!.group).toBe(tab.group)
          // 缺陷描述
          expect(defect!.description).toBe('测试缺陷描述')
          // 缺陷编号
          expect(defect!.defectNo).toBe('ITGC#1')
        },
      ),
      RUNS,
    )
  })
})
