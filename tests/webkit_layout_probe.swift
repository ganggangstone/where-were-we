// Real WebKit (WKWebView, the engine the macOS app uses) layout probe.
// Usage: webkit_layout_probe <page.html>; prints one JSON line of #insp/#map bounds per inspector state.
import WebKit
import AppKit

let states = ["", "<div class=sect><h2>x</h2></div>", "<div class=hint>pick</div>", "", "<div class=sect><h2>y</h2></div>"]
let measure = "(()=>{const r=document.getElementById('insp').getBoundingClientRect(),m=document.getElementById('map').getBoundingClientRect();return JSON.stringify({map_w:Math.round(m.width),insp_x:Math.round(r.x),insp_y:Math.round(r.y),insp_w:Math.round(r.width)})})()"

class Probe: NSObject, WKNavigationDelegate {
  var web: WKWebView!
  var index = 0
  func start() {
    web = WKWebView(frame: NSRect(x: 0, y: 0, width: 1446, height: 870))
    let window = NSWindow(contentRect: web.frame, styleMask: [.titled], backing: .buffered, defer: false)
    window.contentView = web
    window.orderFrontRegardless()
    web.navigationDelegate = self
    web.loadFileURL(URL(fileURLWithPath: CommandLine.arguments[1]), allowingReadAccessTo: URL(fileURLWithPath: "/"))
  }
  // Change only #insp's children, as the app does, then read layout without forcing other restyles.
  func step() {
    if index == states.count { exit(0) }
    let html = states[index].replacingOccurrences(of: "'", with: "\\'")
    web.evaluateJavaScript("document.getElementById('insp').innerHTML='\(html)';1") { _, _ in
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
        self.web.evaluateJavaScript(measure) { result, _ in
          print(result as? String ?? "{}")
          self.index += 1
          self.step()
        }
      }
    }
  }
  func webView(_ view: WKWebView, didFinish navigation: WKNavigation!) { step() }
}

let probe = Probe()
probe.start()
DispatchQueue.main.asyncAfter(deadline: .now() + 30) { exit(2) }
NSApplication.shared.run()
