import { ScoreBadge } from "@/components/ui/ScoreBadge";

interface PlaceholderCardProps {
  title: string;
  description: string;
  module: string;
}

export function PlaceholderCard({ title, description, module }: PlaceholderCardProps) {
  return (
    <div className="atlas-card p-5">
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted">{module}</p>
          <h3 className="mt-1 text-lg font-semibold">{title}</h3>
        </div>
        <span className="rounded-full bg-accent/20 px-2 py-0.5 text-xs text-accent">Coming soon</span>
      </div>
      <p className="mb-4 text-sm text-muted">{description}</p>
      <div className="grid grid-cols-3 gap-2">
        <ScoreBadge label="Confidence" value={null} variant="confidence" />
        <ScoreBadge label="Risk" value={null} variant="risk" />
        <ScoreBadge label="Opportunity" value={null} variant="opportunity" />
      </div>
    </div>
  );
}
