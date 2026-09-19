/**
 * N2 宿主传参接线守卫
 *
 * 🔴 背景（2026-08-01 复盘实测，**第三层阻塞**）
 * ---------------------------------------------
 * `N2TabAdjudication.vue` 声明了 `htmlData?: any` 并靠
 * `htmlData.adjudication_prefill` 种子四表未审数，但宿主 `GtN2TaxesPayable.vue`
 * **漏传该 prop** → `props.htmlData` 恒 `undefined` →
 * `Array.isArray(undefined)` = false → prefill 恒 null →
 * 审定表永远空行、四表入库的数据一步都进不来。
 *
 * 与「漏传 projectId = 披露同步永久静默失败」同款范式：组件不崩、无控制台报错、
 * `get_diagnostics` 与 vitest 全绿，**只有浏览器实测能发现**。
 *
 * 本守卫扫源码，锁死「声明了 htmlData 的 N2 子组件，宿主必须传」。
 *
 * spec: n2-disclosure-and-extraction-alignment Task 6.3
 */
import { describe, expect, it } from 'vitest'

const HOST_SRC = await import('../../GtN2TaxesPayable.vue?raw').then(
  (m) => (m as unknown as { default: string }).default,
)

function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/.*/g, '')
}

const HOST_TEMPLATE = (() => {
  const stripped = stripComments(HOST_SRC)
  const m = stripped.match(/<template>([\s\S]*)<\/template>/)
  return m ? m[1] : ''
})()

describe('N2 宿主 htmlData 传参', () => {
  it('自检：宿主模板抽取成功且含子组件标签', () => {
    expect(HOST_TEMPLATE.length).toBeGreaterThan(500)
    expect(HOST_TEMPLATE).toContain('<N2TabAdjudication')
  })

  it('自检：stripComments 生效（原文含注释）', () => {
    expect(HOST_SRC).toMatch(/<!--|\/\*|\/\//)
    expect(stripComments(HOST_SRC).length).toBeLessThan(HOST_SRC.length)
  })

  it('🔴 N2TabAdjudication 必须收到 :html-data（否则四表预填恒失效）', () => {
    const tagMatch = HOST_TEMPLATE.match(/<N2TabAdjudication\b([\s\S]*?)\/>/)
    expect(tagMatch, '宿主未渲染 N2TabAdjudication').toBeTruthy()
    const attrs = tagMatch![1]
    const wired = /:html-data\s*=/.test(attrs) || /v-bind="\$props"/.test(attrs)
    expect(
      wired,
      'N2TabAdjudication 缺 :html-data —— props.htmlData 恒 undefined，'
        + 'Array.isArray(undefined)=false → adjudication_prefill 恒 null → 审定表永远空行',
    ).toBe(true)
  })

  it('N2TabAdjudication 同时收到 wp-id / project-id / all-responses（回归保护）', () => {
    const attrs = HOST_TEMPLATE.match(/<N2TabAdjudication\b([\s\S]*?)\/>/)![1]
    for (const attr of [':all-responses', ':wp-id', ':project-id']) {
      expect(attrs, `N2TabAdjudication 缺 ${attr}`).toContain(attr)
    }
  })

  it('两个披露 Tab 必须收到 :project-id（既有平台守卫的 N2 局部复核）', () => {
    for (const tag of ['N2TabDisclosureListed', 'N2TabDisclosureSoe']) {
      const m = HOST_TEMPLATE.match(new RegExp(`<${tag}\\b([\\s\\S]*?)\\/>`))
      expect(m, `宿主未渲染 ${tag}`).toBeTruthy()
      const wired = /:project-id\s*=/.test(m![1]) || /v-bind="\$props"/.test(m![1])
      expect(wired, `${tag} 缺 :project-id → 同步（含自动同步）永久静默失败`).toBe(true)
    }
  })

  it('🔴 两个披露 Tab 必须收到 :html-data（审定表未落库时的四表预填兜底）', () => {
    for (const tag of ['N2TabDisclosureListed', 'N2TabDisclosureSoe']) {
      const m = HOST_TEMPLATE.match(new RegExp(`<${tag}\\b([\\s\\S]*?)\\/>`))
      expect(m, `宿主未渲染 ${tag}`).toBeTruthy()
      const wired = /:html-data\s*=/.test(m![1]) || /v-bind="\$props"/.test(m![1])
      expect(
        wired,
        `${tag} 缺 :html-data —— 审定表种子值在用户保存前不在 checklist_responses 里，`
          + '披露表只读 checklist 会全空（四表→披露链路断裂）',
      ).toBe(true)
    }
  })
})

describe('披露 composable 消费 renderPrefill', () => {
  it('两个披露 Tab 都把 htmlData.adjudication_prefill 传给 useN2DisclosureTables', async () => {
    const mods = await Promise.all([
      import('../../n2/core/N2TabDisclosureListed.vue?raw'),
      import('../../n2/core/N2TabDisclosureSoe.vue?raw'),
    ])
    mods.forEach((mod, i) => {
      const name = ['N2TabDisclosureListed', 'N2TabDisclosureSoe'][i]
      const src = stripComments((mod as unknown as { default: string }).default)
      expect(src, `${name} 未声明 htmlData prop`).toMatch(/htmlData\?:/)
      expect(
        src,
        `${name} 未把 adjudication_prefill 传给 useN2DisclosureTables（renderPrefill）`,
      ).toMatch(/renderPrefill[\s\S]{0,120}adjudication_prefill/)
    })
  })
})
