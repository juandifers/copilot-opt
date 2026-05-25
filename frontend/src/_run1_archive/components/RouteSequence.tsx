import { useMemo } from 'react';
import type { RoutePolyline, ScheduleRow, VisualContext } from '../types';

interface Props {
  visual: VisualContext | null;
}

function scheduleLookup(
  schedule: ScheduleRow[],
): Map<number, ScheduleRow> {
  const m = new Map<number, ScheduleRow>();
  for (const row of schedule) {
    if (typeof row.customer_id === 'number') {
      m.set(row.customer_id, row);
    }
  }
  return m;
}

function pickRoutesToShow(visual: VisualContext): RoutePolyline[] {
  const highlightedIdxs = new Set(
    visual.highlighted_routes.map((r) => r.route_idx),
  );
  if (highlightedIdxs.size > 0) {
    return visual.routes.filter((r) => highlightedIdxs.has(r.route_idx));
  }
  // If a customer is highlighted, surface that customer's route(s).
  const highlightedCust = new Set(visual.highlighted_customers);
  if (highlightedCust.size > 0) {
    return visual.routes.filter((r) =>
      r.customer_ids.some((c) => highlightedCust.has(c)),
    );
  }
  return [];
}

function nodeLabel(customer_id: number, kind: 'depot' | 'customer'): string {
  if (kind === 'depot') return 'Depot';
  return `C${customer_id}`;
}

function nodeSubtitle(
  customer_id: number,
  kind: 'depot' | 'customer',
  schedule: Map<number, ScheduleRow>,
): string | null {
  if (kind === 'depot') return null;
  const row = schedule.get(customer_id);
  if (!row) return null;
  const arr = row.arrival;
  const start = row.start_service;
  if (arr == null && start == null) return null;
  if (arr != null && start != null) return `arr ${arr} · svc ${start}`;
  if (arr != null) return `arr ${arr}`;
  if (start != null) return `svc ${start}`;
  return null;
}

export function RouteSequence({ visual }: Props) {
  const routes = useMemo(() => (visual ? pickRoutesToShow(visual) : []), [visual]);
  const highlighted = useMemo(
    () => new Set(visual?.highlighted_customers ?? []),
    [visual],
  );
  const schedule = useMemo(
    () => scheduleLookup(visual?.schedule ?? []),
    [visual],
  );

  if (!visual) {
    return (
      <section className="panel">
        <h2>Route sequence</h2>
        <p className="loading">Select a prompt to view route sequence.</p>
      </section>
    );
  }

  if (routes.length === 0) {
    return (
      <section className="panel">
        <h2>Route sequence</h2>
        <p className="loading">
          No route is highlighted for this prompt. Select or inspect a
          route-referencing prompt (e.g. 029, 040, 046) to see the depot →
          customers → depot sequence.
        </p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>Route sequence</h2>
      <p className="panel-note">
        Depot → customers → depot for the route(s) implied by the evidence.
        Times shown when a SCHEDULE payload is available.
      </p>
      {routes.map((route) => {
        const label =
          route.route_label ??
          `Route ${route.display_route_number ?? route.route_idx + 1}`;
        return (
          <div key={route.route_idx} style={{ marginTop: 10 }}>
            <div
              style={{
                fontSize: '0.82rem',
                color: 'var(--text-dim)',
                marginBottom: 4,
              }}
            >
              {label}{' '}
              <code style={{ marginLeft: 6 }}>route_idx={route.route_idx}</code>{' '}
              · {route.n_customers} customers
            </div>
            <div className="route-sequence">
              {route.points.map((p, i) => {
                const isHighlighted =
                  p.kind === 'customer' && highlighted.has(p.customer_id);
                const sub = nodeSubtitle(p.customer_id, p.kind, schedule);
                return (
                  <div key={`${route.route_idx}-${i}`} className="route-node-wrap">
                    <div
                      className={`route-node ${p.kind} ${isHighlighted ? 'highlighted' : ''}`}
                    >
                      <div className="node-label">
                        {nodeLabel(p.customer_id, p.kind)}
                      </div>
                      {sub && <div className="node-sub">{sub}</div>}
                    </div>
                    {i < route.points.length - 1 && (
                      <div className="route-arrow">→</div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </section>
  );
}
