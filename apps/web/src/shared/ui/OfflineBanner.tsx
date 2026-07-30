import { useI18n } from "../i18n/runtime";
import { useOnline } from "../hooks/useOnline";

export function OfflineBanner() {
  const online = useOnline();
  const { tx } = useI18n();
  if (online) {
    return null;
  }
  return <div className="offline-banner">{tx("common.offline")}</div>;
}
