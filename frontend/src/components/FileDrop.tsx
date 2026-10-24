import { useState, type DragEvent } from "react";
import { Check, CloudUpload, X, type LucideIcon } from "lucide-react";

/** True when a dropped file matches an `accept` string like ".xml" or "image/*". */
function matchesAccept(file: File, accept: string): boolean {
  return accept.split(",").some((rule) => {
    const r = rule.trim().toLowerCase();
    if (r.startsWith(".")) return file.name.toLowerCase().endsWith(r);
    if (r.endsWith("/*")) return file.type.startsWith(r.slice(0, -1));
    return file.type === r;
  });
}

function formatSize(bytes: number): string {
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1e3))} KB`;
}

/** A drag-and-drop zone that also opens the file picker on click. */
export default function FileDrop({
  label,
  hint,
  accept,
  multiple,
  icon: Icon,
  noun,
  files,
  onFiles,
}: {
  label: string;
  hint: string;
  accept: string;
  multiple?: boolean;
  icon: LucideIcon;
  /** Singular noun for the count line, e.g. "photo" -> "2 photos selected". */
  noun?: string;
  files: File[];
  onFiles: (files: File[]) => void;
}) {
  const [over, setOver] = useState(false);
  const chosen = files.length > 0;

  const take = (list: File[]) => {
    const ok = list.filter((f) => matchesAccept(f, accept));
    if (ok.length) onFiles(multiple ? ok : ok.slice(0, 1));
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    take(Array.from(e.dataTransfer.files));
  };

  const summary = multiple
    ? `${files.length} ${noun ?? "file"}${files.length === 1 ? "" : "s"} selected`
    : files[0] && `${files[0].name} · ${formatSize(files[0].size)}`;

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={`group relative flex min-h-[120px] cursor-pointer flex-col justify-between gap-4 rounded-2xl border p-5 transition duration-200 ${
        over
          ? "border-accent bg-accent/10"
          : chosen
            ? "border-good/40 bg-good/[0.06] hover:border-good/60"
            : "border-dashed border-line bg-page/40 hover:border-accent/60 hover:bg-raised/60"
      }`}
    >
      <div className="flex items-start gap-3">
        <span
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition ${
            chosen ? "bg-good/15 text-good" : "bg-raised text-muted group-hover:text-accent"
          }`}
        >
          {chosen ? <Check size={20} strokeWidth={2.25} /> : <Icon size={20} strokeWidth={1.75} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-medium text-ink">{label}</div>
          <div className="text-sm text-faint">{hint}</div>
        </div>
        {chosen && (
          <button
            type="button"
            aria-label={`Remove ${label}`}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onFiles([]);
            }}
            className="-m-1 rounded-lg p-1 text-faint transition hover:bg-overlay hover:text-ink"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {chosen ? (
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-good">{summary}</div>
          {multiple && (
            <div className="mt-0.5 truncate text-xs text-faint">{files.map((f) => f.name).join(", ")}</div>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-2 text-sm text-faint group-hover:text-muted">
          <CloudUpload size={16} strokeWidth={1.75} />
          Drop {multiple ? "files" : "a file"} here or <span className="text-accent">browse</span>
        </div>
      )}

      <input
        type="file"
        accept={accept}
        multiple={multiple}
        className="sr-only"
        onChange={(e) => {
          take(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
    </label>
  );
}
