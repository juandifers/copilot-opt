import type { ProductCopilotResponse, VisualAction } from '../types';

interface Props {
  context: ProductCopilotResponse | null;
}

function fmtValue(value: unknown): string {
  if (value == null) return 'null';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function describeVisualAction(action: VisualAction): string {
  const t = action.target ?? {};
  const parts: string[] = [];
  for (const [k, v] of Object.entries(t)) {
    parts.push(`${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`);
  }
  return parts.length ? `${action.kind} (${parts.join(', ')})` : action.kind;
}

export function EvidencePanel({ context }: Props) {
  if (!context) {
    return (
      <section className="panel">
        <h2>Evidence</h2>
        <p className="loading">Select a prompt to view evidence.</p>
      </section>
    );
  }

  const evidence = context.evidence ?? [];
  const missing = context.missing_fields ?? [];
  const refusal = context.useful_refusal;
  const visualActions = context.visual_actions ?? [];

  return (
    <section className="panel">
      <h2>Evidence &amp; answerability</h2>

      <h3>Evidence items ({evidence.length})</h3>
      {evidence.length === 0 ? (
        <p className="loading">No evidence items.</p>
      ) : (
        evidence.map((item, i) => (
          <div className="evidence-item" key={i}>
            <div className="field-path">{item.field_path}</div>
            {item.display_label && (
              <div className="supports" style={{ fontStyle: 'italic' }}>
                {item.display_label}
              </div>
            )}
            <div className="evidence-value">{fmtValue(item.value)}</div>
            <div className="supports">{item.supports}</div>
          </div>
        ))
      )}

      <h3>Missing fields ({missing.length})</h3>
      {missing.length === 0 ? (
        <p className="loading">None.</p>
      ) : (
        <ul className="tight">
          {missing.map((field) => (
            <li key={field}>
              <code>{field}</code>
            </li>
          ))}
        </ul>
      )}

      <h3>Useful refusal</h3>
      {refusal ? (
        <div className="evidence-item" style={{ background: 'var(--warn-soft)' }}>
          <div className="supports" style={{ fontSize: '0.85rem', color: 'var(--text)' }}>
            {refusal.refusal_reason}
          </div>
          {refusal.available_subclaims.length > 0 && (
            <>
              <div className="supports" style={{ marginTop: 6 }}>
                <strong>Answerable subclaims:</strong>
              </div>
              <ul className="tight">
                {refusal.available_subclaims.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </>
          )}
          {refusal.suggested_next_actions.length > 0 && (
            <>
              <div className="supports" style={{ marginTop: 6 }}>
                <strong>Suggested next actions:</strong>
              </div>
              <ul className="tight">
                {refusal.suggested_next_actions.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      ) : (
        <p className="loading">Not applicable — response is answerable.</p>
      )}

      <h3>Visual actions ({visualActions.length})</h3>
      <p className="panel-note">
        Hints the frontend would use to highlight the map / route view. The
        spatial map is not rendered in Stage 3.
      </p>
      {visualActions.length === 0 ? (
        <p className="loading">No visual actions.</p>
      ) : (
        <ul className="tight">
          {visualActions.map((a, i) => (
            <li key={i} className="visual-action">
              {describeVisualAction(a)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
