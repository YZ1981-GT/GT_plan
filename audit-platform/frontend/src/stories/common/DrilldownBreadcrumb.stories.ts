import type { Meta, StoryObj } from '@storybook/vue3'
import DrilldownBreadcrumb from '@/components/common/DrilldownBreadcrumb.vue'

const meta = {
  title: 'Common/DrilldownBreadcrumb',
  component: DrilldownBreadcrumb,
  tags: ['autodocs'],
} satisfies Meta<typeof DrilldownBreadcrumb>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    stack: [
      { source_view: '/trial-balance', direction: 'down' as const },
      { source_view: '/drilldown', direction: 'down' as const },
      { source_view: '/ledger', label: '明细账 1001' },
    ],
  },
}

export const UpDrillDirection: Story = {
  args: {
    stack: [
      { source_view: '/disclosure-notes', label: '附注', direction: 'up' as const },
      { source_view: '/reports', label: '资产负债表', direction: 'up' as const },
      { source_view: '/trial-balance', label: '试算表' },
    ],
  },
}

export const CollapsedLong: Story = {
  args: {
    stack: [
      { source_view: '/trial-balance', direction: 'down' as const },
      { source_view: '/drilldown', direction: 'down' as const },
      { source_view: '/ledger', direction: 'down' as const },
      { source_view: '/aux-summary', direction: 'down' as const },
      { source_view: '/workpapers', direction: 'down' as const },
      { source_view: '/adjustments', label: '调整分录' },
    ],
  },
}
