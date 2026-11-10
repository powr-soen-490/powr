// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import type { ReactNode } from 'react'
import { PageHeader } from '../layout/PageHeader'
import { Segmented } from '../components/Segmented'
import { SummaryCard } from '../components/SummaryCard'
import type { PageId } from '../layout/navigation'

type Task = {
  title: string
  detail: string
  action: string
  target: PageId
  tone: 'info' | 'warning' | 'error'
  icon: ReactNode
}

const ICON_PROPS = { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', strokeWidth: 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true }

const TASKS: Task[] = [
  {
    title: '2 orders to review',
    detail: 'Costco and IGA · approve before Oct 13',
    action: 'Review orders',
    target: 'orders',
    tone: 'info',
    icon: <svg {...ICON_PROPS} stroke="var(--color-primary)"><path d="M6 2h12l2 6H4z" /><path d="M4 8v12h16V8" /><path d="M10 12h4" /></svg>,
  },
  {
    title: 'Eggs will run out Saturday',
    detail: 'Forecast is 18 dozen higher than your stock',
    action: 'View forecast',
    target: 'forecast',
    tone: 'error',
    icon: <svg {...ICON_PROPS} stroke="var(--color-error)"><circle cx="12" cy="12" r="9" /><path d="M12 7v6" /><path d="M12 16.5h.01" /></svg>,
  },
  {
    title: '3 menu items not mapped',
    detail: "Their sales aren't counted in the forecast yet",
    action: 'Map items',
    target: 'menu',
    tone: 'warning',
    icon: <svg {...ICON_PROPS} stroke="var(--color-warning)"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" /><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" /></svg>,
  },
]

const TONE_BG = { info: 'var(--color-primary-light)', warning: 'var(--color-warning-bg)', error: 'var(--color-error-bg)' }

const ORDERED_VS_USED = [
  { week: 'Sep 14', ordered: 118, used: 92 },
  { week: 'Sep 21', ordered: 112, used: 94 },
  { week: 'Sep 28', ordered: 104, used: 93 },
  { week: 'Oct 5', ordered: 98, used: 95 },
]

// Ordered but not used last month; costs use the same prices as the vendor orders.
const OVER_ORDERED = [
  { ingredient: 'Lamb leg', kg: 11, cost: 121 },
  { ingredient: 'Feta', kg: 8, cost: 96 },
  { ingredient: 'Tomatoes', kg: 7, cost: 18 },
  { ingredient: 'Ground beef', kg: 5, cost: 40 },
  { ingredient: 'Greek yogurt', kg: 4, cost: 24 },
]

const DISHES = [
  { name: 'Chicken Souvlaki Plate', units: 820, change: '+12%', ingredients: ['Chicken thigh', 'Pita', 'Tzatziki'] },
  { name: 'Doner Gyro Pita', units: 760, change: '+4%', ingredients: ['Lamb leg', 'Pita', 'Red onion'] },
  { name: 'Horiatiki Salad', units: 540, change: '−3%', ingredients: ['Tomatoes', 'Cucumbers', 'Feta'] },
  { name: 'Dolmades', units: 310, change: '+9%', ingredients: ['Grape leaves', 'Rice', 'Lemon'] },
]

const NEXT_ORDERS = [
  { vendor: 'Costco', delivery: 'Oct 14', status: 'DRAFT', total: '$434' },
  { vendor: 'IGA', delivery: 'Oct 15', status: 'DRAFT', total: '$312' },
  { vendor: 'Maxi', delivery: 'Oct 15', status: 'APPROVED', total: '$93' },
]

function OrderedVsUsedChart() {
  const scale = 1.2
  return (
    <svg viewBox="0 0 520 200" style={{ width: '100%', height: 200 }} role="img" aria-label="Kilograms ordered versus actually used per week; the gap shrinks from 26 kg to 3 kg">
      <line x1="10" y1="170" x2="510" y2="170" stroke="var(--color-border)" />
      {ORDERED_VS_USED.map((w, i) => {
        const x = 40 + i * 120
        return (
          <g key={w.week}>
            <rect x={x} y={170 - w.ordered * scale} width="34" height={w.ordered * scale} fill="var(--color-chart-light)" />
            <rect x={x + 38} y={170 - w.used * scale} width="34" height={w.used * scale} fill="var(--color-primary)" />
            <text x={x + 36} y={170 - w.ordered * scale - 6} fontSize="12" textAnchor="middle" fill="var(--color-text-muted)">+{w.ordered - w.used} kg</text>
            <text x={x + 36} y="188" fontSize="13" textAnchor="middle" fill="var(--color-text-muted)">{w.week}</text>
          </g>
        )
      })}
    </svg>
  )
}

function OverOrderedList() {
  const maxKg = Math.max(...OVER_ORDERED.map((item) => item.kg))
  return (
    <div className="stack" style={{ gap: 14 }}>
      {OVER_ORDERED.map((item) => (
        <div key={item.ingredient} style={{ display: 'grid', gridTemplateColumns: '110px 1fr 52px 52px', alignItems: 'center', gap: 12 }}>
          <span>{item.ingredient}</span>
          <div className="progress" style={{ height: 12 }} role="img" aria-label={`${item.kg} kg over-ordered`}>
            <div style={{ width: `${(item.kg / maxKg) * 100}%` }} />
          </div>
          <span style={{ textAlign: 'right', fontWeight: 600 }}>{item.kg} kg</span>
          <span className="label" style={{ textAlign: 'right' }}>${item.cost}</span>
        </div>
      ))}
    </div>
  )
}

export function Home({
  onNavigate,
  enabledPages,
}: {
  onNavigate: (page: PageId) => void
  enabledPages: ReadonlySet<PageId>
}) {
  const visibleTasks = TASKS.filter((task) => enabledPages.has(task.target))

  return (
    <>
      <PageHeader title="Good morning, John" subtitle="Monday, Oct 12 · 3 things need your attention · POS synced 2 h ago" />

      {visibleTasks.length > 0 && (
        <section className="stack">
          <h2 style={{ margin: 0 }}>Needs attention</h2>
          <div className="card" style={{ padding: 0 }}>
            {visibleTasks.map((task, i) => (
              <div
                key={task.title}
                style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '16px 20px', borderTop: i === 0 ? 'none' : '1px solid var(--color-divider)', flexWrap: 'wrap' }}
              >
                <div style={{ width: 40, height: 40, borderRadius: 8, background: TONE_BG[task.tone], display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none' }}>
                  {task.icon}
                </div>
                <div style={{ flex: '1 1 260px' }}>
                  <strong>{task.title}</strong>
                  <div className="label">{task.detail}</div>
                </div>
                <button className={`btn ${i === 0 ? 'btn-primary' : 'btn-secondary'}`} onClick={() => onNavigate(task.target)}>{task.action}</button>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="stack">
        <div className="header" style={{ alignItems: 'center' }}>
          <h2 style={{ margin: 0 }}>How POWR is doing</h2>
          <Segmented options={['Week', 'Month', 'Year']} value="Month" />
        </div>
        <div className="grid-4">
          <SummaryCard label="Waste avoided" value="42 kg" trend="+8% vs last month" />
          <SummaryCard label="Cost avoided" value="$610" trend="+12% vs last month" />
          <SummaryCard label="Forecast accuracy" value="91%" note="Last 4 weeks" />
          <SummaryCard label="Food cost" value="29%" note="of sales" />
        </div>
      </section>

      <div className="row">
        <div className="card" style={{ flex: '1 1 440px' }}>
          <h2 style={{ marginBottom: 4 }}>Ordered vs actually used</h2>
          <div className="label" style={{ marginBottom: 8 }}>Kilograms per week · the gap is food you over-ordered</div>
          <OrderedVsUsedChart />
          <div className="label">
            <span style={{ color: 'var(--color-chart-light)' }}>■</span> Ordered &nbsp;&nbsp;
            <span style={{ color: 'var(--color-primary)' }}>■</span> Used
          </div>
        </div>
        <div className="card" style={{ flex: '1 1 440px' }}>
          <h2 style={{ marginBottom: 4 }}>Most over-ordered ingredients</h2>
          <div className="label" style={{ marginBottom: 16 }}>Last month · bought but not used</div>
          <OverOrderedList />
        </div>
      </div>

      <div className="row">
        <div className="card" style={{ flex: '3 1 520px' }}>
          <h2>Menu item sales trends</h2>
          <table>
            <thead><tr><th>Dish</th><th>Sold this month</th><th>vs last month</th><th>Main ingredients</th></tr></thead>
            <tbody>
              {DISHES.map((dish) => {
                const isDown = dish.change.startsWith('−')
                return (
                  <tr key={dish.name}>
                    <td>{dish.name}</td>
                    <td>{dish.units}</td>
                    <td className={isDown ? 'down' : 'up'}>{isDown ? '↓' : '↑'} {dish.change}</td>
                    <td><span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>{dish.ingredients.map((ing) => <span key={ing} className="tag">{ing}</span>)}</span></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {enabledPages.has('orders') && (
          <div className="card" style={{ flex: '2 1 340px' }}>
            <h2>Next orders</h2>
            <table>
              <thead><tr><th>Vendor</th><th>Delivery</th><th>Status</th><th>Total</th></tr></thead>
              <tbody>
                {NEXT_ORDERS.map((order) => (
                  <tr key={order.vendor}>
                    <td>{order.vendor}</td>
                    <td>{order.delivery}</td>
                    <td><span className={`badge ${order.status === 'APPROVED' ? 'success' : ''}`}>{order.status}</span></td>
                    <td>{order.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <button className="link" style={{ marginTop: 12 }} onClick={() => onNavigate('orders')}>Go to recommended orders →</button>
          </div>
        )}
      </div>
    </>
  )
}
