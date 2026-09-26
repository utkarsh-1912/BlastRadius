import PermissionCheckPanel from "@/components/PermissionCheckPanel";
import PageHeader from "@/components/ui/PageHeader";

export default function CheckPage() {
  return (
    <main className="flex flex-col pb-10">
      <PageHeader
        title="Check a Single Permission"
        description="A standalone, read-only spot-check for one role and action — no review workflow, no approval needed, because nothing is ever written."
      />
      <div className="px-8">
        <PermissionCheckPanel />
      </div>
    </main>
  );
}
