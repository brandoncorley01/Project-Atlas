import { GLOSSARY } from "@/lib/glossary";

interface TermHintProps {
  term: keyof typeof GLOSSARY | string;
  label?: string;
  className?: string;
}

export function TermHint({ term, label, className = "" }: TermHintProps) {
  const key = term.toLowerCase().replace(/\s+/g, "_");
  const definition = GLOSSARY[key] ?? GLOSSARY[term.toLowerCase()];
  if (!definition) return <span className={className}>{label ?? term}</span>;

  return (
    <abbr
      title={definition}
      className={`cursor-help border-b border-dotted border-muted/60 no-underline ${className}`}
    >
      {label ?? term}
    </abbr>
  );
}
