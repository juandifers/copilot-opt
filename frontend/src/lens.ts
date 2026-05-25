// Lens overlay: alternative coloring modes for Map pins and Schedule arrival dots.
// 'route' is the default — pins follow their assigned route color.
// 'lateness' highlights how late each stop is.
// 'slack' highlights how much spare time each stop has before its TW closes.

export type LensMode = 'route' | 'lateness' | 'slack';

export const LENS_LABELS: Record<LensMode, string> = {
  route: 'route',
  lateness: 'lateness',
  slack: 'slack',
};

export interface LensInput {
  routeColor: string;
  isLate: boolean;
  lateness: number; // sm; 0 if not late
  slack: number | null; // sm; tw_end - arrival; null if unknown
}

export function lensColor(mode: LensMode, x: LensInput): string {
  if (mode === 'route') return x.routeColor;
  if (mode === 'lateness') {
    if (!x.isLate || x.lateness <= 0) return 'var(--text-faint)';
    const t = Math.min(1, x.lateness / 30);
    const light = 70 - 30 * t;
    return `hsl(0, 75%, ${light}%)`;
  }
  // slack
  if (x.slack == null) return 'var(--text-faint)';
  if (x.slack < 0) return '#d63232';
  if (x.slack < 30) return '#e07a7a';
  if (x.slack < 90) return '#f0a92e';
  if (x.slack < 200) return '#e8c44f';
  return '#7cd47a';
}

export const SLACK_LEGEND: Array<{ color: string; label: string }> = [
  { color: '#d63232', label: '< 0 (already late)' },
  { color: '#e07a7a', label: '< 30 sm' },
  { color: '#f0a92e', label: '< 90 sm' },
  { color: '#e8c44f', label: '< 200 sm' },
  { color: '#7cd47a', label: '≥ 200 sm' },
];

export const LATENESS_LEGEND: Array<{ color: string; label: string }> = [
  { color: 'var(--text-faint)', label: 'on time' },
  { color: 'hsl(0, 75%, 60%)', label: '~ 10 sm late' },
  { color: 'hsl(0, 75%, 50%)', label: '~ 20 sm late' },
  { color: 'hsl(0, 75%, 40%)', label: '≥ 30 sm late' },
];
