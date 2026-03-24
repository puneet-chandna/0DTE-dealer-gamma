import { fireEvent, render, screen } from '@testing-library/react';
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

vi.mock('@/stores/uiStore', () => ({
  useUIStore: () => storeState.state,
}));

vi.mock('@/components/ui', () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
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
});
