import type { Meta, StoryObj } from '@storybook/vue3'
import CellContextMenu from '@/components/common/CellContextMenu.vue'

const meta = {
  title: 'Common/CellContextMenu',
  component: CellContextMenu,
  tags: ['autodocs'],
} satisfies Meta<typeof CellContextMenu>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    visible: true,
    x: 200,
    y: 150,
    itemName: '银行存款',
    value: 4950000,
    multiCount: 1,
  },
}

export const MultiSelect: Story = {
  args: {
    visible: true,
    x: 200,
    y: 150,
    itemName: '选中区域',
    value: null,
    multiCount: 5,
  },
}

export const StringValue: Story = {
  args: {
    visible: true,
    x: 300,
    y: 200,
    itemName: '科目名称',
    value: '应收账款',
    multiCount: 1,
  },
}
