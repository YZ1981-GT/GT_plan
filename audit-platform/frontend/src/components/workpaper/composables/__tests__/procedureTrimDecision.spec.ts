/**
 * 裁剪决策内核守卫（Wave 2 打红）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 5
 * Property 1 / 2 / 3 / 4 / 5 / 33，以及 Wave 2 全域共享的类 A 基线判据。
 *
 * ## 断言分两类（防「全红分不清是功能未做还是守卫写坏」）
 *
 * - **类 A = 独立口径判据**：本守卫自己从真源算出的事实（`materiality` 表列存在性、
 *   `scope-accounts` 是否返回 `amount`、现状智能裁剪是否丢弃 `amount`、`TrimReasonCode`
 *   现有取值域、canonical entry 有无 `reason_code`）。**现在就应全绿** —— 绿了才证明
 *   判据基础设施有效而非空转。
 * - **类 B = 被测实现**：`composables/procedureTrimDecision.ts` 的存在性、导出契约与
 *   决策行为。**现在应全红**，失败消息统一写明「尚未实现（Wave 2 Task 7）。本条红是
 *   **预期**的 Wave 2 打红结果」。
 *
 * ## 三条硬约束
 *
 * 1. **禁在模块顶层 import 尚不存在的生产模块** —— 顶层 import 失败会让整个文件
 *    collection error、零断言执行，那时"全红"既可能是功能没做也可能是守卫写坏。故一律
 *    先 `fs.existsSync` 再 `await import(/* @vite-ignore *​/ spec)`，失败走 `expect.fail`
 *    （**不是 skip** —— skip 会让 Wave 2 看起来"没有红"）。
 * 2. **读源码型断言必须先 `stripComments()`** —— 本文件的说明注释里会写反例（如「现状
 *    丢弃 amount」），裸 `includes` 会把说明文字数成真实引用。
 * 3. **每条扫描判据都配「扫描面非空」自检** —— 防正则失效导致断言空转。
 *
 * ## 类 A 共享判据只放本文件
 *
 * `completenessExemption.spec.ts` / `trimAggregateGate.spec.ts` 不重复这些判据（重复
 * 会让「改一处另一处不红」）。
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

// ── 双哨兵向上找仓库根（禁写死回退级数；`composables/__tests__/` 与
//    `views/__tests__/` 深度不同，照抄级数必 ENOENT）──
function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 14; i += 1) {
    const a = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    const b = path.join(dir, 'backend', 'app', 'main.py')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error(
    'repoRoot 未找到（双哨兵 audit-platform/frontend/package.json + backend/app/main.py）',
  )
}

const ROOT = repoRoot()
const FE = path.join(ROOT, 'audit-platform', 'frontend', 'src')
const BE = path.join(ROOT, 'backend', 'app')

const MOD_DIR = path.join(FE, 'components', 'workpaper', 'composables')
const P_DECISION = path.join(MOD_DIR, 'procedureTrimDecision.ts')
const P_EXEMPTION = path.join(MOD_DIR, 'completenessExemption.ts')
const P_AGGREGATE = path.join(MOD_DIR, 'trimAggregateGate.ts')
/** 理由码前端镜像（Task 12）。本文件读它做**前后端交叉锁死**，见理由码取值域一节。 */
const P_REASON_MIRROR = path.join(MOD_DIR, 'trimReasonCodes.ts')

const P_TRIM_VUE = path.join(FE, 'views', 'ProcedureTrimming.vue')
const P_MODELS = path.join(BE, 'models', 'audit_platform_models.py')
const P_SCOPE_ROUTER = path.join(BE, 'routers', 'b50_scope.py')
const P_TRIM_ENGINE = path.join(BE, 'services', 'procedure_trim_engine.py')
const P_TRIM_SERVICE = path.join(BE, 'services', 'procedure_trim_service.py')

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

/**
 * 带字符串状态的注释剥离（`accept="image/*"` 里的 `/*` 不能当块注释起点）。
 * 字符串字面量原样保留（字面量里可能是真实取值，不能剥）。
 */
function stripComments(src: string): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (quote) {
      out += c
      if (c === '\\') {
        out += n ?? ''
        i += 2
        continue
      }
      if (c === quote) quote = null
      i += 1
      continue
    }
    if (c === '"' || c === "'" || c === '`') {
      quote = c
      out += c
      i += 1
      continue
    }
    if (c === '/' && n === '/') {
      while (i < src.length && src[i] !== '\n') i += 1
      continue
    }
    if (c === '/' && n === '*') {
      i += 2
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) i += 1
      i += 2
      continue
    }
    if (c === '<' && src.startsWith('<!--', i)) {
      const end = src.indexOf('-->', i)
      i = end < 0 ? src.length : end + 3
      continue
    }
    out += c
    i += 1
  }
  return out
}

/** 剥 python 的 `#` 行注释与三引号 docstring（保留普通字符串字面量）。 */
function stripPyComments(src: string): string {
  let out = ''
  let i = 0
  while (i < src.length) {
    const three = src.slice(i, i + 3)
    if (three === '"""' || three === "'''") {
      const end = src.indexOf(three, i + 3)
      const skipped = src.slice(i, end < 0 ? src.length : end + 3)
      // 保留换行，维持行号与「函数体长度」类判据的量级
      out += skipped.replace(/[^\n]/g, ' ')
      i = end < 0 ? src.length : end + 3
      continue
    }
    if (src[i] === '#') {
      while (i < src.length && src[i] !== '\n') i += 1
      continue
    }
    out += src[i]
    i += 1
  }
  return out
}

/**
 * 截取具名函数的**函数体**（花括号配对）。
 *
 * 🔴 不能用「声明后第一个 `{`」定位 —— 那个 `{` 可能是**内联返回类型注解**
 * （`function f(): Promise<{ a: X }> {`）或参数的内联类型字面量，截出来的"函数体"
 * 其实是那段类型，后续断言全在无关文本上求值（Wave 1 已踩过）。
 * 做法：从声明处起逐个候选 `{` 做配对，取第一个**含语句特征**的块。
 */
function fnBody(src: string, decl: RegExp | string): string {
  const re =
    typeof decl === 'string'
      ? new RegExp(`(?:function|const|let)\\s+${decl}\\b|\\b${decl}\\s*[:=]`)
      : decl
  const m = src.match(re)
  if (!m || m.index === undefined) return ''
  let from = m.index + m[0].length
  for (let guard = 0; guard < 14; guard += 1) {
    const open = src.indexOf('{', from)
    if (open < 0) return ''
    let depth = 0
    let end = -1
    for (let i = open; i < src.length; i += 1) {
      if (src[i] === '{') depth += 1
      else if (src[i] === '}') {
        depth -= 1
        if (depth === 0) {
          end = i
          break
        }
      }
    }
    if (end < 0) return ''
    const block = src.slice(open, end + 1)
    if (/\b(return|const|let|await|if|for|throw)\b/.test(block)) return block
    from = end + 1
  }
  return ''
}

/** 按缩进截 python 函数体（先用圆括号配对跳过多行签名）。 */
function pyFnBody(src: string, name: string): string {
  const m = src.match(new RegExp(`^([ \\t]*)(?:async\\s+)?def\\s+${name}\\s*\\(`, 'm'))
  if (!m || m.index === undefined) return ''
  const indent = m[1].length
  // 圆括号配对跳过签名（多行签名的 `) -> X:` 那行缩进为 0，按缩进截会提前中断）
  let i = m.index + m[0].length - 1
  let depth = 0
  for (; i < src.length; i += 1) {
    if (src[i] === '(') depth += 1
    else if (src[i] === ')') {
      depth -= 1
      if (depth === 0) break
    }
  }
  const nl = src.indexOf('\n', i)
  if (nl < 0) return ''
  const lines = src.slice(nl + 1).split('\n')
  const body: string[] = []
  for (const line of lines) {
    if (line.trim() === '') {
      body.push(line)
      continue
    }
    const ind = line.length - line.replace(/^[ \t]*/, '').length
    if (ind <= indent) break
    body.push(line)
  }
  return body.join('\n')
}

/** 统一的「尚未实现」红消息（类 B）。 */
function pendingFail(what: string, task: string): never {
  return expect.fail(
    `${what} 尚未实现（Wave 2 ${task}）。本条红是**预期**的 Wave 2 打红结果。`,
  )
}

/**
 * 加载尚不存在的生产模块（类 B 专用）。
 *
 * 先 `existsSync` 再动态 import，且 import 路径走**变量 + `@vite-ignore`** ——
 * 字面量路径会被 vite 静态分析，文件不存在时在 transform 阶段就崩，导致整个文件
 * collection error（零断言执行）。
 */
async function loadPure(file: string, specifier: string, task: string): Promise<any> {
  if (!fs.existsSync(file)) {
    pendingFail(`模块 ${path.basename(file)}`, task)
  }
  try {
    return await import(/* @vite-ignore */ specifier)
  } catch (e) {
    pendingFail(`模块 ${path.basename(file)} 无法加载（${String(e)}）`, task)
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// helper 自检（反向自检：证明判据本身有效，不是恒真）
// ═══════════════════════════════════════════════════════════════════════════
describe('helper 自检', () => {
  it('stripComments 剥掉注释、保留字符串字面量', () => {
    const s = stripComments(`const a = '.amount' // 注释里写 .amount\n/* 块里也写 .amount */`)
    expect(s).toContain("'.amount'")
    expect(s).not.toContain('注释里写')
    expect(s).not.toContain('块里也写')
  })

  it('stripComments 不把 accept="image/*" 当块注释起点', () => {
    const s = stripComments(`<input accept="image/*" />\nconst keep = 1`)
    expect(s).toContain('const keep = 1')
  })

  it('stripPyComments 剥掉 docstring 与 # 注释', () => {
    const s = stripPyComments(
      ['def f():', '    """docstring 里写 reason_code"""', '    # 注释里写 reason_code', '    return 1'].join('\n'),
    )
    expect(s).not.toContain('docstring 里写')
    expect(s).not.toContain('注释里写')
    expect(s).toContain('return 1')
  })

  it('fnBody 跳过内联返回类型注解', () => {
    const fixture = [
      'export function f(p: string): { a: number } {',
      '  const x = 1',
      '  return x',
      '}',
    ].join('\n')
    const body = fnBody(fixture, /export\s+function\s+f\b/)
    expect(body).toContain('const x = 1')
    // 反向：朴素「第一个 {」会截到类型字面量
    const naive = fixture.slice(fixture.indexOf('{'), fixture.indexOf('}') + 1)
    expect(naive).toContain('a: number')
    expect(naive).not.toContain('const x')
  })

  it('pyFnBody 跳过多行签名', () => {
    const fixture = [
      'def g(',
      '    a: int,',
      ') -> dict:',
      '    x = 1',
      '    return x',
      '',
      'def other():',
      '    pass',
    ].join('\n')
    const body = pyFnBody(fixture, 'g')
    expect(body).toContain('x = 1')
    expect(body).not.toContain('def other')
  })

  it('loadPure 对不存在的模块产生「尚未实现」红而非 collection error', async () => {
    const bogus = path.join(MOD_DIR, '__definitely_not_exists__.ts')
    await expect(loadPure(bogus, './__definitely_not_exists__', 'Task 0')).rejects.toThrow(
      /尚未实现/,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 A：独立口径判据（现在应全绿）
// ═══════════════════════════════════════════════════════════════════════════
// ── 类 A 判据抽成谓词，使同一判据可同时施加于真实源码与替身 fixture ──
//
// 🔴 为什么必须这样写：类 A 的被测对象是**生产源码**，而守卫文件自身不是被测对象。
// 若只在真实源码上断言，则「判据是否真能抓到缺陷」无从证明 —— 变异守卫文件只是把
// 守卫删掉，不构成对被测对象的变异（本轮变异检验首轮 4 个 GREEN 全是此因）。
// 而 `ProcedureTrimming.vue` / `audit_platform_models.py` 是跨 spec 共享热点文件，
// 平台铁律禁止对其做磁盘变异（并发会话会互相回退，且脚本被 Ctrl+C 打断会留残留）。
// ⇒ 正解 = 判据抽成纯谓词 + 用替身字符串在测试内证明「复现旧行为/坏行为必打红」。

/**
 * 判据：某字段在给定源码片段里是否为 `Mapped[...] = mapped_column(...)` 形态。
 *
 * 单独抽出来是为了让上层断言能指出**哪个**字段缺失（`hasMaterialityFields` 只给
 * 布尔，定位不到具体字段）。两者共用同一正则，不构成双真源。
 */
export function hasMappedColumn(pyBody: string, field: string): boolean {
  return new RegExp(`${field}\\s*:\\s*Mapped\\[[^\\]]+\\]\\s*=\\s*mapped_column`).test(pyBody)
}

/** 判据：Materiality 模型三个重要性字段是否都是 mapped_column。 */
export function hasMaterialityFields(pySrc: string): boolean {
  const idx = pySrc.search(/^class\s+Materiality\s*\(Base\)\s*:/m)
  if (idx < 0) return false
  const body = pySrc.slice(idx)
  return ['overall_materiality', 'performance_materiality', 'trivial_threshold'].every((f) =>
    hasMappedColumn(body, f),
  )
}

/** 判据：某函数体是否产出 amount 键（形态：字典字面量里 `"amount":`）。 */
export function producesAmountKey(fnBodySrc: string): boolean {
  return /["']amount["']\s*:/.test(fnBodySrc)
}

/**
 * 判据：函数体是否**取值形态**引用了 `.amount`（排除类型注解行）。
 *
 * 返回 `{ referenced, scanned }` —— `scanned` 供扫描面非空自检，避免「过滤空了
 * 所以判定为未引用」这种假绿。
 */
export function referencesAmountValue(fnBodySrc: string): { referenced: boolean; scanned: string } {
  const valueOnly = fnBodySrc
    .split('\n')
    .filter((ln) => !/\{[^}]*\b(?:name|amount|cycle)\s*:\s*(?:number|string)\b/.test(ln))
    .join('\n')
  return { referenced: /\.amount\b/.test(valueOnly), scanned: valueOnly }
}

// ═══════════════════════════════════════════════════════════════════════════
// 类 A 判据的「内存内变异」自检
//
// 🔴 为什么不做磁盘变异：被测对象是 `audit_platform_models.py` /
// `b50_scope.py` / `procedure_trim_engine.py` / `ProcedureTrimming.vue` /
// `procedure_trim_service.py` —— 全是跨 spec 共享热点文件。平台铁律禁止对其做磁盘
// 变异（并发会话会互相回退；脚本被 Ctrl+C 打断时变异会留在工作树，而下一轮又把
// 变异版当成原文基线 ⇒ 出现「写回校验通过而实际已损坏」的假绿）。本轮已实测被中断
// 一次，5 个文件靠 md5 + 形态双向核验才确认无残留。
//
// ⇒ 正解：**读真实源码 → 在内存里施加变异 → 断言判据必须打红**。强度与磁盘变异
// 等价（判据施加于同一份真实文本），且零残留风险、可长期留在 CI 里持续生效。
// ═══════════════════════════════════════════════════════════════════════════
describe('[类 A] 内存内变异：判据施加于真实源码后必须能打红', () => {
  it('M1 真实 models.py 去掉 performance_materiality 的 mapped_column ⟹ 判据打红', () => {
    const real = stripPyComments(read(P_MODELS))
    expect(hasMaterialityFields(real), '前提：真实源码应通过').toBe(true)

    const mutated = real.replace(
      /performance_materiality\s*:\s*Mapped\[[^\]]+\]\s*=\s*mapped_column/,
      'performance_materiality = None',
    )
    expect(mutated, '变异未施加（锚点未命中真实源码）').not.toBe(real)
    expect(
      hasMaterialityFields(mutated),
      '真实源码去掉 performance_materiality 后判据仍绿 ⇒ 判据空转',
    ).toBe(false)
  })

  it('M2 真实 b50_scope.py 去掉 amount 键 ⟹ 判据打红', () => {
    const body = pyFnBody(stripPyComments(read(P_SCOPE_ROUTER)), 'get_scope_accounts')
    expect(producesAmountKey(body), '前提：真实源码应通过').toBe(true)

    // 去掉 accounts 条目里的 amount 键（保留 name / cycle）
    const mutated = body.replace(/["']amount["']\s*:/g, '"__removed__":')
    expect(mutated, '变异未施加').not.toBe(body)
    expect(
      producesAmountKey(mutated),
      '真实端点去掉 amount 键后判据仍绿 ⇒ 判据空转（重要性维度会静默取不到金额）',
    ).toBe(false)
  })

  // ── Task 23 回收：M3 / M4 原为「改造前」方向（现状丢弃 amount，变异 = 改成真读）。
  //    Task 13 落地后金额消费点已从 `confirmSmartTrim` 迁到 `buildAndDecide`
  //    （`confirmSmartTrim` 不再遍历 accounts、不再读 `a.cycle`），故两条按各自注释
  //    自述的到期条件改写为**落地后方向**：变异 = 复现「丢弃 amount」的旧行为，判据必须打红。
  //    🔴 方向改了但承重不变：仍是「判据施加于真实源码 + 施加变异后必须变色」。
  it('M3 真实 buildAndDecide 退回「丢弃 amount」形态 ⟹ 落地判据打红', () => {
    const body = fnBody(stripComments(read(P_TRIM_VUE)), /function\s+buildAndDecide\b/)
    expect(body, '前提：应截到 buildAndDecide 函数体').not.toBe('')
    expect(
      referencesAmountValue(body).referenced,
      '前提：Task 13 落地后 buildAndDecide 应真读科目金额',
    ).toBe(true)

    // 变异 = 复现改造前的丢弃形态（金额恒 null ⇒ 重要性维度静默失效、永不产生建议）
    const mutated = body.replace(
      /Number\(\(ctx\.accounts as any\)\[accountName\]\?\.amount\)/,
      'null',
    )
    expect(mutated, '变异未施加（取金额锚点未命中真实源码）').not.toBe(body)
    expect(
      referencesAmountValue(mutated).referenced,
      '退回「丢弃 amount」后判据仍判「已引用」⇒ 判据空转，金额消费被删掉时不会转红',
    ).toBe(false)
  })

  it('M4 「剥类型声明」这一步不得过宽：真实取值行必须活过过滤', () => {
    const body = fnBody(stripComments(read(P_TRIM_VUE)), /function\s+buildAndDecide\b/)
    const { referenced, scanned } = referencesAmountValue(body)
    expect(referenced, '前提：落地后 buildAndDecide 真读 `.amount`').toBe(true)
    // 承重方向（落地后与改造前相反）：过滤必须**窄**到不吞真实取值行，
    // 否则判据会在「丢弃 amount」的实现上恒绿 —— 即假绿而非假红。
    expect(
      scanned,
      '取金额那一行被过滤掉了 ⇒ 过滤过宽，判据在「丢弃 amount」的实现上会恒绿',
    ).toMatch(/\?\.amount/)
    // 反向自检：把过滤放宽成「任何含 amount 的行都剥掉」，真实取值行即被吞
    const overBroad = body.split('\n').filter((ln) => !/amount/.test(ln)).join('\n')
    expect(
      /\.amount\b/.test(overBroad),
      '过宽过滤下判据仍能看到取值 ⇒ 本条自检无效（未真的复现过宽形态）',
    ).toBe(false)
  })

  it('M5 真实 procedure_trim_engine.py 去掉一个枚举值 ⟹ 快照判据打红', () => {
    const src = stripPyComments(read(P_TRIM_ENGINE))
    const enumBody = (s: string): string => {
      const i = s.search(/^class\s+TrimReasonCode\s*\(/m)
      if (i < 0) return ''
      const rest = s.slice(i)
      const nxt = rest.search(/\n(?:class|def)\s/)
      return nxt < 0 ? rest : rest.slice(0, nxt)
    }
    const readValues = (s: string): string[] =>
      Array.from(enumBody(s).matchAll(/^\s+[A-Z_]+\s*=\s*"([a-z_]+)"/gm)).map((m) => m[1])

    expect(readValues(src), '前提：真实源码含 4 个既有取值').toEqual(
      expect.arrayContaining(['no_related_business', 'low_risk_assessment', 'control_test_effective', 'other']),
    )

    const mutated = src.replace(/^\s+NO_RELATED_BUSINESS\s*=\s*"no_related_business"\s*$/m, '')
    expect(mutated, '变异未施加').not.toBe(src)
    expect(
      readValues(mutated).includes('no_related_business'),
      '真实源码删掉既有枚举值后快照判据仍绿 ⇒ 判据空转（Task 12 additive 扩展可能悄悄删掉既有值）',
    ).toBe(false)
  })

  it('M6 真实 procedure_trim_service.py 加入 reason_code ⟹ 现状基线打红', () => {
    const body = pyFnBody(stripPyComments(read(P_TRIM_SERVICE)), '_normalize_entry')
    expect(body, '前提：应截到 _normalize_entry 函数体').not.toBe('')
    const hasReasonCode = (s: string): boolean => /["']reason_code["']\s*:/.test(s)
    expect(hasReasonCode(body), '前提：现状 entry 无 reason_code').toBe(false)

    const mutated = body.replace(/["']skip_reason["']\s*:/, '"reason_code": rc, "skip_reason":')
    expect(mutated, '变异未施加（skip_reason 锚点未命中）').not.toBe(body)
    expect(
      hasReasonCode(mutated),
      'entry 加入 reason_code 后基线判据仍绿 ⇒ 判据空转，Task 12 落地时不会转红',
    ).toBe(true)
  })
})

describe('[类 A] 判据谓词替身自检（证明判据真能抓到缺陷）', () => {
  it('hasMaterialityFields：缺任一字段即为 false', () => {
    const good = [
      'class Materiality(Base):',
      '    __tablename__ = "materiality"',
      '    overall_materiality: Mapped[Decimal] = mapped_column(sa.Numeric(20, 2))',
      '    performance_materiality: Mapped[Decimal] = mapped_column(sa.Numeric(20, 2))',
      '    trivial_threshold: Mapped[Decimal] = mapped_column(sa.Numeric(20, 2))',
    ].join('\n')
    expect(hasMaterialityFields(good)).toBe(true)

    // 缺 performance_materiality（决策主口径）⇒ 必须 false
    const missing = good.split('\n').filter((l) => !l.includes('performance_materiality')).join('\n')
    expect(hasMaterialityFields(missing), '缺 performance_materiality 时判据未打红').toBe(false)

    // 字段存在但不是 mapped_column（只是注释/普通赋值）⇒ 必须 false
    const notMapped = good.replace(
      'performance_materiality: Mapped[Decimal] = mapped_column(sa.Numeric(20, 2))',
      'performance_materiality = None',
    )
    expect(hasMaterialityFields(notMapped), '字段非 mapped_column 时判据未打红').toBe(false)

    // 模型整体不存在 ⇒ 必须 false
    expect(hasMaterialityFields('class Other(Base):\n    pass'), '模型缺失时判据未打红').toBe(false)
  })

  it('hasMappedColumn：字段非 mapped_column 形态即为 false', () => {
    const body = '    performance_materiality: Mapped[Decimal] = mapped_column(sa.Numeric(20, 2))'
    expect(hasMappedColumn(body, 'performance_materiality')).toBe(true)
    // 只是普通赋值 / 只在注释里提到 ⇒ 必须 false
    expect(hasMappedColumn('    performance_materiality = None', 'performance_materiality')).toBe(false)
    expect(hasMappedColumn('    # performance_materiality 说明文字', 'performance_materiality')).toBe(false)
    // 字段压根不存在 ⇒ 必须 false
    expect(hasMappedColumn(body, 'trivial_threshold')).toBe(false)
  })

  it('producesAmountKey：不产出 amount 键即为 false', () => {
    expect(producesAmountKey('accounts.append({"name": n, "amount": a, "cycle": c})')).toBe(true)
    // 复现「端点丢掉 amount」这一坏行为 ⇒ 必须 false
    expect(
      producesAmountKey('accounts.append({"name": n, "cycle": c})'),
      '端点不返回 amount 时判据未打红',
    ).toBe(false)
  })

  it('referencesAmountValue：区分类型注解与取值形态（本判据的全部承重之处）', () => {
    // 现状形态：类型声明里有 amount，函数体只读 cycle ⇒ referenced=false
    const current = [
      'let accounts: { name: string; amount: number; cycle: string }[] = []',
      'for (const a of accounts) {',
      '  const c = (a.cycle || "").toUpperCase()',
      '}',
    ].join('\n')
    expect(referencesAmountValue(current).referenced, '现状基线应判为未引用').toBe(false)

    // Task 13 落地后形态：真读了 a.amount ⇒ referenced=true（本条基线届时应转红）
    const after = current.replace('const c =', 'const amt = Math.abs(a.amount); const c =')
    expect(referencesAmountValue(after).referenced, '真读 amount 时判据未识别').toBe(true)

    // 🔴 反向：若**不剥**类型注解行，现状形态会被误判成"已引用"（假红）。
    // 这条证明「剥类型声明」这一步是承重的，不是可省的装饰。
    expect(/\.amount\b/.test(current), '类型声明行不含 .amount 取值形态').toBe(false)
    expect(
      current.includes('amount: number'),
      '现状类型声明里确实有 amount 字面量（故必须按取值形态判定）',
    ).toBe(true)
  })
})

describe('[类 A] materiality 表列存在性与三字段可读', () => {
  const src = stripPyComments(read(P_MODELS))

  it('Materiality 模型存在', () => {
    expect(/^class\s+Materiality\s*\(Base\)\s*:/m.test(src), '未找到 class Materiality').toBe(true)
  })

  it('三个重要性字段均为 mapped_column（决策判据只用后两个）', () => {
    const body = src.slice(src.search(/^class\s+Materiality\s*\(Base\)\s*:/m))
    // 扫描面非空自检：该类体必须足够长且含表名声明
    expect(body.length, 'Materiality 类体过短，扫描面可疑').toBeGreaterThan(400)
    expect(body).toContain('__tablename__')
    // 判据经谓词施加（同一谓词已由上方替身自检证明能抓到缺陷）
    expect(hasMaterialityFields(src), 'Materiality 三个重要性字段未全部是 mapped_column').toBe(true)
    for (const f of ['overall_materiality', 'performance_materiality', 'trivial_threshold']) {
      // 判据经谓词施加（替身自检已证明「字段缺 mapped_column」时它会打红）
      expect(hasMappedColumn(body, f), `Materiality 缺少 mapped_column 字段 ${f}`).toBe(true)
    }
  })

  it('扫描面非空自检：辅助列同样在册（证明不是只匹配到三个名字）', () => {
    for (const f of ['benchmark_type', 'benchmark_amount', 'project_id', 'year']) {
      expect(src, `Materiality 相关列 ${f} 未出现`).toContain(f)
    }
  })
})

describe('[类 A] scope-accounts 端点确实返回 amount 字段', () => {
  const src = stripPyComments(read(P_SCOPE_ROUTER))

  it('get_scope_accounts 存在且函数体非空（扫描面自检）', () => {
    const body = pyFnBody(src, 'get_scope_accounts')
    expect(body, '未截到 get_scope_accounts 函数体').not.toBe('')
    expect(body.length, '函数体过短，扫描面可疑').toBeGreaterThan(500)
  })

  it('逐科目条目含 amount 键（三维判据的重要性维度依赖它）', () => {
    const body = pyFnBody(src, 'get_scope_accounts')
    // 判据经谓词施加（替身自检已证明「端点丢掉 amount」时它会打红）
    expect(
      producesAmountKey(body),
      'get_scope_accounts 未产出 amount 键 —— 重要性维度取不到科目金额',
    ).toBe(true)
    // 同时含 name 与 cycle，证明抓到的是 accounts 条目构造处
    expect(body).toContain('"name"')
    expect(body).toContain('"cycle"')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// [类 A] 落地后基线：智能裁剪真读科目金额（Task 23 回收改造前基线）
//
// 🔴 本 describe 原名「改造前基线：现状智能裁剪丢弃 amount」，两条断言自述
// 「Task 13 落地后本条应转红」。Task 13 已落地 ⇒ 按其自述改写为落地后口径。
//
// 消费点**迁移**了而不只是新增：改造前 `confirmSmartTrim` 自己遍历 accounts、
// 只读 `a.cycle`；落地后它把「程序 → 决策入参」的映射整段委托给 `buildAndDecide`，
// 金额在那里被读出并作为 `accountAmount` 传进 `decideTrim`。故扫描面必须跟着迁移，
// 否则会以「函数体内未见遍历 accounts 的循环」这种形态**假红**（Task 22 收口时的实况）。
// ═══════════════════════════════════════════════════════════════════════════
describe('[类 A] 落地后基线：智能裁剪真读科目金额', () => {
  const raw = read(P_TRIM_VUE)
  const src = stripComments(raw)
  const body = fnBody(src, /function\s+buildAndDecide\b/)
  const confirmBody = fnBody(src, /async\s+function\s+confirmSmartTrim\b/)

  it('扫描面非空自检：截到 buildAndDecide 函数体', () => {
    expect(body, '未截到 buildAndDecide 函数体').not.toBe('')
    expect(body.length, 'buildAndDecide 函数体过短，扫描面可疑').toBeGreaterThan(500)
    // 证明截到的确实是「程序 → 决策入参」那段映射（含内核调用与三维判据入参）
    expect(body, '函数体内未见 decideTrim 调用').toMatch(/return\s+decideTrim\s*\(/)
    expect(body, '未见科目金额入参').toMatch(/accountAmount\s*:/)
    expect(body, '未见数据存在性入参').toMatch(/subjectDataState\s*:/)
    // 循环级数据存在性仍由 ctx.accounts 派生（不另发请求）
    expect(body, '未见遍历 ctx.accounts 的取值').toMatch(/Object\.values\(ctx\.accounts/)
  })

  it('金额被真读并传入决策内核（落地口径，判据经谓词施加）', () => {
    // 判据经 `referencesAmountValue` 谓词施加 —— 该谓词已由替身自检双向证明：
    //   ① 丢弃形态（类型声明有 amount、函数体只读 cycle）判为未引用
    //   ② 落地形态（真读 `.amount`）判为已引用
    //   ③ 过滤过窄/过宽两侧均由 M3 / M4 在真实源码上钉死
    const { referenced, scanned } = referencesAmountValue(body)

    // 扫描面非空自检：剥类型声明后必须仍有实质内容（防把整段过滤空导致断言空转）
    expect(scanned.length, '剥类型声明后函数体被过滤空，判据失效').toBeGreaterThan(500)
    expect(scanned, '剥类型声明后仍应保留 accounts 取值').toMatch(/ctx\.accounts/)

    expect(
      referenced,
      'buildAndDecide 不再读科目金额 —— 重要性维度会静默失效（金额恒 null ⇒ 永不产生建议）',
    ).toBe(true)
  })

  it('confirmSmartTrim 不再自带第二份判据（映射唯一走 buildAndDecide）', () => {
    expect(confirmBody, '未截到 confirmSmartTrim 函数体').not.toBe('')
    expect(confirmBody.length, 'confirmSmartTrim 函数体过短，扫描面可疑').toBeGreaterThan(500)
    // 委托而非内联：调用点在，且自己不再遍历 accounts / 不再自读金额
    expect(confirmBody, 'confirmSmartTrim 未委托 buildAndDecide').toMatch(/buildAndDecide\s*\(/)
    expect(
      referencesAmountValue(confirmBody).referenced,
      'confirmSmartTrim 自己又读了一次金额 ⇒ 第二份判据真源（改造前正是此形态）',
    ).toBe(false)
    expect(
      confirmBody,
      'confirmSmartTrim 又出现遍历 accounts 的循环 ⇒ 内联判据回归',
    ).not.toMatch(/for\s*\(\s*const\s+a\s+of\s+accounts\s*\)/)
  })

  it('反向自检：stripComments 真的生效（原文含说明文字、剥后不含）', () => {
    // 本 SFC 内含中文注释；确认剥离前后有实质差异，否则上面的判据是在原文上求值
    expect(raw.length, '原文长度异常').toBeGreaterThan(src.length)
  })
})

describe('[类 A] TrimReasonCode 现有取值域快照', () => {
  const src = stripPyComments(read(P_TRIM_ENGINE))
  const body = (() => {
    const idx = src.search(/^class\s+TrimReasonCode\s*\(/m)
    if (idx < 0) return ''
    const rest = src.slice(idx)
    const nextClass = rest.search(/\n(?:class|def)\s/)
    return nextClass < 0 ? rest : rest.slice(0, nextClass)
  })()

  const values = Array.from(body.matchAll(/^\s+[A-Z_]+\s*=\s*"([a-z_]+)"/gm)).map((m) => m[1])

  /** 现有 4 值 —— Task 12 additive 扩展后**必须仍在**（防被"优化"掉）。 */
  const BASELINE = [
    'no_related_business',
    'low_risk_assessment',
    'control_test_effective',
    'other',
  ]

  it('扫描面非空自检：截到枚举类体', () => {
    expect(body, '未截到 class TrimReasonCode 类体').not.toBe('')
    expect(values.length, '未抽出任何枚举取值，正则可疑').toBeGreaterThan(0)
  })

  it('现有 4 个取值在扩展后必须仍在（反向锁死）', () => {
    for (const v of BASELINE) {
      expect(values, `TrimReasonCode 丢失既有取值 ${v}`).toContain(v)
    }
  })

  /**
   * Task 12 additive 新增的四值（**登记在此**，对应上一条注释自述的到期条件）。
   *
   * 前三个由 `decideTrim` 自动产出，`covered_elsewhere` 只由人工选择。
   */
  const ADDED = ['no_data', 'below_trivial', 'below_materiality', 'covered_elsewhere']

  it('落地后取值域 ⊇ 既有 4 值，且 Task 12 新增 4 值已登记', () => {
    // ⊇ 方向（既有值不得丢）已由上一条断言；本条钉死新增四值确实在册，
    // 并把全集冻结为 8 值 —— 再新增取值必须同时更新本清单与前端镜像，否则打红。
    for (const v of ADDED) {
      expect(values, `TrimReasonCode 缺 Task 12 新增取值 ${v} —— 粗裁三维判据无码可落`).toContain(v)
    }
    expect(
      values.slice().sort(),
      'TrimReasonCode 取值域已变 —— 若为新一轮 additive 扩展，请在 ADDED 里登记新值并同步前端镜像 trimReasonCodes.ts',
    ).toEqual([...BASELINE, ...ADDED].slice().sort())
  })

  it('前后端交叉锁死：前端镜像 trimReasonCodes.ts 与后端枚举逐值相等', () => {
    // 🔴 R8.7 / Property 19：任一侧新增而另一侧未跟进即红。
    // 只断言后端自洽是不够的 —— 后端加一个值而镜像不动时，前端会把它显示成裸码。
    const mirrorSrc = stripComments(read(P_REASON_MIRROR))
    const m = mirrorSrc.match(/export\s+const\s+TRIM_REASON_CODES\s*=\s*\[([\s\S]*?)\]\s*as\s+const/)
    expect(m, '前端镜像未找到 TRIM_REASON_CODES 数组 —— 交叉锁死失去一侧').not.toBeNull()
    const mirrorValues = Array.from(m![1].matchAll(/'([a-z_]+)'/g)).map((x) => x[1])
    // 扫描面非空自检：抽空了会让下面的比对恒假（而非恒真），但仍要显式点明成因
    expect(mirrorValues.length, '前端镜像抽出 0 个取值，正则可疑').toBeGreaterThan(0)
    expect(
      mirrorValues.slice().sort(),
      '前端镜像与后端 TrimReasonCode 取值域不一致 —— 一侧新增而另一侧未跟进',
    ).toEqual(values.slice().sort())
    // 每个取值都必须有中文标签（少一个即在下拉里显示成裸码）
    for (const v of mirrorValues) {
      expect(mirrorSrc, `前端镜像缺 ${v} 的中文标签`).toMatch(
        new RegExp(`${v}\\s*:\\s*['"]`),
      )
    }
  })
})

describe('[类 A] canonical scope entry 的 reason_code 为 additive 扩展', () => {
  const src = stripPyComments(read(P_TRIM_SERVICE))
  const body = pyFnBody(src, '_normalize_entry')

  /** 截 `normalized: dict = { ... }` 字面量（花括号配对）。 */
  const dictLiteral = (s: string): string => {
    const i = s.search(/normalized\s*:\s*dict\s*=\s*\{/)
    if (i < 0) return ''
    const open = s.indexOf('{', i)
    let depth = 0
    for (let k = open; k < s.length; k += 1) {
      if (s[k] === '{') depth += 1
      else if (s[k] === '}') {
        depth -= 1
        if (depth === 0) return s.slice(open, k + 1)
      }
    }
    return ''
  }

  it('扫描面非空自检：截到 _normalize_entry 且含既有键', () => {
    expect(body, '未截到 _normalize_entry 函数体').not.toBe('')
    expect(body.length, '函数体过短，扫描面可疑').toBeGreaterThan(200)
    for (const k of ['skip_reason', 'target_status', 'wp_index_code']) {
      expect(body, `_normalize_entry 未见既有键 ${k}`).toContain(k)
    }
  })

  // ── Task 23 回收：原断言「归一后的 entry 不含 reason_code」自述「Task 12 需 additive
  //    扩它」。Task 12 已落地 ⇒ 改写为落地后口径，但**承重方向不变**：仍然守住
  //    「存量调用方 payload 逐字节不变」这条 R8.9 红线，只是从「键不存在」升级为
  //    「键存在但**条件**写入」。恒写 None 会让全部存量 preview 凭证 hash 变化 ⇒ 409。
  it('entry 支持 reason_code，且为条件写入（R8.9 additive 零回归）', () => {
    expect(
      /reason_code/.test(body),
      'canonical entry 不支持 reason_code —— 理由码无处可落（Task 12 未落地或被回退）',
    ).toBe(true)
    // 必须是条件写入的形态
    expect(body, '`reason_code` 未做条件写入 ⇒ 存量 payload 多一键 ⇒ hash 全变 ⇒ 409').toMatch(
      /if\s+reason_code\b/,
    )
    // 🔴 且**不得**出现在返回 dict 字面量里（那就是无条件写入）
    const lit = dictLiteral(body)
    expect(lit, '未截到 normalized dict 字面量，扫描面可疑').not.toBe('')
    expect(lit, 'dict 字面量应含既有键').toContain('target_status')
    expect(
      /reason_code/.test(lit),
      '`reason_code` 被无条件写进返回 dict 字面量 —— 破坏 additive 零回归（存量 payload 键集变了）',
    ).toBe(false)
    // 非法取值必须拒绝（否则任意字符串都能落库，理由码统计随即失去意义）
    expect(body, '未见 reason_code 取值域校验').toMatch(/_VALID_TRIM_REASON_CODES/)
  })
})

describe('[类 A] 粗裁已接结构化理由码且存量自由文本仍在', () => {
  const raw = read(P_TRIM_VUE)
  const src = stripComments(raw)

  // ── Task 23 回收：原断言「裁剪页现状只有自由文本 skip_reason」自述
  //    「Task 12/13 落地后本条应转红」。已落地 ⇒ 改写为落地后口径。
  //    🔴 承重的是**两侧同时成立**：新增了理由码 **且** 存量自由文本没被替换掉。
  //    只断言前者会让「把 COMMON_SKIP_REASONS 删掉、全改成理由码」这种破 R8.4 的
  //    改法悄悄通过（存量记录只有自由文本，删了就再也显示不出原理由）。
  it('裁剪页既有结构化理由码，也保留自由文本理由（R8.4）', () => {
    expect(src, '裁剪页丢了自由文本理由常量 —— 存量只有 skip_reason 的记录将无从显示').toMatch(/const\s+COMMON_SKIP_REASONS\s*=\s*\[/)
    const declBody = src.match(/const\s+COMMON_SKIP_REASONS\s*=\s*\[([\s\S]*?)\]/)![1]
    expect(
      Array.from(declBody.matchAll(/'([^']{4,})'/g)).length,
      'COMMON_SKIP_REASONS 被清空 —— 自由文本理由只剩一个空下拉',
    ).toBeGreaterThanOrEqual(3)
    expect(src, 'COMMON_SKIP_REASONS 无模板消费点 —— 声明在而下拉里选不到').toMatch(
      /v-for\s*=\s*"[^"]*\bCOMMON_SKIP_REASONS\b/,
    )
    // T23-6 变异只把声明改名，模板消费点仍写着原名 ⇒ toContain 恒真（2026-08-11 修）
    expect(
      /const\s+COMMON_SKIP_REASONS\s*=\s*\[/.test("const RENAMED_SKIP_REASONS = ['x']"),
      '声明改名后仍被判成「声明存在」⇒ 判据未带定界符',
    ).toBe(false)
    expect(
      /\breason_?[Cc]ode\b/.test(src),
      '裁剪页无结构化理由码 —— 粗裁退回纯自由文本（Task 12/13 被回退）',
    ).toBe(true)
    // 不只是 import 了名字：载荷侧真的带上了它（snake_case 键随 canonical entry 提交）
    expect(src, '未见 `reason_code:` 载荷键 —— 理由码没有随裁剪请求提交').toMatch(
      /reason_code\s*:/,
    )
    // 且取值来自单一真源镜像，不是本页自己另写一份字面量
    expect(src, '未从 trimReasonCodes 单一真源取码').toMatch(
      /from\s+['"][^'"]*trimReasonCodes['"]/,
    )
  })

  it('反向自检：本条判据不是恒真（复现改造前形态必判否）', () => {
    // 复现改造前的裁剪页片段：只有自由文本、无理由码 ⇒ 上一条的两个方向必须一真一假
    const legacy = "const COMMON_SKIP_REASONS = ['本期无该类交易或余额']"
    expect(legacy).toContain('COMMON_SKIP_REASONS')
    expect(/\breason_?[Cc]ode\b/.test(legacy), '改造前形态被判成「已有理由码」⇒ 判据恒真').toBe(
      false,
    )
    // 且 stripComments 真的生效（注释里刻意留了改造前口径的说明文字）
    expect(raw.length, '原文长度异常').toBeGreaterThan(src.length)
  })

  it('扫描面非空自检：DATA_DRIVEN_CYCLES 与 cycles 常量仍为既有形态', () => {
    const dd = src.match(/const\s+DATA_DRIVEN_CYCLES\s*=\s*new\s+Set\(\[([^\]]+)\]\)/)
    expect(dd, '未找到 DATA_DRIVEN_CYCLES').not.toBeNull()
    const codes = Array.from(dd![1].matchAll(/'([A-Z])'/g)).map((m) => m[1])
    expect(codes.slice().sort()).toEqual(
      ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N'].slice().sort(),
    )
    // A/B/C/S 不在科目余额驱动集合内（完整性清单同样不含它们，Property 8）
    for (const c of ['A', 'B', 'C', 'S']) {
      expect(codes, `DATA_DRIVEN_CYCLES 不应含 ${c}`).not.toContain(c)
    }
  })
})

describe('[类 A] pm/te/sat 扫描面必须排除 GtB50RiskAssessment.vue', () => {
  it('该组件确实含 pm/te/sat 既有命名（证明排除是必要的，不是空操作）', () => {
    const src = stripComments(read(path.join(FE, 'components', 'workpaper', 'GtB50RiskAssessment.vue')))
    const hits = ['pm', 'te', 'sat'].filter((id) => new RegExp(`\\b${id}\\b`).test(src))
    expect(
      hits.length,
      'GtB50RiskAssessment.vue 已无 pm/te/sat 命名 —— 若该组件已收敛，可把它纳入扫描面',
    ).toBeGreaterThan(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 B：被测实现（现在应全红）
// ═══════════════════════════════════════════════════════════════════════════

/** 构造决策输入（默认走「保留」路径，逐条 override 触发各档）。 */
function baseInput(over: Record<string, any> = {}): any {
  return {
    procedure: {
      wpCode: 'D2-1',
      cycle: 'D',
      isMandatory: false,
      executionStatus: 'pending',
      hasManualReason: false,
      suggestionRejected: false,
      hasWorkpaperEntry: false,
      ...(over.procedure ?? {}),
    },
    accountAmount: 1_000_000,
    subjectDataState: 'with_data',
    cycleHasData: true,
    materiality: { performanceMateriality: 500_000, trivialThreshold: 25_000 },
    risk: {
      maxRisk: 'M',
      hasSpecial: false,
      completenessRmm: null,
      completenessSpecial: false,
      approach: 'combined',
      reliance: '是',
      ...(over.risk === null ? {} : (over.risk ?? {})),
    },
    riskDimensionAvailable: true,
    completenessSensitiveCycle: false,
    completenessSource: 'cycle_default',
    ...over,
    ...(over.risk === null ? { risk: null } : {}),
  }
}

describe('[类 B] procedureTrimDecision 模块契约', () => {
  it('模块存在且导出 decideTrim', async () => {
    const mod = await loadPure(P_DECISION, '../procedureTrimDecision', 'Task 7')
    expect(typeof mod.decideTrim, 'decideTrim 应为函数').toBe('function')
  })

  it('模块零 Vue 依赖、零 IO（纯函数，可直接单测与变异检验）', () => {
    if (!fs.existsSync(P_DECISION)) pendingFail('模块 procedureTrimDecision.ts', 'Task 7')
    const src = stripComments(read(P_DECISION))
    expect(/from\s+['"]vue['"]/.test(src), '决策内核不得依赖 vue').toBe(false)
    expect(/\bfetch\s*\(|axios|http\.get|http\.put/.test(src), '决策内核不得含 IO').toBe(false)
  })

  it('Property 4: 输入类型不含 overall_materiality，实现体不引用它', () => {
    if (!fs.existsSync(P_DECISION)) pendingFail('模块 procedureTrimDecision.ts', 'Task 7')
    const src = stripComments(read(P_DECISION))
    // 扫描面非空自检
    expect(src, '未见 TrimDecisionInput 类型声明').toContain('TrimDecisionInput')
    expect(
      /overall_?[Mm]ateriality/.test(src),
      'overall_materiality（整体重要性）不得作为裁剪判据 —— 它是财报整体评价基准，不是单科目门槛',
    ).toBe(false)
  })

  it('Property 3: 禁用 pm / te / sat 作标识符', () => {
    const files = [P_DECISION, P_EXEMPTION, P_AGGREGATE].filter((p) => fs.existsSync(p))
    if (files.length === 0) pendingFail('Wave 2 三个纯函数模块', 'Task 6/7/8')
    for (const p of files) {
      const src = stripComments(read(p))
      for (const id of ['pm', 'te', 'sat']) {
        expect(
          new RegExp(`\\b${id}\\b`).test(src),
          `${path.basename(p)} 出现禁用缩写 ${id}（一律用 performanceMateriality / trivialThreshold）`,
        ).toBe(false)
      }
    }
  })
})

describe('[类 B] Property 33: 决策结果结构完备', () => {
  it('返回值恒含五键；keep 时 reasonCode 为 null，其余两态非 null', async () => {
    const { decideTrim } = await loadPure(P_DECISION, '../procedureTrimDecision', 'Task 7')
    const cases = [
      baseInput(), // keep
      baseInput({ subjectDataState: 'no_data' }), // auto_trim
      baseInput({ accountAmount: 100 }), // suggest_trim (below_trivial)
    ]
    for (const input of cases) {
      const d = decideTrim(input)
      for (const k of ['verdict', 'reasonCode', 'narrative', 'evidence', 'hints']) {
        expect(Object.keys(d), `返回值缺少键 ${k}`).toContain(k)
      }
      expect(['keep', 'auto_trim', 'suggest_trim']).toContain(d.verdict)
      expect(typeof d.narrative).toBe('string')
      expect(d.narrative.length, 'narrative 不得为空（面向审计师的说明）').toBeGreaterThan(0)
      expect(Array.isArray(d.hints), 'hints 应为数组').toBe(true)
      expect(d.evidence, 'evidence 不得为空').toBeTruthy()
      if (d.verdict === 'keep') {
        expect(d.reasonCode, 'keep 时 reasonCode 应为 null').toBeNull()
      } else {
        expect(d.reasonCode, `${d.verdict} 时 reasonCode 不得为 null`).not.toBeNull()
      }
    }
  })
})

describe('[类 B] Property 1: 特别风险与高风险不受金额豁免', () => {
  it('hasSpecial 或 maxRisk=H 时恒 keep，与金额及重要性无关', async () => {
    const { decideTrim } = await loadPure(P_DECISION, '../procedureTrimDecision', 'Task 7')
    const protectedRisks = [
      { maxRisk: 'H', hasSpecial: false },
      { maxRisk: 'L', hasSpecial: true },
      { maxRisk: null, hasSpecial: true },
    ]
    const amounts = [0, 1, 100, 24_999, 499_999]
    for (const r of protectedRisks) {
      for (const amount of amounts) {
        const d = decideTrim(
          baseInput({ risk: { ...r }, accountAmount: amount, subjectDataState: 'no_data' }),
        )
        expect(
          d.verdict,
          `风险保护失效：risk=${JSON.stringify(r)} amount=${amount} 得到 ${d.verdict}`,
        ).toBe('keep')
      }
    }
  })
})

describe('[类 B] Property 2: 重要性类判据永不产生自动裁', () => {
  it('reasonCode ∈ {below_trivial, below_materiality} ⟹ verdict === suggest_trim', async () => {
    const { decideTrim } = await loadPure(P_DECISION, '../procedureTrimDecision', 'Task 7')
    for (const amount of [0, 1, 24_999, 25_000, 100_000, 499_999]) {
      const d = decideTrim(baseInput({ accountAmount: amount }))
      if (d.reasonCode === 'below_trivial' || d.reasonCode === 'below_materiality') {
        expect(d.verdict, `重要性类理由码却给出 ${d.verdict}（金额 ${amount}）`).toBe('suggest_trim')
      }
    }
  })

  it('反向：verdict === auto_trim ⟹ reasonCode === no_data', async () => {
    const { decideTrim } = await loadPure(P_DECISION, '../procedureTrimDecision', 'Task 7')
    const inputs = [
      baseInput({ subjectDataState: 'no_data' }),
      baseInput({ subjectDataState: 'unknown', cycleHasData: false }),
      baseInput({ accountAmount: 0 }),
      baseInput({ accountAmount: null, subjectDataState: 'no_data' }),
    ]
    for (const input of inputs) {
      const d = decideTrim(input)
      if (d.verdict === 'auto_trim') {
        expect(d.reasonCode, 'auto_trim 只允许 no_data 一种成因').toBe('no_data')
      }
    }
  })
})

describe('[类 B] Property 5: 决策顺序短路性', () => {
  it('风险保护命中时，金额与重要性取值变化不改变 verdict', async () => {
    const { decideTrim } = await loadPure(P_DECISION, '../procedureTrimDecision', 'Task 7')
    const variants = [
      { accountAmount: 0 },
      { accountAmount: 1 },
      { materiality: null },
      { materiality: { performanceMateriality: 1, trivialThreshold: 1 } },
    ]
    const results = variants.map(
      (v) => decideTrim(baseInput({ risk: { maxRisk: 'H', hasSpecial: false }, ...v })).verdict,
    )
    expect(new Set(results).size, `风险保护未短路，得到多种 verdict: ${results.join(',')}`).toBe(1)
    expect(results[0]).toBe('keep')
  })

  it('数据存在性命中时，重要性取值变化不改变 verdict', async () => {
    const { decideTrim } = await loadPure(P_DECISION, '../procedureTrimDecision', 'Task 7')
    const variants = [
      { materiality: null },
      { materiality: { performanceMateriality: 500_000, trivialThreshold: 25_000 } },
      { materiality: { performanceMateriality: 1, trivialThreshold: 1 } },
    ]
    const results = variants.map(
      (v) => decideTrim(baseInput({ subjectDataState: 'no_data', ...v })).verdict,
    )
    expect(new Set(results).size, `数据存在性未短路: ${results.join(',')}`).toBe(1)
  })
})
