/**
 * 0DTE GEX Frontend - Enhanced WebSocket Hook for Real-time Updates
 *
 * Features:
 * - Exponential backoff for reconnection (1s -> 2s -> 4s -> ... up to 30s)
 * - Connection state tracking (idle, connecting, connected, disconnected, error)
 * - Heartbeat/ping mechanism for connection health
 * - Typed message discrimination for different event types
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import type { GEXUpdate, ConnectionState, ProviderName } from '@/types';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';

// Reconnection configuration
const MIN_RECONNECT_DELAY = 1000; // 1 second
const MAX_RECONNECT_DELAY = 30000; // 30 seconds
const HEARTBEAT_INTERVAL = 30000; // 30 seconds

interface UseWebSocketOptions {
  autoReconnect?: boolean;
  maxRetries?: number;
  onConnected?: () => void;
  onDisconnected?: () => void;
  onError?: (error: string) => void;
}

interface UseWebSocketReturn<T> {
  data: T | null;
  isConnected: boolean;
  connectionState: ConnectionState;
  error: string | null;
  retryCount: number;
  lastUpdateTime: number | null;
  sendMessage: (message: string) => void;
  reconnect: () => void;
  disconnect: () => void;
}

interface WebSocketMessage<T> {
  type: 'connected' | 'gex_update' | 'error' | 'pong';
  data: T;
  timestamp: string;
  market_open?: boolean;
}

/**
 * Calculate exponential backoff delay with jitter.
 * @param attempt - Number of retry attempts (0-indexed)
 * @returns Delay in milliseconds
 */
function calculateBackoffDelay(attempt: number): number {
  // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (capped)
  const delay = Math.min(
    MIN_RECONNECT_DELAY * Math.pow(2, attempt),
    MAX_RECONNECT_DELAY
  );
  // Add ±10% jitter to prevent thundering herd
  const jitter = delay * 0.1 * (Math.random() * 2 - 1);
  return Math.round(delay + jitter);
}

/**
 * Enhanced WebSocket hook with exponential backoff, connection states,
 * and heartbeat mechanism for reliable real-time data streaming.
 */
export function useWebSocket<T>(
  endpoint: string,
  options: UseWebSocketOptions = {}
): UseWebSocketReturn<T> {
  const {
    autoReconnect = true,
    maxRetries = 10,
    onConnected,
    onDisconnected,
    onError,
  } = options;

  const [data, setData] = useState<T | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting');
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [lastUpdateTime, setLastUpdateTime] = useState<number | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const heartbeatRef = useRef<NodeJS.Timeout | null>(null);
  const shouldReconnectRef = useRef(true);
  const retryCountRef = useRef(retryCount);

  useEffect(() => {
    retryCountRef.current = retryCount;
  }, [retryCount]);

  // Derived state for convenience
  const isConnected = connectionState === 'connected';

  /**
   * Clear all pending timeouts.
   */
  const clearTimeouts = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
  }, []);

  /**
   * Start heartbeat ping to keep connection alive.
   */
  const startHeartbeat = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
    }
    heartbeatRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, HEARTBEAT_INTERVAL);
  }, []);

  /**
   * Send message to WebSocket server.
   */
  const sendMessage = useCallback((message: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(message);
    } else {
      console.warn('[WebSocket] Cannot send message - not connected');
    }
  }, []);

  const openConnection = useCallback((mode: 'initial' | 'retry' = 'initial') => {
    const url = `${WS_URL}${endpoint}`;

    if (
      wsRef.current?.readyState === WebSocket.CONNECTING ||
      wsRef.current?.readyState === WebSocket.OPEN
    ) {
      return;
    }

    const scheduleReconnect = (attempt: number) => {
      if (!autoReconnect || !shouldReconnectRef.current) {
        return;
      }

      if (attempt >= maxRetries) {
        setError(`Max reconnection attempts (${maxRetries}) exceeded`);
        setConnectionState('error');
        return;
      }

      const delay = calculateBackoffDelay(attempt);
      console.log(
        `[WebSocket] Reconnecting in ${delay}ms (attempt ${attempt + 1}/${maxRetries})`
      );

      reconnectTimeoutRef.current = setTimeout(() => {
        setConnectionState('connecting');
        setError(null);
        setRetryCount((prev) => prev + 1);
      }, delay);
    };

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log(
          `[WebSocket] ${mode === 'retry' ? 'Reconnected' : 'Connected'} to ${endpoint}`
        );
        setConnectionState('connected');
        setError(null);
        setRetryCount(0);
        startHeartbeat();
        onConnected?.();
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const message = JSON.parse(event.data as string) as WebSocketMessage<T>;
          setLastUpdateTime(Date.now());

          switch (message.type) {
            case 'connected':
              console.log('[WebSocket] Received connection confirmation');
              break;

            case 'gex_update':
              setData(message.data);
              break;

            case 'error':
              console.error('[WebSocket] Server error:', message.data);
              setError(String(message.data));
              onError?.(String(message.data));
              break;

            case 'pong':
              break;

            default:
              if (message.data) {
                setData(message.data);
              }
          }
        } catch (e) {
          console.error('[WebSocket] Failed to parse message:', e);
        }
      };

      ws.onerror = () => {
        const errorMessage = 'WebSocket connection error';
        setError(errorMessage);
        onError?.(errorMessage);
      };

      ws.onclose = (event) => {
        console.log(`[WebSocket] Disconnected from ${endpoint} (code: ${event.code})`);
        clearTimeouts();
        if (wsRef.current === ws) {
          wsRef.current = null;
        }
        onDisconnected?.();

        if (event.code === 1000 || !shouldReconnectRef.current) {
          setConnectionState('disconnected');
          return;
        }

        setConnectionState('disconnected');
        scheduleReconnect(retryCountRef.current);
      };
    } catch (e) {
      console.error('[WebSocket] Failed to create connection:', e);
      scheduleReconnect(retryCountRef.current);
    }
  }, [
    endpoint,
    autoReconnect,
    maxRetries,
    startHeartbeat,
    onConnected,
    onDisconnected,
    onError,
    clearTimeouts,
  ]);

  // Main connection effect - handles all WebSocket lifecycle
  useEffect(() => {
    shouldReconnectRef.current = true;
    openConnection('initial');

    // Cleanup function
    return () => {
      shouldReconnectRef.current = false;
      clearTimeouts();
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
        wsRef.current = null;
      }
    };
  }, [openConnection, clearTimeouts]);

  // Handle retry count changes to trigger reconnection
  useEffect(() => {
    if (retryCount > 0 && shouldReconnectRef.current && wsRef.current === null) {
      openConnection('retry');
    }
  }, [retryCount, openConnection]);

  /**
   * Disconnect from WebSocket and prevent auto-reconnect.
   */
  const disconnect = useCallback(() => {
    shouldReconnectRef.current = false;
    clearTimeouts();
    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnected');
      wsRef.current = null;
    }
    setConnectionState('disconnected');
  }, [clearTimeouts]);

  /**
   * Manually trigger reconnection.
   */
  const reconnect = useCallback(() => {
    shouldReconnectRef.current = false;
    clearTimeouts();
    if (wsRef.current) {
      wsRef.current.close(1000, 'Reconnecting');
      wsRef.current = null;
    }
    shouldReconnectRef.current = true;
    setRetryCount(0);
    setConnectionState('connecting');
    setError(null);
    openConnection('retry');
  }, [clearTimeouts, openConnection]);

  return {
    data,
    isConnected,
    connectionState,
    error,
    retryCount,
    lastUpdateTime,
    sendMessage,
    reconnect,
    disconnect,
  };
}

/**
 * Specialized hook for GEX real-time stream with enhanced options.
 */
export function useGEXStream(
  demoModeEnabled: boolean = false,
  provider?: ProviderName,
  options?: Omit<UseWebSocketOptions, 'onConnected' | 'onDisconnected'>
) {
  const params = new URLSearchParams();
  if (provider) {
    params.set('provider', provider);
  }
  if (demoModeEnabled) {
    params.set('demo', 'true');
  }
  const queryString = params.toString();
  const endpoint = queryString ? `/gex-stream?${queryString}` : '/gex-stream';

  return useWebSocket<GEXUpdate>(endpoint, {
    autoReconnect: true,
    maxRetries: 10,
    ...options,
  });
}
