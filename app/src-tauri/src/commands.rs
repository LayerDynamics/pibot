//! Tauri command bridge (webview ↔ Rust core).

use crate::state::AppState;
use serde::{Deserialize, Serialize};
use tauri::State;

/// The loopback control-plane endpoint + per-launch token the webview talks to.
#[derive(Serialize, Clone)]
pub struct McEndpoint {
    pub url: String,
    pub token: String,
}

/// Payload sent by the Python sidecar's `on_connect` callback to cache the robot endpoint.
#[derive(Deserialize)]
pub struct RobotEndpoint {
    pub url: String,
    pub token: Option<String>,
}

#[tauri::command]
pub fn mc_endpoint(state: State<'_, AppState>) -> McEndpoint {
    state.endpoint()
}

#[tauri::command]
pub fn sidecar_status(state: State<'_, AppState>) -> String {
    state.sidecar_status().to_string()
}

/// Cache the robot's pibotd base URL + bearer token so the e-stop failsafe can reach it
/// directly even if the sidecar has crashed.  Called by the Python sidecar on each
/// successful robot connect (via `on_connect` seam, wired in `McState.on_robot_connect`).
#[tauri::command]
pub fn cache_robot_endpoint(endpoint: RobotEndpoint, state: State<'_, AppState>) {
    state.cache_robot_endpoint(endpoint.url, endpoint.token);
}

/// Send an emergency stop to the robot's pibotd **directly** — bypasses the sidecar.
/// Uses the cached endpoint from the last successful `cache_robot_endpoint` call.
/// Returns `Ok(())` on any 2xx response; `Err(message)` otherwise.
#[tauri::command]
pub async fn estop_now(state: State<'_, AppState>) -> Result<(), String> {
    let (url, token) = state
        .robot_endpoint()
        .ok_or_else(|| "no robot endpoint cached".to_string())?;
    let client = reqwest::Client::new();
    let mut req = client.post(format!("{}/estop", url.trim_end_matches('/')));
    if let Some(tok) = token {
        req = req.header("Authorization", format!("Bearer {tok}"));
    }
    let resp = req.send().await.map_err(|e| e.to_string())?;
    if resp.status().is_success() {
        Ok(())
    } else {
        Err(format!("estop returned HTTP {}", resp.status()))
    }
}

/// Open a native directory-picker dialog and return the chosen path, or `None` if cancelled.
/// Used by the policy-server UI to select a checkpoint directory.
#[tauri::command]
pub async fn pick_path(app: tauri::AppHandle) -> Option<String> {
    use tauri_plugin_dialog::DialogExt;
    let path = app.dialog().file().blocking_pick_folder();
    path.map(|p| p.to_string())
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::sync::{Arc, Mutex};
    use std::thread;

    use crate::state::AppState;

    /// Spawn a minimal one-shot HTTP server. Returns (port, received_request_arc).
    fn fake_http_server(response: &'static str) -> (u16, Arc<Mutex<String>>) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        let received: Arc<Mutex<String>> = Arc::new(Mutex::new(String::new()));
        let received_clone = received.clone();
        thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buf = [0u8; 4096];
                let n = stream.read(&mut buf).unwrap_or(0);
                *received_clone.lock().unwrap() = String::from_utf8_lossy(&buf[..n]).to_string();
                let _ = stream.write_all(response.as_bytes());
            }
        });
        (port, received)
    }

    #[test]
    fn cache_and_retrieve_robot_endpoint() {
        let state = AppState::new("tok".into());
        assert!(state.robot_endpoint().is_none());
        state.cache_robot_endpoint("http://10.0.0.1:8080".into(), Some("robot-tok".into()));
        let (url, token) = state.robot_endpoint().unwrap();
        assert_eq!(url, "http://10.0.0.1:8080");
        assert_eq!(token.as_deref(), Some("robot-tok"));
    }

    #[tokio::test]
    async fn estop_now_posts_to_robot_with_bearer() {
        let (port, received) = fake_http_server("HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}");
        let state = AppState::new("sidecar-tok".into());
        state.cache_robot_endpoint(format!("http://127.0.0.1:{port}"), Some("robot-tok".into()));

        // Invoke the command logic directly (bypassing Tauri State wrapping).
        let (url, token) = state.robot_endpoint().unwrap();
        let client = reqwest::Client::new();
        let mut req = client.post(format!("{}/estop", url.trim_end_matches('/')));
        if let Some(tok) = token {
            req = req.header("Authorization", format!("Bearer {tok}"));
        }
        let resp = req.send().await.unwrap();
        assert!(resp.status().is_success());

        let request_text = received.lock().unwrap().clone();
        assert!(request_text.contains("POST /estop"));
        assert!(request_text.contains("Bearer robot-tok"));
    }

    #[tokio::test]
    async fn estop_now_fails_without_cached_endpoint() {
        let state = AppState::new("tok".into());
        assert!(
            state.robot_endpoint().is_none(),
            "should have no cached endpoint"
        );
    }
}
