//! Sidecar supervisor (SPEC-3 FR-1): spawns the Python control-plane sidecar as a
//! child process, monitors its liveness, restarts it with exponential backoff when it
//! dies, streams its stdout lines to a callback (used to discover the chosen port), and
//! kills it on drop. Runs its own OS thread so it never blocks the Tauri runtime.

use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

/// Liveness check beyond "the process is running" (e.g. an HTTP /api/health probe).
/// M12.1 uses a trivial probe; M12.2 swaps in the real HTTP check.
pub type Probe = Arc<dyn Fn() -> bool + Send + Sync>;

/// Callback invoked for each stdout line of the sidecar (port discovery, logs).
pub type OnLine = Arc<dyn Fn(&str) + Send + Sync>;

pub struct SupervisorConfig {
    /// argv to spawn the sidecar (e.g. `[python, -m, pibot.mc, --port, 0, --token, …]`).
    pub command: Vec<String>,
    pub max_backoff: Duration,
}

pub struct Supervisor {
    stop: Arc<AtomicBool>,
    /// Cumulative spawn count — observability API exercised by the supervisor tests.
    #[allow(dead_code)]
    spawns: Arc<AtomicU32>,
    child: Arc<Mutex<Option<Child>>>,
    handle: Option<JoinHandle<()>>,
}

impl Supervisor {
    pub fn start(cfg: SupervisorConfig, probe: Probe, on_line: OnLine) -> Supervisor {
        let stop = Arc::new(AtomicBool::new(false));
        let spawns = Arc::new(AtomicU32::new(0));
        let child: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));

        let stop_t = stop.clone();
        let spawns_t = spawns.clone();
        let child_t = child.clone();
        let handle = thread::spawn(move || {
            let mut backoff = Duration::from_millis(50);
            while !stop_t.load(Ordering::SeqCst) {
                match spawn_child(&cfg.command) {
                    Ok(mut c) => {
                        // Stream stdout to the callback on a detached reader thread.
                        if let Some(out) = c.stdout.take() {
                            let cb = on_line.clone();
                            thread::spawn(move || {
                                for line in BufReader::new(out).lines().map_while(Result::ok) {
                                    cb(&line);
                                }
                            });
                        }
                        spawns_t.fetch_add(1, Ordering::SeqCst);
                        *child_t.lock().unwrap() = Some(c);
                        backoff = Duration::from_millis(50);
                    }
                    Err(_) => {
                        sleep_backoff(&stop_t, &mut backoff, cfg.max_backoff);
                        continue;
                    }
                }

                // Monitor until the child exits or we're told to stop.
                loop {
                    if stop_t.load(Ordering::SeqCst) {
                        break;
                    }
                    let exited = {
                        let mut guard = child_t.lock().unwrap();
                        match guard.as_mut() {
                            Some(c) => !matches!(c.try_wait(), Ok(None)),
                            None => true,
                        }
                    };
                    if exited {
                        break;
                    }
                    let _ = probe();
                    thread::sleep(Duration::from_millis(100));
                }

                if stop_t.load(Ordering::SeqCst) {
                    break;
                }
                // Unexpected exit → back off, then respawn.
                sleep_backoff(&stop_t, &mut backoff, cfg.max_backoff);
            }

            if let Some(mut c) = child_t.lock().unwrap().take() {
                let _ = c.kill();
                let _ = c.wait();
            }
        });

        Supervisor {
            stop,
            spawns,
            child,
            handle: Some(handle),
        }
    }

    #[allow(dead_code)]
    pub fn spawn_count(&self) -> u32 {
        self.spawns.load(Ordering::SeqCst)
    }

    pub fn is_running(&self) -> bool {
        self.child
            .lock()
            .unwrap()
            .as_mut()
            .map(|c| matches!(c.try_wait(), Ok(None)))
            .unwrap_or(false)
    }
}

impl Drop for Supervisor {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
        if let Some(mut c) = self.child.lock().unwrap().take() {
            let _ = c.kill();
            let _ = c.wait();
        }
    }
}

fn spawn_child(argv: &[String]) -> std::io::Result<Child> {
    let (cmd, args) = argv
        .split_first()
        .ok_or_else(|| std::io::Error::new(std::io::ErrorKind::InvalidInput, "empty command"))?;
    Command::new(cmd)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        // Inherit stderr rather than pipe it: nothing here drains a piped stderr, so once the
        // Python sidecar writes more than the OS pipe buffer (~64 KB of tracebacks/logs) it
        // would block forever on the next write and hang. Inheriting sends those diagnostics to
        // the app's own stderr/log instead, with no buffer to fill.
        .stderr(Stdio::inherit())
        .spawn()
}

fn sleep_backoff(stop: &AtomicBool, backoff: &mut Duration, max: Duration) {
    let step = Duration::from_millis(25);
    let mut waited = Duration::ZERO;
    while waited < *backoff {
        if stop.load(Ordering::SeqCst) {
            return;
        }
        thread::sleep(step);
        waited += step;
    }
    *backoff = (*backoff * 2).min(max);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn trivial_probe() -> Probe {
        Arc::new(|| true)
    }
    fn noop_line() -> OnLine {
        Arc::new(|_| {})
    }
    fn sh(script: &str) -> Vec<String> {
        vec!["/bin/sh".into(), "-c".into(), script.into()]
    }

    #[test]
    fn spawns_and_reports_running() {
        let sup = Supervisor::start(
            SupervisorConfig {
                command: sh("sleep 5"),
                max_backoff: Duration::from_millis(200),
            },
            trivial_probe(),
            noop_line(),
        );
        thread::sleep(Duration::from_millis(200));
        assert!(sup.spawn_count() >= 1);
        assert!(sup.is_running());
    }

    #[test]
    fn restarts_after_child_exits() {
        let sup = Supervisor::start(
            SupervisorConfig {
                command: sh("sleep 0.1"),
                max_backoff: Duration::from_millis(80),
            },
            trivial_probe(),
            noop_line(),
        );
        thread::sleep(Duration::from_millis(800));
        assert!(
            sup.spawn_count() >= 2,
            "expected respawns, got {}",
            sup.spawn_count()
        );
    }

    #[test]
    fn streams_stdout_lines() {
        let seen = Arc::new(Mutex::new(Vec::<String>::new()));
        let seen_cb = seen.clone();
        let sup = Supervisor::start(
            SupervisorConfig {
                command: sh("echo PORT=12345; sleep 2"),
                max_backoff: Duration::from_millis(200),
            },
            trivial_probe(),
            Arc::new(move |l: &str| seen_cb.lock().unwrap().push(l.to_string())),
        );
        thread::sleep(Duration::from_millis(300));
        assert!(seen.lock().unwrap().iter().any(|l| l == "PORT=12345"));
        drop(sup);
    }

    #[test]
    fn kills_child_on_drop() {
        let sup = Supervisor::start(
            SupervisorConfig {
                command: sh("sleep 30"),
                max_backoff: Duration::from_millis(200),
            },
            trivial_probe(),
            noop_line(),
        );
        thread::sleep(Duration::from_millis(200));
        let pid = sup.child.lock().unwrap().as_ref().map(|c| c.id());
        assert!(pid.is_some());
        drop(sup);
        thread::sleep(Duration::from_millis(150));
        let pid = pid.unwrap();
        let alive = Command::new("kill")
            .args(["-0", &pid.to_string()])
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        assert!(!alive, "child {pid} still alive after drop");
    }
}
