import type { Language, ModerationConfig } from "../../shared/api/types";

const copy = {
  ru: {
    title: "Права на фотографию",
    consent:
      "Я подтверждаю, что имею право использовать это фото и получил согласие изображённых людей.",
    textOnly:
      "Модерация проверяет только текст запроса. Содержимое изображения автоматически не проверяется.",
    support: "Оспорить решение или обратиться в поддержку",
    loading: "Загружаем актуальную версию правил…",
    unavailable: "Правила сейчас недоступны. Отправка с фото временно заблокирована.",
  },
  kk: {
    title: "Фотосуретке құқық",
    consent:
      "Бұл фотосуретті пайдалануға құқығым барын және суреттегі адамдардың келісімін алғанымды растаймын.",
    textOnly:
      "Модерация тек сұрау мәтінін тексереді. Сурет мазмұны автоматты түрде тексерілмейді.",
    support: "Шешімге шағымдану немесе қолдауға жазу",
    loading: "Ережелердің өзекті нұсқасы жүктелуде…",
    unavailable: "Ережелер қолжетімсіз. Фотомен жіберу уақытша тоқтатылды.",
  },
} as const;

export function PhotoRightsConsent({
  id,
  language,
  config,
  checked,
  loading = false,
  error = false,
  onChange,
}: {
  id: string;
  language: Language;
  config?: ModerationConfig;
  checked: boolean;
  loading?: boolean;
  error?: boolean;
  onChange: (checked: boolean) => void;
}) {
  const text = copy[language];
  return (
    <section className="photo-rights-consent" aria-labelledby={`${id}-title`}>
      <div className="photo-rights-heading">
        <span aria-hidden>R</span>
        <div>
          <strong id={`${id}-title`}>{text.title}</strong>
          {config ? <small>policy {config.photo_rights_consent_version}</small> : null}
        </div>
      </div>
      {config ? (
        <>
          <label className="photo-rights-check" htmlFor={`${id}-check`}>
            <input
              id={`${id}-check`}
              type="checkbox"
              checked={checked}
              onChange={(event) => onChange(event.target.checked)}
            />
            <span aria-hidden>{checked ? "✓" : ""}</span>
            <strong>{text.consent}</strong>
          </label>
          <p className="photo-rights-limit">
            <b>TEXT ONLY</b> {config.image_moderation_supported ? "" : text.textOnly}
          </p>
          <a className="photo-rights-support" href={config.support_route}>
            {text.support} · {config.support_route}
          </a>
        </>
      ) : (
        <p className="photo-rights-state" role={error ? "alert" : "status"}>
          {loading ? text.loading : text.unavailable}
        </p>
      )}
    </section>
  );
}
