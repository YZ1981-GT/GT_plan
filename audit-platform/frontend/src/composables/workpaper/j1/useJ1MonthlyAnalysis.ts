/**
 * useJ1MonthlyAnalysis — J1-4 应付职工薪酬实质性分析表（对齐源模板）
 *
 * 源模板结构：8大指标区块 × 动态部门行 × 12月列
 *   1. 本期计提工资（输入）    5. 上期员工数量（输入）
 *   2. 本期员工数量（输入）    6. 上期人均工资（公式=4/5）
 *   3. 本期人均工资（公式=1/2）7. 人均工资变动率（公式=(3-6)/6）
 *   4. 上期计提工资（输入）    8. 本期各月计提占比（公式）
 * 底部附加：本期实际发放额/本期留存/上年同期留存
 *
 * 前端交互：Tab切换3区段（本期/同期对比/占比与留存） + 统计概览卡片 + 异常高亮
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcChangeRate } from './useJ1FormulaEngine'

// ─── Types ────────────────────────────────────────────────────────────────

export interface DeptMonthlyRow {
  id: string
  deptName: string
  months: number[]  // 12 values
}

/** 一个指标区块的完整数据 */
export interface IndicatorBlock {
  label: string
  isInput: boolean       // true=用户输入, false=公式计算
  totalRow: number[]     // 合计行12个月
  deptRows: DeptMonthlyRow[]
}

export interface MonthlyFluctuation {
  dept: string
  monthIndex: number
  amount: number
  avgDeviation: number
}

// ─── 存储键 ────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'J1-4-monthly-analysis'
const DEPT_KEY = 'J1-4-departments'

// ─── Composable ────────────────────────────────────────────────────────────

export interface UseJ1MonthlyOptions {
  allResponses: Ref<Map<string, { item_id: string; conclusion: string | null; remark: string | null }>>
  saveImmediate: (items: Array<{ item_id: string; conclusion: string | null; remark: string | null }>) => Promise<void>
  isReadonly: Ref<boolean>
}

export function useJ1MonthlyAnalysis(options: UseJ1MonthlyOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  // ─── 部门列表（动态） ─────────────────────────────────────────────────
  const departments = ref<string[]>(['A部门', 'B部门', 'C部门'])

  // ─── 4个输入区块的数据 ─────────────────────────────────────────────────
  // 每个区块: Map<deptName, number[12]>
  const currentAccrual = ref<Map<string, number[]>>(new Map())   // 本期计提工资
  const currentHeadcount = ref<Map<string, number[]>>(new Map()) // 本期员工数量
  const priorAccrual = ref<Map<string, number[]>>(new Map())     // 上期计提工资
  const priorHeadcount = ref<Map<string, number[]>>(new Map())   // 上期员工数量

  // 底部附加
  const actualPaid = ref<number[]>(Array(12).fill(0))       // 本期实际发放额
  const currentRetained = ref<number[]>(Array(12).fill(0))  // 本期留存
  const priorRetained = ref<number[]>(Array(12).fill(0))    // 上年同期留存

  // ─── 初始化空数据 ─────────────────────────────────────────────────────
  function initEmptyBlock(block: Ref<Map<string, number[]>>) {
    const map = new Map<string, number[]>()
    for (const dept of departments.value) {
      map.set(dept, Array(12).fill(0))
    }
    block.value = map
  }

  // ─── Load ──────────────────────────────────────────────────────────────
  function loadAll() {
    // 加载部门
    const deptRaw = allResponses.value.get(DEPT_KEY)?.remark
    if (deptRaw) {
      try {
        const parsed = JSON.parse(deptRaw)
        if (Array.isArray(parsed) && parsed.length > 0) {
          departments.value = parsed.map(String)
        }
      } catch { /* keep default */ }
    }

    // 加载数据
    const raw = allResponses.value.get(STORAGE_KEY)?.remark
    if (raw) {
      try {
        const data = JSON.parse(raw)
        loadBlock(currentAccrual, data.currentAccrual)
        loadBlock(currentHeadcount, data.currentHeadcount)
        loadBlock(priorAccrual, data.priorAccrual)
        loadBlock(priorHeadcount, data.priorHeadcount)
        actualPaid.value = ensureArr(data.actualPaid)
        currentRetained.value = ensureArr(data.currentRetained)
        priorRetained.value = ensureArr(data.priorRetained)
        return
      } catch { /* fall through to init */ }
    }
    // Default init
    initEmptyBlock(currentAccrual)
    initEmptyBlock(currentHeadcount)
    initEmptyBlock(priorAccrual)
    initEmptyBlock(priorHeadcount)
  }

  function loadBlock(block: Ref<Map<string, number[]>>, data: Record<string, number[]> | undefined) {
    const map = new Map<string, number[]>()
    if (data && typeof data === 'object') {
      for (const dept of departments.value) {
        map.set(dept, ensureArr(data[dept]))
      }
    } else {
      for (const dept of departments.value) {
        map.set(dept, Array(12).fill(0))
      }
    }
    block.value = map
  }

  function ensureArr(val: unknown): number[] {
    if (Array.isArray(val) && val.length >= 12) return val.slice(0, 12).map(v => parseNum(v as number))
    return Array(12).fill(0)
  }

  loadAll()

  // ─── Save ──────────────────────────────────────────────────────────────
  let saveTimer: ReturnType<typeof setTimeout> | null = null
  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(persist, 1500)
  }

  function persist() {
    const data = {
      currentAccrual: mapToObj(currentAccrual.value),
      currentHeadcount: mapToObj(currentHeadcount.value),
      priorAccrual: mapToObj(priorAccrual.value),
      priorHeadcount: mapToObj(priorHeadcount.value),
      actualPaid: actualPaid.value,
      currentRetained: currentRetained.value,
      priorRetained: priorRetained.value,
    }
    const items = [
      { item_id: STORAGE_KEY, conclusion: null, remark: JSON.stringify(data) },
      { item_id: DEPT_KEY, conclusion: null, remark: JSON.stringify(departments.value) },
    ]
    items.forEach(it => allResponses.value.set(it.item_id, it))
    saveImmediate(items).catch(() => {})
  }

  function mapToObj(map: Map<string, number[]>): Record<string, number[]> {
    const obj: Record<string, number[]> = {}
    map.forEach((v, k) => { obj[k] = v })
    return obj
  }

  // ─── 更新单元格 ────────────────────────────────────────────────────────
  type BlockName = 'currentAccrual' | 'currentHeadcount' | 'priorAccrual' | 'priorHeadcount'

  function getBlock(name: BlockName): Ref<Map<string, number[]>> {
    switch (name) {
      case 'currentAccrual': return currentAccrual
      case 'currentHeadcount': return currentHeadcount
      case 'priorAccrual': return priorAccrual
      case 'priorHeadcount': return priorHeadcount
    }
  }

  function updateCell(block: BlockName, dept: string, monthIdx: number, value: number) {
    if (isReadonly.value) return
    const map = getBlock(block).value
    const arr = [...(map.get(dept) || Array(12).fill(0))]
    arr[monthIdx] = value
    map.set(dept, arr)
    getBlock(block).value = new Map(map) // trigger reactivity
    scheduleSave()
  }

  function updateBottomCell(field: 'actualPaid' | 'currentRetained' | 'priorRetained', monthIdx: number, value: number) {
    if (isReadonly.value) return
    const target = field === 'actualPaid' ? actualPaid : field === 'currentRetained' ? currentRetained : priorRetained
    const arr = [...target.value]
    arr[monthIdx] = value
    target.value = arr
    scheduleSave()
  }

  // ─── 部门管理 ──────────────────────────────────────────────────────────
  function addDept(name: string) {
    if (isReadonly.value || departments.value.includes(name)) return
    departments.value = [...departments.value, name]
    // 为每个区块添加空行
    for (const block of [currentAccrual, currentHeadcount, priorAccrual, priorHeadcount]) {
      block.value.set(name, Array(12).fill(0))
      block.value = new Map(block.value)
    }
    scheduleSave()
  }

  function removeDept(name: string) {
    if (isReadonly.value) return
    departments.value = departments.value.filter(d => d !== name)
    for (const block of [currentAccrual, currentHeadcount, priorAccrual, priorHeadcount]) {
      block.value.delete(name)
      block.value = new Map(block.value)
    }
    scheduleSave()
  }

  function renameDept(oldName: string, newName: string) {
    if (isReadonly.value || !newName.trim() || oldName === newName) return
    if (departments.value.includes(newName)) return // 避免重名
    departments.value = departments.value.map(d => d === oldName ? newName : d)
    for (const block of [currentAccrual, currentHeadcount, priorAccrual, priorHeadcount]) {
      const data = block.value.get(oldName)
      if (data) {
        block.value.delete(oldName)
        block.value.set(newName, data)
        block.value = new Map(block.value)
      }
    }
    scheduleSave()
  }

  // ─── 公式计算（computed） ──────────────────────────────────────────────

  /** 按部门求合计行（所有部门之和） */
  function calcTotalRow(block: Ref<Map<string, number[]>>): number[] {
    const total = Array(12).fill(0)
    block.value.forEach(arr => { arr.forEach((v, i) => { total[i] += v }) })
    return total
  }

  /** 除法安全（0→0） */
  function divArr(a: number[], b: number[]): number[] {
    return a.map((v, i) => b[i] === 0 ? 0 : v / b[i])
  }

  /** 变动率 = (本期-上期)/|上期| × 100，上期=0时返回0或100 */
  function changeRateArr(cur: number[], prior: number[]): number[] {
    return cur.map((v, i) => calcChangeRate(v, prior[i]))
  }

  // 合计行
  const currentAccrualTotal = computed(() => calcTotalRow(currentAccrual))
  const currentHeadcountTotal = computed(() => calcTotalRow(currentHeadcount))
  const priorAccrualTotal = computed(() => calcTotalRow(priorAccrual))
  const priorHeadcountTotal = computed(() => calcTotalRow(priorHeadcount))

  // 本期人均工资 = 本期计提 / 本期员工
  const currentAvgWage = computed(() => divArr(currentAccrualTotal.value, currentHeadcountTotal.value))
  // 上期人均工资 = 上期计提 / 上期员工
  const priorAvgWage = computed(() => divArr(priorAccrualTotal.value, priorHeadcountTotal.value))
  // 人均变动率
  const avgWageChangeRate = computed(() => changeRateArr(currentAvgWage.value, priorAvgWage.value))

  // 各月占比 = 当月计提合计 / 年合计
  const monthlyProportion = computed(() => {
    const yearTotal = currentAccrualTotal.value.reduce((s, v) => s + v, 0)
    if (yearTotal === 0) return Array(12).fill(0)
    return currentAccrualTotal.value.map(v => (v / yearTotal) * 100)
  })

  // 按部门计算人均
  function deptAvgWage(block: BlockName, dept: string): number[] {
    const accrualBlock = block.startsWith('current') ? currentAccrual : priorAccrual
    const headcountBlock = block.startsWith('current') ? currentHeadcount : priorHeadcount
    const a = accrualBlock.value.get(dept) || Array(12).fill(0)
    const h = headcountBlock.value.get(dept) || Array(12).fill(0)
    return divArr(a, h)
  }

  // ─── 统计概览 ──────────────────────────────────────────────────────────
  const yearAccrualTotal = computed(() => currentAccrualTotal.value.reduce((s, v) => s + v, 0))
  const yearHeadcountAvg = computed(() => {
    const total = currentHeadcountTotal.value.reduce((s, v) => s + v, 0)
    return Math.round(total / 12)
  })
  const yearAvgWage = computed(() => {
    const headTotal = currentHeadcountTotal.value.reduce((s, v) => s + v, 0)
    return headTotal === 0 ? 0 : yearAccrualTotal.value / headTotal
  })
  const yearAvgChangeRate = computed(() => {
    const priorTotal = priorAccrualTotal.value.reduce((s, v) => s + v, 0)
    const priorHead = priorHeadcountTotal.value.reduce((s, v) => s + v, 0)
    const priorAvg = priorHead === 0 ? 0 : priorTotal / priorHead
    return calcChangeRate(yearAvgWage.value, priorAvg)
  })

  // ─── 异常检测（月度偏离均值>30%） ─────────────────────────────────────
  const fluctuations = computed<MonthlyFluctuation[]>(() => {
    const results: MonthlyFluctuation[] = []
    for (const dept of departments.value) {
      const arr = currentAccrual.value.get(dept) || Array(12).fill(0)
      const avg = arr.reduce((s, v) => s + v, 0) / 12
      if (avg === 0) continue
      for (let i = 0; i < 12; i++) {
        const deviation = ((arr[i] - avg) / Math.abs(avg)) * 100
        if (Math.abs(deviation) > 30) {
          results.push({ dept, monthIndex: i, amount: arr[i], avgDeviation: deviation })
        }
      }
    }
    return results
  })

  // ─── 审计说明/结论 ─────────────────────────────────────────────────────
  const auditNote = ref(allResponses.value.get('J1-4-note')?.remark || '')
  const auditConclusion = ref(allResponses.value.get('J1-4-conclusion')?.remark || '')

  function saveOpinion() {
    if (isReadonly.value) return
    const items = [
      { item_id: 'J1-4-note', conclusion: null, remark: auditNote.value },
      { item_id: 'J1-4-conclusion', conclusion: null, remark: auditConclusion.value },
    ]
    items.forEach(it => allResponses.value.set(it.item_id, it))
    saveImmediate(items).catch(() => {})
  }

  return {
    departments,
    currentAccrual,
    currentHeadcount,
    priorAccrual,
    priorHeadcount,
    actualPaid,
    currentRetained,
    priorRetained,
    currentAccrualTotal,
    currentHeadcountTotal,
    priorAccrualTotal,
    priorHeadcountTotal,
    currentAvgWage,
    priorAvgWage,
    avgWageChangeRate,
    monthlyProportion,
    yearAccrualTotal,
    yearHeadcountAvg,
    yearAvgWage,
    yearAvgChangeRate,
    fluctuations,
    auditNote,
    auditConclusion,
    updateCell,
    updateBottomCell,
    addDept,
    removeDept,
    renameDept,
    saveOpinion,
    deptAvgWage,
  }
}
