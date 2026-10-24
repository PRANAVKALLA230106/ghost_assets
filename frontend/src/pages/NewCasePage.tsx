import { useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Check, CirclePlay, CircleAlert, LoaderCircle } from "lucide-react";
import { createCase, runCase, uploadCase } from "../api";
import FileDrop from "../components/FileDrop";
import { SOURCE_ICON } from "../icons";

const SAMPLE_CASE = {
  deceased_name: "Ramesh Kumar",
  date_of_death: "2026-02-10",
  data_dir: "data/ramesh",
  documents_have: ["death_certificate", "claimant_id"],
  known_assets: ["SBI savings account ending 8812", "LIC life insurance policy"],
};

const DOCUMENTS: { id: string; label: string }[] = [
  { id: "death_certificate", label: "Death certificate" },
  { id: "claimant_id", label: "Claimant ID (Aadhaar / PAN)" },
  { id: "legal_heir_certificate", label: "Legal heir certificate" },
  { id: "succession_certificate", label: "Succession certificate" },
  { id: "deceased_pan", label: "Deceased's PAN card" },
  { id: "relationship_proof", label: "Proof of relationship" },
];

const UPLOADS: { id: string; label: string; hint: string; accept: string; multiple?: boolean; noun?: string }[] = [
  { id: "sms", label: "SMS backup", hint: "XML from SMS Backup & Restore", accept: ".xml" },
  { id: "email", label: "Email export", hint: "JSON export", accept: ".json" },
  { id: "ais", label: "Tax statement (AIS)", hint: "PDF from the income tax portal", accept: ".pdf" },
  { id: "photos", label: "Photos", hint: "Passbooks, certificates, letters", accept: "image/*", multiple: true, noun: "photo" },
];

const inputClass =
  "mt-2 w-full rounded-xl border border-line bg-page/60 px-4 py-3 text-ink placeholder:text-faint outline-none transition focus:border-accent/70 focus:ring-4 focus:ring-accent/10";

function Section({ step, title, hint, children }: { step: number; title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="grid gap-6 border-t border-line/60 px-8 py-8 first:border-t-0 md:grid-cols-[200px_1fr]">
      <div>
        <div className="flex items-center gap-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-full border border-line text-xs font-semibold tabular-nums text-muted">
            {step}
          </span>
          <h2 className="font-medium text-ink">{title}</h2>
        </div>
        {hint && <p className="mt-2 text-sm leading-relaxed text-faint md:pl-10">{hint}</p>}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

export default function NewCasePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [dateOfDeath, setDateOfDeath] = useState("");
  const [docs, setDocs] = useState<string[]>([]);
  const [known, setKnown] = useState("");
  const [files, setFiles] = useState<Record<string, File[]>>({});
  const [busy, setBusy] = useState<"sample" | "upload" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggleDoc = (id: string) =>
    setDocs((d) => (d.includes(id) ? d.filter((x) => x !== id) : [...d, id]));

  const loadSample = async () => {
    setBusy("sample");
    setError(null);
    try {
      const { case_id } = await createCase(SAMPLE_CASE);
      await runCase(case_id);
      navigate(`/case/${case_id}`, { state: { deceasedName: SAMPLE_CASE.deceased_name } });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(null);
    }
  };

  const missing = [
    !name.trim() && "name",
    !dateOfDeath && "date of death",
    !files.sms?.length && "SMS backup",
    !files.email?.length && "email export",
    !files.ais?.length && "AIS statement",
  ].filter(Boolean) as string[];

  const startSearch = async (e: FormEvent) => {
    e.preventDefault();
    if (missing.length) return;
    setBusy("upload");
    setError(null);
    try {
      const { case_id } = await uploadCase({
        deceased_name: name.trim(),
        date_of_death: dateOfDeath,
        documents_have: docs,
        known_assets: known.split("\n").map((k) => k.trim()).filter(Boolean),
        sms: files.sms[0],
        email: files.email[0],
        ais: files.ais[0],
        photos: files.photos ?? [],
      });
      navigate(`/case/${case_id}`, { state: { deceasedName: name.trim() } });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen px-6 py-12 lg:py-16">
      <div className="mx-auto max-w-4xl animate-[fadein_600ms_ease-out]">
        <header>
          <div className="flex items-center gap-3 text-sm font-medium uppercase tracking-[0.2em] text-muted">
            <span className="h-2.5 w-2.5 rounded-full bg-accent shadow-glow" />
            Ghost Assets
          </div>
          <h1 className="mt-6 max-w-3xl font-display text-5xl font-light leading-[1.1] tracking-tight text-ink lg:text-6xl">
            Find everything they left behind, <span className="text-accent">and claim it.</span>
          </h1>
          <p className="mt-5 max-w-2xl text-lg leading-relaxed text-muted">
            With the heir's consent, Ghost Assets reads the messages, statements and papers a person left, finds every
            account, deposit, policy and share, and prepares the claim for each one.
          </p>
        </header>

        <div className="mt-10 flex flex-col gap-5 rounded-2xl border border-line/60 bg-card p-6 shadow-card sm:flex-row sm:items-center">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-accent/10 text-accent">
            <CirclePlay size={24} strokeWidth={1.75} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="font-medium text-ink">See it work on a sample case</div>
            <div className="mt-0.5 text-sm text-faint">
              {SAMPLE_CASE.deceased_name} · SMS, email, tax statement and passbook photos already loaded
            </div>
          </div>
          <button
            onClick={loadSample}
            disabled={busy !== null}
            className="flex items-center justify-center gap-2 rounded-xl bg-accent px-6 py-3.5 font-semibold text-page shadow-glow transition hover:-translate-y-px hover:bg-accent-bright disabled:cursor-wait disabled:opacity-60 disabled:hover:translate-y-0"
          >
            {busy === "sample" ? (
              <>
                <LoaderCircle size={18} className="animate-spin" /> Starting…
              </>
            ) : (
              <>
                Load {SAMPLE_CASE.deceased_name.split(" ")[0]}'s case <ArrowRight size={18} />
              </>
            )}
          </button>
        </div>

        {error && (
          <div className="mt-4 flex items-start gap-3 rounded-xl border border-bad/30 bg-bad/10 px-5 py-4 text-sm text-bad">
            <CircleAlert size={18} className="mt-px shrink-0" />
            Could not start the case: {error}
          </div>
        )}

        <div className="my-10 flex items-center gap-4 text-xs font-medium uppercase tracking-[0.18em] text-faint">
          <div className="h-px flex-1 bg-line/70" />
          or open a new case
          <div className="h-px flex-1 bg-line/70" />
        </div>

        <form onSubmit={startSearch} className="overflow-hidden rounded-3xl border border-line/60 bg-card shadow-raised">
          <Section step={1} title="About the person">
            <div className="grid gap-5 sm:grid-cols-2">
              <label className="block">
                <span className="text-sm text-muted">Name of the deceased</span>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Full name"
                  className={inputClass}
                />
              </label>
              <label className="block">
                <span className="text-sm text-muted">Date of death</span>
                <input
                  type="date"
                  value={dateOfDeath}
                  onChange={(e) => setDateOfDeath(e.target.value)}
                  className={`${inputClass} [color-scheme:dark]`}
                />
              </label>
            </div>
          </Section>

          <Section step={2} title="What they left behind" hint="Upload whatever you have. Every file helps.">
            <div className="grid gap-4 sm:grid-cols-2">
              {UPLOADS.map((u) => (
                <FileDrop
                  key={u.id}
                  label={u.label}
                  hint={u.hint}
                  accept={u.accept}
                  multiple={u.multiple}
                  noun={u.noun}
                  icon={SOURCE_ICON[u.id]}
                  files={files[u.id] ?? []}
                  onFiles={(list) => setFiles((f) => ({ ...f, [u.id]: list }))}
                />
              ))}
            </div>
          </Section>

          <Section
            step={3}
            title="What the family knows"
            hint="One per line. Add the last digits of the account if you know them."
          >
            <textarea
              value={known}
              onChange={(e) => setKnown(e.target.value)}
              rows={3}
              placeholder={"Savings account at the local bank, ending 1234\nLife insurance policy"}
              className={`${inputClass} mt-0 resize-none leading-relaxed`}
            />
          </Section>

          <Section step={4} title="Documents you have">
            <div className="grid gap-3 sm:grid-cols-2">
              {DOCUMENTS.map((d) => {
                const on = docs.includes(d.id);
                return (
                  <label
                    key={d.id}
                    className={`flex cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 text-sm transition ${
                      on ? "border-accent/50 bg-accent/[0.07] text-ink" : "border-line bg-page/40 text-muted hover:bg-raised/60 hover:text-ink"
                    }`}
                  >
                    <input type="checkbox" checked={on} onChange={() => toggleDoc(d.id)} className="peer sr-only" />
                    <span
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition peer-focus-visible:ring-2 peer-focus-visible:ring-accent/60 ${
                        on ? "border-accent bg-accent text-page" : "border-line bg-page"
                      }`}
                    >
                      {on && <Check size={14} strokeWidth={3} />}
                    </span>
                    {d.label}
                  </label>
                );
              })}
            </div>
          </Section>

          <div className="flex flex-col gap-4 border-t border-line/60 bg-raised/40 px-8 py-6 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-faint">
              {missing.length > 0 ? (
                <>
                  Still needed: <span className="text-muted">{missing.join(", ")}</span>
                </>
              ) : (
                <span className="flex items-center gap-2 text-good">
                  <Check size={16} /> Ready to search
                </span>
              )}
            </p>
            <button
              type="submit"
              disabled={busy !== null || missing.length > 0}
              title={missing.length ? `Still needed: ${missing.join(", ")}` : undefined}
              className="flex shrink-0 items-center justify-center gap-2 rounded-xl bg-accent px-7 py-3.5 font-semibold text-page shadow-glow transition hover:-translate-y-px hover:bg-accent-bright disabled:cursor-not-allowed disabled:bg-overlay disabled:text-faint disabled:shadow-none disabled:hover:translate-y-0"
            >
              {busy === "upload" ? (
                <>
                  <LoaderCircle size={18} className="animate-spin" /> Uploading…
                </>
              ) : (
                <>
                  Start the search <ArrowRight size={18} />
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
