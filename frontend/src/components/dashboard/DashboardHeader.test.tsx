import { fireEvent, render, screen } from '@testing-library/react';
import { hydrateRoot } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import type { ReactNode } from 'react';
import { act } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DashboardHeader } from './DashboardHeader';

const storeState = vi.hoisted(() => ({
  state: {
    isDarkMode: false,
    toggleDarkMode: vi.fn(),
    autoRefreshEnabled: true,
    setAutoRefresh: vi.fn(),
    demoModeEnabled: false,
    toggleDemoMode: vi.fn(),
  },
}));

vi.mock('next/link', () => ({
  default: ({
    children,
    href,
    className,
  }: {
    children: ReactNode;
    href: string;
    className?: string;
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/dashboard',
}));

vi.mock('@/stores/uiStore', () => ({
  useUIStore: () => storeState.state,
}));

vi.mock('@/components/ui', () => ({
  Badge: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ConnectionStatus: () => <div>Connection Status</div>,
  ProviderSelector: () => <div>Provider Selector</div>,
}));

describe('DashboardHeader', () => {
  beforeEach(() => {
    storeState.state = {
      isDarkMode: false,
      toggleDarkMode: vi.fn(),
      autoRefreshEnabled: true,
      setAutoRefresh: vi.fn(),
      demoModeEnabled: false,
      toggleDemoMode: vi.fn(),
    };
  });

  it('renders the global demo toggle and wires it to the UI store', () => {
    render(<DashboardHeader />);

    const demoButton = screen.getByRole('button', { name: /demo/i });
    fireEvent.click(demoButton);

    expect(storeState.state.toggleDemoMode).toHaveBeenCalledTimes(1);
  });

  it('shows cross-page navigation links in the top header', () => {
    render(<DashboardHeader />);

    expect(screen.getByRole('link', { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /analytics/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /dealer flows/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /backtest/i })).toBeInTheDocument();
  });

  it('prioritizes the active connection state over a stale connected prop', () => {
    render(
      <DashboardHeader
        isConnected
        connectionState="connecting"
        retryCount={1}
      />
    );

    expect(screen.getByText(/connecting/i)).toBeInTheDocument();
    expect(screen.queryByText(/^connected$/i)).not.toBeInTheDocument();
  });

  it('shows a replay capture timestamp when one is provided', () => {
    render(
      <DashboardHeader
        captureTimestampLabel="Replay capture: Mar 27, 2026 3:34 PM ET"
      />
    );

    expect(screen.getByText(/replay capture: mar 27, 2026 3:34 pm et/i)).toBeInTheDocument();
  });

  it('avoids a hydration mismatch when the client theme differs from the server render', async () => {
    storeState.state = {
      ...storeState.state,
      isDarkMode: false,
    };

    const serverMarkup = renderToString(<DashboardHeader />);
    const container = document.createElement('div');
    container.innerHTML = serverMarkup;
    document.body.appendChild(container);

    storeState.state = {
      ...storeState.state,
      isDarkMode: true,
    };

    const recoverableErrors: Error[] = [];
    let root: ReturnType<typeof hydrateRoot> | undefined;

    await act(async () => {
      root = hydrateRoot(container, <DashboardHeader />, {
        onRecoverableError: (error) => {
          recoverableErrors.push(error);
        },
      });
    });

    expect(recoverableErrors).toEqual([]);

    await act(async () => {
      root?.unmount();
    });
    container.remove();
  });
});
