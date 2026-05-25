// Routes / Customers / Diff tables. Adapts to available_fields.
// Selection is shared with the Schedule Gantt via App-level state.
import { useEffect, useRef, useState } from 'react';
import type {
  CustomerGeometry,
  DiffResponse,
  ScenarioResponse,
} from '../api/types';
import type { Selection } from '../selection';
import { CollapseToggle } from './CollapseToggle';

type Tab = 'routes' | 'customers' | 'diff';

interface Props {
  scenario: ScenarioResponse | null;
  selection: Selection;
  setSelection: (s: Selection) => void;
  diffData: DiffResponse | null;
  diffLoading: boolean;
  diffNotAvailable: boolean;
  onLoadDiff: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  tab: Tab;
  setTab: (t: Tab) => void;
}

const ROUTE_COLORS = [
  '#f0a92e', '#5ec2e8', '#7cd47a', '#e07a7a', '#c084e8',
  '#e8c44f', '#5ed1b7', '#e89a5e', '#9fb8e8', '#d486c1',
];

interface RouteRowView {
  route_idx: number;
  route_label: string;
  n_stops: number;
  load: number | null;
  capacity: number | null;
  distance: number | null;
  end_time: number | null;
  n_late: number | null;
}

interface CustomerRowView {
  customer_id: number;
  route_idx: number;
  route_label: string;
  arrival: number | null;
  tw_s: number | null;
  tw_e: number | null;
  is_late: boolean;
  lateness: number;
  position: number;
}

function NullCell() {
  return <span className="cell-dim">—</span>;
}

function SmCell({ v }: { v: number | null }) {
  if (v == null) return <NullCell />;
  return (
    <span className="sm-time">
      {v.toFixed(1)}
      <span className="sm-unit">sm</span>
    </span>
  );
}

function buildRoutesView(scenario: ScenarioResponse): RouteRowView[] {
  const af = scenario.available_fields;
  const sol = scenario.solution;
  if (af.routes && sol?.routes) {
    return sol.routes.map((r) => ({
      route_idx: r.route_idx,
      route_label: r.route_label,
      n_stops: r.customer_ids.length,
      load: r.load,
      capacity: r.capacity,
      distance: r.distance,
      end_time: r.end_time,
      n_late: null,
    }));
  }
  if (af.customer_schedule && sol?.customer_schedule) {
    const byRoute = new Map<number, RouteRowView>();
    for (const s of sol.customer_schedule) {
      let r = byRoute.get(s.route_idx);
      if (!r) {
        r = {
          route_idx: s.route_idx,
          route_label: s.route_label,
          n_stops: 0,
          load: null,
          capacity: null,
          distance: null,
          end_time: null,
          n_late: 0,
        };
        byRoute.set(s.route_idx, r);
      }
      r.n_stops++;
      if (s.is_late) r.n_late = (r.n_late ?? 0) + 1;
      if (s.service_end != null && (r.end_time == null || s.service_end > r.end_time)) {
        r.end_time = s.service_end;
      }
    }
    return [...byRoute.values()].sort((a, b) => a.route_idx - b.route_idx);
  }
  return [];
}

function buildCustomersView(scenario: ScenarioResponse): CustomerRowView[] {
  const af = scenario.available_fields;
  const sol = scenario.solution;
  const out: CustomerRowView[] = [];
  if (af.customer_schedule && sol?.customer_schedule) {
    for (const s of sol.customer_schedule) {
      out.push({
        customer_id: s.customer_id,
        route_idx: s.route_idx,
        route_label: s.route_label,
        arrival: s.arrival,
        tw_s: s.time_window_start,
        tw_e: s.time_window_end,
        is_late: s.is_late,
        lateness: s.lateness_minutes,
        position: s.position_in_route,
      });
    }
  } else if (af.routes && sol?.routes && scenario.instance) {
    const byCid = new Map<number, CustomerGeometry>();
    for (const c of scenario.instance.customers) byCid.set(c.customer_id, c);
    for (const r of sol.routes) {
      r.customer_ids.forEach((cid, pos) => {
        const c = byCid.get(cid);
        out.push({
          customer_id: cid,
          route_idx: r.route_idx,
          route_label: r.route_label,
          arrival: null,
          tw_s: c?.time_window_start ?? null,
          tw_e: c?.time_window_end ?? null,
          is_late: false,
          lateness: 0,
          position: pos,
        });
      });
    }
  }
  out.sort((a, b) => a.customer_id - b.customer_id);
  return out;
}

interface RoutesTableProps {
  rows: RouteRowView[];
  selection: Selection;
  setSelection: (s: Selection) => void;
}

function RoutesTable({ rows, selection, setSelection }: RoutesTableProps) {
  return (
    <table className="data">
      <thead>
        <tr>
          <th style={{ width: 110 }}>route_label</th>
          <th>customers</th>
          <th>load</th>
          <th>distance</th>
          <th>end_time</th>
          <th>late</th>
          <th>status</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const sel = selection.kind === 'route' && selection.idx === r.route_idx;
          return (
            <tr
              key={r.route_idx}
              id={'route-row-' + r.route_idx}
              className={sel ? 'selected' : ''}
              onClick={() =>
                setSelection({
                  kind: 'route',
                  idx: r.route_idx,
                  label: r.route_label,
                })
              }
            >
              <td>
                <span
                  style={{
                    display: 'inline-block',
                    width: 8,
                    height: 8,
                    background: ROUTE_COLORS[r.route_idx % ROUTE_COLORS.length],
                    marginRight: 8,
                    verticalAlign: 'middle',
                  }}
                />
                {r.route_label}
              </td>
              <td className="cell-num">{r.n_stops}</td>
              <td className="cell-num">
                {r.load == null ? <NullCell /> : `${r.load}/${r.capacity ?? '?'}`}
              </td>
              <td className="cell-num">
                {r.distance == null ? <NullCell /> : r.distance.toFixed(1)}
              </td>
              <td>
                <SmCell v={r.end_time} />
              </td>
              <td
                className={
                  'cell-num ' + ((r.n_late ?? 0) > 0 ? 'cell-late' : 'cell-dim')
                }
              >
                {r.n_late == null ? '—' : r.n_late}
              </td>
              <td>
                {r.n_late == null ? (
                  <span className="badge info">STRUCT</span>
                ) : r.n_late > 0 ? (
                  <span className="badge late">LATE</span>
                ) : (
                  <span className="badge ok">OK</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

interface CustomersTableProps {
  rows: CustomerRowView[];
  selection: Selection;
  setSelection: (s: Selection) => void;
}

function CustomersTable({ rows, selection, setSelection }: CustomersTableProps) {
  return (
    <table className="data">
      <thead>
        <tr>
          <th>customer_id</th>
          <th>route_label</th>
          <th>arrival</th>
          <th>time_window</th>
          <th>lateness</th>
          <th>is_late</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => {
          const sel = selection.kind === 'customer' && selection.id === c.customer_id;
          return (
            <tr
              key={c.customer_id}
              id={'cust-row-' + c.customer_id}
              className={sel ? 'selected' : ''}
              onClick={() =>
                setSelection({ kind: 'customer', id: c.customer_id })
              }
            >
              <td>C{c.customer_id}</td>
              <td>
                <span
                  style={{
                    display: 'inline-block',
                    width: 6,
                    height: 6,
                    background: ROUTE_COLORS[c.route_idx % ROUTE_COLORS.length],
                    marginRight: 6,
                    verticalAlign: 'middle',
                  }}
                />
                {c.route_label}
              </td>
              <td>
                <SmCell v={c.arrival} />
              </td>
              <td className="cell-num cell-dim">
                {c.tw_s == null || c.tw_e == null ? (
                  '—'
                ) : (
                  <span>
                    <span className="sm-time">{c.tw_s.toFixed(1)}</span> –{' '}
                    <span className="sm-time">{c.tw_e.toFixed(1)}</span>
                    <span className="sm-unit"> sm</span>
                  </span>
                )}
              </td>
              <td className={'cell-num ' + (c.is_late ? 'cell-late' : 'cell-dim')}>
                {c.lateness > 0 ? '+' + c.lateness.toFixed(1) + ' sm' : '—'}
              </td>
              <td>
                {c.is_late ? (
                  <span className="badge late">LATE</span>
                ) : (
                  <span className="cell-dim">—</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

interface DiffTabProps {
  hasDiff: boolean;
  diffData: DiffResponse | null;
  loading: boolean;
  notAvailable: boolean;
}

// Diff customer/route change items are typed as Record<string, unknown> on the
// API; the design assumes these specific keys. We narrow defensively here.
interface CustomerChangeAny {
  customer_id?: number;
  change_type?: string;
  from_route_label?: string;
  to_route_label?: string;
  arrival_delta_minutes?: number;
}

interface RouteChangeAny {
  route_label?: string;
  change_type?: string;
  before_end_time?: number;
  after_end_time?: number;
  delta_minutes?: number;
}

function DiffTab({ hasDiff, diffData, loading, notAvailable }: DiffTabProps) {
  if (loading) {
    return (
      <div
        style={{
          padding: 24,
          color: 'var(--text-faint)',
          fontFamily: 'var(--mono)',
          fontSize: 11,
        }}
      >
        Fetching <code>POST /diff</code>…
      </div>
    );
  }
  if (!diffData || notAvailable || !hasDiff) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <div
          className="ep-title"
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 12,
            letterSpacing: '0.16em',
            textTransform: 'uppercase',
            color: 'var(--text-dim)',
            marginBottom: 10,
          }}
        >
          Diff not available
        </div>
        <div
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 11,
            color: 'var(--text-faint)',
            maxWidth: 520,
            margin: '0 auto',
            lineHeight: 1.6,
          }}
        >
          <code>POST /scenarios/.../diff</code> returns{' '}
          <code style={{ color: 'var(--late)' }}>404 diff_not_available</code> for this
          scenario.
          <br />
          The payload carries no <code>baseline_solution</code> or{' '}
          <code>diff</code> field. Most Run-1 scenarios share this state — diff is a
          rarely-available affordance.
        </div>
      </div>
    );
  }
  const customerChanges = diffData.customer_changes as CustomerChangeAny[];
  const routeChanges = diffData.route_changes as RouteChangeAny[];
  return (
    <div className="diff-list">
      <div className="diff-card">
        <div className="dc-head">
          <span>objective_delta_absolute</span>
          <span>delta</span>
        </div>
        <div className="dc-body">
          <span style={{ fontSize: 20 }} className="delta-pos">
            {(diffData.objective_delta_absolute ?? 0) >= 0 ? '+' : ''}
            {(diffData.objective_delta_absolute ?? 0).toFixed(1)}
          </span>{' '}
          <span style={{ color: 'var(--text-faint)' }}>
            ({(diffData.objective_delta_percent ?? 0).toFixed(1)}%)
          </span>
        </div>
      </div>
      <div className="diff-card">
        <div className="dc-head">
          <span>feasibility_changed</span>
        </div>
        <div className="dc-body">
          {diffData.feasibility_changed ? (
            <span className="delta-pos">YES</span>
          ) : (
            <span style={{ color: 'var(--text-dim)' }}>no</span>
          )}
        </div>
      </div>
      {customerChanges.map((c, i) => (
        <div className="diff-card" key={'cc' + i}>
          <div className="dc-head">
            <span>C{c.customer_id}</span>
            <span>{c.change_type ?? '—'}</span>
          </div>
          <div className="dc-body">
            {c.change_type === 'moved_route' && (
              <span>
                {c.from_route_label}{' '}
                <span style={{ color: 'var(--text-faint)' }}>→</span>{' '}
                {c.to_route_label}
              </span>
            )}
            {c.change_type === 'arrival_shifted' && c.arrival_delta_minutes != null && (
              <span>
                {c.from_route_label} ·{' '}
                <span
                  className={c.arrival_delta_minutes >= 0 ? 'delta-pos' : 'delta-neg'}
                >
                  {c.arrival_delta_minutes >= 0 ? '+' : ''}
                  {c.arrival_delta_minutes} sm
                </span>
              </span>
            )}
          </div>
        </div>
      ))}
      {routeChanges.map((r, i) => (
        <div className="diff-card" key={'rc' + i}>
          <div className="dc-head">
            <span>{r.route_label ?? '—'}</span>
            <span>{r.change_type ?? '—'}</span>
          </div>
          <div className="dc-body">
            {r.before_end_time?.toFixed(1)}{' '}
            <span style={{ color: 'var(--text-faint)' }}>→</span>{' '}
            {r.after_end_time?.toFixed(1)} sm{' '}
            {r.delta_minutes != null && (
              <span className={r.delta_minutes >= 0 ? 'delta-pos' : 'delta-neg'}>
                ({r.delta_minutes >= 0 ? '+' : ''}
                {r.delta_minutes.toFixed(1)})
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export type { Tab as TablesTab };

export function TablesPanel({
  scenario,
  selection,
  setSelection,
  diffData,
  diffLoading,
  diffNotAvailable,
  onLoadDiff,
  collapsed,
  onToggleCollapse,
  tab,
  setTab,
}: Props) {
  const [q, setQ] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll the selected row into view
  useEffect(() => {
    if (!scrollRef.current || !scenario) return;
    const af = scenario.available_fields;
    let rowId: string | null = null;
    if (tab === 'routes' && selection.kind === 'route') {
      rowId = 'route-row-' + selection.idx;
    } else if (tab === 'routes' && selection.kind === 'customer') {
      if (af.customer_schedule && scenario.solution?.customer_schedule) {
        const row = scenario.solution.customer_schedule.find(
          (r) => r.customer_id === selection.id,
        );
        if (row) rowId = 'route-row-' + row.route_idx;
      } else if (af.routes && scenario.solution?.routes) {
        const r = scenario.solution.routes.find((r) =>
          r.customer_ids.includes(selection.id),
        );
        if (r) rowId = 'route-row-' + r.route_idx;
      }
    } else if (tab === 'customers' && selection.kind === 'customer') {
      rowId = 'cust-row-' + selection.id;
    }
    if (!rowId) return;
    const container = scrollRef.current;
    const el = container.querySelector<HTMLElement>('#' + CSS.escape(rowId));
    if (!el) return;
    const cRect = container.getBoundingClientRect();
    const eRect = el.getBoundingClientRect();
    if (eRect.top < cRect.top + 30 || eRect.bottom > cRect.bottom) {
      const target =
        container.scrollTop +
        (eRect.top - cRect.top) -
        cRect.height / 2 +
        eRect.height / 2;
      container.scrollTo({ top: target, behavior: 'smooth' });
    }
  }, [selection, tab, scenario]);

  if (!scenario) {
    return (
      <>
        <div className="panel-head" style={{ padding: 0 }}>
          <div className="tab-strip">
            <button className="active" disabled>
              Routes
            </button>
            <button disabled>Customers</button>
            <button disabled>Diff</button>
          </div>
          <span className="spacer" />
          <CollapseToggle collapsed={collapsed} onToggle={onToggleCollapse} />
        </div>
        <div className="panel-body">
          <div className="empty-panel">
            <div>
              <div className="ep-title">No scenario</div>
              Pick a scenario in the top bar to populate.
            </div>
          </div>
        </div>
      </>
    );
  }

  const af = scenario.available_fields;
  const routesView = buildRoutesView(scenario);
  const custView = buildCustomersView(scenario);
  const ft = q.trim().toUpperCase();
  const custFiltered = ft
    ? custView.filter(
        (c) =>
          String(c.customer_id).includes(ft) ||
          c.route_label.toUpperCase().includes(ft),
      )
    : custView;

  return (
    <>
      <div className="panel-head" style={{ padding: 0 }}>
        <div className="tab-strip">
          <button
            className={tab === 'routes' ? 'active' : ''}
            onClick={() => setTab('routes')}
          >
            Routes ({routesView.length})
          </button>
          <button
            className={tab === 'customers' ? 'active' : ''}
            onClick={() => setTab('customers')}
          >
            Customers ({custView.length})
          </button>
          <button
            className={tab === 'diff' ? 'active' : ''}
            onClick={() => {
              setTab('diff');
              if (!diffData && !diffLoading && !diffNotAvailable) onLoadDiff();
            }}
          >
            Diff{diffData ? ' ✓' : af.diff ? ' ●' : ''}
          </button>
        </div>
        <span className="spacer" />
        {tab === 'customers' && (
          <input
            className="table-search"
            placeholder="Search customer_id / route…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        )}
        <CollapseToggle collapsed={collapsed} onToggle={onToggleCollapse} />
      </div>
      <div className="panel-body">
        <div className="tbl-scroll scroll-thin" ref={scrollRef}>
          {tab === 'routes' && (
            <RoutesTable
              rows={routesView}
              selection={selection}
              setSelection={setSelection}
            />
          )}
          {tab === 'customers' && (
            <CustomersTable
              rows={custFiltered}
              selection={selection}
              setSelection={setSelection}
            />
          )}
          {tab === 'diff' && (
            <DiffTab
              hasDiff={af.diff}
              diffData={diffData}
              loading={diffLoading}
              notAvailable={diffNotAvailable}
            />
          )}
        </div>
      </div>
    </>
  );
}
