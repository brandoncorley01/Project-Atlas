import { OptionsSignalsView } from "@/components/options/OptionsSignalsView";
import { PageHeader } from "@/components/ui/PageHeader";

export default function OptionsPage() {
  return (
    <>
      <PageHeader
        title="Retail Options"
        description="Capital-first: under-$100 contracts lead until Atlas proves its options win rate. Every card still shows entry, max loss, take profit, and trade plan."
      />
      <OptionsSignalsView />
    </>
  );
}
