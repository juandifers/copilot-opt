// Thin drag handles between panels.
// Vertical handle (row-resize) and horizontal handle (col-resize).
// Caller receives the live mouse delta and decides whether/how to apply it
// (typically updating two adjacent panel sizes with clamping).
import type React from 'react';

type Direction = 'row' | 'col';

function startDrag(
  e: React.MouseEvent,
  direction: Direction,
  onResize: (delta: number) => void,
) {
  e.preventDefault();
  const isRow = direction === 'row';
  let last = isRow ? e.clientY : e.clientX;
  const cursor = isRow ? 'row-resize' : 'col-resize';

  function move(ev: MouseEvent) {
    const now = isRow ? ev.clientY : ev.clientX;
    const delta = now - last;
    last = now;
    onResize(delta);
  }
  function up() {
    document.removeEventListener('mousemove', move);
    document.removeEventListener('mouseup', up);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }
  document.body.style.cursor = cursor;
  document.body.style.userSelect = 'none';
  document.addEventListener('mousemove', move);
  document.addEventListener('mouseup', up);
}

export function RowResizer({ onResize }: { onResize: (dy: number) => void }) {
  return (
    <div
      className="row-resizer"
      onMouseDown={(e) => startDrag(e, 'row', onResize)}
      title="Drag to resize"
    />
  );
}

export function ColResizer({ onResize }: { onResize: (dx: number) => void }) {
  return (
    <div
      className="col-resizer"
      onMouseDown={(e) => startDrag(e, 'col', onResize)}
      title="Drag to resize"
    />
  );
}
