

import argparse
import asyncio
import random
import string
import logging
import os
import pickle
import ssl
from time import sleep
import time
from collections import deque
from typing import BinaryIO, Deque, Dict, List, Optional, Union, cast
from urllib.parse import urlparse, urlencode, parse_qs
import aioquic
from aioquic.asyncio.client import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.packet_builder import QuicPacketBuilder
# from qh3.h0.connection import H0_ALPN, H0Connection
from aioquic.h3.connection import H3_ALPN, ErrorCode, H3Connection
from aioquic.h3.events import DataReceived, H3Event, HeadersReceived, PushPromiseReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent
from tests import perform_tests
logger = logging.getLogger("client")

HttpConnection = Union[H3Connection]

USER_AGENT = "qh3/" + aioquic.__version__


class URL:
    def __init__(self, url: str) -> None:
        parsed = urlparse(url)
        self.authority = parsed.netloc
        self.full_path = parsed.path or "/"
        if parsed.query:
            self.full_path += "?" + parsed.query
        self.scheme = parsed.scheme


class HttpRequest:
    def __init__(
        self,
        method: str,
        url: URL,
        content: bytes = b"",
        headers: Optional[Dict] = None,
    ) -> None:
        if headers is None:
            headers = {}
        self.content = content
        self.headers = headers
        self.method = method
        self.url = url


class HttpClient(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.pushes: Dict[int, Deque[H3Event]] = {}
        self._request_events: Dict[int, Deque[H3Event]] = {}
        self._request_waiter: Dict[int, asyncio.Future[Deque[H3Event]]] = {}
        if self._quic.configuration.alpn_protocols[0].startswith("hq-"):
            print("ERROR: Missing python-module qh3.h0. Program exits.")
            exit(1)
            # self._http = H0Connection(self._quic)
        else:
            self._http = H3Connection(self._quic)


    def http_event_received(self, event: H3Event) -> None:
        if isinstance(event, (HeadersReceived, DataReceived)):
            stream_id = event.stream_id
            if stream_id in self._request_events:
                self._request_events[event.stream_id].append(event)
                if event.stream_ended:
                    request_waiter = self._request_waiter.pop(stream_id)
                    request_waiter.set_result(self._request_events.pop(stream_id))

            elif event.push_id in self.pushes:
                self.pushes[event.push_id].append(event)

        elif isinstance(event, PushPromiseReceived):
            self.pushes[event.push_id] = deque()
            self.pushes[event.push_id].append(event)

    def quic_event_received(self, event: QuicEvent) -> None:
        if self._http is not None:
            for http_event in self._http.handle_event(event):
                self.http_event_received(http_event)


async def perform_normal_http_request(
    client: HttpClient,
    urls: List[str],
    params: Optional[str]=None,
    headers: Optional[list]=None,
    data: Optional[str]=None,
    include: bool=True,
    cookie: str="",
    num_streams: int = 1,  # Default to 1 stream per request
) -> str:
    """
    Perform HTTP requests and process the responses.

    Args:
        client: The HTTP client instance to use.
        urls: List of URLs to send requests to.
        params: Optional parameters to include in the GET requests
        data: Optional data to include in the request body.
        include: Flag indicating whether to include headers in the response output.
        num_streams: The number of streams to initiate for each request.
    """
    start = time.time()
    http_events_list = []


    for url in urls:
        stream_id = client._quic.get_next_available_stream_id()

        parsed_url = urlparse(url)
        query_params = params
        full_path = parsed_url.path + '?' + query_params if query_params else parsed_url.path

        if headers is None:
            headers = [
                    (b":method", b"GET" if data is None else b"POST"),
                    (b":scheme", b"https"),
                    (b":authority", parsed_url.netloc.encode()),
                    (b":path", full_path.encode()),
                    (b"user-agent", b"test")
                ]
        print(headers)
        client._http.send_headers(
            stream_id=stream_id,
            headers=headers,
            end_stream=True if data is None else False,
        )
        
        if data is not None:
            client._http.send_data(
                stream_id=stream_id, data=data.encode(), end_stream=True
            )

        client.transmit()

        waiter = client._loop.create_future()
        client._request_events[stream_id] = deque()
        client._request_waiter[stream_id] = waiter
        # Wait for response
        http_events = await asyncio.shield(waiter)
        return http_events


def process_http_pushes(
    client: HttpClient,
    include: bool,
    output_dir: Optional[str],
) -> None:
    """
    Process HTTP/3 server push events.

    Args:
        client: The HTTP client instance to use.
        include: Flag indicating whether to include headers in the response output.
        output_dir: The directory to write the responses to.
    """
    for _, http_events in client.pushes.items():
        method = ""
        octets = 0
        path = ""
        for http_event in http_events:
            if isinstance(http_event, DataReceived):
                octets += len(http_event.data)
            elif isinstance(http_event, PushPromiseReceived):
                for header, value in http_event.headers:
                    if header == b":method":
                        method = value.decode()
                    elif header == b":path":
                        path = value.decode()
        logger.info("Push received for %s %s : %s bytes", method, path, octets)


async def main(
    configuration: QuicConfiguration,
    urls: List[str],
    data: Optional[str],
    local_port: int,
    num_streams: int = 1,  # Default to 1 stream per request
) -> None:
    """
    Main function to execute HTTP/3 requests.

    Args:
        configuration: The QUIC configuration.
        urls: List of URLs to make requests to.
        data: Optional data to include in the request body.
        include: Flag indicating whether to include headers in the response output.
        local_port: The local port to bind to.
        zero_rtt: Flag indicating whether to enable 0-RTT connection.
        num_streams: The number of streams to initiate for each request.
    """
    # Parse the first URL
    parsed = urlparse(urls[0])
    assert parsed.scheme == "https", "Only https:// URLs are supported."
    host = parsed.hostname
    if parsed.port is not None:
        port = parsed.port
    else:
        port = 443

    # Validate and process subsequent URLs
    for i in range(1, len(urls)):
        _p = urlparse(urls[i])

        # Fill in if empty
        _scheme = _p.scheme or parsed.scheme
        _host = _p.hostname or host
        _port = _p.port or port

        assert _scheme == parsed.scheme, "URL scheme doesn't match"
        assert _host == host, "URL hostname doesn't match"
        assert _port == port, "URL port doesn't match"

        # Reconstruct URL with new hostname and port
        _p = _p._replace(scheme=_scheme)
        _p = _p._replace(netloc="{}:{}".format(_host, _port))
        _p = urlparse(_p.geturl())
        urls[i] = _p.geturl()

    async with connect(
        host,
        port,
        configuration=configuration,
        create_protocol=HttpClient,
        local_port=local_port,
    ) as client:
        client = cast(HttpClient, client)
        urls = [urls[0]]
        print("TARGET-URL:", urls[0])
        print("TESTING NORMAL REQUEST:")
        try:
            res = await asyncio.wait_for(perform_normal_http_request(client=client, urls=urls), timeout=2)
            print("NORMAL REQUEST SUCCEEDED, PROCEEDING WITH TESTS")
        except Exception as e:
            print(e)
            exit(-1)

        # Perform tests
        print("PERFORM TESTS:")
        num_tests = await perform_tests(client, urls[0], perform_normal_http_request)
        print(num_tests, "TESTS COMPLETED")

        # Close QUIC connection
        client._quic.close(error_code=ErrorCode.H3_NO_ERROR)


if __name__ == "__main__":
    # Default QUIC configuration
    defaults = QuicConfiguration(is_client=True)

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="HTTP/3 client")
    parser.add_argument(
        "url", type=str, nargs="+", help="the URL to query (must be HTTPS)"
    )
    parser.add_argument(
        "--ca-certs", type=str, help="load CA certificates from the specified file"
    )
    parser.add_argument(
        "-d", "--data", type=str, help="send the specified data in a POST request"
    )
    parser.add_argument(
        "-q",
        "--quic-log",
        type=str,
        help="log QUIC events to QLOG files in the specified directory",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="increase logging verbosity"
    )
    parser.add_argument(
        "--local-port",
        type=int,
        default=0,
        help="local port to bind for connections",
    )
    parser.add_argument(
        "--num-streams",
        type=int,
        default=1,
        help="the number of stream to send",
    )
    parser.add_argument(
        "-l",
        "--secrets-log",
        type=str,
        help="log secrets to a file, for use with Wireshark",
    )

    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    # Prepare QUIC configuration
    configuration = QuicConfiguration(
        is_client=True, alpn_protocols=H3_ALPN
    )
    if args.ca_certs:
        configuration.load_verify_locations(args.ca_certs)

    if args.secrets_log:
        configuration.secrets_log_file = open(args.secrets_log, "a")

    configuration.verify_mode = ssl.CERT_NONE

    # Run the main event loop
    asyncio.run(
        main(
            configuration=configuration,
            urls=args.url,
            data=args.data,
            local_port=args.local_port,
            num_streams=args.num_streams,
        )
    )
