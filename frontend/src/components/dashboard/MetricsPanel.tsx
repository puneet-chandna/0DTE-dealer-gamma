/**
 * MetricsPanel - Detailed GEX breakdown metrics
 */

'use client';

import { memo } from 'react';
import { TrendingUp, TrendingDown, Target, Crosshair } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatGEX, formatCurrency } from '@/lib/utils';
import { Card, CardHeader, CardContent, CardTitle, Skeleton } from '@/components/ui';
import type { GEXSnapshot } from '@/types';

interface MetricsPanelProps {
  data?: GEXSnapshot | null;
  isLoading?: boolean;
}

interface MetricRowProps {
  label: string;
  value: string;
  icon?: React.ReactNode;
  color?: 'default' | 'positive' | 'negative';
}

function MetricRow({ label, value, icon, color = 'default' }: MetricRowProps) {
  const colorClass =
    color === 'positive'
      ? 'text-emerald-400'
      : color === 'negative'
        ? 'text-rose-400'
        : 'text-zinc-50';

  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex items-center gap-2 text-sm text-zinc-400">
        {icon}
        {label}
      </div>
      <span className={cn('text-sm font-semibold', colorClass)}>{value}</span>
    </div>
  );
}

function MetricsPanelComponent({ data, isLoading = false }: MetricsPanelProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Metrics</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="flex justify-between py-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-20" />
            </div>
          ))}
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Metrics</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-zinc-500">No data available</p>
        </CardContent>
      </Card>
    );
  }

  // Calculate derived metrics
  const callGexBillions = data.total_call_gex / 1e9;
  const putGexBillions = data.total_put_gex / 1e9;
  const netGexBillions = data.net_gex / 1e9;

  // Distance from spot to zero gamma
  const distanceToZeroGamma = data.zero_gamma_level - data.spot_price;
  const distancePercent = (distanceToZeroGamma / data.spot_price) * 100;


  return (
    <Card>
      <CardHeader>
        <CardTitle>GEX Breakdown</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="divide-y divide-zinc-800">
          <MetricRow
            label="Call GEX"
            value={formatGEX(data.total_call_gex)}
            icon={<TrendingDown className="h-3.5 w-3.5 text-rose-400" />}
            color="negative"
          />
          <MetricRow
            label="Put GEX"
            value={formatGEX(data.total_put_gex)}
            icon={<TrendingUp className="h-3.5 w-3.5 text-emerald-400" />}
            color="positive"
          />
          <MetricRow
            label="Net GEX"
            value={formatGEX(data.net_gex)}
            icon={<Target className="h-3.5 w-3.5" />}
            color={netGexBillions < 0 ? 'negative' : 'positive'}
          />
          <MetricRow
            label="Zero Gamma"
            value={formatCurrency(data.zero_gamma_level, 0)}
            icon={<Crosshair className="h-3.5 w-3.5 text-violet-400" />}
          />
          <MetricRow
            label="Distance to 0Γ"
            value={`${distanceToZeroGamma >= 0 ? '+' : ''}${formatCurrency(distanceToZeroGamma, 0)} (${distancePercent.toFixed(2)}%)`}
            color={distanceToZeroGamma >= 0 ? 'positive' : 'negative'}
          />
          <MetricRow
            label="Dominant Strike"
            value={formatCurrency(data.dominant_strike, 0)}
          />
          <MetricRow
            label="Spot Price"
            value={formatCurrency(data.spot_price, 2)}
          />
        </div>

        {/* Ratio visualization */}
        <div className="mt-4">
          <div className="mb-1 flex justify-between text-xs text-zinc-500">
            <span>Call/Put Ratio</span>
            <span>
              {(Math.abs(callGexBillions) / (Math.abs(putGexBillions) || 1)).toFixed(2)}
            </span>
          </div>
          <div className="flex h-2 overflow-hidden rounded-full bg-zinc-800">
            <div
              className="bg-rose-500 transition-all duration-300"
              style={{
                width: `${
                  (Math.abs(callGexBillions) /
                    (Math.abs(callGexBillions) + Math.abs(putGexBillions) || 1)) *
                  100
                }%`,
              }}
            />
            <div
              className="bg-emerald-500 transition-all duration-300"
              style={{
                width: `${
                  (Math.abs(putGexBillions) /
                    (Math.abs(callGexBillions) + Math.abs(putGexBillions) || 1)) *
                  100
                }%`,
              }}
            />
          </div>
          <div className="mt-1 flex justify-between text-xs">
            <span className="text-rose-400">Calls</span>
            <span className="text-emerald-400">Puts</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export const MetricsPanel = memo(MetricsPanelComponent);
