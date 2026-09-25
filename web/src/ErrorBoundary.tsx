import { Component, type ReactNode } from "react";
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="fatal-error" role="alert">
        <h1>Le panneau a rencontré une erreur</h1>
        <p>
          Aucune réussite de commande ne peut être confirmée. Le runtime peut
          encore être actif : consultez son état via Codex avant de relancer une
          opération.
        </p>
        <button onClick={() => window.location.reload()}>
          Recharger le panneau
        </button>
      </main>
    );
  }
}
