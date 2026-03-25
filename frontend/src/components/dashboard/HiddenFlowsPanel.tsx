/**
 * HiddenFlowsPanel - Charm & Vanna dealer hidden flow visualization
 *
 * Shows the invisible structural forces acting on the market:
 * - Charm Flow: dealer hedging pressure from time decay
 * - Vanna Flow: dealer hedging pressure from IV changes
 * - Net Hidden Flow: combined effect
 */

'use client';

import { memo } from 'react';
import { Clock, Waves, ArrowUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui';
import type { CharmVannaSnapshot } from '@/types';

interface HiddenFlowsPanelProps {
  data?: CharmVannaSnapshot | null;
  isLoading?: boolean;
}

function formatFlow(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(0)}K`;
  return value.toFixed(0);
}

function FlowBar({
  label,
  value,
  icon,
  description,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  description: string;
}) {
  const isPositive = value >= 0;
  const barWidth = Math.min(100, Math.abs(value) / 1e8); // Scale: 100M = full bar

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-sm font-medium text-zinc-300">{label}</span>
        </div>
        <span
          className={cn(
            'text-sm font-bold tabular-nums',
            isPositive ? 'text-emerald-400' : 'text-rose-400'
          )}
        >
          {isPositive ? '+' : ''}${formatFlow(value)}
        </span>
      </div>

      {/* Flow bar */}
      <div className="relative h-2 overflow-hidden rounded-full bg-zinc-800">
        <div
          className={cn(
            'h-full rounded-full transition-all duration-700 ease-out',
            isPositive
              ? 'bg-gradient-to-r from-emerald-600 to-emerald-400'
              : 'bg-gradient-to-r from-rose-600 to-rose-400'
          )}
          style={{ width: `${Math.max(2, barWidth)}%` }}
        />
      </div>

      <p className="text-xs text-zinc-500">{description}</p>
    </div>
  );
}

function HiddenFlowsPanelComponent({ data, isLoading }: HiddenFlowsPanelProps) {
  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Hidden Flows</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-zinc-500">
            {isLoading ? 'Calculating hidden flows...' : 'Awaiting analytics data'}
          </p>
        </CardContent>
      </Card>
    );
  }

  const netIsPositive = data.net_hidden_flow >= 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Hidden Dealer Flows</CardTitle>
          <div
            className={cn(
              'rounded-md px-2 py-0.5 text-xs font-medium',
              netIsPositive
                ? 'bg-emerald-900/50 text-emerald-300'
                : 'bg-rose-900/50 text-rose-300'
            )}
          >
            {netIsPositive ? '▲ Dealers Buying' : '▼ Dealers Selling'}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <FlowBar
          label="Charm Flow"
          value={data.charm_flow}
          icon={<Clock className="h-4 w-4 text-amber-400" />}
          description="Hedging pressure from time decay (30 min forward)"
        />

        <FlowBar
          label="Vanna Flow"
          value={data.vanna_flow}
          icon={<Waves className="h-4 w-4 text-sky-400" />}
          description="Hedging pressure if IV drops 1%"
        />

        <div className="border-t border-zinc-800 pt-3">
          <FlowBar
            label="Net Hidden Flow"
            value={data.net_hidden_flow}
            icon={<ArrowUpDown className="h-4 w-4 text-violet-400" />}
            description="Combined Charm + Vanna pressure on the market"
          />
        </div>
      </CardContent>
    </Card>
  );
}

export const HiddenFlowsPanel = memo(HiddenFlowsPanelComponent);
