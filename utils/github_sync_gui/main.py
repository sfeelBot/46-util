import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
import winreg
from pathlib import Path

from PyQt5.QtCore import Qt, QProcess, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

OWNER = "sfeelBot"
REPO = "46-util"
BRANCH = "main"

STABLE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "46util-sync"
CONFIG_PATH = STABLE_DIR / "config.json"
SYNC_SCRIPT = STABLE_DIR / "Sync-FromGitHub.ps1"


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "resources"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2] / "tools" / "github_sync"


def asset_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "resources"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "assets"


ICON_ON = asset_dir() / "icon_on.ico"


def ensure_stable_scripts() -> None:
    STABLE_DIR.mkdir(parents=True, exist_ok=True)
    src_dir = resource_dir()
    src = src_dir / "Sync-FromGitHub.ps1"
    if src.exists():
        shutil.copyfile(src, STABLE_DIR / "Sync-FromGitHub.ps1")


def default_config() -> dict:
    return {
        "Owner": OWNER,
        "Repo": REPO,
        "Branch": BRANCH,
        "DestDir": r"C:\Work\46 util",
        "StateDir": str(STABLE_DIR / "state"),
        "PythonExe": "py",
        "Token": "",
    }


def parse_github_url(url: str):
    """'https://github.com/owner/repo(.git)' 또는 'git@github.com:owner/repo.git' 형태에서
    (owner, repo)를 추출한다. 매치되지 않으면 None."""
    url = url.strip()
    match = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url)
    if not match:
        return None
    return match.group(1), match.group(2)


def load_config() -> dict:
    cfg = default_config()
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    else:
        save_config(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- Windows 시작 프로그램 등록
STARTUP_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_VALUE_NAME = "46util-sync-gui"


def _startup_command() -> str:
    """레지스트리 Run 키에 넣을 실행 커맨드. exe로 빌드된 경우 exe 경로,
    개발 모드(스크립트 실행)에서는 venv python으로 이 스크립트를 실행하도록 등록한다."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{Path(__file__).resolve()}"'


def is_startup_registered() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, STARTUP_VALUE_NAME)
        return True
    except FileNotFoundError:
        return False


def set_startup_registered(enabled: bool) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, STARTUP_RUN_KEY, 0, winreg.KEY_WRITE) as key:
        if enabled:
            winreg.SetValueEx(key, STARTUP_VALUE_NAME, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(key, STARTUP_VALUE_NAME)
            except FileNotFoundError:
                pass


class CommitCheckWorker(QThread):
    """GitHub 최신 커밋 조회(urllib, 네트워크 I/O)를 GUI 스레드 밖에서 실행한다."""

    result = pyqtSignal(str)

    def __init__(self, owner: str, repo: str, branch: str, token: str, parent=None):
        super().__init__(parent)
        self._owner = owner
        self._repo = repo
        self._branch = branch
        self._token = token

    def run(self) -> None:
        url = f"https://api.github.com/repos/{self._owner}/{self._repo}/commits/{self._branch}"
        headers = {"User-Agent": "46util-sync-gui"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self.result.emit(f"GitHub 최신 커밋: {data['sha']}")
        except (urllib.error.URLError, TimeoutError, KeyError) as exc:
            self.result.emit(f"GitHub 최신 커밋: 조회 실패 ({exc})")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("46 util - GitHub 동기화 관리")
        self.resize(720, 640)

        ensure_stable_scripts()
        self.cfg = load_config()

        self.sync_process: QProcess | None = None
        self._sync_cancelled = False
        self._commit_worker: CommitCheckWorker | None = None

        self._build_ui()
        self._build_tray_icon()
        self.refresh_status()
        self._refresh_startup_state()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(60_000)

    # ---------------------------------------------------------------- 트레이 아이콘
    def _build_tray_icon(self) -> None:
        self.setWindowIcon(QIcon(str(ICON_ON)))

        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = None
            return

        self.tray_icon = QSystemTrayIcon(QIcon(str(ICON_ON)), self)
        self.tray_icon.setToolTip("46 util - GitHub 동기화")
        self.tray_icon.activated.connect(self._on_tray_activated)

        menu = QMenu()
        action_sync = QAction("지금 동기화", self)
        action_sync.triggered.connect(self.on_sync_now)
        menu.addAction(action_sync)

        menu.addSeparator()
        action_open = QAction("창 열기", self)
        action_open.triggered.connect(self._show_and_raise)
        menu.addAction(action_open)

        action_quit = QAction("종료", self)
        action_quit.triggered.connect(self._quit_app)
        menu.addAction(action_quit)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._show_and_raise()

    def _show_and_raise(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self) -> None:
        if self.tray_icon is not None:
            self.tray_icon.hide()
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:
        if self.tray_icon is None:
            super().closeEvent(event)
            return
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "46 util - GitHub 동기화",
            "트레이에서 계속 실행됩니다. 완전히 종료하려면 트레이 아이콘에서 '종료'를 선택하세요.",
            QSystemTrayIcon.Information,
            3000,
        )

    # ---------------------------------------------------------------- UI 구성
    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        layout.addWidget(self._build_repo_group())
        layout.addWidget(self._build_path_group())
        layout.addWidget(self._build_startup_group())
        layout.addWidget(self._build_manual_group())
        layout.addWidget(self._build_status_group())
        layout.addWidget(self._build_log_group())

        self.setCentralWidget(central)

    def _build_repo_group(self) -> QGroupBox:
        box = QGroupBox("저장소 설정")
        grid = QVBoxLayout(box)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("GitHub URL"))
        current_url = f"https://github.com/{self.cfg['Owner']}/{self.cfg['Repo']}"
        self.repo_url_edit = QLineEdit(current_url)
        self.repo_url_edit.setPlaceholderText("https://github.com/owner/repo")
        url_row.addWidget(self.repo_url_edit)
        grid.addLayout(url_row)

        branch_row = QHBoxLayout()
        branch_row.addWidget(QLabel("브랜치"))
        self.branch_edit = QLineEdit(self.cfg["Branch"])
        branch_row.addWidget(self.branch_edit)
        grid.addLayout(branch_row)

        token_row = QHBoxLayout()
        token_row.addWidget(QLabel("Personal Access Token (Private 저장소만 필요)"))
        self.token_edit = QLineEdit(self.cfg.get("Token", ""))
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.setPlaceholderText("Public 저장소면 비워두세요")
        token_row.addWidget(self.token_edit)
        grid.addLayout(token_row)

        save_btn = QPushButton("저장")
        save_btn.clicked.connect(self.on_save_repo)
        grid.addWidget(save_btn, alignment=Qt.AlignRight)

        return box

    def _build_path_group(self) -> QGroupBox:
        box = QGroupBox("경로 설정")
        grid = QVBoxLayout(box)

        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("프로젝트 경로 (DestDir)"))
        self.dest_edit = QLineEdit(self.cfg["DestDir"])
        dest_row.addWidget(self.dest_edit)
        dest_browse = QPushButton("찾아보기")
        dest_browse.clicked.connect(lambda: self._browse_into(self.dest_edit))
        dest_row.addWidget(dest_browse)
        grid.addLayout(dest_row)

        state_row = QHBoxLayout()
        state_row.addWidget(QLabel("상태/로그 경로 (StateDir)"))
        self.state_edit = QLineEdit(self.cfg["StateDir"])
        state_row.addWidget(self.state_edit)
        state_browse = QPushButton("찾아보기")
        state_browse.clicked.connect(lambda: self._browse_into(self.state_edit))
        state_row.addWidget(state_browse)
        grid.addLayout(state_row)

        save_btn = QPushButton("저장")
        save_btn.clicked.connect(self.on_save_paths)
        grid.addWidget(save_btn, alignment=Qt.AlignRight)

        return box

    def _build_startup_group(self) -> QGroupBox:
        box = QGroupBox("Windows 시작 시 자동 실행")
        vbox = QVBoxLayout(box)
        self.startup_toggle_btn = QPushButton("확인 중...")
        self.startup_toggle_btn.setCheckable(True)
        self.startup_toggle_btn.clicked.connect(self.on_toggle_startup)
        vbox.addWidget(self.startup_toggle_btn)
        hint = QLabel("켜면 컴퓨터를 켜고 로그인할 때 이 프로그램이 자동으로 실행되어 트레이에 상주합니다.")
        hint.setWordWrap(True)
        vbox.addWidget(hint)
        return box

    def _build_manual_group(self) -> QGroupBox:
        box = QGroupBox("수동 동기화")
        row = QHBoxLayout(box)
        self.sync_now_btn = QPushButton("지금 바로 동기화")
        self.sync_now_btn.clicked.connect(self.on_sync_now)
        row.addWidget(self.sync_now_btn)
        self.cancel_sync_btn = QPushButton("강제 동기화 취소")
        self.cancel_sync_btn.setEnabled(False)
        self.cancel_sync_btn.clicked.connect(self.on_cancel_sync)
        row.addWidget(self.cancel_sync_btn)
        self.sync_now_label = QLabel("")
        row.addWidget(self.sync_now_label)
        row.addStretch()
        return box

    def _build_status_group(self) -> QGroupBox:
        box = QGroupBox("상태")
        vbox = QVBoxLayout(box)

        self.local_sha_label = QLabel("로컬에 반영된 커밋: -")
        self.last_sync_label = QLabel("마지막 동기화 시각: -")
        vbox.addWidget(self.local_sha_label)
        vbox.addWidget(self.last_sync_label)

        row = QHBoxLayout()
        self.latest_sha_label = QLabel("GitHub 최신 커밋: 확인 안 함")
        row.addWidget(self.latest_sha_label)
        refresh_btn = QPushButton("새로고침")
        refresh_btn.clicked.connect(self.check_latest_commit)
        row.addWidget(refresh_btn)
        row.addStretch()
        vbox.addLayout(row)

        return box

    def _build_log_group(self) -> QGroupBox:
        box = QGroupBox("로그")
        vbox = QVBoxLayout(box)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        vbox.addWidget(self.log_view)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        refresh_btn = QPushButton("로그 새로고침")
        refresh_btn.clicked.connect(self.refresh_log)
        btn_row.addWidget(refresh_btn)
        clear_btn = QPushButton("로그 삭제")
        clear_btn.clicked.connect(self.on_clear_log)
        btn_row.addWidget(clear_btn)
        vbox.addLayout(btn_row)
        return box

    def _refresh_startup_state(self) -> None:
        registered = is_startup_registered()
        self.startup_toggle_btn.blockSignals(True)
        self.startup_toggle_btn.setChecked(registered)
        self.startup_toggle_btn.setText(f"Windows 시작 시 자동 실행: {'ON' if registered else 'OFF'}")
        self.startup_toggle_btn.blockSignals(False)

    def on_toggle_startup(self, checked: bool) -> None:
        try:
            set_startup_registered(checked)
        except OSError as exc:
            QMessageBox.warning(self, "오류", f"시작 프로그램 등록에 실패했습니다.\n{exc}")
        self._refresh_startup_state()

    def _browse_into(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "폴더 선택", edit.text())
        if path:
            edit.setText(str(Path(path)))

    # --------------------------------------------------------------- 동작들
    def on_save_repo(self) -> None:
        parsed = parse_github_url(self.repo_url_edit.text())
        if not parsed:
            QMessageBox.warning(
                self, "URL 오류", "GitHub URL 형식을 인식할 수 없습니다.\n예: https://github.com/owner/repo"
            )
            return
        owner, repo = parsed
        self.cfg["Owner"] = owner
        self.cfg["Repo"] = repo
        self.cfg["Branch"] = self.branch_edit.text().strip() or "main"
        self.cfg["Token"] = self.token_edit.text().strip()
        save_config(self.cfg)
        self.repo_url_edit.setText(f"https://github.com/{owner}/{repo}")
        QMessageBox.information(self, "저장됨", f"저장소 설정을 저장했습니다.\n{owner}/{repo} @ {self.cfg['Branch']}")
        self.check_latest_commit()

    def on_save_paths(self) -> None:
        self.cfg["DestDir"] = self.dest_edit.text().strip()
        self.cfg["StateDir"] = self.state_edit.text().strip()
        save_config(self.cfg)
        QMessageBox.information(self, "저장됨", "경로 설정을 저장했습니다.")
        self.refresh_status()

    def on_sync_now(self) -> None:
        if self.sync_process is not None:
            return
        self._sync_cancelled = False
        self.sync_now_btn.setEnabled(False)
        self.cancel_sync_btn.setEnabled(True)
        self.sync_now_label.setText("실행 중...")
        self.log_view.clear()

        proc = QProcess(self)
        proc.setProgram("powershell.exe")
        proc.setArguments(
            ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SYNC_SCRIPT), "-Force"]
        )
        proc.readyReadStandardOutput.connect(lambda: self._append_process_output(proc))
        proc.readyReadStandardError.connect(lambda: self._append_process_output(proc))
        proc.finished.connect(self.on_sync_finished)
        self.sync_process = proc
        proc.start()

    def _append_process_output(self, proc: QProcess) -> None:
        data = bytes(proc.readAllStandardOutput()) + bytes(proc.readAllStandardError())
        if data:
            text = data.decode("utf-8", errors="replace")
            self.log_view.appendPlainText(text.rstrip("\n"))

    def on_sync_finished(self, exit_code: int, _exit_status) -> None:
        self.sync_process = None
        self.sync_now_btn.setEnabled(True)
        self.cancel_sync_btn.setEnabled(False)
        if self._sync_cancelled:
            self.sync_now_label.setText("취소됨")
        else:
            self.sync_now_label.setText("완료" if exit_code == 0 else f"실패 (code={exit_code})")
        self.refresh_status()
        self.refresh_log()

    def on_cancel_sync(self) -> None:
        """QProcess.kill()은 powershell.exe만 종료하고 그 자식인 robocopy.exe는
        고아 프로세스로 남아 재시도를 계속할 수 있으므로, taskkill /T로 프로세스 트리 전체를 종료한다."""
        if self.sync_process is None:
            return
        pid = self.sync_process.processId()
        self._sync_cancelled = True
        self.cancel_sync_btn.setEnabled(False)
        self.sync_now_label.setText("취소 중...")
        if pid:
            QProcess.startDetached("taskkill", ["/PID", str(pid), "/T", "/F"])

    def refresh_status(self) -> None:
        state_dir = Path(self.cfg.get("StateDir", ""))
        sha_file = state_dir / "last_sha.txt"
        if sha_file.exists():
            sha = sha_file.read_text(encoding="utf-8").strip()
            self.local_sha_label.setText(f"로컬에 반영된 커밋: {sha}")
            import datetime

            mtime = datetime.datetime.fromtimestamp(sha_file.stat().st_mtime)
            self.last_sync_label.setText(f"마지막 동기화 시각: {mtime:%Y-%m-%d %H:%M:%S}")
        else:
            self.local_sha_label.setText("로컬에 반영된 커밋: (아직 동기화한 적 없음)")
            self.last_sync_label.setText("마지막 동기화 시각: -")

        self.refresh_log()

    def refresh_log(self) -> None:
        state_dir = Path(self.cfg.get("StateDir", ""))
        log_file = state_dir / "sync.log"
        if log_file.exists():
            text = log_file.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()[-200:]
            self.log_view.setPlainText("\n".join(lines))
        else:
            self.log_view.setPlainText("(아직 로그 없음)")

    def on_clear_log(self) -> None:
        state_dir = Path(self.cfg.get("StateDir", ""))
        log_file = state_dir / "sync.log"
        if not log_file.exists():
            QMessageBox.information(self, "알림", "삭제할 로그가 없습니다.")
            return
        reply = QMessageBox.question(
            self, "로그 삭제", "기존 로그를 삭제할까요? (동기화 자체에는 영향 없으며, 다음 동기화부터 새로 기록됩니다)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            log_file.unlink()
        except OSError as exc:
            QMessageBox.warning(self, "오류", f"로그 삭제 실패: {exc}")
            return
        self.refresh_log()

    def check_latest_commit(self) -> None:
        if self._commit_worker is not None:
            return
        self.latest_sha_label.setText("GitHub 최신 커밋: 확인 중...")
        worker = CommitCheckWorker(
            self.cfg["Owner"], self.cfg["Repo"], self.cfg["Branch"], self.cfg.get("Token", ""), self
        )
        worker.result.connect(self.latest_sha_label.setText)
        worker.finished.connect(self._on_commit_worker_finished)
        worker.finished.connect(worker.deleteLater)
        self._commit_worker = worker
        worker.start()

    def _on_commit_worker_finished(self) -> None:
        self._commit_worker = None


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 창을 닫아도 트레이에서 계속 실행됨
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
