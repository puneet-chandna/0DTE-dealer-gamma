'use client';

import { memo } from 'react';
import { formatMarketTimestamp } from '@/lib/utils';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui';
import type { GEXSnapshot } from '@/types';

interface GammaDecayClockProps {
  data?: GEXSnapshot | null;
  isLoading?: boolean;
}

const SESSION_MINUTES = 390;

function GammaDecayClockComponent({ data, isLoading }: GammaDecayClockProps) {
  const capturedAt = data ? new Date(data.timestamp) : null;
  const validClock = capturedAt !== null && Number.isFinite(capturedAt.getTime());
  const parts = validClock ? new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York', hour: 'numeric', minute: 'numeric', second: 'numeric', hourCycle: 'h23', weekday: 'short',
  }).formatToParts(capturedAt) : [];
  const part = (type: string) => parts.find((item) => item.type === type)?.value;
  const clockMinutes = Number(part('hour')) * 60 + Number(part('minute')) + Number(part('second')) / 60;
  const remaining = 16 * 60 - clockMinutes;
  const weekday = part('weekday') !== 'Sat' && part('weekday') !== 'Sun';
  const inInterval = validClock && weekday && remaining > 0 && remaining <= SESSION_MINUTES;
  const factor = inInterval ? Math.sqrt(SESSION_MINUTES / remaining) : null;

  return (
    <Card>
      <CardHeader><CardTitle>Fixed-volatility ATM time factor</CardTitle></CardHeader>
      <CardContent className="space-y-5">
        {isLoading || !data ? <p className="text-sm text-[var(--text-secondary)]">{isLoading ? 'Loading snapshot clock…' : 'Awaiting GEX snapshot'}</p> : (
          <>
            <p className="text-sm text-[var(--text-secondary)]">Snapshot clock: {validClock ? formatMarketTimestamp(data.timestamp) : 'unavailable'}. Frozen to this capture.</p>
            <dl className="grid grid-cols-2 gap-6 border-y border-[var(--stroke)] py-4">
              <div>
                <dt className="text-sm text-[var(--text-secondary)]">Time to assumed close</dt>
                <dd className="mt-1 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">{inInterval ? remaining < 1 ? '<1m' : `${Math.floor(remaining / 60)}h ${Math.floor(remaining % 60)}m` : '—'}</dd>
              </div>
              <div>
                <dt className="text-sm text-[var(--text-secondary)]">ATM time factor vs 09:30 ET</dt>
                <dd className="mt-1 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">{factor !== null ? `${factor.toFixed(2)}×` : '—'}</dd>
              </div>
            </dl>
            {!inInterval && <p className="text-sm text-[var(--text-secondary)]">Outside illustration interval</p>}
            <div className="space-y-2 text-sm leading-6 text-[var(--text-secondary)]">
              <p>Assumed regular session: 09:30–16:00 ET on the capture date. Time factor = √(390 / minutes remaining), holding volatility fixed and the option at the money.</p>
              <p>This is a time-only illustration, not aggregate GEX, a risk calibration, or a forecast. The approximation is undefined at expiry; actual gamma also depends on spot, strike, volatility and inventory.</p>
              <p className="text-[var(--text-muted)]">Session-calendar limits: weekdays only; holidays, early closes and contract-specific expiries are not resolved.</p>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export const GammaDecayClock = memo(GammaDecayClockComponent);
