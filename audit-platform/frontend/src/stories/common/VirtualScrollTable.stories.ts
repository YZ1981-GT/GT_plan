import type { Meta, StoryObj } from '@storybook/vue3'
import VirtualScrollTable from '@/components/common/VirtualScrollTable.vue'

const meta = {
  title: 'Common/VirtualScrollTable',
  component: VirtualScrollTable,
  tags: ['autodocs'],
} satisfies Meta<typeof VirtualScrollTable>

export default meta
type Story = StoryObj<typeof meta>

const sampleColumns = [
  { key: 'code', label: '科目编号', width: '120px' },
  { key: 'name', label: '科目名称', width: '200px' },
  { key: 'balance', label: '期末余额', width: '150px', align: 'right' as const },
]

const sampleData = Array.from({ length: 200 }, (_, i) => ({
  id: `row-${i}`,
  code: `${1001 + i}`,
  name: `科目名称 ${i + 1}`,
  balance: Math.round(Math.random() * 1000000),
}))

export const Default: Story = {
  args: {
    columns: sampleColumns,
    data: sampleData,
    height: 400,
    rowHeight: 36,
  },
}

export const LargeDataset: Story = {
  args: {
    columns: sampleColumns,
    data: Array.from({ length: 5000 }, (_, i) => ({
      id: `row-${i}`,
      code: `${1001 + i}`,
      name: `明细科目 ${i + 1}`,
      balance: Math.round(Math.random() * 5000000),
    })),
    height: 500,
    rowHeight: 36,
  },
}

export const WithActiveRow: Story = {
  args: {
    columns: sampleColumns,
    data: sampleData,
    height: 400,
    activeIndex: 5,
  },
}
