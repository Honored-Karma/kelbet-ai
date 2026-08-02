import { useI18n } from "../i18n/runtime";
import { useOnline } from "../hooks/useOnline";
import { Icon } from "./Icon";

export function OfflineBanner() {
  const online = useOnline();
  const { tx } = useI18n();
  if (online) {
    return null;
  }
  return (
    <div className="offline-banner" role="status" aria-live="polite" aria-atomic="true">
      <Icon name="support" />
      <span>{tx("common.offline")}</span>
    </div>
  );
}
