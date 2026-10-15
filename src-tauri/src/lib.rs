use std::{fs, path::{Path, PathBuf}, process::Command};
use tauri::Manager;

fn root() -> PathBuf {
    PathBuf::from(std::env::var("HOME").unwrap_or_default()).join(".where-were-we")
}

/// ~/.where-were-we/<프로젝트>/ 폴더 이름 목록.
#[tauri::command]
fn list_projects() -> Vec<String> {
    let mut v: Vec<String> = fs::read_dir(root())
        .map(|d| d.flatten().filter(|e| e.path().is_dir()).filter_map(|e| e.file_name().into_string().ok()).collect())
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
    let out = backend(app)?.command(script, args).output().map_err(|e| e.to_string())?;
    if out.status.success() { Ok(String::from_utf8_lossy(&out.stdout).to_string()) }
    else { Err(String::from_utf8_lossy(&out.stderr).to_string()) }
}

/// 새로고침: refresh.py 가 fetch, 바뀐 브랜치의 지도 다시 뽑기, 수집, 달라진 것 기록을 한다. 로그를 돌려준다.
#[tauri::command]
async fn refresh(app: tauri::AppHandle, project: String, repo: String, since: String) -> Result<String, String> {
    run_py(&app, "refresh.py", &[&project, &repo, &since])
}

/// group.py 를 돌려 묶음을 다시 제안받는다 (AI 호출, 버튼을 눌렀을 때만).
#[tauri::command]
async fn suggest_groups(app: tauri::AppHandle, project: String, branch: String) -> Result<String, String> {
    run_py(&app, "group.py", &[&project, &branch])
}

/// 에이전트 연결 프롬프트 (mapcore.py setup). 이 맥의 경로가 채워진다.
#[tauri::command]
async fn setup_prompt(app: tauri::AppHandle, lang: Option<String>) -> Result<String, String> {
    run_py(&app, "mapcore.py", &["setup", if lang.as_deref() == Some("en") { "--lang=en" } else { "--lang=ko" }])
}

/// 테스트가 안 이어진 서버 기능 하나에 대해 에이전트가 테스트를 찾게 하는 글 (mapcore.py tests).
#[tauri::command]
async fn tests_prompt(app: tauri::AppHandle, project: String, route: String, lang: Option<String>) -> Result<String, String> {
    run_py(&app, "mapcore.py", &["tests", &project, &route, if lang.as_deref() == Some("en") { "--lang=en" } else { "--lang=ko" }])
}

/// jobs.py 를 돌려 서버 밖 프로그램 하나가 하는 일을 에이전트가 읽어 적게 한다 (AI 호출, 버튼을 눌렀을 때만).
#[tauri::command]
async fn make_jobs(app: tauri::AppHandle, project: String, node: String) -> Result<String, String> {
    run_py(&app, "jobs.py", &[&project, &node])
}

/// system.py 를 돌려 전체 구조를 에이전트가 저장소를 읽어 다시 적게 한다 (AI 호출, 버튼을 눌렀을 때만).
#[tauri::command]
async fn make_system(app: tauri::AppHandle, project: String) -> Result<String, String> {
    run_py(&app, "system.py", &[&project])
}

/// steps.py 를 돌려 화면 하나의 "누르면 생기는 일" 단계를 만든다 (AI 호출, 버튼을 눌렀을 때만).
#[tauri::command]
async fn make_steps(app: tauri::AppHandle, project: String, branch: String, screen: String) -> Result<String, String> {
    run_py(&app, "steps.py", &[&project, &branch, &screen])
}

/// zed://file/... 같은 주소를 macOS `open` 으로 연다.
#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    Command::new("open").arg(&url).status().map(|_| ()).map_err(|e| e.to_string())
}

const RELEASE_API: &str = "https://api.github.com/repos/ganggangstone/where-were-we/releases/latest";
const RELEASE_PAGE: &str = "https://github.com/ganggangstone/where-were-we/releases";

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
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![list_projects, read_map, open_url, refresh, suggest_groups, make_steps, make_system, make_jobs, setup_prompt, tests_prompt, app_version, check_release])
        .run(tauri::generate_context!())
        .expect("error while building tauri application");
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
}
