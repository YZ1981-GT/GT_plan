/**
 * useNoteRefresh — 从底稿刷新 / 手动重试 / stale 重算 + 差异化提示文案
 *
 * 从 DisclosureEditor.vue 抽取，保持原有语义不变。
 * 包含组① 的「已刷新 / 需手动重填」差异化提示逻辑（Req 2.8, 2.9, 1.4）。
 */
import { ref, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { refreshDisclosureFromWorkpapers, refreshDisclosureSection, type RefreshFromWorkpapersResult } from '@/services/commonApi'
import { handleApiError } from '@/utils/errorHandler'
import http from '@/utils/http'
// 复用「跳转至披露表」的同一套章节判定函数，消除跳转/刷新两套硬编码映射漂移（单一真源）
import {
  isD1NotesReceivableNoteSection,
  isD2AccountsReceivableNoteSection,
  isD3PrepaymentNoteSection,
  isD4RevenueNoteSection,
  isD5ReceivablesFinancingNoteSection,
  isD6ContractAssetNoteSection,
  isD7ContractLiabilityNoteSection,
  isG14CreditImpairmentNoteSection,
  isH1FixedAssetNoteSection,
  isH5OilGasAssetNoteSection,
  isH8RouNoteSection,
  isH9LeaseLiabilityNoteSection,
  isH10AssetDisposalNoteSection,
  isI1IntangibleNoteSection,
  isK1OtherReceivableNoteSection,
  isN1DeferredTaxNoteSection,
  isN2TaxesPayableNoteSection,
  isN4TaxesAndSurchargesNoteSection,
  isN5IncomeTaxExpenseNoteSection,
  isH2CipNoteSection,
  isF3NotesPayableNoteSection,
  isG8OtherEquityInstrumentNoteSection,
  isG9OtherNoncurrentFinancialNoteSection,
  isG12HedgingGainsNoteSection,
} from './noteDisclosureJump'

export interface UseNoteRefreshOptions {
  projectId: ComputedRef<string> | Ref<string>
  year: ComputedRef<number> | Ref<number>
  currentNote: Ref<{ note_section: string } | null>
  fetchDetail: (noteSection: string) => Promise<void>
  fetchTree: () => Promise<void>
  /** 触发试算表重算；返回后端 stale 收敛结果（cleared/refilled/kept_stale）供提示 */
  staleRecalc: () => Promise<{ cleared?: number; refilled?: number; kept_stale?: number } | null | void>
  /** 清空全部章节详情缓存（「全部刷新」用，使所有章节都反映最新科目数据而非仅当前节） */
  invalidateAllCache?: () => void
}

export interface UseNoteRefreshReturn {
  refreshLoading: Ref<boolean>
  refreshAllLoading: Ref<boolean>
  syncError: Ref<boolean>
  onRefreshFromWP: () => Promise<void>
  onRefreshAll: () => Promise<void>
  onManualRefresh: () => Promise<void>
  onStaleRecalc: () => Promise<void>
  showRefreshResultMessage: (result: RefreshFromWorkpapersResult) => void
  onWorkpaperSaved: (payload: { projectId: string }) => void
  onDisclosureNoteTextUpdated: (payload: Record<string, unknown>) => void
}

export function useNoteRefresh(options: UseNoteRefreshOptions): UseNoteRefreshReturn {
  const { projectId, year, currentNote, fetchDetail, fetchTree, staleRecalc, invalidateAllCache } = options

  const refreshLoading = ref(false)
  const refreshAllLoading = ref(false)
  const syncError = ref(false)
  let syncDebounceTimer: ReturnType<typeof setTimeout> | null = null

  /**
   * 刷新结果差异化提示（Req 2.8, 2.9, 1.4）
   * GT 紫令牌通过 customClass: 'gt-msg-purple' 实现
   */
  function showRefreshResultMessage(result: RefreshFromWorkpapersResult) {
    const cellsUpdated = result?.cells_updated ?? 0
    const textOnlySections = result?.text_only_sections ?? []
    const errors = result?.errors ?? []

    // 有错误时优先提示错误
    if (errors.length > 0) {
      ElMessage({
        type: 'warning',
        message: `刷新完成，${errors.length} 个章节取数失败：${errors.slice(0, 3).join('；')}${errors.length > 3 ? '…' : ''}`,
        duration: 5000,
        customClass: 'gt-msg-purple',
      })
      return
    }

    // 有更新的单元格
    if (cellsUpdated > 0) {
      let msg = `已刷新 ${cellsUpdated} 个单元格`
      // 存在纯文本章节需手动重填
      if (textOnlySections.length > 0) {
        const sectionNames = textOnlySections.slice(0, 5).join('、')
        const suffix = textOnlySections.length > 5 ? '等' : ''
        msg += `；以下章节需手动重填：${sectionNames}${suffix}`
      }
      ElMessage({
        type: 'success',
        message: msg,
        duration: 4000,
        customClass: 'gt-msg-purple',
      })
      return
    }

    // 无更新但有纯文本章节
    if (textOnlySections.length > 0) {
      const sectionNames = textOnlySections.slice(0, 5).join('、')
      const suffix = textOnlySections.length > 5 ? '等' : ''
      ElMessage({
        type: 'info',
        message: `数据已是最新，无需刷新；以下章节需手动重填：${sectionNames}${suffix}`,
        duration: 4000,
        customClass: 'gt-msg-purple',
      })
      return
    }

    // 全无更新也无纯文本章节
    ElMessage({
      type: 'info',
      message: '数据已是最新，无需刷新',
      duration: 3000,
      customClass: 'gt-msg-purple',
    })
  }

  /**
   * 触发底稿→附注同步标记（让 refill 知道有底稿映射的章节应跳过表格覆盖）。
   * section=null 时全部章节，否则单个章节。fail-open：失败不阻断刷新流程。
   */
  async function _pullFromWorkpapers(section: string | null) {
    try {
      await http.post(`/api/disclosure-notes/${projectId.value}/${year.value}/pull-from-workpapers`, null, {
        params: section ? { note_section: section } : undefined,
        _silent: true,
      } as any)
    } catch { /* fail-open: 拉取失败不阻断刷新 */ }
  }

  /**
   * 刷新（当前页面级）— 只重算并重载「当前正在查看的章节」。
   *
   * 后端只重算该节（refresh_section_from_workpaper），前端也只重载该节，
   * 前后端一致；不再全量写库导致其它章节 DB 新、前端缓存旧的不一致。
   * 需刷新全部章节请用「全部刷新」(onRefreshAll)。
   *
   * 对有底稿映射且已同步的章节：先触发 sync 确保标记最新，refill 跳过表格覆盖。
   */
  async function onRefreshFromWP() {
    const section = currentNote.value?.note_section
    if (!section) {
      ElMessage({ type: 'info', message: '请先选择要刷新的附注章节', duration: 3000, customClass: 'gt-msg-purple' })
      return
    }
    refreshLoading.value = true
    try {
      // 先触发底稿→附注同步标记（确保 refill 知道该章节由底稿驱动，跳过表格覆盖）
      await _pullFromWorkpapers(section)
      const result = await refreshDisclosureSection(projectId.value, year.value, section)
      showRefreshResultMessage(result)
      await fetchDetail(section)
    } catch (e) { handleApiError(e, '刷新附注') }
    finally { refreshLoading.value = false }
  }

  /**
   * 全部刷新 — 从底稿披露表起，刷新更新「全部」附注主要项目下的科目数据。
   *
   * 后端项目级重算（refill_sections）本就覆盖所有映射章节；此处在其基础上
   * 清空全部章节缓存 + 重拉整棵章节树 + 重载当前节，使每个附注章节（非仅当前节）
   * 都立即反映最新科目数据。
   */
  async function onRefreshAll() {
    refreshAllLoading.value = true
    try {
      // 先触发全部底稿→附注同步标记
      await _pullFromWorkpapers(null)
      const result = await refreshDisclosureFromWorkpapers(projectId.value, year.value)
      // 清空全部章节详情缓存，避免其它已缓存章节仍显示旧数据
      invalidateAllCache?.()
      // 重拉章节树（含各章节完成度/stale 标记）
      await fetchTree()
      // 重载当前正在查看的章节详情
      if (currentNote.value) await fetchDetail(currentNote.value.note_section)
      showRefreshResultMessage(result)
    } catch (e) { handleApiError(e, '全部刷新附注') }
    finally { refreshAllLoading.value = false }
  }

  async function onManualRefresh() {
    syncError.value = false
    try {
      const result = await refreshDisclosureFromWorkpapers(projectId.value, year.value)
      if (currentNote.value) await fetchDetail(currentNote.value.note_section)
      showRefreshResultMessage(result)
    } catch (e) {
      syncError.value = true
      handleApiError(e, '刷新附注')
    }
  }

  async function onStaleRecalc() {
    let resolution: { kept_stale?: number } | null | void = null
    try {
      resolution = await staleRecalc()
    } catch (e) {
      // 重算失败必须让用户看见（此前非 2xx 被 validateStatus 吞掉，表现为「点了没反应」）
      handleApiError(e, '试算表重算')
      return
    }
    // 重算试算表后，再触发附注从底稿刷新获取差异化提示
    try {
      const result = await refreshDisclosureFromWorkpapers(projectId.value, year.value)
      showRefreshResultMessage(result)
    } catch { /* stale recalc 已完成，附注刷新失败静默 */ }
    await fetchTree()

    const kept = Number(resolution?.kept_stale ?? 0)
    if (kept > 0) {
      ElMessage({
        type: 'warning',
        message: `试算表已重算；仍有 ${kept} 张底稿正文已保存、重算不覆盖，需打开该底稿刷新后重新保存`,
        duration: 6000,
        customClass: 'gt-msg-purple',
      })
    }
  }

  /** 底稿保存事件监听（自动同步附注数据） */
  function onWorkpaperSaved(payload: { projectId: string }) {
    if (payload.projectId !== projectId.value) return
    if (syncDebounceTimer) clearTimeout(syncDebounceTimer)
    syncDebounceTimer = setTimeout(async () => {
      syncError.value = false
      try {
        await refreshDisclosureFromWorkpapers(projectId.value, year.value)
        if (currentNote.value) await fetchDetail(currentNote.value.note_section)
      } catch {
        syncError.value = true
      }
    }, 1000)
  }

  /** 底稿披露 tab 同步/改叙述后：若当前正在看对应附注节，刷新详情（不整树重拉） */
  function onDisclosureNoteTextUpdated(payload: Record<string, unknown>) {
    if (!payload || !currentNote.value) return
    const pid = String(payload.projectId ?? payload.project_id ?? '')
    if (pid && pid !== projectId.value) return

    const current = String(currentNote.value.note_section || '')
    if (!current) return

    const sectionIds: string[] = []
    const single = payload.sectionId ?? payload.section_id
    if (typeof single === 'string' && single.trim()) sectionIds.push(single.trim())
    if (Array.isArray(payload.sectionIds)) {
      for (const id of payload.sectionIds) {
        if (typeof id === 'string' && id.trim()) sectionIds.push(id.trim())
      }
    }
    if (Array.isArray(payload.payloads)) {
      for (const item of payload.payloads as Array<Record<string, unknown>>) {
        const id = item?.noteSectionId ?? item?.section_id
        if (typeof id === 'string' && id.trim()) sectionIds.push(id.trim())
      }
    }

    const matched = sectionIds.some(id =>
      current === id || current.startsWith(id) || id.startsWith(current),
    )
    // 1511 长期股权投资：上市五、18 / 国企八、18 及合并范围「七」
    const isG7Lte = String(payload.accountCode || '') === '1511'
      && (current.includes('18') || current.startsWith('七'))
    // 2101 交易性金融负债：五、34/35 / 八、34/35
    const isG10Tfl = String(payload.accountCode || '') === '2101'
      && (current.includes('34') || current.includes('35'))
    // 6101 公允价值变动收益：三、公允价值变动收益 / 八、72
    const isG13Fvc = String(payload.accountCode || '') === '6101'
      && (
        current.includes('公允价值变动')
        || current.startsWith('三、公允')
        || current.startsWith('八、72')
        || current === '八、72'
      )
    // 1911 其他非流动资产：五、31 / 八、32
    const isI5Ona = String(payload.accountCode || '') === '1911'
      && (
        current.includes('其他非流动资产')
        || current.startsWith('五、31')
        || current.startsWith('八、32')
        || current === '五、31'
        || current === '八、32'
      )
    // 6701 资产减值损失（K11）：上市三、资产减值损失(关键词) / 国企 八、74
    const isK11Impair = String(payload.accountCode || '') === '6701'
      && (
        current.includes('资产减值损失')
        || current.startsWith('八、74')
      )
    // 6711 营业外支出（K13）：上市三、营业外支出(关键词) / 国企 八、77（区别于营业外收入 6301）
    const isK13NonOpExp = String(payload.accountCode || '') === '6711'
      && (
        current.includes('营业外支出')
        || current.startsWith('八、77')
      )
    // K2-K10 精确编号匹配刷新
    const isK2Refresh = String(payload.accountCode || '') === '1231' && (current === '五、13' || current === '八、14')
    const isK3Refresh = String(payload.accountCode || '') === '2241' && (current === '五、42' || current === '八、42')
    const isK4Refresh = String(payload.accountCode || '') === '2245' && (current === '五、44' || current === '八、48')
    const isK5Refresh = String(payload.accountCode || '') === '2701' && (current === '五、50' || current === '八、55')
    const isK6Refresh = String(payload.accountCode || '') === '1481' && (current === '持有待售资产' || current === '八、12')
    const isK7Refresh = String(payload.accountCode || '') === '2401' && (current === '五、51' || current === '八、56')
    const isK8Refresh = String(payload.accountCode || '') === '6601' && (current === '五、64' || current === '八、65')
    const isK9Refresh = String(payload.accountCode || '') === '6602' && (current === '五、65' || current === '八、66')
    const isK10Refresh = String(payload.accountCode || '') === '6117' && (current === '五、68' || current === '八、69')
    // 1811 递延所得税资产（N1）：上市五、30 / 国企八、31（与 N3 共用章节）
    const isN1DeferredTax = String(payload.accountCode || '') === '1811'
      && isN1DeferredTaxNoteSection(current)
    // 2211 应付职工薪酬（J1）：上市五、40 / 国企八、40（J1 独占）
    const isJ1EmployeeBenefits = String(payload.accountCode || '') === '2211'
      && (current === '五、40' || current === '八、40')
    // 1604 在建工程（H2）：上市五、23 / 国企八、23
    const isH2Cip = String(payload.accountCode || '') === '1604'
      && isH2CipNoteSection(current)
    // 1503 投资性房地产（H3）：上市五、21 / 国企八、22
    const isH3InvestProp = String(payload.accountCode || '') === '1503'
      && (
        current === '五、21'
        || current === '八、22'
        || current.includes('投资性房地产')
      )
    // H5 油气资产（1631/1632）
    const isH5OilGas = (String(payload.accountCode || '') === '1631' || String(payload.accountCode || '') === '1632')
      && isH5OilGasAssetNoteSection(current)
    // F3 应付票据（2201）：上市五、36 / 国企八、36
    const isF3NotesPay = String(payload.accountCode || '') === '2201'
      && isF3NotesPayableNoteSection(current)
    // G8 其他权益工具投资（1503）：上市五、19 / 国企八、19
    const isG8OtherEquity = String(payload.accountCode || '') === '1503'
      && isG8OtherEquityInstrumentNoteSection(current)
    // G9 其他非流动金融资产（1519）：上市五、20 / 国企八、20
    const isG9OtherNoncurFin = String(payload.accountCode || '') === '1519'
      && isG9OtherNoncurrentFinancialNoteSection(current)
    // G12 套期净损益（6103）：上市五、70 / 国企八、71
    const isG12Hedge = String(payload.accountCode || '') === '6103'
      && isG12HedgingGainsNoteSection(current)
    // 兜底：补齐跳转侧支持但刷新侧此前缺失的 6 族（G14/H1/H8/H9/H10/I1）。
    // 复用 noteDisclosureJump 的章节判定（单一真源），当载荷携带 accountCode（=某底稿披露已变更）
    // 且当前正查看的附注节匹配上述任一披露族时兜底刷新；重取当前节详情幂等无害。
    const hasAccountCode = !!String(payload.accountCode || '').trim()
    const matchesDisclosureFamily = hasAccountCode && (
      isD1NotesReceivableNoteSection(current)
      || isD2AccountsReceivableNoteSection(current)
      || isD3PrepaymentNoteSection(current)
      || isD4RevenueNoteSection(current)
      || isD5ReceivablesFinancingNoteSection(current)
      || isD6ContractAssetNoteSection(current)
      || isD7ContractLiabilityNoteSection(current)
      || isG14CreditImpairmentNoteSection(current)
      || isH1FixedAssetNoteSection(current)
      || isH5OilGasAssetNoteSection(current)
      || isH8RouNoteSection(current)
      || isH9LeaseLiabilityNoteSection(current)
      || isH10AssetDisposalNoteSection(current)
      || isI1IntangibleNoteSection(current)
      || isK1OtherReceivableNoteSection(current)
      || isF3NotesPayableNoteSection(current)
      || isG8OtherEquityInstrumentNoteSection(current)
      || isG9OtherNoncurrentFinancialNoteSection(current)
      || isG12HedgingGainsNoteSection(current)
      || isN2TaxesPayableNoteSection(current)
      || isN4TaxesAndSurchargesNoteSection(current)
      || isN5IncomeTaxExpenseNoteSection(current)
    )
    if (
      !matched && !isG7Lte && !isG10Tfl && !isG13Fvc && !isI5Ona
      && !isK11Impair && !isK13NonOpExp && !isN1DeferredTax && !isJ1EmployeeBenefits && !isH2Cip && !isH3InvestProp && !isH5OilGas
      && !isK2Refresh && !isK3Refresh && !isK4Refresh && !isK5Refresh && !isK6Refresh && !isK7Refresh && !isK8Refresh && !isK9Refresh && !isK10Refresh
      && !isF3NotesPay && !isG8OtherEquity && !isG9OtherNoncurFin && !isG12Hedge
      && !matchesDisclosureFamily
    ) return

    if (syncDebounceTimer) clearTimeout(syncDebounceTimer)
    syncDebounceTimer = setTimeout(async () => {
      try {
        await fetchDetail(current)
      } catch {
        /* 静默：用户可手动刷新 */
      }
    }, 400)
  }

  return {
    refreshLoading,
    refreshAllLoading,
    syncError,
    onRefreshFromWP,
    onRefreshAll,
    onManualRefresh,
    onStaleRecalc,
    showRefreshResultMessage,
    onWorkpaperSaved,
    onDisclosureNoteTextUpdated,
  }
}
