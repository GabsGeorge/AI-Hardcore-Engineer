/**
 * Minimal client for the Mailpit HTTP API. We use it to pull the single transactional link
 * the test flow needs, keeping the E2E deterministic (no polling against an inbox).
 */

export type Message = { ID: string; To: Array<{ Address: string }> };

const MAILPIT = process.env.MAILPIT_URL ?? "http://mailpit:8025";

export async function clearInbox(): Promise<void> {
  await fetch(`${MAILPIT}/api/v1/messages`, { method: "DELETE" });
}

export async function waitForLink(
  to: string,
  pattern: RegExp,
  timeoutMs = 10_000,
): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const list = (await (await fetch(`${MAILPIT}/api/v1/messages`)).json()) as {
      messages: Message[];
    };
    const match = list.messages.find((m) => m.To.some((r) => r.Address === to));
    if (match !== undefined) {
      const body = (await (await fetch(`${MAILPIT}/api/v1/message/${match.ID}`)).json()) as {
        Text: string;
        HTML: string;
      };
      const text = `${body.Text}\n${body.HTML}`;
      const found = pattern.exec(text);
      if (found !== null) {
        return found[0];
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(`no e-mail matching ${pattern} to ${to} within ${timeoutMs}ms`);
}
