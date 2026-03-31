/**
 * 0DTE GEX Frontend - Utility Functions
 */

import { type ClassValue, clsx } from 'clsx';
import type { GEXSnapshot } from '@/types';

const MARKET_TIME_ZONE = 'America/New_York';

/**
 * Merge class names with clsx (for conditional classes).
 */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}

/**
 * Format large numbers with abbreviations (K, M, B).
 */
export function formatNumber(value: number, decimals: number = 2): string {
  if (Math.abs(value) >= 1e9) {
    return `${(value / 1e9).toFixed(decimals)}B`;
  }
  if (Math.abs(value) >= 1e6) {
    return `${(value / 1e6).toFixed(decimals)}M`;
  }
  if (Math.abs(value) >= 1e3) {
    return `${(value / 1e3).toFixed(decimals)}K`;
  }
  return value.toFixed(decimals);
}

/**
 * Format GEX value in billions with sign.
 */
export function formatGEX(value: number): string {
  const billions = value / 1e9;
  const sign = billions >= 0 ? '+' : '';
  return `${sign}$${billions.toFixed(2)}B`;
}

/**
 * Format currency value.
 */
export function formatCurrency(value: number, decimals: number = 2): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatMarketTimestamp(timestamp: string): string | null {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) return null;

  const dateLabel = new Intl.DateTimeFormat('en-US', {
    timeZone: MARKET_TIME_ZONE,
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(parsed);
  const timeLabel = new Intl.DateTimeFormat('en-US', {
    timeZone: MARKET_TIME_ZONE,
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(parsed);

  return `${dateLabel} ${timeLabel} ET`;
}

function readZeroGammaRelation(snapshot?: Pick<GEXSnapshot, 'metrics'> | null) {
  const relation = snapshot?.metrics?.zero_gamma_relation;
  return relation === 'below_range' || relation === 'above_range' ? relation : null;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function hasZeroGammaCrossing(snapshot?: Pick<GEXSnapshot, 'metrics'> | null): boolean {
  const crossingMetric = snapshot?.metrics?.zero_gamma_crossing_found;

  if (typeof crossingMetric === 'boolean') return crossingMetric;
  if (typeof crossingMetric === 'number') return Number.isFinite(crossingMetric) && crossingMetric !== 0;
  if (typeof crossingMetric === 'string') {
    const normalized = crossingMetric.trim().toLowerCase();
    if (['false', '0', 'no', 'off'].includes(normalized)) return false;
    if (['true', '1', 'yes', 'on'].includes(normalized)) return true;
  }

  return false;
}

export function formatZeroGammaValue(snapshot?: GEXSnapshot | null): string {
  if (!snapshot) return '--';

  if (!hasZeroGammaCrossing(snapshot)) {
    const relation = readZeroGammaRelation(snapshot);

    if (relation === 'above_range') return 'Above Range';
    if (relation === 'below_range') return 'Below Range';

    return 'Unknown';
  }

  if (!isFiniteNumber(snapshot.zero_gamma_level)) return 'Unknown';

  return formatCurrency(snapshot.zero_gamma_level, 0);
}

export function formatZeroGammaStatus(snapshot?: GEXSnapshot | null): string {
  if (!snapshot) return '--';

  if (!hasZeroGammaCrossing(snapshot)) {
    const relation = readZeroGammaRelation(snapshot);

    if (relation === 'above_range') return 'Above sampled range';
    if (relation === 'below_range') return 'Below sampled range';

    return 'Unknown';
  }

  if (!isFiniteNumber(snapshot.zero_gamma_level) || !isFiniteNumber(snapshot.spot_price)) {
    return 'Unknown';
  }

  const distanceToZeroGamma = snapshot.zero_gamma_level - snapshot.spot_price;
  const distancePercent =
    snapshot.spot_price === 0 ? null : (distanceToZeroGamma / snapshot.spot_price) * 100;
  const percentText =
    distancePercent === null || !Number.isFinite(distancePercent)
      ? 'N/A'
      : `${distanceToZeroGamma >= 0 ? '+' : '-'}${Math.abs(distancePercent).toFixed(2)}%`;

  return `${distanceToZeroGamma >= 0 ? '+' : ''}${formatCurrency(distanceToZeroGamma, 0)} (${percentText})`;
}

/**
 * Format percentage with sign.
 */
export function formatPercent(value: number, decimals: number = 2): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(decimals)}%`;
}

/**
 * Get regime color class based on regime type.
 */
export function getRegimeColor(regime: string): string {
  switch (regime) {
    case 'short_gamma':
      return 'text-red-600';
    case 'long_gamma':
      return 'text-green-600';
    default:
      return 'text-yellow-600';
  }
}

/**
 * Get regime background color class.
 */
export function getRegimeBackgroundColor(regime: string): string {
  switch (regime) {
    case 'short_gamma':
      return 'bg-red-50 border-red-200';
    case 'long_gamma':
      return 'bg-green-50 border-green-200';
    default:
      return 'bg-yellow-50 border-yellow-200';
  }
}

/**
 * Parse date string to Date object in ET timezone.
 */
export function parseETDate(dateString: string): Date {
  // SPX trades in ET - ensure proper timezone handling
  return new Date(dateString);
}

export function getCurrentMarketDateString(now: Date = new Date()): string {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: MARKET_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  const parts = formatter.formatToParts(now);
  const partLookup = Object.fromEntries(parts.map((part) => [part.type, part.value]));

  return `${partLookup.year}-${partLookup.month}-${partLookup.day}`;
}

export function isFutureMarketDate(
  dateString: string,
  marketDate: string = getCurrentMarketDateString()
): boolean {
  if (!dateString) return false;
  return dateString > marketDate;
}

/**
 * Check if current time is within market hours (9:30 AM - 4:00 PM ET).
 */
export function isMarketOpen(): boolean {
  const now = new Date();
  // Convert to ET
  const etTime = new Date(
    now.toLocaleString('en-US', { timeZone: MARKET_TIME_ZONE })
  );

  const hours = etTime.getHours();
  const minutes = etTime.getMinutes();
  const day = etTime.getDay();

  // Weekends
  if (day === 0 || day === 6) return false;

  // Before 9:30 AM
  if (hours < 9 || (hours === 9 && minutes < 30)) return false;

  // After 4:00 PM
  if (hours >= 16) return false;

  return true;
}
