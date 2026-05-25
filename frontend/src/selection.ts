// Shared cross-panel selection state.
// The Schedule, Map, Tables, and Copilot panels all read/write this so a click
// in one surface (route, customer, evidence chip) highlights everywhere.

export type Selection =
  | { kind: 'none' }
  | { kind: 'route'; idx: number; label?: string }
  | { kind: 'customer'; id: number }
  | { kind: 'summary' };

export const NONE: Selection = { kind: 'none' };
