//! Tauri command bridge (webview ↔ Rust core).

use crate::state::AppState;
use serde::Serialize;
use tauri::State;

/// The loopback control-plane endpoint + per-launch token the webview talks to.
#[derive(Serialize, Clone)]
pub struct McEndpoint {
    pub url: String,
    pub token: String,
}

#[tauri::command]
pub fn mc_endpoint(state: State<'_, AppState>) -> McEndpoint {
    state.endpoint()
}

#[tauri::command]
pub fn sidecar_status(state: State<'_, AppState>) -> String {
    state.sidecar_status().to_string()
}
