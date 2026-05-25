import type {
  AnswerabilityStatus,
  ProductCopilotResponse,
  RunResultRow,
} from '../types';

interface Props {
  promptId: string | null;
  row: RunResultRow | null;
  context: ProductCopilotResponse | null;
  loading: boolean;
  error: string | null;
}

function badgeClass(status: AnswerabilityStatus | undefined): string {
  if (!status) return 'neutral';
  return status;
}

function badgeLabel(status: AnswerabilityStatus | undefined): string {
  switch (status) {
    case 'answerable':
      return 'answerable';
    case 'partially_answerable':
      return 'partially answerable';
    case 'not_answerable':
      return 'not answerable';
    default:
      return 'unknown';
  }
}

function MetadataDl({
  row,
  context,
}: {
  row: RunResultRow | null;
  context: ProductCopilotResponse | null;
}) {
  const entries: Array<[string, string]> = [];
  const push = (k: string, v: unknown) => {
    if (v == null || v === '') return;
    entries.push([k, String(v)]);
  };
  const prompt = context;
  push('prompt_id', prompt?.prompt_id ?? row?.prompt_id);
  push('family', prompt?.family ?? row?.family);
  push('source', prompt?.source ?? row?.source);
  push('quadrant', prompt?.quadrant ?? row?.quadrant);
  push('action_taken', prompt?.action_taken ?? row?.action_taken);
  push('sufficiency_label', row?.sufficiency_label);
  push('policy_decision', row?.policy_decision);
  push('instance_id', row?.instance_id);
  push('perturbation_id', row?.perturbation_id);

  return (
    <dl className="prompt-meta">
      {entries.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function PromptDetail({ promptId, row, context, loading, error }: Props) {
  if (!promptId) {
    return (
      <section className="panel">
        <h2>Prompt detail</h2>
        <p className="loading">Select a prompt from the table.</p>
      </section>
    );
  }

  const intent = context?.intent;
  const answerability = context?.answerability;
  const faithScore = row?.faithfulness_score;
  const grounded = context?.metrics_flags.grounded_answer_available;

  return (
    <section className="panel">
      <h2>Prompt detail — {promptId}</h2>
      {loading && <p className="loading">Loading copilot context…</p>}
      {error && <p className="error-message">{error}</p>}

      <MetadataDl row={row} context={context} />

      <h3>User question</h3>
      <div className="question-block">
        {context?.question || row?.prompt_text || '—'}
      </div>

      <h3>Generator answer</h3>
      <div className="answer-block">
        {context?.answer_text || row?.answer_text || '—'}
      </div>

      <h3>Intent &amp; answerability</h3>
      <div className="kv-row">
        <span className="k">intent</span>
        <span className="v">{intent ?? '—'}</span>
      </div>
      <div className="kv-row">
        <span className="k">answerability</span>
        <span className={`badge ${badgeClass(answerability?.status)}`}>
          {badgeLabel(answerability?.status)}
        </span>
      </div>

      <h3>Faithfulness &amp; grounding</h3>
      <div className="kv-row">
        <span className="k">faithfulness_score</span>
        <span className="v">
          {faithScore == null ? '—' : String(faithScore)}
          {typeof faithScore === 'number' && (
            <span
              className={`badge ${faithScore >= 4 ? 'score-pass' : 'score-fail'}`}
              style={{ marginLeft: 8 }}
            >
              {faithScore >= 4 ? '≥ 4 (grounded)' : '< 4'}
            </span>
          )}
        </span>
      </div>
      <div className="kv-row">
        <span className="k">grounded_answer_available</span>
        <span className="v">{grounded == null ? '—' : grounded ? 'yes' : 'no'}</span>
      </div>
      <div className="kv-row">
        <span className="k">evidence_shown</span>
        <span className="v">
          {context?.metrics_flags.evidence_shown == null
            ? '—'
            : context.metrics_flags.evidence_shown
              ? 'yes'
              : 'no'}
        </span>
      </div>
      <div className="kv-row">
        <span className="k">route_label_ambiguity_resolved</span>
        <span className="v">
          {context?.metrics_flags.route_label_ambiguity_resolved == null
            ? '—'
            : context.metrics_flags.route_label_ambiguity_resolved
              ? 'yes'
              : 'no'}
        </span>
      </div>
      <div className="kv-row">
        <span className="k">useful_refusal_available</span>
        <span className="v">
          {context?.metrics_flags.useful_refusal_available == null
            ? '—'
            : context.metrics_flags.useful_refusal_available
              ? 'yes'
              : 'no'}
        </span>
      </div>

      {context?.suggested_next_actions && context.suggested_next_actions.length > 0 && (
        <>
          <h3>Suggested next actions</h3>
          <ul className="tight">
            {context.suggested_next_actions.map((action, i) => (
              <li key={i}>{action}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
