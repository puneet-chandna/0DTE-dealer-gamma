import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { NavBar } from './NavBar';

const storeState = vi.hoisted(() => ({
  state: {
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
  usePathname: () => '/analytics',
}));

vi.mock('@/hooks/useMarketStatus', () => ({
  useMarketStatus: () => ({
    data: {
      is_open: false,
      status: 'closed_weekend',
    },
  }),
}));

vi.mock('@/stores/uiStore', () => ({
  useUIStore: () => storeState.state,
}));

vi.mock('@/components/ui/ProviderSelector', () => ({
  ProviderSelector: () => <div>Provider Selector</div>,
}));

describe('NavBar mobile menu', () => {
  beforeEach(() => {
    storeState.state = {
      demoModeEnabled: false,
      toggleDemoMode: vi.fn(),
    };
  });

  it('keeps compact controls behind a mobile menu until the user opens it', () => {
    render(<NavBar />);

    expect(screen.getByRole('button', { name: /open navigation menu/i })).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: /mobile navigation/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /open navigation menu/i }));

    const mobileNav = screen.getByRole('dialog', { name: /mobile navigation/i });
    expect(mobileNav).toBeInTheDocument();
    expect(screen.getAllByText('Provider Selector')).toHaveLength(2);
    expect(screen.getAllByRole('link', { name: /dealer flows/i }).length).toBeGreaterThanOrEqual(1);
  });
});
