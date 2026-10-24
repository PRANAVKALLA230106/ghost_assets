import { useState } from "react";
import { postAnswer } from "../api";
import { useGhostStore } from "../store";

/** Shows the oldest unanswered question. Which ones were answered is UI state, kept locally. */
export default function QuestionModal({ caseId }: { caseId: string }) {
  const questions = useGhostStore((s) => s.questions);
  const [answered, setAnswered] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [freeText, setFreeText] = useState("");

  const question = questions.find((q) => !answered.includes(q.id));
  if (!question) return null;

  const answer = async (value: string) => {
    if (!value.trim()) return;
    setSending(true);
    setError(null);
    try {
      await postAnswer(caseId, question.id, value);
      setAnswered((a) => [...a, question.id]);
      setFreeText("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-[760px] animate-[fadein_300ms_ease-out] rounded-2xl border border-accent bg-card p-10 shadow-2xl">
        <div className="text-sm uppercase tracking-widest text-accent">The agent needs the family's help</div>
        <div className="mt-4 text-3xl leading-snug">{question.text}</div>
        {question.options.length > 0 ? (
          <div className="mt-8 flex flex-wrap gap-4">
            {question.options.map((opt) => (
              <button
                key={opt}
                disabled={sending}
                onClick={() => answer(opt)}
                className="min-w-40 rounded-lg border-2 border-accent px-8 py-4 text-2xl font-semibold text-accent transition hover:bg-accent hover:text-page disabled:opacity-50"
              >
                {opt}
              </button>
            ))}
          </div>
        ) : (
          <form
            className="mt-8 flex gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              answer(freeText);
            }}
          >
            <input
              autoFocus
              value={freeText}
              onChange={(e) => setFreeText(e.target.value)}
              className="flex-1 rounded-lg border border-muted/30 bg-page px-4 py-3 text-xl outline-none focus:border-accent"
            />
            <button
              disabled={sending}
              className="rounded-lg bg-accent px-8 py-3 text-xl font-semibold text-page disabled:opacity-50"
            >
              Send
            </button>
          </form>
        )}
        {error && <p className="mt-4 text-red-300">Could not send the answer: {error}</p>}
      </div>
    </div>
  );
}
