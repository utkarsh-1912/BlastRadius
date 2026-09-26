import Badge from "@/components/ui/Badge";

interface Props {
  roleName?: string | null;
  validatorSource?: string | null;
}

/** A page-specific context line for a review's detail page. */
export default function ProjectHeader({ roleName, validatorSource }: Props) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-8 pb-5 pt-8">
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{roleName ?? "AWS IAM"}</h1>
      {validatorSource && (
        <Badge tone="brand">validated via {validatorSource === "aws" ? "real AWS policy simulator" : validatorSource}</Badge>
      )}
    </div>
  );
}
