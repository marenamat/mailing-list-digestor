# Mail Receiver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Rust SMTP service that accepts mail for one configured address and saves each message as a `.eml` file in a Maildir-format directory shared with the digestor.

**Architecture:** A minimal SMTP server using `mailin-embedded` filters incoming messages by recipient address at SMTP level, accumulates the message body across chunks, and writes it atomically to `/data/maildir/new/` via the standard Maildir `tmp/` → `new/` rename pattern. No outbound network access. Configuration entirely via environment variables.

**Tech Stack:** Rust 1.75+, `mailin-embedded` 0.7, `thiserror` 1, `log` + `env_logger`, `gcr.io/distroless/static` runtime image

---

## Scope note

This is **Plan 1 of 4**. Subsequent plans cover:

- Plan 2: Digestor (Python) — Maildir watcher, email parsing, SQLite schema, ollama triage, Claude pipeline, digest generation, archive fetch, health endpoint
- Plan 3: Notifier (Python) — Matrix bot, notification delivery, reply handling, cancel commands
- Plan 4: Deployment — `compose.yaml`, `.env.example`, network policy, integration smoke test

---

## File Map

All files are new (empty repo except DESING.md).

```
Cargo.toml                          workspace root
mail-receiver/
  Cargo.toml                        package manifest and dependencies
  src/
    lib.rs                          exports modules; pub fn run(cfg) entry point
    main.rs                         reads config, calls run(), exits on error
    config.rs                       Config struct; from_env() -> Result<Config, ConfigError>
    maildir.rs                      ensure_dirs(); write_message() atomic tmp→new rename
    handler.rs                      MailHandler: impl mailin_embedded::Handler
  tests/
    integration_test.rs             unit tests for config/maildir/handler + full SMTP e2e
  Dockerfile                        multi-stage: rust:1-alpine builder → distroless/static
config/
  context.md.example                template for digestor evaluation context
  lists.yaml.example                template for WG→list-address mapping
.env.example                        all required env vars with placeholder values
```

---

## Task 1: Workspace scaffold

**Files:**
- Create: `Cargo.toml` (workspace)
- Create: `mail-receiver/Cargo.toml`
- Create: `mail-receiver/src/main.rs` (stub)

- [ ] **Step 1: Create workspace `Cargo.toml` at repo root**

```toml
[workspace]
members = ["mail-receiver"]
resolver = "2"
```

- [ ] **Step 2: Create `mail-receiver/Cargo.toml`**

```toml
[package]
name = "mail-receiver"
version = "0.1.0"
edition = "2021"

[lib]
name = "mail_receiver"
path = "src/lib.rs"

[[bin]]
name = "mail-receiver"
path = "src/main.rs"

[dependencies]
mailin-embedded = "0.7"
thiserror = "1"
log = "0.4"
env_logger = "0.11"

[dev-dependencies]
# raw-TCP SMTP in tests — no extra deps needed
```

- [ ] **Step 3: Create `mail-receiver/src/main.rs` stub**

```rust
fn main() {
    println!("mail-receiver starting");
}
```

- [ ] **Step 4: Verify it compiles**

```
cd mail-receiver && cargo build
```

Expected: `Compiling mail-receiver v0.1.0` with no errors.

- [ ] **Step 5: Commit**

```bash
git add Cargo.toml mail-receiver/
git commit -m "feat(mail-receiver): scaffold Rust workspace"
```

---

## Task 2: Config module

**Files:**
- Create: `mail-receiver/src/config.rs`
- Create: `mail-receiver/src/lib.rs`
- Create: `mail-receiver/tests/integration_test.rs`

- [ ] **Step 1: Write the failing tests**

Create `mail-receiver/tests/integration_test.rs`:

```rust
#[test]
fn config_rejects_missing_recipient() {
    // isolate: remove var in case a previous test set it
    std::env::remove_var("SMTP_RECIPIENT");
    let result = mail_receiver::config::Config::from_env();
    assert!(result.is_err(), "Config must fail without SMTP_RECIPIENT");
}

#[test]
fn config_uses_defaults() {
    std::env::set_var("SMTP_RECIPIENT", "list@example.com");
    std::env::remove_var("SMTP_LISTEN_ADDR");
    std::env::remove_var("MAILDIR_PATH");
    let cfg = mail_receiver::config::Config::from_env().unwrap();
    assert_eq!(cfg.listen_addr, "0.0.0.0:25");
    assert_eq!(cfg.recipient, "list@example.com");
    assert_eq!(cfg.maildir, "/data/maildir");
}

#[test]
fn config_reads_env_overrides() {
    std::env::set_var("SMTP_RECIPIENT", "r@x.com");
    std::env::set_var("SMTP_LISTEN_ADDR", "127.0.0.1:2525");
    std::env::set_var("MAILDIR_PATH", "/tmp/md");
    let cfg = mail_receiver::config::Config::from_env().unwrap();
    assert_eq!(cfg.listen_addr, "127.0.0.1:2525");
    assert_eq!(cfg.maildir, "/tmp/md");
    std::env::remove_var("SMTP_LISTEN_ADDR");
    std::env::remove_var("MAILDIR_PATH");
}
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd mail-receiver && cargo test config --test integration_test 2>&1 | head -20
```

Expected: compile error — `mail_receiver::config` does not exist.

- [ ] **Step 3: Create `mail-receiver/src/config.rs`**

```rust
use thiserror::Error;

#[derive(Debug, Clone)]
pub struct Config {
    pub listen_addr: String,
    pub recipient: String,
    pub maildir: String,
}

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("SMTP_RECIPIENT environment variable is required")]
    MissingRecipient,
}

impl Config {
    pub fn from_env() -> Result<Self, ConfigError> {
        Ok(Config {
            listen_addr: std::env::var("SMTP_LISTEN_ADDR")
                .unwrap_or_else(|_| "0.0.0.0:25".into()),
            recipient: std::env::var("SMTP_RECIPIENT")
                .map_err(|_| ConfigError::MissingRecipient)?,
            maildir: std::env::var("MAILDIR_PATH")
                .unwrap_or_else(|_| "/data/maildir".into()),
        })
    }
}
```

- [ ] **Step 4: Create `mail-receiver/src/lib.rs`**

```rust
pub mod config;
pub mod handler;
pub mod maildir;

pub fn run(cfg: config::Config) -> std::io::Result<()> {
    todo!("implemented in Task 5")
}
```

- [ ] **Step 5: Run tests to verify they pass**

```
cd mail-receiver && cargo test config --test integration_test -- --test-threads=1
```

Expected: 3 tests pass. (`--test-threads=1` prevents env-var races between config tests.)

- [ ] **Step 6: Commit**

```bash
git add mail-receiver/src/config.rs mail-receiver/src/lib.rs mail-receiver/tests/integration_test.rs
git commit -m "feat(mail-receiver): config module with env var loading"
```

---

## Task 3: Maildir writer

**Files:**
- Create: `mail-receiver/src/maildir.rs`

- [ ] **Step 1: Write the failing tests**

Add to `mail-receiver/tests/integration_test.rs`:

```rust
// ── helpers ──────────────────────────────────────────────────────────────────

fn tmp_maildir() -> std::path::PathBuf {
    let p = std::env::temp_dir()
        .join(format!("mr-test-{}-{}", std::process::id(), next_id()));
    std::fs::create_dir_all(&p).unwrap();
    p
}

static TEST_ID: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
fn next_id() -> u64 {
    TEST_ID.fetch_add(1, std::sync::atomic::Ordering::SeqCst)
}

// ── maildir tests ─────────────────────────────────────────────────────────────

#[test]
fn maildir_ensure_dirs_creates_subdirs() {
    let root = tmp_maildir();
    mail_receiver::maildir::ensure_dirs(&root).unwrap();
    for sub in &["new", "cur", "tmp"] {
        assert!(root.join(sub).is_dir(), "missing subdir: {sub}");
    }
}

#[test]
fn maildir_write_lands_in_new() {
    let root = tmp_maildir();
    mail_receiver::maildir::ensure_dirs(&root).unwrap();
    let data = b"From: a@b.com\r\nSubject: Hi\r\n\r\nbody";
    let path = mail_receiver::maildir::write_message(&root, data).unwrap();
    assert!(path.starts_with(root.join("new")), "file not in new/: {path:?}");
    assert_eq!(std::fs::read(&path).unwrap(), data);
}

#[test]
fn maildir_two_writes_produce_distinct_files() {
    let root = tmp_maildir();
    mail_receiver::maildir::ensure_dirs(&root).unwrap();
    let p1 = mail_receiver::maildir::write_message(&root, b"msg1").unwrap();
    let p2 = mail_receiver::maildir::write_message(&root, b"msg2").unwrap();
    assert_ne!(p1, p2);
    assert_eq!(std::fs::read_dir(root.join("new")).unwrap().count(), 2);
}
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd mail-receiver && cargo test maildir --test integration_test 2>&1 | head -20
```

Expected: compile error — `mail_receiver::maildir` has no public items.

- [ ] **Step 3: Create `mail-receiver/src/maildir.rs`**

```rust
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static COUNTER: AtomicU64 = AtomicU64::new(0);

pub fn ensure_dirs(maildir: &Path) -> std::io::Result<()> {
    for sub in &["new", "cur", "tmp"] {
        fs::create_dir_all(maildir.join(sub))?;
    }
    Ok(())
}

/// Writes `data` atomically into `maildir/new/` using the standard
/// Maildir tmp→new rename pattern.
pub fn write_message(maildir: &Path, data: &[u8]) -> std::io::Result<PathBuf> {
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let pid = std::process::id();
    let seq = COUNTER.fetch_add(1, Ordering::SeqCst);
    let hostname = std::env::var("HOSTNAME").unwrap_or_else(|_| "localhost".into());
    let filename = format!("{ts}.P{pid}Q{seq}.{hostname}");

    let tmp_path = maildir.join("tmp").join(&filename);
    let new_path = maildir.join("new").join(&filename);

    {
        let mut f = fs::File::create(&tmp_path)?;
        f.write_all(data)?;
        f.sync_all()?;
    }
    fs::rename(&tmp_path, &new_path)?;
    Ok(new_path)
}
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd mail-receiver && cargo test maildir --test integration_test
```

Expected: all three maildir tests pass.

- [ ] **Step 5: Commit**

```bash
git add mail-receiver/src/maildir.rs mail-receiver/tests/integration_test.rs
git commit -m "feat(mail-receiver): atomic Maildir writer"
```

---

## Task 4: SMTP handler

**Files:**
- Create: `mail-receiver/src/handler.rs`

`mailin-embedded` 0.7 re-exports the `Handler` trait from the `mailin` crate. After `cargo build` run `cargo doc --open` inside `mail-receiver/` to see the exact method signatures — the code below follows the 0.7 API. The `Response` type wraps an SMTP reply code; `Response::new(code, message)` is the constructor (verify the exact signature in the generated docs if the build fails).

- [ ] **Step 1: Write the failing tests**

Add to `mail-receiver/tests/integration_test.rs`:

```rust
#[test]
fn handler_rejects_wrong_recipient() {
    let root = tmp_maildir();
    mail_receiver::maildir::ensure_dirs(&root).unwrap();
    let mut h = mail_receiver::handler::MailHandler::new(
        "good@example.com".into(),
        root,
    );
    let resp = h.rcpt("wrong@example.com");
    assert_eq!(resp.code, 550, "wrong recipient should yield 550, got {}", resp.code);
}

#[test]
fn handler_accepts_correct_recipient() {
    let root = tmp_maildir();
    mail_receiver::maildir::ensure_dirs(&root).unwrap();
    let mut h = mail_receiver::handler::MailHandler::new(
        "good@example.com".into(),
        root,
    );
    let resp = h.rcpt("good@example.com");
    assert_eq!(resp.code, 250, "correct recipient should yield 250, got {}", resp.code);
}

#[test]
fn handler_accepts_recipient_case_insensitive() {
    let root = tmp_maildir();
    mail_receiver::maildir::ensure_dirs(&root).unwrap();
    let mut h = mail_receiver::handler::MailHandler::new(
        "Good@Example.COM".into(),
        root,
    );
    assert_eq!(h.rcpt("good@example.com").code, 250);
}
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd mail-receiver && cargo test handler --test integration_test 2>&1 | head -20
```

Expected: compile error — `mail_receiver::handler` has no public items.

- [ ] **Step 3: Create `mail-receiver/src/handler.rs`**

```rust
use std::path::PathBuf;
use mailin_embedded::{Handler, Response};
use crate::maildir;

pub struct MailHandler {
    recipient: String,
    maildir: PathBuf,
    buf: Vec<u8>,
}

impl MailHandler {
    pub fn new(recipient: String, maildir: PathBuf) -> Self {
        Self { recipient, maildir, buf: Vec::new() }
    }

    fn smtp_ok() -> Response {
        Response::new(250, vec![], false, "OK")
    }

    fn smtp_reject_mailbox() -> Response {
        Response::new(550, vec![], false, "No such mailbox")
    }

    fn smtp_start_data() -> Response {
        Response::new(354, vec![], false, "Start mail input; end with <CRLF>.<CRLF>")
    }

    fn smtp_temp_fail() -> Response {
        Response::new(451, vec![], false, "Temporary failure, try again later")
    }
}

impl Handler for MailHandler {
    fn rcpt(&mut self, to: &str) -> Response {
        let to_clean = to.trim_matches(|c| c == '<' || c == '>');
        if to_clean.to_lowercase() == self.recipient.to_lowercase() {
            Self::smtp_ok()
        } else {
            log::warn!("Rejected recipient: {to}");
            Self::smtp_reject_mailbox()
        }
    }

    fn data_start(
        &mut self,
        _domain: &str,
        _from: &str,
        _is8bit: bool,
        _to: &[String],
    ) -> Response {
        self.buf.clear();
        Self::smtp_start_data()
    }

    fn data(&mut self, buf: &[u8]) -> Response {
        self.buf.extend_from_slice(buf);
        Self::smtp_ok()
    }

    fn data_end(&mut self) -> Response {
        match maildir::write_message(&self.maildir, &self.buf) {
            Ok(path) => {
                log::info!("Saved {} bytes → {}", self.buf.len(), path.display());
                Self::smtp_ok()
            }
            Err(e) => {
                log::error!("Failed to write message: {e}");
                Self::smtp_temp_fail()
            }
        }
    }
}
```

If the compiler reports `Response::new` does not exist with that signature, run `cargo doc --open` and locate the correct constructor. The four helper methods (`smtp_ok`, etc.) are the only place that needs adjustment.

- [ ] **Step 4: Run tests to verify they pass**

```
cd mail-receiver && cargo test handler --test integration_test
```

Expected: all three handler tests pass.

- [ ] **Step 5: Commit**

```bash
git add mail-receiver/src/handler.rs mail-receiver/tests/integration_test.rs
git commit -m "feat(mail-receiver): SMTP handler with recipient filter"
```

---

## Task 5: Server entry point + end-to-end test

**Files:**
- Modify: `mail-receiver/src/lib.rs` (replace `todo!` in `run()`)
- Modify: `mail-receiver/src/main.rs`

- [ ] **Step 1: Write the end-to-end test**

Add to `mail-receiver/tests/integration_test.rs`:

```rust
/// Spawns a real server on a local port, sends a message via raw TCP SMTP,
/// and asserts the .eml file appears in new/.
#[test]
fn end_to_end_smtp_to_maildir() {
    use std::io::{BufRead, BufReader, Write};
    use std::net::TcpStream;
    use std::thread;
    use std::time::Duration;

    let maildir = tmp_maildir().join("e2e");
    mail_receiver::maildir::ensure_dirs(&maildir).unwrap();

    let addr = "127.0.0.1:12587";
    let md = maildir.clone();
    thread::spawn(move || {
        let cfg = mail_receiver::config::Config {
            listen_addr: addr.into(),
            recipient: "rcpt@test.local".into(),
            maildir: md.to_str().unwrap().into(),
        };
        mail_receiver::run(cfg).expect("server failed");
    });

    // Give the server time to bind
    thread::sleep(Duration::from_millis(200));

    let stream = TcpStream::connect(addr).expect("could not connect to test server");
    stream.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
    let mut reader = BufReader::new(stream.try_clone().unwrap());
    let mut w = stream;

    macro_rules! read_line {
        () => {{
            let mut l = String::new();
            reader.read_line(&mut l).unwrap();
            l
        }};
    }

    let banner = read_line!();
    assert!(banner.starts_with("220"), "Expected 220 banner, got: {banner}");

    write!(w, "EHLO test.local\r\n").unwrap();
    loop {
        let l = read_line!();
        if l.starts_with("250 ") { break; }   // last EHLO response line
        assert!(l.starts_with("250"), "Unexpected EHLO line: {l}");
    }

    write!(w, "MAIL FROM:<sender@test.local>\r\n").unwrap();
    let r = read_line!();
    assert!(r.starts_with("250"), "MAIL FROM rejected: {r}");

    write!(w, "RCPT TO:<rcpt@test.local>\r\n").unwrap();
    let r = read_line!();
    assert!(r.starts_with("250"), "RCPT TO rejected: {r}");

    write!(w, "DATA\r\n").unwrap();
    let r = read_line!();
    assert!(r.starts_with("354"), "DATA rejected: {r}");

    write!(w, "Subject: Hello\r\n\r\nTest body\r\n.\r\n").unwrap();
    let r = read_line!();
    assert!(r.starts_with("250"), "Message body rejected: {r}");

    write!(w, "QUIT\r\n").unwrap();
    thread::sleep(Duration::from_millis(100)); // let handler finish rename

    let count = std::fs::read_dir(maildir.join("new")).unwrap().count();
    assert_eq!(count, 1, "Expected 1 message in new/, found {count}");
}
```

- [ ] **Step 2: Run test to verify it fails**

```
cd mail-receiver && cargo test end_to_end --test integration_test 2>&1 | head -20
```

Expected: compile error — `mail_receiver::run` contains `todo!()` and `Config` fields are private.

- [ ] **Step 3: Make `Config` fields public (already are in Task 2) — verify**

Check `config.rs`: all three fields (`listen_addr`, `recipient`, `maildir`) are `pub`. If not, add `pub`.

- [ ] **Step 4: Implement `run()` in `lib.rs`**

Replace the `todo!()` stub:

```rust
pub mod config;
pub mod handler;
pub mod maildir;

use std::io;
use std::net::SocketAddr;
use std::path::Path;

pub fn run(cfg: config::Config) -> io::Result<()> {
    let maildir = Path::new(&cfg.maildir).to_path_buf();
    maildir::ensure_dirs(&maildir)?;

    let addr: SocketAddr = cfg.listen_addr.parse().map_err(|e| {
        io::Error::new(io::ErrorKind::InvalidInput, format!("bad SMTP_LISTEN_ADDR: {e}"))
    })?;

    let h = handler::MailHandler::new(cfg.recipient.clone(), maildir);
    let mut server = mailin_embedded::Server::new(h);

    server
        .with_name("mail-receiver")
        .with_ssl(mailin_embedded::SslConfig::None)
        .map_err(|e| io::Error::new(io::ErrorKind::Other, format!("SSL config: {e}")))?
        .with_addr(addr)
        .map_err(|e| io::Error::new(io::ErrorKind::Other, format!("bind: {e}")))?;

    log::info!("Listening on {addr} for <{}>", cfg.recipient);
    server
        .serve()
        .map_err(|e| io::Error::new(io::ErrorKind::Other, format!("serve: {e}")))
}
```

- [ ] **Step 5: Update `main.rs`**

```rust
fn main() {
    env_logger::init();
    let cfg = mail_receiver::config::Config::from_env().unwrap_or_else(|e| {
        eprintln!("Configuration error: {e}");
        std::process::exit(1);
    });
    if let Err(e) = mail_receiver::run(cfg) {
        eprintln!("Server error: {e}");
        std::process::exit(1);
    }
}
```

- [ ] **Step 6: Run the end-to-end test**

```
cd mail-receiver && cargo test end_to_end --test integration_test
```

Expected: `end_to_end_smtp_to_maildir` passes.

- [ ] **Step 7: Run all tests**

```
cd mail-receiver && cargo test -- --test-threads=1
```

Expected: all tests pass. (`--test-threads=1` avoids env-var races in config tests.)

- [ ] **Step 8: Commit**

```bash
git add mail-receiver/src/lib.rs mail-receiver/src/main.rs mail-receiver/tests/integration_test.rs
git commit -m "feat(mail-receiver): server entry point and end-to-end SMTP test"
```

---

## Task 6: Dockerfile

**Files:**
- Create: `mail-receiver/Dockerfile`

- [ ] **Step 1: Create `mail-receiver/Dockerfile`**

```dockerfile
# ── build stage ───────────────────────────────────────────────────────────────
FROM rust:1-alpine AS builder

RUN apk add --no-cache musl-dev

WORKDIR /src
COPY Cargo.toml Cargo.lock* ./
COPY src ./src

RUN cargo build --release --locked

# ── runtime stage ─────────────────────────────────────────────────────────────
FROM gcr.io/distroless/static:nonroot

COPY --from=builder /src/target/release/mail-receiver /mail-receiver

EXPOSE 25

ENTRYPOINT ["/mail-receiver"]
```

- [ ] **Step 2: Build the image**

```bash
podman build -t mail-receiver:local mail-receiver/
```

Expected: successful two-stage build, final image under 15 MB.

```bash
podman image inspect mail-receiver:local --format '{{.Size}}' | numfmt --to=iec
```

- [ ] **Step 3: Verify error handling on missing config**

```bash
podman run --rm mail-receiver:local 2>&1
```

Expected output: `Configuration error: SMTP_RECIPIENT environment variable is required`  
Expected exit code: `1`

- [ ] **Step 4: Commit**

```bash
git add mail-receiver/Dockerfile
git commit -m "feat(mail-receiver): distroless Dockerfile"
```

---

## Task 7: Config example files

**Files:**
- Create: `config/context.md.example`
- Create: `config/lists.yaml.example`
- Create: `.env.example`

- [ ] **Step 1: Create `config/context.md.example`**

```markdown
# Digestor Context

This file tells the digestor what topics matter to you.
Mount it at /config/context.md in the digestor container.

## My interests

I am an IETF participant focused on the QUIC working group and related
transport protocols. I care about:

- Protocol design discussions in QUIC, TLS, HTTPBIS, WEBTRANS
- Calls for adoption and working group last calls
- Interim meeting announcements
- Documents entering IETF last call in my WGs

I am less interested in:

- Administrative or procedural threads unrelated to my WGs
- Social/off-topic content
- Re-subscription confirmation emails (these are always urgent regardless)
```

- [ ] **Step 2: Create `config/lists.yaml.example`**

```yaml
# Maps mailing-list addresses to working group names.
# The digestor uses this to group emails in the daily digest.
# Copy to config/lists.yaml and adjust for your subscriptions.

working_groups:
  QUIC:
    - quic@ietf.org
    - quic-issues@ietf.org
  TLS:
    - tls@ietf.org
  HTTPBIS:
    - ietf-http-wg@w3.org
    - httpbis@ietf.org
  WEBTRANS:
    - webtransport@ietf.org
  General:
    - ietf-announce@ietf.org
    - ietf@ietf.org
```

- [ ] **Step 3: Create `.env.example`**

```bash
# ── Mail receiver ─────────────────────────────────────────────────────────────
SMTP_LISTEN_ADDR=0.0.0.0:25
SMTP_RECIPIENT=digest@yourdomain.example
MAILDIR_PATH=/data/maildir

# ── Digestor ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...
OLLAMA_MODEL=gemma3:4b
DIGEST_TIME=07:00

# ── Notifier ──────────────────────────────────────────────────────────────────
MATRIX_HOMESERVER=https://matrix.example.com
MATRIX_USERNAME=@digestbot:example.com
MATRIX_PASSWORD=changeme
MATRIX_WHITELIST=@you:example.com
```

- [ ] **Step 4: Verify `.env.example` is not gitignored (it must be committed)**

```bash
grep '\.env' .gitignore 2>/dev/null || echo "no gitignore yet — safe"
# If .env (without .example) is in gitignore, that's correct.
# .env.example must NOT be ignored.
```

- [ ] **Step 5: Commit**

```bash
git add config/ .env.example
git commit -m "docs: config example files for all services"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by |
|---|---|
| Mailserver for one address, never sends | Tasks 4+5 (recipient filter, no egress in Dockerfile) |
| Communicates one-way with digestor | Maildir shared volume (established here, wired in Plan 4) |
| Runs separated from other services | Dockerfile + Plan 4 network isolation |
| Everything committed to git | Each task ends with a commit step |
| Everything logged | `log`/`env_logger` in handler and run() |
| Deployment documented | `.env.example`, Dockerfile, Plan 4 |
| Config files (context.md, lists.yaml) | Task 7 (examples only; digestor reads them in Plan 2) |

**Gaps:** None for the mail receiver scope. The Maildir volume definition, network policy, and `MAILDIR_PATH` wiring to the digestor are Plan 4 concerns.
