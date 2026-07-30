import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../shared/api/client";
import {
  ApiError,
  type Me,
  type PromptAssistantIntent,
} from "../../shared/api/types";
import { useI18n } from "../../shared/i18n/runtime";
import type { MessageKey } from "../../shared/i18n/messages";

const intents: Array<{ value: PromptAssistantIntent; label: MessageKey }> = [
  { value: "general", label: "create.intentGeneral" },
  { value: "product", label: "create.intentProduct" },
  { value: "social", label: "create.intentSocial" },
  { value: "portrait", label: "create.intentPortrait" },
  { value: "interior", label: "create.intentInterior" },
  { value: "food", label: "create.intentFood" },
  { value: "fashion", label: "create.intentFashion" },
];

type Proposal = {
  original: string;
  improved: string;
};

function errorMessage(error: unknown): MessageKey {
  if (error instanceof ApiError) {
    if (error.status === 429 || error.code.includes("rate")) return "create.assistantRateError";
    if (error.code === "insufficient_credits") return "create.assistantInsufficient";
    if (error.status === 502 || error.status === 503 || error.code.includes("provider")) {
      return "create.assistantProviderError";
    }
  }
  return "create.assistantGenericError";
}

export function PromptAssistant({
  prompt,
  setPrompt,
  modelMaxChars,
}: {
  prompt: string;
  setPrompt: (value: string) => void;
  modelMaxChars: number;
}) {
  const { tx, language } = useI18n();
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);
  const [intent, setIntent] = useState<PromptAssistantIntent>("general");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [undoPrompt, setUndoPrompt] = useState<string | null>(null);
  const [wasCropped, setWasCropped] = useState(false);

  const configQuery = useQuery({
    queryKey: ["prompt-assistant-config"],
    queryFn: () => api.getPromptAssistantConfig(),
    staleTime: Number.POSITIVE_INFINITY,
  });
  const meQuery = useQuery({ queryKey: ["me"], queryFn: () => api.getMe() });
  const improveMutation = useMutation({
    mutationFn: (input: {
      brief: string;
      intent: PromptAssistantIntent;
      idempotencyKey: string;
    }) =>
      api.improvePrompt({
        ...input,
        targetLanguage: language,
      }),
    onSuccess: (result, variables) => {
      setProposal({ original: variables.brief, improved: result.improved_prompt });
      setWasCropped(false);
      queryClient.setQueryData<Me>(["me"], (current) =>
        current
          ? {
              ...current,
              balance: result.balance,
              available: Math.max(0, result.balance - current.reserved),
            }
          : current,
      );
    },
  });

  const config = configQuery.data;
  const cleanPrompt = prompt.trim();
  const isTooLong = Boolean(config && cleanPrompt.length > config.max_input_chars);
  const insufficient = Boolean(
    config && (meQuery.data?.available ?? 0) < config.credit_cost,
  );
  const disabled =
    !cleanPrompt ||
    !config ||
    isTooLong ||
    insufficient ||
    improveMutation.isPending;

  const disabledReason = !cleanPrompt
    ? tx("create.assistantEmpty")
    : isTooLong
      ? tx("create.assistantTooLong")
      : insufficient
        ? tx("create.assistantInsufficient")
        : null;

  const applyProposal = () => {
    if (!proposal) return;
    setUndoPrompt(prompt);
    const next = proposal.improved.slice(0, modelMaxChars);
    setWasCropped(proposal.improved.length > modelMaxChars);
    setPrompt(next);
    setProposal(null);
  };

  return (
    <div className={`prompt-lab${isOpen ? " is-open" : ""}`}>
      <button
        type="button"
        className="prompt-lab-trigger"
        aria-expanded={isOpen}
        aria-controls="prompt-lab-panel"
        onClick={() => setIsOpen((current) => !current)}
      >
        <span className="prompt-lab-mark" aria-hidden>KL</span>
        <span>
          <small>{tx("create.promptLabEyebrow")}</small>
          <strong>{tx("create.promptLab")}</strong>
        </span>
        <span className="prompt-lab-trigger-action">
          {isOpen ? tx("create.promptLabClose") : tx("create.promptLabOpen")} {isOpen ? "↑" : "↗"}
        </span>
      </button>

      {isOpen ? (
        <div id="prompt-lab-panel" className="prompt-lab-panel">
          <p className="prompt-lab-help">{tx("create.promptLabHelp")}</p>
          <div className="prompt-lab-meter">
            <span>
              {cleanPrompt.length}/{config?.max_input_chars ?? "—"}
            </span>
            <span
              style={{
                width: config
                  ? `${Math.min(100, (cleanPrompt.length / config.max_input_chars) * 100)}%`
                  : "0%",
              }}
            />
          </div>

          <fieldset className="prompt-lab-intents">
            <legend>{tx("create.assistantIntent")}</legend>
            <div>
              {intents.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  aria-pressed={intent === item.value}
                  className={intent === item.value ? "selected" : ""}
                  onClick={() => setIntent(item.value)}
                >
                  {tx(item.label)}
                </button>
              ))}
            </div>
          </fieldset>

          <div className="prompt-lab-charge">
            <div>
              <span>{tx("create.assistantPrice")}</span>
              <strong>{config ? `${config.credit_cost} ${tx("create.credits")}` : "—"}</strong>
            </div>
            <p>{tx("create.assistantChargeRule")}</p>
          </div>

          <button
            type="button"
            className="prompt-lab-submit"
            disabled={disabled}
            onClick={() => {
              improveMutation.reset();
              setProposal(null);
              improveMutation.mutate({
                brief: cleanPrompt,
                intent,
                idempotencyKey: crypto.randomUUID(),
              });
            }}
          >
            <span aria-hidden>✦</span>
            {improveMutation.isPending
              ? tx("create.assistantImproving")
              : tx("create.assistantImprove")}
          </button>
          {disabledReason ? <p className="prompt-lab-note">{disabledReason}</p> : null}
          {improveMutation.isError ? (
            <p className="prompt-lab-error" role="alert">
              {tx(errorMessage(improveMutation.error))}
            </p>
          ) : null}

          {proposal ? (
            <section className="prompt-lab-proposal" aria-live="polite">
              <header>
                <span className="proposal-spark" aria-hidden>✦</span>
                <div>
                  <h3>{tx("create.assistantProposal")}</h3>
                  <p>{tx("create.assistantProposalHelp")}</p>
                </div>
              </header>
              <div className="prompt-compare">
                <div>
                  <small>{tx("create.assistantOriginal")}</small>
                  <p>{proposal.original}</p>
                </div>
                <div className="is-proposed">
                  <small>{tx("create.assistantVersion")}</small>
                  <p>{proposal.improved}</p>
                </div>
              </div>
              <div className="proposal-actions">
                <button type="button" className="apply" onClick={applyProposal}>
                  {tx("create.assistantApply")} <span aria-hidden>→</span>
                </button>
                <button type="button" onClick={() => setProposal(null)}>
                  {tx("create.assistantKeep")}
                </button>
              </div>
            </section>
          ) : null}

          {undoPrompt !== null ? (
            <div className="prompt-lab-undo" role="status">
              <span>{wasCropped ? tx("create.assistantCropped") : tx("create.assistantVersion")}</span>
              <button
                type="button"
                onClick={() => {
                  setPrompt(undoPrompt);
                  setUndoPrompt(null);
                  setWasCropped(false);
                }}
              >
                ↶ {tx("create.assistantUndo")}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
