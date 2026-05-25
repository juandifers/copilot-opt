// Top bar v3: scenario select dropdown + solver-health badge.
// System selector removed — only the final D4 system is in scope.
import { useEffect, useRef, useState } from 'react';
import type { InstanceSummary, ScenarioResponse } from '../api/types';

export interface HealthSummary {
  warnings: number;
  warnings_list: string[];
  missing: string[];
  errors: number;
}

interface Option {
  value: string;
  label: string;
}

interface TopBarProps {
  scenario: ScenarioResponse | null;
  scenarioId: string | null;
  instances: InstanceSummary[];
  onPickScenario: (instanceId: string, perturbationId: string) => void;
  health: HealthSummary;
}

export function TopBar({
  scenario,
  scenarioId,
  instances,
  onPickScenario,
  health,
}: TopBarProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function h(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const level =
    health.errors > 0 ? 'error' : health.warnings > 0 ? 'warn' : 'ok';

  const grouped: Record<string, Option[]> = {};
  for (const ins of instances) {
    if (!grouped[ins.family]) grouped[ins.family] = [];
    for (const pid of ins.available_perturbations) {
      grouped[ins.family].push({
        value: `${ins.instance_id}__${pid}`,
        label: `${ins.instance_id}  ·  ${pid}`,
      });
    }
  }

  return (
    <div className="topbar">
      <div className="tb-brand">
        <span className="tb-logo">V</span>
        VRPTW · COPILOT
      </div>
      <div
        className="tb-field"
        style={{ minWidth: 260, borderRight: '1px solid var(--border)' }}
      >
        <span className="lbl">Scenario</span>
        <span className="val" style={{ marginTop: 4 }}>
          <select
            className="tb-scenario-select"
            value={scenarioId ?? ''}
            disabled={instances.length === 0}
            onChange={(e) => {
              const [i, p] = e.target.value.split('__');
              onPickScenario(i, p);
            }}
          >
            {scenarioId == null && (
              <option value="" disabled>
                — select scenario —
              </option>
            )}
            {Object.entries(grouped).map(([fam, opts]) => (
              <optgroup label={fam} key={fam}>
                {opts.map((o) => (
                  <option value={o.value} key={o.value}>
                    {o.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </span>
      </div>
      <div className="tb-field" style={{ minWidth: 220 }}>
        <span className="lbl">Perturbation</span>
        <span className="val" title={scenario?.perturbation_summary}>
          {scenario ? scenario.perturbation_summary : '—'}
        </span>
      </div>
      <div className="tb-spacer" />
      <div
        ref={ref}
        className={'tb-health ' + level}
        onClick={() => setOpen((x) => !x)}
        title="Solver output health"
      >
        <span className="dot" />
        <span className="label">Solver health</span>
        <span className="count">
          {health.warnings}W · {health.missing.length}M
        </span>
        {open && (
          <div className="health-popover" onClick={(e) => e.stopPropagation()}>
            <h4>Solver Output Diagnostics</h4>
            {health.warnings_list.map((w, i) => (
              <div className="h-row" key={'w' + i}>
                <span className="h-tag warn">warn</span>
                <span>{w}</span>
              </div>
            ))}
            {health.missing.length > 0 && (
              <div className="h-row">
                <span className="h-tag missing">missing</span>
                <span>
                  Payload does not include:{' '}
                  {health.missing.map((m, i) => (
                    <code
                      key={i}
                      style={{ fontFamily: 'var(--mono)', fontSize: 11 }}
                    >
                      {m}
                      {i < health.missing.length - 1 ? ', ' : ''}
                    </code>
                  ))}
                </span>
              </div>
            )}
            <div className="h-row">
              <span className="h-tag" style={{ color: 'var(--text-dim)' }}>
                route_idx
              </span>
              <span style={{ color: 'var(--text-dim)' }}>
                Solver returns zero-based <code>route_idx</code>; UI displays{' '}
                <code>route_label</code>.
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
