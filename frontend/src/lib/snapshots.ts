import { replaceEqualDeep } from '@tanstack/react-query';

export function canReplaceSnapshot(previousTimestamp?: string, incomingTimestamp?: string): boolean {
  const previous = Date.parse(previousTimestamp ?? '');
  const incoming = Date.parse(incomingTimestamp ?? '');
  return !Number.isFinite(previous) || (Number.isFinite(incoming) && incoming >= previous);
}

export function retainLatestSnapshot<T extends { timestamp: string }>(previous: T | undefined, incoming: T): T {
  return canReplaceSnapshot(previous?.timestamp, incoming.timestamp)
    ? replaceEqualDeep(previous, incoming)
    : previous!;
}
