import type { ProductMetrics } from '../types';

interface Props {
  metrics: ProductMetrics | null;
  error: string | null;
}

type MetricKind = 'quality' | 'compliance' | 'probe' | 'future';

const KIND_LABEL: Record<MetricKind, string> = {
  quality: 'Quality',
  compliance: 'Compliance',
  probe: 'Probe',
  future: 'Future',
};

function fmtRate(rate: number | null | undefined): string {
  if (rate == null || Number.isNaN(rate)) return '—';
  return rate.toFixed(3);
}

function PromptIdList({ ids }: { ids: string[] }) {
  if (!ids.length) return null;
  return <div className="prompt-ids">{ids.join(', ')}</div>;
}

function RateCard({
  kind,
  name,
  rate,
  numerator,
  denominator,
  target,
}: {
  kind: MetricKind;
  name: string;
  rate: number | null;
  numerator?: number;
  denominator?: number;
  target?: string;
}) {
  return (
    <div className={`metric-card ${kind}`}>
      <div className="metric-tag">{KIND_LABEL[kind]}</div>
      <div className="metric-name">{name}</div>
      <div className="metric-value">{fmtRate(rate)}</div>
      {numerator != null && denominator != null && (
        <div className="metric-sub">
          {numerator}/{denominator}
        </div>
      )}
      {target && <div className="metric-sub">target: {target}</div>}
    </div>
  );
}

function CountCard({
  kind,
  name,
  count,
  promptIds,
}: {
  kind: MetricKind;
  name: string;
  count: number;
  promptIds: string[];
}) {
  return (
    <div className={`metric-card ${kind}`}>
      <div className="metric-tag">{KIND_LABEL[kind]}</div>
      <div className="metric-name">{name}</div>
      <div className="metric-value">{count}</div>
      <PromptIdList ids={promptIds} />
    </div>
  );
}

export function ProductMetricsPanel({ metrics, error }: Props) {
  if (error) {
    return (
      <section className="panel">
        <h2>Run 1 Product Metrics</h2>
        <p className="error-message">Failed to load metrics: {error}</p>
      </section>
    );
  }
  if (!metrics) {
    return (
      <section className="panel">
        <h2>Run 1 Product Metrics</h2>
        <p className="loading">Loading metrics…</p>
      </section>
    );
  }

  const conv = metrics.convention_consistency;

  return (
    <section className="panel">
      <h2>Run 1 Product Metrics ({metrics.n_prompts} prompts)</h2>
      <p className="panel-note">
        Compliance metrics verify that the product contract exists. They do
        not by themselves prove user usefulness; user-facing usefulness
        requires the later task study.
      </p>

      <div className="metric-group">
        <h3>Direct Run 1 — quality</h3>
        <div className="metric-card-row">
          <RateCard
            kind="quality"
            name="grounded_answer_accuracy"
            rate={metrics.grounded_answer_accuracy.rate}
            numerator={metrics.grounded_answer_accuracy.numerator}
            denominator={metrics.grounded_answer_accuracy.denominator}
            target="≥ 0.95"
          />
        </div>
      </div>

      <div className="metric-group">
        <h3>Compliance / contract</h3>
        <div className="metric-card-row">
          <RateCard
            kind="compliance"
            name="evidence_coverage"
            rate={metrics.evidence_coverage.rate}
            numerator={metrics.evidence_coverage.numerator}
            denominator={metrics.evidence_coverage.denominator}
            target="= 1.000"
          />
          <CountCard
            kind="compliance"
            name="route_label_ambiguity_incidents"
            count={metrics.route_label_ambiguity_incidents.count}
            promptIds={metrics.route_label_ambiguity_incidents.prompt_ids}
          />
          <RateCard
            kind="compliance"
            name="useful_refusal_rate"
            rate={metrics.useful_refusal_rate.rate}
            numerator={metrics.useful_refusal_rate.numerator}
            denominator={metrics.useful_refusal_rate.denominator}
            target="= 1.000"
          />
        </div>
      </div>

      <div className="metric-group">
        <h3>Diagnostic / probe</h3>
        <div className="metric-card-row">
          <CountCard
            kind="probe"
            name="user_requested_unsupported_comparison"
            count={metrics.user_requested_unsupported_comparison_detection.count}
            promptIds={
              metrics.user_requested_unsupported_comparison_detection.prompt_ids
            }
          />
          <CountCard
            kind="probe"
            name="volunteered_or_risky_comparison_guardrail"
            count={metrics.volunteered_or_risky_comparison_guardrail_hits.count}
            promptIds={
              metrics.volunteered_or_risky_comparison_guardrail_hits.prompt_ids
            }
          />
          <CountCard
            kind="probe"
            name="route_indexing_warning_count"
            count={metrics.route_indexing_warning_count.count}
            promptIds={metrics.route_indexing_warning_count.prompt_ids}
          />
          <CountCard
            kind="probe"
            name="struct_membership_warning_count"
            count={metrics.struct_membership_warning_count.count}
            promptIds={metrics.struct_membership_warning_count.prompt_ids}
          />
          <div className="metric-card probe">
            <div className="metric-tag">Probe</div>
            <div className="metric-name">convention_consistency</div>
            <div className="metric-value">
              {conv.consistent.length} / {conv.inconsistent.length} / {conv.not_applicable.length}
            </div>
            <div className="metric-sub">consistent / inconsistent / N/A</div>
            {conv.inconsistent.length > 0 && (
              <>
                <div className="metric-sub" style={{ marginTop: 4 }}>
                  inconsistent:
                </div>
                <PromptIdList ids={conv.inconsistent} />
              </>
            )}
            {conv.consistent.length > 0 && (
              <>
                <div className="metric-sub" style={{ marginTop: 4 }}>
                  consistent:
                </div>
                <PromptIdList ids={conv.consistent} />
              </>
            )}
          </div>
        </div>
      </div>

      <div className="metric-group">
        <h3>Future — user study</h3>
        <div className="metric-card-row">
          <div className="metric-card future">
            <div className="metric-tag">Future</div>
            <div className="metric-name">time_to_answer_reduction</div>
            <div className="metric-value">not measured</div>
            <div className="metric-sub">{metrics.time_to_answer_reduction_note}</div>
          </div>
        </div>
      </div>
    </section>
  );
}
