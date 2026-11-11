import type { ReactNode } from 'react';

/** Message d'erreur (rouille), annoncé aux lecteurs d'écran. */
export function Alert({ children }: { readonly children: ReactNode }) {
  return (
    <p role="alert" className="border-l-4 border-rust-500 bg-rust-500/10 px-3 py-1 text-rust-400">
      <span aria-hidden="true">!! </span>
      {children}
    </p>
  );
}
