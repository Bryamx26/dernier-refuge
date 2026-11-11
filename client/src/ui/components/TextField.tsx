import { useId, type InputHTMLAttributes } from 'react';

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  readonly label: string;
  readonly hint?: string;
}

/** Champ de saisie façon invite de commande. */
export function TextField({ label, hint, className = '', ...rest }: TextFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      <label htmlFor={id} className="font-display text-xs tracking-[0.2em] text-ash uppercase">
        {label}
      </label>
      <div className="flex items-center gap-2 border-2 border-charcoal-600 bg-charcoal-950 px-2 focus-within:border-verdigris-500">
        <span aria-hidden="true" className="text-verdigris-500">
          &gt;
        </span>
        <input
          id={id}
          aria-describedby={hint ? hintId : undefined}
          className="w-full bg-transparent py-1 text-xl text-bone placeholder:text-charcoal-600 focus:outline-none"
          autoComplete="off"
          spellCheck={false}
          {...rest}
        />
      </div>
      {hint && (
        <p id={hintId} className="text-base text-ash/80">
          {hint}
        </p>
      )}
    </div>
  );
}
