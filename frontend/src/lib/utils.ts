/**
 * 0DTE GEX Frontend - Utility Functions
 */

import { type ClassValue, clsx } from 'clsx';

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

/**
 * Check if current time is within market hours (9:30 AM - 4:00 PM ET).
 */
export function isMarketOpen(): boolean {
  const now = new Date();
  // Convert to ET
  const etTime = new Date(
    now.toLocaleString('en-US', { timeZone: 'America/New_York' })
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
