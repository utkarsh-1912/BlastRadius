interface Props {
  roleName?: string | null;
  validatorSource?: string | null;
}

export default function ProjectHeader({ roleName, validatorSource }: Props) {
  return (
    <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
      <div className="flex items-center gap-3">
        <span className="text-lg font-semibold tracking-tight text-gray-900">BLAST RADIUS</span>
        <span className="text-xs text-gray-400">AWS IAM Access-Review Agent</span>
      </div>
      <div className="text-right">
        <div className="text-sm font-medium text-gray-800">{roleName ?? "AWS IAM"}</div>
        {validatorSource && (
          <div className="text-xs text-gray-400">
            validated via {validatorSource === "aws" ? "real AWS policy simulator" : validatorSource}
          </div>
        )}
      </div>
    </header>
  );
}
