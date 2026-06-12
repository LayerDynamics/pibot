mod commands;
mod state;
mod supervisor;
mod token;

use state::AppState;
use std::sync::Arc;
use std::time::Duration;
use supervisor::{Supervisor, SupervisorConfig};
use tauri::Manager;

/// Resolve the argv that launches the control-plane sidecar.
///
/// `PIBOT_MC_CMD` overrides for packaged builds (the externalBin path, wired in T12.1.7);
/// otherwise we run the `pibot.mc` module from the repo venv with cwd = repo root (dev).
fn sidecar_command(token: &str) -> Vec<String> {
    if let Ok(cmd) = std::env::var("PIBOT_MC_CMD") {
        let mut argv: Vec<String> = cmd.split_whitespace().map(String::from).collect();
        argv.push("--port".into());
        argv.push("0".into());
        argv.push("--token".into());
        argv.push(token.to_string());
        return argv;
    }
    let manifest = env!("CARGO_MANIFEST_DIR"); // <repo>/app/src-tauri
    let repo = format!("{manifest}/../..");
    let py = format!("{repo}/.venv/bin/python");
    vec![
        "/bin/sh".into(),
        "-c".into(),
        format!("cd '{repo}' && '{py}' -m pibot.mc --port 0 --token '{token}'"),
    ]
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app_state = AppState::new(token::generate());

    tauri::Builder::default()
        .manage(app_state)
        .invoke_handler(tauri::generate_handler![
            commands::mc_endpoint,
            commands::sidecar_status
        ])
        .setup(move |app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            let token = app.state::<AppState>().token().to_string();

            // Port discovery: the sidecar prints `PORT=<n>` once it binds loopback.
            let handle = app.handle().clone();
            let on_line: supervisor::OnLine = Arc::new(move |line: &str| {
                if let Some(rest) = line.strip_prefix("PORT=") {
                    if let Ok(port) = rest.trim().parse::<u16>() {
                        handle
                            .state::<AppState>()
                            .set_url(format!("http://127.0.0.1:{port}"));
                    }
                }
            });
            let probe: supervisor::Probe = Arc::new(|| true);

            let sup = Supervisor::start(
                SupervisorConfig {
                    command: sidecar_command(&token),
                    max_backoff: Duration::from_secs(5),
                },
                probe,
                on_line,
            );
            app.state::<AppState>().set_supervisor(sup);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
