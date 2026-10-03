import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api, ApiError } from '../api/client'
import { makeProduct, makeSnapshot } from '../test/fixtures'
import { EditDrawer } from './EditDrawer'

const milk = makeProduct({ stock: 18, max_stock: 30, reorder_point: 12, lead_time_s: 60, sell_weight: 5 })

function open(onClose = vi.fn()) {
  const view = render(<EditDrawer product={milk} scenario="normal_day" onClose={onClose} />)
  return { ...view, onClose }
}

describe('EditDrawer', () => {
  beforeEach(() => {
    vi.spyOn(api, 'scenarios').mockResolvedValue(['low_stock_start', 'normal_day', 'rush_hour'])
  })
  afterEach(() => vi.restoreAllMocks())

  it('sends only the fields that changed, then closes', async () => {
    const edit = vi.spyOn(api, 'editProduct').mockResolvedValue(makeSnapshot())
    const { onClose } = open()
    fireEvent.change(screen.getByLabelText('Max capacity'), { target: { value: '40' } })
    fireEvent.change(screen.getByLabelText('Reorder mark'), { target: { value: '12' } }) // unchanged
    fireEvent.change(screen.getByLabelText('Sell speed'), { target: { value: '8' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply and save to CSV' }))
    expect(edit).toHaveBeenCalledWith('milk', { max_stock: 40, sell_weight: 8 })
    await vi.waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('untouched inputs follow the live product', () => {
    const { rerender } = open()
    rerender(<EditDrawer product={{ ...milk, stock: 15 }} scenario="normal_day" onClose={vi.fn()} />)
    expect(screen.getByLabelText('Current stock')).toHaveValue(15)
  })

  it('shows validation errors inline and stays open', async () => {
    vi.spyOn(api, 'editProduct').mockRejectedValue(
      new ApiError(422, 'bad', [
        { loc: ['body', 'reorder_point'], msg: 'reorder_point must be below max_stock', type: 'value_error' },
        { loc: ['body'], msg: 'stock must be between 0 and max_stock', type: 'value_error' },
      ]),
    )
    const { onClose } = open()
    fireEvent.change(screen.getByLabelText('Reorder mark'), { target: { value: '30' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply and save to CSV' }))
    expect(await screen.findByText('reorder_point must be below max_stock')).toBeInTheDocument()
    expect(screen.getByLabelText('Reorder mark')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent('stock must be between 0 and max_stock')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('rejects a non-number before sending', () => {
    const edit = vi.spyOn(api, 'editProduct')
    open()
    fireEvent.change(screen.getByLabelText('Current stock'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply and save to CSV' }))
    expect(screen.getByText('Enter a whole number')).toBeInTheDocument()
    expect(edit).not.toHaveBeenCalled()
  })

  it('runs the quick demo actions at once', () => {
    const sell = vi.spyOn(api, 'sell').mockResolvedValue(makeSnapshot())
    const edit = vi.spyOn(api, 'editProduct').mockResolvedValue(makeSnapshot())
    open()
    fireEvent.click(screen.getByRole('button', { name: 'Sell 5' }))
    expect(sell).toHaveBeenCalledWith('milk', 5)
    fireEvent.click(screen.getByRole('button', { name: 'Drop to mark' }))
    expect(edit).toHaveBeenCalledWith('milk', { stock: 12 })
    fireEvent.click(screen.getByRole('button', { name: 'Empty shelf' }))
    expect(edit).toHaveBeenCalledWith('milk', { stock: 0 })
  })

  it('loads a scenario from the picker', async () => {
    const load = vi.spyOn(api, 'loadScenario').mockResolvedValue(makeSnapshot())
    const { onClose } = open()
    await screen.findByRole('option', { name: 'rush_hour.csv' })
    fireEvent.change(screen.getByLabelText('Load scenario'), { target: { value: 'rush_hour' } })
    fireEvent.click(screen.getByRole('button', { name: 'Load' }))
    expect(load).toHaveBeenCalledWith('rush_hour')
    expect(onClose).toHaveBeenCalled()
  })

  it('closes on Escape, the backdrop and Cancel', () => {
    const { onClose } = open()
    fireEvent.keyDown(window, { key: 'Escape' })
    fireEvent.click(screen.getByTestId('drawer-backdrop'))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledTimes(3)
  })
})
