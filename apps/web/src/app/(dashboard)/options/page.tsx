import { OptionsSignalsView } from "@/components/options/OptionsSignalsView";
import { PageHeader } from "@/components/ui/PageHeader";

export default function OptionsPage() {
  return (
    <>
      <PageHeader
        title="Retail Options"
        description="Atlas ranks call and put setups by confidence and profit odds. Pick #1 for the strongest play — expand any card for entry dates, breakeven, and beginner tips."
      />
      <OptionsSignalsView />
    </>
  );
}
