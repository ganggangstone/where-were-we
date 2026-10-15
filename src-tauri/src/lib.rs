use std::{fs, path::PathBuf, process::Command};

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

fn scripts_dir() -> PathBuf {
    // 개발 중에는 src-tauri/target/debug/<bin> 이므로 세 단계 위가 저장소 루트다.
    let exe = std::env::current_exe().unwrap_or_default();
    for anc in exe.ancestors() {
        if anc.join("extract.py").exists() { return anc.to_path_buf(); }
    }
    PathBuf::from(".")
}

fn run_py(script: &str, args: &[&str]) -> Result<String, String> {
    let out = Command::new("python3").arg(scripts_dir().join(script)).args(args).output().map_err(|e| e.to_string())?;
    if out.status.success() { Ok(String::from_utf8_lossy(&out.stdout).to_string()) }
    else { Err(String::from_utf8_lossy(&out.stderr).to_string()) }
}

/// 새로고침: refresh.py 가 fetch, 바뀐 브랜치의 지도 다시 뽑기, 수집, 달라진 것 기록을 한다. 로그를 돌려준다.
#[tauri::command]
async fn refresh(project: String, repo: String, since: String) -> Result<String, String> {
    run_py("refresh.py", &[&project, &repo, &since])
}

/// group.py 를 돌려 묶음을 다시 제안받는다 (AI 호출, 버튼을 눌렀을 때만).
#[tauri::command]
async fn suggest_groups(project: String, branch: String) -> Result<String, String> {
    run_py("group.py", &[&project, &branch])
}

/// 에이전트 연결 프롬프트 (mapcore.py setup). 이 맥의 경로가 채워진다.
#[tauri::command]
async fn setup_prompt() -> Result<String, String> {
    run_py("mapcore.py", &["setup"])
}

/// 테스트가 안 이어진 서버 기능 하나에 대해 에이전트가 테스트를 찾게 하는 글 (mapcore.py tests).
#[tauri::command]
async fn tests_prompt(project: String, route: String) -> Result<String, String> {
    run_py("mapcore.py", &["tests", &project, &route])
}

/// jobs.py 를 돌려 서버 밖 프로그램 하나가 하는 일을 에이전트가 읽어 적게 한다 (AI 호출, 버튼을 눌렀을 때만).
#[tauri::command]
async fn make_jobs(project: String, node: String) -> Result<String, String> {
    run_py("jobs.py", &[&project, &node])
}

/// system.py 를 돌려 전체 구조를 에이전트가 저장소를 읽어 다시 적게 한다 (AI 호출, 버튼을 눌렀을 때만).
#[tauri::command]
async fn make_system(project: String) -> Result<String, String> {
    run_py("system.py", &[&project])
}

/// steps.py 를 돌려 화면 하나의 "누르면 생기는 일" 단계를 만든다 (AI 호출, 버튼을 눌렀을 때만).
#[tauri::command]
async fn make_steps(project: String, branch: String, screen: String) -> Result<String, String> {
    run_py("steps.py", &[&project, &branch, &screen])
}

/// zed://file/... 같은 주소를 macOS `open` 으로 연다.
#[tauri::command]
fn open_url(url: String) -> Result<(), String> {
    Command::new("open").arg(&url).status().map(|_| ()).map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![list_projects, read_map, open_url, refresh, suggest_groups, make_steps, make_system, make_jobs, setup_prompt, tests_prompt])
        .run(tauri::generate_context!())
        .expect("error while building tauri application");
}
