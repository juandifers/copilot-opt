// Shared striped empty-state used by panels with no data yet.
import type { ReactNode } from 'react';

interface Props {
  title: string;
  children?: ReactNode;
}

export function EmptyPanel({ title, children }: Props) {
  return (
    <div className="empty-panel">
      <div>
        <div className="ep-title">{title}</div>
        {children}
      </div>
    </div>
  );
}
