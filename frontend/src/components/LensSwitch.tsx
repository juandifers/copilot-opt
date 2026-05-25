// Compact lens-mode selector for Map and Schedule panel headers.
import type { LensMode } from '../lens';

interface Props {
  lens: LensMode;
  setLens: (l: LensMode) => void;
}

const MODES: LensMode[] = ['route', 'lateness', 'slack'];

export function LensSwitch({ lens, setLens }: Props) {
  return (
    <span className="lens-switch" title="Lens overlay">
      <span className="lens-label">lens</span>
      {MODES.map((m) => (
        <button
          key={m}
          className={'lens-btn' + (m === lens ? ' active' : '')}
          onClick={() => setLens(m)}
        >
          {m}
        </button>
      ))}
    </span>
  );
}
