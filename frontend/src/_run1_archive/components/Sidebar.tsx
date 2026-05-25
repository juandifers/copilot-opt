import type { RunResultRow } from '../types';
import type { FilterState } from '../App';

interface Props {
  rows: RunResultRow[] | null;
  filters: FilterState;
  onChange: (f: FilterState) => void;
  onClear: () => void;
}

const FACETS: Array<{ key: keyof FilterState; label: string }> = [
  { key: 'family', label: 'family' },
  { key: 'source', label: 'source' },
  { key: 'quadrant', label: 'quadrant' },
  { key: 'action_taken', label: 'action_taken' },
  { key: 'sufficiency_label', label: 'sufficiency_label' },
  { key: 'policy_decision', label: 'policy_decision' },
];

function distinctValues(rows: RunResultRow[], key: keyof RunResultRow): string[] {
  const set = new Set<string>();
  for (const r of rows) {
    const v = r[key];
    if (v == null || v === '') continue;
    set.add(String(v));
  }
  return Array.from(set).sort();
}

export function Sidebar({ rows, filters, onChange, onClear }: Props) {
  if (!rows) {
    return (
      <section className="panel">
        <h2>Filters</h2>
        <p className="loading">Loading prompt list…</p>
      </section>
    );
  }

  const set = (key: keyof FilterState, value: string) =>
    onChange({ ...filters, [key]: value });

  const scoreValues = Array.from(
    new Set(
      rows
        .map((r) => (r.faithfulness_score == null ? 'null' : String(r.faithfulness_score)))
        .filter((v) => v !== ''),
    ),
  ).sort();

  return (
    <section className="panel">
      <h2>Filters</h2>
      <div className="filters">
        {FACETS.map(({ key, label }) => {
          const values = distinctValues(rows, key as keyof RunResultRow);
          if (values.length === 0) return null;
          return (
            <div className="filter-row" key={key}>
              <label htmlFor={`f-${key}`}>{label}</label>
              <select
                id={`f-${key}`}
                value={filters[key]}
                onChange={(e) => set(key, e.target.value)}
              >
                <option value="">(any)</option>
                {values.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
          );
        })}

        <div className="filter-row">
          <label htmlFor="f-faithfulness">faithfulness_score</label>
          <select
            id="f-faithfulness"
            value={filters.faithfulness_score}
            onChange={(e) => set('faithfulness_score', e.target.value)}
          >
            <option value="">(any)</option>
            {scoreValues.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-row">
          <label htmlFor="f-refusal">refusal</label>
          <select
            id="f-refusal"
            value={filters.refusal}
            onChange={(e) => set('refusal', e.target.value)}
          >
            <option value="">(any)</option>
            <option value="refused">refused (runner or judge)</option>
            <option value="not_refused">not refused</option>
          </select>
        </div>

        <button className="linklike" onClick={onClear} type="button">
          clear filters
        </button>
      </div>
    </section>
  );
}
