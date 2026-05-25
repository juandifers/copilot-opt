import type { ProductCopilotResponse } from '../types';

interface Props {
  context: ProductCopilotResponse | null;
}

const EXPLANATIONS: Record<string, { title: string; body: string }> = {
  route_indexing_ambiguity: {
    title: 'Route indexing convention',
    body:
      'Route labels can be confusing because internal route_idx starts at 0 while users see Route 1, Route 2, etc. The product schema now exposes both display_route_number and route_idx so the answer and the evidence point to the same route.',
  },
  struct_membership_ambiguity: {
    title: 'STRUCT membership ambiguity',
    body:
      'This is a single-customer route-membership claim. It should be checked as "customer is contained in route", not as "the full route equals this one customer". The product layer enforces the containment interpretation.',
  },
  unsupported_comparison: {
    title: 'Unsupported before/after comparison',
    body:
      'The question asks for a before/after comparison, but the current payload lacks baseline_solution or diff fields. The product layer surfaces a useful refusal with the available subclaims instead of a hallucinated comparison.',
  },
  missing_new_customer_attribution: {
    title: 'Missing new-customer attribution',
    body:
      'The question depends on knowing which customer was newly inserted by the perturbation, but the current payload does not expose new_customer_ids. The product layer cannot attribute the assignment directly.',
  },
};

export function WarningPanel({ context }: Props) {
  if (!context) {
    return (
      <section className="panel">
        <h2>Warnings</h2>
        <p className="loading">Select a prompt to view warnings.</p>
      </section>
    );
  }

  const warnings = context.warnings ?? [];

  return (
    <section className="panel">
      <h2>Warnings &amp; diagnostics</h2>
      {warnings.length === 0 ? (
        <p className="loading">No warnings raised for this prompt.</p>
      ) : (
        warnings.map((code) => {
          const info = EXPLANATIONS[code];
          return (
            <div className="warning-banner" key={code}>
              <div className="warning-code">{code}</div>
              <div>
                <strong>{info?.title ?? code}</strong>
                {info && <p style={{ margin: '4px 0 0' }}>{info.body}</p>}
              </div>
            </div>
          );
        })
      )}

      <h3>Metrics flags</h3>
      <div className="kv-row">
        <span className="k">grounded_answer_available</span>
        <span className="v">
          {context.metrics_flags.grounded_answer_available ? 'yes' : 'no'}
        </span>
      </div>
      <div className="kv-row">
        <span className="k">unsupported_comparison_detected</span>
        <span className="v">
          {context.metrics_flags.unsupported_comparison_detected ? 'yes' : 'no'}
        </span>
      </div>
      <div className="kv-row">
        <span className="k">route_label_ambiguity_resolved</span>
        <span className="v">
          {context.metrics_flags.route_label_ambiguity_resolved ? 'yes' : 'no'}
        </span>
      </div>
      <div className="kv-row">
        <span className="k">useful_refusal_available</span>
        <span className="v">
          {context.metrics_flags.useful_refusal_available ? 'yes' : 'no'}
        </span>
      </div>
    </section>
  );
}
