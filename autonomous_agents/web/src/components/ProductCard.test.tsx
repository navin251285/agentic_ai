import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Product } from '../api/client'
import { makeProduct } from '../test/fixtures'
import { ProductCard } from './ProductCard'

function card(product: Product) {
  render(<ProductCard product={product} />)
  return screen.getByRole('article')
}

describe('ProductCard', () => {
  it('shows stock, max, bar and reorder mark', () => {
    const el = card(makeProduct({ stock: 15, max_stock: 30, reorder_point: 12 }))
    expect(el).toHaveTextContent('15/ 30')
    expect(el).toHaveTextContent('Reorder mark 12')
    expect(screen.getByTestId('stock-bar')).toHaveStyle({ width: '50%' })
    expect(screen.getByTestId('reorder-mark')).toHaveStyle({ left: '40%' })
  })

  it.each([
    ['SELLING', 'Selling', null, null, 'border-border'],
    ['DANGER', 'Danger zone', 'agent', 'Agent checks in 3s', 'animate-danger-pulse'],
    ['AWAITING', 'Order placed · awaiting', 'arriving', '+18 arriving in 38s', 'border-blue-line'],
    ['RESTOCKED', 'Restocked', 'delivered', '+18 delivered just now', 'bg-green-wash'],
    ['EMPTY', 'Out of stock', 'arriving', '+36 arriving in 12s', 'bg-red-wash'],
  ] as const)('renders %s with its pill, badge and card style', (state, label, kind, badge, cardClass) => {
    const el = card(makeProduct({ state, badge, badge_kind: kind }))
    expect(el).toHaveAttribute('data-state', state)
    expect(el).toHaveClass(cardClass)
    expect(el).toHaveTextContent(label)
    if (badge) {
      const badgeEl = screen.getByText(badge).closest('[data-badge]')
      expect(badgeEl).toHaveAttribute('data-badge', kind)
    } else {
      expect(el.querySelector('[data-badge]')).toBeNull()
    }
  })

  it('only DANGER pulses', () => {
    for (const state of ['SELLING', 'AWAITING', 'RESTOCKED', 'EMPTY'] as const) {
      const { unmount } = render(<ProductCard product={makeProduct({ state })} />)
      expect(screen.getByRole('article')).not.toHaveClass('animate-danger-pulse')
      unmount()
    }
  })

  it('shows the countdown text from the snapshot as it changes', () => {
    const p = makeProduct({ state: 'AWAITING', badge: '+18 arriving in 38s', badge_kind: 'arriving' })
    const { rerender } = render(<ProductCard product={p} />)
    rerender(<ProductCard product={{ ...p, badge: '+18 arriving in 37s' }} />)
    expect(screen.getByText('+18 arriving in 37s')).toBeInTheDocument()
  })

  it('calls onEdit with the product id', () => {
    const onEdit = vi.fn()
    render(<ProductCard product={makeProduct()} onEdit={onEdit} />)
    fireEvent.click(screen.getByRole('button', { name: 'Edit Milk' }))
    expect(onEdit).toHaveBeenCalledWith('milk')
  })
})
