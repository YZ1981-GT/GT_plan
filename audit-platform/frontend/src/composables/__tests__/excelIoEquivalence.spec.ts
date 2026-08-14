/**
 * 行为等价守卫 —— Wave 1 Task 2（迁移前快照）+ Wave 3~4 各批验证
 * spec: frontend-excel-io-single-entry-convergence
 *   (Requirements 2.1~2.6 / 5.4 / 5.5 · Property 6~11 / 28 / 29)
 *
 * ## 快照必须在改动前抓
 *
 * 事后补抓等于把「迁移后的结果」当基线，守卫会永远绿 —— memory 已把「守卫把错值
 * 当基线锁死」列为假绿三源之一。故本文件的基线 JSON 由 `UPDATE_EXCEL_SNAPSHOT=1`
 * 显式生成，且**生成动作只在迁移前做一次**。
 *
 * ## 为什么不用 vitest 内置 toMatchSnapshot
 *
 * 内置快照在文件缺失时**静默新建并判绿**。若基线被误删或被 `-u` 顺手刷新，
 * 回归就此消失且无人察觉。这里改为：基线缺失时**报错并提示显式生成命令**。
 *
 * ## 禁 HEAD-swap（R5.5 / Property 29）
 *
 * 工作树长期有并发会话改动，`git stash` / `git checkout` 取基线会连带别人的改动一起
 * 换进换出，基线自身就漂了。故基线一律是磁盘上的 JSON 文件。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import {
  diffSnapshots,
  formatDiffs,
  snapshotWorkbook,
  type WorkbookSnapshot,
} from './_helpers/workbookSnapshot'

// ── mock ElMessage ──
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

// ── 捕获落盘调用（两个库都要拦：迁移前后写引擎可能不同）──
const captured: Array<{ fileName: string; wb: any }> = []

function makeWriteFileStub() {
  return (wb: any, fileName: string) => {
    captured.push({ fileName, wb })
  }
}

vi.mock('xlsx', async (importOriginal) => {
  const actual: any = await importOriginal()
  const stub = makeWriteFileStub()
  return {
    ...actual,
    writeFile: stub,
    writeFileXLSX: stub,
    default: { ...actual, writeFile: stub, writeFileXLSX: stub },
  }
})

vi.mock('xlsx-js-style', async () => {
  const actual: any = await vi.importActual('xlsx-js-style')
  const real: any = actual.default && actual.default.utils ? actual.default : actual
  const stub = makeWriteFileStub()
  return {
    ...real,
    writeFile: stub,
    writeFileXLSX: stub,
    default: { ...real, writeFile: stub, writeFileXLSX: stub },
  }
})

// ═══════════════════════════════════════════════════════════════════════════
// 基线读写
// ═══════════════════════════════════════════════════════════════════════════

const BASELINE_DIR = path.join(__dirname, '_baseline', 'equivalence')
const UPDATE = process.env.UPDATE_EXCEL_SNAPSHOT === '1'

function baselinePath(key: string): string {
  return path.join(BASELINE_DIR, `${key}.json`)
}

/**
 * 与基线比对；`UPDATE_EXCEL_SNAPSHOT=1` 时写入基线。
 *
 * 基线缺失且非 UPDATE 模式 ⇒ **报错**，不静默新建。
 */
function assertMatchesBaseline(key: string, actual: WorkbookSnapshot): void {
  const file = baselinePath(key)

  if (UPDATE) {
    fs.mkdirSync(BASELINE_DIR, { recursive: true })
    fs.writeFileSync(file, `${JSON.stringify(actual, null, 2)}\n`, 'utf-8')
    return
  }

  if (!fs.existsSync(file)) {
    throw new Error(
      `行为等价基线缺失: ${path.relative(process.cwd(), file)}\n` +
        '基线必须在迁移前生成。若这是首次建立，请在**改动调用方之前**运行：\n' +
        '  UPDATE_EXCEL_SNAPSHOT=1 npx vitest run src/composables/__tests__/excelIoEquivalence.spec.ts\n' +
        '（PowerShell: $env:UPDATE_EXCEL_SNAPSHOT=1 后再跑）\n' +
        '🔴 若迁移已经开始，不要现在生成 —— 那会把迁移后的结果当基线，守卫从此永远绿。',
    )
  }

  const expected = JSON.parse(fs.readFileSync(file, 'utf-8')) as WorkbookSnapshot
  const diffs = diffSnapshots(expected, actual)
  expect(diffs.length, formatDiffs(key, diffs)).toBe(0)
}

beforeEach(() => {
  captured.length = 0
})

/** 取唯一一次落盘捕获，多于一次即判错（防调用方误写两份） */
function soleCapture(): { fileName: string; wb: any } {
  expect(captured.length, `期望恰好一次落盘调用，实得 ${captured.length} 次`).toBe(1)
  return captured[0]
}

// ═══════════════════════════════════════════════════════════════════════════
// B1 批 —— 次级封装（纯 TS 模块，可直接调用，快照最可靠，故作为姿势样板）
// ═══════════════════════════════════════════════════════════════════════════

describe('B1 · components/query/queryExport.ts', () => {
  const INPUT = {
    columns: ['account_code', 'account_name', 'closing_balance'],
    rows: [
      { account_code: '1002', account_name: '银行存款', closing_balance: 1234567.5 },
      { account_code: '1012', account_name: '其他货币资金', closing_balance: 0 },
      { account_code: '1122', account_name: '应收账款', closing_balance: -890.25 },
    ],
    labelFn: (k: string) => ({ account_code: '科目编码', account_name: '科目名称', closing_balance: '期末余额' })[k] || k,
    fileName: '高级查询_2025年度',
    sheetName: '查询结果',
  }

  it('导出产物与迁移前逐项等价', async () => {
    const { exportQueryResultToXlsx } = await import('../../components/query/queryExport')
    await exportQueryResultToXlsx(INPUT)

    const { fileName, wb } = soleCapture()
    assertMatchesBaseline('b1-queryExport-basic', snapshotWorkbook(wb, fileName))
  })

  it('文件名清洗规则不变（非法字符 + emoji）', async () => {
    const { exportQueryResultToXlsx, sanitizeExportName } = await import('../../components/query/queryExport')

    // 纯函数层面先锁死
    expect(sanitizeExportName('a/b:c*d?e"f<g>h|i')).toBe('a_b_c_d_e_f_g_h_i')
    expect(sanitizeExportName('  报表📊导出  ')).toBe('报表导出')
    expect(sanitizeExportName('***')).toBe('___')
    expect(sanitizeExportName('📊')).toBe('导出')

    await exportQueryResultToXlsx({ ...INPUT, fileName: 'A/B:C📊' })
    expect(soleCapture().fileName, '落盘文件名应经清洗且带 .xlsx').toBe('A_B_C.xlsx')
  })

  it('空行集也能导出（只有表头）', async () => {
    const { exportQueryResultToXlsx } = await import('../../components/query/queryExport')
    await exportQueryResultToXlsx({ ...INPUT, rows: [] })

    const { fileName, wb } = soleCapture()
    assertMatchesBaseline('b1-queryExport-empty', snapshotWorkbook(wb, fileName))
  })
})

/*
 * ⚠️ 原有 `describe('B1 · utils/batchExport.ts')`（3 例）已随被测代码一并删除。
 *
 * `utils/batchExport.ts` 的 `exportBatchToXlsx` 全库零消费方；唯一可能的调用场景
 * `components/query/BatchQueryResultGroup.vue` 带「合并导出」按钮，但它
 * `emit('merged-export')` 交给父组件，而该组件自身也零消费方 ⇒ 整条链是
 * **用户不可达的功能**。2026-08-14 经用户裁决直接删除（而非接线上线）。
 *
 * 连带删除：`_baseline/equivalence/b1-batchExport-multi.json` 快照、变异 M8、
 * 以及 `ExcelMultiSheetDef.headerStyle`（那个覆写通道是**专为本文件**而加的，
 * 唯一用户消失后即零消费方 —— 留着会让下一个人问「这是给谁用的」）。
 *
 * 保留 B1 的另一半（`components/query/queryExport.ts`，见上方两个 describe）：
 * 它有真实调用方（CustomQueryDialog / CustomQueryTab）。
 */
