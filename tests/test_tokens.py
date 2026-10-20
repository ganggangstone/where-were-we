"""ui/check_tokens.py 가 실제로 생길 법한 디자인 값 사본을 잡는지 본다.
ui 폴더를 임시로 복사해 한 곳씩 깨뜨리고 검사기를 돌린다."""
import os, shutil, subprocess, sys, tempfile, unittest

UI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")
CHECK = os.path.join(UI, "check_tokens.py")


def run(folder):
    return subprocess.run([sys.executable, CHECK, folder], capture_output=True, text=True)


class TokenCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ui = os.path.join(self.tmp, "ui")
        shutil.copytree(UI, self.ui, ignore=shutil.ignore_patterns("__pycache__", "vendor"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def append(self, name, text):
        with open(os.path.join(self.ui, name), "a", encoding="utf-8") as f:
            f.write(text)

    def test_current_ui_passes(self):
        r = run(self.ui)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_css_literals_fail(self):
        for text in (".x { opacity:.5 }", ".x { font-weight:500 }", ".x:active { transform:scale(0.95) }",
                     ".x { margin:1rem }", ".x { height:50vh }", ".x { color:hsl(0 0% 50%) }", ".x { color:#0066cc }"):
            with self.subTest(text=text):
                shutil.copy(os.path.join(UI, "app.css"), os.path.join(self.ui, "app.css"))
                self.append("app.css", "\n" + text + "\n")
                self.assertEqual(run(self.ui).returncode, 1, text)

    def test_script_literals_fail(self):
        cases = {
            "control.js": ["el.style.color = 'red';", "const c = '#0066cc';", "el.style.cssText = 'top:0';", "const w = '12px';",
                           "el.style.width = 12 + 'px';", "el.style.opacity = 0.5;", "el.style.setProperty('color', 'red');",
                           "el.style['color'] = 'red';", "Object.assign(el.style, { color: 'red' });",
                           "svg.setAttribute('fill', 'var(--color-accent, #06c)');", "el.setAttribute('stroke-width', 2);"],
            "connection.js": ["svg.setAttribute('fill', 'rgba(0,0,0,.2)');", "ln.setAttribute('stroke-width', '2');", "path.setAttribute('stroke', '#888');"],
            "index.html": ["<script>const gap = parseFloat(getComputedStyle(b).getPropertyValue('--space-8')) || 48;</script>",
                           "<i style='width:3px'></i>", '<svg><path stroke-width="1.5" d="M0 0"/></svg>',
                           "<script>const attrs = { d, fill: '#0066cc' };</script>"],
        }
        for name, texts in cases.items():
            for text in texts:
                with self.subTest(file=name, text=text):
                    shutil.copy(os.path.join(UI, name), os.path.join(self.ui, name))
                    self.append(name, "\n" + text + "\n")
                    self.assertEqual(run(self.ui).returncode, 1, text)

    def test_computed_geometry_is_allowed(self):
        # 자료에서 계산한 위치·막대 길이는 디자인 값이 아니다
        self.append("control.js", "\nel.style.left = x + 'px'; el.style.top = p.y * 0.35 + 'px';\n")
        self.append("index.html", '\n<i style="width:${pct}%"></i>\n<marker viewBox="0 0 10 10" markerWidth="9"><path d="M0 0L10 5"/></marker>\n')
        # 토큰을 쓰는 대입, 배치 낱말, 화면에 넣지 않는 보통 글자도 통과한다
        self.append("connection.js", "\nel.style.color = 'var(--color-accent)'; el.style.display = 'none'; el.style.width = '';"
                    " const c = 'red'; path.setAttribute('fill', 'none'); Object.assign(el.style, { left: x + 'px' });\n")
        r = run(self.ui)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
