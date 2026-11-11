import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { WorldPanel } from './WorldPanel';

describe('WorldPanel', () => {
  it('affiche position en tuiles, joueurs visibles et correction', () => {
    render(
      <WorldPanel
        stats={{ tileX: 64.46, tileY: 12, visiblePlayers: 3, correctionTiles: 0.031, loading: '' }}
      />,
    );
    expect(screen.getByTestId('world-position')).toHaveTextContent('64,5 · 12,0');
    expect(screen.getByTestId('world-players')).toHaveTextContent('3');
    expect(screen.getByTestId('world-correction')).toHaveTextContent('0,03 t');
  });

  it('signale une correction au-delà de 0,25 tuile', () => {
    render(
      <WorldPanel
        stats={{ tileX: null, tileY: null, visiblePlayers: 0, correctionTiles: 0.4, loading: '' }}
      />,
    );
    expect(screen.getByTestId('world-position')).toHaveTextContent('—');
    expect(screen.getByText('0,40 t')).toHaveClass('text-rust-400');
  });
});
