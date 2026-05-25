import type { ProductCopilotResponse } from '../types';

interface Props {
  context: ProductCopilotResponse | null;
}

type Dict = Record<string, unknown>;

function isDict(x: unknown): x is Dict {
  return typeof x === 'object' && x !== null && !Array.isArray(x);
}

function num(x: unknown): string {
  if (x == null) return '—';
  if (typeof x === 'number') return Number.isInteger(x) ? String(x) : x.toFixed(3);
  return String(x);
}

function bool(x: unknown): string {
  if (x === true) return 'yes';
  if (x === false) return 'no';
  return '—';
}

function ObjectiveCard({ payload }: { payload: Dict }) {
  const action = payload.action_objective;
  const base = payload.baseline_objective;
  const dAbs = payload.objective_delta_absolute;
  const dPct = payload.objective_delta_percent;
  const units = isDict(payload.units) ? String(payload.units.objective ?? '') : '';
  if (action == null && base == null && dAbs == null && dPct == null) return null;
  return (
    <section className="panel">
      <h2>Objective</h2>
      <div className="kv-row">
        <span className="k">action_objective</span>
        <span className="v">
          {num(action)} {units && <small>({units})</small>}
        </span>
      </div>
      <div className="kv-row">
        <span className="k">baseline_objective</span>
        <span className="v">{num(base)}</span>
      </div>
      <div className="kv-row">
        <span className="k">objective_delta_absolute</span>
        <span className="v">{num(dAbs)}</span>
      </div>
      <div className="kv-row">
        <span className="k">objective_delta_percent</span>
        <span className="v">{num(dPct)}</span>
      </div>
    </section>
  );
}

function FeasibilityCard({ payload }: { payload: Dict }) {
  const feasible = payload.feasible;
  if (feasible === undefined) return null;
  const breakdown = isDict(payload.feasibility_breakdown)
    ? payload.feasibility_breakdown
    : {};
  const capacity = breakdown.capacity_ok ?? payload.capacity_ok;
  const tw = breakdown.time_windows_ok ?? payload.time_windows_ok;
  const coverage = breakdown.coverage_ok ?? payload.coverage_ok;
  const n = payload.n_unserved_customers;
  const ids = Array.isArray(payload.unserved_customer_ids)
    ? (payload.unserved_customer_ids as unknown[])
    : [];

  return (
    <section className="panel">
      <h2>Feasibility</h2>
      <div className="kv-row">
        <span className="k">feasible</span>
        <span
          className={`badge ${feasible === true ? 'answerable' : feasible === false ? 'not_answerable' : 'neutral'}`}
        >
          {bool(feasible)}
        </span>
      </div>
      <div className="kv-row">
        <span className="k">capacity_ok</span>
        <span className="v">{bool(capacity)}</span>
      </div>
      <div className="kv-row">
        <span className="k">time_windows_ok</span>
        <span className="v">{bool(tw)}</span>
      </div>
      <div className="kv-row">
        <span className="k">coverage_ok</span>
        <span className="v">{bool(coverage)}</span>
      </div>
      <div className="kv-row">
        <span className="k">n_unserved_customers</span>
        <span className="v">{num(n)}</span>
      </div>
      {ids.length > 0 && (
        <div className="kv-row">
          <span className="k">unserved_customer_ids</span>
          <span className="v">{ids.map(String).join(', ')}</span>
        </div>
      )}
    </section>
  );
}

function RouteTableCard({ payload }: { payload: Dict }) {
  const routes = payload.routes;
  if (!Array.isArray(routes) || routes.length === 0) return null;
  return (
    <section className="panel">
      <h2>Routes ({routes.length})</h2>
      <table className="simple-table">
        <thead>
          <tr>
            <th>display</th>
            <th>route_idx</th>
            <th>route_label</th>
            <th># cust.</th>
            <th>customer_ids</th>
          </tr>
        </thead>
        <tbody>
          {routes.map((rRaw, i) => {
            const r = isDict(rRaw) ? rRaw : {};
            const ids = Array.isArray(r.customer_ids)
              ? (r.customer_ids as unknown[]).map(String)
              : [];
            return (
              <tr key={i}>
                <td className="num">{num(r.display_route_number)}</td>
                <td className="num">{num(r.route_idx)}</td>
                <td>{String(r.route_label ?? '—')}</td>
                <td className="num">{ids.length}</td>
                <td style={{ whiteSpace: 'normal', wordBreak: 'break-word' }}>
                  {ids.join(', ')}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

function highlightedCustomerIdsFromContext(
  context: ProductCopilotResponse,
): Set<number> {
  const set = new Set<number>();
  for (const a of context.visual_actions ?? []) {
    if (a.kind !== 'highlight_customer') continue;
    const t = a.target as Dict;
    const ids = t.customer_ids;
    if (Array.isArray(ids)) {
      for (const id of ids) {
        const n = typeof id === 'number' ? id : Number(id);
        if (!Number.isNaN(n)) set.add(n);
      }
    }
    if (t.customer_id != null) {
      const n =
        typeof t.customer_id === 'number'
          ? t.customer_id
          : Number(t.customer_id);
      if (!Number.isNaN(n)) set.add(n);
    }
  }
  return set;
}

function ScheduleCard({
  payload,
  context,
}: {
  payload: Dict;
  context: ProductCopilotResponse;
}) {
  const schedule = Array.isArray(payload.customer_schedule)
    ? (payload.customer_schedule as Dict[])
    : null;
  const ends = Array.isArray(payload.route_end_times)
    ? (payload.route_end_times as Dict[])
    : null;
  const lateIds = Array.isArray(payload.late_customer_ids)
    ? (payload.late_customer_ids as unknown[])
    : [];
  const nLate = payload.n_late_customers;
  if (!schedule && !ends && lateIds.length === 0 && nLate == null) return null;

  const highlighted = highlightedCustomerIdsFromContext(context);

  return (
    <section className="panel">
      <h2>Schedule</h2>
      <div className="kv-row">
        <span className="k">n_late_customers</span>
        <span className="v">{num(nLate)}</span>
      </div>
      {lateIds.length > 0 && (
        <div className="kv-row">
          <span className="k">late_customer_ids</span>
          <span className="v">{lateIds.map(String).join(', ')}</span>
        </div>
      )}
      {ends && ends.length > 0 && (
        <>
          <h3>Route end times ({ends.length})</h3>
          <table className="simple-table">
            <thead>
              <tr>
                <th>display</th>
                <th>route_idx</th>
                <th>end_time</th>
                <th>time_warp</th>
              </tr>
            </thead>
            <tbody>
              {ends.map((e, i) => (
                <tr key={i}>
                  <td className="num">{num(e.display_route_number)}</td>
                  <td className="num">{num(e.route_idx)}</td>
                  <td className="num">{num(e.end_time)}</td>
                  <td>{bool(e.has_time_warp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {schedule && schedule.length > 0 && (
        <>
          <h3>
            Customer schedule ({schedule.length}
            {highlighted.size > 0 ? `, highlighted: ${[...highlighted].join(', ')}` : ''}
            )
          </h3>
          <p className="panel-note">
            {highlighted.size > 0
              ? 'Rows for highlighted customers are emphasized; full schedule below.'
              : 'Showing first 12 rows.'}
          </p>
          <table className="simple-table">
            <thead>
              <tr>
                <th>cust.</th>
                <th>route (display)</th>
                <th>arrival</th>
                <th>start_svc</th>
                <th>end_svc</th>
                <th>tw_early</th>
                <th>tw_late</th>
                <th>late?</th>
              </tr>
            </thead>
            <tbody>
              {schedule
                .filter((row) => {
                  if (highlighted.size === 0) return true;
                  const cid = Number(row.customer_id);
                  return highlighted.has(cid);
                })
                .map((row, i) => (
                  <tr
                    key={i}
                    style={
                      highlighted.has(Number(row.customer_id))
                        ? { background: 'var(--accent-soft)' }
                        : undefined
                    }
                  >
                    <td className="num">{num(row.customer_id)}</td>
                    <td className="num">{num(row.display_route_number)}</td>
                    <td className="num">{num(row.arrival)}</td>
                    <td className="num">{num(row.start_service)}</td>
                    <td className="num">{num(row.end_service)}</td>
                    <td className="num">{num(row.tw_early)}</td>
                    <td className="num">{num(row.tw_late)}</td>
                    <td>{bool(row.is_late)}</td>
                  </tr>
                ))
                .slice(0, highlighted.size > 0 ? 50 : 12)}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

export function DomainCards({ context }: Props) {
  if (!context || !isDict(context.payload_augmented)) return null;
  const payload = context.payload_augmented as Dict;
  return (
    <>
      <ObjectiveCard payload={payload} />
      <FeasibilityCard payload={payload} />
      <RouteTableCard payload={payload} />
      <ScheduleCard payload={payload} context={context} />
    </>
  );
}
