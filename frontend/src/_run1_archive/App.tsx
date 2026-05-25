import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  DEFAULT_RUN_ID,
  getCopilotContext,
  getHealth,
  getProductMetrics,
  getRunResults,
  getVisualContext,
} from './api/client';
import type {
  ProductCopilotResponse,
  ProductMetrics,
  RunResultRow,
  VisualContext,
} from './types';
import { ProductMetricsPanel } from './components/ProductMetricsPanel';
import { Sidebar } from './components/Sidebar';
import { ResultsTable } from './components/ResultsTable';
import { PromptDetail } from './components/PromptDetail';
import { EvidencePanel } from './components/EvidencePanel';
import { WarningPanel } from './components/WarningPanel';
import { KnownIssueBanner } from './components/KnownIssueBanner';
import { PayloadInspector } from './components/PayloadInspector';
import { DomainCards } from './components/DomainCards';
import { RouteMap } from './components/RouteMap';
import { RouteSequence } from './components/RouteSequence';
import { PerturbationPanel } from './components/PerturbationPanel';

type HealthState = 'unknown' | 'ok' | 'unreachable';

export interface FilterState {
  family: string;
  source: string;
  quadrant: string;
  action_taken: string;
  sufficiency_label: string;
  policy_decision: string;
  faithfulness_score: string;
  refusal: string;
}

const EMPTY_FILTERS: FilterState = {
  family: '',
  source: '',
  quadrant: '',
  action_taken: '',
  sufficiency_label: '',
  policy_decision: '',
  faithfulness_score: '',
  refusal: '',
};

function matchesFilter(row: RunResultRow, filters: FilterState): boolean {
  const checks: [keyof FilterState, unknown][] = [
    ['family', row.family],
    ['source', row.source],
    ['quadrant', row.quadrant],
    ['action_taken', row.action_taken],
    ['sufficiency_label', row.sufficiency_label],
    ['policy_decision', row.policy_decision],
  ];
  for (const [key, value] of checks) {
    const filterValue = filters[key];
    if (filterValue && String(value ?? '') !== filterValue) return false;
  }
  if (filters.faithfulness_score) {
    const score = row.faithfulness_score;
    if (filters.faithfulness_score === 'null' && score != null) return false;
    if (filters.faithfulness_score !== 'null' && String(score) !== filters.faithfulness_score) {
      return false;
    }
  }
  if (filters.refusal) {
    const refused =
      row.runner_refusal_detected === true || row.judge_refusal_detected === true;
    if (filters.refusal === 'refused' && !refused) return false;
    if (filters.refusal === 'not_refused' && refused) return false;
  }
  return true;
}

export default function App() {
  const [health, setHealth] = useState<HealthState>('unknown');

  const [results, setResults] = useState<RunResultRow[] | null>(null);
  const [resultsError, setResultsError] = useState<string | null>(null);

  const [metrics, setMetrics] = useState<ProductMetrics | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);

  const [selectedPromptId, setSelectedPromptId] = useState<string | null>('001');
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);

  const [context, setContext] = useState<ProductCopilotResponse | null>(null);
  const [contextLoading, setContextLoading] = useState<boolean>(false);
  const [contextError, setContextError] = useState<string | null>(null);

  const [visual, setVisual] = useState<VisualContext | null>(null);
  const [visualLoading, setVisualLoading] = useState<boolean>(false);
  const [visualError, setVisualError] = useState<string | null>(null);

  // ---- health ----
  useEffect(() => {
    let cancelled = false;
    const check = () => {
      getHealth()
        .then((res) => {
          if (cancelled) return;
          setHealth(res.status === 'ok' ? 'ok' : 'unreachable');
        })
        .catch(() => {
          if (!cancelled) setHealth('unreachable');
        });
    };
    check();
    const id = window.setInterval(check, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  // ---- run-level data (only when backend OK) ----
  useEffect(() => {
    if (health !== 'ok') return;
    let cancelled = false;
    getRunResults(DEFAULT_RUN_ID)
      .then((res) => {
        if (cancelled) return;
        setResults(res.rows);
        setResultsError(null);
      })
      .catch((err: Error) => {
        if (!cancelled) setResultsError(err.message);
      });
    getProductMetrics(DEFAULT_RUN_ID)
      .then((m) => {
        if (cancelled) return;
        setMetrics(m);
        setMetricsError(null);
      })
      .catch((err: Error) => {
        if (!cancelled) setMetricsError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [health]);

  // ---- visible rows after filtering ----
  const visibleRows = useMemo(() => {
    if (!results) return [];
    const filtered = results.filter((r) => matchesFilter(r, filters));
    return filtered.sort((a, b) => a.prompt_id.localeCompare(b.prompt_id));
  }, [results, filters]);

  // ---- keep selection consistent ----
  useEffect(() => {
    if (!results) return;
    const hasSelection =
      selectedPromptId && visibleRows.some((r) => r.prompt_id === selectedPromptId);
    if (!hasSelection) {
      setSelectedPromptId(visibleRows[0]?.prompt_id ?? null);
    }
  }, [results, visibleRows, selectedPromptId]);

  // ---- copilot context for the selected prompt ----
  useEffect(() => {
    if (!selectedPromptId || health !== 'ok') {
      setContext(null);
      return;
    }
    let cancelled = false;
    setContextLoading(true);
    setContextError(null);
    getCopilotContext(selectedPromptId, DEFAULT_RUN_ID)
      .then((res) => {
        if (cancelled) return;
        setContext(res);
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setContext(null);
          setContextError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) setContextLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedPromptId, health]);

  // ---- visual context (Stage 4) for the selected prompt ----
  useEffect(() => {
    if (!selectedPromptId || health !== 'ok') {
      setVisual(null);
      return;
    }
    let cancelled = false;
    setVisualLoading(true);
    setVisualError(null);
    getVisualContext(selectedPromptId, DEFAULT_RUN_ID)
      .then((res) => {
        if (cancelled) return;
        setVisual(res);
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setVisual(null);
          setVisualError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) setVisualLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedPromptId, health]);

  const clearFilters = useCallback(() => setFilters(EMPTY_FILTERS), []);

  const selectedRow =
    results?.find((r) => r.prompt_id === selectedPromptId) ?? null;

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>VRPTW Copilot — Run 1 Product Inspector</h1>
        <p className="subtitle">
          A product replay dashboard showing how Run 1 grounded answers map
          into evidence, answerability, warnings, and useful refusals.
        </p>
        <div className="status-row">
          <span
            className={`status-dot ${
              health === 'ok' ? 'ok' : health === 'unreachable' ? 'bad' : ''
            }`}
          />
          {health === 'unknown' && <span>checking backend…</span>}
          {health === 'ok' && <span>backend connected</span>}
          {health === 'unreachable' && (
            <span>
              backend not reachable — start with{' '}
              <span className="status-hint">
                uvicorn product.api.main:app --reload --port 8000
              </span>
            </span>
          )}
          <span style={{ marginLeft: 'auto' }}>run_id: {DEFAULT_RUN_ID}</span>
        </div>
      </header>

      <main className="app-main">
        <div className="left-column">
          <ProductMetricsPanel metrics={metrics} error={metricsError} />
          <Sidebar
            rows={results}
            filters={filters}
            onChange={setFilters}
            onClear={clearFilters}
          />
        </div>

        <div className="center-column">
          <ResultsTable
            rows={visibleRows}
            totalRows={results?.length ?? 0}
            error={resultsError}
            selectedPromptId={selectedPromptId}
            onSelect={setSelectedPromptId}
          />
          <PromptDetail
            promptId={selectedPromptId}
            row={selectedRow}
            context={context}
            loading={contextLoading}
            error={contextError}
          />
          <RouteMap
            visual={visual}
            loading={visualLoading}
            error={visualError}
          />
          <RouteSequence visual={visual} />
          <DomainCards context={context} />
        </div>

        <div className="right-column">
          <KnownIssueBanner promptId={selectedPromptId} />
          <PerturbationPanel visual={visual} />
          <WarningPanel context={context} />
          <EvidencePanel context={context} />
          <PayloadInspector context={context} />
        </div>
      </main>
    </div>
  );
}
