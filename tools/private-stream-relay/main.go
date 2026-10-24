package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"html"
	"net"
	"net/http"
	"net/http/httputil"
	"net/netip"
	"os"
	"path/filepath"
	"regexp"
	"sync"
	"tailscale.com/tsnet"
	"time"
)

type Config struct {
	ClientIP    string `json:"client_ip"`
	TailnetHash string `json:"tailnet_name_sha256"`
	Hostname    string `json:"hostname"`
}
type Status struct {
	Phase             string `json:"phase"`
	PrivateIP         string `json:"private_ip,omitempty"`
	TCP               int    `json:"tcp_port"`
	UDP               int    `json:"udp_port"`
	ClientOnly        string `json:"client_only"`
	MediaIn           uint64 `json:"media_in"`
	MediaOut          uint64 `json:"media_out"`
	MediaWriteErrors  uint64 `json:"media_write_errors"`
	NativeWriteErrors uint64 `json:"native_write_errors"`
	NativeReadErrors  uint64 `json:"native_read_errors"`
}

var mu sync.Mutex
var state Status
var authURL string

func phase(s string) { mu.Lock(); state.Phase = s; mu.Unlock() }
func fail(s string)  { phase(s); fmt.Println(s) }
func allowed(addr net.Addr, ip string) bool {
	host, _, err := net.SplitHostPort(addr.String())
	return err == nil && host == ip
}
func tcpRelay(listener net.Listener, client string) {
	proxy := func(port string) *httputil.ReverseProxy {
		return &httputil.ReverseProxy{Director: func(r *http.Request) { r.URL.Scheme = "http"; r.URL.Host = "127.0.0.1:" + port; r.Host = r.URL.Host }, ErrorHandler: func(w http.ResponseWriter, r *http.Request, e error) {
			http.Error(w, "private runtime unavailable", 502)
		}}
	}
	streaming := proxy("49100")
	control := proxy("9048")
	server := http.Server{ReadHeaderTimeout: 5 * time.Second, IdleTimeout: 90 * time.Second, Handler: privateRelayHandler(client, streaming, control)}
	server.Serve(listener)
}
func privateRelayHandler(client string, streaming, control http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host, _, err := net.SplitHostPort(r.RemoteAddr)
		if err != nil || host != client {
			http.Error(w, "peer refused", 403)
			return
		}
		if r.URL.Path == "/sign_in" && r.Method == "GET" {
			streaming.ServeHTTP(w, r)
			return
		}
		if r.URL.Path == "/omnistream/control" && r.Method == "POST" {
			control.ServeHTTP(w, r)
			return
		}
		http.NotFound(w, r)
	})
}

type Session struct {
	conn *net.UDPConn
	last time.Time
	peer net.Addr
}

func udpRelay(pc net.PacketConn, client string) {
	udpRelayTo(pc, client, "127.0.0.1:47998")
}
func udpRelayTo(pc net.PacketConn, client, target string) {
	sessions := map[string]*Session{}
	var lock sync.Mutex
	remove := func(key string, s *Session) {
		lock.Lock()
		if sessions[key] == s {
			delete(sessions, key)
		}
		lock.Unlock()
		s.conn.Close()
	}
	done := make(chan struct{})
	defer close(done)
	defer func() {
		lock.Lock()
		defer lock.Unlock()
		for _, s := range sessions {
			s.conn.Close()
		}
	}()
	go func() {
		ticker := time.NewTicker(15 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-done:
				return
			case <-ticker.C:
				lock.Lock()
				for key, s := range sessions {
					if time.Since(s.last) > 90*time.Second {
						s.conn.Close()
						delete(sessions, key)
					}
				}
				lock.Unlock()
			}
		}
	}()
	buffer := make([]byte, 65535)
	for {
		n, peer, err := pc.ReadFrom(buffer)
		if err != nil {
			return
		}
		if !allowed(peer, client) {
			continue
		}
		key := peer.String()
		lock.Lock()
		session := sessions[key]
		if session == nil {
			if len(sessions) >= 32 {
				lock.Unlock()
				continue
			}
			remote, err := net.ResolveUDPAddr("udp", target)
			if err != nil {
				lock.Unlock()
				continue
			}
			conn, err := net.DialUDP("udp", nil, remote)
			if err != nil {
				lock.Unlock()
				continue
			}
			session = &Session{conn: conn, last: time.Now(), peer: peer}
			sessions[key] = session
			go func(key string, s *Session) {
				defer remove(key, s)
				reply := make([]byte, 65535)
				for {
					n, err := s.conn.Read(reply)
					if err != nil {
						mu.Lock()
						state.NativeReadErrors++
						mu.Unlock()
						return
					}
					_, err = pc.WriteTo(reply[:n], s.peer)
					mu.Lock()
					if err != nil {
						state.MediaWriteErrors++
					} else {
						state.MediaOut++
					}
					mu.Unlock()
					lock.Lock()
					if sessions[key] == s {
						s.last = time.Now()
					}
					lock.Unlock()
				}
			}(key, session)
		}
		session.last = time.Now()
		lock.Unlock()
		_, err = session.conn.Write(buffer[:n])
		mu.Lock()
		state.MediaIn++
		if err != nil {
			state.NativeWriteErrors++
		}
		mu.Unlock()
		if err != nil {
			remove(key, session)
		}
	}
}
func main() {
	configPath := flag.String("config", "transport-plan.json", "Bounded private transport plan")
	root := flag.String("state-dir", "node-state", "Private ephemeral node state in Colab only")
	authorized := flag.Bool("connect-authorized", false, "Only after explicit user authorization for this new private node")
	flag.Parse()
	raw, err := os.ReadFile(*configPath)
	if err != nil {
		panic("transport plan unavailable")
	}
	var cfg Config
	if json.Unmarshal(raw, &cfg) != nil {
		panic("invalid transport plan")
	}
	client, err := netip.ParseAddr(cfg.ClientIP)
	if err != nil || !netip.MustParsePrefix("100.64.0.0/10").Contains(client) || len(cfg.TailnetHash) != 64 || !regexp.MustCompile(`^[a-z][a-z0-9-]{0,62}$`).MatchString(cfg.Hostname) {
		panic("unapproved transport scope")
	}
	state = Status{Phase: "plan_only_no_network_started", TCP: 49100, UDP: 47998, ClientOnly: cfg.ClientIP}
	if !*authorized {
		json.NewEncoder(os.Stdout).Encode(map[string]any{"hostname": cfg.Hostname, "ephemeral": true, "tailnet_only": true, "client_only": cfg.ClientIP, "tcp_port": 49100, "udp_port": 47998, "no_other_ports": true, "public_funnel": false, "network_started": false})
		return
	}
	if err = os.MkdirAll(*root, 0700); err != nil {
		panic("private state directory unavailable")
	}
	os.Chmod(*root, 0700)
	server := &tsnet.Server{Dir: filepath.Clean(*root), Hostname: cfg.Hostname, Ephemeral: true, Logf: func(string, ...any) {}, UserLogf: func(string, ...any) {}}
	defer server.Close()
	phase("awaiting_private_network_authorization")
	http.HandleFunc("/status", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "GET" {
			w.WriteHeader(405)
			return
		}
		mu.Lock()
		defer mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(state)
	})
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" || r.Method != "GET" {
			http.NotFound(w, r)
			return
		}
		mu.Lock()
		s := state
		link := authURL
		mu.Unlock()
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Header().Set("Cache-Control", "no-store")
		fmt.Fprintf(w, "<!doctype html><html lang=fr><meta charset=utf-8><title>OmniStream — connexion privée Justin</title><body><h1>Connexion privée du L4 Justin</h1><p>État : %s</p><p>Nœud temporaire %s ; uniquement TCP 49100 et UDP 47998 ; un seul PC autorisé.</p>", html.EscapeString(s.Phase), html.EscapeString(cfg.Hostname))
		if link != "" {
			fmt.Fprintf(w, "<p><a href=\"%s\">Autoriser ce nœud dans le réseau Tailscale du PC</a></p>", html.EscapeString(link))
		}
		fmt.Fprint(w, "<p>Aucun Funnel public, routage de sous-réseau, SSH ou accès aux autres ports.</p></body></html>")
	})
	go func() {
		if err := http.ListenAndServe("127.0.0.1:9050", nil); err != nil {
			fail("loopback_status_unavailable")
		}
	}()
	local, err := server.LocalClient()
	if err != nil {
		fail("private_client_initialization_failed")
		return
	}
	go func() {
		for {
			status, err := local.Status(context.Background())
			if err == nil {
				mu.Lock()
				authURL = status.AuthURL
				mu.Unlock()
			}
			time.Sleep(time.Second)
		}
	}()
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()
	status, err := server.Up(ctx)
	if err != nil {
		fail("private_network_not_authorized")
		return
	}
	if status.CurrentTailnet == nil {
		fail("private_network_identity_missing")
		return
	}
	digest := sha256.Sum256([]byte(status.CurrentTailnet.Name))
	if hex.EncodeToString(digest[:]) != cfg.TailnetHash {
		fail("private_network_does_not_match_pc")
		return
	}
	var own netip.Addr
	for _, ip := range status.TailscaleIPs {
		if ip.Is4() {
			own = ip
			break
		}
	}
	if !own.IsValid() {
		fail("private_ipv4_unavailable")
		return
	}
	listener, err := server.Listen("tcp", net.JoinHostPort(own.String(), "49100"))
	if err != nil {
		fail("private_signaling_listener_failed")
		return
	}
	defer listener.Close()
	packets, err := server.ListenPacket("udp4", net.JoinHostPort(own.String(), "47998"))
	if err != nil {
		fail("private_media_listener_failed")
		return
	}
	defer packets.Close()
	mu.Lock()
	state.Phase = "private_relay_ready"
	state.PrivateIP = own.String()
	authURL = ""
	mu.Unlock()
	fmt.Println("PRIVATE_RELAY_READY: one peer; TCP 49100; UDP 47998")
	go udpRelay(packets, cfg.ClientIP)
	tcpRelay(listener, cfg.ClientIP)
}
