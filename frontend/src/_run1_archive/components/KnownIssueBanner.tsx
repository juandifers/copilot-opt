interface Props {
  promptId: string | null;
}

const NOTES: Record<string, { title: string; body: string }> = {
  '002': {
    title: 'Volunteered/risky comparison',
    body:
      'Probe metric flagged this answer for using comparison-style language ("more than", "compared to", etc.) whose payload referent may be ambiguous. The user did not request a comparison.',
  },
  '010': {
    title: 'Volunteered/risky comparison',
    body:
      'Probe metric flagged this answer for using comparison-style language. The user did not request a comparison.',
  },
  '025': {
    title: 'New-customer pathway',
    body:
      'Asks which route the newly inserted customer joined. The product layer needs new_customer_ids in the payload; without it, attribution is not possible.',
  },
  '029': {
    title: 'STRUCT membership + route indexing',
    body:
      'Single-customer route-membership claim. Also exhibits route-indexing convention drift (answer uses internal route_idx).',
  },
  '031': {
    title: 'STRUCT membership + route indexing',
    body:
      'Membership-style claim with route-indexing convention drift.',
  },
  '032': {
    title: 'Route indexing convention drift',
    body:
      'Answer references a route number that resolves under internal route_idx rather than the display convention (route_idx + 1).',
  },
  '033': {
    title: 'Unsupported before/after comparison',
    body:
      'User asked for a before/after comparison. The current payload does not carry baseline_solution or diff fields, so the comparison is not supported.',
  },
  '034': {
    title: 'Route indexing convention drift',
    body:
      'Answer references a route number that resolves under internal route_idx rather than the display convention.',
  },
  '035': {
    title: 'Unsupported before/after comparison',
    body:
      'User asked for a before/after comparison the payload cannot supply.',
  },
  '036': {
    title: 'Unsupported before/after comparison',
    body:
      'User asked for a before/after comparison the payload cannot supply.',
  },
  '040': {
    title: 'Route indexing convention',
    body:
      'Route-end-time question. Answer uses the display convention (Route N); the product layer exposes display_route_number alongside route_idx so this resolves cleanly.',
  },
  '041': {
    title: 'Route indexing convention',
    body:
      'Route-end-time question; display-label augmentation applies.',
  },
};

export function KnownIssueBanner({ promptId }: Props) {
  if (!promptId) return null;
  const info = NOTES[promptId];
  if (!info) return null;
  return (
    <section className="panel" style={{ borderLeft: '3px solid var(--warn)' }}>
      <h2>Known issue for prompt {promptId}</h2>
      <div>
        <strong>{info.title}</strong>
        <p style={{ margin: '4px 0 0', fontSize: '0.85rem' }}>{info.body}</p>
      </div>
    </section>
  );
}
