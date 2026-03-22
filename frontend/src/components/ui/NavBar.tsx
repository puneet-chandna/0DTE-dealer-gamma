/**
 * NavBar — Shared navigation bar across all pages.
 *
 * Industrial dark aesthetic with active page highlighting.
 */

'use client';

import { memo } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useMarketStatus } from '@/hooks/useMarketStatus';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import {
  BarChart3,
  LineChart,
  FlaskConical,
  Activity,
} from 'lucide-react';

const navItems = [
  { href: '/dashboard', label: 'Dashboard', icon: BarChart3 },
  { href: '/analytics', label: 'Analytics', icon: LineChart },
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

  const statusLabel = demoModeEnabled
    ? 'Demo'
    : marketStatus
      ? marketStatusLabel[marketStatus.status]
      : 'Checking';

  const statusTone = demoModeEnabled
    ? 'bg-amber-400'
    : marketStatus?.is_open
      ? 'bg-emerald-500'
      : 'bg-amber-400';

  return (
    <nav className="border-b border-zinc-800 bg-zinc-950/90 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
        {/* Logo / App Name */}
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/15 ring-1 ring-violet-500/30 transition-all group-hover:bg-violet-500/25 group-hover:ring-violet-500/50">
            <Activity className="h-4 w-4 text-violet-400" />
          </div>
          <span className="text-sm font-semibold tracking-tight text-zinc-200">
            0DTE GEX
          </span>
        </Link>

        {/* Page links */}
        <div className="flex items-center gap-1">
          {navItems.map(({ href, label, icon: Icon }) => {
            const isActive = pathname === href || pathname?.startsWith(href + '/');
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

        <div className="flex items-center gap-2">
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

          <div className="flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-900/80 px-3 py-1.5">
            <span className={cn('h-2 w-2 rounded-full', statusTone, marketStatus?.is_open && !demoModeEnabled && 'animate-pulse')} />
            <span className="text-xs text-zinc-400">{statusLabel}</span>
          </div>
        </div>
      </div>
    </nav>
  );
}

export const NavBar = memo(NavBarComponent);
