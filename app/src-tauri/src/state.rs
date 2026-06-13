//! Shared application state managed by Tauri: the per-launch token, the discovered
//! sidecar URL, the robot endpoint cache (for the e-stop failsafe), and the sidecar
//! supervisor handle.

use crate::commands::McEndpoint;
use crate::supervisor::Supervisor;
use std::sync::Mutex;

pub struct AppState {
    token: String,
    url: Mutex<Option<String>>,
    /// Cached robot endpoint for the e-stop failsafe (wired from Python `on_connect`).
    robot_url: Mutex<Option<String>>,
    robot_token: Mutex<Option<String>>,
    supervisor: Mutex<Option<Supervisor>>,
}

impl AppState {
    pub fn new(token: String) -> Self {
        Self {
            token,
            url: Mutex::new(None),
            robot_url: Mutex::new(None),
            robot_token: Mutex::new(None),
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

    /// Cache the robot base URL + bearer token for the e-stop failsafe.
    pub fn cache_robot_endpoint(&self, url: String, token: Option<String>) {
        *self.robot_url.lock().unwrap() = Some(url);
        *self.robot_token.lock().unwrap() = token;
    }

    /// Return `(robot_url, bearer_token)` if a robot has been connected.
    pub fn robot_endpoint(&self) -> Option<(String, Option<String>)> {
        let url = self.robot_url.lock().unwrap().clone()?;
        let token = self.robot_token.lock().unwrap().clone();
        Some((url, token))
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
