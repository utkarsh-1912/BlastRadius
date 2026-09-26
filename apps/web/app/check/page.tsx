import PermissionCheckPanel from "@/components/PermissionCheckPanel";

export default function CheckPage() {
  return (
    <main className="flex flex-col px-6 py-8">
      <h1 className="text-xl font-semibold text-gray-900">Check a Single Permission</h1>
      <p className="mt-1 max-w-2xl text-sm text-gray-500">
        A standalone, read-only spot-check for one role and action — no review workflow, no approval needed,
        because nothing is ever written.
      </p>
      <div className="mt-6 max-w-2xl">
        <PermissionCheckPanel />
      </div>
    </main>
  );
}
