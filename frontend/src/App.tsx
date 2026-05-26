// App shell v2. Picker rail removed; scenario selection moved into TopBar dropdown.
// System hardcoded to "d4" (the only system in scope).
// Loads /health + /instances on mount, then fetches scenarios on dropdown change.
import { useEffect, useMemo, useState } from 'react';
import {
  ApiError,
  fetchDiff,
  fetchHealth,
  fetchInstances,
  fetchScenario,
} from './api/client';
import type {
  DiffResponse,
  HealthResponse,
  InstanceSummary,
  ScenarioResponse,
} from './api/types';
import { CopilotPanel } from './components/CopilotPanel';
import { MapPanel } from './components/MapPanel';
import { SchedulePanel } from './components/SchedulePanel';
import { TablesPanel } from './components/TablesPanel';
import { CollapseToggle } from './components/CollapseToggle';
import { LensSwitch } from './components/LensSwitch';
import { ColResizer, RowResizer } from './components/Resizers';
import type { TablesTab } from './components/TablesPanel';
import { TopBar, type HealthSummary } from './components/TopBar';
import { NONE, type Selection } from './selection';
import type { LensMode } from './lens';

interface Layout {
  mapH: number;
  scheduleH: number;
  tablesH: number;
  copilotW: number;
}

interface Collapsed {
  map: boolean;
  schedule: boolean;
  tables: boolean;
  copilot: boolean;
}

const DEFAULT_LAYOUT: Layout = {
  mapH: 240,
  scheduleH: 240,
  tablesH: 140,
  copilotW: 400,
};

const DEFAULT_COLLAPSED: Collapsed = {
  map: false,
  schedule: false,
  tables: false,
  copilot: false,
};

const LS_LAYOUT = 'copilot-opt:layout-v1';
const LS_COLLAPSED = 'copilot-opt:collapsed-v1';
const LS_LENS = 'copilot-opt:lens-v1';
const LS_TAB = 'copilot-opt:tables-tab-v1';

function loadLens(): LensMode {
  try {
    const v = localStorage.getItem(LS_LENS);
    if (v === 'route' || v === 'lateness' || v === 'slack') return v;
  } catch {}
  return 'route';
}
function loadTab(): TablesTab {
  try {
    const v = localStorage.getItem(LS_TAB);
    if (v === 'routes' || v === 'customers' || v === 'diff') return v;
  } catch {}
  return 'routes';
}

function loadLayout(): Layout {
  try {
    const raw = localStorage.getItem(LS_LAYOUT);
    if (!raw) return DEFAULT_LAYOUT;
    const parsed = JSON.parse(raw) as Partial<Layout>;
    return {
      mapH: typeof parsed.mapH === 'number' ? parsed.mapH : DEFAULT_LAYOUT.mapH,
      scheduleH: typeof parsed.scheduleH === 'number' ? parsed.scheduleH : DEFAULT_LAYOUT.scheduleH,
      tablesH: typeof parsed.tablesH === 'number' ? parsed.tablesH : DEFAULT_LAYOUT.tablesH,
      copilotW: typeof parsed.copilotW === 'number' ? parsed.copilotW : DEFAULT_LAYOUT.copilotW,
    };
  } catch {
    return DEFAULT_LAYOUT;
  }
}

function loadCollapsed(): Collapsed {
  try {
    const raw = localStorage.getItem(LS_COLLAPSED);
    if (!raw) return DEFAULT_COLLAPSED;
    const parsed = JSON.parse(raw) as Partial<Collapsed>;
    return {
      map: !!parsed.map,
      schedule: !!parsed.schedule,
      tables: !!parsed.tables,
      copilot: !!parsed.copilot,
    };
  } catch {
    return DEFAULT_COLLAPSED;
  }
}

const PANEL_HEAD_H = 32;
const COPILOT_HEAD_W = 36;
const MIN_MAP_W = 40;
const MIN_SCHEDULE_W = 60;
const MIN_TABLES_W = 40;
const MIN_COPILOT_W = 280;
const MIN_MAIN_LEFT_W = 480;

const FALLBACK_HEALTH: HealthResponse = {
  status: 'ok',
  run2_contract_base_commit: '',
  run2_contract_base_tag: '',
  current_git_commit: null,
  available_systems: ['d4'],
  default_system: 'd4',
};

function inferShape(scenario: ScenarioResponse | null): 'SCHEDULE' | 'STRUCT' | 'OBJ' | null {
  if (!scenario) return null;
  const af = scenario.available_fields;
  if (af.customer_schedule) return 'SCHEDULE';
  if (af.routes) return 'STRUCT';
  return 'OBJ';
}

export default function App() {
  const [, setHealth] = useState<HealthResponse | null>(null);
  const [instances, setInstances] = useState<InstanceSummary[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [scenario, setScenario] = useState<ScenarioResponse | null>(null);
  const [scenarioError, setScenarioError] = useState<string | null>(null);

  // Diff data lands here once the Diff tab triggers a fetch.
  const [diffData, setDiffData] = useState<DiffResponse | null>(null);
  const [diffLoading, setDiffLoading] = useState<boolean>(false);
  const [diffNotAvailable, setDiffNotAvailable] = useState<boolean>(false);

  // Cross-panel selection (route / customer / summary). Schedule and Tables
  // share the same state; Map will adopt the same selection when it's wired.
  const [selection, setSelection] = useState<Selection>(NONE);

  // Operator-adjustable panel sizes; persisted to localStorage across reloads.
  const [layout, setLayout] = useState<Layout>(loadLayout);
  const [collapsed, setCollapsed] = useState<Collapsed>(loadCollapsed);

  useEffect(() => {
    try { localStorage.setItem(LS_LAYOUT, JSON.stringify(layout)); } catch {}
  }, [layout]);
  useEffect(() => {
    try { localStorage.setItem(LS_COLLAPSED, JSON.stringify(collapsed)); } catch {}
  }, [collapsed]);

  // Tab state is lifted so the Copilot can auto-switch to Routes/Customers
  // when an evidence chip with a routing anchor is clicked.
  const [tablesTab, setTablesTab] = useState<TablesTab>(loadTab);

  // Lens overlay: shared between Map and Schedule so toggling one updates both.
  const [lens, setLens] = useState<LensMode>(loadLens);

  useEffect(() => {
    try { localStorage.setItem(LS_LENS, lens); } catch {}
  }, [lens]);
  useEffect(() => {
    try { localStorage.setItem(LS_TAB, tablesTab); } catch {}
  }, [tablesTab]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const inField =
        !!target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable);
      if (e.key === 'Escape') {
        // Even from inside an input: blur and clear (matches operator muscle memory).
        if (inField && target) target.blur();
        setSelection(NONE);
        return;
      }
      if (inField) return;
      if (e.key === '/') {
        const el = document.querySelector<HTMLInputElement>('input[data-copilot-input]');
        if (el && !el.disabled) {
          e.preventDefault();
          el.focus();
        }
        return;
      }
      if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
        // Cycle route selection
        const sol = scenario?.solution;
        let routeIdxs: number[] = [];
        if (sol?.routes) {
          routeIdxs = sol.routes.map((r) => r.route_idx);
        } else if (sol?.customer_schedule) {
          const s = new Set<number>();
          for (const row of sol.customer_schedule) s.add(row.route_idx);
          routeIdxs = [...s];
        }
        routeIdxs.sort((a, b) => a - b);
        if (routeIdxs.length === 0) return;
        let cur = selection.kind === 'route' ? selection.idx : -1;
        const i = routeIdxs.indexOf(cur);
        const delta = e.key === 'ArrowDown' ? 1 : -1;
        const next = i === -1
          ? (delta === 1 ? routeIdxs[0] : routeIdxs[routeIdxs.length - 1])
          : routeIdxs[(i + delta + routeIdxs.length) % routeIdxs.length];
        const label = sol?.routes?.find((r) => r.route_idx === next)?.route_label
          ?? sol?.customer_schedule?.find((r) => r.route_idx === next)?.route_label
          ?? 'Route ' + (next + 1);
        e.preventDefault();
        setSelection({ kind: 'route', idx: next, label });
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [scenario, selection]);

  function toggleCollapse(key: keyof Collapsed) {
    setCollapsed((c) => ({ ...c, [key]: !c[key] }));
  }

  function maximizePanel(key: 'map' | 'schedule' | 'tables') {
    const others = (['map', 'schedule', 'tables'] as const).filter((k) => k !== key);
    const allOthersCollapsed = others.every((k) => collapsed[k]);
    if (allOthersCollapsed && !collapsed[key]) {
      setCollapsed((c) => ({ ...c, map: false, schedule: false, tables: false }));
    } else {
      const next: Partial<Collapsed> = { [key]: false };
      for (const k of others) next[k] = true;
      setCollapsed((c) => ({ ...c, ...next }));
    }
  }

  function resizeMapVsSchedule(dy: number) {
    setLayout((l) => {
      const nm = l.mapH + dy;
      const ns = l.scheduleH - dy;
      if (nm < MIN_MAP_W || ns < MIN_SCHEDULE_W) return l;
      return { ...l, mapH: nm, scheduleH: ns };
    });
  }
  function resizeScheduleVsTables(dy: number) {
    setLayout((l) => {
      const ns = l.scheduleH + dy;
      const nt = l.tablesH - dy;
      if (ns < MIN_SCHEDULE_W || nt < MIN_TABLES_W) return l;
      return { ...l, scheduleH: ns, tablesH: nt };
    });
  }
  function resizeMainVsCopilot(dx: number) {
    setLayout((l) => {
      const nw = l.copilotW - dx;
      if (nw < MIN_COPILOT_W) return l;
      // Don't let main-left collapse below its min either.
      if (window.innerWidth - nw - 4 < MIN_MAIN_LEFT_W) return l;
      return { ...l, copilotW: nw };
    });
  }

  useEffect(() => {
    let live = true;
    Promise.all([fetchHealth(), fetchInstances()])
      .then(([h, ins]) => {
        if (!live) return;
        setHealth(h);
        setInstances(ins.instances);
      })
      .catch((err: unknown) => {
        if (!live) return;
        if (err instanceof ApiError) {
          setLoadError(`API error · ${err.body.code}: ${err.body.message}`);
        } else {
          setLoadError(
            'Could not reach FastAPI at /api. Start it with: uvicorn product.api.app:app --port 8000',
          );
        }
        setHealth(FALLBACK_HEALTH);
      });
    return () => {
      live = false;
    };
  }, []);

  function pickScenario(instanceId: string, perturbationId: string) {
    const sid = `${instanceId}__${perturbationId}`;
    setScenarioId(sid);
    setScenario(null);
    setScenarioError(null);
    setSelection(NONE);
    setDiffData(null);
    setDiffLoading(false);
    setDiffNotAvailable(false);
    fetchScenario(instanceId, perturbationId)
      .then((s) => setScenario(s))
      .catch((err: unknown) => {
        if (err instanceof ApiError) {
          setScenarioError(`${err.body.code}: ${err.body.message}`);
        } else {
          setScenarioError('Failed to load scenario.');
        }
      });
  }

  function loadDiff() {
    if (!scenario || diffLoading) return;
    setDiffLoading(true);
    setDiffNotAvailable(false);
    fetchDiff(scenario.instance_id, scenario.perturbation_id)
      .then((d) => setDiffData(d))
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.body.code === 'diff_not_available') {
          setDiffNotAvailable(true);
        }
        // Other errors fall through; tab will show empty state again.
      })
      .finally(() => setDiffLoading(false));
  }

  const healthSummary: HealthSummary = useMemo(() => {
    const af = scenario?.available_fields;
    const warnings_list = [
      'Route numbering is solver-zero-based (`route_idx`) but rendered as one-based labels.',
    ];
    const missing: string[] = [];
    if (af) {
      if (!af.diff && !af.baseline_solution) {
        missing.push('baseline_solution', 'diff');
      }
      if (!af.causal_diagnostics) missing.push('causal_diagnostics');
      if (!af.objective_delta) missing.push('objective_delta');
      if (!af.routes && !af.customer_schedule) {
        warnings_list.push(
          'Payload carries neither routes[] nor customer_schedule — map and tables are constrained.',
        );
      }
    }
    return {
      warnings: warnings_list.length,
      warnings_list,
      missing,
      errors: 0,
    };
  }, [scenario]);

  const shape = inferShape(scenario);
  const isOBJ = shape === 'OBJ';

  // Effective track sizes: collapsed panels get a fixed px header,
  // expanded panels share remaining space via fr weights.
  const mapTrack = collapsed.map ? `${PANEL_HEAD_H}px` : `${layout.mapH}fr`;
  const scheduleTrack = collapsed.schedule ? `${PANEL_HEAD_H}px` : `${layout.scheduleH}fr`;
  const tablesTrack = collapsed.tables ? `${PANEL_HEAD_H}px` : `${layout.tablesH}fr`;
  const copilotW = collapsed.copilot ? COPILOT_HEAD_W : layout.copilotW;

  // Hide the resizer track when either neighbor is collapsed.
  const mapScheduleResizerH = collapsed.map || collapsed.schedule ? 0 : 4;
  const scheduleTablesResizerH =
    collapsed.schedule || collapsed.tables ? 0 : 4;
  const colResizerW = collapsed.copilot ? 0 : 4;

  return (
    <>
      <TopBar
        scenario={scenario}
        scenarioId={scenarioId}
        instances={instances}
        onPickScenario={pickScenario}
        health={healthSummary}
      />
      <div
        className="main"
        style={{
          gridTemplateColumns: `1fr ${colResizerW}px ${copilotW}px`,
        }}
      >
        <div
          className="main-left"
          style={{
            gridTemplateRows: `${mapTrack} ${mapScheduleResizerH}px ${scheduleTrack} ${scheduleTablesResizerH}px ${tablesTrack}`,
          }}
        >

          <div className={'panel' + (collapsed.map ? ' collapsed' : '')}>
            <div className="panel-head" onDoubleClick={() => maximizePanel('map')}>
              <span className="title">
                {isOBJ ? 'Solution · Summary' : 'Network · Map'}
              </span>
              <span style={{ color: 'var(--text-faint)' }}>
                {scenario ? scenario.scenario_id : scenarioId ?? ''}
              </span>
              <span className="spacer" />
              {loadError && (
                <span style={{ color: 'var(--late)' }}>{loadError}</span>
              )}
              {scenarioError && !loadError && (
                <span style={{ color: 'var(--late)' }}>{scenarioError}</span>
              )}
              {scenario && !isOBJ && !collapsed.map && (
                <LensSwitch lens={lens} setLens={setLens} />
              )}
              <CollapseToggle
                collapsed={collapsed.map}
                onToggle={() => toggleCollapse('map')}
              />
            </div>
            <div className="panel-body">
              <MapPanel
                scenario={scenario}
                selection={selection}
                setSelection={setSelection}
                lens={lens}
                diffData={diffData}
              />
            </div>
          </div>

          {!collapsed.map && !collapsed.schedule && (
            <RowResizer onResize={resizeMapVsSchedule} />
          )}
          {(collapsed.map || collapsed.schedule) && <div />}

          <div className={'panel' + (collapsed.schedule ? ' collapsed' : '')}>
            <div className="panel-head" onDoubleClick={() => maximizePanel('schedule')}>
              <span className="title">Schedule · Gantt</span>
              <span style={{ color: 'var(--text-faint)' }}>solomon-minutes</span>
              <span className="spacer" />
              <span className="legend">
                <span className="item">
                  <span
                    style={{
                      display: 'inline-block',
                      width: 16,
                      height: 8,
                      border: '1px solid var(--text-faint)',
                    }}
                  />
                  time_window
                </span>
                <span className="item">
                  <span
                    style={{
                      display: 'inline-block',
                      width: 8,
                      height: 8,
                      background: 'var(--ok)',
                      borderRadius: '50%',
                    }}
                  />
                  on time
                </span>
                <span className="item">
                  <span
                    style={{
                      display: 'inline-block',
                      width: 8,
                      height: 8,
                      background: 'var(--late)',
                      borderRadius: '50%',
                    }}
                  />
                  is_late
                </span>
              </span>
              {selection.kind !== 'none' && (
                <span style={{ color: 'var(--accent)', marginLeft: 12 }}>
                  ◉{' '}
                  {selection.kind === 'route'
                    ? selection.label ?? 'Route ' + (selection.idx + 1)
                    : selection.kind === 'customer'
                      ? 'C' + selection.id
                      : 'summary'}
                  <span
                    onClick={() => setSelection(NONE)}
                    style={{
                      marginLeft: 8,
                      cursor: 'pointer',
                      color: 'var(--text-faint)',
                    }}
                  >
                    clear ×
                  </span>
                </span>
              )}
              {scenario && scenario.available_fields.customer_schedule && !collapsed.schedule && (
                <LensSwitch lens={lens} setLens={setLens} />
              )}
              <CollapseToggle
                collapsed={collapsed.schedule}
                onToggle={() => toggleCollapse('schedule')}
              />
            </div>
            <div className="panel-body">
              <SchedulePanel
                scenario={scenario}
                selection={selection}
                setSelection={setSelection}
                lens={lens}
                diffData={diffData}
              />
            </div>
          </div>

          {!collapsed.schedule && !collapsed.tables && (
            <RowResizer onResize={resizeScheduleVsTables} />
          )}
          {(collapsed.schedule || collapsed.tables) && <div />}

          <div
            className={'panel' + (collapsed.tables ? ' collapsed' : '')}
            style={{ borderBottom: 'none' }}
          >
            <TablesPanel
              scenario={scenario}
              selection={selection}
              setSelection={setSelection}
              diffData={diffData}
              diffLoading={diffLoading}
              diffNotAvailable={diffNotAvailable}
              onLoadDiff={loadDiff}
              collapsed={collapsed.tables}
              onToggleCollapse={() => toggleCollapse('tables')}
              onMaximize={() => maximizePanel('tables')}
              tab={tablesTab}
              setTab={setTablesTab}
            />
          </div>
        </div>

        {!collapsed.copilot && <ColResizer onResize={resizeMainVsCopilot} />}
        {collapsed.copilot && <div />}

        <CopilotPanel
          scenarioId={scenarioId}
          scenario={scenario}
          selection={selection}
          setSelection={setSelection}
          setTablesTab={setTablesTab}
          collapsed={collapsed.copilot}
          onToggleCollapse={() => toggleCollapse('copilot')}
        />
      </div>
    </>
  );
}
