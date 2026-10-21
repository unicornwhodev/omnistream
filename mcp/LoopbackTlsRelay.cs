using System;
using System.Collections.Concurrent;
using System.Net;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Security.Cryptography.X509Certificates;
using System.Threading;
using System.Threading.Tasks;

// Managed loopback transport. No certificate creation, trust installation,
// bearer rewriting, SDK modification or non-loopback binding occurs here.
public sealed class OmniStreamLoopbackTlsRelay : IDisposable
{
    private readonly TcpListener listener;
    private readonly X509Certificate2 certificate;
    private readonly int targetPort;
    private readonly ConcurrentDictionary<TcpClient, byte> clients = new ConcurrentDictionary<TcpClient, byte>();
    private readonly CancellationTokenSource cancellation = new CancellationTokenSource();
    private Task accepting;

    public OmniStreamLoopbackTlsRelay(X509Certificate2 certificate, int listenPort, int targetPort)
    {
        if (certificate == null || !certificate.HasPrivateKey) throw new ArgumentException("A certificate with a private key is required.");
        if (listenPort < 1024 || listenPort > 65535 || targetPort < 1024 || targetPort > 65535 || listenPort == targetPort)
            throw new ArgumentException("Invalid loopback ports.");
        this.certificate = certificate;
        this.targetPort = targetPort;
        listener = new TcpListener(IPAddress.Loopback, listenPort);
    }

    public void Start()
    {
        listener.Start(8);
        accepting = Accept();
    }

    private async Task Accept()
    {
        while (!cancellation.IsCancellationRequested)
        {
            TcpClient client;
            try { client = await listener.AcceptTcpClientAsync().ConfigureAwait(false); }
            catch (ObjectDisposedException) { break; }
            catch (SocketException) { if (cancellation.IsCancellationRequested) break; throw; }
            clients.TryAdd(client, 0);
            if (clients.Count > 32) { byte ignored; clients.TryRemove(client, out ignored); client.Close(); continue; }
            Task handling = Forward(client);
            // All connection failures are observed inside Forward; no request
            // bytes or WebSocket authorization subprotocol are logged.
        }
    }

    private async Task Forward(TcpClient client)
    {
        TcpClient upstream = null;
        try
        {
            client.NoDelay = true;
            using (var tls = new SslStream(client.GetStream(), false))
            {
                Task handshake = tls.AuthenticateAsServerAsync(certificate, false, SslProtocols.None, false);
                if (await Task.WhenAny(handshake, Task.Delay(5000, cancellation.Token)).ConfigureAwait(false) != handshake) return;
                await handshake.ConfigureAwait(false);
                upstream = new TcpClient();
                clients.TryAdd(upstream, 0);
                await upstream.ConnectAsync(IPAddress.Loopback, targetPort).ConfigureAwait(false);
                upstream.NoDelay = true;
                using (var raw = upstream.GetStream())
                {
                    Task toKit = tls.CopyToAsync(raw);
                    Task toBrowser = raw.CopyToAsync(tls);
                    Task finished = await Task.WhenAny(toKit, toBrowser).ConfigureAwait(false);
                    Task other = finished == toKit ? toBrowser : toKit;
                    Task observeOther = other.ContinueWith(t => { var observed = t.Exception; }, TaskContinuationOptions.OnlyOnFaulted);
                    await finished.ConfigureAwait(false);
                }
            }
        }
        catch (Exception) { /* Closed or failed connection; never log private bytes. */ }
        finally
        {
            byte ignored;
            clients.TryRemove(client, out ignored);
            client.Close();
            if (upstream != null) { clients.TryRemove(upstream, out ignored); upstream.Close(); }
        }
    }

    public void Dispose()
    {
        cancellation.Cancel();
        listener.Stop();
        foreach (var client in clients.Keys) client.Close();
        if (accepting != null) { try { accepting.Wait(2000); } catch (AggregateException) { } }
        cancellation.Dispose();
    }
}
