// Map: native Euclidean coordinates (Solomon 0–100 / Homberger 0–200).
// Renders depot, customer pins, and route polylines. Selection is shared
// with Schedule and Tables; clicking a customer or route highlights everywhere.
import { useMemo, useState } from 'react';
import type {
  CustomerGeometry,
  CustomerScheduleRow,
  DiffResponse,
  Route,
  ScenarioResponse,
} from '../api/types';
import type { Selection } from '../selection';
import { lensColor, type LensMode } from '../lens';

interface Props {
  scenario: ScenarioResponse | null;
  selection: Selection;
  setSelection: (s: Selection) => void;
  lens: LensMode;
  diffData: DiffResponse | null;
}

interface DiffCustomerChange {
  customer_id?: number;
  change_type?: string;
}
interface DiffRouteChange {
  route_label?: string;
  change_type?: string;
}

interface RouteView {
  route_idx: number;
  route_label: string;
  customer_ids: number[];
}

const ROUTE_COLORS = [
  '#f0a92e', '#5ec2e8', '#7cd47a', '#e07a7a', '#c084e8',
  '#e8c44f', '#5ed1b7', '#e89a5e', '#9fb8e8', '#d486c1',
];
const PAD = 4;

function familyBoundFromCustomers(cs: CustomerGeometry[]): number {
  if (!cs.length) return 100;
  let m = 0;
  for (const c of cs) {
    if (c.x > m) m = c.x;
    if (c.y > m) m = c.y;
  }
  return m > 110 ? 200 : 100;
}

function deriveRoutes(scenario: ScenarioResponse): RouteView[] {
  const af = scenario.available_fields;
  const sol = scenario.solution;
  if (af.routes && sol?.routes) {
    return sol.routes.map((r: Route) => ({
      route_idx: r.route_idx,
      route_label: r.route_label,
      customer_ids: r.customer_ids,
    }));
  }
  if (af.customer_schedule && sol?.customer_schedule) {
    const byRoute = new Map<number, { route_idx: number; route_label: string; stops: CustomerScheduleRow[] }>();
    for (const row of sol.customer_schedule) {
      let g = byRoute.get(row.route_idx);
      if (!g) {
        g = { route_idx: row.route_idx, route_label: row.route_label, stops: [] };
        byRoute.set(row.route_idx, g);
      }
      g.stops.push(row);
    }
    return [...byRoute.values()].map((g) => {
      g.stops.sort((a, b) => a.position_in_route - b.position_in_route);
      return {
        route_idx: g.route_idx,
        route_label: g.route_label,
        customer_ids: g.stops.map((s) => s.customer_id),
      };
    });
  }
  return [];
}

interface Hover {
  cid: number;
  px: number; // page px relative to wrap
  py: number;
}

export function MapPanel({ scenario, selection, setSelection, lens, diffData }: Props) {
  const [hover, setHover] = useState<Hover | null>(null);

  // Pre-compute scenario-derived structures (safe with null scenario).
  // Hooks must run on every render in the same order, so we declare useMemo
  // before any early-returns.
  const { customers, depot, bound, customersById, routes, routeOf } = useMemo(() => {
    const cs = scenario?.instance?.customers ?? [];
    const d = scenario?.instance?.depot ?? { x: 0, y: 0 };
    const b = cs.length > 0 ? familyBoundFromCustomers(cs) : 100;
    const cbi = new Map<number, CustomerGeometry>();
    for (const c of cs) cbi.set(c.customer_id, c);
    const rs = scenario ? deriveRoutes(scenario) : [];
    const ro = new Map<number, RouteView>();
    for (const r of rs) for (const cid of r.customer_ids) ro.set(cid, r);
    return { customers: cs, depot: d, bound: b, customersById: cbi, routes: rs, routeOf: ro };
  }, [scenario]);
  const W = bound + PAD * 2;
  const H = bound + PAD * 2;

  // Selection-driven viewBox zoom (declared up-front so hook order is stable).
  const viewBox = useMemo(() => {
    const fullVB = `0 0 ${W} ${H}`;
    if (!scenario || customers.length === 0) return fullVB;
    if (selection.kind === 'none' || selection.kind === 'summary') return fullVB;
    let pts: Array<{ x: number; y: number }> = [];
    if (selection.kind === 'route') {
      const r = routes.find((rr) => rr.route_idx === selection.idx);
      if (!r) return fullVB;
      pts = [{ x: depot.x, y: depot.y }];
      for (const cid of r.customer_ids) {
        const c = customersById.get(cid);
        if (c) pts.push({ x: c.x, y: c.y });
      }
    } else if (selection.kind === 'customer') {
      const c = customersById.get(selection.id);
      if (!c) return fullVB;
      const r = routeOf.get(selection.id);
      pts = [{ x: depot.x, y: depot.y }, { x: c.x, y: c.y }];
      if (r) {
        for (const cid of r.customer_ids) {
          const cc = customersById.get(cid);
          if (cc) pts.push({ x: cc.x, y: cc.y });
        }
      }
    }
    if (pts.length < 2) return fullVB;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const p of pts) {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    }
    const w = maxX - minX;
    const h = maxY - minY;
    const side = Math.max(w, h, bound * 0.18) * 1.25;
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    let vbMinX = cx - side / 2;
    let vbMinY = cy - side / 2;
    vbMinX = Math.max(0, Math.min(vbMinX, bound - side));
    vbMinY = Math.max(0, Math.min(vbMinY, bound - side));
    const clampedSide = Math.min(side, bound);
    const svgMinX = vbMinX + PAD;
    const svgMinY = H - (vbMinY + clampedSide + PAD);
    return `${svgMinX} ${svgMinY} ${clampedSide} ${clampedSide}`;
  }, [scenario, selection, customers, depot, bound, W, H, routes, routeOf, customersById]);

  if (!scenario) {
    return (
      <div className="empty-panel">
        <div>
          <div className="ep-title">No scenario loaded</div>
          Pick a scenario in the top bar to load.
        </div>
      </div>
    );
  }

  if (!scenario.instance || customers.length === 0) {
    return (
      <div className="empty-panel">
        <div>
          <div className="ep-title">No spatial data</div>
          <code>instance.customers</code> is empty for this scenario.
          <br />
          OBJ-family payloads carry an objective value but no geometry.
        </div>
      </div>
    );
  }

  const vx = (x: number) => x + PAD;
  const vy = (y: number) => H - (y + PAD); // y-flip for chart orientation

  const colorFor = (idx: number) => ROUTE_COLORS[idx % ROUTE_COLORS.length];
  const anySel = selection.kind !== 'none';

  // Diff overlay sets
  const changedCustomerIds = new Set<number>();
  const changedRouteLabels = new Set<string>();
  if (diffData) {
    for (const c of (diffData.customer_changes as DiffCustomerChange[])) {
      if (typeof c.customer_id === 'number') changedCustomerIds.add(c.customer_id);
    }
    for (const r of (diffData.route_changes as DiffRouteChange[])) {
      if (typeof r.route_label === 'string') changedRouteLabels.add(r.route_label);
    }
  }
  const diffActive = diffData != null && (changedCustomerIds.size > 0 || changedRouteLabels.size > 0);

  function isRouteSelected(r: RouteView): boolean {
    if (selection.kind === 'route') return selection.idx === r.route_idx;
    if (selection.kind === 'customer') return r.customer_ids.includes(selection.id);
    return false;
  }

  // Lateness lookup (red pins) + per-customer lateness/slack for lens overlay
  const lateIds = new Set<number>();
  const scheduleByCid = new Map<number, CustomerScheduleRow>();
  if (scenario.available_fields.customer_schedule && scenario.solution?.customer_schedule) {
    for (const r of scenario.solution.customer_schedule) {
      if (r.is_late) lateIds.add(r.customer_id);
      scheduleByCid.set(r.customer_id, r);
    }
  }
  // Lens disables when there's no schedule to compute from
  const effLens: LensMode = scheduleByCid.size > 0 ? lens : 'route';

  return (
    <div className="map-wrap">
      <svg
        className="map-svg"
        viewBox={viewBox}
        preserveAspectRatio="xMidYMid meet"
        style={{ transition: 'all 240ms ease' }}
      >
        <defs>
          <pattern
            id="dot-grid-v2"
            x="0"
            y="0"
            width={bound / 10}
            height={bound / 10}
            patternUnits="userSpaceOnUse"
          >
            <circle cx="0" cy="0" r={bound / 250} fill="var(--border)" />
          </pattern>
        </defs>
        <rect x="0" y="0" width={W} height={H} fill="url(#dot-grid-v2)" />

        {/* Route polylines */}
        {routes.map((r) => {
          const sel = isRouteSelected(r);
          const isChanged = changedRouteLabels.has(r.route_label);
          const diffDim = diffActive && !isChanged;
          const dim = (anySel && !sel) || diffDim;
          const color = colorFor(r.route_idx);
          let d = `M ${vx(depot.x)} ${vy(depot.y)} `;
          for (const cid of r.customer_ids) {
            const c = customersById.get(cid);
            if (!c) continue;
            d += `L ${vx(c.x)} ${vy(c.y)} `;
          }
          d += `L ${vx(depot.x)} ${vy(depot.y)}`;
          return (
            <path
              key={'r' + r.route_idx}
              d={d}
              fill="none"
              stroke={color}
              strokeOpacity={dim ? 0.18 : 0.85}
              strokeWidth={
                isChanged ? bound * 0.006 : sel ? bound * 0.005 : bound * 0.003
              }
              strokeDasharray={isChanged ? `${bound * 0.018} ${bound * 0.006}` : undefined}
              style={{ cursor: 'pointer', transition: 'stroke-opacity 120ms' }}
              onClick={() =>
                setSelection({
                  kind: 'route',
                  idx: r.route_idx,
                  label: r.route_label,
                })
              }
            />
          );
        })}

        {/* Customer pins */}
        {customers.map((c) => {
          const isLate = lateIds.has(c.customer_id);
          const route = routeOf.get(c.customer_id);
          const sel =
            (selection.kind === 'customer' && selection.id === c.customer_id) ||
            (selection.kind === 'route' && route?.route_idx === selection.idx);
          const isChangedCustomer = changedCustomerIds.has(c.customer_id);
          const isOnChangedRoute = route ? changedRouteLabels.has(route.route_label) : false;
          const diffDim = diffActive && !isChangedCustomer && !isOnChangedRoute;
          const dim = (anySel && !sel) || diffDim;
          const routeColor = route ? colorFor(route.route_idx) : 'var(--text-faint)';
          const sched = scheduleByCid.get(c.customer_id);
          const slack =
            sched && sched.time_window_end != null && sched.arrival != null
              ? sched.time_window_end - sched.arrival
              : null;
          const lateness = sched?.lateness_minutes ?? 0;
          const lensFill = lensColor(effLens, {
            routeColor,
            isLate,
            lateness,
            slack,
          });
          const pinFill =
            effLens === 'route'
              ? isLate
                ? 'var(--late)'
                : 'var(--surface-3)'
              : lensFill;
          const rad = bound * (sel ? 0.014 : 0.009);
          return (
            <g
              key={c.customer_id}
              transform={`translate(${vx(c.x)} ${vy(c.y)})`}
              style={{
                cursor: 'pointer',
                opacity: dim ? 0.3 : 1,
                transition: 'opacity 120ms',
              }}
              onClick={(e) => {
                e.stopPropagation();
                setSelection({ kind: 'customer', id: c.customer_id });
              }}
              onMouseEnter={(e) => {
                const wrap = e.currentTarget.closest('.map-wrap') as HTMLElement | null;
                if (!wrap) return;
                const rect = wrap.getBoundingClientRect();
                setHover({
                  cid: c.customer_id,
                  px: e.clientX - rect.left,
                  py: e.clientY - rect.top,
                });
              }}
              onMouseMove={(e) => {
                const wrap = e.currentTarget.closest('.map-wrap') as HTMLElement | null;
                if (!wrap) return;
                const rect = wrap.getBoundingClientRect();
                setHover((h) =>
                  h && h.cid === c.customer_id
                    ? { cid: c.customer_id, px: e.clientX - rect.left, py: e.clientY - rect.top }
                    : h,
                );
              }}
              onMouseLeave={() =>
                setHover((h) => (h && h.cid === c.customer_id ? null : h))
              }
            >
              {isChangedCustomer && (
                <circle
                  r={rad * 1.8}
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth={bound * 0.004}
                  strokeDasharray={`${bound * 0.012} ${bound * 0.006}`}
                />
              )}
              <circle
                r={rad}
                fill={pinFill}
                stroke={routeColor}
                strokeWidth={bound * 0.003}
              />
              {sel && (
                <text
                  y={-rad * 2.5}
                  textAnchor="middle"
                  fontFamily="var(--mono)"
                  fontSize={bound * 0.022}
                  fill="var(--text)"
                  style={{
                    paintOrder: 'stroke',
                    stroke: 'var(--surface)',
                    strokeWidth: bound * 0.01,
                  }}
                >
                  C{c.customer_id}
                </text>
              )}
            </g>
          );
        })}

        {/* Depot — yellow square at center */}
        <g transform={`translate(${vx(depot.x)} ${vy(depot.y)})`}>
          <rect
            x={-bound * 0.014}
            y={-bound * 0.014}
            width={bound * 0.028}
            height={bound * 0.028}
            fill="var(--accent)"
            stroke="var(--bg)"
            strokeWidth={bound * 0.004}
          />
        </g>
      </svg>

      <div className="map-tools">
        <span className="chip">
          depot ({depot.x.toFixed(0)}, {depot.y.toFixed(0)})
        </span>
        <span className="chip">{customers.length} customers</span>
        <span className="chip">{routes.length} routes</span>
        {lateIds.size > 0 && <span className="chip late">{lateIds.size} late</span>}
        {diffActive && (
          <span className="chip diff" title="Diff overlay active">
            Δ {changedCustomerIds.size}c {changedRouteLabels.size}r
          </span>
        )}
      </div>
      <div className="map-legend">
        <span style={{ color: 'var(--text-faint)' }}>
          Euclidean · {bound === 100 ? 'Solomon 0–100' : 'Homberger 0–200'}
        </span>
      </div>
      {hover && (() => {
        const c = customersById.get(hover.cid);
        if (!c) return null;
        const route = routeOf.get(hover.cid);
        const sched = scheduleByCid.get(hover.cid);
        const slack =
          sched && sched.time_window_end != null && sched.arrival != null
            ? sched.time_window_end - sched.arrival
            : null;
        return (
          <div
            className="map-tooltip"
            style={{ left: hover.px + 14, top: hover.py + 14 }}
          >
            <div className="mtt-head">
              C{hover.cid}
              {route && (
                <span className="mtt-route" style={{ color: colorFor(route.route_idx) }}>
                  {' '}· {route.route_label}
                </span>
              )}
              {sched?.is_late && <span className="mtt-late"> · LATE</span>}
            </div>
            <div className="mtt-row">
              <span className="k">demand</span>
              <span className="v">{c.demand}</span>
            </div>
            <div className="mtt-row">
              <span className="k">tw</span>
              <span className="v">
                {c.time_window_start.toFixed(1)}–{c.time_window_end.toFixed(1)} sm
              </span>
            </div>
            <div className="mtt-row">
              <span className="k">service</span>
              <span className="v">{c.service_time.toFixed(1)} sm</span>
            </div>
            {sched?.arrival != null && (
              <div className="mtt-row">
                <span className="k">arrival</span>
                <span className="v">
                  {sched.arrival.toFixed(1)} sm
                  {sched.is_late && (
                    <span style={{ color: 'var(--late)' }}>
                      {' '}(+{sched.lateness_minutes.toFixed(1)})
                    </span>
                  )}
                </span>
              </div>
            )}
            {slack != null && (
              <div className="mtt-row">
                <span className="k">slack</span>
                <span className="v">{slack.toFixed(1)} sm</span>
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
}
