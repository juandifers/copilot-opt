// Schedule Gantt over Solomon-minutes. One row per route_idx.
// Time axis auto-fits to the data + adds 2%/4% padding.
// Track width auto-fills the container via ResizeObserver, so short-span
// scenarios (RC101 ~210 sm) and long-span scenarios (C105 ~1230 sm) both
// fill the panel horizontally.
// Route end times are derived from max(service_end) per route_idx
// (the API doesn't expose them separately for SCHEDULE-shape payloads).
import React, { Fragment, useLayoutEffect, useRef, useState } from 'react';
import type {
  CustomerScheduleRow,
  DiffResponse,
  ScenarioResponse,
} from '../api/types';
import { EMPTY_HIGHLIGHTS, type Highlights, type Selection } from '../selection';
import { lensColor, type LensMode } from '../lens';

const LABEL_COL_PX = 110;
const PADDING_PX = 28; // schedule-grid padding 14px L/R
const MIN_TRACK_PX = 300;

interface Props {
  scenario: ScenarioResponse | null;
  selection: Selection;
  setSelection: (s: Selection) => void;
  highlights?: Highlights;
  lens: LensMode;
  diffData: DiffResponse | null;
}

interface DiffRouteChange {
  route_label?: string;
  delta_minutes?: number;
  change_type?: string;
}
interface DiffCustomerChange {
  customer_id?: number;
  change_type?: string;
  arrival_delta_minutes?: number;
}

const ROUTE_COLORS = [
  '#f0a92e',
  '#5ec2e8',
  '#7cd47a',
  '#e07a7a',
  '#c084e8',
  '#e8c44f',
  '#5ed1b7',
  '#e89a5e',
  '#9fb8e8',
  '#d486c1',
];

const TICK_TARGETS = [50, 100, 200, 250, 500, 1000];

function pickTickStep(span: number): number {
  for (const t of TICK_TARGETS) if (span / t < 12) return t;
  return 1000;
}

interface RouteGroup {
  route_idx: number;
  route_label: string;
  stops: CustomerScheduleRow[];
  end_time: number | null;
}

function renderEmptyState(scenario: ScenarioResponse | null): React.ReactNode | null {
  if (!scenario) {
    return (
      <div className="empty-panel">
        <div>
          <div className="ep-title">No scenario</div>
          Pick a scenario in the top bar to load.
        </div>
      </div>
    );
  }
  if (!scenario.available_fields.customer_schedule) {
    return (
      <div className="empty-panel">
        <div>
          <div className="ep-title">Schedule unavailable</div>
          <code>available_fields.customer_schedule</code> = <code>false</code>
          <br />
          Switch to a SCHEDULE-shape payload to populate this panel.
        </div>
      </div>
    );
  }
  const schedule = scenario.solution?.customer_schedule ?? [];
  if (schedule.length === 0) {
    return (
      <div className="empty-panel">
        <div>
          <div className="ep-title">Empty schedule</div>
          Payload returned <code>customer_schedule = []</code>.
        </div>
      </div>
    );
  }
  return null;
}

export function SchedulePanel({
  scenario,
  selection,
  setSelection,
  highlights = EMPTY_HIGHLIGHTS,
  lens,
  diffData,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [wrapWidth, setWrapWidth] = useState<number>(800);
  const [cursorX, setCursorX] = useState<number | null>(null);
  useLayoutEffect(() => {
    if (!wrapRef.current) return;
    const el = wrapRef.current;
    setWrapWidth(el.clientWidth);
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w && Number.isFinite(w)) setWrapWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [scenario]);

  // Render gate: empty states still need the ref attached for width tracking.
  const empty = renderEmptyState(scenario);
  if (empty) {
    return (
      <div
        ref={wrapRef}
        style={{ position: 'absolute', inset: 0 }}
      >
        {empty}
      </div>
    );
  }

  const schedule = scenario!.solution!.customer_schedule!;

  // Time range — auto-fit
  const numericValues: number[] = [];
  for (const r of schedule) {
    for (const v of [r.time_window_start, r.time_window_end, r.arrival, r.service_end]) {
      if (v != null) numericValues.push(v);
    }
  }
  if (numericValues.length === 0) {
    return (
      <div ref={wrapRef} style={{ position: 'absolute', inset: 0 }}>
        <div className="empty-panel">
          <div>
            <div className="ep-title">No time values</div>
            Schedule rows carried no time-window or arrival data.
          </div>
        </div>
      </div>
    );
  }
  let tMin = Math.min(...numericValues);
  let tMax = Math.max(...numericValues);
  const span0 = tMax - tMin;
  tMin = Math.max(0, tMin - span0 * 0.02);
  tMax = tMax + span0 * 0.04;
  // Auto-fit pxPerMin so the gantt fills the container horizontally.
  const availableTrack = Math.max(MIN_TRACK_PX, wrapWidth - LABEL_COL_PX - PADDING_PX);
  const pxPerMin = availableTrack / (tMax - tMin);
  const trackWidth = (tMax - tMin) * pxPerMin;
  const x = (m: number) => (m - tMin) * pxPerMin;

  // Group by route
  const byRoute = new Map<number, RouteGroup>();
  for (const row of schedule) {
    let g = byRoute.get(row.route_idx);
    if (!g) {
      g = {
        route_idx: row.route_idx,
        route_label: row.route_label,
        stops: [],
        end_time: null,
      };
      byRoute.set(row.route_idx, g);
    }
    g.stops.push(row);
  }
  const routes: RouteGroup[] = [...byRoute.values()].sort(
    (a, b) => a.route_idx - b.route_idx,
  );
  for (const r of routes) {
    r.stops.sort((a, b) => a.position_in_route - b.position_in_route);
    let end: number | null = null;
    for (const s of r.stops) {
      if (s.service_end != null && (end == null || s.service_end > end)) {
        end = s.service_end;
      }
    }
    r.end_time = end;
  }

  // Ticks
  const tickStep = pickTickStep(tMax - tMin);
  const firstTick = Math.ceil(tMin / tickStep) * tickStep;
  const ticks: number[] = [];
  for (let t = firstTick; t <= tMax; t += tickStep) ticks.push(t);

  // Diff overlay lookups
  const routeDeltaByLabel = new Map<string, number>();
  const changedCustomerIds = new Set<number>();
  const customerDeltaById = new Map<number, number>();
  if (diffData) {
    for (const r of (diffData.route_changes as DiffRouteChange[])) {
      if (typeof r.route_label === 'string' && typeof r.delta_minutes === 'number') {
        routeDeltaByLabel.set(r.route_label, r.delta_minutes);
      }
    }
    for (const c of (diffData.customer_changes as DiffCustomerChange[])) {
      if (typeof c.customer_id === 'number') {
        changedCustomerIds.add(c.customer_id);
        if (typeof c.arrival_delta_minutes === 'number') {
          customerDeltaById.set(c.customer_id, c.arrival_delta_minutes);
        }
      }
    }
  }
  const diffActive =
    diffData != null && (routeDeltaByLabel.size > 0 || changedCustomerIds.size > 0);

  const cursorTime = cursorX != null ? tMin + cursorX / pxPerMin : null;

  return (
    <div ref={wrapRef} style={{ position: 'absolute', inset: 0 }}>
    <div className="schedule-wrap scroll-thin">
      <div
        className="schedule-grid"
        style={{ width: trackWidth + 130 }}
        onMouseMove={(e) => {
          const tr = (e.currentTarget as HTMLElement).querySelector('.sched-track') as HTMLElement | null;
          if (!tr) return;
          const rect = tr.getBoundingClientRect();
          const x = e.clientX - rect.left;
          if (x < 0 || x > rect.width) {
            setCursorX(null);
          } else {
            setCursorX(x);
          }
        }}
        onMouseLeave={() => setCursorX(null)}
      >
        <div className="sched-hours" style={{ width: trackWidth }}>
          {ticks.map((t, i) => (
            <Fragment key={i}>
              <div className="tick" style={{ left: x(t) }} />
              <div className="h" style={{ left: x(t) }}>
                {Math.round(t)}
              </div>
            </Fragment>
          ))}
          {cursorX != null && cursorTime != null && (
            <div className="cursor-readout" style={{ left: cursorX }}>
              {cursorTime.toFixed(1)} sm
            </div>
          )}
        </div>
        {cursorX != null && (
          <div className="cursor-line" style={{ left: LABEL_COL_PX + cursorX + 14 }} />
        )}
        {routes.map((r) => {
          const sel =
            (selection.kind === 'route' && selection.idx === r.route_idx) ||
            (selection.kind === 'customer' &&
              r.stops.some((s) => s.customer_id === selection.id)) ||
            highlights.routes.has(r.route_idx) ||
            r.stops.some((s) => highlights.customers.has(s.customer_id));
          const color = ROUTE_COLORS[r.route_idx % ROUTE_COLORS.length];
          const nLate = r.stops.filter((s) => s.is_late).length;
          const rDelta = routeDeltaByLabel.get(r.route_label);
          const isChangedRoute =
            rDelta != null ||
            r.stops.some((s) => changedCustomerIds.has(s.customer_id));
          const diffDim = diffActive && !isChangedRoute;
          return (
            <div
              key={r.route_idx}
              className={
                'sched-row' +
                (sel ? ' selected' : '') +
                (isChangedRoute ? ' diff-changed' : '') +
                (diffDim ? ' diff-dim' : '')
              }
              onClick={() =>
                setSelection({
                  kind: 'route',
                  idx: r.route_idx,
                  label: r.route_label,
                })
              }
            >
              <div className="rlabel">
                <span className="rdot" style={{ background: color }} />
                {r.route_label}
                <span className="rmeta">
                  · {r.stops.length}st
                  {nLate > 0 && (
                    <span style={{ color: 'var(--late)' }}> · {nLate} late</span>
                  )}
                  {rDelta != null && (
                    <span
                      className={'rdelta ' + (rDelta >= 0 ? 'pos' : 'neg')}
                      title={`route end ${rDelta >= 0 ? '+' : ''}${rDelta.toFixed(1)} sm vs baseline`}
                    >
                      {' '}
                      Δ{rDelta >= 0 ? '+' : ''}
                      {rDelta.toFixed(1)}
                    </span>
                  )}
                </span>
              </div>
              <div className="sched-track" style={{ width: trackWidth }}>
                {r.end_time != null && (
                  <div
                    className="baseline-line"
                    style={{ left: 0, width: x(r.end_time) }}
                  />
                )}
                {r.stops.map((s) => {
                  if (s.time_window_start == null || s.time_window_end == null) return null;
                  const left = x(s.time_window_start);
                  const width = Math.max(2, x(s.time_window_end) - left);
                  return (
                    <div
                      key={'tw' + s.customer_id}
                      className="tw-bar"
                      style={{ left, width }}
                      title={`C${s.customer_id} TW: ${s.time_window_start.toFixed(1)}–${s.time_window_end.toFixed(1)} sm`}
                    />
                  );
                })}
                {r.stops.map((s) => {
                  if (s.arrival == null) return null;
                  const customerSel =
                    (selection.kind === 'customer' && selection.id === s.customer_id) ||
                    highlights.customers.has(s.customer_id);
                  const slack =
                    s.time_window_end != null && s.arrival != null
                      ? s.time_window_end - s.arrival
                      : null;
                  const dotColor =
                    lens === 'route'
                      ? undefined
                      : lensColor(lens, {
                          routeColor: color,
                          isLate: s.is_late,
                          lateness: s.lateness_minutes,
                          slack,
                        });
                  const cDelta = customerDeltaById.get(s.customer_id);
                  const isChangedCustomer = changedCustomerIds.has(s.customer_id);
                  return (
                    <div
                      key={'a' + s.customer_id}
                      className={
                        'arrival-dot' +
                        (s.is_late && lens === 'route' ? ' late' : '') +
                        (customerSel ? ' selected' : '') +
                        (isChangedCustomer ? ' diff-marked' : '')
                      }
                      style={
                        dotColor
                          ? { left: x(s.arrival), background: dotColor }
                          : { left: x(s.arrival) }
                      }
                      title={`C${s.customer_id}: arrive ${s.arrival.toFixed(1)} sm${
                        s.is_late ? ' · LATE +' + s.lateness_minutes.toFixed(1) : ''
                      }${slack != null ? ' · slack ' + slack.toFixed(1) + ' sm' : ''}${
                        cDelta != null ? ' · Δ' + (cDelta >= 0 ? '+' : '') + cDelta.toFixed(1) + ' sm' : ''
                      }`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelection({ kind: 'customer', id: s.customer_id });
                      }}
                    />
                  );
                })}
                {r.end_time != null && (
                  <div className="end-tag" style={{ left: x(r.end_time) }}>
                    {r.end_time.toFixed(1)}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
    </div>
  );
}
