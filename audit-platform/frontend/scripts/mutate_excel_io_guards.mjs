#!/usr/bin/env node
/**
 * excelIo 收敛守卫的变异检验 —— spec: frontend-excel-io-single-entry-convergence
 *   (Requirements 5.2 / 5.3 · Property 26)
 *
 * ## 为什么需要它
 *
 * memory 铁律：「每写完守卫必做变异检验，没打红=守卫有缺陷不是代码没问题」。
 * 守卫本身可能是假绿的 —— 例如断言「解析后 Object.prototype 未被污染」看着严格，
 * 实则因 xlsx 单元格值只能是标量而永远成立（撤掉防护也绿）。只有对每条判据各注入
 * 一个变异、确认它**确实打红且红的正是预期那条**，守卫才算立住。
 *
 * ## 四态判定（按失败测试名集合差集，不看退出码）
 *
 *   RED         —— 打红，且失败集合恰好覆盖预期测试名 ⇒ 守卫有效
 *   GREEN       —— 未打红 ⇒ **守卫缺陷**，判据没落到行为上
 *   ANCHOR-MISS —— 锚点未命中或命中 >1 处 ⇒ **脚本缺陷**，本次结论无效
 *   WRONG-TEST  —— 打红了但不是预期项 ⇒ 污染残留或锚点错行
 *
 * 只看退出码会把后三态全误判成 RED，这是变异检验最常见的自欺形式。
 *
 * ## 用法
 *
 *   node scripts/mutate_excel_io_guards.mjs --list
 *   node scripts/mutate_excel_io_guards.mjs --run
 *   node scripts/mutate_excel_io_guards.mjs --run --mid M3
 *   node scripts/mutate_excel_io_guards.mjs --restore     # 异常中断后手工还原
 */
import fs from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'

// ── 仓库定位（双哨兵，禁写死回退级数）──
function findRoot() {
  let dir = process.cwd()
  for (let i = 0; i < 12; i += 1) {
    if (
      fs.existsSync(path.join(dir, 'audit-platform', 'frontend', 'package.json')) &&
      fs.existsSync(path.join(dir, 'audit-platform', 'frontend', 'src', 'composables', 'useExcelIO.ts'))
    ) {
      return dir
    }
    dir = path.dirname(dir)
  }
  throw new Error('repo root not found (双哨兵均未命中)')
}

const ROOT = findRoot()
const FE = path.join(ROOT, 'audit-platform', 'frontend')
const ENTRY = path.join(FE, 'src', 'composables', 'useExcelIO.ts')

const SPEC_SECURITY = 'src/composables/__tests__/useExcelIO.security.spec.ts'
const SPEC_NEWAPI = 'src/composables/__tests__/useExcelIO.newApi.spec.ts'
const SPEC_CONVERGE = 'src/composables/__tests__/excelIoConvergence.spec.ts'
const SPEC_EQUIV = 'src/composables/__tests__/excelIoEquivalence.spec.ts'
const SPEC_EXCELJS = 'src/composables/__tests__/useExcelIO.excelJs.spec.ts'
const SPEC_SHEETNAME = 'src/components/consolidation/__tests__/consolNoteSheetName.spec.ts'

/** 进度基线本身也是被守卫对象（M18~M20 变异它，验「清单漏记」能不能被拦住） */
const BASELINE = path.join(FE, 'src', 'composables', '__tests__', '_baseline', 'excelIoConvergence.baseline.json')

/**
 * 变异清单。
 *
 * 锚点一律**单行**：memory 已记「`\n` 跨行锚点在 CRLF 必 ANCHOR-MISS」。
 * `expect` 是预期打红的测试名子串（用子串以免测试名微调就失效）。
 */
const MUTATIONS = [
  {
    id: 'M1',
    desc: '撤掉 _BLOCKED_KEYS 过滤（原型污染防护失效）',
    file: ENTRY,
    anchor: '    if (_BLOCKED_KEYS.has(h)) {',
    replace: '    if (false && _BLOCKED_KEYS.has(h)) {',
    specs: [SPEC_SECURITY],
    expect: ['危险列头不进 headers', '危险列头不进行对象的自有键', 'blockedKeys 如实回报'],
  },
  // M2（customInstructionSheet 互斥改静默择一）已随该选项一并删除，2026-08-14：
  // 该选项零生产消费方，功能被 L1-5（多 sheet 纯 AOA 形态）覆盖。
  {
    id: 'M3',
    desc: 'successMessage:false 失效（封装强行弹提示）',
    file: ENTRY,
    anchor: '  if (msg === false) return',
    replace: '  if (false) return',
    specs: [SPEC_NEWAPI],
    expect: ['传 false 时不弹', 'exportMultiSheetData 三态一致'],
  },
  {
    id: 'M4',
    desc: '列索引改回「过滤后下标」（复现既有错位缺陷）',
    file: ENTRY,
    anchor: '    headerEntries.push({ header: h, colIdx: i })',
    replace: '    headerEntries.push({ header: h, colIdx: headerEntries.length })',
    specs: [SPEC_SECURITY],
    expect: ['表头中间有空列时后续列不错位', '危险列头位于中间时后续列不错位'],
  },
  {
    id: 'M5',
    desc: '行数上限失效（不截断）',
    file: ENTRY,
    anchor: '    if (rows.length >= maxRows) {',
    replace: '    if (false && rows.length >= maxRows) {',
    specs: [SPEC_SECURITY],
    expect: ['超过 maxRows 时截断且回报被丢弃条数'],
  },
  {
    id: 'M7',
    // 锚点已随 B1 迁移更新：原本钉在 `ws['!cols'] = headers.map(...wch:16)`，
    // 迁移后改为 exportData 的 `columns[].width`，那行不复存在（曾 ANCHOR-MISS）。
    desc: 'queryExport 列宽 16 → 20（模拟迁移时列宽算法被换掉）',
    file: path.join(FE, 'src', 'components', 'query', 'queryExport.ts'),
    anchor: '    columns: columns.map(c => ({ key: c, header: labelFn(c), width: 16 })),',
    replace: '    columns: columns.map(c => ({ key: c, header: labelFn(c), width: 20 })),',
    specs: [SPEC_EQUIV],
    expect: ['导出产物与迁移前逐项等价', '空行集也能导出'],
  },
  // M8（batchExport 表头灰底）已随被测代码删除：`utils/batchExport.ts` 整条链
  // 是用户不可达的孤儿功能，2026-08-14 经用户裁决删掉，连带 headerStyle 覆写通道。
  {
    id: 'M9',
    desc: 'readWorkbookAoa 改成逐 sheet 重新解析（抹掉本 API 的存在理由）',
    file: ENTRY,
    anchor: '    const ws = wb.Sheets[name]',
    replace: "    const ws = (XLSX.read(await file.arrayBuffer(), { type: 'array' })).Sheets[name]",
    specs: [SPEC_NEWAPI],
    expect: ['只解析一次'],
  },
  {
    id: 'M10',
    // 锚点已随「加 truncatedRows 回报」的重构更新（2026-08-14）：原先是单行三元表达式，
    // 现在拆成了 if/continue + slice 两段。清单静态自检当场抓到了这次 stale。
    desc: 'readWorkbookAoa 空 sheet 返回 undefined（调用方 .length 会抛）',
    file: ENTRY,
    anchor: '    sheets[name] = all.slice(0, maxRows)',
    replace:
      '    sheets[name] = all.slice(0, maxRows); if (sheets[name].length === 0) sheets[name] = undefined as any',
    specs: [SPEC_NEWAPI],
    expect: ['空 sheet 返回空数组'],
  },
  {
    id: 'M11',
    desc: 'readWorkbookAoa 的 sheetNames 排序（破坏工作簿内顺序）',
    file: ENTRY,
    anchor: '  const sheetNames: string[] = [...(wb.SheetNames || [])]',
    replace: '  const sheetNames: string[] = [...(wb.SheetNames || [])].sort()',
    specs: [SPEC_NEWAPI],
    expect: ['sheetNames 保持工作簿内顺序'],
  },
  {
    id: 'M12',
    desc: 'loadExcelJsWorkbook 的 source 分流改回 instanceof ArrayBuffer（复现踩过的坑）',
    file: ENTRY,
    anchor: "    typeof (source as any)?.arrayBuffer === 'function'",
    replace: '    !(source instanceof ArrayBuffer)',
    specs: [SPEC_EXCELJS],
    expect: ['冻结窗格能真的写出去', 'loadExcelJsWorkbook 接受 ArrayBuffer', 'row.values 仍是 1-based'],
  },
  {
    id: 'M13',
    desc: 'createExcelJsWorkbook 变回调式（调用方失去写出前的判断时机）',
    file: ENTRY,
    anchor: 'export async function createExcelJsWorkbook(): Promise<{',
    replace: 'export async function createExcelJsWorkbook(_build: (wb: any) => void): Promise<{',
    specs: [SPEC_EXCELJS],
    expect: ['非回调式'],
  },
  {
    id: 'M14',
    desc: 'vertical 改回非法值 middle（复现让 openpyxl 打不开文件的既有缺陷）',
    file: ENTRY,
    anchor: "const _STYLE_VERTICAL = 'center' as const",
    replace: "const _STYLE_VERTICAL = 'middle' as const",
    specs: [SPEC_EXCELJS],
    expect: ['vertical 只写 OOXML 合法值'],
  },
  {
    id: 'M17',
    desc: 'readWorkbookAoa 不回报截断（退回静默丢数据，违反 R4.3）',
    file: ENTRY,
    anchor: '    if (all.length > maxRows) truncatedRows[name] = all.length - maxRows',
    replace: '    void 0',
    specs: [SPEC_NEWAPI],
    expect: ['截断必须如实回报 truncatedRows'],
  },
  {
    id: 'M15',
    desc: 'uniqueSheetName 退回「只 add 不 check」（去重变死参数 → 撞名时整批导出失败）',
    file: path.join(FE, 'src', 'components', 'consolidation', 'ConsolNoteTab.vue'),
    anchor: '  if (!usedNames.has(base)) {',
    replace: '  if (true) {',
    specs: [SPEC_SHEETNAME],
    // 🔴 只期望「源码一致性」那条红，不期望行为类测试红 —— 因为该 spec 里的
    // uniqueSheetName 是**副本**（.vue 的 script setup 内部函数无法 import），
    // 变异生产源码不会影响副本的行为测试。这恰恰说明「源码一致性」那条兜底测试
    // 是不可省的：没有它，变异生产代码时全部测试都不红，守卫完全失效。
    expect: ['生产源码与本文件的算法保持一致'],
  },
  {
    id: 'M16',
    desc: 'uniqueSheetName 加后缀时不为后缀预留位置（拼完超 31，Excel 仍拒绝）',
    file: path.join(FE, 'src', 'components', 'consolidation', 'ConsolNoteTab.vue'),
    anchor: '    const candidate = base.substring(0, 31 - suffix.length) + suffix',
    replace: '    const candidate = base + suffix',
    specs: [SPEC_SHEETNAME],
    // 同 M15：只「源码一致性」会红（行为测试跑的是副本）
    expect: ['生产源码与本文件的算法保持一致'],
  },
  // ───────────────────────────────────────────────────────────────────────
  // M18~M20：变异**进度基线自身**。
  //
  // 起因是 2026-08-14 提交前发现的一次真实漏记：`B2-14/14` 那批 13 个 confirmation
  // 文件只写在 `note` 的自然语言里（"其余 13 个：GtConfirmationSummary · …"），
  // `files` 数组是空的。后果连锁三处 —— 按 files 精确 stage 的脚本漏掉它们（远端
  // 仍带裸 import ⇒ CI 必红）、CI 的 Vite 编译扫描只覆盖 33/46、成果计数不自洽。
  //
  // 教训：写在 note 里等于没写。补了两条守卫把判据落到 files 数组上，这三条变异
  // 证明那两条守卫真能拦住同类漏记（当时它们不存在，所以漏记一路走到了提交前）。
  // ───────────────────────────────────────────────────────────────────────
  {
    id: 'M18',
    desc: '基线 files 漏记一个文件（复刻 2026-08-14 的 B2 漏 13 个）',
    file: BASELINE,
    anchor: '        "components/workpaper/confirmation/GtConfirmationSummary.vue",',
    replace: '',
    specs: [SPEC_CONVERGE],
    expect: ['_progress[].files 覆盖完整'],
  },
  {
    id: 'M19',
    desc: '基线 files 里的路径写错（CI 的 --from-baseline 编译扫描会直接失败）',
    file: BASELINE,
    anchor: '        "components/workpaper/confirmation/wealthList/GtConfirmationWealthList.vue"',
    replace: '        "components/workpaper/confirmation/wealthList/__GhostFile__.vue"',
    specs: [SPEC_CONVERGE],
    expect: ['_progress[].files 声明即已迁'],
  },
  {
    id: 'M20',
    desc: '把已删文件塞回 files（删除被算成迁移成果，进度虚高）',
    file: BASELINE,
    anchor: '        "components/workpaper/confirmation/reliability/GtConfirmationReliability.vue",',
    replace:
      '        "components/workpaper/confirmation/reliability/GtConfirmationReliability.vue",\n        "utils/batchExport.ts",',
    specs: [SPEC_CONVERGE],
    expect: ['_progress[].files 覆盖完整'],
  },
  {
    id: 'M6',
    desc: '新增一处裸 import（模拟收敛回退）',
    newFile: path.join(FE, 'src', 'composables', '__mutation_probe_M6.ts'),
    content: "export async function probe() { const X = await import('xlsx'); return X }\n",
    specs: [SPEC_CONVERGE],
    expect: ['生产文件零裸 import', '基线 current 与实测一致', '进度基线未上调'],
  },
]

// ── vitest 执行与失败集合提取 ──
function runSpecs(specs) {
  const res = spawnSync(
    process.platform === 'win32' ? 'npx.cmd' : 'npx',
    ['vitest', 'run', ...specs, '--reporter=dot'],
    { cwd: FE, encoding: 'utf-8', shell: process.platform === 'win32', maxBuffer: 64 * 1024 * 1024 },
  )
  const raw = `${res.stdout || ''}\n${res.stderr || ''}`.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
  const failed = new Set()
  for (const m of raw.matchAll(/FAIL\s+\S+\s*>\s*(.+)/g)) {
    failed.add(m[1].trim())
  }
  const summary = raw.match(/Tests\s+(?:(\d+)\s+failed\s*\|\s*)?(\d+)\s+passed\s*\((\d+)\)/)
  return {
    failed,
    passed: summary ? Number(summary[2]) : -1,
    failedCount: summary ? Number(summary[1] || 0) : -1,
    ok: res.status === 0,
  }
}

function classify(mut, baseFailed, mutFailed) {
  const newlyFailed = [...mutFailed].filter((t) => !baseFailed.has(t))
  if (newlyFailed.length === 0) return { verdict: 'GREEN', newlyFailed }
  const hitExpected = mut.expect.filter((e) => newlyFailed.some((t) => t.includes(e)))
  if (hitExpected.length === 0) return { verdict: 'WRONG-TEST', newlyFailed }
  return { verdict: 'RED', newlyFailed, hitExpected }
}

// ── 主流程 ──
const args = process.argv.slice(2)
const wantList = args.includes('--list')
const wantRun = args.includes('--run')
const wantRestore = args.includes('--restore')
const midIdx = args.indexOf('--mid')
const onlyMid = midIdx >= 0 ? args[midIdx + 1] : null

/**
 * 清单静态自检 —— **不改任何文件**，故可挂 CI
 *
 * 变异检验有两类会静默失效的 stale，而它们只在有人手工跑 `--run` 时才暴露：
 *
 * 1. **锚点漂移** —— 生产代码重构后锚点不再命中（或命中多处）。表现为 ANCHOR-MISS。
 *    2026-08-12 实测踩了三次：M7/M8 的锚点写的是 B1 **迁移前**的代码，迁移后那两行
 *    根本不存在；M12 把缩进猜成 6 空格而实际 4 空格。
 * 2. **测试名漂移** —— spec 里的测试名改了但 `expect` 没同步。表现为 WRONG-TEST，
 *    或更坏：`expect` 恰好匹配了另一条测试，于是变异「看起来 RED」但钉的不是原意。
 *
 * 两者都让变异检验退化成自我安慰。故本自检在 CI 里静态校验：
 *   - 锚点在目标文件命中**恰好 1 次**
 *   - 每条 `expect` 字符串能在其 spec 文件里找到
 */
function verifyList() {
  const problems = []

  for (const m of MUTATIONS) {
    // ── 锚点命中数 ──
    if (m.newFile) {
      // 新建文件型变异无锚点，只校验目录存在
      if (!fs.existsSync(path.dirname(m.newFile))) {
        problems.push(`${m.id}: 目标目录不存在 ${path.dirname(m.newFile)}`)
      }
    } else {
      if (!fs.existsSync(m.file)) {
        problems.push(`${m.id}: 目标文件不存在 ${path.relative(FE, m.file)}`)
      } else {
        const hits = fs.readFileSync(m.file, 'utf-8').split(m.anchor).length - 1
        if (hits !== 1) {
          problems.push(
            `${m.id}: 锚点命中 ${hits} 处（须恰为 1）—— 生产代码可能已重构，锚点 stale\n` +
              `        文件: ${path.relative(FE, m.file)}\n` +
              `        锚点: ${JSON.stringify(m.anchor)}`,
          )
        }
      }
    }

    // ── expect 能否在 spec 里找到 ──
    const specSources = m.specs.map((s) => {
      const full = path.join(FE, s)
      return fs.existsSync(full) ? fs.readFileSync(full, 'utf-8') : ''
    })
    for (const s of m.specs) {
      if (!fs.existsSync(path.join(FE, s))) problems.push(`${m.id}: spec 文件不存在 ${s}`)
    }
    for (const e of m.expect) {
      if (!specSources.some((src) => src.includes(e))) {
        problems.push(
          `${m.id}: expect ${JSON.stringify(e)} 在其 spec 里找不到 —— 测试名可能已改，` +
            `变异会退化成 WRONG-TEST（或误配到别的测试上）`,
        )
      }
    }
  }

  return problems
}

if (wantList) {
  console.log(`变异清单（共 ${MUTATIONS.length} 条）\n`)
  for (const m of MUTATIONS) {
    console.log(`  ${m.id}  ${m.desc}`)
    console.log(`      目标: ${m.newFile ? '新建 ' + path.basename(m.newFile) : path.basename(m.file)}`)
    console.log(`      期望打红: ${m.expect.join(' / ')}`)
  }

  console.log('\n── 清单静态自检（锚点命中数 + expect 能否匹配真实测试名）──')
  const problems = verifyList()
  if (problems.length === 0) {
    console.log(`✅ ${MUTATIONS.length} 条变异的锚点与 expect 全部有效`)
    process.exit(0)
  }
  console.log(`🔴 发现 ${problems.length} 处 stale：\n`)
  for (const p of problems) console.log(`  ${p}`)
  console.log('\n变异清单 stale 会让检验静默退化（ANCHOR-MISS 或钉错测试），请修到全绿。')
  process.exit(1)
}

if (wantRestore) {
  let n = 0
  // 遍历全部变异声明的目标文件，各自从自己的 .mutbak 还原
  for (const m of MUTATIONS) {
    if (m.file) {
      const bak = `${m.file}.mutbak`
      if (fs.existsSync(bak)) {
        fs.copyFileSync(bak, m.file)
        fs.unlinkSync(bak)
        console.log(`已还原 ${path.relative(FE, m.file)}`)
        n += 1
      }
    }
    if (m.newFile && fs.existsSync(m.newFile)) {
      fs.unlinkSync(m.newFile)
      console.log(`已删除残留探针 ${path.basename(m.newFile)}`)
      n += 1
    }
  }
  console.log(n === 0 ? '无残留，无需还原' : `共处理 ${n} 项`)
  process.exit(0)
}

if (!wantRun) {
  console.log('用法: --list | --run [--mid M3] | --restore')
  process.exit(1)
}

const targets = onlyMid ? MUTATIONS.filter((m) => m.id === onlyMid) : MUTATIONS
if (targets.length === 0) {
  console.error(`未找到变异 ${onlyMid}`)
  process.exit(1)
}

// 基线：先跑一次拿到「变异前就已失败」的集合（防把既有红误判成变异战果）
const allSpecs = [...new Set(targets.flatMap((m) => m.specs))]
console.log(`跑基线（${allSpecs.length} 个 spec）...`)
const base = runSpecs(allSpecs)
console.log(`  基线: 通过 ${base.passed} / 失败 ${base.failedCount}`)
if (base.failed.size > 0) {
  console.log(`  基线已失败项（将从变异战果中扣除）:`)
  for (const t of base.failed) console.log(`    - ${t}`)
}
console.log()

const results = []

/**
 * 🔴 备份必须 per-mutation。
 *
 * 早先版本只备份 `ENTRY` 一个文件，还原时无论变异目标是谁都写回 ENTRY 的内容 ——
 * 一旦某条变异的目标是别的文件（如 M7 的 queryExport.ts），还原就会把
 * useExcelIO.ts 的整份内容覆盖进那个文件，直接写坏生产代码。
 */
for (const mut of targets) {
  process.stdout.write(`${mut.id} ${mut.desc} ... `)

  let backup = null
  let applied = false
  try {
    if (mut.newFile) {
      fs.writeFileSync(mut.newFile, mut.content, 'utf-8')
      applied = true
    } else {
      if (!fs.existsSync(mut.file)) {
        console.log(`ANCHOR-MISS（目标文件不存在: ${mut.file}）`)
        results.push({ id: mut.id, verdict: 'ANCHOR-MISS', reason: 'file missing' })
        continue
      }
      const src = fs.readFileSync(mut.file, 'utf-8')
      const hits = src.split(mut.anchor).length - 1
      if (hits !== 1) {
        console.log(`ANCHOR-MISS（锚点命中 ${hits} 处，须恰为 1）`)
        results.push({ id: mut.id, verdict: 'ANCHOR-MISS', hits })
        continue
      }
      backup = src
      fs.writeFileSync(`${mut.file}.mutbak`, src, 'utf-8')
      fs.writeFileSync(mut.file, src.replace(mut.anchor, mut.replace), 'utf-8')
      applied = true
    }

    const after = runSpecs(mut.specs)
    const { verdict, newlyFailed, hitExpected } = classify(mut, base.failed, after.failed)
    console.log(verdict)
    if (verdict !== 'RED') {
      console.log(`    新增失败: ${newlyFailed.length ? newlyFailed.join(' | ') : '(无)'}`)
      console.log(`    期望包含: ${mut.expect.join(' | ')}`)
    } else {
      console.log(`    命中 ${hitExpected.length}/${mut.expect.length} 条预期，新增失败 ${newlyFailed.length} 项`)
    }
    results.push({ id: mut.id, verdict, newlyFailed, hitExpected })
  } finally {
    if (applied) {
      if (mut.newFile) {
        if (fs.existsSync(mut.newFile)) fs.unlinkSync(mut.newFile)
      } else if (backup !== null) {
        // 用**该文件自己**的备份还原
        fs.writeFileSync(mut.file, backup, 'utf-8')
        if (fs.existsSync(`${mut.file}.mutbak`)) fs.unlinkSync(`${mut.file}.mutbak`)
      }
    }
  }
}

// ── 汇总 ──
console.log('\n══════ 汇总 ══════')
const counts = {}
for (const r of results) counts[r.verdict] = (counts[r.verdict] || 0) + 1
for (const [k, v] of Object.entries(counts)) console.log(`  ${k}: ${v}`)

const bad = results.filter((r) => r.verdict !== 'RED')
if (bad.length > 0) {
  console.log('\n🔴 以下变异未达 RED —— 守卫或脚本有缺陷，必须修到 RED：')
  for (const r of bad) console.log(`  ${r.id}: ${r.verdict}`)
  process.exit(1)
}
console.log(`\n✅ 全部 ${results.length} 条变异均为 RED，守卫有效`)
