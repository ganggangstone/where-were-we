use std::{fs, path::{Path, PathBuf}, process::Command};
use tauri::Manager;
use std::{io::{Read, Write}, process::{Child, ExitStatus, Stdio}, sync::Mutex, time::{Duration, Instant}};

// App updates reserve the backend so collection/AI work cannot be interrupted.
static WORK: Mutex<(usize, bool)> = Mutex::new((0, false));
struct BackendWork;
impl BackendWork {
    fn start() -> Result<Self, String> {
        let mut work = WORK.lock().map_err(|e| e.to_string())?;
        if work.1 { return Err("An app update is running".into()); }
        work.0 += 1;
        Ok(Self)
    }
}
impl Drop for BackendWork {
    fn drop(&mut self) { if let Ok(mut work) = WORK.lock() { work.0 -= 1; } }
}

fn reserve_update_work() -> Result<(), String> {
    let mut work = WORK.lock().map_err(|e| e.to_string())?;
    if work.0 > 0 || work.1 { return Err("Wait for collection or AI work to finish before updating".into()); }
    work.1 = true;
    Ok(())
}

fn root() -> PathBuf {
    PathBuf::from(std::env::var("HOME").unwrap_or_default()).join(".where-were-we")
}

/// ~/.where-were-we/<프로젝트>/ 폴더 이름 목록.
#[tauri::command]
fn list_projects() -> Vec<String> { project_names(&root()) }

fn project_names(directory: &Path) -> Vec<String> {
    let mut v: Vec<String> = fs::read_dir(directory)
        .map(|d| d.flatten().filter(|e| e.path().is_dir()).filter_map(|e| e.file_name().into_string().ok()).filter(|name| !name.starts_with('.')).collect())
        .unwrap_or_default();
    v.sort();
    v
}

/// ~/.where-were-we/<프로젝트>/<브랜치>.json 내용. 파일이 없으면 Err.
#[tauri::command]
fn read_map(project: String, branch: String) -> Result<String, String> {
    let p = root().join(&project).join(format!("{branch}.json"));
    fs::read_to_string(&p).map_err(|e| format!("{}: {e}", p.display()))
}

#[derive(Debug)]
struct Backend {
    python: PathBuf,
    scripts: PathBuf,
}

impl Backend {
    fn bundled(resources: &Path) -> Result<Self, String> {
        let base = resources.join("runtime");
        let backend = Self {
            python: base.join("python/bin/python3"),
            scripts: base.join("backend"),
        };
        if !backend.python.is_file() || !backend.scripts.join("mcp_server.py").is_file() {
            return Err("The bundled Python/MCP runtime is missing. Reinstall the app.".into());
        }
        Ok(backend)
    }

    fn command(&self, script: &str, args: &[&str]) -> Command {
        let mut command = Command::new(&self.python);
        command.args(["-I", "-B"]).arg(self.scripts.join(script)).args(args);
        // GUI apps do not inherit a terminal's PATH. Keep existing entries and add
        // common CLI install locations only for this child process.
        let mut paths: Vec<PathBuf> = std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default()).collect();
        if let Some(home) = std::env::var_os("HOME") { paths.push(PathBuf::from(home).join(".local/bin")); }
        paths.extend([PathBuf::from("/opt/homebrew/bin"), PathBuf::from("/usr/local/bin"), PathBuf::from("/usr/bin"), PathBuf::from("/bin")]);
        if let Ok(path) = std::env::join_paths(paths) { command.env("PATH", path); }
        command.env_remove("PYTHONHOME").env_remove("PYTHONPATH")
            .env("PYTHONNOUSERSITE", "1").env("PYTHONDONTWRITEBYTECODE", "1");
        command
    }
}

fn backend(app: &tauri::AppHandle) -> Result<Backend, String> {
    // Source checkout execution is available only in debug builds.
    // Release builds always use the installed app's resources, never the cwd.
    #[cfg(debug_assertions)]
    {
        let scripts = PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().unwrap().to_path_buf();
        let venv = scripts.join(".venv/bin/python");
        if venv.is_file() { return Ok(Backend { python: venv, scripts }); }
    }
    Backend::bundled(&app.path().resource_dir().map_err(|e| e.to_string())?)
}

fn run_py(app: &tauri::AppHandle, script: &str, args: &[&str]) -> Result<String, String> {
    let _work = BackendWork::start()?;
    let out = backend(app)?.command(script, args).output().map_err(|e| e.to_string())?;
    if out.status.success() { Ok(String::from_utf8_lossy(&out.stdout).to_string()) }
    else { Err(String::from_utf8_lossy(&out.stderr).to_string()) }
}

/// One composed read model for the UI and MCP, including repository status.
#[tauri::command]
async fn read_project(app: tauri::AppHandle, project: String, repository: Option<String>) -> Result<String, String> {
    run_py(&app, "project.py", &["read", &project, "--repository", repository.as_deref().unwrap_or("")])
}

#[tauri::command]
async fn save_project(app: tauri::AppHandle, project: String, configuration: String) -> Result<String, String> {
    run_py(&app, "project.py", &["configure", &project, &configuration])
}

#[tauri::command]
async fn github_accounts(app: tauri::AppHandle, project: String, repository: String) -> Result<String, String> {
    run_py(&app,"project.py",&["github-accounts",&project,"--repository",&repository])
}

#[tauri::command]
async fn github_logins(app: tauri::AppHandle, project: String) -> Result<String, String> {
    run_py(&app,"project.py",&["github-logins",&project])
}

#[tauri::command]
async fn use_github_account(app: tauri::AppHandle, project: String, repository: String, account: String) -> Result<String, String> {
    run_py(&app,"project.py",&["github-account",&project,"--repository",&repository,&account])
}

#[tauri::command]
async fn read_settings(app: tauri::AppHandle) -> Result<String, String> {
    run_py(&app, "mapcore.py", &["settings"])
}

#[tauri::command]
async fn save_settings(app: tauri::AppHandle, json: String) -> Result<String, String> {
    run_py(&app, "mapcore.py", &["save-settings", &json])
}

fn task_request(app: &tauri::AppHandle, project: &str, branch: &str, lang: &str, repository: Option<&str>, task: &str, target: &str) -> Result<String, String> {
    run_py(app, "ai_extract.py", &[project, branch, lang, "--request", "--repository", repository.unwrap_or(""), "--task", task, "--target", target])
}

/// 새로고침: refresh.py 가 fetch, 바뀐 브랜치의 지도 다시 뽑기, 수집, 달라진 것 기록을 한다. 로그를 돌려준다.
#[tauri::command]
async fn refresh(app: tauri::AppHandle, project: String, repo: String, since: String, repository: Option<String>) -> Result<String, String> {
    if root().join(&project).join("project.json").is_file() {
        run_py(&app, "project.py", &["refresh", &project, "--repository", repository.as_deref().unwrap_or("")])
    } else { run_py(&app, "refresh.py", &[&project, &repo, &since]) }
}

/// Prepare group naming for the connected MCP agent.
#[tauri::command]
async fn suggest_groups(app: tauri::AppHandle, project: String, branch: String, lang: String, repository: Option<String>) -> Result<String, String> {
    task_request(&app, &project, &branch, &lang, repository.as_deref(), "groups", "")
}

/// 에이전트 연결 프롬프트 (mapcore.py setup). 이 맥의 경로가 채워진다.
#[tauri::command]
async fn setup_prompt(app: tauri::AppHandle, lang: Option<String>) -> Result<String, String> {
    run_py(&app, "mapcore.py", &["setup", if lang.as_deref() == Some("en") { "--lang=en" } else { "--lang=ko" }])
}

/// 테스트가 안 이어진 서버 기능 하나에 대해 에이전트가 테스트를 찾게 하는 글 (mapcore.py tests).
#[tauri::command]
async fn tests_prompt(app: tauri::AppHandle, project: String, route: String, lang: Option<String>, repository: Option<String>) -> Result<String, String> {
    let scope = format!("--repository={}", repository.as_deref().unwrap_or(""));
    run_py(&app, "mapcore.py", &["tests", &project, &route, &scope, if lang.as_deref() == Some("en") { "--lang=en" } else { "--lang=ko" }])
}

/// Prepare program jobs for the connected MCP agent.
#[tauri::command]
async fn make_jobs(app: tauri::AppHandle, project: String, node: String, branch: String, lang: String, repository: Option<String>) -> Result<String, String> {
    task_request(&app, &project, &branch, &lang, repository.as_deref(), "jobs", &node)
}

/// Prepare architecture for the connected MCP agent.
#[tauri::command]
async fn make_system(app: tauri::AppHandle, project: String, branch: String, lang: String, repository: Option<String>) -> Result<String, String> {
    task_request(&app, &project, &branch, &lang, repository.as_deref(), "system", "")
}

/// Prepare request steps for the connected MCP agent.
#[tauri::command]
async fn make_steps(app: tauri::AppHandle, project: String, branch: String, screen: String, lang: String, repository: Option<String>) -> Result<String, String> {
    task_request(&app, &project, &branch, &lang, repository.as_deref(), "steps", &screen)
}

/// Language-independent detailed analysis, explicitly requested by the user.
#[tauri::command]
async fn analysis_request(app: tauri::AppHandle, project: String, branch: String, lang: String, repository: Option<String>) -> Result<String, String> {
    run_py(&app,"ai_extract.py",&[&project,&branch,&lang,"--request","--repository",repository.as_deref().unwrap_or("")])
}

#[tauri::command]
async fn briefing_request(app: tauri::AppHandle, project: String, branch: String, lang: String, repository: Option<String>) -> Result<String, String> {
    run_py(&app,"briefing.py",&["request",&project,"--branch",&branch,"--lang",&lang,"--repository",repository.as_deref().unwrap_or("")])
}

/// zed://file/... 같은 주소를 macOS `open` 으로 연다.
#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    Command::new("open").arg(&url).status().map(|_| ()).map_err(|e| e.to_string())
}

const RELEASE_API: &str = "https://api.github.com/repos/ganggangstone/where-were-we/releases/latest";
const RELEASE_PAGE: &str = "https://github.com/ganggangstone/where-were-we/releases";
const CASK: &str = "ganggangstone/tap/where-were-we";

fn managed_version(info: &serde_json::Value, app: &Path) -> Result<semver::Version, String> {
    let cask = info["casks"].as_array().and_then(|rows| rows.iter().find(|r| r["full_token"] == CASK))
        .ok_or("This app is not managed by the where-were-we Homebrew cask")?;
    let same_path = |target: &str| {
        let path = Path::new(target);
        path == app || matches!((path.canonicalize(), app.canonicalize()), (Ok(a), Ok(b)) if a == b)
    };
    if !cask["artifacts"].as_array().is_some_and(|rows| rows.iter().any(|r|
        r.get("app").is_some() && r["target"].as_str().is_some_and(same_path))) {
        return Err("Open the Homebrew-installed app to update it here".into());
    }
    semver::Version::parse(cask["installed"].as_str().ok_or("The Homebrew cask is not installed")?)
        .map_err(|_| "Invalid installed Homebrew version".into())
}

fn available_update(available: &str, wanted: &str) -> Result<(), String> {
    let available = semver::Version::parse(available).map_err(|_| "Invalid Homebrew version")?;
    let wanted = semver::Version::parse(wanted).map_err(|_| "Invalid requested version")?;
    if !available.pre.is_empty() || !wanted.pre.is_empty() || available.cmp_precedence(&wanted).is_lt() {
        return Err("Homebrew does not have the requested stable version yet".into());
    }
    Ok(())
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
struct UpdateState {
    stage: String,
    version: String,
    error: Option<String>,
    #[serde(default)]
    app: Option<PathBuf>,
    #[serde(default)]
    backup: Option<PathBuf>,
    #[serde(default)]
    recovery_command: Option<String>,
}

#[derive(serde::Serialize, serde::Deserialize)]
struct UpdateJob {
    brew: PathBuf, app: PathBuf, backup: PathBuf, state: PathBuf, log: PathBuf,
    version: String, parent: u32,
}

fn update_state(path: &Path) -> Option<UpdateState> {
    serde_json::from_slice(&fs::read(path).ok()?).ok()
}

fn save_update_state(path: &Path, state: &UpdateState) -> Result<(), String> {
    let temp = path.with_extension(format!("{}.tmp", std::process::id()));
    let mut file=fs::File::create(&temp).map_err(|e| e.to_string())?;
    file.write_all(&serde_json::to_vec(state).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    file.sync_all().map_err(|e| e.to_string())?;
    fs::rename(&temp, path).map_err(|e| e.to_string())
}

fn write_update(job: &UpdateJob, stage: &str, error: Option<String>) -> Result<(), String> {
    let command=format!("'{}' reinstall --cask {}",job.brew.to_string_lossy().replace('\'', "'\"'\"'"),CASK);
    let state = UpdateState { stage: stage.into(), version: job.version.clone(), error,
        app: Some(job.app.clone()), backup: Some(job.backup.clone()), recovery_command: Some(command) };
    // Persist recovery instructions before Homebrew is allowed to replace the app.
    if stage=="installing" {
        let mut log=fs::OpenOptions::new().create(true).append(true).open(&job.log).map_err(|e| e.to_string())?;
        writeln!(log,"Recovery copy: {}\nRestore with Finder: copy this app to {} and choose Replace.\nOr reinstall with: {}",
            job.backup.display(),job.app.parent().unwrap_or(Path::new("/Applications")).display(),state.recovery_command.as_deref().unwrap_or("")).map_err(|e| e.to_string())?;
        log.sync_all().map_err(|e| e.to_string())?;
    }
    save_update_state(&job.state,&state)
}

fn brew_command(brew: &Path) -> Command {
    let mut command = Command::new(brew);
    let prefix = brew.parent().unwrap_or(Path::new("/usr/bin"));
    command.env("PATH", format!("{}:/usr/bin:/bin:/usr/sbin:/sbin", prefix.display()))
        .env("HOMEBREW_NO_AUTO_UPDATE", "1").env("HOMEBREW_NO_INSTALL_CLEANUP", "1")
        .stdin(Stdio::null());
    command
}

fn brew_info(brew: &Path) -> Result<serde_json::Value, String> {
    let mut command = brew_command(brew);
    command.args(["info", "--json=v2", "--cask", CASK]).stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(unix)]
    { use std::os::unix::process::CommandExt; command.process_group(0); }
    let mut child = command.spawn().map_err(|e| e.to_string())?;
    let mut stdout = child.stdout.take().ok_or("Missing Homebrew output")?;
    let mut stderr = child.stderr.take().ok_or("Missing Homebrew error output")?;
    let out = std::thread::spawn(move || { let mut bytes=Vec::new(); stdout.read_to_end(&mut bytes).map(|_| bytes) });
    let err = std::thread::spawn(move || { let mut bytes=Vec::new(); stderr.read_to_end(&mut bytes).map(|_| bytes) });
    let status = wait_child(&mut child, Duration::from_secs(30));
    let stdout = out.join().map_err(|_| "Homebrew output reader failed")?.map_err(|e| e.to_string())?;
    let stderr = err.join().map_err(|_| "Homebrew error reader failed")?.map_err(|e| e.to_string())?;
    if !status?.success() { return Err(String::from_utf8_lossy(&stderr).chars().take(2000).collect()); }
    serde_json::from_slice(&stdout).map_err(|e| e.to_string())
}

fn wait_child(child: &mut Child, timeout: Duration) -> Result<ExitStatus, String> {
    let start = Instant::now();
    loop {
        if let Some(status) = child.try_wait().map_err(|e| e.to_string())? { return Ok(status); }
        if start.elapsed() > timeout {
            #[cfg(unix)]
            { let _ = Command::new("/bin/kill").args(["-KILL", "--", &format!("-{}", child.id())]).status(); }
            let _ = child.kill(); let _ = child.wait();
            return Err("Homebrew command timed out".into());
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

fn run_brew(job: &UpdateJob, args: &[&str], timeout: Duration) -> Result<(), String> {
    let file = fs::OpenOptions::new().create(true).append(true).open(&job.log).map_err(|e| e.to_string())?;
    let mut command = brew_command(&job.brew);
    command.args(args).stdout(file.try_clone().map_err(|e| e.to_string())?).stderr(file);
    #[cfg(unix)]
    { use std::os::unix::process::CommandExt; command.process_group(0); }
    let mut child = command.spawn().map_err(|e| e.to_string())?;
    if wait_child(&mut child, timeout)?.success() { Ok(()) } else {
        let log = fs::read_to_string(&job.log).unwrap_or_default();
        Err(format!("Homebrew {} failed: {}", args[0], log.chars().rev().take(2000).collect::<String>().chars().rev().collect::<String>()))
    }
}

fn perform_update(job: &UpdateJob) -> Result<(), String> {
    write_update(job, "checking", None)?;
    run_brew(job, &["update"], Duration::from_secs(900))?;
    let info = brew_info(&job.brew)?;
    let installed = managed_version(&info, &job.app)?;
    available_update(info["casks"][0]["version"].as_str().unwrap_or(""), &job.version)?;
    write_update(job, "ready", None)?;
    let start = Instant::now();
    while process_exists(job.parent) {
        if start.elapsed() > Duration::from_secs(60) { return Err("The app did not close; no files were replaced".into()); }
        std::thread::sleep(Duration::from_millis(200));
    }
    prepare_backup(job, copy_app)?;
    write_update(job, "installing", None)?;
    // A previous rollback may leave Homebrew's receipt ahead of the restored app.
    let operation = if available_update(&installed.to_string(), &job.version).is_ok() { "reinstall" } else { "upgrade" };
    run_brew(job, &[operation, "--cask", CASK], Duration::from_secs(900))?;
    let installed = managed_version(&brew_info(&job.brew)?, &job.app)?;
    available_update(&installed.to_string(), &job.version)?;
    let output = Command::new("/usr/libexec/PlistBuddy").args(["-c", "Print :CFBundleShortVersionString"]).arg(job.app.join("Contents/Info.plist"))
        .output().map_err(|e| e.to_string())?;
    if !output.status.success() { return Err("Could not verify the updated app version".into()); }
    available_update(String::from_utf8_lossy(&output.stdout).trim(), &job.version)?;
    write_update(job, "restarting", None)
}

fn copy_app(source: &Path, target: &Path) -> Result<(), String> {
    let mut child = Command::new("/usr/bin/ditto").arg(source).arg(target).stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null())
        .spawn().map_err(|e| e.to_string())?;
    if wait_child(&mut child, Duration::from_secs(120))?.success() { Ok(()) }
    else { Err("Could not copy the app for recovery".into()) }
}

fn prepare_backup(job: &UpdateJob, copy: impl Fn(&Path, &Path) -> Result<(), String>) -> Result<(), String> {
    fs::create_dir_all(job.backup.parent().ok_or("Invalid backup path")?).map_err(|e| e.to_string())?;
    let partial = job.backup.with_extension("partial");
    copy(&job.app, &partial)?;
    fs::rename(&partial, &job.backup).map_err(|e| e.to_string())
}

fn restore_app(job: &UpdateJob) -> Result<(), String> {
    restore_app_using(job, copy_app)
}

fn restore_app_using(job: &UpdateJob, copy: impl Fn(&Path, &Path) -> Result<(), String>) -> Result<(), String> {
    if !job.backup.join("Contents/Info.plist").is_file() { return Err("No complete recovery copy exists".into()); }
    let parent = job.app.parent().ok_or("Invalid app path")?;
    let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(|e| e.to_string())?.as_nanos();
    let recovery = parent.join(format!(".where-were-we-recovery-{}-{stamp}", std::process::id()));
    fs::create_dir(&recovery).map_err(|e| e.to_string())?;
    let ready = recovery.join("ready.app");
    if let Err(error) = copy(&job.backup, &ready) { let _ = fs::remove_dir_all(&recovery); return Err(error); }
    let failed = recovery.join("failed.app");
    if job.app.exists() {
        if let Err(error) = fs::rename(&job.app, &failed) { let _ = fs::remove_dir_all(&recovery); return Err(error.to_string()); }
    }
    if let Err(error) = fs::rename(&ready, &job.app) {
        if failed.exists() { let _ = fs::rename(&failed, &job.app); }
        return Err(format!("Could not restore app: {error}. Preserved files: {}", recovery.display()));
    }
    let _ = fs::remove_dir_all(&recovery);
    Ok(())
}

fn process_exists(pid: u32) -> bool {
    Command::new("/bin/kill").args(["-0", &pid.to_string()]).stdout(Stdio::null()).stderr(Stdio::null()).status().is_ok_and(|s| s.success())
}

// The helper is a copy of this native executable outside the .app being replaced.
// Its inherited stdin holds the OS file lock until it exits, including after a crash.
pub fn run_update_helper() -> Option<i32> {
    let args: Vec<_> = std::env::args().collect();
    if args.get(1).map(String::as_str) != Some("--apply-update") { return None; }
    let job: UpdateJob = match args.get(2).and_then(|s| serde_json::from_str(s).ok()) { Some(job) => job, None => return Some(2) };
    let mut result = perform_update(&job);
    if result.is_ok() {
        // Keep the child PID so a failed startup can be stopped before rollback.
        let mut launch = Command::new(job.app.join("Contents/MacOS/where-were-we"));
        launch.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
        #[cfg(unix)]
        { use std::os::unix::process::CommandExt; launch.process_group(0); }
        match launch.spawn() {
            Err(error) => result = Err(format!("Could not reopen the updated app: {error}")),
            Ok(mut child) => {
                let start = Instant::now();
                loop {
                    if update_state(&job.state).is_some_and(|s| s.stage == "completed") { break; }
                    if child.try_wait().is_ok_and(|s| s.is_some()) || start.elapsed() > Duration::from_secs(60) {
                        let _ = child.kill(); let _ = child.wait();
                        result = Err("The updated app did not finish reopening".into()); break;
                    }
                    std::thread::sleep(Duration::from_millis(250));
                }
            }
        }
    }
    let mut restored = false;
    if result.is_err() && job.backup.is_dir() {
        match restore_app(&job) {
            Ok(()) => restored = true,
            Err(error) => result = Err(format!("{}; {error}. Recovery copy: {}", result.unwrap_err(), job.backup.display())),
        }
    }
    if let Err(error) = &result {
        let _ = write_update(&job, "failed", Some(error.clone()));
        if !process_exists(job.parent) {
            let _ = Command::new("/usr/bin/open").arg("-n").arg(&job.app).status();
            // An OS launch block can also prevent the old app displaying the error.
            let _ = Command::new("/usr/bin/osascript").args(["-e", "on run argv\ndisplay alert \"where-were-we\" message (item 1 of argv) as warning\nend run", error]).status();
        }
    }
    // Only the helper's own generated staging directory is removed.
    if let Ok(exe) = std::env::current_exe() {
        if let Some(stage) = exe.parent() {
            if (result.is_ok() || restored || !job.backup.exists()) && exe.file_name().is_some_and(|s| s == "updater")
                && stage.file_name().is_some_and(|s| s.to_string_lossy().starts_with("where-were-we-update-"))
                && stage.parent().and_then(|p| p.canonicalize().ok()) == std::env::temp_dir().canonicalize().ok() {
                let _ = fs::remove_dir_all(stage);
            }
        }
    }
    if result.is_ok() || restored {
        let _=fs::remove_dir_all(&job.backup);
        if let Some(parent)=job.backup.parent().filter(|p| p.file_name().is_some_and(|n| n.to_string_lossy().starts_with(".app-update-backup-"))) {
            let _=fs::remove_dir(parent); // Only the now-empty directory for this attempt.
        }
    }
    Some(if result.is_ok() { 0 } else { 1 })
}

#[tauri::command]
fn app_update_status() -> Option<UpdateState> { read_update_status(&root()) }

fn read_update_status(directory: &Path) -> Option<UpdateState> {
    let path = directory.join(".app-update.json");
    let mut state = update_state(&path)?;
    if ["starting", "checking", "ready", "installing", "restarting"].contains(&state.stage.as_str()) {
        if let Ok(lock) = fs::OpenOptions::new().create(true).truncate(false).read(true).write(true).open(directory.join(".app-update.lock")) {
            if lock.try_lock().is_ok() {
                state.stage = "failed".into();
                let mut message="The previous update was interrupted.".to_string();
                if let Some(backup)=state.backup.as_ref().filter(|p| p.join("Contents/Info.plist").is_file()) {
                    message.push_str(&format!(" Recovery copy: {}. Copy this app to its original location with Finder and choose Replace.",backup.display()));
                }
                if let Some(command)=&state.recovery_command { message.push_str(&format!(" Or reinstall with: {command}")); }
                state.error=Some(message);
                let _ = save_update_state(&path,&state);
            }
        }
    }
    Some(state)
}

fn acknowledge_update(path: &Path, version: &str, bundle: &Path) {
    if let Some(state) = update_state(path) {
        let expected = state.app.as_deref().and_then(|p| p.canonicalize().ok());
        if state.stage == "restarting" && expected.is_some() && expected == bundle.canonicalize().ok()
            && available_update(version, &state.version).is_ok() {
            let mut completed=state;completed.stage="completed".into();completed.error=None;
            let _ = save_update_state(path,&completed);
        }
    }
}

#[tauri::command]
async fn start_app_update(app: tauri::AppHandle, version: String) -> Result<(), String> {
    let current = app.package_info().version.clone();
    let wanted = semver::Version::parse(&version).map_err(|_| "Invalid requested version")?;
    if !wanted.pre.is_empty() || !wanted.cmp_precedence(&current).is_gt() { return Err("No newer stable version was requested".into()); }
    reserve_update_work()?;
    let result = tauri::async_runtime::spawn_blocking(move || -> Result<(), String> {
        fs::create_dir_all(root()).map_err(|e| e.to_string())?;
        let lock = fs::OpenOptions::new().create(true).truncate(false).read(true).write(true).open(root().join(".app-update.lock")).map_err(|e| e.to_string())?;
        lock.try_lock().map_err(|_| "Another app update is already running")?;
        let exe = std::env::current_exe().map_err(|e| e.to_string())?;
        let bundle = exe.parent().and_then(Path::parent).and_then(Path::parent).filter(|p| p.extension().is_some_and(|e| e == "app")).ok_or("Open the installed app to update")?.to_path_buf();
        let brew = ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"].into_iter().map(PathBuf::from).find(|p| p.is_file()).ok_or("Homebrew was not found")?;
        managed_version(&brew_info(&brew)?, &bundle)?;
        let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(|e| e.to_string())?.as_nanos();
        let stage = std::env::temp_dir().join(format!("where-were-we-update-{}-{stamp}", std::process::id()));
        fs::create_dir(&stage).map_err(|e| e.to_string())?;
        let helper = stage.join("updater");
        let job = UpdateJob { brew, app: bundle.clone(), backup: root().join(format!(".app-update-backup-{}-{stamp}",std::process::id())).join(bundle.file_name().ok_or("Invalid app filename")?), state: root().join(".app-update.json"), log: root().join(".app-update.log"), version, parent: std::process::id() };
        let launch = (|| -> Result<(), String> {
            // Write a fresh inode; do not re-sign or overwrite the installed executable.
            let mut output = fs::File::create(&helper).map_err(|e| e.to_string())?;
            output.write_all(&fs::read(&exe).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
            fs::set_permissions(&helper, fs::metadata(&exe).map_err(|e| e.to_string())?.permissions()).map_err(|e| e.to_string())?;
            fs::write(&job.log, "").map_err(|e| e.to_string())?;
            write_update(&job, "starting", None)?;
            let mut command = Command::new(&helper);
            command.arg("--apply-update").arg(serde_json::to_string(&job).map_err(|e| e.to_string())?)
                .stdin(Stdio::from(lock)).stdout(Stdio::null()).stderr(Stdio::null());
            #[cfg(unix)]
            { use std::os::unix::process::CommandExt; command.process_group(0); }
            let mut child = command.spawn().map_err(|e| e.to_string())?;
            std::thread::spawn(move || {
                loop {
                    if update_state(&job.state).is_some_and(|s| s.stage == "ready") { app.exit(0); return; }
                    if let Ok(Some(status)) = child.try_wait() {
                        if !update_state(&job.state).is_some_and(|s| s.stage == "failed" || s.stage == "completed") {
                            let _ = write_update(&job, "failed", Some(format!("Update helper stopped: {status}")));
                        }
                        if let Ok(mut work) = WORK.lock() { work.1 = false; }
                        return;
                    }
                    std::thread::sleep(Duration::from_millis(200));
                }
            });
            Ok(())
        })();
        if launch.is_err() { let _ = fs::remove_dir_all(stage); }
        launch
    }).await.map_err(|e| e.to_string()).and_then(|r| r);
    if result.is_err() { if let Ok(mut work) = WORK.lock() { work.1 = false; } }
    result
}

#[derive(Debug, serde::Serialize)]
struct PublicRelease {
    version: String,
    notes: String,
    url: String,
    newer: bool,
}

#[derive(Debug, serde::Serialize)]
struct ReleaseStatus {
    current: String,
    latest: Option<PublicRelease>,
}

fn parse_release(status: u16, body: &str, current: &str) -> Result<ReleaseStatus, String> {
    let mut result = ReleaseStatus { current: current.to_owned(), latest: None };
    if status == 404 { return Ok(result); }
    if status != 200 { return Err(format!("Release check returned HTTP {status}")); }
    let value: serde_json::Value = serde_json::from_str(body).map_err(|_| "Invalid release response")?;
    let tag = value["tag_name"].as_str().ok_or("Missing release tag")?;
    let version = semver::Version::parse(tag.strip_prefix('v').unwrap_or(tag)).map_err(|_| "Invalid release version")?;
    if value["draft"].as_bool() != Some(false) || value["prerelease"].as_bool() != Some(false) || !version.pre.is_empty() {
        return Ok(result);
    }
    let installed = semver::Version::parse(current).map_err(|_| "Invalid installed version")?;
    result.latest = Some(PublicRelease {
        version: version.to_string(),
        notes: value["body"].as_str().unwrap_or("").to_owned(),
        // Derive the link from the validated tag, never a response-supplied URL.
        url: format!("{RELEASE_PAGE}/tag/{tag}"),
        newer: version.cmp_precedence(&installed).is_gt(),
    });
    Ok(result)
}

#[tauri::command]
fn app_version(app: tauri::AppHandle) -> String {
    app.package_info().version.to_string()
}

#[tauri::command]
async fn check_release(app: tauri::AppHandle) -> Result<ReleaseStatus, String> {
    let current = app.package_info().version.to_string();
    tauri::async_runtime::spawn_blocking(move || {
        // -q is first to ignore user curl configuration. No gh login or token is
        // read; the request contains only this fixed public release endpoint.
        let output = Command::new("/usr/bin/curl").args([
            "-q", "--silent", "--show-error", "--proto", "=https",
            "--connect-timeout", "5", "--max-time", "15", "--max-filesize", "1048576",
            "--header", "Accept: application/vnd.github+json",
            "--user-agent", "where-were-we-release-check",
            "--write-out", "\n%{http_code}", RELEASE_API,
        ]).output().map_err(|_| "Could not start release check".to_owned())?;
        if !output.status.success() { return Err("Could not reach the release service".into()); }
        let response = String::from_utf8(output.stdout).map_err(|_| "Invalid release encoding")?;
        let (body, code) = response.rsplit_once('\n').ok_or("Missing release status")?;
        parse_release(code.parse().map_err(|_| "Invalid release status")?, body, &current)
    }).await.map_err(|e| e.to_string())?
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![list_projects, read_map, read_project, save_project, github_logins, github_accounts, use_github_account, read_settings, save_settings, open_url, refresh, suggest_groups, make_steps, make_system, make_jobs, analysis_request, briefing_request, setup_prompt, tests_prompt, app_version, check_release, app_update_status, start_app_update])
        .build(tauri::generate_context!()).expect("error while building tauri application");
    app.run(|app, event| {
        if matches!(event, tauri::RunEvent::Ready) {
            if app.get_webview_window("main").is_some_and(|w| w.is_visible().unwrap_or(false)) {
                if let Ok(exe) = std::env::current_exe() {
                    if let Some(bundle) = exe.parent().and_then(Path::parent).and_then(Path::parent) {
                        acknowledge_update(&root().join(".app-update.json"), &app.package_info().version.to_string(), bundle);
                    }
                }
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn release_json(tag: &str) -> String {
        serde_json::json!({"tag_name":tag, "draft":false, "prerelease":false,
            "body":"### 한국어\n- 예시\n\n### English\n- Example"}).to_string()
    }

    #[test]
    fn release_versions_use_semver_precedence() {
        let release = parse_release(200, &release_json("v0.10.0"), "0.9.0").unwrap().latest.unwrap();
        assert!(release.newer);
        assert_eq!(release.url, "https://github.com/ganggangstone/where-were-we/releases/tag/v0.10.0");
        assert!(release.notes.contains("### 한국어"));
        assert!(release.notes.contains("### English"));
        assert!(!parse_release(200, &release_json("v0.9.0+rebuild"), "0.9.0").unwrap().latest.unwrap().newer);
        assert!(!parse_release(200, &release_json("v0.8.0"), "0.9.0").unwrap().latest.unwrap().newer);
    }

    #[test]
    fn release_check_handles_unpublished_and_invalid_responses() {
        assert!(parse_release(404, "{}", "0.1.0").unwrap().latest.is_none());
        assert!(parse_release(403, "{}", "0.1.0").is_err());
        assert!(parse_release(200, "not JSON", "0.1.0").is_err());
        assert!(parse_release(200, &release_json("../../other"), "0.1.0").is_err());
        assert!(parse_release(200, &release_json("v0.2.0-beta.1"), "0.1.0").unwrap().latest.is_none());
        for field in ["draft", "prerelease"] {
            let mut value: serde_json::Value = serde_json::from_str(&release_json("v0.2.0")).unwrap();
            value[field] = true.into();
            assert!(parse_release(200, &value.to_string(), "0.1.0").unwrap().latest.is_none());
        }
    }

    #[test]
    fn missing_bundled_runtime_is_an_error() {
        assert!(Backend::bundled(Path::new("/nonexistent/where-were-we-resources")).is_err());
    }

    #[test]
    fn backend_passes_paths_as_separate_arguments() {
        let backend = Backend {
            python: PathBuf::from("/Applications/where were we.app/runtime/python/bin/python3"),
            scripts: PathBuf::from("/Applications/where were we.app/runtime/backend"),
        };
        let command = backend.command("mapcore.py", &["setup"]);
        assert_eq!(command.get_program(), backend.python.as_os_str());
        let args: Vec<_> = command.get_args().collect();
        assert_eq!(args, ["-I", "-B", "/Applications/where were we.app/runtime/backend/mapcore.py", "setup"]);
    }

    #[test]
    fn bundled_python_runs_with_an_empty_home() {
        let backend = Backend::bundled(Path::new(env!("CARGO_MANIFEST_DIR"))).expect("Run scripts/prepare-runtime.py first");
        let home = std::env::temp_dir().join(format!("where-were-we-rust-{}", std::process::id()));
        fs::create_dir(&home).unwrap();
        let output = backend.command("mapcore.py", &["setup"])
            .env("HOME", &home).current_dir(&home).output().unwrap();
        fs::remove_dir(&home).unwrap();
        assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
        let text = String::from_utf8_lossy(&output.stdout);
        assert!(text.contains(backend.python.to_str().unwrap()));
        assert!(!text.contains(".venv"));
    }
    #[test]
    fn update_only_accepts_the_managed_app() {
        let app = Path::new("/Applications/where were we.app");
        let data = serde_json::json!({"casks":[{"full_token":"ganggangstone/tap/where-were-we", "installed":"0.1.0", "artifacts":[{"app":["where-were-we.app"], "target":app}]}]});
        assert_eq!(managed_version(&data, app).unwrap().to_string(), "0.1.0");
        assert!(managed_version(&data, Path::new("/other/build.app")).is_err());
        let mut other=data.clone();other["casks"][0]["full_token"]="another/tap/where-were-we".into();
        assert!(managed_version(&other, app).is_err());
        let mut absent=data;absent["casks"][0]["installed"]=serde_json::Value::Null;
        assert!(managed_version(&absent, app).is_err());
    }

    #[test]
    fn update_waits_for_a_published_brew_version() {
        assert!(available_update("0.2.0", "0.2.0").is_ok());
        assert!(available_update("0.3.0", "0.2.0").is_ok());
        assert!(available_update("0.1.0", "0.2.0").is_err());
        assert!(available_update("0.2.0-beta.1", "0.2.0").is_err());
        assert!(available_update("invalid", "0.2.0").is_err());
    }

    struct UpdateFixture { dir: PathBuf, job: UpdateJob }
    impl Drop for UpdateFixture { fn drop(&mut self) { let _ = fs::remove_dir_all(&self.dir); } }
    fn update_fixture() -> UpdateFixture {
        use std::os::unix::fs::PermissionsExt;
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        let sequence=NEXT.fetch_add(1,std::sync::atomic::Ordering::Relaxed);
        let dir=std::env::temp_dir().join(format!("www updater test {} {stamp} {sequence}",std::process::id()));
        let app=dir.join("Demo's app.app");fs::create_dir_all(app.join("Contents")).unwrap();
        for (name,version) in [("before.json","0.1.0"),("after.json","0.2.0")] {
            fs::write(dir.join(name),serde_json::to_vec(&serde_json::json!({"casks":[{
                "full_token":CASK,"version":"0.2.0","installed":version,"artifacts":[{"app":["where-were-we.app"],"target":app}]}]})).unwrap()).unwrap();
        }
        let plist=|v:&str|format!("<?xml version=\"1.0\"?><plist version=\"1.0\"><dict><key>CFBundleShortVersionString</key><string>{v}</string></dict></plist>");
        fs::write(app.join("Contents/Info.plist"),plist("0.1.0")).unwrap();
        fs::write(dir.join("new.plist"),plist("0.2.0")).unwrap();
        let brew=dir.join("brew");
        fs::write(&brew,r#"#!/bin/sh
base=$(dirname "$0")
echo "$*" >> "$base/calls"
case "$1" in
 update) if test -f "$base/hang"; then exec /bin/sleep 5; fi ;;
 info) if test -f "$base/upgraded"; then cat "$base/after.json"; else cat "$base/before.json"; fi ;;
 upgrade|reinstall) if test -f "$base/fail"; then echo 'download failed' >&2; exit 7; fi
          cp "$base/new.plist" "$base/Demo's app.app/Contents/Info.plist"
          touch "$base/upgraded" ;;
 *) exit 9 ;;
esac
"#).unwrap();fs::set_permissions(&brew,fs::Permissions::from_mode(0o755)).unwrap();
        let job=UpdateJob {brew,app,backup:dir.join("previous.app"),state:dir.join("state.json"),log:dir.join("log"),version:"0.2.0".into(),parent:99_999_999};
        UpdateFixture {dir,job}
    }

    #[test]
    fn updater_runs_the_brew_flow_and_checks_the_actual_app() {
        let fixture=update_fixture();perform_update(&fixture.job).unwrap();
        assert_eq!(update_state(&fixture.job.state).unwrap().stage,"restarting");
        let calls=fs::read_to_string(fixture.dir.join("calls")).unwrap();
        assert!(calls.contains("upgrade --cask ganggangstone/tap/where-were-we"));
        assert!(calls.starts_with("update\n"));
    }

    #[test]
    fn updater_stops_before_quitting_when_the_tap_is_behind() {
        let fixture=update_fixture();let path=fixture.dir.join("before.json");
        let mut data:serde_json::Value=serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        data["casks"][0]["version"]="0.1.0".into();fs::write(path,serde_json::to_vec(&data).unwrap()).unwrap();
        assert!(perform_update(&fixture.job).unwrap_err().contains("Homebrew does not have"));
        assert_eq!(update_state(&fixture.job.state).unwrap().stage,"checking");
        assert!(!fixture.dir.join("upgraded").exists());
    }

    #[test]
    fn updater_reports_download_failure_and_keeps_the_old_app() {
        let fixture=update_fixture();fs::write(fixture.dir.join("fail"),"").unwrap();
        assert!(perform_update(&fixture.job).unwrap_err().contains("download failed"));
        assert!(fs::read_to_string(fixture.job.app.join("Contents/Info.plist")).unwrap().contains("0.1.0"));
    }

    #[test]
    fn updater_rejects_a_wrong_bundle_version_and_times_out() {
        let fixture=update_fixture();fs::write(fixture.dir.join("new.plist"),fs::read(fixture.job.app.join("Contents/Info.plist")).unwrap()).unwrap();
        assert!(perform_update(&fixture.job).is_err());
        fs::write(fixture.dir.join("hang"),"").unwrap();let start=Instant::now();
        assert!(run_brew(&fixture.job,&["update"],Duration::from_millis(150)).unwrap_err().contains("timed out"));
        assert!(start.elapsed()<Duration::from_secs(2));
    }

    #[test]
    fn partial_backup_and_partial_recovery_never_replace_the_app() {
        let fixture=update_fixture();let original=fs::read(fixture.job.app.join("Contents/Info.plist")).unwrap();
        let partial_copy=|_source:&Path,target:&Path| -> Result<(),String> {
            fs::create_dir_all(target.join("Contents")).unwrap();
            fs::write(target.join("Contents/Info.plist"),"partial").unwrap();Err("disk full".into())
        };
        assert!(prepare_backup(&fixture.job,partial_copy).is_err());
        assert!(!fixture.job.backup.exists());
        assert_eq!(fs::read(fixture.job.app.join("Contents/Info.plist")).unwrap(),original);
        prepare_backup(&fixture.job,copy_app).unwrap();
        assert!(restore_app_using(&fixture.job,partial_copy).is_err());
        assert_eq!(fs::read(fixture.job.app.join("Contents/Info.plist")).unwrap(),original);
    }

    #[test]
    fn recovery_restores_missing_apps_and_retries_a_newer_receipt() {
        let fixture=update_fixture();perform_update(&fixture.job).unwrap();
        fs::remove_dir_all(&fixture.job.app).unwrap();restore_app(&fixture.job).unwrap();
        assert!(fs::read_to_string(fixture.job.app.join("Contents/Info.plist")).unwrap().contains("0.1.0"));
        fs::remove_dir_all(&fixture.job.backup).unwrap();perform_update(&fixture.job).unwrap();
        assert!(fs::read_to_string(fixture.dir.join("calls")).unwrap().contains("reinstall --cask"));
    }

    #[test]
    fn helper_inherits_the_update_lock_and_stale_states_are_recoverable() {
        let fixture=update_fixture();let lockpath=fixture.dir.join(".app-update.lock");
        let lock=fs::OpenOptions::new().create(true).truncate(false).read(true).write(true).open(&lockpath).unwrap();lock.try_lock().unwrap();
        let mut child=Command::new("/bin/sleep").arg("5").stdin(Stdio::from(lock)).spawn().unwrap();
        let other=fs::OpenOptions::new().read(true).write(true).open(&lockpath).unwrap();
        assert!(other.try_lock().is_err(),"Helper must retain the parent's lock");
        fs::write(fixture.dir.join(".app-update.json"),serde_json::to_vec(&UpdateState {stage:"checking".into(),version:"0.2.0".into(),error:None,app:None,backup:None,recovery_command:None}).unwrap()).unwrap();
        assert_eq!(read_update_status(&fixture.dir).unwrap().stage,"checking");
        child.kill().unwrap();child.wait().unwrap();assert!(other.try_lock().is_ok());
        // Release the probe explicitly before testing the no-lock state.
        other.unlock().unwrap();drop(other);
        assert_eq!(read_update_status(&fixture.dir).unwrap().stage,"failed");
    }

    #[test]
    fn recovery_storage_is_not_a_project() {
        let fixture=update_fixture();
        fs::create_dir(fixture.dir.join(".app-update-backup-example")).unwrap();
        fs::create_dir(fixture.dir.join("studio")).unwrap();
        assert!(!project_names(&fixture.dir).iter().any(|name| name.starts_with('.')));
        assert!(project_names(&fixture.dir).contains(&"studio".to_string()));
    }

    #[test]
    fn interrupted_updates_preserve_manual_recovery_details() {
        let mut fixture=update_fixture();
        fixture.job.state=fixture.dir.join(".app-update.json");
        prepare_backup(&fixture.job,copy_app).unwrap();
        write_update(&fixture.job,"installing",None).unwrap();
        let before=update_state(&fixture.job.state).unwrap();
        let data=serde_json::to_value(&before).unwrap();
        assert_eq!(data["backup"],fixture.job.backup.to_string_lossy().as_ref());
        assert!(data["recovery_command"].as_str().unwrap().contains("reinstall --cask ganggangstone/tap/where-were-we"));
        assert!(fs::read_to_string(&fixture.job.log).unwrap().contains(&fixture.job.backup.to_string_lossy().to_string()));
        fs::remove_dir_all(&fixture.job.app).unwrap();
        let interrupted=read_update_status(&fixture.dir).unwrap();
        assert_eq!(interrupted.stage,"failed");
        assert!(interrupted.error.unwrap().contains("Recovery copy:"));
        let after=serde_json::to_value(update_state(&fixture.job.state).unwrap()).unwrap();
        assert_eq!(after["backup"],data["backup"]);
        assert_eq!(after["app"],data["app"]);
        assert_eq!(after["recovery_command"],data["recovery_command"]);
        assert!(fixture.job.backup.join("Contents/Info.plist").exists());
    }

    #[test]
    fn only_the_requested_app_and_version_can_acknowledge_restart() {
        let fixture=update_fixture();write_update(&fixture.job,"restarting",None).unwrap();
        acknowledge_update(&fixture.job.state,"0.2.0",&fixture.dir);
        assert_eq!(update_state(&fixture.job.state).unwrap().stage,"restarting");
        acknowledge_update(&fixture.job.state,"0.1.0",&fixture.job.app);
        assert_eq!(update_state(&fixture.job.state).unwrap().stage,"restarting");
        acknowledge_update(&fixture.job.state,"0.2.0",&fixture.job.app);
        assert_eq!(update_state(&fixture.job.state).unwrap().stage,"completed");
    }

    #[test]
    fn updates_and_backend_work_exclude_each_other() {
        let work=BackendWork::start().unwrap();assert!(reserve_update_work().is_err());drop(work);
        reserve_update_work().unwrap();
        assert!(BackendWork::start().is_err());assert!(reserve_update_work().is_err());
        WORK.lock().unwrap().1=false;
        assert!(BackendWork::start().is_ok());
    }

}
