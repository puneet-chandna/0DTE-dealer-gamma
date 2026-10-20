import { fireEvent, render, screen } from '@testing-library/react';
import type { AnchorHTMLAttributes, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NavBar } from './NavBar';
const { state, invalidateQueries } = vi.hoisted(() => ({
  state: { demoModeEnabled: false, toggleDemoMode: vi.fn(), autoRefreshEnabled: true, setAutoRefresh: vi.fn() },
  invalidateQueries: vi.fn(),
}));
vi.mock('next/link', () => ({ default: ({ children, href, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { children: ReactNode; href: string }) => <a href={href} {...props}>{children}</a> }));
vi.mock('next/navigation', () => ({ usePathname: () => '/analytics' }));
vi.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries }) }));
vi.mock('@/hooks/useMarketStatus', () => ({ useMarketStatus: () => ({ data: { is_open: false, status: 'closed_weekend', next_open: 'Monday 9:30 AM ET' } }) }));
vi.mock('@/stores/uiStore', () => ({ useUIStore: () => state }));
vi.mock('./ProviderSelector', () => ({ ProviderSelector: () => <label>Data provider<select aria-label="Data provider"><option>Yahoo Finance</option></select></label> }));
describe('shared desktop research navigation', () => {
  beforeEach(() => vi.clearAllMocks());
  it('identifies current page and toggle state without duplicate mobile navigation', () => {
    render(<NavBar />);
    expect(screen.getByRole('link', { name: 'Analytics' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: 'Demo' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Auto poll' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('button', { name: /theme|navigation menu/i })).not.toBeInTheDocument();
    expect(screen.getByText('US session closed')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Demo' }));
    expect(state.toggleDemoMode).toHaveBeenCalledOnce();
  });
  it('refreshes data independently from market-session status', () => {
    const refresh = vi.fn();
    render(<NavBar onRefresh={refresh} isRealtime connectionState="connected" />);
    expect(screen.getByText('Stream connected')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh data' }));
    expect(refresh).toHaveBeenCalledOnce();
  });
});
