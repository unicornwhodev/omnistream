import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
type Request = {
  title: string;
  message: string;
  confirmLabel?: string;
  destructive?: boolean;
};
type Confirm = (request: Request) => Promise<boolean>;
const Context = createContext<Confirm>(async () => false);
export const useConfirm = () => useContext(Context);
export function ConfirmationProvider({ children }: { children: ReactNode }) {
  const [request, setRequest] = useState<Request | null>(null);
  const resolver = useRef<((answer: boolean) => void) | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const confirm: Confirm = (value) => {
    if (resolver.current) return Promise.resolve(false);
    trigger.current = document.activeElement as HTMLElement;
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
      setRequest(value);
    });
  };
  const settle = (answer: boolean) => {
    dialog.current?.close();
    resolver.current?.(answer);
    resolver.current = null;
    setRequest(null);
    trigger.current?.focus();
  };
  useEffect(() => {
    if (request) dialog.current?.showModal();
  }, [request]);
  useEffect(
    () => () => {
      resolver.current?.(false);
    },
    [],
  );
  return (
    <Context.Provider value={confirm}>
      {children}
      <dialog
        ref={dialog}
        className="confirmation-dialog"
        aria-labelledby="confirmation-title"
        aria-describedby="confirmation-message"
        onCancel={(e) => {
          e.preventDefault();
          settle(false);
        }}
      >
        {request && (
          <>
            <h2 id="confirmation-title">{request.title}</h2>
            <p id="confirmation-message">{request.message}</p>
            <div className="button-row">
              <button autoFocus onClick={() => settle(false)}>
                Annuler
              </button>
              <button
                className={request.destructive ? "danger" : "primary"}
                onClick={() => settle(true)}
              >
                {request.confirmLabel || "Confirmer"}
              </button>
            </div>
          </>
        )}
      </dialog>
    </Context.Provider>
  );
}
