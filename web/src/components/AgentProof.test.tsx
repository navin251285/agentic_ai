// CurveballPanel, AgentPlanCard, ScoreboardPanel, and the backup / curveball bits of the pipeline and feed.
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api, ApiError, type AgentPlan } from '../api/client'
import { feedLines } from '../lib/events'
import { makeAgent, makeEvent, makeOrder, makeScoreboard, makeSnapshot } from '../test/fixtures'
import { AgentPlanCard } from './AgentPlanCard'
import { CurveballPanel } from './CurveballPanel'
import { OrdersPipeline } from './OrdersPipeline'
import { ScoreboardPanel } from './ScoreboardPanel'

afterEach(() => vi.restoreAllMocks())

describe('CurveballPanel', () => {
  beforeEach(() => {
    vi.spyOn(api, 'curveballs').mockResolvedValue([
      { id: 'heatwave', title: 'Heatwave', text: 'Heatwave this afternoon.', effect: 'Cold drinks sell 3× more.' },
      { id: 'strike', title: 'Supplier strike', text: 'Main supplier on strike.', effect: 'Main ships after it ends.' },
    ])
  })

  it('sends a preset or typed news, and lists active curveballs', async () => {
    const add = vi.spyOn(api, 'addCurveball').mockResolvedValue(makeSnapshot())
    const snapshot = makeSnapshot({
      agent: makeAgent({ mode: 'gemini' }),
      curveballs: [{ id: 1, preset: 'strike', title: 'Supplier strike', text: 'Main supplier on strike.', seconds_left: 95 }],
    })
    render(<CurveballPanel snapshot={snapshot} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Heatwave' }))
    expect(add).toHaveBeenCalledWith({ preset: 'heatwave' })
    await vi.waitFor(() => expect(screen.getByRole('button', { name: 'Heatwave' })).toBeEnabled())

    const box = screen.getByLabelText('Your own news for the agent')
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    fireEvent.change(box, { target: { value: '  Diwali sale this weekend ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(add).toHaveBeenLastCalledWith({ text: 'Diwali sale this weekend' })
    await vi.waitFor(() => expect(box).toHaveValue(''))

    const active = screen.getByRole('list', { name: 'Active curveballs' })
    expect(within(active).getByText('1m 35s left')).toBeInTheDocument()
    expect(screen.queryByText(/Rules brain can’t read news/)).not.toBeInTheDocument()
  })

  it('shows the server error inline and the rules hint', async () => {
    vi.spyOn(api, 'addCurveball').mockRejectedValue(new ApiError(422, 'At most 3 curveballs at a time; wait for one to end'))
    render(<CurveballPanel snapshot={makeSnapshot()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Supplier strike' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('At most 3 curveballs')
    expect(screen.getByText(/Rules brain can’t read news/)).toBeInTheDocument()
  })
})

const plan: AgentPlan = {
  sim_s: 120,
  shop_time: 'Day 1 · 18:00',
  trigger: 'Curveball: Supplier strike',
  situation: 'Main supplier is down for 3 minutes; milk and bread will run out first.',
  steps: [
    { product_id: 'milk', product_name: 'Milk', action: 'order', qty: 18, supplier: 'backup', reason: 'Strike; milk sells fast.', source: 'gemini' },
    { product_id: 'bread', product_name: 'Bread', action: 'order', qty: 16, supplier: 'main', reason: 'At its mark.', source: 'fallback' },
    { product_id: 'soap', product_name: 'Soap', action: 'wait', qty: 0, supplier: 'main', reason: 'Slow seller.', source: 'gemini' },
  ],
}

describe('AgentPlanCard', () => {
  it('shows the trigger, the situation and each step', () => {
    render(<AgentPlanCard agent={makeAgent({ mode: 'gemini', plan })} />)
    expect(screen.getByText('Curveball: Supplier strike')).toBeInTheDocument()
    expect(screen.getByText('18:00')).toBeInTheDocument()
    expect(screen.getByText(/Main supplier is down/)).toBeInTheDocument()
    const [milk, bread] = within(screen.getByRole('list', { name: 'Orders in this plan' })).getAllByRole('listitem')
    expect(milk).toHaveTextContent('Milk · order 18 from backup')
    expect(milk).toHaveTextContent('Strike; milk sells fast.')
    expect(bread).toHaveTextContent('order 16 from main')
    expect(bread).toHaveTextContent('rules fallback')
    expect(screen.getByText('Waiting on: Soap')).toBeInTheDocument()
  })

  it('explains that the rules brain does not plan, and waits for Gemini', () => {
    const { rerender } = render(<AgentPlanCard agent={makeAgent({ mode: 'rules', plan })} />)
    expect(screen.getByText(/fixed formula; it doesn’t plan/)).toBeInTheDocument()
    expect(screen.queryByText(/Main supplier is down/)).not.toBeInTheDocument()
    rerender(<AgentPlanCard agent={makeAgent({ mode: 'gemini', thinking: true })} />)
    expect(screen.getByText('Gemini is thinking…')).toBeInTheDocument()
  })
})

describe('ScoreboardPanel', () => {
  it('compares both shops and names the leader', () => {
    const scoreboard = makeScoreboard({
      agent: { missed_sales: 3, lost_profit: 30, extra_fees: 54, total_cost: 84 },
      rules: { missed_sales: 34, lost_profit: 340, extra_fees: 0, total_cost: 340 },
      agent_ahead_by: 256,
      same_brain: false,
    })
    const { rerender } = render(<ScoreboardPanel scoreboard={scoreboard} />)
    expect(screen.getByTestId('score-headline')).toHaveTextContent('Agent ahead by ₹256')
    const total = screen.getByRole('row', { name: /Total cost/ })
    expect(total).toHaveTextContent('₹84')
    expect(total).toHaveTextContent('₹340')
    expect(screen.queryByText(/both shops now decide the same way/)).not.toBeInTheDocument()

    rerender(<ScoreboardPanel scoreboard={{ ...scoreboard, agent_ahead_by: -40 }} />)
    expect(screen.getByTestId('score-headline')).toHaveTextContent('Rules ahead by ₹40')
    rerender(<ScoreboardPanel scoreboard={makeScoreboard()} />)
    expect(screen.getByTestId('score-headline')).toHaveTextContent('Level with the rules')
    expect(screen.getByText(/both shops now decide the same way/)).toBeInTheDocument()
  })
})

describe('backup orders and curveball events', () => {
  it('tags backup orders in the pipeline', () => {
    render(<OrdersPipeline orders={[makeOrder({ supplier: 'backup' }), makeOrder({ id: 'O-0002', product_name: 'Eggs' })]} />)
    expect(screen.getAllByText('Backup')).toHaveLength(1)
  })

  it('shows a curveball as its own feed line', () => {
    const [line] = feedLines([makeEvent({ type: 'CURVEBALL', product_id: null, message: 'Heatwave this afternoon.' })], {})
    expect([line.label, line.tone, line.text]).toEqual(['Curveball', 'curveball', 'Heatwave this afternoon.'])
  })
})
