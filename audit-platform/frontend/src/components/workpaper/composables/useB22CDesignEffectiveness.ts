/**
 * useB22CDesignEffectiveness — B22C 企业层面控制设计有效性评价（缺陷汇总表）
 *
 * 致同 2025 修订版 B22C 源模板「评价设计有效性-缺陷汇总表」的结构化实现。
 *
 * 职责（参照同目录 useB22BFormData.ts / useB22BDeficiency.ts 的范式）：
 * - 数据持久化：GET/PUT /api/workpapers/{wpId}/checklist-responses，item_id 前缀 B22C-
 *   🔴 PUT 请求体绝对不传 project_id（传 wpId 会触发 422 project_mismatch；省略后端从 wp_id 反查）
 * - 结构：源模板 B22C 按 5 个区块（要素）汇总缺陷
 *   控制环境(env) / 风险评估过程(risk) / 信息与沟通(info) / 监督(monitor) / IT一般控制(itgc)
 * - 消费上游缺陷：loadFromUpstream(b22aResponses, b22bResponses)
 *   从 B22A 提取缺陷按 tab 映射到区块；从 B22B 读取严重程度映射为「值得关注的缺陷」
 * - debounce 2000ms 文本保存 + 选择/勾选变更立即保存 + onScopeDispose flush
 */
import { ref, computed, onScopeDispose, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
  wp_ref: string | null
}

export type ChecklistResponse = ChecklistItem

/** 5 个要素区块 key */
export const BLOCK_KEYS = ['env', 'risk', 'info', 'monitor', 'itgc'] as const
export type BlockKey = (typeof BLOCK_KEYS)[number]

/** 区块名称（源模板要素名） */
export const BLOCK_NAMES: Record<BlockKey, string> = {
  env: '控制环境',
  risk: '风险评估过程',
  info: '信息与沟通',
  monitor: '监督',
  itgc: 'IT一般控制',
}

/** 缺陷严重程度（中文，B22C 单一真源；null=未评定） */
export type DeficiencySeverity = '重大缺陷' | '重要缺陷' | '一般缺陷' | null

/** 有效严重程度中文值集合 */
export const SEVERITY_VALUES: Array<Exclude<DeficiencySeverity, null>> = ['重大缺陷', '重要缺陷', '一般缺陷']

/**
 * CAS1152 两级派生：severity 为权威字段。
 * 重大缺陷/重要缺陷 → 值得关注的缺陷（isSignificant=true）；一般缺陷 → 一般控制缺陷（false）。
 */
export function severityIsSignificant(sev: DeficiencySeverity): boolean {
  return sev === '重大缺陷' || sev === '重要缺陷'
}

/** 归一化任意值为合法 severity（否则 null） */
export function normalizeSeverity(v: unknown): DeficiencySeverity {
  return v === '重大缺陷' || v === '重要缺陷' || v === '一般缺陷' ? v : null
}

/** 单条缺陷条目 */
export interface DeficiencyEntry {
  /** 缺陷描述 */
  desc: string
  /** 是否「控制缺陷」 */
  isControlDeficiency: boolean
  /**
   * 是否「值得关注的缺陷」。
   * 🔴 口径：severity 为权威，本字段在 severity 非 null 时由 severityIsSignificant(severity) 派生，避免口径分裂。
   */
  isSignificant: boolean
  /** 严重程度（权威字段，B22C 单一真源；持久化到 B22C-{key}-def-{n}-severity 的 conclusion） */
  severity: DeficiencySeverity
  /** 重要职业判断 */
  judgment: string
}

/** 单个要素区块结构化数据 */
export interface BlockData {
  key: BlockKey
  name: string
  deficiencies: DeficiencyEntry[]
  /** 汇总来看是否表明存在值得关注的缺陷（null=未评价） */
  sectionSignificant: boolean | null
  /** 说明文本 */
  sectionNote: string
}

/** 缺陷统计 */
export interface B22CStats {
  /** 控制缺陷数 */
  controlDeficiencyCount: number
  /** 值得关注的缺陷数 */
  significantCount: number
}

/** 可编辑字段 */
export type DeficiencyField = 'desc' | 'isControlDeficiency' | 'isSignificant' | 'severity' | 'judgment'

/** 值得关注缺陷的迹象（源模板指引，勾选=该迹象存在） */
export const SIGNIFICANT_INDICATORS: string[] = [
  '控制环境无效的证据',
  '风险评估流程无效的证据',
  '审计中发现内部控制未能防止或发现的错报',
  '重述以前期间财务报表以更正重大错报',
  '管理层无力监督财务报表的编制',
]

/** 判断严重程度时应考虑的因素（源模板指引，勾选=已在职业判断中考虑） */
export const SEVERITY_FACTORS: string[] = [
  '错报发生的可能性',
  '相关资产或负债易于发生舞弊或损失',
  '相关金额确定所涉及的主观程度和复杂程度',
  '受缺陷影响的财务报表金额',
  '相关账户或交易类别的交易量',
  '控制对财务报告流程的重要程度',
  '例外情况发生的频率',
  '控制运行的精确度',
  '缺陷之间的相互影响',
]

// ─── 内部工具：从 B22A/B22B item_id 解析 ─────────────────────────────────────

/** B22A tab → B22C 区块映射
 * T1→env、T2→risk、T3→info、T4非IT→env(控制活动缺陷归控制环境区)、T4-IT→itgc、T5→monitor
 */
function b22aTabToBlock(tab: number, isIt: boolean): BlockKey {
  if (isIt) return 'itgc'
  switch (tab) {
    case 1:
      return 'env'
    case 2:
      return 'risk'
    case 3:
      return 'info'
    case 4:
      return 'info' // 源 B22A-4 属信息与沟通(IT)，非 IT 的控制活动缺陷归信息与沟通区
    case 5:
      return 'monitor'
    default:
      return 'env'
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB22CDesignEffectiveness(wpId: Ref<string>, projectId: Ref<string>) {
  // ─── State ────────────────────────────────────────────────────────────────

  const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
  const loading = ref(false)
  const saving = ref(false)

  const overallNote = ref<string>('')

  function makeEmptyBlocks(): Record<BlockKey, BlockData> {
    const out = {} as Record<BlockKey, BlockData>
    for (const key of BLOCK_KEYS) {
      out[key] = {
        key,
        name: BLOCK_NAMES[key],
        deficiencies: [],
        sectionSignificant: null,
        sectionNote: '',
      }
    }
    return out
  }

  const blockState = ref<Record<BlockKey, BlockData>>(makeEmptyBlocks())

  // 判断矩阵：迹象（5）+ 因素（9）勾选状态
  const indicatorChecks = ref<boolean[]>(SIGNIFICANT_INDICATORS.map(() => false))
  const factorChecks = ref<boolean[]>(SEVERITY_FACTORS.map(() => false))

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  let pendingSave = false

  // ─── Field helper ──────────────────────────────────────────────────────────

  function getField(itemId: string): ChecklistResponse {
    return (
      allResponses.value.get(itemId) || {
        item_id: itemId,
        conclusion: null,
        remark: null,
        wp_ref: null,
      }
    )
  }

  // ─── Build checklist items from current state ───────────────────────────────

  function buildItems(): ChecklistItem[] {
    const items: ChecklistItem[] = []
    for (const key of BLOCK_KEYS) {
      const b = blockState.value[key]
      items.push({
        item_id: `B22C-${key}-def-count`,
        conclusion: null,
        remark: String(b.deficiencies.length),
        wp_ref: null,
      })
      b.deficiencies.forEach((d, i) => {
        const n = i + 1
        items.push({
          item_id: `B22C-${key}-def-${n}-desc`,
          conclusion: null,
          remark: d.desc || null,
          wp_ref: null,
        })
        items.push({
          item_id: `B22C-${key}-def-${n}-flags`,
          conclusion: null,
          remark: JSON.stringify({ cd: d.isControlDeficiency, sig: d.isSignificant }),
          wp_ref: null,
        })
        items.push({
          item_id: `B22C-${key}-def-${n}-judgment`,
          conclusion: null,
          remark: d.judgment || null,
          wp_ref: null,
        })
        // 🔴 严重程度（B22C 单一真源）：conclusion 存中文严重程度
        items.push({
          item_id: `B22C-${key}-def-${n}-severity`,
          conclusion: d.severity,
          remark: null,
          wp_ref: null,
        })
      })
      items.push({
        item_id: `B22C-${key}-section-significant`,
        conclusion: b.sectionSignificant === null ? null : b.sectionSignificant ? 'Y' : 'N',
        remark: null,
        wp_ref: null,
      })
      items.push({
        item_id: `B22C-${key}-section-note`,
        conclusion: null,
        remark: b.sectionNote || null,
        wp_ref: null,
      })
    }
    // 整体结论：conclusion 仅用 'Y'/'N'（是否存在值得关注的缺陷），说明存 remark
    items.push({
      item_id: 'B22C-overall-conclusion',
      conclusion: overallHasSignificant.value ? 'Y' : 'N',
      remark: null,
      wp_ref: null,
    })
    items.push({
      item_id: 'B22C-overall-note',
      conclusion: null,
      remark: overallNote.value || null,
      wp_ref: null,
    })
    // 判断矩阵勾选状态
    items.push({
      item_id: 'B22C-judgment-indicators',
      conclusion: null,
      remark: JSON.stringify(indicatorChecks.value),
      wp_ref: null,
    })
    items.push({
      item_id: 'B22C-judgment-factors',
      conclusion: null,
      remark: JSON.stringify(factorChecks.value),
      wp_ref: null,
    })
    return items
  }

  // ─── Save ────────────────────────────────────────────────────────────────

  async function doSave(items: ChecklistItem[]): Promise<void> {
    if (!wpId.value || items.length === 0) return
    saving.value = true
    try {
      // 🔴 注意：不要传 project_id（传 wpId 会触发 422 project_mismatch）。省略后端从 wp_id 反查。
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        items: items.map((item) => ({
          item_id: item.item_id,
          conclusion: item.conclusion || null,
          remark: item.remark || null,
          wp_ref: item.wp_ref || null,
        })),
      })
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败')
      }
    } finally {
      saving.value = false
    }
  }

  /** 立即持久化（选择/勾选变更、增删行、上游带入用） */
  function persistImmediate(): void {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    pendingSave = false
    const items = buildItems()
    for (const it of items) allResponses.value.set(it.item_id, it)
    doSave(items)
  }

  /** debounce 2000ms 持久化（文本字段用） */
  function persistDebounced(): void {
    const items = buildItems()
    for (const it of items) allResponses.value.set(it.item_id, it)
    pendingSave = true
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      pendingSave = false
      doSave(Array.from(allResponses.value.values()))
    }, 2000)
  }

  /** flush 未保存数据（组件卸载时调用） */
  function flushPendingSave(): void {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    if (pendingSave) {
      pendingSave = false
      doSave(Array.from(allResponses.value.values()))
    }
  }

  // ─── Load ────────────────────────────────────────────────────────────────

  function hydrateFromResponses(): void {
    const blocks = makeEmptyBlocks()
    for (const key of BLOCK_KEYS) {
      const b = blocks[key]
      const count = parseInt(getField(`B22C-${key}-def-count`).remark || '0', 10)
      const defs: DeficiencyEntry[] = []
      for (let n = 1; n <= count; n++) {
        const desc = getField(`B22C-${key}-def-${n}-desc`).remark || ''
        const flagsRaw = getField(`B22C-${key}-def-${n}-flags`).remark
        let cd = false
        let sig = false
        if (flagsRaw) {
          try {
            const parsed = JSON.parse(flagsRaw)
            cd = !!parsed.cd
            sig = !!parsed.sig
          } catch {
            // ignore malformed flags
          }
        }
        const judgment = getField(`B22C-${key}-def-${n}-judgment`).remark || ''
        // 严重程度（权威）：存于 conclusion；有 severity 时 isSignificant 由其派生，保证口径一致
        const severity = normalizeSeverity(getField(`B22C-${key}-def-${n}-severity`).conclusion)
        if (severity !== null) sig = severityIsSignificant(severity)
        defs.push({ desc, isControlDeficiency: cd, isSignificant: sig, severity, judgment })
      }
      b.deficiencies = defs
      const secSig = getField(`B22C-${key}-section-significant`).conclusion
      b.sectionSignificant = secSig === 'Y' ? true : secSig === 'N' ? false : null
      b.sectionNote = getField(`B22C-${key}-section-note`).remark || ''
    }
    blockState.value = blocks
    overallNote.value = getField('B22C-overall-note').remark || ''

    // 判断矩阵勾选状态（长度对齐常量，兼容旧数据缺失）
    const parseChecks = (raw: string | null, len: number): boolean[] => {
      const out = Array.from({ length: len }, () => false)
      if (!raw) return out
      try {
        const arr = JSON.parse(raw)
        if (Array.isArray(arr)) for (let i = 0; i < len; i++) out[i] = !!arr[i]
      } catch {
        // ignore malformed
      }
      return out
    }
    indicatorChecks.value = parseChecks(getField('B22C-judgment-indicators').remark, SIGNIFICANT_INDICATORS.length)
    factorChecks.value = parseChecks(getField('B22C-judgment-factors').remark, SEVERITY_FACTORS.length)
  }

  async function loadAll(): Promise<void> {
    if (!wpId.value) return
    loading.value = true
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: any[] = Array.isArray(res) ? res : res?.data ?? []
      const map = new Map<string, ChecklistResponse>()
      for (const r of responses) {
        if (r.item_id?.startsWith('B22C-')) {
          map.set(r.item_id, {
            item_id: r.item_id,
            conclusion: r.conclusion ?? null,
            remark: r.remark ?? null,
            wp_ref: r.wp_ref ?? null,
          })
        }
      }
      allResponses.value = map
      hydrateFromResponses()
    } catch {
      ElMessage.warning('数据加载失败，可手动填写')
    } finally {
      loading.value = false
    }
  }

  // ─── 消费上游缺陷（核心价值） ────────────────────────────────────────────────

  interface UpstreamDeficiency {
    block: BlockKey
    desc: string
    isSignificant: boolean
    judgment: string
    /** 匹配 B22B 的稳定 key */
    matchKey: string
  }

  /** 解析 B22A responses 提取缺陷 */
  function parseB22ADeficiencies(b22aResponses: ChecklistResponse[]): UpstreamDeficiency[] {
    const out: UpstreamDeficiency[] = []
    for (const r of b22aResponses) {
      if (!r.item_id.includes('-conclusion')) continue
      if (r.conclusion !== '设计无效' && r.conclusion !== '未实施') continue

      // B22A-T{tab}-IT-{sub}-{i}-conclusion 或 B22A-T{tab}-item-{i}-conclusion
      const itMatch = r.item_id.match(/^B22A-T(\d)-IT-([^-]+)-(\d+)-conclusion$/)
      const normalMatch = r.item_id.match(/^B22A-T(\d)-item-(\d+)-conclusion$/)

      let tab = 0
      let sub: string | null = null
      let index = -1
      if (itMatch) {
        tab = parseInt(itMatch[1], 10)
        sub = itMatch[2]
        index = parseInt(itMatch[3], 10)
      } else if (normalMatch) {
        tab = parseInt(normalMatch[1], 10)
        index = parseInt(normalMatch[2], 10)
      } else {
        continue
      }

      // 管理层凌驾（复用 subPanel 'mo'）不是 IT 控制，应归风险评估区，不能因 -IT- 前缀误判为 ITGC
      const isMo = sub === 'mo'
      const isIt = itMatch !== null && !isMo
      const block: BlockKey = isMo ? 'risk' : b22aTabToBlock(tab, isIt)

      // 对应 -point 后缀 item 的 remark 为控制要点文本
      const pointId = r.item_id.replace('-conclusion', '-point')
      const pointItem = b22aResponses.find((x) => x.item_id === pointId)
      const controlPoint = pointItem?.remark || ''
      const desc = controlPoint || `${BLOCK_NAMES[block]}（${r.conclusion}）`

      out.push({
        block,
        desc,
        isSignificant: false,
        judgment: '',
        matchKey: `${tab}|${sub ?? ''}|${index}`,
      })
    }
    return out
  }

  /** 从 B22B responses 解析每条缺陷的严重程度（按 source 匹配） */
  function parseB22BSeverities(b22bResponses: ChecklistResponse[]): Map<string, string> {
    const byId = new Map<string, ChecklistResponse>()
    for (const r of b22bResponses) byId.set(r.item_id, r)

    const countRaw = byId.get('B22B-def-count')?.remark || '0'
    const count = parseInt(countRaw, 10) || 0
    const result = new Map<string, string>()

    for (let n = 1; n <= count; n++) {
      const sourceRaw = byId.get(`B22B-def-${n}-source`)?.remark
      const severity = byId.get(`B22B-def-${n}-severity`)?.conclusion
      if (!sourceRaw || !severity) continue
      try {
        const src = JSON.parse(sourceRaw)
        const key = `${src.tab}|${src.subPanel ?? ''}|${src.index}`
        result.set(key, severity)
      } catch {
        // ignore malformed source
      }
    }
    return result
  }

  /**
   * 从上游 B22A/B22B 带入缺陷（仅填空，不覆盖已保存编辑）。
   * @param b22aResponses B22A checklist responses
   * @param b22bResponses B22B checklist responses
   */
  function loadFromUpstream(
    b22aResponses: ChecklistResponse[],
    b22bResponses: ChecklistResponse[]
  ): { added: number } {
    const upstream = parseB22ADeficiencies(b22aResponses)
    const severities = parseB22BSeverities(b22bResponses)

    let added = 0
    for (const u of upstream) {
      // 🔴 从 B22B 带入中文严重程度写入 B22C 的 severity 字段（B22C 成为单一真源）。
      //   CAS1152 派生：重大/重要 → 值得关注的缺陷；一般 → 仅控制缺陷。
      const severity = normalizeSeverity(severities.get(u.matchKey))
      const isSignificant = severityIsSignificant(severity)

      const block = blockState.value[u.block]
      // 去重：同一 block 下 desc 相同则视为已存在，不覆盖（仅填空、不覆盖已编辑）
      const exists = block.deficiencies.some((d) => d.desc.trim() === u.desc.trim() && u.desc.trim() !== '')
      if (exists) continue

      block.deficiencies.push({
        desc: u.desc,
        isControlDeficiency: true,
        isSignificant,
        severity,
        judgment: u.judgment,
      })
      added++
    }

    if (added > 0) persistImmediate()
    return { added }
  }

  // ─── Computed ────────────────────────────────────────────────────────────

  const blocks: ComputedRef<BlockData[]> = computed(() => BLOCK_KEYS.map((k) => blockState.value[k]))

  const overallHasSignificant: ComputedRef<boolean> = computed(() => {
    for (const key of BLOCK_KEYS) {
      const b = blockState.value[key]
      if (b.sectionSignificant === true) return true
      if (b.deficiencies.some((d) => d.isSignificant)) return true
    }
    return false
  })

  const stats: ComputedRef<B22CStats> = computed(() => {
    let controlDeficiencyCount = 0
    let significantCount = 0
    for (const key of BLOCK_KEYS) {
      for (const d of blockState.value[key].deficiencies) {
        if (d.isControlDeficiency) controlDeficiencyCount++
        if (d.isSignificant) significantCount++
      }
    }
    return { controlDeficiencyCount, significantCount }
  })

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addDeficiency(blockKey: BlockKey): void {
    const block = blockState.value[blockKey]
    if (!block) return
    block.deficiencies.push({
      desc: '',
      isControlDeficiency: true,
      isSignificant: false,
      severity: null,
      judgment: '',
    })
    persistImmediate()
  }

  function removeDeficiency(blockKey: BlockKey, idx: number): void {
    const block = blockState.value[blockKey]
    if (!block || idx < 0 || idx >= block.deficiencies.length) return
    block.deficiencies.splice(idx, 1)
    persistImmediate()
  }

  function setDeficiencyField(
    blockKey: BlockKey,
    idx: number,
    field: DeficiencyField,
    value: string | boolean
  ): void {
    const block = blockState.value[blockKey]
    if (!block || idx < 0 || idx >= block.deficiencies.length) return
    const entry = block.deficiencies[idx]

    if (field === 'desc') {
      entry.desc = String(value)
      persistDebounced()
    } else if (field === 'judgment') {
      entry.judgment = String(value)
      persistDebounced()
    } else if (field === 'isControlDeficiency') {
      entry.isControlDeficiency = !!value
      persistImmediate()
    } else if (field === 'severity') {
      // 🔴 severity 为权威：设定后立即派生 isSignificant，避免口径分裂
      entry.severity = normalizeSeverity(value)
      entry.isSignificant = severityIsSignificant(entry.severity)
      persistImmediate()
    } else if (field === 'isSignificant') {
      entry.isSignificant = !!value
      persistImmediate()
    }
  }

  function setSectionSignificant(blockKey: BlockKey, val: boolean | null): void {
    const block = blockState.value[blockKey]
    if (!block) return
    block.sectionSignificant = val
    persistImmediate()
  }

  function setSectionNote(blockKey: BlockKey, val: string): void {
    const block = blockState.value[blockKey]
    if (!block) return
    block.sectionNote = val
    persistDebounced()
  }

  function setOverallNote(val: string): void {
    overallNote.value = val
    persistDebounced()
  }

  function setIndicatorCheck(idx: number, val: boolean): void {
    if (idx < 0 || idx >= indicatorChecks.value.length) return
    indicatorChecks.value[idx] = !!val
    persistImmediate()
  }

  function setFactorCheck(idx: number, val: boolean): void {
    if (idx < 0 || idx >= factorChecks.value.length) return
    factorChecks.value[idx] = !!val
    persistImmediate()
  }

  /** 任一「值得关注缺陷迹象」勾选 → 建议存在值得关注的缺陷 */
  const suggestedSignificant: ComputedRef<boolean> = computed(() =>
    indicatorChecks.value.some((v) => v)
  )

  /** 已勾选迹象数 / 已考虑因素数（完成度提示） */
  const indicatorCheckedCount: ComputedRef<number> = computed(() => indicatorChecks.value.filter((v) => v).length)
  const factorCheckedCount: ComputedRef<number> = computed(() => factorChecks.value.filter((v) => v).length)

  // ─── Lifecycle ───────────────────────────────────────────────────────────

  onScopeDispose(() => {
    flushPendingSave()
  })

  return {
    // 响应式数据
    allResponses,
    loading,
    saving,
    overallNote,
    blockState,
    indicatorChecks,
    factorChecks,
    // 计算属性
    blocks,
    overallHasSignificant,
    stats,
    suggestedSignificant,
    indicatorCheckedCount,
    factorCheckedCount,
    // 加载
    loadAll,
    loadFromUpstream,
    flushPendingSave,
    // CRUD
    addDeficiency,
    removeDeficiency,
    setDeficiencyField,
    setSectionSignificant,
    setSectionNote,
    setOverallNote,
    setIndicatorCheck,
    setFactorCheck,
    // helper
    getField,
  }
}

export default useB22CDesignEffectiveness
