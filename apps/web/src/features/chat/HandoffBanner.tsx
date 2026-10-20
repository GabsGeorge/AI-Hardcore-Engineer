import { useTranslation } from "react-i18next";
import { Alert } from "@/design";
import type { HandoffRef } from "./types";

/** Four states map 1:1 to the backend events. The copy comes from i18n so the merchant sees
 * their chosen language, independent of the message language. */
export function HandoffBanner({
  handoff,
  slaBreached,
}: {
  handoff: HandoffRef;
  slaBreached: boolean;
}) {
  const { t } = useTranslation();
  if (handoff.status === "none") {
    return null;
  }
  if (handoff.status === "awaiting_human") {
    if (slaBreached) {
      return (
        <Alert tone="warning" title={t("chat.handoff.slaTitle")}>
          {t("chat.handoff.slaBody")}
        </Alert>
      );
    }
    return (
      <Alert tone="info" title={t("chat.handoff.waitingTitle")}>
        {t("chat.handoff.waitingBody", { ticket: handoff.ticket_id ?? "" })}
      </Alert>
    );
  }
  if (handoff.status === "resolved") {
    return (
      <Alert tone="success" title={t("chat.handoff.resolvedTitle")}>
        {t("chat.handoff.resolvedBody")}
      </Alert>
    );
  }
  return (
    <Alert tone="danger" title={t("chat.handoff.expiredTitle")}>
      {t("chat.handoff.expiredBody")}
    </Alert>
  );
}
