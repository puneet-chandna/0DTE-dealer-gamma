/**
 * NavBar — Shared navigation bar across all pages.
 *
 * Industrial dark aesthetic with active page highlighting.
 */

'use client';

import { memo, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useMarketStatus } from '@/hooks/useMarketStatus';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { ProviderSelector } from '@/components/ui/ProviderSelector';
import {
  BarChart3,
  LineChart,
  FlaskConical,
  Activity,
  Waves,
  Menu,
  X,
} from 'lucide-react';

const navItems = [
  { href: '/dashboard', label: 'Dashboard', icon: BarChart3 },
  { href: '/analytics', label: 'Analytics', icon: LineChart },
  { href: '/dealer-flows', label: 'Dealer Flows', icon: Waves },
  { href: '/backtest', label: 'Backtest', icon: FlaskConical },
] as const;

const marketStatusLabel = {
  open: 'Open',
  pre_market: 'Pre-Market',
  after_hours: 'After Hours',
  closed_weekend: 'Weekend',
} as const;

function NavBarComponent() {
  const pathname = usePathname();
  const { demoModeEnabled, toggleDemoMode } = useUIStore();
  const { data: marketStatus } = useMarketStatus();
  const currentPath = pathname ?? '/';
  const [mobileMenuState, setMobileMenuState] = useState(() => ({
    isOpen: false,
    path: currentPath,
  }));

  const statusLabel = demoModeEnabled
    ? 'Demo'
    : marketStatus
      ? marketStatusLabel[marketStatus.status] ?? 'Closed'
      : 'Checking';

  const statusTone = demoModeEnabled
    ? 'bg-amber-400'
    : marketStatus?.is_open
      ? 'bg-emerald-500'
      : 'bg-amber-400';
  const activeItem = navItems.find((item) => pathname === item.href || pathname?.startsWith(`${item.href}/`));
  const mobileMenuOpen =
    mobileMenuState.path === currentPath ? mobileMenuState.isOpen : false;

  const closeMobileMenu = () =>
    setMobileMenuState({
      isOpen: false,
      path: currentPath,
    });

  const toggleMobileMenu = () =>
    setMobileMenuState((state) => ({
      isOpen:
        state.path === currentPath ? !state.isOpen : true,
      path: currentPath,
    }));

  const statusPill = (
    <div className="flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-900/80 px-3 py-1.5">
      <span
        className={cn(
          'h-2 w-2 rounded-full',
          statusTone,
          marketStatus?.is_open && !demoModeEnabled && 'animate-pulse'
        )}
      />
      <span className="text-xs text-zinc-400">{statusLabel}</span>
    </div>
  );

  return (
    <nav className="border-b border-zinc-800 bg-zinc-950/90 backdrop-blur-sm">
      <div className="mx-auto max-w-[1600px] px-4 sm:px-6 xl:px-8">
        <div className="flex h-14 items-center justify-between gap-3 md:h-16">
          <Link href="/" className="group flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/15 ring-1 ring-violet-500/30 transition-all group-hover:bg-violet-500/25 group-hover:ring-violet-500/50">
              <Activity className="h-4 w-4 text-violet-400" />
            </div>
            <div className="min-w-0">
              <span className="block text-sm font-semibold tracking-tight text-zinc-200">
                0DTE GEX
              </span>
              <span className="hidden text-[11px] text-zinc-500 sm:block">
                {activeItem?.label ?? 'Dashboard'}
              </span>
            </div>
          </Link>

          <div className="hidden md:flex md:flex-1 md:items-center md:justify-center">
            <div className="flex items-center gap-1">
              {navItems.map(({ href, label, icon: Icon }) => {
                const isActive = pathname === href || pathname?.startsWith(`${href}/`);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={cn(
                      'flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200',
                      isActive
                        ? 'bg-violet-500/15 text-violet-300 ring-1 ring-violet-500/20'
                        : 'text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200'
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {label}
                  </Link>
                );
              })}
            </div>
          </div>

          <div className="hidden md:flex items-center gap-2">
            <ProviderSelector />

            <button
              type="button"
              onClick={toggleDemoMode}
              className={cn(
                'rounded-lg px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] transition-all',
                demoModeEnabled
                  ? 'bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30'
                  : 'bg-zinc-800/70 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
              )}
            >
              Demo
            </button>

            {statusPill}
          </div>

          <div className="flex items-center gap-2 md:hidden">
            <span className="rounded-full border border-zinc-800 bg-zinc-900/80 px-2.5 py-1 text-[11px] text-zinc-400">
              {activeItem?.label ?? 'Menu'}
            </span>
            <button
              type="button"
              aria-label={mobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
              aria-expanded={mobileMenuOpen}
              aria-controls="mobile-navigation"
              onClick={toggleMobileMenu}
              className="inline-flex items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/80 p-2 text-zinc-300 transition-colors hover:bg-zinc-800"
            >
              {mobileMenuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {mobileMenuOpen && (
          <div
            id="mobile-navigation"
            role="dialog"
            aria-label="Mobile navigation"
            className="border-t border-zinc-800 py-4 md:hidden"
          >
            <div className="space-y-4 rounded-2xl border border-zinc-800 bg-zinc-900/70 p-4 shadow-xl shadow-black/20">
              <div className="flex flex-wrap items-center gap-2">
                {statusPill}
                <button
                  type="button"
                  onClick={toggleDemoMode}
                  className={cn(
                    'rounded-lg px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] transition-all',
                    demoModeEnabled
                      ? 'bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30'
                      : 'bg-zinc-800/70 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
                  )}
                >
                  Demo
                </button>
              </div>

              <ProviderSelector />

              <div className="grid grid-cols-2 gap-2">
                {navItems.map(({ href, label, icon: Icon }) => {
                  const isActive = pathname === href || pathname?.startsWith(`${href}/`);
                  return (
                    <Link
                      key={href}
                      href={href}
                      onClick={closeMobileMenu}
                      className={cn(
                        'flex items-center gap-2 rounded-xl px-3 py-3 text-sm font-medium transition-all duration-200',
                        isActive
                          ? 'bg-violet-500/15 text-violet-300 ring-1 ring-violet-500/20'
                          : 'bg-zinc-950/70 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
                      )}
                    >
                      <Icon className="h-4 w-4" />
                      {label}
                    </Link>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
}

export const NavBar = memo(NavBarComponent);
