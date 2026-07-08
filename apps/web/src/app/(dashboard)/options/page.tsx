import { OptionsSignalsView } from "@/components/options/OptionsSignalsView";
import { PageHeader } from "@/components/ui/PageHeader";

export default function OptionsPage() {
  return (
    <>
      <PageHeader
        title="Retail Options"
        description="Full decision data on every pick — entry window, max loss, take profit, breakeven, win probability, ITM timeline, and strategy comparison."
      />
      <OptionsSignalsView />
    </>
  );
}
