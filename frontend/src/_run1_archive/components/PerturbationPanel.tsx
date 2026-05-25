import type { VisualContext } from '../types';

interface Props {
  visual: VisualContext | null;
}

export function PerturbationPanel({ visual }: Props) {
  if (!visual) {
    return (
      <section className="panel">
        <h2>Perturbation</h2>
        <p className="loading">Select a prompt to view perturbation context.</p>
      </section>
    );
  }

  const ctx = visual.perturbation_context;

  return (
    <section className="panel">
      <h2>Perturbation</h2>
      <div className="kv-row">
        <span className="k">perturbation_id</span>
        <span className="v">{ctx.perturbation_id ?? '—'}</span>
      </div>
      <div className="kv-row">
        <span className="k">perturbation_family</span>
        <span className="v">{ctx.perturbation_family ?? '—'}</span>
      </div>
      <div className="kv-row">
        <span className="k">instance_id</span>
        <span className="v">{visual.instance_id ?? '—'}</span>
      </div>
      <div className="pert-summary">{ctx.summary}</div>

      {Object.keys(ctx.known_fields).length > 0 && (
        <>
          <h3>Known fields</h3>
          <ul className="tight">
            {Object.entries(ctx.known_fields).map(([k, v]) => (
              <li key={k}>
                <code>{k}</code>:{' '}
                <span style={{ fontFamily: 'ui-monospace, monospace' }}>
                  {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      {ctx.missing_fields.length > 0 && (
        <>
          <h3>Missing fields</h3>
          <ul className="tight">
            {ctx.missing_fields.map((f, i) => (
              <li key={i} style={{ color: 'var(--text-dim)' }}>
                {f}
              </li>
            ))}
          </ul>
        </>
      )}

      {visual.limitations.length > 0 && (
        <>
          <h3>Limitations</h3>
          <ul className="tight">
            {visual.limitations.map((l, i) => (
              <li key={i} style={{ color: 'var(--warn)' }}>
                {l}
              </li>
            ))}
          </ul>
        </>
      )}

      {visual.geometry_error && (
        <p className="error-message" style={{ marginTop: 8 }}>
          {visual.geometry_error}
        </p>
      )}
    </section>
  );
}
