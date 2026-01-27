/**
 * 0DTE GEX Frontend - WebSocket Hook for Real-time Updates
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import type { GEXUpdate } from '@/types';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';

interface UseWebSocketOptions {
  autoReconnect?: boolean;
  reconnectInterval?: number;
  maxRetries?: number;
}

interface UseWebSocketReturn<T> {
  data: T | null;
  isConnected: boolean;
  error: string | null;
  sendMessage: (message: string) => void;
  reconnect: () => void;
}

/**
 * Generic WebSocket hook for real-time data streaming.
 */
export function useWebSocket<T>(
  endpoint: string,
  options: UseWebSocketOptions = {}
): UseWebSocketReturn<T> {
  const {
    autoReconnect = true,
    reconnectInterval = 5000,
    maxRetries = 3,
  } = options;

  const [data, setData] = useState<T | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Clear any pending reconnect on unmount
  useEffect(() => {
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, []);

  // Main connection effect
  useEffect(() => {
    const url = `${WS_URL}${endpoint}`;
    let connectionError: string | null = null;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log(`WebSocket connected to ${endpoint}`);
      setIsConnected(true);
      setError(null);
      setRetryCount(0);
    };

    ws.onmessage = (event: MessageEvent) => {
      try {
        const message = JSON.parse(event.data as string) as { data: T };
        setData(message.data);
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.onerror = () => {
      connectionError = 'WebSocket connection error';
      setError(connectionError);
    };

    ws.onclose = () => {
      console.log(`WebSocket disconnected from ${endpoint}`);
      setIsConnected(false);

      // Schedule reconnect if enabled and within retry limit
      if (autoReconnect && retryCount < maxRetries) {
        console.log(
          `Reconnecting in ${reconnectInterval}ms (attempt ${retryCount + 1})`
        );
        reconnectTimeoutRef.current = setTimeout(() => {
          setRetryCount((prev) => prev + 1);
        }, reconnectInterval);
      }
    };

    return () => {
      ws.close();
    };
  }, [endpoint, retryCount, autoReconnect, reconnectInterval, maxRetries]);

  const sendMessage = useCallback((message: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(message);
    }
  }, []);

  const reconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    setRetryCount(0);
  }, []);

  return { data, isConnected, error, sendMessage, reconnect };
}

/**
 * Specialized hook for GEX real-time stream.
 */
export function useGEXStream() {
  return useWebSocket<GEXUpdate>('/gex-stream');
}
