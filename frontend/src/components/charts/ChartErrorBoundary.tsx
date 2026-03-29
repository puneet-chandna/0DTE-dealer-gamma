/**
 * ChartErrorBoundary - Error boundary for chart components
 *
 * Keep chart rendering isolated so a chart failure does not break the page.
 */

'use client';

import { Component, type ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ChartErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  chartName?: string;
  onReset?: () => void;
}

interface ChartErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ChartErrorBoundary extends Component<
  ChartErrorBoundaryProps,
  ChartErrorBoundaryState
> {
  constructor(props: ChartErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ChartErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('Chart rendering error:', error, errorInfo);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-4 rounded-lg border border-rose-500/20 bg-rose-500/5 p-6">
          <AlertTriangle className="h-8 w-8 text-rose-500" />
          <div className="text-center">
            <h3 className="font-medium text-rose-400">
              {this.props.chartName
                ? `${this.props.chartName} Error`
                : 'Chart Error'}
            </h3>
            <p className="mt-1 text-sm text-zinc-500">
              Failed to render chart. Please try again.
            </p>
            {this.state.error && (
              <pre className="mt-2 max-w-xs overflow-auto rounded bg-zinc-900 p-2 text-xs text-zinc-400">
                {this.state.error.message}
              </pre>
            )}
          </div>
          <button
            onClick={this.handleReset}
            className="inline-flex items-center gap-2 rounded-md bg-zinc-800 px-3 py-1.5 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-700"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retry
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
