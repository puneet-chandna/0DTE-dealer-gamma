import { act, render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AppShellEffects } from './AppShellEffects';
import { useUIStore } from '@/stores/uiStore';

vi.mock('@/hooks/useProviders', () => ({
  useProviders: vi.fn(),
}));

vi.mock('@/components/ui/MarketStatusAlert', () => ({
  MarketStatusAlert: () => <div data-testid="market-status-alert" />,
}));

const defaultUIState = {
  isSidebarOpen: true,
  alertThreshold: 1.0,
  selectedDate: null,
  selectedProvider: 'yfinance' as const,
  availableProviders: [],
  activeDefaultProvider: 'yfinance' as const,
  showCallGex: true,
  showPutGex: true,
  showNetGex: true,
  isDarkMode: false,
  autoRefreshEnabled: true,
  refreshInterval: 30,
  demoModeEnabled: false,
};

function renderWithQueryClient() {
  const queryClient = new QueryClient();

  return render(
    <QueryClientProvider client={queryClient}>
      <AppShellEffects />
    </QueryClientProvider>
  );
}

describe('AppShellEffects theme sync', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    document.documentElement.classList.remove('dark');
    document.documentElement.style.colorScheme = '';
    useUIStore.setState(defaultUIState);
  });

  it('applies the current light theme preference to the document root', async () => {
    renderWithQueryClient();

    await waitFor(() => {
      expect(document.documentElement).toHaveAttribute('data-theme', 'light');
    });

    expect(document.documentElement).not.toHaveClass('dark');
    expect(document.documentElement.style.colorScheme).toBe('light');
  });

  it('updates the document root when dark mode is toggled', async () => {
    renderWithQueryClient();

    act(() => {
      useUIStore.getState().toggleDarkMode();
    });

    await waitFor(() => {
      expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
    });

    expect(document.documentElement).toHaveClass('dark');
    expect(document.documentElement.style.colorScheme).toBe('dark');
  });
});
