import type { ButtonHTMLAttributes } from 'react';

type Variant = 'primary' | 'ghost' | 'danger';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  readonly variant?: Variant;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    'border-verdigris-500 bg-verdigris-700/40 text-verdigris-300 hover:bg-verdigris-700/70 hover:text-bone',
  ghost: 'border-charcoal-600 bg-transparent text-ash hover:border-ash hover:text-bone',
  danger: 'border-rust-500 bg-rust-500/15 text-rust-400 hover:bg-rust-500/30',
};

export function Button({ variant = 'primary', className = '', type = 'button', ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={`border-2 px-4 py-1 font-display text-sm tracking-widest uppercase transition-colors duration-75 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40 ${VARIANTS[variant]} ${className}`}
      {...rest}
    />
  );
}
