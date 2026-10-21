// Check the same authenticated WebSocket endpoint used by the NVIDIA client.
// This does not negotiate media or report a successful video connection.
export function probeSignaling(
  host: string,
  port: number,
  accessToken: string,
  timeoutMs = 5_000,
  secure = false,
): Promise<void> {
  return new Promise((resolve, reject) => {
    let socket: WebSocket | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const finish = (error?: Error) => {
      if (timer !== undefined) clearTimeout(timer);
      if (socket) {
        socket.onopen = null;
        socket.onerror = null;
        socket.onclose = null;
        socket.close();
      }
      if (error) reject(error);
      else resolve();
    };
    try {
      if (!(["127.0.0.1", "localhost", "::1"].includes(host)) || (secure && host !== "localhost") || !Number.isInteger(port) || port < 1 || port > 65535 || !accessToken) {
        throw new Error("Le canal vidéo local n’a pas de configuration authentifiée valide.");
      }
      const peer = `omnistream-check-${crypto.randomUUID()}`;
      socket = new WebSocket(
        `${secure ? "wss" : "ws"}://${host === "::1" ? "[::1]" : host}:${port}/sign_in?peer_id=${peer}&version=2&peer_role=1`,
        [`authorization.bearer.${accessToken}`],
      );
      socket.onopen = () => finish();
      socket.onerror = () => finish(new Error("Codex ne peut pas ouvrir le canal WebSocket vidéo local. Consultez le journal pour une éventuelle restriction de l’hôte."));
      socket.onclose = () => finish(new Error("Le canal WebSocket vidéo local s’est fermé avant son ouverture."));
      timer = setTimeout(() => finish(new Error("L’ouverture du canal WebSocket vidéo local a dépassé le délai de vérification.")), timeoutMs);
    } catch {
      finish(new Error("L’hôte a refusé la création du canal WebSocket vidéo local."));
    }
  });
}
