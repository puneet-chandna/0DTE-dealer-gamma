export type AppDataMode = 'live' | 'demo';

export function getAppDataMode(demoModeEnabled: boolean): AppDataMode {
  return demoModeEnabled ? 'demo' : 'live';
}
