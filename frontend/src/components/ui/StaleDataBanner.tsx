/**
 * Stale Data Banner Component
 *
 * Displays a warning banner when data is older than the threshold.
 * Provides visual feedback for data freshness issues.
 */

'use client';

import { memo, useState, useEffect } from 'react';
import { formatDistanceToNow } from 'date-fns';

interface StaleDataBannerProps {
  lastUpdateTime: number | null;
  staleThresholdMs?: number;
  isVisible?: boolean;
  onDismiss?: () => void;
  className?: string;
}

// Default stale threshold: 60 seconds
const DEFAULT_STALE_THRESHOLD = 60000;
// Time update interval for staleness checks
const TIME_UPDATE_INTERVAL = 5000;

/**
 * StaleDataBanner shows a warning when data hasn't been updated recently.
 */
export const StaleDataBanner = memo(function StaleDataBanner({
  lastUpdateTime,
  staleThresholdMs = DEFAULT_STALE_THRESHOLD,
  isVisible,
  onDismiss,
  className = '',
}: StaleDataBannerProps) {
  const [currentTime, setCurrentTime] = useState(Date.now);
  const [timeSinceUpdate, setTimeSinceUpdate] = useState<string | null>(null);

  // Update current time periodically
  useEffect(() => {
    const updateTime = () => {
      setCurrentTime(Date.now());
      if (lastUpdateTime) {
        setTimeSinceUpdate(formatDistanceToNow(lastUpdateTime, { addSuffix: true }));
      }
    };

    updateTime();
    const interval = setInterval(updateTime, TIME_UPDATE_INTERVAL);
    return () => clearInterval(interval);
  }, [lastUpdateTime]);

  // Calculate if data is stale
  const isStale = !lastUpdateTime || (currentTime - lastUpdateTime > staleThresholdMs);

  // Don't render if not stale or explicitly hidden
  if (!isStale || isVisible === false) {
    return null;
  }

  return (
    <div
      className={`flex items-center justify-between rounded-lg border border-amber-500/30 bg-amber-950/50 px-4 py-2.5 ${className}`}
      role="alert"
    >
      <div className="flex items-center gap-3">
        {/* Warning icon */}
        <svg
          className="h-4 w-4 flex-shrink-0 text-amber-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>

        {/* Message */}
        <div className="flex flex-col">
          <span className="text-sm font-medium text-amber-200">
            Data may be stale
          </span>
          {timeSinceUpdate && (
            <span className="text-xs text-amber-400/80">
              Last updated {timeSinceUpdate}
            </span>
          )}
        </div>
      </div>

      {/* Dismiss button (optional) */}
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="rounded p-1 text-amber-400 hover:bg-amber-900/50 hover:text-amber-300 transition-colors"
          aria-label="Dismiss"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
});

/**
 * Inline version for compact layouts.
 */
export const StaleDataIndicator = memo(function StaleDataIndicator({
  lastUpdateTime,
  staleThresholdMs = DEFAULT_STALE_THRESHOLD,
}: Pick<StaleDataBannerProps, 'lastUpdateTime' | 'staleThresholdMs'>) {
  const [currentTime, setCurrentTime] = useState(Date.now);

  // Update current time periodically
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(Date.now());
    }, TIME_UPDATE_INTERVAL);
    return () => clearInterval(interval);
  }, []);

  const isStale = !lastUpdateTime || (currentTime - lastUpdateTime > staleThresholdMs);

  if (!isStale) return null;

  return (
    <span
      className="inline-flex items-center gap-1 rounded bg-amber-900/50 px-1.5 py-0.5 text-xs text-amber-300"
      title="Data may be stale"
    >
      <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
        <path
          fillRule="evenodd"
          d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
          clipRule="evenodd"
        />
      </svg>
      Stale
    </span>
  );
});
