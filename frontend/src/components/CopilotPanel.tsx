// Copilot: conversational front-end over the contract's CopilotAskResponse.
//
// The contract returns structured fields (intent, evidence, compute_decision,
// useful_refusal). This panel renders those as a natural-sounding chat reply —
// no raw chips, no field paths surfaced. Route and customer mentions inside
// the prose are inline clickable; clicking one drives the shared selection
// state across Map, Schedule, and Tables.
import { useEffect, useRef, useState } from 'react';
import React from 'react';
import { ApiError, fetchCopilotAsk } from '../api/client';
import type {
  ComputeDecisionBlock,
  CopilotAskResponse,
  DisplayAnchor,
  EvidenceItem,
  ScenarioResponse,
} from '../api/types';
import type { Highlights, Selection } from '../selection';
import type { LensMode } from '../lens';
import { AvailableFieldsStrip } from './AvailableFieldsStrip';
import { CollapseToggle } from './CollapseToggle';
import type { TablesTab } from './TablesPanel';

// Panel focus targets, mirrored from the highlight contract's focus_panel
// VisualAction. App.tsx maps these onto its Collapsed/tablesTab state.
export type FocusTarget = 'map' | 'schedule' | 'tables' | 'impact';

interface Props {
  scenarioId: string | null;
  scenario: ScenarioResponse | null;
  selection: Selection;
  setSelection: (s: Selection) => void;
  setHighlights: (h: Highlights) => void;
  setLens: (m: LensMode) => void;
  setCollapsed: (key: 'map' | 'schedule' | 'tables', value: boolean) => void;
  setTablesTab?: (t: TablesTab) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

// ---------------------------------------------------------------------------
// Conversational lead-ins (picked at random per intent for variety)
// ---------------------------------------------------------------------------

const LEAD_INS: Record<string, string[]> = {
  route_end_time: ['', 'Sure — ', 'Looking it up… ', ''],
  customer_arrival: ['', 'Yep — ', 'Got it — '],
  single_customer_route_membership: ['', 'Yes — ', ''],
  objective_value: ['', 'The current ', ''],
  objective_delta: ['', 'It ', ''],
  route_count: ['', 'There are ', ''],
  lateness_summary: ['', '', 'Looking at the schedule, '],
  full_route_listing: ['Here are the routes for this plan. ', ''],
  before_after_comparison: ['', ''],
};

function lead(intent: string): string {
  const opts = LEAD_INS[intent] ?? [''];
  return opts[Math.floor(Math.random() * opts.length)];
}

// ---------------------------------------------------------------------------
// Inline clickable mentions
// ---------------------------------------------------------------------------

interface SelectFns {
  setSelection: (s: Selection) => void;
  setTablesTab?: (t: TablesTab) => void;
}

interface VisualActionFns extends SelectFns {
  setHighlights: (h: Highlights) => void;
  setLens: (m: LensMode) => void;
  setCollapsed: (key: 'map' | 'schedule' | 'tables', value: boolean) => void;
}

function RouteRef({
  label,
  idx,
  sel,
}: {
  label: string;
  idx?: number;
  sel: SelectFns;
}) {
  return (
    <span
      className="ref-chip route-ref"
      onClick={() => {
        if (typeof idx === 'number') {
          sel.setSelection({ kind: 'route', idx, label });
        }
        sel.setTablesTab?.('routes');
      }}
      title="Highlight this route on the map and schedule"
    >
      {label}
    </span>
  );
}

function CustomerRef({
  id,
  sel,
}: {
  id: number;
  sel: SelectFns;
}) {
  return (
    <span
      className="ref-chip cust-ref"
      onClick={() => {
        sel.setSelection({ kind: 'customer', id });
        sel.setTablesTab?.('customers');
      }}
      title="Highlight this customer"
    >
      C{id}
    </span>
  );
}

function fmtTime(v: unknown): string {
  if (typeof v === 'number') return v.toFixed(1);
  return String(v);
}

// ---------------------------------------------------------------------------
// Aspectual fallback composer: renders the intent=unknown + evidence path
// produced by the backend's within-family aspectual dispatcher.
// ---------------------------------------------------------------------------

const FIELD_LABELS: Record<string, string> = {
  arrival: 'arrives at',
  start_service: 'service starts',
  end_service: 'service ends',
  tw_early: 'window opens',
  tw_late: 'window closes',
  is_late: 'late?',
  lateness_minutes: 'minutes late',
  end_time: 'finishes at',
  has_time_warp: 'time-warp flagged',
  n_late_customers: 'total late customers',
  late_customer_ids: 'late customer ids',
};

function humanizeFieldPath(path: string): { label: string; cid?: number; routeIdx?: number } {
  // customer_schedule[customer_id=N].FIELD
  // route_end_times[route_idx=N].FIELD
  // n_late_customers / late_customer_ids
  const cidMatch = /customer_id=(\d+)\]\.(\w+)/.exec(path);
  if (cidMatch) {
    return {
      label: FIELD_LABELS[cidMatch[2]] ?? cidMatch[2],
      cid: Number(cidMatch[1]),
    };
  }
  const ridxMatch = /route_idx=(\d+)\]\.(\w+)/.exec(path);
  if (ridxMatch) {
    return {
      label: FIELD_LABELS[ridxMatch[2]] ?? ridxMatch[2],
      routeIdx: Number(ridxMatch[1]),
    };
  }
  return { label: FIELD_LABELS[path] ?? path };
}

function fmtEvidenceValue(v: unknown, field: string): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') {
    if (field === 'lateness_minutes') return v.toFixed(1) + ' sm';
    if (field === 'arrival' || field === 'start_service' || field === 'end_service'
        || field === 'tw_early' || field === 'tw_late' || field === 'end_time') {
      return v.toFixed(1) + ' sm';
    }
    return Number.isInteger(v) ? String(v) : v.toFixed(1);
  }
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (Array.isArray(v)) return v.length === 0 ? 'none' : v.join(', ');
  return String(v);
}

function composeAspectualProse(
  resp: CopilotAskResponse,
  asp: NonNullable<CopilotAskResponse['aspectual_dispatch']>,
  sel: SelectFns,
): React.ReactNode {
  // Describe the entity scope succinctly. When both customer_ids and
  // route_labels are present, the route is the user-facing scope — the
  // customer_ids are usually the route's members surfaced via the
  // per-customer arrival evidence, not the question's subject.
  const cids = asp.entities_resolved.customer_ids ?? [];
  const routeLabels = asp.entities_resolved.route_labels ?? [];
  let scopeNode: React.ReactNode = 'this scenario';
  if (routeLabels.length === 1) {
    const m = /(\d+)/.exec(routeLabels[0]);
    const idx = m ? Number(m[1]) - 1 : undefined;
    scopeNode = <RouteRef label={routeLabels[0]} idx={idx} sel={sel} />;
  } else if (routeLabels.length > 1) {
    scopeNode = <>{routeLabels.length} routes</>;
  } else if (cids.length === 1) {
    scopeNode = <CustomerRef id={cids[0]} sel={sel} />;
  } else if (cids.length > 1) {
    scopeNode = <>{cids.length} customers</>;
  }

  const aspectWord = asp.aspect === 'lateness' ? 'lateness' : 'timing';
  const header = (
    <>
      I'm not 100% sure I caught the question, but here's what I see for{' '}
      {scopeNode} on {aspectWord}:
    </>
  );

  const lines = resp.evidence.map((ev, i) => {
    const path = (ev as { field_path: string }).field_path;
    const value = (ev as { value: unknown }).value;
    const parsed = humanizeFieldPath(path);
    const fieldName = path.split('.').pop() || path;
    const valText = fmtEvidenceValue(value, fieldName);
    return (
      <div key={i} className="aspect-line">
        <span className="aspect-key">{parsed.label}</span>
        <span className="aspect-val">{valText}</span>
      </div>
    );
  });

  return (
    <>
      <div className="aspect-header">{header}</div>
      <div className="aspect-list">{lines}</div>
      <div className="aspect-footer">
        Was that what you were asking? If not, try rephrasing.
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Prose composer (returns null if no answerable evidence — caller falls
// through to refusal text)
// ---------------------------------------------------------------------------

function composeProse(
  resp: CopilotAskResponse,
  sel: SelectFns,
): React.ReactNode | null {
  if (resp.answerability.status === 'not_answerable') return null;
  const ev = resp.evidence;
  const findEv = (
    p: string | ((e: EvidenceItem) => boolean),
  ): EvidenceItem | undefined =>
    typeof p === 'string'
      ? ev.find((e) => e.field_path === p || e.field_path.startsWith(p))
      : ev.find(p);

  switch (resp.intent) {
    case 'route_end_time': {
      const e = ev[0];
      if (!e) return null;
      const a = e.display_anchor as DisplayAnchor & {
        route_label?: string;
        route_idx?: number;
      };
      return (
        <>
          {lead(resp.intent)}
          <RouteRef label={a.route_label ?? 'Route'} idx={a.route_idx} sel={sel} />{' '}
          finishes at <strong>{fmtTime(e.value)} sm</strong>.
        </>
      );
    }
    case 'customer_arrival': {
      const arr = ev[0];
      if (!arr) return null;
      const late = findEv((e) => e.field_path.includes('lateness'));
      const a = arr.display_anchor as DisplayAnchor & {
        customer_id?: number;
        route_label?: string;
        route_idx?: number;
      };
      const cid = a.customer_id;
      return (
        <>
          {lead(resp.intent)}
          {cid != null && <CustomerRef id={cid} sel={sel} />} arrives at{' '}
          <strong>{fmtTime(arr.value)} sm</strong>
          {a.route_label && (
            <>
              {' '}
              on{' '}
              <RouteRef label={a.route_label} idx={a.route_idx} sel={sel} />
            </>
          )}
          {late && (
            <>
              ,{' '}
              <span style={{ color: 'var(--late)' }}>
                +{fmtTime(late.value)} sm late
              </span>
            </>
          )}
          .
        </>
      );
    }
    case 'single_customer_route_membership': {
      const e = ev[0];
      if (!e) return null;
      const m = e.field_path.match(/customer_id=(\d+)/);
      let cid: number | null = null;
      if (m) cid = Number(m[1]);
      else if (typeof e.value === 'number') cid = e.value;
      const a = e.display_anchor as DisplayAnchor & {
        route_label?: string;
        route_idx?: number;
      };
      return (
        <>
          {lead(resp.intent)}
          {cid != null && <CustomerRef id={cid} sel={sel} />} is on{' '}
          {a.route_label ? (
            <RouteRef label={a.route_label} idx={a.route_idx} sel={sel} />
          ) : (
            'a route'
          )}
          .
        </>
      );
    }
    case 'objective_value': {
      const v = findEv('action_objective');
      const u = findEv('units.objective');
      if (!v) return null;
      return (
        <>
          {lead(resp.intent)}objective is <strong>{fmtTime(v.value)}</strong>
          {u && (
            <span style={{ color: 'var(--text-faint)' }}>
              {' '}
              {String(u.value)}
            </span>
          )}
          .
        </>
      );
    }
    case 'objective_delta': {
      const abs = findEv((e) => e.field_path.includes('delta_absolute'));
      const pct = findEv((e) => e.field_path.includes('delta_percent'));
      if (!abs) return null;
      const av = typeof abs.value === 'number' ? abs.value : 0;
      const pv = typeof pct?.value === 'number' ? pct.value : null;
      const direction = av >= 0 ? 'went up' : 'went down';
      return (
        <>
          {lead(resp.intent)}objective {direction} by{' '}
          <strong>
            {av >= 0 ? '+' : ''}
            {fmtTime(av)}
          </strong>
          {pv != null && (
            <span style={{ color: 'var(--text-faint)' }}>
              {' '}
              ({pv >= 0 ? '+' : ''}
              {fmtTime(pv)}%)
            </span>
          )}
          .
        </>
      );
    }
    case 'route_count': {
      const e = ev[0];
      if (!e) return null;
      return (
        <>
          {lead(resp.intent)}
          <strong>{String(e.value)}</strong> routes in this plan.
        </>
      );
    }
    case 'lateness_summary': {
      const n = findEv('n_late_customers');
      const sample = ev
        .filter((e) => e.field_path.includes('lateness_minutes'))
        .slice(0, 3);
      if (!n) return null;
      const count = Number(n.value) || 0;
      if (count === 0) {
        return (
          <>
            {lead(resp.intent)}
            no customers are late in this plan — everyone arrives within their
            time window.
          </>
        );
      }
      return (
        <>
          {lead(resp.intent)}
          <strong>{String(n.value)}</strong>{' '}
          {count === 1 ? 'customer is' : 'customers are'} late
          {sample.length > 0 && (
            <>
              . The worst{sample.length > 1 ? ' offenders are' : ' is'}{' '}
              {sample.map((e, i) => {
                const a = e.display_anchor as DisplayAnchor & {
                  customer_id?: number;
                };
                return (
                  <React.Fragment key={i}>
                    {i > 0 && (i === sample.length - 1 ? ' and ' : ', ')}
                    {a.customer_id != null ? (
                      <CustomerRef id={a.customer_id} sel={sel} />
                    ) : (
                      'C?'
                    )}{' '}
                    <span style={{ color: 'var(--late)' }}>
                      (+{fmtTime(e.value)} sm)
                    </span>
                  </React.Fragment>
                );
              })}
            </>
          )}
          .
        </>
      );
    }
    case 'full_route_listing': {
      const routeEvs = ev.slice(0, 6);
      return (
        <>
          {lead(resp.intent)}This plan has <strong>{ev.length}</strong> routes
          {routeEvs.length > 0 && (
            <>
              :{' '}
              {routeEvs.map((e, i) => {
                const a = e.display_anchor as DisplayAnchor & {
                  route_label?: string;
                  route_idx?: number;
                };
                return (
                  <React.Fragment key={i}>
                    {i > 0 && (i === routeEvs.length - 1 ? ' and ' : ', ')}
                    {a.route_label ? (
                      <RouteRef
                        label={a.route_label}
                        idx={a.route_idx}
                        sel={sel}
                      />
                    ) : (
                      'a route'
                    )}
                  </React.Fragment>
                );
              })}
              {ev.length > routeEvs.length && (
                <span style={{ color: 'var(--text-faint)' }}>
                  {' '}
                  (+{ev.length - routeEvs.length} more)
                </span>
              )}
            </>
          )}
          . Click any route to highlight it on the map.
        </>
      );
    }
    case 'before_after_comparison': {
      const cc = findEv((e) => e.field_path.includes('customer_changes'));
      const rc = findEv((e) => e.field_path.includes('route_changes'));
      const cv = Number(cc?.value ?? 0);
      const rv = Number(rc?.value ?? 0);
      if (cv === 0 && rv === 0) {
        return (
          <>
            {lead(resp.intent)}nothing significant changed between the baseline
            and the perturbed plan.
          </>
        );
      }
      return (
        <>
          {lead(resp.intent)}
          <strong>{cv}</strong> customer{cv === 1 ? '' : 's'} and{' '}
          <strong>{rv}</strong> route{rv === 1 ? '' : 's'} changed. The Diff tab
          has the details.
        </>
      );
    }
    case 'scenario_summary':
    case 'solution_summary':
    case 'perturbation_summary':
    case 'perturbation_impact_summary':
    case 'route_impact_summary':
    case 'evaluation_verdict':
    case 'what_to_watch': {
      const text = resp.answer_text;
      if (text) return <>{lead(resp.intent)}{text}</>;
      return null;
    }
    default:
      if (resp.answer_text) return <>{resp.answer_text}</>;
      return null;
  }
}

// ---------------------------------------------------------------------------
// Friendlier refusal prose (varied by intent + scenario shape signal)
// ---------------------------------------------------------------------------

function refusalProse(resp: CopilotAskResponse): React.ReactNode {
  const missing = resp.answerability.missing_fields;
  const missingHas = (s: string) => missing.some((m) => m.includes(s));

  switch (resp.intent) {
    case 'objective_delta':
    case 'before_after_comparison':
      return (
        <>
          I don't have a baseline to compare against for this scenario, so I
          can't say what changed. Try a scenario that ships with both the
          baseline and the perturbed plan.
        </>
      );
    case 'route_end_time':
      if (missingHas('customer_schedule') || missingHas('route_end_times')) {
        return (
          <>
            This scenario doesn't carry schedule timing — try one that does
            (the impact strip will show "late_customers / N" when it's
            available).
          </>
        );
      }
      return <>I can't find route end-times in this payload.</>;
    case 'customer_arrival':
      return (
        <>
          No arrival times in this scenario. Pick a schedule-shape scenario
          (the ones with a populated Gantt) and ask again.
        </>
      );
    case 'single_customer_route_membership':
      return (
        <>
          This scenario doesn't expose per-customer route membership. STRUCT-
          and SCHEDULE-shape payloads do.
        </>
      );
    case 'feasibility_status':
      return <>Feasibility isn't asserted in this payload.</>;
    case 'new_customer_assignment':
      return (
        <>
          The perturbation doesn't name a new customer to attribute, so I can't
          tell you where it landed.
        </>
      );
    case 'unknown':
      return (
        <>
          I didn't quite catch that one. Try a phrasing like the suggestions
          below — I'm good at route end-times, arrivals, lateness, and
          objective values.
        </>
      );
    default:
      return <>That one needs fields the current payload doesn't carry.</>;
  }
}

// ---------------------------------------------------------------------------
// Compact compute-decision footnote (replaces the big banner)
// ---------------------------------------------------------------------------

const COMPUTE_FOOTNOTE: Record<string, string> = {
  needs_recompute: 'A recompute would resolve this.',
  partial_from_payload: 'I can describe what I see, but the cause is out of reach.',
  needs_comparison_payload: 'A baseline payload would unlock the answer.',
  clarification_needed: 'A more specific question would help.',
  unsupported: 'This question is outside the contract scope.',
};

function ComputeNote({ cd }: { cd: ComputeDecisionBlock }) {
  if (cd.mode === 'answer_from_payload') return null;
  const note = COMPUTE_FOOTNOTE[cd.mode] ?? null;
  if (!note) return null;
  return (
    <div className="compute-note">
      <span className="cn-dot" /> {note}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Typing dots while pending
// ---------------------------------------------------------------------------

function TypingDots() {
  return (
    <div className="msg bot">
      <div className="role">Copilot</div>
      <div className="bubble typing">
        <span className="dot" />
        <span className="dot" />
        <span className="dot" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Local answer computation — fallback when the LLM-D1 adapter returns
// intent='unknown' for clear questions whose answer is sitting in the loaded
// scenario data. Keeps the bot from feeling helpless on common phrasings.
// ---------------------------------------------------------------------------

function pickLead(opts: string[]): string {
  return opts[Math.floor(Math.random() * opts.length)];
}

function localAnswer(
  prompt: string,
  scenario: ScenarioResponse | null,
  sel: SelectFns,
): { node: React.ReactNode; select?: Selection } | null {
  if (!scenario) return null;
  const p = prompt.toLowerCase().trim();
  const sol = scenario.solution;

  // Route count
  if (
    /\bhow many routes?\b|\broute count\b|\bnumber of routes?\b|\bhow many vehicles?\b|\bvehicle count\b/.test(p)
  ) {
    const n =
      sol?.n_routes ??
      sol?.routes?.length ??
      (sol?.customer_schedule
        ? new Set(sol.customer_schedule.map((r) => r.route_idx)).size
        : null);
    if (n != null) {
      return {
        node: (
          <>
            {pickLead(['', 'There are ', 'This plan uses '])}
            <strong>{n}</strong> routes in this plan.
          </>
        ),
      };
    }
  }

  // Objective value
  if (
    /\bwhat(?:'s| is)\s+(?:the\s+)?objective\b|\bobjective\s+value\b|\btotal\s+(?:cost|distance|objective)\b/.test(p)
  ) {
    const obj = sol?.objective;
    if (obj != null) {
      return {
        node: (
          <>
            {pickLead(['The current ', 'Current ', ''])}
            objective is <strong>{obj.toFixed(1)}</strong>.
          </>
        ),
      };
    }
    // Objective isn't in the payload — give a useful answer anyway.
    const routesN =
      sol?.routes?.length ??
      (sol?.customer_schedule
        ? new Set(sol.customer_schedule.map((r) => r.route_idx)).size
        : null);
    const late = sol?.customer_schedule?.filter((r) => r.is_late).length ?? 0;
    return {
      node: (
        <>
          This scenario doesn't carry a single objective value, but I can tell
          you{routesN != null && (
            <>
              {' '}
              it uses <strong>{routesN}</strong> routes
            </>
          )}
          {late > 0 ? (
            <>
              {' '}
              with <strong>{late}</strong> late customers.
            </>
          ) : (
            <> with all customers arriving on time.</>
          )}{' '}
          The Impact strip shows the headline metrics.
        </>
      ),
    };
  }

  // Single-customer route membership
  const cm = p.match(/(?:which|what)\s+route\s+(?:is\s+)?c(?:ustomer)?\s*(\d+)\s+on/) ||
    p.match(/c(?:ustomer)?\s*(\d+).*\bon\s+which\s+route/);
  if (cm) {
    const cid = Number(cm[1]);
    if (sol?.customer_schedule) {
      const row = sol.customer_schedule.find((r) => r.customer_id === cid);
      if (row) {
        return {
          node: (
            <>
              {pickLead(['', 'Yes — '])}
              <CustomerRef id={cid} sel={sel} /> is on{' '}
              <RouteRef label={row.route_label} idx={row.route_idx} sel={sel} />.
            </>
          ),
          select: { kind: 'customer', id: cid },
        };
      }
    }
    if (sol?.routes) {
      for (const r of sol.routes) {
        if (r.customer_ids.includes(cid)) {
          return {
            node: (
              <>
                <CustomerRef id={cid} sel={sel} /> is on{' '}
                <RouteRef label={r.route_label} idx={r.route_idx} sel={sel} />.
              </>
            ),
            select: { kind: 'customer', id: cid },
          };
        }
      }
    }
    return {
      node: (
        <>
          I don't see <CustomerRef id={cid} sel={sel} /> in this plan's routes
          — double-check the customer id?
        </>
      ),
    };
  }

  // Lateness summary
  if (/\bwhich customers? are late\b|\bwho('s| is) late\b|\bany late\b|\blate customers?\b/.test(p)) {
    if (sol?.customer_schedule) {
      const late = sol.customer_schedule.filter((r) => r.is_late);
      if (late.length === 0) {
        return {
          node: (
            <>
              No customers are late in this plan — everyone arrives within
              their time window.
            </>
          ),
        };
      }
      const worst = [...late]
        .sort((a, b) => b.lateness_minutes - a.lateness_minutes)
        .slice(0, 3);
      return {
        node: (
          <>
            <strong>{late.length}</strong>{' '}
            {late.length === 1 ? 'customer is' : 'customers are'} late. The
            worst {worst.length > 1 ? 'offenders are' : 'is'}{' '}
            {worst.map((r, i) => (
              <React.Fragment key={i}>
                {i > 0 && (i === worst.length - 1 ? ' and ' : ', ')}
                <CustomerRef id={r.customer_id} sel={sel} />{' '}
                <span style={{ color: 'var(--late)' }}>
                  (+{r.lateness_minutes.toFixed(1)} sm)
                </span>
              </React.Fragment>
            ))}
            .
          </>
        ),
      };
    }
  }

  // Route end time
  const re = p.match(
    /(?:what time|when)\s+(?:does\s+)?route\s+(\d+)\s+(?:finish|end|complete)/,
  );
  if (re) {
    const oneBased = Number(re[1]);
    const idx0 = oneBased - 1;
    if (sol?.customer_schedule) {
      const rows = sol.customer_schedule.filter((r) => r.route_idx === idx0);
      if (rows.length > 0) {
        let maxEnd = -Infinity;
        let label = `Route ${oneBased}`;
        for (const r of rows) {
          if (r.service_end != null && r.service_end > maxEnd)
            maxEnd = r.service_end;
          label = r.route_label;
        }
        if (Number.isFinite(maxEnd)) {
          return {
            node: (
              <>
                <RouteRef label={label} idx={idx0} sel={sel} /> finishes at{' '}
                <strong>{maxEnd.toFixed(1)} sm</strong>.
              </>
            ),
            select: { kind: 'route', idx: idx0, label },
          };
        }
      }
    }
    if (sol?.routes) {
      const r = sol.routes.find((rr) => rr.route_idx === idx0);
      if (r && r.end_time != null) {
        return {
          node: (
            <>
              <RouteRef label={r.route_label} idx={idx0} sel={sel} /> finishes
              at <strong>{r.end_time.toFixed(1)} sm</strong>.
            </>
          ),
          select: { kind: 'route', idx: idx0, label: r.route_label },
        };
      }
    }
  }

  // Customer arrival
  const ca = p.match(/when\s+does\s+c(?:ustomer)?\s*(\d+)\s+arrive/);
  if (ca) {
    const cid = Number(ca[1]);
    if (sol?.customer_schedule) {
      const row = sol.customer_schedule.find((r) => r.customer_id === cid);
      if (row && row.arrival != null) {
        return {
          node: (
            <>
              <CustomerRef id={cid} sel={sel} /> arrives at{' '}
              <strong>{row.arrival.toFixed(1)} sm</strong>
              {row.route_label && (
                <>
                  {' '}
                  on{' '}
                  <RouteRef
                    label={row.route_label}
                    idx={row.route_idx}
                    sel={sel}
                  />
                </>
              )}
              {row.is_late && (
                <>
                  ,{' '}
                  <span style={{ color: 'var(--late)' }}>
                    +{row.lateness_minutes.toFixed(1)} sm late
                  </span>
                </>
              )}
              .
            </>
          ),
          select: { kind: 'customer', id: cid },
        };
      }
    }
  }

  return null;
}

// ---------------------------------------------------------------------------
// Message model
// ---------------------------------------------------------------------------

type Message =
  | { role: 'user'; text: string }
  | { role: 'bot-info'; text: React.ReactNode }
  | { role: 'bot-response'; resp: CopilotAskResponse }
  | { role: 'bot-local'; node: React.ReactNode }
  | { role: 'bot-error'; code: string; message: string };

interface MsgProps {
  m: Message;
  sel: SelectFns;
  scenario: ScenarioResponse | null;
}

function CopilotMessage({ m, sel, scenario }: MsgProps) {
  if (m.role === 'user') {
    return (
      <div className="msg user">
        <div className="role">You</div>
        <div className="bubble">{m.text}</div>
      </div>
    );
  }
  if (m.role === 'bot-info') {
    return (
      <div className="msg bot">
        <div className="role">Copilot</div>
        <div className="bubble info">
          <div className="answer">{m.text}</div>
        </div>
      </div>
    );
  }
  if (m.role === 'bot-error') {
    return (
      <div className="msg bot">
        <div className="role">Copilot</div>
        <div className="bubble" style={{ borderLeftColor: 'var(--late)' }}>
          <div className="answer" style={{ color: 'var(--late)' }}>
            Something went wrong — {m.message}.
          </div>
        </div>
      </div>
    );
  }
  if (m.role === 'bot-local') {
    return (
      <div className="msg bot">
        <div className="role">Copilot</div>
        <div className="bubble">
          <div className="answer">{m.node}</div>
        </div>
      </div>
    );
  }

  const resp = m.resp;
  const aspectual = resp.aspectual_dispatch?.triggered ? resp.aspectual_dispatch : null;
  const composed = aspectual
    ? composeAspectualProse(resp, aspectual, sel)
    : composeProse(resp, sel);
  const showProse = composed != null;

  // On refusal/unknown the contract emits no visual_actions and the prose
  // composer falls through to refusalProse. Show the AvailableFieldsStrip
  // beneath the refusal text so the operator immediately sees which payload
  // blocks ARE populated — the honest-refusal UX.
  const isRefusal =
    !showProse ||
    resp.intent === 'unknown' ||
    resp.intent === 'refusal_or_insufficient_payload';

  return (
    <div className="msg bot">
      <div className="role">Copilot</div>
      <div className="bubble">
        <div className="answer">
          {showProse ? composed : refusalProse(resp)}
        </div>
        {isRefusal && scenario && (
          <div style={{ marginTop: 8 }}>
            <AvailableFieldsStrip scenario={scenario} />
          </div>
        )}
        {/* Suppress ComputeNote when the aspectual fallback drove the
           response — compute_decision will read clarification_needed
           and clash visually with the grounded evidence we just shared. */}
        {!aspectual && resp.compute_decision && (
          <ComputeNote cd={resp.compute_decision} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Suggestion chips
// ---------------------------------------------------------------------------

const SUGGESTIONS = [
  'How many late customers are there?',
  'When does route 3 finish?',
  'Which route is customer 12 on?',
  'How many routes are we using?',
  'What changed in this perturbation?',
  'Rank routes by lateness.',
  'What time does customer 5 arrive?',
  'What changed between baseline and now?',
];

// ---------------------------------------------------------------------------
// Apply visual_actions from the highlight contract on response arrival.
//
// docs/highlight_contract.md is the source of truth. Backend infers a list of
// VisualAction{kind, target} from (intent, evidence); this function maps each
// kind onto the corresponding frontend state setter.
//
// Empty actions list → refusal/unknown: leave the operator's lens alone and
// let the caller surface the available-fields hint instead.
// ---------------------------------------------------------------------------

const LENS_MODES = new Set<LensMode>(['route', 'lateness', 'slack']);

function applyVisualActions(
  resp: CopilotAskResponse,
  sel: VisualActionFns,
) {
  const actions = resp.visual_actions ?? [];
  if (actions.length === 0) return; // refusal / unknown: do NOT touch lens.

  const routes = new Set<number>();
  const customers = new Set<number>();

  for (const a of actions) {
    if (a.kind === 'set_lens') {
      const mode = a.target.mode;
      if (typeof mode === 'string' && LENS_MODES.has(mode as LensMode)) {
        sel.setLens(mode as LensMode);
      }
    } else if (a.kind === 'highlight_route') {
      const idx = a.target.route_idx;
      if (typeof idx === 'number') routes.add(idx);
    } else if (a.kind === 'highlight_customer') {
      const id = a.target.customer_id;
      if (typeof id === 'number') customers.add(id);
    } else if (a.kind === 'focus_panel') {
      const panel = a.target.panel;
      if (panel === 'map' || panel === 'schedule' || panel === 'tables') {
        sel.setCollapsed(panel, false);
      } else if (panel === 'impact') {
        // The "impact" panel is the diff tab inside Tables today.
        sel.setCollapsed('tables', false);
        sel.setTablesTab?.('diff');
      }
    }
    // highlight_summary / show_* card kinds: no-op here. The bot prose
    // already renders the answer; the cards live in their respective panels
    // and react to lens + selection, not to these kinds directly.
  }

  sel.setHighlights({ routes, customers });

  // Keep single-target Selection in sync when there's exactly one target —
  // existing click-aware code (scroll-into-view, tables tab nudge) keeps
  // working without churn.
  if (routes.size === 1 && customers.size === 0) {
    const [idx] = [...routes];
    sel.setSelection({ kind: 'route', idx });
    sel.setTablesTab?.('routes');
  } else if (customers.size === 1 && routes.size === 0) {
    const [id] = [...customers];
    sel.setSelection({ kind: 'customer', id });
    sel.setTablesTab?.('customers');
  }
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

export function CopilotPanel({
  scenarioId,
  scenario,
  selection: _selection,
  setSelection,
  setHighlights,
  setLens,
  setCollapsed,
  setTablesTab,
  collapsed,
  onToggleCollapse,
}: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const sel: SelectFns = { setSelection, setTablesTab };
  const va: VisualActionFns = {
    setSelection,
    setTablesTab,
    setHighlights,
    setLens,
    setCollapsed,
  };

  useEffect(() => {
    setMessages(
      scenarioId
        ? [
            {
              role: 'bot-info',
              text: (
                <>
                  Loaded <strong>{scenarioId}</strong>. Ask me anything about
                  this plan — routes, arrivals, lateness, the objective. I'll
                  highlight things on the map and tables as I go.
                </>
              ),
            },
          ]
        : [
            {
              role: 'bot-info',
              text: <>Pick a scenario in the top bar and we'll get going.</>,
            },
          ],
    );
  }, [scenarioId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, pending]);

  async function ask(text: string) {
    const t = text.trim();
    if (!t || !scenarioId || pending) return;
    setMessages((m) => [...m, { role: 'user', text: t }]);
    setDraft('');
    setPending(true);
    try {
      const resp = await fetchCopilotAsk({
        scenario_id: scenarioId,
        prompt: t,
      });
      // Frontend fallback: when the LLM-D1 adapter couldn't classify but the
      // answer is sitting in the loaded scenario payload, compute it locally.
      const contractDidNotAnswer =
        resp.intent === 'unknown' ||
        (resp.behavior_class === 'useful_refusal' && resp.evidence.length === 0);
      if (contractDidNotAnswer) {
        const local = localAnswer(t, scenario, sel);
        if (local) {
          setMessages((m) => [...m, { role: 'bot-local', node: local.node }]);
          if (local.select) setSelection(local.select);
          return;
        }
      }
      setMessages((m) => [...m, { role: 'bot-response', resp }]);
      applyVisualActions(resp, va);
    } catch (err: unknown) {
      const code = err instanceof ApiError ? err.body.code : 'network_error';
      const message =
        err instanceof ApiError
          ? err.body.message
          : err instanceof Error
            ? err.message
            : 'Unknown error';
      setMessages((m) => [...m, { role: 'bot-error', code, message }]);
    } finally {
      setPending(false);
    }
  }

  if (collapsed) {
    return (
      <div className="copilot-col collapsed">
        <div className="copilot-head">
          <CollapseToggle
            collapsed={collapsed}
            onToggle={onToggleCollapse}
            orientation="col"
          />
        </div>
      </div>
    );
  }

  return (
    <div className="copilot-col">
      <div className="copilot-head">
        <span className="pulse" />
        <span className="label">Copilot</span>
        <span style={{ flex: 1 }} />
        <CollapseToggle
          collapsed={collapsed}
          onToggle={onToggleCollapse}
          orientation="col"
        />
      </div>
      <div className="copilot-scroll scroll-thin" ref={scrollRef}>
        {messages.map((m, i) => (
          <CopilotMessage key={i} m={m} sel={sel} scenario={scenario} />
        ))}
        {pending && <TypingDots />}
      </div>
      <div className="copilot-suggest">
        {SUGGESTIONS.map((s) => (
          <span className="sg" key={s} onClick={() => ask(s)}>
            {s}
          </span>
        ))}
      </div>
      <form
        className="copilot-input"
        onSubmit={(e) => {
          e.preventDefault();
          ask(draft);
        }}
      >
        <input
          autoComplete="off"
          data-copilot-input
          placeholder={
            scenarioId ? 'Ask the copilot… ( / )' : 'Pick a scenario to start'
          }
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={!scenarioId || pending}
        />
        <button type="submit" disabled={!scenarioId || pending || !draft.trim()}>
          Ask
        </button>
      </form>
    </div>
  );
}
