import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PageShell } from './PageShell';

describe('PageShell', () => {
  it('provides the common research landmark targeted by the skip link', () => {
    render(<PageShell>Standard shell</PageShell>);
    expect(screen.getByRole('main')).toHaveAttribute('id', 'research-content');
    expect(screen.getByRole('main')).toHaveTextContent('Standard shell');
  });
  it('accepts page additions on the wide desktop shell', () => {
    render(<PageShell variant="wide" className="page-extra">Wide shell</PageShell>);
    expect(screen.getByRole('main')).toHaveClass('research-page', 'page-extra');
  });
});
