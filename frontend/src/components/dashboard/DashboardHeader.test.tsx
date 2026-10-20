import { describe, expect, it } from 'vitest';
import { DashboardHeader } from './DashboardHeader';
import { NavBar } from '@/components/ui/NavBar';

describe('DashboardHeader', () => {
  it('uses the shared workstation header on the dashboard', () => {
    expect(DashboardHeader).toBe(NavBar);
  });
});
