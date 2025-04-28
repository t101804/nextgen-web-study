// server

use bytes::{Buf, Bytes};
use h3::{client::RequestStream, quic::BidiStream, server::Connection};
use h3_quinn::quinn::{self, crypto::rustls::QuicServerConfig};
use http::{Request, StatusCode};
use quinn::{Endpoint, ServerConfig};
use rcgen::{CertifiedKey, generate_simple_self_signed};
use rustls::pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer};
use std::{error::Error, net::{Ipv4Addr, SocketAddr}, sync::Arc, thread::sleep, vec};

// const SERVER_NAME: &str = "localhost";
// const LOCALHOST_V4: std::net::IpAddr = std::net::IpAddr::V4("0.0.0.0");
const SERVER_ADDR: SocketAddr = SocketAddr::new(std::net::IpAddr::V4(Ipv4Addr::new(0, 0, 0, 0)), 5001);
// const LOCALHOST_V6: std::net::IpAddr = std::net::IpAddr::V6(std::net::Ipv6Addr::LOCALHOST);
// const SERVER_ADDR_V6: SocketAddr = SocketAddr::new(LOCALHOST_V6, 5001);

static ALPN: &[u8] = b"h3";

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    // 1) Load TLS cert & key
    // let cert_chain = quinn::Certi
    let (cert_der, key_pkcs8) = generate_self_signed_cert().await?;
    let key_der: PrivateKeyDer<'static> = PrivateKeyDer::Pkcs8(key_pkcs8);
    // let server_config = quinn::ServerConfig::with_single_cert(
    //     vec![cert_der.clone()],
    //     PrivateKeyDer::from(key_der.clone_key()),
    // );
    let mut tls_config = rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(
            vec![cert_der.clone()],
            PrivateKeyDer::from(key_der.clone_key()),
        )?;
    tls_config.max_early_data_size = u32::MAX;
    tls_config.alpn_protocols = vec![ALPN.into()];
    let server_config =
        quinn::ServerConfig::with_crypto(Arc::new(QuicServerConfig::try_from(tls_config)?));

    server(server_config).await?;
    Ok(())
}

 async fn read_payload(
    stream: &mut h3::server::RequestStream<h3_quinn::BidiStream<Bytes>, Bytes>,
) -> Result<Option<Vec<u8>>, h3::Error>

{
    let mut body = Vec::new();
    while let Some(buf) = stream.recv_data().await? {
        body.extend_from_slice(buf.chunk());
    }
    Ok(Some(body))
}

// async fn ip_check(quic_conn: &quinn::Connection) {}
async fn server(config: ServerConfig) -> Result<(), Box<dyn Error>> {
    let endpoint = Endpoint::server(config, SERVER_ADDR)?;
    // let (endpoint, mut incoming) = h3::quic::

    while let Some(quin_conn) = endpoint.accept().await {
        // let conn = conn.await?;
        println!("New Connection being attempted");
        tokio::spawn(async move {
            match quin_conn.await {
                Ok(quin_conn) => {
                    println!("Connection established with QUIC");
                    // let mut server_builder = h3::server::builder();
                    // let mut h3_conn = server_builder.build(conn).await.unwrap_or(default::h3_conn());
                    // let h3 = h3_quinn::Connection::new(conn);
                    let mut h3_conn: h3::server::Connection<_, Bytes> =
                        h3::server::Connection::new(h3_quinn::Connection::new(quin_conn.clone()))
                            .await
                            .unwrap();

                    loop {
                        match h3_conn.accept().await {
                            Ok(Some((req, mut stream))) => {
                                // let (req, mut stream) = resolver;
                                // tokio::spawn({
                                // let quin_conn = quin_conn.clone();
                                // async move {
                                // ip_check(&quin_conn).await;
                                println!("[-] ip-before-read-body==> {:?}", quin_conn.remote_address().ip());
                                let resp = http::Response::builder()
                                    .status(StatusCode::OK)
                                    .body(())
                                    .unwrap();
                          
                                let Some(payload) = read_payload(&mut stream).await.unwrap() else {
                                    // return Ok(());
                                    println!("no payload");
                                    break;
                                };
                                println!("[x] body==> {:?}", payload);
                                tokio::time::sleep(std::time::Duration::from_secs(1)).await;
                                println!("[+] ip-after-read-body==> {:?}", quin_conn.remote_address().ip());
                              
                                stream.send_response(resp).await.unwrap();
                                stream.send_data(Bytes::from("ancok")).await.unwrap();
                                stream.finish().await.unwrap();
                            }
                            Ok(None) => {
                                break;
                            }
                            Err(e) => {
                                match e.get_error_level() {
                                    // break on connection errors
                                    h3::error::ErrorLevel::ConnectionError => {
                                        println!("Request malformed error: {:?}", e);
                                        break;
                                    }
                                    // continue on stream errors
                                    h3::error::ErrorLevel::StreamError => {
                                        println!("Stream error: {:?}", e);
                                        continue; // Continue on stream errors
                                    }
                                }

                                // println!("Error on accepting http/3: {:?}", e);
                                // break;
                            }
                        }
                    }
                }
                Err(e) => {
                    println!("Error establishing QUIC connection: {:?}", e);
                }
            }
        });
    }
    endpoint.wait_idle().await;
    Ok(())
}
async fn generate_self_signed_cert()
-> Result<(CertificateDer<'static>, PrivatePkcs8KeyDer<'static>), Box<dyn Error>> {
    let cert = rcgen::generate_simple_self_signed(vec!["localhost".to_string()])?;
    let cert_der = CertificateDer::from(cert.cert);
    let key = PrivatePkcs8KeyDer::from(cert.key_pair.serialize_der());
    Ok((cert_der, key))
}
