import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import type { Data, Layout } from 'plotly.js';
import type { RoutePolyline, VisualContext } from '../types';

interface Props {
  visual: VisualContext | null;
  loading: boolean;
  error: string | null;
}

const HIGHLIGHT_COLOR = '#a8221a';
const HIGHLIGHT_ROUTE_COLOR = '#a8221a';
const ROUTE_PALETTE = [
  '#2a5dbf',
  '#2f7a3c',
  '#a25b00',
  '#7c4eb1',
  '#3a8ea3',
  '#b15a83',
  '#5b7a35',
  '#925e1a',
  '#395f8a',
  '#8a3a3a',
  '#3a8a6e',
  '#6e3a8a',
];

function routeColor(routeIdx: number): string {
  return ROUTE_PALETTE[routeIdx % ROUTE_PALETTE.length];
}

function buildRouteTrace(
  route: RoutePolyline,
  highlightedRouteIdxs: Set<number>,
): Data {
  const isHighlighted = highlightedRouteIdxs.has(route.route_idx);
  const color = isHighlighted ? HIGHLIGHT_ROUTE_COLOR : routeColor(route.route_idx);
  const xs = route.points.map((p) => p.x);
  const ys = route.points.map((p) => p.y);
  const labels = route.points.map((p) =>
    p.kind === 'depot' ? 'depot' : `c${p.customer_id}`,
  );
  const label = route.route_label ?? `Route ${route.display_route_number ?? route.route_idx + 1}`;
  return {
    type: 'scatter',
    mode: 'lines',
    name: label,
    legendgroup: `route-${route.route_idx}`,
    x: xs,
    y: ys,
    text: labels,
    hovertemplate: `${label}<br>%{text}<br>(%{x:.1f}, %{y:.1f})<extra></extra>`,
    line: {
      color,
      width: isHighlighted ? 3.5 : 1.5,
    },
    opacity: isHighlighted || highlightedRouteIdxs.size === 0 ? 1 : 0.45,
  };
}

export function RouteMap({ visual, loading, error }: Props) {
  const data: Data[] = useMemo(() => {
    if (!visual) return [];
    const highlightedRouteIdxs = new Set(
      visual.highlighted_routes.map((r) => r.route_idx),
    );
    const highlightedCustomers = new Set(visual.highlighted_customers);

    const traces: Data[] = [];

    // 1. Customer scatter (skipping highlighted customers — they get a
    //    second trace with a larger marker on top).
    const baseCustomers = visual.customers.filter(
      (c) => !highlightedCustomers.has(c.customer_id),
    );
    if (baseCustomers.length > 0) {
      traces.push({
        type: 'scatter',
        mode: 'markers',
        name: 'customers',
        x: baseCustomers.map((c) => c.x),
        y: baseCustomers.map((c) => c.y),
        text: baseCustomers.map((c) => `c${c.customer_id}`),
        hovertemplate:
          '%{text}<br>(%{x:.1f}, %{y:.1f})<br>demand=%{customdata[0]}<br>tw=[%{customdata[1]}, %{customdata[2]}]<extra></extra>',
        customdata: baseCustomers.map((c) => [c.demand, c.tw_early, c.tw_late]),
        marker: { size: 6, color: '#888' },
      });
    }

    // 2. Route polylines (highlighted ones drawn last so they appear on top).
    const nonHighlightedRoutes = visual.routes.filter(
      (r) => !highlightedRouteIdxs.has(r.route_idx),
    );
    const highlightedRoutes = visual.routes.filter((r) =>
      highlightedRouteIdxs.has(r.route_idx),
    );
    for (const r of nonHighlightedRoutes) {
      traces.push(buildRouteTrace(r, highlightedRouteIdxs));
    }
    for (const r of highlightedRoutes) {
      traces.push(buildRouteTrace(r, highlightedRouteIdxs));
    }

    // 3. Depot marker.
    if (visual.depot) {
      traces.push({
        type: 'scatter',
        mode: 'text+markers',
        name: 'depot',
        x: [visual.depot.x],
        y: [visual.depot.y],
        text: ['depot'],
        textposition: 'top center',
        hovertemplate: 'depot<br>(%{x:.1f}, %{y:.1f})<extra></extra>',
        marker: {
          symbol: 'square',
          size: 12,
          color: '#1a1d22',
          line: { width: 1, color: '#fff' },
        },
      });
    }

    // 4. Highlighted customers as a distinct trace.
    const highlightedCustList = visual.customers.filter((c) =>
      highlightedCustomers.has(c.customer_id),
    );
    if (highlightedCustList.length > 0) {
      traces.push({
        type: 'scatter',
        mode: 'text+markers',
        name: 'highlighted',
        x: highlightedCustList.map((c) => c.x),
        y: highlightedCustList.map((c) => c.y),
        text: highlightedCustList.map((c) => `c${c.customer_id}`),
        textposition: 'top center',
        hovertemplate:
          '%{text} (highlighted)<br>(%{x:.1f}, %{y:.1f})<br>demand=%{customdata[0]}<br>tw=[%{customdata[1]}, %{customdata[2]}]<extra></extra>',
        customdata: highlightedCustList.map((c) => [
          c.demand,
          c.tw_early,
          c.tw_late,
        ]),
        marker: {
          symbol: 'star',
          size: 14,
          color: HIGHLIGHT_COLOR,
          line: { width: 1, color: '#fff' },
        },
      });
    }

    return traces;
  }, [visual]);

  const layout = useMemo<Partial<Layout>>(() => {
    return {
      autosize: true,
      height: 480,
      margin: { l: 40, r: 16, t: 28, b: 40 },
      showlegend: true,
      legend: { font: { size: 10 } },
      xaxis: {
        title: { text: 'x', font: { size: 11 } },
        scaleanchor: 'y' as const,
        scaleratio: 1,
        zeroline: false,
      },
      yaxis: {
        title: { text: 'y', font: { size: 11 } },
        zeroline: false,
      },
      title: {
        text: 'Synthetic Euclidean coordinates — not a geographic map.',
        font: { size: 11, color: '#5b6470' },
        x: 0.02,
        xanchor: 'left',
      },
    };
  }, []);

  if (loading) {
    return (
      <section className="panel">
        <h2>Route map</h2>
        <p className="loading">Loading visual context…</p>
      </section>
    );
  }
  if (error) {
    return (
      <section className="panel">
        <h2>Route map</h2>
        <p className="error-message">{error}</p>
      </section>
    );
  }
  if (!visual) {
    return (
      <section className="panel">
        <h2>Route map</h2>
        <p className="loading">Select a prompt to view its route map.</p>
      </section>
    );
  }

  const hasGeometry = visual.depot != null || visual.customers.length > 0;

  return (
    <section className="panel">
      <h2>
        Route map — instance {visual.instance_id ?? '—'}
        {visual.routes.length > 0 && ` · ${visual.routes.length} routes`}
      </h2>
      <p className="panel-note">
        {visual.coordinate_note ?? visual.coordinate_system}
      </p>
      {!hasGeometry ? (
        <p className="error-message">
          Instance geometry unavailable for this prompt.
        </p>
      ) : (
        <Plot
          data={data}
          layout={layout}
          useResizeHandler
          style={{ width: '100%', height: 480 }}
          config={{ displaylogo: false, responsive: true }}
        />
      )}
      {visual.limitations.length > 0 && (
        <ul className="tight" style={{ marginTop: 8 }}>
          {visual.limitations.map((l, i) => (
            <li key={i} style={{ color: 'var(--warn)' }}>
              {l}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
