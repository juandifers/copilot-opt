// Tiny chevron button used in panel headers to collapse/expand.
// For row panels (Map / Schedule / Tables): ▾ expanded, ▸ collapsed (click to expand).
// For the Copilot column: ▸ expanded (chevron points right = collapse-to-right), ◂ collapsed.
import type React from 'react';

interface Props {
  collapsed: boolean;
  onToggle: () => void;
  orientation?: 'row' | 'col';
}

export function CollapseToggle({ collapsed, onToggle, orientation = 'row' }: Props) {
  const icon =
    orientation === 'row'
      ? collapsed
        ? '▸'
        : '▾'
      : collapsed
        ? '◂'
        : '▸';
  function handle(e: React.MouseEvent) {
    e.stopPropagation();
    onToggle();
  }
  return (
    <button
      className="collapse-toggle"
      onClick={handle}
      title={collapsed ? 'Expand' : 'Collapse'}
      aria-label={collapsed ? 'Expand panel' : 'Collapse panel'}
    >
      {icon}
    </button>
  );
}
