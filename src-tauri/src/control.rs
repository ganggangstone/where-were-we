//! Local command mailbox. Only the webview acknowledges an applied UI action.
use serde_json::{json, Value};
use std::{collections::{VecDeque,HashSet}, sync::{Arc, Mutex}, time::{Duration, Instant}};

struct Entry { request:Value, session:String, created:Instant, status:String, result:Option<Value> }
#[derive(Default)]
struct Mailbox { session:String, heartbeat:Option<Instant>, entries:VecDeque<Entry>, seen:HashSet<String> }
pub struct Hub { inner:Mutex<Mailbox>, pub instance:String }
impl Default for Hub {fn default()->Self {Self {inner:Mutex::new(Mailbox::default()),instance:format!("{:x}",std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos())}}}
impl Hub {
    pub fn submit(&self, request:Value)->Value {
        let id=request["id"].as_str().unwrap_or("");
        if id.is_empty() || id.len()>80 || !id.bytes().all(|c| c.is_ascii_alphanumeric() || b"-_".contains(&c)) || !request["action"].is_string() || !request["arguments"].is_object() {return json!({"status":"invalid_command"});}
        let mut m=self.inner.lock().unwrap();
        if !id.starts_with(&(self.instance.clone()+"-")) {return json!({"id":id,"status":"obsolete_instance"});}
        if let Some(e)=m.entries.iter().find(|e| e.request["id"]==id) {return if e.request==request {Self::result(e)} else {json!({"id":id,"status":"command_id_conflict"})};}
        if m.seen.contains(id) {return json!({"id":id,"status":"result_expired","message":"Already accepted; will not replay"});}
        if m.heartbeat.is_none_or(|t| t.elapsed()>Duration::from_secs(5)) {return json!({"id":id,"status":"app_not_ready"});}
        if m.entries.iter().filter(|e| e.result.is_none()).count()>=32 {return json!({"id":id,"status":"busy"});}
        while m.entries.len()>=256 {if let Some(i)=m.entries.iter().position(|e|e.result.is_some()){m.entries.remove(i);}else{break;}}
        m.seen.insert(id.into());
        let session=m.session.clone();
        m.entries.push_back(Entry {request,session,created:Instant::now(),status:"queued".into(),result:None});
        Self::result(m.entries.back().unwrap())
    }
    fn result(e:&Entry)->Value {json!({"id":e.request["id"],"status":e.status,"result":e.result})}
    pub fn outcome(&self,id:&str)->Value {
        let m=self.inner.lock().unwrap();
        m.entries.iter().find(|e|e.request["id"]==id).map(Self::result).unwrap_or(json!({"id":id,"status":if m.seen.contains(id){"result_expired"}else{"unknown_command"}}))
    }
    pub fn poll(&self,session:&str)->Value {
        let mut m=self.inner.lock().unwrap();
        if session.is_empty() || session.len()>100 {return Value::Null;}
        if m.session!=session {
            for e in &mut m.entries {if e.result.is_none() {e.status="interrupted".into();e.result=Some(json!({"reason":"ui_reloaded","effect":"unknown; inspect current state before retrying"}));}}
            m.session=session.into();
        }
        m.heartbeat=Some(Instant::now());
        for e in &mut m.entries {if e.status=="queued" && e.created.elapsed()>Duration::from_secs(30) {e.status="expired".into();e.result=Some(json!({"reason":"not applied before queue deadline"}));}}
        if m.entries.iter().any(|e|e.status=="running") {return Value::Null;}
        if let Some(e)=m.entries.iter_mut().find(|e|e.status=="queued") {e.status="running".into();return e.request.clone();}
        Value::Null
    }
    pub fn acknowledge(&self,session:&str,id:&str,result:Value)->Value {
        let mut m=self.inner.lock().unwrap();
        if m.session!=session {return json!({"status":"obsolete_ui"});}
        if let Some(e)=m.entries.iter_mut().find(|e|e.request["id"]==id && e.session==session && e.status=="running") {
            e.status=if result["ok"]==true {"completed"}else{"failed"}.into();e.result=Some(result);return Self::result(e);
        }
        json!({"status":"not_running"})
    }
}

#[cfg(unix)]
pub fn listen(hub:Arc<Hub>,root:&std::path::Path)->Result<(),String> {
    use std::{fs,io::{BufRead,BufReader,Read,Write},os::unix::{fs::PermissionsExt,net::UnixListener}};
    let nonce=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let dir=std::path::PathBuf::from(format!("/tmp/where-were-we-{}-{nonce:x}",std::process::id()));
    fs::create_dir(&dir).map_err(|e|e.to_string())?;fs::set_permissions(&dir,fs::Permissions::from_mode(0o700)).map_err(|e|e.to_string())?;
    let socket=dir.join("app.sock");let listener=UnixListener::bind(&socket).map_err(|e|e.to_string())?;
    fs::set_permissions(&socket,fs::Permissions::from_mode(0o600)).map_err(|e|e.to_string())?;
    fs::create_dir_all(root).map_err(|e|e.to_string())?;
    let tmp=root.join(format!(".app-control-{}.tmp",std::process::id()));
    use std::os::unix::fs::OpenOptionsExt;
    let mut file=fs::OpenOptions::new().write(true).create_new(true).mode(0o600).open(&tmp).map_err(|e|e.to_string())?;
    file.write_all(json!({"protocol":1,"socket":socket,"instance":hub.instance,"pid":std::process::id()}).to_string().as_bytes()).map_err(|e|e.to_string())?;
    fs::rename(tmp,root.join(".app-control.json")).map_err(|e|e.to_string())?;
    std::thread::spawn(move || {
        for stream in listener.incoming() {
            let Ok(mut stream)=stream else {break};
            let _=stream.set_read_timeout(Some(Duration::from_secs(2)));let _=stream.set_write_timeout(Some(Duration::from_secs(2)));
            let mut line=String::new();
            let out=match BufReader::new((&stream).take(1_048_577)).read_line(&mut line) {
                Ok(n) if n<=1_048_576 => match serde_json::from_str::<Value>(&line) {
                    Ok(v) if v["op"]=="submit"=>hub.submit(v["command"].clone()),
                    Ok(v) if v["op"]=="result"=>hub.outcome(v["id"].as_str().unwrap_or("")),
                    _=>json!({"status":"invalid_request"})
                }, _=>json!({"status":"invalid_request"})
            };
            let _=writeln!(stream,"{out}");
        }
    });
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn command(h:&Hub,id:&str)->Value {json!({"id":h.instance.clone()+"-"+id,"action":"navigate","arguments":{"project":"demo"}})}
    #[test]fn only_webview_acknowledges_completion_and_commands_are_serial() {
        let h=Hub::default();assert_eq!(h.submit(command(&h,"one"))["status"],"app_not_ready");h.poll("ui1");
        assert_eq!(h.submit(command(&h,"one"))["status"],"queued");h.submit(command(&h,"two"));
        assert_eq!(h.poll("ui1")["id"],h.instance.clone()+"-one");assert!(h.poll("ui1").is_null());assert_eq!(h.outcome(&(h.instance.clone()+"-one"))["status"],"running");
        assert_eq!(h.acknowledge("ui1",&(h.instance.clone()+"-one"),json!({"ok":true,"state":{"selection":"screen:upload"}}))["status"],"completed");
        assert_eq!(h.poll("ui1")["id"],h.instance.clone()+"-two");assert_eq!(h.submit(command(&h,"one"))["status"],"completed");
        assert_eq!(h.acknowledge("ui1",&(h.instance.clone()+"-one"),json!({"ok":true}))["status"],"not_running");
    }
    #[test]fn reloaded_ui_never_replays_unknown_effects_or_accepts_old_ack() {
        let h=Hub::default();h.poll("ui1");h.submit(command(&h,"one"));h.submit(command(&h,"two"));h.poll("ui1");h.poll("ui2");
        assert_eq!(h.outcome(&(h.instance.clone()+"-one"))["status"],"interrupted");assert_eq!(h.outcome(&(h.instance.clone()+"-two"))["status"],"interrupted");
        assert_eq!(h.acknowledge("ui1",&(h.instance.clone()+"-one"),json!({"ok":true}))["status"],"obsolete_ui");
        assert_eq!(h.submit(json!({"id":h.instance.clone()+"-one","action":"state","arguments":{}}))["status"],"command_id_conflict");
    }
    #[test]fn evicted_results_and_old_app_ids_never_replay() {
        let h=Hub::default();h.poll("ui");let first=command(&h,"first");h.submit(first.clone());h.poll("ui");h.acknowledge("ui",first["id"].as_str().unwrap(),json!({"ok":true}));
        for i in 0..260 {let c=command(&h,&i.to_string());h.submit(c.clone());h.poll("ui");h.acknowledge("ui",c["id"].as_str().unwrap(),json!({"ok":true}));}
        assert_eq!(h.submit(first.clone())["status"],"result_expired");
        let next=Hub::default();next.poll("ui");assert_eq!(next.submit(first)["status"],"obsolete_instance");
    }
    #[cfg(unix)]
    #[test]fn real_private_socket_round_trip_preserves_ack_boundary() {
        use std::{fs,io::{BufRead,BufReader,Write},os::unix::{fs::PermissionsExt,net::UnixStream}};
        let h=Arc::new(Hub::default());let root=std::env::temp_dir().join(format!("www-hub-test-{}",h.instance));
        super::listen(h.clone(),&root).unwrap();
        let meta:Value=serde_json::from_str(&fs::read_to_string(root.join(".app-control.json")).unwrap()).unwrap();let socket=std::path::Path::new(meta["socket"].as_str().unwrap());
        assert_eq!(fs::metadata(socket).unwrap().permissions().mode() & 0o777,0o600);assert_eq!(fs::metadata(socket.parent().unwrap()).unwrap().permissions().mode() & 0o777,0o700);
        let send=|value:Value| {let mut s=UnixStream::connect(socket).unwrap();writeln!(s,"{value}").unwrap();let mut line=String::new();BufReader::new(s).read_line(&mut line).unwrap();serde_json::from_str::<Value>(&line).unwrap()};
        h.poll("ui");let c=command(&h,"socket");assert_eq!(send(json!({"op":"submit","command":c}))["status"],"queued");h.poll("ui");assert_eq!(send(json!({"op":"result","id":c["id"]}))["status"],"running");
        h.acknowledge("ui",c["id"].as_str().unwrap(),json!({"ok":true,"state":{"selection":["screen:upload"]}}));assert_eq!(send(json!({"op":"result","id":c["id"]}))["result"]["state"]["selection"][0],"screen:upload");
        fs::remove_file(socket).unwrap();fs::remove_dir(socket.parent().unwrap()).unwrap();fs::remove_dir_all(root).unwrap();
    }
    #[test]fn stale_and_expired_commands_do_not_apply_late() {
        let h=Hub::default();h.poll("ui");h.submit(command(&h,"one"));
        {let mut m=h.inner.lock().unwrap();m.entries[0].created=Instant::now()-Duration::from_secs(31);m.heartbeat=Some(Instant::now()-Duration::from_secs(6));}
        assert_eq!(h.submit(command(&h,"two"))["status"],"app_not_ready");assert!(h.poll("ui").is_null());assert_eq!(h.outcome(&(h.instance.clone()+"-one"))["status"],"expired");
    }
}
