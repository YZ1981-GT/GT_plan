import type { Meta, StoryObj } from '@storybook/vue3'
import GtToolbar from '@/components/common/GtToolbar.vue'

const meta = {
  title: 'Common/GtToolbar',
  component: GtToolbar,
  tags: ['autodocs'],
  argTypes: {
    variant: { control: 'select', options: ['banner', 'default', 'compact'] },
  },
} satisfies Meta<typeof GtToolbar>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    variant: 'default',
    showExport: true,
    showCopy: true,
  },
}

export const BannerVariant: Story = {
  args: {
    variant: 'banner',
    showExport: true,
    showFullscreen: true,
    showEditToggle: true,
    isEditing: false,
  },
}

export const CompactVariant: Story = {
  args: {
    variant: 'compact',
    showExport: true,
    showImport: true,
  },
}

export const AllButtons: Story = {
  args: {
    variant: 'default',
    showCopy: true,
    showFullscreen: true,
    showExport: true,
    showImport: true,
    showFormula: true,
    showTemplate: true,
    showEditToggle: true,
    showDisplaySettings: true,
    isEditing: true,
  },
}
