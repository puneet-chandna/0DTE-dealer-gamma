import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
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
});
