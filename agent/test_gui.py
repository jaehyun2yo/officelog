"""ComputerOff Agent 테스트 GUI

기존 agent 코드의 기능을 테스트하기 위한 GUI 도구
- 시작시간 보내기 (boot)
- 종료시간 보내기 (shutdown)
- 하트비트 보내기
- 이벤트 로그 복구 테스트
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from datetime import datetime, timedelta
import threading
import socket
import json
import os
import sys
import requests

# installer.py에서 필요한 함수들 import
from installer import (
    send_event,
    send_heartbeat,
    check_server_connection,
    get_shutdown_events_from_log,
    recover_missed_shutdown_events,
    load_state,
    save_state,
    load_config,
    log_error,
    get_install_dir,
    get_computer_name,
    uninstall_agent
)

# 로그 파일 경로
LOG_FILE = get_install_dir() / "agent.log"


class TestGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ComputerOff Agent 테스트 도구")
        self.root.geometry("700x600")
        self.root.resizable(True, True)

        # 서버 설정 기본값
        self.server_url = "http://34.64.116.152:8000"
        self.api_key = "Rk60sPWdkZSFNLLEH71n2iOO1BzEKPUqMVIgl2dIIms"
        self.log_text = None  # 위젯 생성 전 초기화

        # 설정 로드 (위젯 생성 전)
        self.load_config()

        self.create_widgets()

    def load_config(self):
        """config.json 또는 config_test.json 로드"""
        config_paths = [
            os.path.join(os.path.dirname(__file__), 'config_test.json'),
            os.path.join(os.path.dirname(__file__), 'config.json'),
        ]

        # PyInstaller 번들 경로
        if getattr(sys, 'frozen', False):
            bundle_dir = sys._MEIPASS
            config_paths.insert(0, os.path.join(bundle_dir, 'config_test.json'))
            config_paths.insert(1, os.path.join(bundle_dir, 'config.json'))

        for path in config_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        self.server_url = config.get('server_url', self.server_url)
                        self.api_key = config.get('api_key', self.api_key)
                        self.log(f"설정 로드: {path}")
                        return
                except Exception as e:
                    self.log(f"설정 로드 실패: {e}")

    def create_widgets(self):
        # 메인 프레임
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # === 서버 설정 섹션 ===
        server_frame = ttk.LabelFrame(main_frame, text="서버 설정", padding="10")
        server_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(server_frame, text="서버 URL:").grid(row=0, column=0, sticky=tk.W)
        self.url_var = tk.StringVar(value=self.server_url)
        self.url_entry = ttk.Entry(server_frame, textvariable=self.url_var, width=50)
        self.url_entry.grid(row=0, column=1, padx=5, sticky=tk.EW)

        ttk.Label(server_frame, text="API 키:").grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.api_var = tk.StringVar(value=self.api_key)
        self.api_entry = ttk.Entry(server_frame, textvariable=self.api_var, width=50)
        self.api_entry.grid(row=1, column=1, padx=5, pady=(5, 0), sticky=tk.EW)

        self.connect_btn = ttk.Button(server_frame, text="연결 테스트", command=self.test_connection)
        self.connect_btn.grid(row=0, column=2, rowspan=2, padx=5, pady=5)

        server_frame.columnconfigure(1, weight=1)

        # === 이벤트 전송 섹션 ===
        event_frame = ttk.LabelFrame(main_frame, text="이벤트 전송", padding="10")
        event_frame.pack(fill=tk.X, pady=(0, 10))

        # 타임스탬프 입력
        ttk.Label(event_frame, text="타임스탬프:").grid(row=0, column=0, sticky=tk.W)
        self.timestamp_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.timestamp_entry = ttk.Entry(event_frame, textvariable=self.timestamp_var, width=25)
        self.timestamp_entry.grid(row=0, column=1, padx=5, sticky=tk.W)

        ttk.Button(event_frame, text="현재 시간", command=self.set_current_time).grid(row=0, column=2, padx=5)

        # UTC 변환 옵션 (서버가 UTC 기준일 때만 사용)
        self.utc_convert_var = tk.BooleanVar(value=False)
        self.utc_check = ttk.Checkbutton(
            event_frame,
            text="KST→UTC 변환",
            variable=self.utc_convert_var
        )
        self.utc_check.grid(row=0, column=3, padx=10, sticky=tk.W)

        # 버튼들
        btn_frame = ttk.Frame(event_frame)
        btn_frame.grid(row=1, column=0, columnspan=4, pady=(10, 0))

        self.boot_btn = ttk.Button(btn_frame, text="시작(Boot) 전송", command=self.send_boot, width=18)
        self.boot_btn.pack(side=tk.LEFT, padx=5)

        self.shutdown_btn = ttk.Button(btn_frame, text="종료(Shutdown) 전송", command=self.send_shutdown, width=18)
        self.shutdown_btn.pack(side=tk.LEFT, padx=5)

        self.heartbeat_btn = ttk.Button(btn_frame, text="하트비트 전송", command=self.send_heartbeat_click, width=18)
        self.heartbeat_btn.pack(side=tk.LEFT, padx=5)

        # === 복구 테스트 섹션 ===
        recovery_frame = ttk.LabelFrame(main_frame, text="이벤트 로그 복구 테스트", padding="10")
        recovery_frame.pack(fill=tk.X, pady=(0, 10))

        btn_frame2 = ttk.Frame(recovery_frame)
        btn_frame2.pack(fill=tk.X)

        self.view_log_btn = ttk.Button(btn_frame2, text="Windows 이벤트 로그 조회", command=self.view_event_log, width=25)
        self.view_log_btn.pack(side=tk.LEFT, padx=5)

        self.recover_btn = ttk.Button(btn_frame2, text="미전송 이벤트 복구", command=self.recover_events, width=25)
        self.recover_btn.pack(side=tk.LEFT, padx=5)

        self.view_state_btn = ttk.Button(btn_frame2, text="상태 파일 보기", command=self.view_state, width=25)
        self.view_state_btn.pack(side=tk.LEFT, padx=5)

        # === 설치 관리 섹션 ===
        manage_frame = ttk.LabelFrame(main_frame, text="설치 관리", padding="10")
        manage_frame.pack(fill=tk.X, pady=(0, 10))

        btn_frame3 = ttk.Frame(manage_frame)
        btn_frame3.pack(fill=tk.X)

        self.show_install_btn = ttk.Button(btn_frame3, text="설치 정보 보기", command=self.show_install_info, width=20)
        self.show_install_btn.pack(side=tk.LEFT, padx=5)

        self.uninstall_btn = ttk.Button(btn_frame3, text="Agent 완전 삭제", command=self.uninstall_agent_click, width=20, style="Danger.TButton")
        self.uninstall_btn.pack(side=tk.LEFT, padx=5)

        # 위험 버튼 스타일
        style = ttk.Style()
        style.configure("Danger.TButton", foreground="red")

        # === 로그 출력 섹션 ===
        log_frame = ttk.LabelFrame(main_frame, text="로그", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 로그 버튼
        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Button(log_btn_frame, text="로그 지우기", command=self.clear_log).pack(side=tk.LEFT)
        ttk.Button(log_btn_frame, text="Agent 로그 파일 보기", command=self.view_agent_log).pack(side=tk.LEFT, padx=5)

        # 상태바
        self.status_var = tk.StringVar(value="준비됨")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(5, 0))

        # 초기 로그
        self.log(f"ComputerOff Agent 테스트 도구 시작")
        self.log(f"컴퓨터 이름: {socket.gethostname()}")
        self.log(f"서버 URL: {self.server_url}")

    def log(self, message):
        """로그 메시지 추가"""
        if self.log_text is None:
            return  # 위젯 생성 전이면 무시
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)

    def clear_log(self):
        """로그 지우기"""
        self.log_text.delete(1.0, tk.END)

    def set_current_time(self):
        """현재 시간으로 설정"""
        self.timestamp_var.set(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def get_server_url(self):
        """현재 서버 URL 반환"""
        return self.url_var.get().strip()

    def get_timestamp(self):
        """입력된 타임스탬프를 datetime으로 변환"""
        try:
            ts_str = self.timestamp_var.get().strip()
            return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            messagebox.showerror("오류", "타임스탬프 형식이 올바르지 않습니다.\n형식: YYYY-MM-DD HH:MM:SS")
            return None

    def test_connection(self):
        """서버 연결 테스트"""
        def task():
            self.status_var.set("연결 테스트 중...")
            url = self.get_server_url()
            self.log(f"서버 연결 테스트: {url}")

            if check_server_connection(url):
                self.log("연결 성공!")
                self.root.after(0, lambda: messagebox.showinfo("성공", "서버 연결 성공!"))
            else:
                self.log("연결 실패!")
                self.root.after(0, lambda: messagebox.showerror("실패", "서버 연결 실패"))

            self.status_var.set("준비됨")

        threading.Thread(target=task, daemon=True).start()

    def send_event_with_detail(self, event_type: str, timestamp: datetime):
        """이벤트 전송 (상세 에러 표시)"""
        url = self.get_server_url()
        api_url = f"{url.rstrip('/')}/api/events"

        config = load_config()
        api_key = config.get('api_key', '') or self.api_var.get()

        # KST → UTC 변환 (서버가 UTC 기준일 때)
        timestamp_for_server = timestamp
        if self.utc_convert_var.get():
            timestamp_for_server = timestamp - timedelta(hours=9)
            self.log(f"KST→UTC 변환: {timestamp.isoformat()} → {timestamp_for_server.isoformat()}")

        data = {
            "computer_name": get_computer_name(),
            "event_type": event_type,
            "timestamp": timestamp_for_server.isoformat()
        }
        headers = {"X-API-Key": api_key} if api_key else {}

        self.log(f"=== {event_type.upper()} 이벤트 전송 ===")
        self.log(f"URL: {api_url}")
        self.log(f"컴퓨터: {data['computer_name']}")
        self.log(f"타임스탬프 (원본 KST): {timestamp.isoformat()}")
        self.log(f"타임스탬프 (전송): {data['timestamp']}")
        self.log(f"API 키: {'설정됨' if api_key else '없음'}")

        try:
            response = requests.post(api_url, json=data, headers=headers, timeout=10)

            self.log(f"HTTP 상태: {response.status_code}")
            self.log(f"응답 헤더: {dict(response.headers)}")

            try:
                response_json = response.json()
                self.log(f"응답 본문: {json.dumps(response_json, ensure_ascii=False, indent=2)}")
            except ValueError:
                self.log(f"응답 본문 (텍스트): {response.text[:500]}")

            if response.status_code == 200:
                self.log(f"전송 성공!")
                return True, None
            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    err_json = response.json()
                    if 'detail' in err_json:
                        error_msg += f": {err_json['detail']}"
                    elif 'message' in err_json:
                        error_msg += f": {err_json['message']}"
                except:
                    error_msg += f": {response.text[:200]}"
                self.log(f"전송 실패: {error_msg}")
                return False, error_msg

        except requests.exceptions.ConnectionError as e:
            error_msg = f"연결 실패: 서버에 연결할 수 없습니다.\n{str(e)}"
            self.log(f"에러: {error_msg}")
            return False, error_msg
        except requests.exceptions.Timeout as e:
            error_msg = f"타임아웃: 서버 응답 시간 초과"
            self.log(f"에러: {error_msg}")
            return False, error_msg
        except requests.exceptions.RequestException as e:
            error_msg = f"요청 에러: {type(e).__name__}: {str(e)}"
            self.log(f"에러: {error_msg}")
            return False, error_msg
        except Exception as e:
            error_msg = f"예외 발생: {type(e).__name__}: {str(e)}"
            self.log(f"에러: {error_msg}")
            return False, error_msg

    def send_boot(self):
        """Boot 이벤트 전송"""
        timestamp = self.get_timestamp()
        if not timestamp:
            return

        def task():
            self.status_var.set("Boot 이벤트 전송 중...")

            success, error_msg = self.send_event_with_detail('boot', timestamp)

            if success:
                self.root.after(0, lambda: messagebox.showinfo("성공", "Boot 이벤트 전송 성공!"))
            else:
                self.root.after(0, lambda: messagebox.showerror("실패", f"Boot 이벤트 전송 실패\n\n{error_msg}"))

            self.status_var.set("준비됨")

        threading.Thread(target=task, daemon=True).start()

    def send_shutdown(self):
        """Shutdown 이벤트 전송"""
        timestamp = self.get_timestamp()
        if not timestamp:
            return

        def task():
            self.status_var.set("Shutdown 이벤트 전송 중...")

            success, error_msg = self.send_event_with_detail('shutdown', timestamp)

            if success:
                self.root.after(0, lambda: messagebox.showinfo("성공", "Shutdown 이벤트 전송 성공!"))
            else:
                self.root.after(0, lambda: messagebox.showerror("실패", f"Shutdown 이벤트 전송 실패\n\n{error_msg}"))

            self.status_var.set("준비됨")

        threading.Thread(target=task, daemon=True).start()

    def send_heartbeat_with_detail(self):
        """하트비트 전송 (상세 에러 표시)"""
        url = self.get_server_url()
        api_url = f"{url.rstrip('/')}/api/heartbeat"

        config = load_config()
        api_key = config.get('api_key', '') or self.api_var.get()

        # 서버 API는 computer_name을 query parameter로 받음
        computer_name = get_computer_name()
        params = {"computer_name": computer_name}
        headers = {"X-API-Key": api_key} if api_key else {}

        self.log(f"=== 하트비트 전송 ===")
        self.log(f"URL: {api_url}")
        self.log(f"컴퓨터: {computer_name}")

        try:
            response = requests.post(api_url, params=params, headers=headers, timeout=10)

            self.log(f"HTTP 상태: {response.status_code}")

            try:
                response_json = response.json()
                self.log(f"응답: {json.dumps(response_json, ensure_ascii=False)}")
            except ValueError:
                self.log(f"응답 (텍스트): {response.text[:200]}")

            if response.status_code == 200:
                self.log(f"전송 성공!")
                return True, None
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                self.log(f"전송 실패: {error_msg}")
                return False, error_msg

        except requests.exceptions.ConnectionError as e:
            error_msg = f"연결 실패: 서버에 연결할 수 없습니다."
            self.log(f"에러: {error_msg}")
            return False, error_msg
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.log(f"에러: {error_msg}")
            return False, error_msg

    def send_heartbeat_click(self):
        """하트비트 전송"""
        def task():
            self.status_var.set("하트비트 전송 중...")

            success, error_msg = self.send_heartbeat_with_detail()

            if success:
                self.root.after(0, lambda: messagebox.showinfo("성공", "하트비트 전송 성공!"))
            else:
                self.root.after(0, lambda: messagebox.showerror("실패", f"하트비트 전송 실패\n\n{error_msg}"))

            self.status_var.set("준비됨")

        threading.Thread(target=task, daemon=True).start()

    def view_event_log(self):
        """Windows 이벤트 로그 조회"""
        def task():
            self.status_var.set("이벤트 로그 조회 중...")
            self.log("Windows 이벤트 로그에서 종료 이벤트 조회...")

            try:
                events = get_shutdown_events_from_log(max_events=10)

                if events:
                    self.log(f"조회된 이벤트: {len(events)}개")
                    for i, event in enumerate(events):
                        self.log(f"  [{i+1}] {event['shutdown_type']} - {event['timestamp']} (record_id={event['record_id']})")
                else:
                    self.log("조회된 종료 이벤트 없음")
            except Exception as e:
                self.log(f"이벤트 로그 조회 실패: {e}")

            self.status_var.set("준비됨")

        threading.Thread(target=task, daemon=True).start()

    def recover_events(self):
        """미전송 이벤트 복구"""
        def task():
            self.status_var.set("이벤트 복구 중...")
            url = self.get_server_url()
            self.log(f"미전송 종료 이벤트 복구 시작...")

            try:
                count = recover_missed_shutdown_events(url)
                self.log(f"복구 완료: {count}개 이벤트 전송됨")
                self.root.after(0, lambda: messagebox.showinfo("완료", f"복구 완료: {count}개 이벤트 전송됨"))
            except Exception as e:
                self.log(f"복구 실패: {e}")
                self.root.after(0, lambda: messagebox.showerror("실패", f"복구 실패: {e}"))

            self.status_var.set("준비됨")

        threading.Thread(target=task, daemon=True).start()

    def view_state(self):
        """상태 파일 보기"""
        try:
            state = load_state()
            self.log("=== 상태 파일 내용 ===")
            for key, value in state.items():
                self.log(f"  {key}: {value}")
            self.log("======================")
        except Exception as e:
            self.log(f"상태 파일 로드 실패: {e}")

    def view_agent_log(self):
        """Agent 로그 파일 보기"""
        try:
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, 'r', encoding='utf-8') as f:
                    lines = f.readlines()[-50:]  # 마지막 50줄
                self.log(f"=== Agent 로그 (마지막 50줄) ===")
                for line in lines:
                    self.log(line.rstrip())
                self.log("================================")
            else:
                self.log(f"로그 파일 없음: {LOG_FILE}")
        except Exception as e:
            self.log(f"로그 파일 읽기 실패: {e}")

    def show_install_info(self):
        """설치 정보 표시"""
        import subprocess

        self.log("=== 설치 정보 ===")

        install_dir = get_install_dir()
        self.log(f"설치 디렉토리: {install_dir}")

        # 설치된 파일 목록
        if install_dir.exists():
            self.log(f"설치된 파일:")
            for f in install_dir.iterdir():
                size = f.stat().st_size if f.is_file() else 0
                self.log(f"  - {f.name} ({size:,} bytes)")
        else:
            self.log(f"설치 디렉토리 없음")

        # Task Scheduler 작업 확인
        self.log(f"\nTask Scheduler 작업:")
        tasks = ["ComputerOff-Boot", "ComputerOff-Monitor", "ComputerOff-Shutdown", "ComputerOff-Heartbeat"]
        for task_name in tasks:
            try:
                result = subprocess.run(
                    ['schtasks', '/Query', '/TN', task_name],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    self.log(f"  - {task_name}: 등록됨")
                else:
                    self.log(f"  - {task_name}: 없음")
            except Exception as e:
                self.log(f"  - {task_name}: 확인 실패 ({e})")

        self.log("=================")

    def is_admin(self):
        """관리자 권한 확인"""
        import ctypes
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def run_as_admin(self):
        """관리자 권한으로 재실행"""
        import ctypes
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join(sys.argv), None, 1
            )
            self.root.quit()
        except Exception as e:
            self.log(f"관리자 권한 실행 실패: {e}")

    def uninstall_agent_click(self):
        """Agent 완전 삭제"""
        # 관리자 권한 확인
        if not self.is_admin():
            result = messagebox.askyesno(
                "관리자 권한 필요",
                "Task Scheduler 작업 삭제에는 관리자 권한이 필요합니다.\n\n"
                "관리자 권한으로 다시 실행하시겠습니까?",
                icon='warning'
            )
            if result:
                self.run_as_admin()
            return

        # 확인 대화상자
        confirm = messagebox.askyesno(
            "경고",
            "ComputerOff Agent를 완전히 삭제하시겠습니까?\n\n"
            "다음 항목이 삭제됩니다:\n"
            "- Task Scheduler 작업 (부팅, 종료, 하트비트)\n"
            "- 설정 파일 (config.json)\n"
            "- 상태 파일 (state.json)\n"
            "- 로그 파일\n\n"
            "이 작업은 되돌릴 수 없습니다.",
            icon='warning'
        )

        if not confirm:
            self.log("삭제 취소됨")
            return

        def task():
            self.status_var.set("Agent 삭제 중...")
            self.log("=== Agent 삭제 시작 ===")

            try:
                results = uninstall_agent()

                self.log("삭제 결과:")
                all_success = True
                for name, success in results:
                    status = "성공" if success else "실패"
                    self.log(f"  - {name}: {status}")
                    if not success:
                        all_success = False

                if all_success:
                    self.log("Agent 삭제 완료!")
                    self.root.after(0, lambda: messagebox.showinfo("완료", "Agent가 완전히 삭제되었습니다."))
                else:
                    self.log("일부 항목 삭제 실패 (위 로그 참조)")
                    self.root.after(0, lambda: messagebox.showwarning("부분 완료", "일부 항목 삭제에 실패했습니다.\n로그를 확인하세요."))

            except Exception as e:
                self.log(f"삭제 실패: {e}")
                self.root.after(0, lambda: messagebox.showerror("실패", f"삭제 실패: {e}"))

            self.log("====================")
            self.status_var.set("준비됨")

        threading.Thread(target=task, daemon=True).start()


def main():
    root = tk.Tk()
    app = TestGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
