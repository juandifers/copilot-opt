// Available-fields strip — shows which payload blocks are populated for the current scenario.
import type { AvailableFields, ScenarioResponse } from '../api/types';

const FIELDS: [keyof AvailableFields, string][] = [
  ['solution', 'solution'],
  ['routes', 'routes'],
  ['customer_schedule', 'schedule'],
  ['route_end_times', 'end_times'],
  ['baseline_solution', 'baseline'],
  ['diff', 'diff'],
  ['objective_delta', 'obj_delta'],
  ['causal_diagnostics', 'causal'],
];

interface Props {
  scenario: ScenarioResponse | null;
}

export function AvailableFieldsStrip({ scenario }: Props) {
  const af: Partial<AvailableFields> = scenario?.available_fields || {};
  return (
    <div className="af-strip scroll-thin">
      <span className="af-label">available_fields</span>
      {FIELDS.map(([k, label]) => (
        <span key={k} className={'af-pill ' + (af[k] ? 'on' : 'off')}>
          {label}
        </span>
      ))}
      <span className="af-spacer" />
      {scenario && <span className="pert-summary">{scenario.perturbation_summary}</span>}
    </div>
  );
}
