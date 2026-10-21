// Execute the same fixture contract in the app's actual engine.
import WebKit
import AppKit
class Probe: NSObject, WKNavigationDelegate {
 var web: WKWebView!
 var window: NSWindow!
 func start() {
  if CommandLine.arguments.count > 3 { NSApplication.shared.appearance=NSAppearance(named:CommandLine.arguments[3]=="dark" ? .darkAqua : .aqua) }
  let configuration=WKWebViewConfiguration()
  if CommandLine.arguments.count > 3 {
   let dark=CommandLine.arguments[3]=="dark" ? "true" : "false"
   configuration.userContentController.addUserScript(WKUserScript(source:"window.uiExpectedDark="+dark,injectionTime:.atDocumentStart,forMainFrameOnly:true))
  }
  web = WKWebView(frame: NSRect(x:0,y:0,width:Int(CommandLine.arguments[2])!,height:900),configuration:configuration)
  window = NSWindow(contentRect:web.frame,styleMask:[.titled],backing:.buffered,defer:false)
  window.contentView=web
  web.navigationDelegate=self
  web.loadFileURL(URL(fileURLWithPath:CommandLine.arguments[1]),allowingReadAccessTo:URL(fileURLWithPath:"/"))
 }
 func webView(_ view: WKWebView,didFinish navigation: WKNavigation!) {
  readResult()
 }
 func readResult() {
  web.evaluateJavaScript("window.uiSystemResult") { result,error in
   if let value=result as? String { print(value);exit(0) }
   DispatchQueue.main.asyncAfter(deadline:.now()+0.1){self.readResult()}
  }
 }
}
let probe=Probe();probe.start()
DispatchQueue.main.asyncAfter(deadline:.now()+20){exit(2)}
NSApplication.shared.run()
