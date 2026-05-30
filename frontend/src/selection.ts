// Shared cross-panel selection state.
// The Schedule, Map, Tables, and Copilot panels all read/write this so a click
// in one surface (route, customer, evidence chip) highlights everywhere.

export type Selection =
  | { kind: 'none' }
  | { kind: 'route'; idx: number; label?: string }
  | { kind: 'customer'; id: number }
  | { kind: 'summary' };

export const NONE: Selection = { kind: 'none' };

// Multi-target highlight set, driven by Copilot visual_actions. Lives in
// parallel with Selection: click-driven UI still uses Selection (single
// target); intents like lateness_summary populate Highlights with every late
// stop. MapPanel / SchedulePanel check both with a union predicate.
export interface Highlights {
  routes: Set<number>;
  customers: Set<number>;
}

export const EMPTY_HIGHLIGHTS: Highlights = {
  routes: new Set<number>(),
  customers: new Set<number>(),
};

export function isRouteHighlighted(h: Highlights, routeIdx: number): boolean {
  return h.routes.has(routeIdx);
}

export function isCustomerHighlighted(h: Highlights, customerId: number): boolean {
  return h.customers.has(customerId);
}
