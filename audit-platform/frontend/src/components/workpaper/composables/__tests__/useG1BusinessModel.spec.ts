import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  determineG1BusinessModel,
  createDefaultG1BizQuestionnaire,
  useG1BusinessModel,
  G1_BIZ_MODEL_CHIP,
} from '../useG1BusinessModel'
import type { ChecklistResponse } from '../useF1FormData'

describe('determineG1BusinessModel', () => {
  it('未答完 → INCOMPLETE', () => {
    expect(determineG1BusinessModel({ q1: true })).toBe('INCOMPLETE')
  })

  it('Excel 交易性样例路径 → OTHER', () => {
    const r = determineG1BusinessModel({
      q1: true,
      q2: true,
      q2_1: true,
      q2_2: false,
      q2_3: false,
      q3: false,
      q4: false,
      q5: false,
    })
    expect(r).toBe('OTHER')
    expect(G1_BIZ_MODEL_CHIP.OTHER.label).toContain('其他业务模式')
  })

  it('全部为否 → HOLD_COLLECT', () => {
    const r = determineG1BusinessModel({
      q1: false,
      q2: false,
      q2_1: false,
      q2_2: false,
      q2_3: false,
      q3: false,
      q4: false,
      q5: false,
    })
    expect(r).toBe('HOLD_COLLECT')
  })

  it('仅公允价值管理 → OTHER', () => {
    expect(
      determineG1BusinessModel({
        q1: false,
        q2: false,
        q2_1: false,
        q2_2: false,
        q2_3: false,
        q3: true,
        q4: false,
        q5: false,
      }),
    ).toBe('OTHER')
  })
})

describe('useG1BusinessModel', () => {
  it('答题后持久化问卷与结论；未完成时不写提示文案到 conclusion', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const saves: Array<{ id: string; conclusion: string | null | undefined; remark: string | null | undefined }> = []
    const bm = useG1BusinessModel({
      allResponses,
      debouncedSave: (id, data) => {
        saves.push({ id, conclusion: data.conclusion, remark: data.remark })
        allResponses.value.set(id, {
          item_id: id,
          conclusion: data.conclusion ?? null,
          remark: data.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })

    expect(bm.questionnaire.value).toHaveLength(createDefaultG1BizQuestionnaire().length)
    expect(bm.result.value).toBe('INCOMPLETE')
    // 挂载时未完成 → 不落库「请完成问卷全部问题」
    expect(saves.some((s) => s.id === 'G1-8-model-result')).toBe(false)

    for (const q of bm.questionnaire.value) {
      bm.setAnswer(q.id, false)
    }
    expect(bm.result.value).toBe('HOLD_COLLECT')
    expect(bm.crossCheckWarning.value).toBeTruthy()
    expect(saves.some((s) => s.id === 'G1-8-questionnaire')).toBe(true)
    const resultSaves = saves.filter((s) => s.id === 'G1-8-model-result')
    const resultSave = resultSaves[resultSaves.length - 1]
    expect(resultSave?.remark).toBe('HOLD_COLLECT')
    expect(resultSave?.conclusion).toBe('以收取合同现金流量为目标')
    expect(resultSaves.every((s) => s.conclusion !== '请完成问卷全部问题')).toBe(true)
  })

  it('填入交易性示例路径 → OTHER 且无科目警示', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const bm = useG1BusinessModel({
      allResponses,
      debouncedSave: (id, data) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: data.conclusion ?? null,
          remark: data.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })
    bm.applyTradingPathHints()
    expect(bm.result.value).toBe('OTHER')
    expect(bm.crossCheckWarning.value).toBeNull()
    expect(bm.conclusionChip.value.label).toBe('属于其他业务模式')
  })
})
