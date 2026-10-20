import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

type Announce = (message: string, politeness?: "polite" | "assertive") => void;

const LiveContext = createContext<Announce | null>(null);

export function LiveRegion({ children }: { children: ReactNode }) {
  const [polite, setPolite] = useState("");
  const [assertive, setAssertive] = useState("");
  const timeout = useRef<number | null>(null);

  const announce = useCallback<Announce>((message, politeness = "polite") => {
    if (timeout.current !== null) {
      window.clearTimeout(timeout.current);
    }
    if (politeness === "assertive") {
      setAssertive("");
      // Nudge the DOM so a re-announcement of the same text is read.
      window.requestAnimationFrame(() => setAssertive(message));
    } else {
      setPolite("");
      window.requestAnimationFrame(() => setPolite(message));
    }
    timeout.current = window.setTimeout(() => {
      setPolite("");
      setAssertive("");
    }, 4000);
  }, []);

  useEffect(
    () => () => {
      if (timeout.current !== null) {
        window.clearTimeout(timeout.current);
      }
    },
    [],
  );

  return (
    <LiveContext.Provider value={announce}>
      {children}
      <div className="sr-only" aria-live="polite">
        {polite}
      </div>
      <div className="sr-only" aria-live="assertive" role="alert">
        {assertive}
      </div>
    </LiveContext.Provider>
  );
}

export function useLiveAnnouncer(): Announce {
  const context = useContext(LiveContext);
  if (context === null) {
    // Returning a no-op lets screens that don't mount LiveRegion still compile. Tests of
    // SSE must wrap with LiveRegion to verify announcement.
    return () => {};
  }
  return context;
}
