/**
 * 「el-input 只绑 :model-value + @change」棘轮（spec voucher-identity-writeback-and-audit-phase 任务 10 浏览器走查勘误）
 *
 * Element Plus 的 el-input 每次输入后都把原生值重置回 modelValue（源码注释 ensure native input value
 * is controlled）。父组件只听 `@change`、不回写 modelValue 时，打的字立即消失，失焦时 `@change` 拿到的
 * 也是旧值 ⇒ 这种框根本输不进内容（2026-10-27 浏览器实测：D2-7 矩阵视图、D2-8 政策检查的说明框）。
 * 改法：换成 WpCommitInput（失焦 / 回车才提交，`components/workpaper/shared/WpCommitInput.vue`），
 * 或改成 `@update:model-value` / `v-model`。
 *
 * - CLEAN：已改完的文件（抽凭回填宿主与抽凭引擎）必须为 0；
 * - 全前端总数只许降不许升（BASELINE），且基线不得虚高超过 20（改掉一批就把基线降下来）。
 * 🔴 VTU 的 `setValue` 在 input 之后同步补发 change，读到的是还没被重置的值 ⇒ 组件测试用它测这类框
 * 恒绿（这正是它们长期输不进字却没有测试打红的原因）；这条棘轮按源码形态判，不依赖组件测试。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

function findRepoRoot(): string {
  const SENTINEL = join('backend', 'app', 'routers', 'voucher_sampling.py')
  let dir = dirname(fileURLToPath(import.meta.url))
  for (let i = 0; i < 12; i++) {
    try {
      readFileSync(join(dir, SENTINEL))
      return dir
    } catch {
      const parent = resolve(dir, '..')
      if (parent === dir) break
      dir = parent
    }
  }
  throw new Error('未找到仓库根（哨兵 backend/app/routers/voucher_sampling.py）')
}

const SRC = join(findRepoRoot(), 'audit-platform', 'frontend', 'src')
const rel = (p: string) => relative(SRC, p).replace(/\\/g, '/')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === '__tests__') continue
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (name.endsWith('.vue')) out.push(p)
  }
  return out
}

/** 文本框 el-input 的开始标签（el-input-number 输入中自己保管 userInput、失焦才 change，不受影响）；属性值里的 `>` 不截断 */
const TAG = /<el-input(?![-\w])(?:[^>"']|"[^"]*"|'[^']*')*?\/?>/g
const WRITES_BACK = /v-model\b|@update:model-value|@update:modelValue|@input\b|v-on:input/

/** 只绑 :model-value、只听 @change、不回写的文本框个数 */
function countCommitOnlyInputs(text: string): number {
  let n = 0
  for (const m of text.matchAll(TAG)) {
    const tag = m[0]
    if ((tag.includes(':model-value') || tag.includes(':modelValue')) && tag.includes('@change') && !WRITES_BACK.test(tag)) n += 1
  }
  return n
}

/** 已改完的文件：再出现即打红 */
const CLEAN = [
  'components/workpaper/shared/WpCommitInput.vue',
  'components/workpaper/voucher-sampling/GtVoucherSamplingEngine.vue',
  'components/workpaper/d1/D1TabVoucherCheck.vue',
  'components/workpaper/d2/D2VcMatrixView.vue',
  'components/workpaper/d3/D3TabVoucherCheck.vue',
  'components/workpaper/d5/D5TabVoucherCheck.vue',
  'components/workpaper/d6/D6TabVoucherCheck.vue',
  'components/workpaper/d7/D7TabVoucherCheck.vue',
  'components/workpaper/d7/D7VoucherCheckTable.vue',
  'components/workpaper/e1/E1TabBankFlowReconcile.vue',
  'components/workpaper/e1/E1TabLargeCheck.vue',
  // 任务 11（F / G 宿主）
  'components/workpaper/g1-trading-financial-assets/inspection/G1TabDerivativeCheck.vue',
  'components/workpaper/g1-trading-financial-assets/inspection/G1TabVoucherCheck.vue',
  'components/workpaper/g2-interest-receivable/G2TabVoucherCheck.vue',
  'components/workpaper/g8-other-equity-instruments/voucher/G8TabVoucherCheck.vue',
  'components/workpaper/g9-other-noncurrent-financial/voucher/G9TabVoucherCheck.vue',
  'components/workpaper/g10-trading-financial-liabilities/voucher/G10TabVoucherCheck.vue',
  'components/workpaper/g11-investment-income/voucher/G11TabVoucherCheck.vue',
  'components/workpaper/g12-net-hedge-gains/voucher/G12TabVoucherCheck.vue',
  'components/workpaper/g4-bond-investment-ecl/voucher/G4TabVoucherCheck.vue',
  'components/workpaper/g5-long-term-receivable/voucher/G5TabVoucherCheck.vue',
  'components/workpaper/g6-other-bond-investment-ecl/voucher/G6TabVoucherCheck.vue',
  'components/workpaper/g7-long-term-equity-subsidiary/voucher/G7TabVoucherCheck.vue',
  'components/workpaper/g7-shared/G7VoucherSampleSection.vue',
  'components/workpaper/f1/F1TabComprehensiveCheck.vue',
  'components/workpaper/f1/F1CreditCheckTable.vue',
  'components/workpaper/f2-special/contract/F2TabContractCostCheck.vue',
  'components/workpaper/f2/valuation/F2TabPurchaseInboundCheck.vue',
  'components/workpaper/f2/valuation/F2TabMaterialUsageCheck.vue',
  'components/workpaper/f3-notes-payable/F3TabVoucherCheck.vue',
  'components/workpaper/f3-notes-payable/F3VoucherCheckTable.vue',
  'components/workpaper/f4-accounts-payable/F4TabVoucherCheck.vue',
  'components/workpaper/f4-accounts-payable/F4VoucherCheckTable.vue',
  'components/workpaper/f5-cost-of-sales/F5TabMajorAdjustment.vue',
  'components/workpaper/g3-dividend-receivable/G3TabCalcCheck.vue',
  // 任务 12（H / I 宿主）
  'components/workpaper/h1/inspection/H1TabAdditionCheck.vue',
  'components/workpaper/h1/inspection/H1TabDisposalCheck.vue',
  'components/workpaper/h2/inspection/H2TabAdditionCheck.vue',
  'components/workpaper/h2/inspection/H2TabDecreaseCheck.vue',
  'components/workpaper/h3/inspection/H3TabAdditionCheck.vue',
  'components/workpaper/h4/inspection/H4TabAdditionCheck.vue',
  'components/workpaper/h4/inspection/H4TabDisposalCheck.vue',
  'components/workpaper/h5/inspection/H5TabAdditionCheck.vue',
  'components/workpaper/h5/inspection/H5TabDisposalCheck.vue',
  'components/workpaper/h6/inspection/H6TabCheck.vue',
  'components/workpaper/h8/inspection/H8TabDisposalCheck.vue',
  'components/workpaper/h10/inspection/H10TabCheck.vue',
  'components/workpaper/i1/inspection/I1TabAdditionCheck.vue',
  'components/workpaper/i1/inspection/I1TabDisposalCheck.vue',
  'components/workpaper/i2/cutoff/I2CutoffSampleTable.vue',
  'components/workpaper/i2/cutoff/I2TabCutoffForward.vue',
  'components/workpaper/i2/cutoff/I2TabCutoffBackward.vue',
  'components/workpaper/i2/inspection/I2TabMaterialCheck.vue',
  'components/workpaper/i2/inspection/I2TabOutsourceCheck.vue',
  'components/workpaper/i2/inspection/I2TabStaffCheck.vue',
  'components/workpaper/i2/inspection/I2TabTargetedCheck.vue',
  'components/workpaper/i2/inspection/I2TabWorkHourCheck.vue',
  'components/workpaper/i3/core/I3TabTargetedCheck.vue',
  'components/workpaper/i4/core/I4TabTargetedCheck.vue',
  'components/workpaper/i5/core/I5TabTargetedCheck.vue',
  'components/workpaper/i6/core/I6TabTargetedCheck.vue',
  'components/workpaper/i6/cutoff/I6TabCutoffForward.vue',
  'components/workpaper/i6/cutoff/I6TabCutoffBackward.vue',
  // 任务 13（J、K、M、N 宿主与子表格）
  'components/workpaper/j1/inspection/J1TabGeneralCheck.vue',
  'components/workpaper/k1/inspection/K1TabReceivableCheck.vue',
  'components/workpaper/k2/inspection/K2TabCheck.vue',
  'components/workpaper/k3/inspection/K3RowVoucherTable.vue',
  'components/workpaper/k3/inspection/K3TabLongOutstanding.vue',
  'components/workpaper/k3/inspection/K3TabPayableCheck.vue',
  'components/workpaper/k3/inspection/K3TabRelatedParty.vue',
  'components/workpaper/k4/core/K4TabCheck.vue',
  'components/workpaper/k5/contingency/K5TabLitigationCheck.vue',
  'components/workpaper/k5/contingency/K5TabProvisionCheck.vue',
  'components/workpaper/k7/inspection/K7TabDeferredCheck.vue',
  'components/workpaper/k8/cutoff/K8CutoffS2VTable.vue',
  'components/workpaper/k8/cutoff/K8CutoffV2STable.vue',
  'components/workpaper/k8/cutoff/K8TabCutoffS2V.vue',
  'components/workpaper/k8/cutoff/K8TabCutoffV2S.vue',
  'components/workpaper/k8/inspection/K8TabContractCheck.vue',
  'components/workpaper/k8/inspection/K8TabSellingCheck.vue',
  'components/workpaper/k9/inspection/K9TabAdminCheck.vue',
  'components/workpaper/k10/inspection/K10TabOtherIncomeCheck.vue',
  'components/workpaper/k12/core/K12TabNonOperatingCheck.vue',
  'components/workpaper/k13/core/K13TabNonOperatingCheck.vue',
  'components/workpaper/m1/inspection/M1TabDividendCheck.vue',
  'components/workpaper/m2/inspection/M2TabCapitalCheck.vue',
  'components/workpaper/n2/inspection/N2TabTaxCheck.vue',
]

/**
 * 2026-10-27 现算：改完任务 10 的 9 个文件后 481 个文件 1965 处；任务 11 改完 G 宿主后 474 个文件 1914 处；再改完 F 宿主后
 * 466 个文件 1828 处；G3-4 后 1825 处；任务 12 改完 H / I 宿主（21 个文件 54 处）后 1771 处；任务 13 改完 J、K、M、N 宿主（6 个文件 33 处）后 1738 处。只许降
 * 2026-10-28 合入上游后 1748 处（不是本 spec 新增）：oo-writeback-template-parity-closure 9.4f / 9.4g 按模板补列新增 25 处
 * （D2TabBizModel / D2TabPledgeCheck / D2TabRelatedParty / D2TabWriteoffCheck / D6TabRelatedParty / D7TabAnalysis /
 * K3 / K4 / K5TabAdjustment，同样输不进字），GtA121LegalConfirmation 与 AlternativeD05Master 改掉 15 处；拆出的
 * D7VoucherCheckTable 随 D7 凭证检查表换成 WpCommitInput（进 CLEAN）。新增的 25 处登记在本 spec 任务 14 发现未修
 */
const BASELINE = 1748

describe('el-input 只绑 :model-value + @change（打字即被还原）棘轮', () => {
  const counts = new Map(walk(SRC).map(p => [rel(p), countCommitOnlyInputs(readFileSync(p, 'utf-8'))]))
  const total = [...counts.values()].reduce((a, b) => a + b, 0)

  it('判据自检：坏写法计数、回写写法与 el-input-number 不计', () => {
    expect(countCommitOnlyInputs('<el-input :model-value="row.a" size="small" @change="(v: string) => set(row, \'a\', v > 0 ? v : \'\')" />')).toBe(1)
    expect(countCommitOnlyInputs('<el-input\n  type="textarea"\n  :model-value="note"\n  @change="save"\n>\n</el-input>')).toBe(1)
    expect(countCommitOnlyInputs('<el-input :model-value="a" @update:model-value="v => a = v" @change="save" />')).toBe(0)
    expect(countCommitOnlyInputs('<el-input v-model="a" @change="save" />')).toBe(0)
    expect(countCommitOnlyInputs('<el-input-number :model-value="a" @change="save" />')).toBe(0)
    expect(countCommitOnlyInputs('<WpCommitInput :model-value="a" @change="save" />')).toBe(0)
    expect(countCommitOnlyInputs('<el-input :model-value="label" readonly />')).toBe(0)
  })

  it('已改完的文件为 0（换 WpCommitInput 或改回写写法）', () => {
    for (const f of CLEAN) expect(counts.has(f), `${f} 不存在（改名了就同步清单）`).toBe(true)
    const dirty = CLEAN.filter(f => (counts.get(f) ?? 0) > 0).map(f => `${f}: ${counts.get(f)}`)
    expect(dirty).toEqual([])
  })

  it(`全前端只许降不许升（基线 ${BASELINE}），基线不得虚高超过 20`, () => {
    expect(total, '新增了「只绑 :model-value + @change」的文本框：换 WpCommitInput').toBeLessThanOrEqual(BASELINE)
    expect(BASELINE - total, `已降到 ${total}：把 BASELINE 改成现算值`).toBeLessThanOrEqual(20)
  })
})
