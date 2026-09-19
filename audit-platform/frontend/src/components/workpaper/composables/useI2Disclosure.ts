/**
 * useI2Disclosure — I2 开发支出附注披露
 * 上市：按性质 + 项目滚动 + 重要资本化 + 减值；国企：项目滚动
 * 取数：I2-2 / I2-6 / I2-7；同步附注：sync-from-workpaper + disclosure:note-text-updated
 */
import { ref, computed, watch, type Ref } from 'vue'
import {
  I2_DISC_KEYS,
  type I2NatureRow,
  type I2MovementRow,
  type I2ImportantCapRow,
  type I2ImpairmentRow,
  defaultNatureRows,
  addI2NatureRow,
  removeI2NatureRow,
  emptyMovementRow,
  emptyImportantRow,
  emptyImpairmentRow,
  normalizeNatureRow,
  normalizeMovementRow,
  normalizeImportantRow,
  normalizeImpairmentRow,
  recalcMovementEnd,
  summarizeNature,
  summarizeMovement,
  seedMovementFromI22,
  enrichFromI26,
  seedNatureCapitalizedFromI27,
  applyNatureCapitalizedMap,
  safeParseArray,
  readText,
} from './i2DisclosureModel'
import {
  resolveI2NoteSectionTarget,
  type I2DisclosureVariant,
} from './i2NoteSectionMap'
import type { I2ListedSyncSnapshot, I2SoeSyncSnapshot } from './i2DisclosureSyncPayload'

export type { I2DisclosureVariant, I2NatureRow, I2MovementRow, I2ImportantCapRow, I2ImpairmentRow }

export function useI2Disclosure(
  allResponses: Ref<Map<string, any>>,
  options: {
    variant: I2DisclosureVariant
    saveResponse?: (sheetCode: string, data: Record<string, any>) => Promise<void>
    applicableStandards?: Ref<readonly string[] | null | undefined> | (() => readonly string[] | null | undefined)
  },
) {
  const variant = options.variant
  const sheetCode = variant === 'listed' ? 'disc-listed' : 'disc-soe'

  const natureRows = ref<I2NatureRow[]>(defaultNatureRows())
  const movementRows = ref<I2MovementRow[]>([])
  const importantRows = ref<I2ImportantCapRow[]>([])
  const impairmentRows = ref<I2ImpairmentRow[]>([])
  const noteText = ref('')
  const noteCap = ref('')
  const noteImpairTest = ref('')
  const notePurchased = ref('')
  const auditNote = ref('')
  const auditConclusion = ref('')

  function _standards(): readonly string[] | null | undefined {
    const s = options.applicableStandards
    if (!s) return undefined
    return typeof s === 'function' ? s() : s.value
  }

  const noteTarget = computed(() => resolveI2NoteSectionTarget(variant, _standards()))

  function load() {
    const map = allResponses.value
    if (variant === 'listed') {
      const natureRaw = safeParseArray(map.get(I2_DISC_KEYS.listedNature))
      natureRows.value = natureRaw.length ? natureRaw.map(normalizeNatureRow) : defaultNatureRows()

      let mov = safeParseArray(map.get(I2_DISC_KEYS.listedMovement)).map(normalizeMovementRow)
      if (!mov.length) {
        mov = safeParseArray(map.get(I2_DISC_KEYS.listedLegacyRows)).map(normalizeMovementRow)
      }
      movementRows.value = mov

      importantRows.value = safeParseArray(map.get(I2_DISC_KEYS.listedImportant)).map(normalizeImportantRow)
      impairmentRows.value = safeParseArray(map.get(I2_DISC_KEYS.listedImpairment)).map(normalizeImpairmentRow)
      noteText.value = readText(map.get(I2_DISC_KEYS.listedNote))
      noteCap.value = readText(map.get(I2_DISC_KEYS.listedNoteCap))
      noteImpairTest.value = readText(map.get(I2_DISC_KEYS.listedNoteImpairTest))
      notePurchased.value = readText(map.get(I2_DISC_KEYS.listedNotePurchased))
      auditNote.value = readText(map.get(I2_DISC_KEYS.listedAuditNote))
      auditConclusion.value = readText(map.get(I2_DISC_KEYS.listedAuditConclusion))
    } else {
      let mov = safeParseArray(map.get(I2_DISC_KEYS.soeMovement)).map(normalizeMovementRow)
      if (!mov.length) {
        mov = safeParseArray(map.get(I2_DISC_KEYS.soeLegacyRows)).map(normalizeMovementRow)
      }
      movementRows.value = mov
      noteText.value = readText(map.get(I2_DISC_KEYS.soeNote))
      auditNote.value = readText(map.get(I2_DISC_KEYS.soeAuditNote))
      auditConclusion.value = readText(map.get(I2_DISC_KEYS.soeAuditConclusion))
    }
  }

  watch(() => allResponses.value, () => load(), { immediate: true })

  const natureSummary = computed(() => summarizeNature(natureRows.value))
  const movementSummary = computed(() => summarizeMovement(movementRows.value))

  /** 性质表资本化合计 vs 滚动内部开发增加 */
  const natureVsMovementDiff = computed(() => {
    if (variant !== 'listed') return null
    return Math.round((natureSummary.value.currentCapitalized - movementSummary.value.increaseInternal) * 100) / 100
  })

  /**
   * 新增费用性质行（源模板 `A15 = ……` 可扩位）。
   * 必须先命名：空名/撞名一律拒绝并返回 false，由组件 prompt 提示（禁产生无名行）。
   */
  function addNatureRow(label: string): boolean {
    const next = addI2NatureRow(natureRows.value, label)
    if (!next) return false
    natureRows.value = next
    return true
  }

  /** 删除自定义费用性质行；源模板固定 6 类不可删（返回 false） */
  function removeNatureRow(rowId: string): boolean {
    const next = removeI2NatureRow(natureRows.value, rowId)
    if (!next) return false
    natureRows.value = next
    return true
  }
  function addMovementRow() { movementRows.value.push(emptyMovementRow()) }
  function addImportantRow() { importantRows.value.push(emptyImportantRow()) }
  function addImpairmentRow() { impairmentRows.value.push(emptyImpairmentRow()) }

  function onMovementChange(row: I2MovementRow) { recalcMovementEnd(row) }

  /**
   * 从 I2-2 明细 / I2-6 资本化时点 / I2-7 项目构成自动取数。
   *
   * 🔴 返回类型曾只声明 `{ ok, message }`，而成功路径实际还返回了
   *    `unmatched` / `fuzzyMatched` 两个清单 ⇒ `tsc` 报 TS2353，
   *    且**消费方在类型上拿不到这两个字段**（只能从拼好的 `message` 里读文本）。
   *    未匹配项目清单是审计师要逐个核对的东西，必须可程序化取用。
   */
  function autoFillFromSources(): {
    ok: boolean
    message: string
    /** 在 I2-6 里找不到资本化时点的项目名（需审计师逐个核对） */
    unmatched?: string[]
    /** 靠模糊匹配对上的项目名（需审计师确认匹配正确） */
    fuzzyMatched?: string[]
  } {
    const map = allResponses.value
    const detail = safeParseArray(map.get('I2-2-rows'))
    const cap = safeParseArray(map.get('I2-6-rows'))
    const project = safeParseArray(map.get('I2-7-rows'))

    let seeded = seedMovementFromI22(detail)
    if (!seeded.length) {
      // 兜底：I2-7 项目名
      seeded = project
        .filter((r) => (r.projectName || '').trim())
        .map((r) => emptyMovementRow({
          name: r.projectName,
          beginBalance: Number(r.begin?.capitalized) || 0,
          increaseInternal: Number(r.increase?.capitalized) || Number(r.totalAmount) || 0,
          isAutoFilled: true,
        }))
    }

    const enriched = enrichFromI26(seeded, importantRows.value, cap)
    movementRows.value = enriched.movement
    if (variant === 'listed') {
      importantRows.value = enriched.important
      if (project.length) {
        const cmap = seedNatureCapitalizedFromI27(project)
        natureRows.value = applyNatureCapitalizedMap(
          natureRows.value.length ? natureRows.value : defaultNatureRows(),
          cmap,
        )
      }
    }

    if (!movementRows.value.length) {
      return { ok: false, message: '暂无 I2-2/I2-7 项目数据可供自动取数' }
    }
    const parts = [`已取数 ${movementRows.value.length} 个项目`]
    if (enriched.filled) parts.push(`补齐资本化信息 ${enriched.filled} 处`)
    if (enriched.fuzzyMatched.length) {
      parts.push(`模糊匹配 ${enriched.fuzzyMatched.length} 项（请核对项目名）`)
    }
    if (enriched.unmatched.length) {
      parts.push(`⚠ 未匹配 I2-6：${enriched.unmatched.slice(0, 5).join('、')}${enriched.unmatched.length > 5 ? '…' : ''}`)
    }
    return {
      ok: true,
      message: parts.join('；'),
      unmatched: enriched.unmatched,
      fuzzyMatched: enriched.fuzzyMatched,
    }
  }

  function getListedSnapshot(): I2ListedSyncSnapshot {
    return {
      natureRows: natureRows.value,
      movementRows: movementRows.value,
      importantRows: importantRows.value,
      impairmentRows: impairmentRows.value,
      noteText: noteText.value,
      noteCap: noteCap.value,
      noteImpairTest: noteImpairTest.value,
      notePurchased: notePurchased.value,
    }
  }

  function getSoeSnapshot(): I2SoeSyncSnapshot {
    return {
      movementRows: movementRows.value,
      noteText: noteText.value,
    }
  }

  async function persistAll() {
    const save = options.saveResponse
    if (!save) return
    if (variant === 'listed') {
      await save(sheetCode, {
        [I2_DISC_KEYS.listedNature]: JSON.stringify(natureRows.value),
        [I2_DISC_KEYS.listedMovement]: JSON.stringify(movementRows.value),
        [I2_DISC_KEYS.listedImportant]: JSON.stringify(importantRows.value),
        [I2_DISC_KEYS.listedImpairment]: JSON.stringify(impairmentRows.value),
        [I2_DISC_KEYS.listedNote]: noteText.value,
        [I2_DISC_KEYS.listedNoteCap]: noteCap.value,
        [I2_DISC_KEYS.listedNoteImpairTest]: noteImpairTest.value,
        [I2_DISC_KEYS.listedNotePurchased]: notePurchased.value,
        [I2_DISC_KEYS.listedAuditNote]: auditNote.value,
        [I2_DISC_KEYS.listedAuditConclusion]: auditConclusion.value,
        // 兼容旧消费者
        [I2_DISC_KEYS.listedLegacyRows]: JSON.stringify(movementRows.value),
      })
    } else {
      await save(sheetCode, {
        [I2_DISC_KEYS.soeMovement]: JSON.stringify(movementRows.value),
        [I2_DISC_KEYS.soeNote]: noteText.value,
        [I2_DISC_KEYS.soeAuditNote]: auditNote.value,
        [I2_DISC_KEYS.soeAuditConclusion]: auditConclusion.value,
        [I2_DISC_KEYS.soeLegacyRows]: JSON.stringify(movementRows.value),
      })
    }
  }

  return {
    variant,
    natureRows,
    movementRows,
    importantRows,
    impairmentRows,
    noteText,
    noteCap,
    noteImpairTest,
    notePurchased,
    auditNote,
    auditConclusion,
    natureSummary,
    movementSummary,
    natureVsMovementDiff,
    noteTarget,
    load,
    addNatureRow,
    // 🔴 曾漏这一行：`removeNatureRow` 函数体写了、却没进 return 清单 ⇒
    //    `I2TabDisclosureListed.vue` 从 `disc` 解构到的是 `undefined`，
    //    点「删」即 `TypeError: removeNatureRow is not a function` → **整页「页面渲染出错」白屏**。
    //    四层守卫全查不出：grep 搜得到定义（看着像接通了）、model 层 vitest 测的是
    //    `removeI2NatureRow` 纯函数、`tsc --noEmit` **不解析 `.vue`**（SFC 解构错误要 `vue-tsc`）、
    //    `get_diagnostics` 无报。只有浏览器点一下才暴露。
    removeNatureRow,
    addMovementRow,
    addImportantRow,
    addImpairmentRow,
    onMovementChange,
    autoFillFromSources,
    getListedSnapshot,
    getSoeSnapshot,
    persistAll,
  }
}

export default useI2Disclosure
