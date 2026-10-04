import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import { makeAgent, makeSnapshot } from '../test/fixtures'
import { useShopStore } from '../store/useShopStore'
import { BudgetMeter } from './BudgetMeter'
import { AgentStatusChip } from './AgentBar'
import { TopBar } from './TopBar'

const gemini = (agent = {}) =>
  makeSnapshot({
    settings: { ...makeSnapshot().settings, agent_mode: 'gemini' },
    agent: makeAgent({ mode: 'gemini', ...agent }),
  })

describe('TopBar', () => {
  beforeEach(() => {
    useShopStore.setState({ snapshot: null, actionError: null })
    vi.spyOn(api, 'setSpeed').mockResolvedValue(makeSnapshot({ speed: 1 }))
    vi.spyOn(api, 'updateSettings').mockResolvedValue(makeSnapshot())
    vi.spyOn(api, 'reset').mockResolvedValue(makeSnapshot())
  })
  afterEach(() => vi.restoreAllMocks())

  it('shows the shop clock, saved-ago and the active speed', () => {
    render(<TopBar snapshot={makeSnapshot({ shop_time: 'Day 2 · 09:15', saved_ago_s: 3.4 })} />)
    expect(screen.getByText('Day 2 · 09:15')).toBeInTheDocument()
    expect(screen.getByTestId('saved-ago')).toHaveTextContent('saved 3s ago')
    expect(screen.getByRole('button', { name: 'Pause' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('sends speed, toggles and reset, and applies the returned snapshot', async () => {
    render(<TopBar snapshot={makeSnapshot()} />)
    fireEvent.click(screen.getByRole('button', { name: '1x' }))
    expect(api.setSpeed).toHaveBeenCalledWith(1)
    await vi.waitFor(() => expect(useShopStore.getState().snapshot?.speed).toBe(1))

    fireEvent.click(screen.getByRole('button', { name: 'Rush hour: off' }))
    expect(api.updateSettings).toHaveBeenCalledWith({ rush_hour: true })
    fireEvent.click(screen.getByRole('button', { name: 'Supplier delay: off' }))
    expect(api.updateSettings).toHaveBeenCalledWith({ supplier_delay: true })
    fireEvent.click(screen.getByRole('button', { name: 'Agent: on' }))
    expect(api.updateSettings).toHaveBeenCalledWith({ agent_enabled: false })
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(api.reset).toHaveBeenCalled()
  })

  it('shows a failed action in the store for the banner', async () => {
    vi.mocked(api.setSpeed).mockRejectedValueOnce(new Error('Network down'))
    render(<TopBar snapshot={makeSnapshot()} />)
    fireEvent.click(screen.getByRole('button', { name: '5x' }))
    await vi.waitFor(() => expect(useShopStore.getState().actionError).toBe('Network down'))
  })

  it('switches the brain and shows "warming up" until llm_ready', () => {
    render(<TopBar snapshot={makeSnapshot({ agent: makeAgent({ llm_ready: false }) })} />)
    const geminiButton = screen.getByRole('button', { name: /Gemini/ })
    expect(geminiButton).toHaveTextContent('Gemini warming up')
    fireEvent.click(geminiButton)
    expect(api.updateSettings).toHaveBeenCalledWith({ agent_mode: 'gemini' })
  })

  it('in rules mode hides the budget meter and the 5x hint', () => {
    render(<TopBar snapshot={makeSnapshot()} />)
    expect(screen.queryByTestId('budget-meter')).toBeNull()
    expect(screen.queryByText(/Gemini is limited at 5x/)).toBeNull()
    expect(screen.getByRole('button', { name: 'Rules' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('in Gemini mode shows the budget meter and ties the 5x hint to the 5x button', () => {
    render(<TopBar snapshot={gemini({ calls_last_60s: 4 })} />)
    expect(screen.getByTestId('budget-meter')).toHaveTextContent('Calls this minute4 / 10')
    const fiveX = screen.getByRole('button', { name: '5x' })
    expect(fiveX).toHaveAccessibleDescription('Gemini is limited at 5x — rules will cover most decisions')
    expect(screen.getByRole('button', { name: 'Gemini' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('shows the 5x hint on screen only while running at 5x', () => {
    const hint = () => screen.getByText('Gemini is limited at 5x — rules will cover most decisions')
    const { rerender } = render(<TopBar snapshot={gemini()} />)
    expect(hint()).toHaveClass('sr-only')
    rerender(<TopBar snapshot={{ ...gemini(), speed: 5 }} />)
    expect(hint()).not.toHaveClass('sr-only')
  })
})

describe('BudgetMeter', () => {
  it.each([
    [4, 'ok', 'bg-green'],
    [7, 'ok', 'bg-green'],
    [8, 'warn', 'bg-amber'],
    [10, 'full', 'bg-red'],
  ] as const)('%i calls → %s', (calls, level, fill) => {
    render(<BudgetMeter agent={makeAgent({ mode: 'gemini', calls_last_60s: calls })} />)
    expect(screen.getByTestId('budget-meter')).toHaveAttribute('data-level', level)
    const segments = screen.getByRole('meter').children
    expect(segments).toHaveLength(10)
    expect([...segments].filter((s) => s.getAttribute('data-filled') === 'true')).toHaveLength(calls)
    expect(segments[0]).toHaveClass(fill)
  })

  it('shows "next call in Ns" only while waiting for the gap', () => {
    const { rerender } = render(<BudgetMeter agent={makeAgent({ next_call_allowed_in_s: 3.2 })} />)
    expect(screen.getByText('next call in 4s')).toBeInTheDocument()
    rerender(<BudgetMeter agent={makeAgent({ next_call_allowed_in_s: 0 })} />)
    expect(screen.queryByText(/next call in/)).toBeNull()
  })
})

describe('AgentStatusChip', () => {
  it.each([
    [{ thinking: true }, 'Gemini thinking…'],
    [{ last_latency_ms: 642.4 }, 'Gemini · last 642 ms'],
    [{ enabled: false }, 'Agent is off'],
  ])('%o → %s', (agent, text) => {
    render(<AgentStatusChip agent={makeAgent({ mode: 'gemini', llm_calls: 7, fallbacks: 2, ...agent })} />)
    const chip = screen.getByTestId('agent-chip')
    expect(chip).toHaveTextContent(text)
    expect(chip).toHaveTextContent('7 calls · 2 fallbacks')
  })
})
