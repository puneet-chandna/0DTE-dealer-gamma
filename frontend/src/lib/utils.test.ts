/**
 * 0DTE GEX Frontend - Utils Tests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  formatNumber,
  formatGEX,
  formatCurrency,
  formatZeroGammaStatus,
  formatZeroGammaValue,
  formatPercent,
  getRegimeColor,
  getRegimeBackgroundColor,
  getCurrentMarketDateString,
  hasZeroGammaCrossing,
  isFutureMarketDate,
  isMarketOpen,
} from './utils';
import type { GEXSnapshot } from '@/types';

describe('formatNumber', () => {
  it('formats billions correctly', () => {
    expect(formatNumber(1e9)).toBe('1.00B');
    expect(formatNumber(2.5e9)).toBe('2.50B');
    expect(formatNumber(-1.5e9)).toBe('-1.50B');
  });

  it('formats millions correctly', () => {
    expect(formatNumber(1e6)).toBe('1.00M');
    expect(formatNumber(500e6)).toBe('500.00M');
    expect(formatNumber(-250e6)).toBe('-250.00M');
  });

  it('formats thousands correctly', () => {
    expect(formatNumber(1000)).toBe('1.00K');
    expect(formatNumber(50000)).toBe('50.00K');
    expect(formatNumber(-10000)).toBe('-10.00K');
  });

  it('formats small numbers without suffix', () => {
    expect(formatNumber(100)).toBe('100.00');
    expect(formatNumber(0)).toBe('0.00');
    expect(formatNumber(-50)).toBe('-50.00');
  });

  it('respects decimal parameter', () => {
    expect(formatNumber(1e9, 0)).toBe('1B');
    expect(formatNumber(1.234e9, 3)).toBe('1.234B');
  });
});

describe('formatGEX', () => {
  it('formats positive GEX with + prefix', () => {
    expect(formatGEX(1e9)).toBe('+$1.00B');
    expect(formatGEX(2.5e9)).toBe('+$2.50B');
  });

  it('formats negative GEX without + prefix', () => {
    expect(formatGEX(-1e9)).toBe('$-1.00B');
    expect(formatGEX(-500e6)).toBe('$-0.50B');
  });

  it('formats zero GEX', () => {
    expect(formatGEX(0)).toBe('+$0.00B');
  });
});

describe('formatCurrency', () => {
  it('formats currency with USD symbol', () => {
    expect(formatCurrency(5950.25)).toBe('$5,950.25');
    expect(formatCurrency(1000)).toBe('$1,000.00');
  });

  it('formats negative currency', () => {
    expect(formatCurrency(-100)).toBe('-$100.00');
  });

  it('respects decimal parameter', () => {
    expect(formatCurrency(5950.123, 0)).toBe('$5,950');
    expect(formatCurrency(5950.1234, 4)).toBe('$5,950.1234');
  });
});

describe('formatPercent', () => {
  it('formats positive percent with + sign', () => {
    expect(formatPercent(5)).toBe('+5.00%');
    expect(formatPercent(0.5)).toBe('+0.50%');
  });

  it('formats negative percent without + sign', () => {
    expect(formatPercent(-5)).toBe('-5.00%');
  });

  it('formats zero', () => {
    expect(formatPercent(0)).toBe('+0.00%');
  });
});

describe('zero gamma helpers', () => {
  const createSnapshot = (overrides: Partial<GEXSnapshot> = {}): GEXSnapshot => ({
    timestamp: '2026-03-25T10:30:00.000Z',
    spot_price: 6000,
    total_call_gex: -2.0e9,
    total_put_gex: 1.5e9,
    net_gex: -5.0e8,
    zero_gamma_level: 6010,
    gex_by_strike: { 6000: 1.0e8 },
    dominant_strike: 6000,
    metrics: {
      zero_gamma_crossing_found: true,
    },
    ...overrides,
  });

  it('treats missing crossing metadata as no zero gamma crossing', () => {
    expect(hasZeroGammaCrossing(createSnapshot({ metrics: {} }))).toBe(false);
  });

  it('treats unrecognized crossing metadata as no zero gamma crossing', () => {
    expect(
      hasZeroGammaCrossing(
        createSnapshot({
          metrics: {
            zero_gamma_crossing_found: 'maybe',
          },
        })
      )
    ).toBe(false);
  });

  it('returns Unknown when range relation metadata is absent', () => {
    const snapshot = createSnapshot({
      metrics: {
        zero_gamma_crossing_found: false,
      },
    });

    expect(formatZeroGammaValue(snapshot)).toBe('Unknown');
    expect(formatZeroGammaStatus(snapshot)).toBe('Unknown');
  });

  it('returns Above Range and Above sampled range for above-range snapshots', () => {
    const snapshot = createSnapshot({
      metrics: {
        zero_gamma_crossing_found: false,
        zero_gamma_relation: 'above_range',
      },
    });

    expect(formatZeroGammaValue(snapshot)).toBe('Above Range');
    expect(formatZeroGammaStatus(snapshot)).toBe('Above sampled range');
  });

  it('returns Unknown instead of formatting a missing zero gamma level', () => {
    const snapshot = createSnapshot({
      zero_gamma_level: undefined as unknown as number,
    });

    expect(formatZeroGammaValue(snapshot)).toBe('Unknown');
  });

  it('returns a signed distance and percent for valid crossing data', () => {
    const snapshot = createSnapshot({
      spot_price: 6000,
      zero_gamma_level: 6005,
    });

    expect(formatZeroGammaStatus(snapshot)).toBe('+$5 (+0.08%)');
  });

  it('returns N/A percent when spot price is zero', () => {
    const snapshot = createSnapshot({
      spot_price: 0,
      zero_gamma_level: 6005,
    });

    expect(formatZeroGammaStatus(snapshot)).toBe('+$6,005 (N/A)');
  });
});

describe('getRegimeColor', () => {
  it('returns red for short_gamma', () => {
    expect(getRegimeColor('short_gamma')).toBe('text-red-600');
  });

  it('returns green for long_gamma', () => {
    expect(getRegimeColor('long_gamma')).toBe('text-green-600');
  });

  it('returns yellow for neutral and unknown', () => {
    expect(getRegimeColor('neutral')).toBe('text-yellow-600');
    expect(getRegimeColor('unknown')).toBe('text-yellow-600');
  });
});

describe('getRegimeBackgroundColor', () => {
  it('returns red background for short_gamma', () => {
    expect(getRegimeBackgroundColor('short_gamma')).toBe('bg-red-50 border-red-200');
  });

  it('returns green background for long_gamma', () => {
    expect(getRegimeBackgroundColor('long_gamma')).toBe('bg-green-50 border-green-200');
  });

  it('returns yellow background for neutral', () => {
    expect(getRegimeBackgroundColor('neutral')).toBe('bg-yellow-50 border-yellow-200');
  });
});

describe('isMarketOpen', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns false on weekends', () => {
    // Saturday
    vi.setSystemTime(new Date('2026-01-31T12:00:00-05:00'));
    expect(isMarketOpen()).toBe(false);

    // Sunday
    vi.setSystemTime(new Date('2026-02-01T12:00:00-05:00'));
    expect(isMarketOpen()).toBe(false);
  });

  it('returns false before market open', () => {
    // Monday 9:00 AM ET
    vi.setSystemTime(new Date('2026-01-26T09:00:00-05:00'));
    expect(isMarketOpen()).toBe(false);

    // Monday 9:29 AM ET
    vi.setSystemTime(new Date('2026-01-26T09:29:00-05:00'));
    expect(isMarketOpen()).toBe(false);
  });

  it('returns true during market hours', () => {
    // Monday 10:00 AM ET
    vi.setSystemTime(new Date('2026-01-26T10:00:00-05:00'));
    expect(isMarketOpen()).toBe(true);

    // Monday 3:30 PM ET
    vi.setSystemTime(new Date('2026-01-26T15:30:00-05:00'));
    expect(isMarketOpen()).toBe(true);
  });

  it('returns false after market close', () => {
    // Monday 4:00 PM ET
    vi.setSystemTime(new Date('2026-01-26T16:00:00-05:00'));
    expect(isMarketOpen()).toBe(false);

    // Monday 5:00 PM ET
    vi.setSystemTime(new Date('2026-01-26T17:00:00-05:00'));
    expect(isMarketOpen()).toBe(false);
  });
});

describe('market date helpers', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('uses the New York calendar date around UTC day boundaries', () => {
    vi.setSystemTime(new Date('2026-03-31T02:30:00Z'));

    expect(getCurrentMarketDateString()).toBe('2026-03-30');
  });

  it('detects dates after the current New York market date', () => {
    expect(isFutureMarketDate('2026-03-31', '2026-03-30')).toBe(true);
    expect(isFutureMarketDate('2026-03-30', '2026-03-30')).toBe(false);
    expect(isFutureMarketDate('2026-03-29', '2026-03-30')).toBe(false);
  });
});
