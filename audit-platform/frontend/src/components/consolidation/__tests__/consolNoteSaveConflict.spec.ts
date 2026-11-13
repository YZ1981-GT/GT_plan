import { describe, expect, it } from 'vitest'
import {
  CONSOL_NOTE_CONFLICT_CODE,
  CONSOL_NOTE_DIGEST_REQUIRED_CODE,
  extractConsolNoteConflictInfo,
  getConsolNoteConflictInfo,
  isConsolNoteConflict,
  isConsolNoteDigestRequired,
} from '../composables/consolNoteSaveConflict'

function axiosError(status: number, data: unknown) {
  return { response: { status, data } }
}

const conflictDetail = {
  error_code: CONSOL_NOTE_CONFLICT_CODE,
  current_digest: 'a'.repeat(64),
  updated_at: '2026-11-11T10:20:30+00:00',
  last_write_source: 'subtree_aggregate',
  message: '该章节已被其他人修改，请重新加载或保留本地修改',
}

describe('consolNoteSaveConflict', () => {
  it('识别 Axios 的 detail 业务信封并提取冲突信息', () => {
    const error = axiosError(409, { detail: conflictDetail })

    expect(isConsolNoteConflict(error)).toBe(true)
    expect(extractConsolNoteConflictInfo(error)).toEqual({
      currentDigest: 'a'.repeat(64),
      updatedAt: '2026-11-11T10:20:30+00:00',
      lastWriteSource: 'subtree_aggregate',
      message: '该章节已被其他人修改，请重新加载或保留本地修改',
    })
  })

  it('兼容尚未经过拦截器归一化的平台 message 信封与已解包 response', () => {
    const error = { status: 409, data: { message: conflictDetail } }

    expect(isConsolNoteConflict(error)).toBe(true)
    expect(getConsolNoteConflictInfo(error)?.currentDigest).toBe('a'.repeat(64))
  })

  it('识别缺少摘要令牌，并拒绝显式错误状态不匹配的业务码', () => {
    const missingDetail = {
      error_code: CONSOL_NOTE_DIGEST_REQUIRED_CODE,
      message: '保存附注必须提供 expected_digest 或 force_overwrite=true',
    }
    const missingDigest = axiosError(428, { detail: missingDetail })

    expect(isConsolNoteDigestRequired(missingDigest)).toBe(true)
    expect(isConsolNoteConflict(axiosError(500, { detail: conflictDetail }))).toBe(false)
    expect(isConsolNoteDigestRequired(axiosError(422, { detail: missingDetail }))).toBe(false)
  })

  it('业务对象已被解包时仍可按业务码识别', () => {
    expect(isConsolNoteConflict(conflictDetail)).toBe(true)
    expect(isConsolNoteDigestRequired({ error_code: CONSOL_NOTE_DIGEST_REQUIRED_CODE })).toBe(true)
  })

  it('冲突字段缺失时返回安全默认值，不泄露原始异常文本', () => {
    const error = axiosError(409, {
      detail: {
        error_code: CONSOL_NOTE_CONFLICT_CODE,
        message: '   ',
        current_digest: 123,
        updated_at: null,
        last_write_source: false,
      },
    })

    expect(extractConsolNoteConflictInfo(error)).toEqual({
      currentDigest: null,
      updatedAt: null,
      lastWriteSource: 'manual',
      message: '附注内容已被其他人修改，请重新加载或保留本地修改',
    })
  })

  it('非目标错误返回 null，且解析不会修改原始错误对象', () => {
    const error = axiosError(409, { detail: { error_code: 'OTHER_ERROR', message: '其他错误' } })
    const snapshot = JSON.parse(JSON.stringify(error))

    expect(extractConsolNoteConflictInfo(error)).toBeNull()
    expect(error).toEqual(snapshot)
  })
})
