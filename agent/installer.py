"""
ComputerOff Agent 설치 프로그램
- 서버 URL 설정 GUI
- Windows Task Scheduler 등록 (부팅/종료 트리거)
- Windows 7/8/10/11 호환
"""

import ctypes
import json
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
from pathlib import Path


def is_admin() -> bool:
    """관리자 권한 확인"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_as_admin():
    """관리자 권한으로 재실행"""
    if sys.platform != 'win32':
        return False

    try:
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
        else:
            exe_path = sys.executable
            script = sys.argv[0]
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe_path, f'"{script}"', None, 1
            )
            return True

        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe_path, "", None, 1
        )
        return True
    except:
        return False


def get_exe_path() -> str:
    """실행 파일 경로 반환"""
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def get_install_dir() -> Path:
    """설치 디렉토리 반환"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def save_config(server_url: str):
    """설정 파일 저장"""
    config_path = get_install_dir() / "config.json"
    config = {"server_url": server_url}
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)


def load_config() -> dict:
    """설정 파일 로드"""
    config_path = get_install_dir() / "config.json"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def create_task_scheduler_xml(event_type: str) -> str:
    """Task Scheduler XML 생성 (Windows 7 호환)"""
    exe_path = get_exe_path()

    if event_type == 'boot':
        trigger = """
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>"""
    elif event_type == 'heartbeat':
        # 30초마다 반복 실행 (실시간 온라인 상태 확인용)
        trigger = """
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Repetition>
        <Interval>PT30S</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </LogonTrigger>"""
    else:
        trigger = """
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>&lt;QueryList&gt;&lt;Query Id="0" Path="System"&gt;&lt;Select Path="System"&gt;*[System[Provider[@Name='User32'] and (EventID=1074)]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>
    </EventTrigger>"""

    xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>ComputerOff Agent - {event_type} event</Description>
  </RegistrationInfo>
  <Triggers>{trigger}
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT1M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"{exe_path}"</Command>
      <Arguments>--run {event_type}</Arguments>
    </Exec>
  </Actions>
</Task>'''
    return xml


def register_task(task_name: str, event_type: str) -> bool:
    """Task Scheduler에 작업 등록"""
    try:
        xml_content = create_task_scheduler_xml(event_type)
        xml_path = get_install_dir() / f"{task_name}.xml"

        with open(xml_path, 'w', encoding='utf-16') as f:
            f.write(xml_content)

        result = subprocess.run(
            ['schtasks', '/Create', '/TN', task_name, '/XML', str(xml_path), '/F'],
            capture_output=True,
            text=True
        )

        xml_path.unlink(missing_ok=True)

        return result.returncode == 0

    except Exception as e:
        print(f"작업 등록 실패: {e}")
        return False


def unregister_task(task_name: str) -> bool:
    """Task Scheduler에서 작업 제거"""
    try:
        result = subprocess.run(
            ['schtasks', '/Delete', '/TN', task_name, '/F'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except:
        return False


def install_agent(server_url: str) -> tuple:
    """Agent 설치"""
    results = []

    save_config(server_url)
    results.append(("설정 저장", True))

    boot_result = register_task("ComputerOff-Boot", "boot")
    results.append(("부팅 작업 등록", boot_result))

    shutdown_result = register_task("ComputerOff-Shutdown", "shutdown")
    results.append(("종료 작업 등록", shutdown_result))

    # 실시간 상태 확인용 하트비트 (30초마다)
    heartbeat_result = register_task("ComputerOff-Heartbeat", "heartbeat")
    results.append(("실시간 상태 확인 등록", heartbeat_result))

    return results


def uninstall_agent() -> tuple:
    """Agent 제거"""
    results = []

    boot_result = unregister_task("ComputerOff-Boot")
    results.append(("부팅 작업 제거", boot_result))

    shutdown_result = unregister_task("ComputerOff-Shutdown")
    results.append(("종료 작업 제거", shutdown_result))

    heartbeat_result = unregister_task("ComputerOff-Heartbeat")
    results.append(("실시간 상태 확인 제거", heartbeat_result))

    config_path = get_install_dir() / "config.json"
    if config_path.exists():
        config_path.unlink()
        results.append(("설정 파일 제거", True))

    return results


class InstallerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ComputerOff Agent 설치")
        self.root.geometry("450x320")
        self.root.resizable(False, False)

        self.setup_ui()
        self.center_window()

    def center_window(self):
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'+{x}+{y}')

    def setup_ui(self):
        title_frame = tk.Frame(self.root, bg="#2c3e50", height=60)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)

        title_label = tk.Label(
            title_frame,
            text="ComputerOff Agent",
            font=("맑은 고딕", 16, "bold"),
            bg="#2c3e50",
            fg="white"
        )
        title_label.pack(pady=15)

        main_frame = tk.Frame(self.root, padx=30, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        url_label = tk.Label(
            main_frame,
            text="서버 주소:",
            font=("맑은 고딕", 10)
        )
        url_label.pack(anchor=tk.W)

        self.url_entry = tk.Entry(main_frame, font=("맑은 고딕", 11), width=40)
        self.url_entry.pack(pady=(5, 15), fill=tk.X)

        config = load_config()
        if config.get('server_url'):
            self.url_entry.insert(0, config['server_url'])
        else:
            self.url_entry.insert(0, "http://192.168.1.100:8000")

        hint_label = tk.Label(
            main_frame,
            text="예: http://192.168.1.100:8000",
            font=("맑은 고딕", 9),
            fg="#888"
        )
        hint_label.pack(anchor=tk.W)

        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(pady=20)

        install_btn = tk.Button(
            btn_frame,
            text="설치",
            font=("맑은 고딕", 11),
            width=12,
            height=2,
            bg="#27ae60",
            fg="white",
            command=self.on_install
        )
        install_btn.pack(side=tk.LEFT, padx=10)

        # 제거 버튼은 관리자 권한일 때만 표시
        if is_admin():
            uninstall_btn = tk.Button(
                btn_frame,
                text="제거",
                font=("맑은 고딕", 11),
                width=12,
                height=2,
                bg="#e74c3c",
                fg="white",
                command=self.on_uninstall
            )
            uninstall_btn.pack(side=tk.LEFT, padx=10)

        self.status_label = tk.Label(
            main_frame,
            text="",
            font=("맑은 고딕", 9),
            fg="#666"
        )
        self.status_label.pack(pady=10)

        if not is_admin():
            self.status_label.config(
                text="⚠ 관리자 권한이 필요합니다. 관리자로 실행해주세요.",
                fg="#e74c3c"
            )

    def on_install(self):
        if not is_admin():
            messagebox.showwarning(
                "권한 필요",
                "관리자 권한이 필요합니다.\n프로그램을 관리자 권한으로 실행해주세요."
            )
            return

        server_url = self.url_entry.get().strip()
        if not server_url:
            messagebox.showerror("오류", "서버 주소를 입력하세요.")
            return

        if not server_url.startswith(('http://', 'https://')):
            messagebox.showerror("오류", "올바른 URL 형식이 아닙니다.\n예: http://192.168.1.100:8000")
            return

        results = install_agent(server_url)

        success_count = sum(1 for _, success in results if success)
        total_count = len(results)

        result_text = "\n".join(
            f"{'✓' if success else '✗'} {name}"
            for name, success in results
        )

        if success_count == total_count:
            messagebox.showinfo("설치 완료", f"Agent가 설치되었습니다.\n\n{result_text}")
            self.status_label.config(text="✓ 설치 완료", fg="#27ae60")
        else:
            messagebox.showwarning("설치 부분 완료", f"일부 작업이 실패했습니다.\n\n{result_text}")
            self.status_label.config(text="⚠ 설치 부분 완료", fg="#f39c12")

    def on_uninstall(self):
        if not is_admin():
            messagebox.showwarning(
                "권한 필요",
                "관리자 권한이 필요합니다.\n프로그램을 관리자 권한으로 실행해주세요."
            )
            return

        if not messagebox.askyesno("확인", "Agent를 제거하시겠습니까?"):
            return

        results = uninstall_agent()

        result_text = "\n".join(
            f"{'✓' if success else '✗'} {name}"
            for name, success in results
        )

        messagebox.showinfo("제거 완료", f"Agent가 제거되었습니다.\n\n{result_text}")
        self.status_label.config(text="✓ 제거 완료", fg="#27ae60")

    def run(self):
        self.root.mainloop()


def run_agent(event_type: str):
    """Agent 실행 (이벤트/하트비트 전송)"""
    from agent import send_event, send_heartbeat, load_config, log_error

    config = load_config()
    server_url = config.get('server_url')

    if not server_url:
        log_error("서버 URL이 설정되지 않았습니다")
        return

    if event_type == 'heartbeat':
        send_heartbeat(server_url)
    else:
        send_event(server_url, event_type)


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == '--run' and len(sys.argv) > 2:
            event_type = sys.argv[2]
            if event_type in ('boot', 'shutdown', 'heartbeat'):
                run_agent(event_type)
            return

    gui = InstallerGUI()
    gui.run()


if __name__ == "__main__":
    main()
