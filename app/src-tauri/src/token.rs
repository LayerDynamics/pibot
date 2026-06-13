//! Per-launch bearer token for the loopback control-plane API (SPEC-3 FR-2).
//!
//! Generated fresh each launch by the Rust core, handed to the sidecar via env on
//! spawn and to the webview via the `mc_endpoint` command. Never written to disk.

use getrandom::getrandom;

/// 32 random bytes, hex-encoded → a 64-char URL-safe token.
pub fn generate() -> String {
    let mut bytes = [0u8; 32];
    getrandom(&mut bytes).expect("OS RNG unavailable");
    let mut s = String::with_capacity(64);
    for b in bytes {
        s.push_str(&format!("{b:02x}"));
    }
    s
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn token_is_64_hex_chars() {
        let t = generate();
        assert_eq!(t.len(), 64);
        assert!(t.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn tokens_are_unique() {
        assert_ne!(generate(), generate());
    }
}
