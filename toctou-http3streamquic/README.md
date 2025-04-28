# toctou in ip and stream causes bypass ip validation

## this vulnerabelity occurs because 
```rust
  while let Some(buf) = stream.recv_data().await? {
        body.extend_from_slice(buf.chunk());
    }
```

it'll wait untill we send the data, and we can use that to wait for our ip changing. we use STREAM data. to send each chunk of the http
what i mean chunk in here the server will auto respond untill we call Close() on the stream. so if we open stream and not close it the server think
we still connected. we use sleep to change our ip and send the stream.

for more you can check in `main.go` files