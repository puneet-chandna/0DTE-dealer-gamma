import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

describe('PageShell', () => {
  it('renders the standard shell with the default responsive spacing scale', async () => {
    const pageShellModule = await import('./PageShell');
    const PageShell = pageShellModule.PageShell;

    const { container } = render(<PageShell>Standard shell</PageShell>);

    expect(screen.getByText('Standard shell')).toBeInTheDocument();
    expect(container.firstChild).toHaveClass(
      'w-full',
      'max-w-[1440px]',
      'px-4',
      'sm:px-6',
      'xl:px-8',
      'py-6',
      'md:py-8'
    );
  });

  it('renders the wide shell variant for terminal-style pages', async () => {
    const pageShellModule = await import('./PageShell');
    const PageShell = pageShellModule.PageShell;

    const { container } = render(<PageShell variant="wide">Wide shell</PageShell>);

    expect(screen.getByText('Wide shell')).toBeInTheDocument();
    expect(container.firstChild).toHaveClass('max-w-[1600px]');
  });
});
