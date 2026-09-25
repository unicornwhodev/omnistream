export function record(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value
    : null;
}
export function parseToolResult(response) {
  const outer = record(response);
  const owner = record(outer?.result) ?? outer;
  if (outer?.error || owner?.error)
    throw new Error(
      String(
        record(owner?.error ?? outer?.error)?.message ||
          "La requête MCP a échoué.",
      ),
    );
  const data =
    record(owner?.structuredContent) ?? record(outer?.structuredContent);
  const text = [owner?.content, outer?.content]
    .flatMap((parts) => (Array.isArray(parts) ? parts : []))
    .find((part) => typeof part?.text === "string")?.text;
  if (owner?.isError === true || outer?.isError === true || data?.ok === false)
    throw new Error(
      data?.message || text || "La commande Omniverse a été refusée.",
    );
  if (!data || Object.keys(data).length === 0)
    throw new Error(
      "Réponse MCP incomplète : aucune donnée structurée reçue. Aucune réussite ne peut être confirmée.",
    );
  return data;
}
export function observedState(value) {
  const names = {
    ready: "Prêt",
    playing: "Lecture",
    paused: "En pause",
    stopped: "Arrêté",
    idle: "Au repos",
    offline: "Hors ligne",
    unavailable: "Indisponible",
    starting: "Démarrage",
    waiting: "En attente",
    empty: "Aucune scène",
    unknown: "Non vérifié",
    stale: "État ancien",
  };
  return names[value] || value || "Non vérifié";
}
