"""Optional real-browser presentation checks (not a core unittest dependency).

Install Playwright separately: python -m pip install playwright
Use a system Chromium or: python -m playwright install chromium
Run: python tests/check_presentation_browser.py [--browser /path/to/chromium]
The analysis pipeline itself needs neither Playwright nor a browser.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser",default=shutil.which("chromium") or shutil.which("google-chrome"))
    args=parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise SystemExit("Optional check: install playwright separately first. See this file's docstring.") from error
    checks=[]
    requests=[]
    errors=[]
    url=(ROOT/"presentation.html").as_uri()
    def checked(name,condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.browser,headless=True,args=["--no-sandbox","--allow-file-access-from-files"])
        context=browser.new_context(viewport={"width":1366,"height":900},offline=True,reduced_motion="reduce")
        page=context.new_page()
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.on("request",lambda request:requests.append(request.url) if request.url.startswith(("https:","http:")) else None)
        page.goto(url)
        page.wait_for_load_state("networkidle")
        def current():
            return page.evaluate("document.querySelectorAll('.slide:not([hidden])').length===1 ? Array.from(document.querySelectorAll('.slide')).indexOf(document.querySelector('.slide:not([hidden])'))+1 : 0")
        def go(n):
            page.evaluate("n=>{location.hash='/'+n}",n)
            page.wait_for_function("n=>document.querySelector('.slide:not([hidden])').getAttribute('aria-labelledby')==='s'+n",arg=n)
        def unfocus():
            page.evaluate("document.activeElement.blur()")
        checked("offline opening / slide 1",current()==1)
        checked("five local images decoded",page.evaluate("Array.from(document.images).length===5 && Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)"))
        checked("reduced-motion preference",page.locator("#progress").evaluate("e=>getComputedStyle(e).transitionDuration==='0s'"))
        page.keyboard.press("ArrowRight")
        checked("right arrow",current()==2)
        page.locator("#next").click()
        page.keyboard.press("ArrowRight")
        checked("arrow navigation after button focus",current()==4)
        page.locator("#next").focus()
        page.keyboard.press("Space")
        checked("focused button space advances only once",current()==5)
        unfocus();page.keyboard.press("Home")
        checked("Home and disabled previous",current()==1 and page.locator("#prev").is_disabled())
        page.keyboard.press("ArrowLeft")
        checked("lower navigation boundary",current()==1)
        page.keyboard.press("End")
        checked("End and disabled next",current()==11 and page.locator("#next").is_disabled())
        page.keyboard.press("ArrowRight")
        checked("upper navigation boundary",current()==11)
        page.keyboard.press("m")
        checked("keyboard table of contents",page.locator("#toc").evaluate("e=>e.open"))
        checked("dialog focus is contained",page.locator("#toc").evaluate("e=>e.contains(document.activeElement)"))
        page.locator("#tocGrid button").nth(8).click()
        checked("table of contents selection",current()==9 and not page.locator("#toc").evaluate("e=>e.open"))
        unfocus();page.keyboard.press("n")
        checked("per-slide speaker notes",page.locator("#notes").evaluate("e=>e.open") and "2024" in page.locator("#notesContent").inner_text())
        page.keyboard.press("Escape")
        checked("native Escape dialog close",not page.locator("#notes").evaluate("e=>e.open"))
        page.locator("#readerToggle").click()
        checked("reader exposes all slides",page.locator(".slide:not([hidden])").count()==11)
        page.locator("#readerToggle").click()
        checked("reader restores one slide",current()==9)
        page.locator("#fullscreen").click()
        page.wait_for_function("document.fullscreenElement!==null")
        checked("fullscreen entered",page.evaluate("!!document.fullscreenElement"))
        page.locator("#fullscreen").click()
        page.wait_for_function("document.fullscreenElement===null")
        checked("fullscreen exited",not page.evaluate("!!document.fullscreenElement"))
        page.goto(url+"#/10")
        checked("direct hash link",current()==10)
        viewports=[(1366,900),(1366,768),(1920,1080),(375,812),(768,1024)]
        for width,height in viewports:
            page.set_viewport_size({"width":width,"height":height})
            for i in range(1,12):
                go(i)
                layout=page.evaluate("""()=>{const s=document.querySelector('.slide:not([hidden])'),b=s.getBoundingClientRect();return document.documentElement.scrollWidth<=innerWidth+2 && s.scrollHeight<=s.clientHeight+3 && s.querySelector('.foot').getBoundingClientRect().bottom<=b.bottom+2;}""")
                checked(f"layout {width}x{height} / slide {i:02}",layout)
        page.set_viewport_size({"width":375,"height":812});go(1)
        page.evaluate("""()=>{const d=document.getElementById('deck');const a=new Touch({identifier:1,target:d,clientX:280,clientY:200});const b=new Touch({identifier:1,target:d,clientX:60,clientY:200});d.dispatchEvent(new TouchEvent('touchstart',{touches:[a],bubbles:true}));d.dispatchEvent(new TouchEvent('touchend',{changedTouches:[b],bubbles:true}));}""")
        checked("horizontal touch swipe",current()==2)
        checked("mobile navigation labels stay on one line",page.locator(".controls button").evaluate_all("buttons=>buttons.every(b=>{const r=document.createRange();r.selectNodeContents(b);return r.getClientRects().length===1;})"))
        page.evaluate("window.scrollTo(0,document.body.scrollHeight)")
        page.locator("#next").click()
        checked("mobile navigation restores slide top",current()==3 and page.evaluate("window.scrollY===0"))
        go(2)
        page.set_viewport_size({"width":1366,"height":900})
        with tempfile.TemporaryDirectory(prefix="co2-presentation-print-") as temporary:
            pdf=page.pdf(path=str(Path(temporary)/"presentation.pdf"),print_background=True,prefer_css_page_size=True)
            pages=len(re.findall(rb"/Type /Page\b",pdf))
            checked("print / PDF contains all 11 slides",pages==11)
        checked("afterprint restores current slide",current()==2)
        nojs=browser.new_context(java_script_enabled=False,offline=True,viewport={"width":1366,"height":900})
        fallback=nojs.new_page();fallback.goto(url)
        checked("no-JavaScript readable fallback",fallback.locator(".slide:visible").count()==11)
        checked("no-JavaScript explanation",fallback.locator("noscript").is_visible())
        nojs.close()
        checked("no JavaScript errors",not errors)
        checked("no remote network requests",not requests)
        result={
            "status":"passed", "browser":"Chromium "+browser.version,
            "presentation_sha256":hashlib.sha256((ROOT/"presentation.html").read_bytes()).hexdigest(),
            "raw_sha256":hashlib.sha256((ROOT/"data/raw/monthly_in_situ_co2_mlo.csv").read_bytes()).hexdigest(),
            "offline_browser_context":True, "remote_request_count":len(requests),
            "javascript_errors":errors, "slides":11, "print_pdf_pages":pages,
            "viewports":[{"width":w,"height":h} for w,h in viewports],
            "layout_checks":len(viewports)*11, "checks_passed":len(checks), "checks":checks,
            "scope":"Chromium on Linux; other browsers and presentation hardware not tested. PDF is temporary, not a submitted artifact."
        }
        browser.close()
    path=ROOT/"results/presentation_validation.json"
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"PASS: {len(checks)} browser checks, 55 responsive slide layouts, 11 printed pages, no network requests")
    print(f"Saved {path.relative_to(ROOT)}")


if __name__=="__main__":
    main()
