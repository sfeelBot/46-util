import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from PyQt5.QtCore import Qt, QObject, QProcess, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

OWNER = "sfeelBot"
REPO = "46-util"
BRANCH = "main"
TASK_NAMES = ["46util-GitHubSync-0800", "46util-GitHubSync-1200", "46util-GitHubSync-1800"]
TASK_TIMES = ["08:00", "12:00", "18:00"]

STABLE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "46util-sync"
CONFIG_PATH = STABLE_DIR / "config.json"
SYNC_SCRIPT = STABLE_DIR / "Sync-FromGitHub.ps1"
MANAGE_SCRIPT = STABLE_DIR / "Register-ScheduledTasks.ps1"


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "resources"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2] / "tools" / "github_sync"


def ensure_stable_scripts() -> None:
    STABLE_DIR.mkdir(parents=True, exist_ok=True)
    src_dir = resource_dir()
    for name in ("Sync-FromGitHub.ps1", "Register-ScheduledTasks.ps1"):
        src = src_dir / name
        if src.exists():
            shutil.copyfile(src, STABLE_DIR / name)


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


class PsRunner(QObject):
    """powershell.exe -File <script> ...를 QProcess로 비동기 실행한다.

    subprocess.run(...)을 GUI 스레드에서 직접 부르면 프로세스가 끝날 때까지 창이 멈춘다.
    QProcess는 이벤트 루프 안에서 논블로킹으로 동작하고 finished 시그널로 결과를 알려준다.
    """

    finished = pyqtSignal(int, str, str)  # exit_code, stdout, stderr

    def __init__(self, args: list, parent=None):
        super().__init__(parent)
        self._proc = QProcess(self)
        self._proc.setProgram("powershell.exe")
        self._proc.setArguments(["-NoProfile", "-ExecutionPolicy", "Bypass"] + args)
        self._proc.finished.connect(self._on_finished)

    def start(self) -> None:
        self._proc.start()

    def _on_finished(self, exit_code: int, _exit_status) -> None:
        stdout = bytes(self._proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        stderr = bytes(self._proc.readAllStandardError()).decode("utf-8", errors="replace")
        self.finished.emit(exit_code, stdout, stderr)


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
        self._status_runner: PsRunner | None = None
        self._toggle_runner: PsRunner | None = None
        self._commit_worker: CommitCheckWorker | None = None

        self._build_ui()
        self.refresh_status()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(60_000)

    # ---------------------------------------------------------------- UI 구성
    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        layout.addWidget(self._build_repo_group())
        layout.addWidget(self._build_path_group())
        layout.addWidget(self._build_schedule_group())
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

    def _build_schedule_group(self) -> QGroupBox:
        box = QGroupBox("자동 동기화 스케줄 (매일 08:00 / 12:00 / 18:00)")
        vbox = QVBoxLayout(box)

        self.toggle_btn = QPushButton("자동 동기화: 확인 중...")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.clicked.connect(self.on_toggle_schedule)
        vbox.addWidget(self.toggle_btn)

        self.schedule_table = QTableWidget(3, 3)
        self.schedule_table.setHorizontalHeaderLabels(["시각", "마지막 실행", "결과"])
        self.schedule_table.verticalHeader().setVisible(False)
        self.schedule_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.schedule_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for row, t in enumerate(TASK_TIMES):
            self.schedule_table.setItem(row, 0, QTableWidgetItem(t))
            self.schedule_table.setItem(row, 1, QTableWidgetItem("-"))
            self.schedule_table.setItem(row, 2, QTableWidgetItem("-"))
        vbox.addWidget(self.schedule_table)

        return box

    def _build_manual_group(self) -> QGroupBox:
        box = QGroupBox("수동 동기화")
        row = QHBoxLayout(box)
        self.sync_now_btn = QPushButton("지금 바로 동기화")
        self.sync_now_btn.clicked.connect(self.on_sync_now)
        row.addWidget(self.sync_now_btn)
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
        refresh_btn = QPushButton("로그 새로고침")
        refresh_btn.clicked.connect(self.refresh_log)
        vbox.addWidget(refresh_btn, alignment=Qt.AlignRight)
        return box

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

    def on_toggle_schedule(self, checked: bool) -> None:
        if self._toggle_runner is not None:
            return
        self.toggle_btn.setEnabled(False)
        action = "Register" if checked else "DisableAll"
        runner = PsRunner(["-File", str(MANAGE_SCRIPT), "-Action", action], self)
        runner.finished.connect(self._on_toggle_finished)
        runner.finished.connect(runner.deleteLater)
        self._toggle_runner = runner
        runner.start()

    def _on_toggle_finished(self, exit_code: int, _stdout: str, stderr: str) -> None:
        self._toggle_runner = None
        if exit_code != 0:
            QMessageBox.warning(self, "실패", f"스케줄 변경에 실패했습니다.\n\n{stderr}")
        self.toggle_btn.setEnabled(True)
        self.refresh_status()

    def on_sync_now(self) -> None:
        if self.sync_process is not None:
            return
        self.sync_now_btn.setEnabled(False)
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
        self.sync_now_label.setText("완료" if exit_code == 0 else f"실패 (code={exit_code})")
        self.refresh_status()
        self.refresh_log()

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
        self._refresh_schedule_state()

    def _refresh_schedule_state(self) -> None:
        if self._status_runner is not None:
            return  # 이전 조회가 아직 진행 중이면 이번 틱은 건너뜀 (중복 프로세스 방지)
        runner = PsRunner(["-File", str(MANAGE_SCRIPT), "-Action", "Status"], self)
        runner.finished.connect(self._on_schedule_status_result)
        runner.finished.connect(runner.deleteLater)
        self._status_runner = runner
        runner.start()

    def _on_schedule_status_result(self, _exit_code: int, stdout: str, _stderr: str) -> None:
        self._status_runner = None
        try:
            items = json.loads(stdout) if stdout.strip() else []
        except Exception:
            items = []

        by_name = {item["Name"]: item for item in items}
        all_on = bool(items) and all(item.get("Exists") and item.get("Enabled") for item in items)

        self.toggle_btn.blockSignals(True)
        self.toggle_btn.setChecked(all_on)
        self.toggle_btn.setText(f"자동 동기화: {'ON' if all_on else 'OFF'}")
        self.toggle_btn.blockSignals(False)

        for row, name in enumerate(TASK_NAMES):
            item = by_name.get(name, {})
            last_run = item.get("LastRunTime") or "-"
            result_code = item.get("LastResult")
            result_text = "-" if result_code is None else str(result_code)
            self.schedule_table.setItem(row, 1, QTableWidgetItem(str(last_run)))
            self.schedule_table.setItem(row, 2, QTableWidgetItem(result_text))

    def refresh_log(self) -> None:
        state_dir = Path(self.cfg.get("StateDir", ""))
        log_file = state_dir / "sync.log"
        if log_file.exists():
            text = log_file.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()[-200:]
            self.log_view.setPlainText("\n".join(lines))
        else:
            self.log_view.setPlainText("(아직 로그 없음)")

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
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
