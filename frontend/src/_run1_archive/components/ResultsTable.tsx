import type { RunResultRow } from '../types';

interface Props {
  rows: RunResultRow[];
  totalRows: number;
  error: string | null;
  selectedPromptId: string | null;
  onSelect: (promptId: string) => void;
}

function formatScore(v: number | null | undefined): string {
  if (v == null) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(2);
}

function formatBool(v: unknown): { text: string; cls: string } {
  if (v === true) return { text: 'pass', cls: 'pass' };
  if (v === false) return { text: 'fail', cls: 'fail' };
  return { text: '—', cls: '' };
}

export function ResultsTable({
  rows,
  totalRows,
  error,
  selectedPromptId,
  onSelect,
}: Props) {
  return (
    <section className="panel">
      <h2>
        Prompts ({rows.length}
        {totalRows && totalRows !== rows.length ? ` / ${totalRows}` : ''})
      </h2>
      {error && <p className="error-message">Failed to load results: {error}</p>}
      <div className="results-scroll">
        <table className="results-table">
          <thead>
            <tr>
              <th>prompt</th>
              <th>family</th>
              <th>source</th>
              <th>quadrant</th>
              <th>sufficiency</th>
              <th>policy</th>
              <th>action</th>
              <th>faith</th>
              <th>op_val</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const passClass = formatBool(row.runner_op_validity_pass);
              return (
                <tr
                  key={row.prompt_id}
                  className={row.prompt_id === selectedPromptId ? 'selected' : ''}
                  onClick={() => onSelect(row.prompt_id)}
                  title={row.prompt_text || ''}
                >
                  <td className="num">{row.prompt_id}</td>
                  <td>{row.family}</td>
                  <td>{row.source}</td>
                  <td>{row.quadrant ?? '—'}</td>
                  <td>{row.sufficiency_label ?? '—'}</td>
                  <td>{row.policy_decision ?? '—'}</td>
                  <td>{row.action_taken ?? '—'}</td>
                  <td className="num">{formatScore(row.faithfulness_score)}</td>
                  <td className={passClass.cls}>{passClass.text}</td>
                </tr>
              );
            })}
            {rows.length === 0 && !error && (
              <tr>
                <td colSpan={9} style={{ textAlign: 'center', padding: '12px' }}>
                  No prompts match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
