import os
import time
import threading
from typing import Optional, Dict, Any, List

class WorkerStatus:
    IDLE = "Idle"
    RUNNING = "Running"
    PAUSED = "Paused"
    STOPPED = "Stopped"
    COMPLETED = "Completed"
    FAILED = "Failed"
    WAITING_FOR_GMAIL = "Waiting for Gmail"
    ENTERING_EMAIL = "Entering Email"
    ENTERING_VERIFICATION = "Entering Verification"
    CREATING_TEST_ACCOUNT = "Creating Account"
    OPENING_DOLA = "Opening Dola"
    GOOGLE_LOGIN = "Google Login"

class QAWorker:
    def __init__(self, worker_id: int, state_manager, gmail_manager, workflow_manager, on_update_callback=None):
        self.worker_id = worker_id
        self.state_manager = state_manager
        self.gmail_manager = gmail_manager
        self.workflow_manager = workflow_manager
        self.on_update_callback = on_update_callback
        
        self.status = WorkerStatus.IDLE
        self.account_email = ""
        self.step = "Initialized"
        self.error_message = ""
        self.last_url = ""
        self.matched_code = ""

        self._thread: Optional[threading.Thread] = None
        self._pw = None
        self._browser_context = None
        self._page = None

        self._paused = False
        self._stopped = False
        self.pending_selector: Optional[Dict[str, Any]] = None
        self._selector_event = threading.Event()

    def _log(self, level: str, msg: str):
        self.state_manager.log(self.worker_id, level, f"Worker #{self.worker_id} {msg}")

    def _update(self, status: str, step: str, last_url: str = None, error: str = ""):
        self.status = status
        self.step = step
        if last_url is not None:
            self.last_url = last_url
        if error:
            self.error_message = error

        self.state_manager.save_worker_state(
            self.worker_id, self.account_email, status, step,
            self.last_url, self.error_message,
        )
        if self.on_update_callback:
            self.on_update_callback(self.worker_id, status, step)

    def _wait_if_paused(self):
        while self._paused and not self._stopped:
            time.sleep(0.3)

    def _pause_missing_selector(self, step_name: str, step_data: dict):
        self._log("WARN", f"Failed step: {step_name}. Pausing for manual selector entry.")
        self.pending_selector = {
            "step": step_name,
            "data": step_data
        }
        self._update(WorkerStatus.PAUSED, f"Missing selector for {step_name}")
        self._selector_event.clear()
        
        while not self._selector_event.is_set() and not self._stopped:
            time.sleep(0.3)
            
        self.pending_selector = None
        if not self._stopped:
            self._update(WorkerStatus.RUNNING, f"Resuming {step_name}")

    def _screenshot_on_error(self):
        if not self._page or self.state_manager.get_setting("mock_mode", False): return
        try:
            os.makedirs("errors", exist_ok=True)
            path = f"errors/worker_{self.worker_id}_error.png"
            self._page.screenshot(path=path)
            self._log("INFO", f"Saved error screenshot to {path}")
        except Exception as e:
            self._log("WARN", f"Failed to save screenshot: {e}")

    def _try_fill(self, step_data: dict, text: str) -> bool:
        sel_type = step_data["selector_type"]
        selector = step_data["selector_value"]
        fallback = step_data.get("fallback_selector", "")
        pw_sel = self.workflow_manager.to_playwright(sel_type, selector)
        timeout = step_data.get("timeout", 15000)
        
        try:
            self._page.wait_for_selector(pw_sel, state="visible", timeout=timeout)
            self._page.fill(pw_sel, text)
            return True
        except:
            if fallback:
                fb_sel = self.workflow_manager.to_playwright(sel_type, fallback)
                try:
                    self._page.wait_for_selector(fb_sel, state="visible", timeout=timeout)
                    self._page.fill(fb_sel, text)
                    return True
                except:
                    pass
        return False

    def _try_click(self, step_data: dict) -> bool:
        sel_type = step_data["selector_type"]
        selector = step_data["selector_value"]
        fallback = step_data.get("fallback_selector", "")
        pw_sel = self.workflow_manager.to_playwright(sel_type, selector)
        timeout = step_data.get("timeout", 15000)
        
        try:
            self._page.wait_for_selector(pw_sel, state="visible", timeout=timeout)
            self._page.click(pw_sel)
            return True
        except:
            if fallback:
                fb_sel = self.workflow_manager.to_playwright(sel_type, fallback)
                try:
                    self._page.wait_for_selector(fb_sel, state="visible", timeout=timeout)
                    self._page.click(fb_sel)
                    return True
                except:
                    pass
        return False

    def _run(self):
        self._stopped = False
        self._paused = False
        self.error_message = ""
        self.matched_code = ""
        self.workflow_start_time = time.time()
        mock_mode = self.state_manager.get_setting("mock_mode", False)
        headless = self.state_manager.get_setting("browser_mode", "headed") == "headless"

        self._update(WorkerStatus.RUNNING, "Starting browser")
        self._log("INFO", "Browser started")

        try:
            if not mock_mode:
                try:
                    from playwright.sync_api import sync_playwright
                    self._pw = sync_playwright().start()
                    nav_timeout = self.state_manager.get_setting("navigation_timeout", 30000)
                    self._browser = self._pw.chromium.launch(
                        headless=headless,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                        ]
                    )
                    self._browser_context = self._browser.new_context()
                    self._browser_context.set_default_navigation_timeout(nav_timeout)
                    self._browser_context.set_default_timeout(
                        self.state_manager.get_setting("default_timeout", 15000)
                    )
                    pages = self._browser_context.pages
                    self._page = pages[0] if pages else self._browser_context.new_page()
                    self._log("INFO", f"Chromium launched ({'headless' if headless else 'headed'})")
                except ImportError:
                    raise RuntimeError("Playwright is not installed. Run: python -m pip install playwright")
            else:
                self._log("INFO", "Mock mode active")

            # Execute Workflow Steps Dynamically
            steps = self.workflow_manager.get_all()
            step_idx = 0
            while step_idx < len(steps):
                step = steps[step_idx]
                self._wait_if_paused()
                if self._stopped: return

                step_name = step["step_name"]
                action = step["action"]
                delay = step.get("delay_seconds", 2)
                
                self._update(WorkerStatus.RUNNING, f"Executing: {step_name}")
                self._log("INFO", f"Step: {step_name} [{action}]")

                # Wait for the page to settle before doing any UI action
                if not mock_mode and action not in ("Wait for Gmail", "Save Cookies", "Stop Workflow", "Navigate"):
                    try:
                        self._page.wait_for_load_state("domcontentloaded", timeout=5000)
                        # Optionally wait a tiny bit for JS frameworks to hydrate
                        self._page.wait_for_timeout(500)
                    except:
                        pass

                if action == "Navigate":
                    url = step["selector_value"].replace("{{SIGNUP_URL}}", self.state_manager.get_setting("signup_flow_url", "")).replace("{{DOLA_URL}}", self.state_manager.get_setting("dola_url", ""))
                    if not mock_mode:
                        self._page.goto(url, wait_until="domcontentloaded")
                        self.last_url = self._page.url
                    
                elif action == "Type":
                    val = step["input_value"].replace("{{EMAIL}}", self.account_email).replace("{{GMAIL_CODE}}", self.matched_code)
                    if not mock_mode:
                        if not self._try_fill(step, val):
                            self._pause_missing_selector(step_name, step)
                            if not self._stopped and not self._try_fill(step, val):
                                raise RuntimeError(f"Could not complete step: {step_name}")
                        self._log("INFO", f"Typed: {val}")

                elif action == "Click":
                    if not mock_mode:
                        if not self._try_click(step):
                            self._pause_missing_selector(step_name, step)
                            if not self._stopped and not self._try_click(step):
                                raise RuntimeError(f"Could not complete step: {step_name}")
                                
                elif action == "Click If Exists":
                    if not mock_mode:
                        try:
                            sel_type = step["selector_type"]
                            selector = step["selector_value"]
                            pw_sel = self.workflow_manager.to_playwright(sel_type, selector)
                            self._page.wait_for_selector(pw_sel, state="visible", timeout=step.get("timeout", 5000))
                            self._page.click(pw_sel)
                            self._log("INFO", "Element found and clicked")
                        except:
                            self._log("INFO", "Element not found, skipping click")

                elif action == "Wait for Gmail":
                    self._update(WorkerStatus.WAITING_FOR_GMAIL, "Waiting for verification email...")
                    email_timeout = self.state_manager.get_setting("email_timeout", 120)
                    poll_interval = self.state_manager.get_setting("gmail_polling_interval", 5)
                    start_wait = time.time()
                    self.matched_code = ""

                    while time.time() - start_wait < email_timeout and not self._stopped:
                        self._wait_if_paused()
                        res = self.gmail_manager.search_verification_email(
                            self.account_email, 
                            after_timestamp=self.workflow_start_time
                        )
                        if res and res.get("matched"):
                            self.matched_code = res["code"]
                            break
                        time.sleep(poll_interval)

                    if not self.matched_code and not self._stopped:
                        raise RuntimeError("Verification email timeout")

                elif action == "Wait for Element":
                    if not mock_mode:
                        sel_type = step["selector_type"]
                        selector = step["selector_value"]
                        pw_sel = self.workflow_manager.to_playwright(sel_type, selector)
                        self._page.wait_for_selector(pw_sel, state="visible", timeout=step.get("timeout", 15000))
                        
                elif action in ("Skip Next If Exists", "Skip Next If Missing", "Jump To If Exists", "Jump To If Missing"):
                    if not mock_mode:
                        sel_type = step["selector_type"]
                        selector = step["selector_value"]
                        pw_sel = self.workflow_manager.to_playwright(sel_type, selector)
                        found = False
                        try:
                            self._page.wait_for_selector(pw_sel, state="visible", timeout=step.get("timeout", 5000))
                            found = True
                        except:
                            pass
                        
                        should_trigger = (found and "If Exists" in action) or (not found and "If Missing" in action)
                        
                        if should_trigger:
                            self._log("INFO", f"Condition met! Triggering {action}")
                            if action.startswith("Skip Next"):
                                step_idx += 2
                                continue
                            elif action.startswith("Jump To"):
                                target_name = step.get("input_value", "").strip()
                                target_idx = -1
                                for i, s in enumerate(steps):
                                    if s["step_name"] == target_name:
                                        target_idx = i
                                        break
                                if target_idx != -1:
                                    step_idx = target_idx
                                    continue
                                else:
                                    self._log("WARN", f"Jump target '{target_name}' not found!")
                        else:
                            self._log("INFO", "Condition not met.")
                
                elif action == "Save Cookies":
                    if not mock_mode:
                        import json
                        os.makedirs("cookies", exist_ok=True)
                        all_cookies = self._browser_context.cookies()
                        
                        # Filter to strictly keep ONLY Dola cookies, ignore Google/others
                        dola_cookies = [c for c in all_cookies if "dola" in c["domain"].lower()]
                        
                        cookie_path = os.path.abspath(f"cookies/{self.account_email}.json")
                        with open(cookie_path, "w", encoding="utf-8") as f:
                            json.dump(dola_cookies, f, indent=4)
                        self._log("INFO", f"Successfully saved {len(dola_cookies)} Dola cookies to {cookie_path}")
                        
                elif action == "Stop Workflow":
                    self._log("INFO", "Stop Workflow triggered. Halting gracefully.")
                    break
                    
                elif action == "Stop If URL Contains":
                    if not mock_mode:
                        target_url = step.get("selector_value", "")
                        if target_url and target_url in self._page.url:
                            self._log("WARN", f"URL matched '{target_url}'. Halting workflow early.")
                            break
                            
                elif action == "Jump To If URL Contains":
                    if not mock_mode:
                        target_url = step.get("selector_value", "")
                        if target_url and target_url in self._page.url:
                            target_name = step.get("input_value", "").strip()
                            target_idx = -1
                            for i, s in enumerate(steps):
                                if s["step_name"] == target_name:
                                    target_idx = i
                                    break
                            if target_idx != -1:
                                self._log("INFO", f"URL matched '{target_url}'. Jumping to {target_name}.")
                                step_idx = target_idx
                                continue
                            else:
                                self._log("WARN", f"Jump target '{target_name}' not found!")

                if delay > 0 and not self._stopped:
                    self._log("INFO", f"Waiting {delay} seconds...")
                    if not mock_mode:
                        self._page.wait_for_timeout(delay * 1000)
                    else:
                        time.sleep(delay)
                
                step_idx += 1

            if self._stopped: return
            
            self._update(WorkerStatus.COMPLETED, "Workflow Completed successfully")
            self._log("INFO", "Workflow Completed successfully")

        except Exception as exc:
            self._update(WorkerStatus.FAILED, f"Error: {str(exc)[:80]}", error=str(exc))
            self._log("ERROR", f"Error in worker #{self.worker_id}: {exc}")
            self._screenshot_on_error()
        finally:
            if self._browser_context:
                try: self._browser_context.close()
                except: pass
            if hasattr(self, '_browser') and self._browser:
                try: self._browser.close()
                except: pass
            if self._pw:
                try: self._pw.stop()
                except: pass

    def start_workflow(self, mock_mode: bool = False, account_email: str = None):
        if not account_email:
            import random, string
            domain = self.state_manager.get_setting("test_email_pattern", "@nariwal.shop").replace("*", "")
            rand_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            self.account_email = f"chloe{rand_str}{domain}"
        else:
            self.account_email = account_email

        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self):
        if self.status in (WorkerStatus.RUNNING, WorkerStatus.WAITING_FOR_GMAIL):
            self._paused = True
            self._update(WorkerStatus.PAUSED, "Worker paused")
            self._log("INFO", "Worker paused")

    def resume(self):
        if self._paused:
            self._paused = False
            self._update(WorkerStatus.RUNNING, "Worker resumed")
            self._log("INFO", "Worker resumed")

    def stop(self):
        self._stopped = True
        self._paused = False
        self._selector_event.set()
        self._update(WorkerStatus.STOPPED, "Worker stopped")
        self._log("INFO", "Worker stopped cleanly")

    def restart(self, mock_mode: bool = False):
        self.stop()
        if self._thread:
            self._thread.join(timeout=2)
        self.start_workflow(mock_mode=mock_mode)
