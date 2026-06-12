//! Shared application state managed by Tauri: the per-launch token, the discovered
//! sidecar URL, and the sidecar supervisor handle.

use crate::commands::McEndpoint;
use crate::supervisor::Supervisor;
use std::sync::Mutex;

pub struct AppState {
    token: String,
    url: Mutex<Option<String>>,
    supervisor: Mutex<Option<Supervisor>>,
}

impl AppState {
    pub fn new(token: String) -> Self {
        Self {
            token,
            url: Mutex::new(None),
            supervisor: Mutex::new(None),
        }
    }

    pub fn token(&self) -> &str {
        &self.token
    }

    /// Set once the sidecar prints its bound port (`PORT=<n>` on stdout).
    pub fn set_url(&self, url: String) {
        *self.url.lock().unwrap() = Some(url);
    }

    pub fn endpoint(&self) -> McEndpoint {
        McEndpoint {
            url: self.url.lock().unwrap().clone().unwrap_or_default(),
            token: self.token.clone(),
        }
    }

    pub fn set_supervisor(&self, s: Supervisor) {
        *self.supervisor.lock().unwrap() = Some(s);
    }

    pub fn sidecar_status(&self) -> &'static str {
        match self.supervisor.lock().unwrap().as_ref() {
            Some(s) if s.is_running() => "running",
            Some(_) => "starting",
            None => "stopped",
        }
    }
}
