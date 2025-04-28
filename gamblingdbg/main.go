// client.go
package main

import (
	"context"
	"crypto/tls"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"time"

	quic "github.com/quic-go/quic-go"
	http3 "github.com/quic-go/quic-go/http3"
)

func main() {
	pc1, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.ParseIP("127.0.0.1"), Port: 0})
	if err != nil {
		panic(err)
	}
	defer pc1.Close()
	pc2, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.ParseIP("127.0.0.3"), Port: 0})
	if err != nil {
		panic(err)
	}
	defer pc2.Close()

	dialAddress := "127.0.0.1:5001"

	tlsConf := &tls.Config{InsecureSkipVerify: true, NextProtos: []string{http3.NextProtoH3}}
	quicConf := &quic.Config{
		MaxIdleTimeout:  10 * time.Second,
		KeepAlivePeriod: 10 * time.Millisecond,
	}
	tr := quic.Transport{
		Conn: pc1,
	}
	defer tr.Close()
	tr2 := quic.Transport{
		Conn: pc2,
	}
	defer tr2.Close()

	addr, err := net.ResolveUDPAddr("udp", dialAddress)
	if err != nil {
		panic(err)
	}

	// var packetsPath1, packetsPath2 atomic.Int64
	// const rtt = 5 * time.Millisecond
	// proxy := quicproxy.Proxy{
	// 	Conn:       pc1,
	// 	ServerAddr: addr,
	// 	// DelayPacket: func(dir quicproxy.Direction, from, to net.Addr, _ []byte) time.Duration {
	// 	// 	var port int
	// 	// 	switch dir {
	// 	// 	case quicproxy.DirectionIncoming:
	// 	// 		port = from.(*net.UDPAddr).Port
	// 	// 	case quicproxy.DirectionOutgoing:
	// 	// 		port = to.(*net.UDPAddr).Port
	// 	// 	}
	// 	// 	switch port {
	// 	// 	case tr.Conn.LocalAddr().(*net.UDPAddr).Port:
	// 	// 		packetsPath1.Add(1)
	// 	// 	case tr2.Conn.LocalAddr().(*net.UDPAddr).Port:
	// 	// 		packetsPath2.Add(1)
	// 	// 	default:
	// 	// 		fmt.Println("address not found", from)
	// 	// 	}
	// 	// 	return rtt / 2
	// 	// },
	// }
	// if err = proxy.Start(); err != nil {
	// 	panic(err)
	// }
	// defer proxy.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	// fmt.Printf("running proxy on %s\n", proxy.LocalAddr().String())
	// fmt.Println("starting dialing the proxy")
	// if using proxy dialing proxy.LocalAddr()
	conn, err := tr.Dial(ctx, addr, tlsConf, quicConf)
	if err != nil {
		panic(err)
	}
	defer conn.CloseWithError(0, "")

	h3tr := &http3.Transport{
		TLSClientConfig: &tls.Config{
			ClientSessionCache: tls.NewLRUClientSessionCache(100),
		},

		Dial: func(ctx context.Context, addr string, tlsConf *tls.Config, quicConf *quic.Config) (quic.EarlyConnection, error) {
			a, err := net.ResolveUDPAddr("udp", addr)
			if err != nil {
				return nil, err
			}
			return tr2.DialEarly(ctx, a, tlsConf, quicConf)
		},
	}
	defer h3tr.Close()

	cc := h3tr.NewClientConn(conn)
	sendRequest(ctx, cc, "first-payload")

	// sendRequest(ctx, cc, "second-payload")

}

func sendRequest(ctx context.Context, cc *http3.ClientConn, payload string) {
	stream, err := cc.OpenRequestStream(ctx)
	if err != nil {
		log.Fatalf("OpenRequestStream: %v", err)
	}

	req := &http.Request{
		Method: http.MethodPost,
		URL:    &url.URL{Scheme: "https", Host: "127.0.0.1:5001"},
		Header: http.Header{"User-Agent": {"migrate-client"}},
	}
	if err := stream.SendRequestHeader(req); err != nil {
		log.Fatalf("SendRequestHeader: %v", err)
	}

	if _, err := stream.Write([]byte(payload)); err != nil {
		log.Fatalf("Write: %v", err)
	}
	if err := stream.Close(); err != nil {
		log.Fatalf("Stream.Close: %v", err)
	}

	resp, err := stream.ReadResponse()
	if err != nil {
		log.Fatalf("ReadResponse: %v", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	fmt.Printf("← response for %q: %q\n\n", payload, string(body))
}

func scale_duration(t time.Duration) time.Duration {
	scaleFactor := 1
	if f, err := strconv.Atoi(os.Getenv("TIMESCALE_FACTOR")); err == nil { // parsing "" errors, so this works fine if the env is not set
		scaleFactor = f
	}
	if scaleFactor == 0 {
		panic("TIMESCALE_FACTOR is 0")
	}
	return time.Duration(scaleFactor) * t
}
