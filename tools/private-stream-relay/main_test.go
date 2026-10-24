package main

import (
	"bytes"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestPrivateGatewayOnlyRoutesDeclaredPathsFromExactPC(t *testing.T) {
	calls := []string{}
	stream := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { calls = append(calls, "stream") })
	control := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls = append(calls, "control")
		if r.Header.Get("Authorization") != "Bearer synthetic-test" {
			t.Error("Control authentication header lost")
		}
	})
	handler := privateRelayHandler("100.78.12.34", stream, control)
	for _, c := range []struct {
		peer, method, path string
		status             int
	}{{"100.78.12.34:1234", "GET", "/sign_in?peer_id=test", 200}, {"100.78.12.34:1234", "POST", "/omnistream/control", 200}, {"100.78.12.35:1234", "POST", "/omnistream/control", 403}, {"100.78.12.34:1234", "GET", "/other", 404}, {"100.78.12.34:1234", "GET", "/omnistream/control", 404}} {
		request := httptest.NewRequest(c.method, c.path, nil)
		request.RemoteAddr = c.peer
		request.Header.Set("Authorization", "Bearer synthetic-test")
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != c.status {
			t.Fatalf("Wrong gateway status: %d", response.Code)
		}
	}
	if len(calls) != 2 || calls[0] != "stream" || calls[1] != "control" {
		t.Fatal("Unexpected route forwarded")
	}
}

func TestUDPRecoversWhenNativePortOpensAfterFirstPacket(t *testing.T) {
	reserve, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	target := reserve.LocalAddr().String()
	reserve.Close()
	relay, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer relay.Close()
	mu.Lock()
	state = Status{}
	mu.Unlock()
	done := make(chan struct{})
	go func() { udpRelayTo(relay, "127.0.0.1", target); close(done) }()
	client, err := net.Dial("udp", relay.LocalAddr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	if _, err = client.Write([]byte("early")); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(2 * time.Second)
	for {
		mu.Lock()
		failed := state.NativeReadErrors > 0
		mu.Unlock()
		if failed {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("Native closed-port error was not observed")
		}
		time.Sleep(5 * time.Millisecond)
	}
	native, err := net.ListenPacket("udp", target)
	if err != nil {
		t.Fatal(err)
	}
	defer native.Close()
	echoed := make(chan struct{})
	go func() {
		defer close(echoed)
		buffer := make([]byte, 256)
		native.SetReadDeadline(time.Now().Add(2 * time.Second))
		n, peer, e := native.ReadFrom(buffer)
		if e == nil {
			native.WriteTo(buffer[:n], peer)
		}
	}()
	expected := []byte("real-native-reply")
	client.SetReadDeadline(time.Now().Add(2 * time.Second))
	if _, err = client.Write(expected); err != nil {
		t.Fatal(err)
	}
	buffer := make([]byte, 256)
	n, err := client.Read(buffer)
	if err != nil {
		t.Fatal("Reply reader did not recover:", err)
	}
	if !bytes.Equal(buffer[:n], expected) {
		t.Fatal("Wrong recovered reply")
	}
	<-echoed
	mu.Lock()
	returned := state.MediaOut
	mu.Unlock()
	if returned == 0 {
		t.Fatal("No successful return traffic recorded")
	}
	relay.Close()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("Relay did not stop")
	}
}

func TestUDPRejectsUnapprovedClient(t *testing.T) {
	relay, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer relay.Close()
	mu.Lock()
	state = Status{}
	mu.Unlock()
	done := make(chan struct{})
	go func() { udpRelayTo(relay, "100.78.12.34", "127.0.0.1:1"); close(done) }()
	client, err := net.Dial("udp", relay.LocalAddr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	client.Write([]byte("unapproved"))
	client.SetReadDeadline(time.Now().Add(100 * time.Millisecond))
	if _, err = client.Read(make([]byte, 16)); err == nil {
		t.Fatal("Unapproved client received data")
	}
	mu.Lock()
	forwarded := state.MediaIn
	mu.Unlock()
	if forwarded != 0 {
		t.Fatal("Unapproved client reached native relay")
	}
	relay.Close()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("Relay did not stop")
	}
}
