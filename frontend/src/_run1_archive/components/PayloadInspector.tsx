import type { ProductCopilotResponse } from '../types';

interface Props {
  context: ProductCopilotResponse | null;
}

type Dict = Record<string, unknown>;

function isDict(x: unknown): x is Dict {
  return typeof x === 'object' && x !== null && !Array.isArray(x);
}

function topLevelFields(p: Dict): string[] {
  return Object.keys(p).sort();
}

interface RoutePreviewRow {
  route_idx: unknown;
  route_label: unknown;
  display_route_number: unknown;
  customers: number;
}

function routeRows(payload: Dict): RoutePreviewRow[] {
  const routes = payload.routes;
  if (!Array.isArray(routes)) return [];
  return routes.map((r) => {
    const route = isDict(r) ? r : {};
    const customers = Array.isArray(route.customer_ids)
      ? route.customer_ids.length
      : 0;
    return {
      route_idx: route.route_idx ?? '—',
      route_label: route.route_label ?? '—',
      display_route_number: route.display_route_number ?? '—',
      customers,
    };
  });
}

function arrayLen(payload: Dict, key: string): number | null {
  const v = payload[key];
  return Array.isArray(v) ? v.length : null;
}

export function PayloadInspector({ context }: Props) {
  if (!context) {
    return (
      <section className="panel">
        <h2>Payload</h2>
        <p className="loading">Select a prompt to view payload.</p>
      </section>
    );
  }

  const payload = context.payload_augmented;
  if (!payload || !isDict(payload)) {
    return (
      <section className="panel">
        <h2>Payload</h2>
        <p className="loading">No augmented payload available.</p>
      </section>
    );
  }

  const fields = topLevelFields(payload);
  const routes = routeRows(payload);
  const scheduleN = arrayLen(payload, 'customer_schedule');
  const routeEndN = arrayLen(payload, 'route_end_times');

  return (
    <section className="panel">
      <h2>Payload (augmented)</h2>
      <div className="payload-summary">
        <strong>Top-level fields:</strong>{' '}
        {fields.map((f) => (
          <code key={f} style={{ marginRight: 4 }}>
            {f}
          </code>
        ))}
      </div>

      {routes.length > 0 && (
        <>
          <h3>Routes ({routes.length})</h3>
          <table className="route-preview-table">
            <thead>
              <tr>
                <th>route_idx</th>
                <th>display</th>
                <th>route_label</th>
                <th>customers</th>
              </tr>
            </thead>
            <tbody>
              {routes.map((r, i) => (
                <tr key={i}>
                  <td className="num">{String(r.route_idx)}</td>
                  <td className="num">{String(r.display_route_number)}</td>
                  <td>{String(r.route_label)}</td>
                  <td className="num">{r.customers}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {scheduleN != null && (
        <div className="payload-summary" style={{ marginTop: 6 }}>
          <strong>customer_schedule:</strong> {scheduleN} entries
        </div>
      )}
      {routeEndN != null && (
        <div className="payload-summary">
          <strong>route_end_times:</strong> {routeEndN} entries
        </div>
      )}

      <details className="payload-tree" style={{ marginTop: 8 }}>
        <summary>Full JSON ({fields.length} top-level keys)</summary>
        <pre className="json-block">{JSON.stringify(payload, null, 2)}</pre>
      </details>
    </section>
  );
}
