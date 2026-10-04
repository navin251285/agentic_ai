import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'

import { makeProduct } from '../test/fixtures'
import { ProductGrid } from './ProductGrid'

it('renders one card per product with a count heading and legend', () => {
  const products = ['milk', 'bread', 'eggs'].map((id) => makeProduct({ id, name: id }))
  render(<ProductGrid products={products} />)
  expect(screen.getByRole('heading', { name: 'Inventory · 3 products' })).toBeInTheDocument()
  expect(screen.getAllByRole('article')).toHaveLength(3)
  expect(screen.getByText('Danger zone (below mark)')).toBeInTheDocument()
})
