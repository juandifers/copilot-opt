// Error boundary: contains a render-time crash to a single subtree instead of
// letting React unmount the whole app (which blanks the operator console).
// A malformed copilot response should degrade to an inline notice, not a
// black screen. See https://reactjs.org/link/error-boundaries.
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  /** Short label for what failed, shown in the fallback (e.g. "Copilot"). */
  label?: string;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Keep the detail in the console for debugging; the UI stays calm.
    console.error('[ErrorBoundary]', this.props.label ?? 'subtree', error, info);
  }

  private reset = (): void => this.setState({ error: null });

  render(): ReactNode {
    if (this.state.error) {
      const what = this.props.label ?? 'This panel';
      return (
        <div className="error-boundary" role="alert">
          <div className="error-boundary-title">{what} hit a snag.</div>
          <div className="error-boundary-detail">{this.state.error.message}</div>
          <button type="button" className="error-boundary-retry" onClick={this.reset}>
            Dismiss
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
