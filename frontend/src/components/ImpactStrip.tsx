// Impact strip — context-aware perturbation-effect metrics across the top of the main area.
// Shape-aware: SCHEDULE shows lateness/slack/histogram; STRUCT shows route/customer counts;
// OBJ shows objective + diff deltas or "open Diff tab" hint.
import type { DiffResponse, ScenarioResponse } from '../api/types';

interface ImpactStripProps {
  scenario: ScenarioResponse | null;
  diffData: DiffResponse | null;
}

interface LateMetrics {
  lates: { lateness_minutes: number; route_idx: number }[];
  maxLate: number;
  lateRoutes: number;
  totalRoutes: number;
  avgSlack: number;
  hist: number[];
}

const HIST_BUCKETS = [0, 5, 10, 20, 40, 80, Infinity];
const HIST_LABELS = ['<5', '5-10', '10-20', '20-40', '40-80', '80+'];

function computeScheduleMetrics(scenario: ScenarioResponse): LateMetrics {
  const sched = scenario.solution?.customer_schedule ?? [];
  const lates = sched.filter((r) => r.is_late);
  const maxLate = lates.reduce(
    (m, r) => Math.max(m, r.lateness_minutes),
    0,
  );
  const lateRoutes = new Set(lates.map((r) => r.route_idx));
  const totalRoutes = new Set(sched.map((r) => r.route_idx)).size;
  const slacks = sched
    .filter(
      (r) => !r.is_late && r.arrival != null && r.time_window_end != null,
    )
    .map((r) => (r.time_window_end as number) - (r.arrival as number));
  const avgSlack = slacks.length
    ? slacks.reduce((a, b) => a + b, 0) / slacks.length
    : 0;
  const hist = new Array(HIST_BUCKETS.length - 1).fill(0) as number[];
  for (const r of lates) {
    for (let i = 0; i < HIST_BUCKETS.length - 1; i++) {
      if (
        r.lateness_minutes >= HIST_BUCKETS[i] &&
        r.lateness_minutes < HIST_BUCKETS[i + 1]
      ) {
        hist[i]++;
        break;
      }
    }
  }
  return {
    lates: lates.map((r) => ({
      lateness_minutes: r.lateness_minutes,
      route_idx: r.route_idx,
    })),
    maxLate,
    lateRoutes: lateRoutes.size,
    totalRoutes,
    avgSlack,
    hist,
  };
}

function LatenessHistogram({ hist }: { hist: number[] }) {
  const max = Math.max(1, ...hist);
  return (
    <div className="lh-wrap">
      {hist.map((v, i) => (
        <div className="lh-col" key={i} title={`${HIST_LABELS[i]} sm: ${v}`}>
          <div
            className="lh-bar"
            style={{ height: `${(v / max) * 100}%`, opacity: v > 0 ? 1 : 0.18 }}
          />
          <div className="lh-label">{HIST_LABELS[i]}</div>
        </div>
      ))}
    </div>
  );
}

export function ImpactStrip({ scenario, diffData }: ImpactStripProps) {
  if (!scenario) return null;
  const af = scenario.available_fields;
  const shape: 'SCHEDULE' | 'STRUCT' | 'OBJ' = af.customer_schedule
    ? 'SCHEDULE'
    : af.routes
      ? 'STRUCT'
      : 'OBJ';

  return (
    <div className="impact-strip">
      <div className="is-pert">
        <div className="is-label">perturbation</div>
        <div className="is-pert-summary">{scenario.perturbation_summary}</div>
      </div>

      {shape === 'SCHEDULE' && scenario.solution && <ScheduleMetrics scenario={scenario} />}
      {shape === 'STRUCT' && scenario.solution && <StructMetrics scenario={scenario} />}
      {shape === 'OBJ' && scenario.solution && <ObjMetrics scenario={scenario} diffData={diffData} />}
    </div>
  );
}

function ScheduleMetrics({ scenario }: { scenario: ScenarioResponse }) {
  const m = computeScheduleMetrics(scenario);
  const total = scenario.solution?.customer_schedule?.length ?? 0;
  return (
    <>
      <div className="is-metric">
        <div className="is-label">late_customers</div>
        <div className={'is-value ' + (m.lates.length > 0 ? 'bad' : 'ok')}>
          {m.lates.length}
          <span className="is-of"> / {total}</span>
        </div>
      </div>
      <div className="is-metric">
        <div className="is-label">max lateness</div>
        <div className={'is-value ' + (m.maxLate > 0 ? 'bad' : '')}>
          {m.maxLate > 0 ? '+' + m.maxLate.toFixed(1) : '—'}
          {m.maxLate > 0 && <span className="is-of"> sm</span>}
        </div>
      </div>
      <div className="is-metric">
        <div className="is-label">affected_routes</div>
        <div className={'is-value ' + (m.lateRoutes > 0 ? 'bad' : '')}>
          {m.lateRoutes}
          <span className="is-of"> / {m.totalRoutes}</span>
        </div>
      </div>
      <div className="is-metric">
        <div className="is-label">avg_slack</div>
        <div className="is-value">
          {m.avgSlack.toFixed(1)}
          <span className="is-of"> sm</span>
        </div>
      </div>
      <div className="is-metric histo">
        <div className="is-label">lateness · buckets</div>
        <LatenessHistogram hist={m.hist} />
      </div>
    </>
  );
}

function StructMetrics({ scenario }: { scenario: ScenarioResponse }) {
  const nRoutes =
    scenario.solution?.n_routes ?? scenario.solution?.routes?.length ?? 0;
  const nCustomers = scenario.instance?.customers.length ?? 0;
  return (
    <>
      <div className="is-metric">
        <div className="is-label">routes</div>
        <div className="is-value">{nRoutes}</div>
      </div>
      <div className="is-metric">
        <div className="is-label">customers</div>
        <div className="is-value">{nCustomers}</div>
      </div>
      <div className="is-metric wide">
        <div className="is-label">schedule</div>
        <div className="is-value dim" style={{ fontSize: 13 }}>
          not in payload — lateness/slack metrics unavailable
        </div>
      </div>
    </>
  );
}

function ObjMetrics({
  scenario,
  diffData,
}: {
  scenario: ScenarioResponse;
  diffData: DiffResponse | null;
}) {
  const obj = scenario.solution?.objective;
  return (
    <>
      <div className="is-metric">
        <div className="is-label">objective</div>
        <div className="is-value">{obj != null ? obj.toFixed(1) : '—'}</div>
      </div>
      {diffData ? (
        <>
          <div className="is-metric">
            <div className="is-label">Δ_absolute</div>
            <div
              className={
                'is-value ' +
                ((diffData.objective_delta_absolute ?? 0) > 0 ? 'bad' : 'good')
              }
            >
              {(diffData.objective_delta_absolute ?? 0) > 0 ? '+' : ''}
              {(diffData.objective_delta_absolute ?? 0).toFixed(1)}
            </div>
          </div>
          <div className="is-metric">
            <div className="is-label">Δ_percent</div>
            <div
              className={
                'is-value ' +
                ((diffData.objective_delta_percent ?? 0) > 0 ? 'bad' : 'good')
              }
            >
              {(diffData.objective_delta_percent ?? 0) > 0 ? '+' : ''}
              {(diffData.objective_delta_percent ?? 0).toFixed(1)}%
            </div>
          </div>
          <div className="is-metric">
            <div className="is-label">feasibility</div>
            <div
              className={'is-value ' + (diffData.feasibility_changed ? 'bad' : '')}
            >
              {diffData.feasibility_changed ? 'FLIPPED' : 'unchanged'}
            </div>
          </div>
        </>
      ) : (
        <div className="is-metric wide">
          <div className="is-label">diff</div>
          <div className="is-value dim" style={{ fontSize: 13 }}>
            Open Diff tab to fetch <code>POST /diff</code>
          </div>
        </div>
      )}
    </>
  );
}
