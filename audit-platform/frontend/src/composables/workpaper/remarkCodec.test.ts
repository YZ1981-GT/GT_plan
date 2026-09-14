import { describe, expect, it } from 'vitest'
import { decodeRemark, encodeRemark, type JsonValue } from './remarkCodec'

describe('remarkCodec', () => {
  /** **Validates: Requirements 3.4** */
  it('新写仅序列化一次且不增加 remark 包装', () => {
    const value = { rows: [{ amount: 12.5 }], note: '中文', enabled: true }
    const encoded = encodeRemark(value)

    expect(encoded).toBe(JSON.stringify(value))
    expect(JSON.parse(encoded)).toEqual(value)
    expect(JSON.parse(encoded)).not.toEqual({ remark: JSON.stringify(value) })
  })

  it.each<JsonValue>([
    '123', 'true', 'null', '{"nested":true}', '[1,2]', '"quoted"',
    123, true, null, ['明细', 1], { remark: '普通业务字段', other: 1 },
  ])('单层编解码保持业务值和类型：%j', (value) => {
    expect(decodeRemark(encodeRemark(value))).toEqual(value)
  })

  it('兼容历史对象与字符串形式的双层 remark 包装', () => {
    const value = { rows: [{ amount: 12.5 }], note: '历史数据' }
    const legacyEnvelope = { remark: encodeRemark(value) }

    expect(decodeRemark(legacyEnvelope)).toEqual(value)
    expect(decodeRemark(JSON.stringify(legacyEnvelope))).toEqual(value)
  })

  it('保留非历史包装的业务对象与无效 JSON 字符串', () => {
    expect(decodeRemark({ remark: '普通业务字段' })).toEqual({ remark: '普通业务字段' })
    expect(decodeRemark({ remark: encodeRemark({ a: 1 }), other: 2 })).toEqual({
      remark: encodeRemark({ a: 1 }), other: 2,
    })
    expect(decodeRemark('普通文本')).toBe('普通文本')
  })
})
