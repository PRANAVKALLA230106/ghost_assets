import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { createCase, runCase, uploadCase } from "../api";

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

const UPLOADS: { id: string; label: string; hint: string; accept: string; multiple?: boolean }[] = [
  { id: "sms", label: "SMS backup", hint: "XML from SMS Backup & Restore", accept: ".xml" },
  { id: "email", label: "Email export", hint: "JSON export", accept: ".json" },
  { id: "ais", label: "Tax statement (AIS)", hint: "PDF from the income tax portal", accept: ".pdf" },
  { id: "photos", label: "Photos", hint: "Passbooks, certificates, letters", accept: "image/*", multiple: true },
];

export default function NewCasePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [dateOfDeath, setDateOfDeath] = useState("");
  const [docs, setDocs] = useState<string[]>([]);
  const [known, setKnown] = useState("");
  const [files, setFiles] = useState<Record<string, File[]>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleDoc = (id: string) =>
    setDocs((d) => (d.includes(id) ? d.filter((x) => x !== id) : [...d, id]));

  const loadSample = async () => {
    setBusy(true);
    setError(null);
    try {
      const { case_id } = await createCase(SAMPLE_CASE);
      await runCase(case_id);
      navigate(`/case/${case_id}`, { state: { deceasedName: SAMPLE_CASE.deceased_name } });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
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
    setBusy(true);
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
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-3xl font-semibold text-accent">Ghost Assets</h1>
      <p className="mt-2 text-muted">
        Find every bank account, deposit, policy, fund and share your family member left behind, and get a
        claim pack for each one.
      </p>

      <button
        onClick={loadSample}
        disabled={busy}
        className="mt-8 w-full rounded-lg bg-accent px-6 py-4 text-lg font-semibold text-page shadow-lg transition hover:brightness-110 disabled:cursor-wait disabled:opacity-60"
      >
        {busy ? "Starting the sample case…" : "Load Ramesh's sample case"}
      </button>
      {error && (
        <p className="mt-3 rounded bg-card px-4 py-3 text-sm text-red-300">
          Could not start the case: {error}
        </p>
      )}

      <div className="my-8 flex items-center gap-4 text-sm text-muted">
        <div className="h-px flex-1 bg-card" />
        or start your own case
        <div className="h-px flex-1 bg-card" />
      </div>

      <form onSubmit={startSearch}>
      <section className="rounded-lg bg-card p-6">
        <h2 className="text-lg font-semibold">About the person</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="text-sm text-muted">Name of the deceased</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Ramesh Kumar"
              className="mt-1 w-full rounded border border-muted/30 bg-page px-3 py-2 text-ink outline-none focus:border-accent"
            />
          </label>
          <label className="block">
            <span className="text-sm text-muted">Date of death</span>
            <input
              type="date"
              value={dateOfDeath}
              onChange={(e) => setDateOfDeath(e.target.value)}
              className="mt-1 w-full rounded border border-muted/30 bg-page px-3 py-2 text-ink outline-none [color-scheme:dark] focus:border-accent"
            />
          </label>
        </div>
      </section>

      <section className="mt-4 rounded-lg bg-card p-6">
        <h2 className="text-lg font-semibold">What they left behind</h2>
        <p className="mt-1 text-sm text-muted">Upload whatever you have. Every file helps.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {UPLOADS.map((u) => (
            <label
              key={u.id}
              className="flex cursor-pointer flex-col rounded border border-dashed border-muted/40 bg-page px-4 py-4 transition hover:border-accent"
            >
              <span className="font-medium">{u.label}</span>
              <span className="text-xs text-muted">{u.hint}</span>
              <span className="mt-2 truncate text-sm text-accent">
                {files[u.id]?.length ? files[u.id].map((x) => x.name).join(", ") : "Choose file…"}
              </span>
              <input
                type="file"
                accept={u.accept}
                multiple={u.multiple}
                className="hidden"
                onChange={(e) =>
                  setFiles((f) => ({ ...f, [u.id]: Array.from(e.target.files ?? []) }))
                }
              />
            </label>
          ))}
        </div>
      </section>

      <section className="mt-4 rounded-lg bg-card p-6">
        <h2 className="text-lg font-semibold">What the family already knows about</h2>
        <p className="mt-1 text-sm text-muted">One per line. Add the last digits of the account if you know them.</p>
        <textarea
          value={known}
          onChange={(e) => setKnown(e.target.value)}
          rows={3}
          placeholder={"SBI savings account ending 8812\nLIC life insurance policy"}
          className="mt-3 w-full rounded border border-muted/30 bg-page px-3 py-2 text-ink outline-none focus:border-accent"
        />
      </section>

      <section className="mt-4 rounded-lg bg-card p-6">
        <h2 className="text-lg font-semibold">Documents you already have</h2>
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {DOCUMENTS.map((d) => (
            <label key={d.id} className="flex cursor-pointer items-center gap-3 text-sm">
              <input
                type="checkbox"
                checked={docs.includes(d.id)}
                onChange={() => toggleDoc(d.id)}
                className="h-4 w-4 accent-accent"
              />
              {d.label}
            </label>
          ))}
        </div>
      </section>

      <button
        type="submit"
        disabled={busy || missing.length > 0}
        title={missing.length ? `Still needed: ${missing.join(", ")}` : undefined}
        className="mt-6 w-full rounded-lg bg-accent px-6 py-3 font-semibold text-page transition hover:brightness-110 disabled:cursor-not-allowed disabled:bg-transparent disabled:text-muted disabled:outline disabled:outline-1 disabled:outline-muted/30"
      >
        {busy ? "Uploading…" : "Start the search"}
      </button>
      {missing.length > 0 && <p className="mt-2 text-center text-xs text-muted">Still needed: {missing.join(", ")}</p>}
      </form>
    </div>
  );
}
