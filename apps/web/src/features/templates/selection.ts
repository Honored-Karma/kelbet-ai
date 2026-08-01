import type { GenerationTemplate, Language, Quote } from "../../shared/api/types";

export type TemplateSelection = {
  templateId: string | null;
  templateInputs: Record<string, unknown>;
};

export function buildTemplateSelection(
  template: GenerationTemplate | null | undefined,
  values: Record<string, string>,
): TemplateSelection {
  if (!template) return { templateId: null, templateInputs: {} };
  const templateInputs = Object.fromEntries(
    template.required_inputs.fields.flatMap((field) => {
      const value = (values[field.key] ?? "").trim();
      return value ? [[field.key, value]] : [];
    }),
  );
  return { templateId: template.id, templateInputs };
}

/** Create must replay the server-normalized snapshot returned by the fresh quote. */
export function templateSelectionFromQuote(quote: Quote): TemplateSelection {
  return {
    templateId: quote.template_id,
    templateInputs: { ...quote.template_inputs },
  };
}

export function isTemplateUnavailable(
  templateId: string | null,
  template: GenerationTemplate | null | undefined,
  catalogLoadedSuccessfully: boolean,
): boolean {
  return Boolean(catalogLoadedSuccessfully && templateId && !template);
}

export function templateFieldsValid(
  template: GenerationTemplate | null | undefined,
  values: Record<string, string>,
): boolean {
  if (!template) return true;
  return template.required_inputs.fields.every((field) => {
    const value = (values[field.key] ?? "").trim();
    return (!field.required || value.length > 0) && value.length <= field.max_length;
  });
}

export function templateMarker(template: GenerationTemplate): string {
  const marker = template.preview_metadata.marker;
  return typeof marker === "string" && marker.trim() ? marker : "✦";
}

export function templateFieldLabel(
  field: GenerationTemplate["required_inputs"]["fields"][number],
  language: Language,
): string {
  return typeof field.label === "string" ? field.label : field.label[language];
}
