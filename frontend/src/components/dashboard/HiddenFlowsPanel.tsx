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

function FlowEstimate({
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

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-sm font-medium text-[var(--text-primary)]">{label}</span>
        </div>
        <span
          className={cn(
            'text-sm font-bold tabular-nums',
            isPositive ? 'text-[var(--positive)]' : 'text-[var(--negative)]'
          )}
        >
          {isPositive ? '+' : '−'}${formatFlow(Math.abs(value))}
        </span>
      </div>

      <p className="text-sm text-[var(--text-secondary)]">{description}</p>
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
          <p className="text-sm text-[var(--text-secondary)]">
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
              'rounded-md px-2 py-0.5 text-sm font-medium',
              netIsPositive
                ? 'bg-emerald-900/50 text-emerald-300'
                : 'bg-rose-900/50 text-rose-300'
            )}
          >
            {data.net_hidden_flow === 0 ? 'No net adjustment' : netIsPositive ? 'Buy scenario' : 'Sell scenario'}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <FlowEstimate
          label="Charm Flow"
          value={data.charm_flow}
          icon={<Clock className="h-4 w-4 text-amber-400" />}
          description="Hedging pressure from time decay (30 min forward)"
        />

        <FlowEstimate
          label="Vanna Flow"
          value={data.vanna_flow}
          icon={<Waves className="h-4 w-4 text-sky-400" />}
          description="Hedge notional if IV drops 1 percentage point"
        />

        <div className="border-t border-[var(--stroke)] pt-3">
          <FlowEstimate
            label="Net Hidden Flow"
            value={data.net_hidden_flow}
            icon={<ArrowUpDown className="h-4 w-4 text-violet-400" />}
            description="Combined fixed-spot scenarios; not observed orders"
          />
        </div>
      </CardContent>
    </Card>
  );
}

export const HiddenFlowsPanel = memo(HiddenFlowsPanelComponent);
