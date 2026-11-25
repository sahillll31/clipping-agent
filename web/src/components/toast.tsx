import * as React from "react";

const ToastContext = React.createContext<(message: string) => void>(() => {});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [message, setMessage] = React.useState<string | null>(null);
  const timer = React.useRef<number | undefined>(undefined);

  const push = React.useCallback((next: string) => {
    setMessage(next);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setMessage(null), 2400);
  }, []);

  React.useEffect(() => () => window.clearTimeout(timer.current), []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      {message ? (
        <div
          role="status"
          className="fixed bottom-6 left-1/2 z-[100] -translate-x-1/2 rounded-xl border border-border bg-[#151922] px-4 py-2.5 text-sm text-foreground shadow-[0_24px_60px_-20px_rgba(0,0,0,0.9)]"
          style={{ animation: "toast-in 0.2s ease both" }}
        >
          {message}
        </div>
      ) : null}
    </ToastContext.Provider>
  );
}

export function useToast() {
  return React.useContext(ToastContext);
}
