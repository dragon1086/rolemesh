"""
installer.py — RoleMesh Installer Wizard
비개발자도 15분 내에 로컬 AI 팀 구성 완료.

실행: python3 -m rolemesh init
"""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_DB_PATH = os.path.expanduser("~/rolemesh/rolemesh.db")

# questionary 없으면 input() 폴백
try:
    import questionary
    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False


def _ask_confirm(message: str, default: bool = True) -> bool:
    """Y/n 확인 프롬프트. questionary 없으면 input() 폴백."""
    if HAS_QUESTIONARY:
        return questionary.confirm(message, default=default).ask()
    hint = "[Y/n]" if default else "[y/N]"
    raw = input(f"{message} {hint}: ").strip().lower()
    if raw == "":
        return default
    return raw in ("y", "yes")


def _ask_text(message: str, default: str = "") -> str:
    """텍스트 입력 프롬프트."""
    if HAS_QUESTIONARY:
        return questionary.text(message, default=default).ask() or default
    hint = f" [{default}]" if default else ""
    raw = input(f"{message}{hint}: ").strip()
    return raw if raw else default


def _print_box(lines: list, width: int = 56) -> None:
    """간단한 박스 출력."""
    print("┌" + "─" * (width - 2) + "┐")
    for line in lines:
        padded = line.ljust(width - 4)
        print(f"│  {padded}  │")
    print("└" + "─" * (width - 2) + "┘")


@dataclass
class Environment:
    has_claude: bool = False
    claude_path: Optional[str] = None
    has_openclaw: bool = False
    openclaw_path: Optional[str] = None
    has_amp: bool = False
    amp_path: Optional[str] = None
    python_version: Optional[str] = None
    anthropic_model: Optional[str] = None
    has_oauth_token: bool = False


@dataclass
class RoleConfig:
    role: str          # "PM" | "Builder" | "Analyst"
    agent_id: str
    display_name: str
    description: str
    capabilities: list[dict] = field(default_factory=list)
    tool: Optional[str] = None   # 감지된 툴 이름


class RoleMeshInstaller:
    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path

    # ── 환경 탐지 ──────────────────────────────────────────────

    def detect_environment(self) -> Environment:
        """시스템에서 사용 가능한 도구와 환경변수를 탐지."""
        env = Environment()
        env.claude_path = shutil.which("claude")
        env.has_claude = env.claude_path is not None
        env.openclaw_path = shutil.which("openclaw")
        env.has_openclaw = env.openclaw_path is not None
        env.amp_path = shutil.which("amp")
        env.has_amp = env.amp_path is not None
        env.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        env.anthropic_model = os.environ.get("ANTHROPIC_MODEL")
        env.has_oauth_token = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
        return env

    # ── 연결 테스트 ────────────────────────────────────────────

    def health_check(self, env: Environment) -> dict:
        """각 도구의 실행 가능 여부를 테스트."""
        results = {}

        def _check(name, path):
            if not path:
                results[name] = (False, "바이너리 미감지")
                return
            try:
                out = subprocess.run(
                    [path, "--version"],
                    capture_output=True, text=True, timeout=5
                )
                if out.returncode == 0:
                    ver = (out.stdout or out.stderr).strip().split("\n")[0]
                    results[name] = (True, ver)
                else:
                    results[name] = (False, f"exit {out.returncode}")
            except Exception as e:
                results[name] = (False, str(e))

        if env.claude_path:
            _check("claude", env.claude_path)
        if env.openclaw_path:
            _check("openclaw", env.openclaw_path)
        if env.amp_path:
            _check("amp", env.amp_path)

        return results

    # ── 역할 추천 ──────────────────────────────────────────────

    def recommend_roles(self, env: Environment) -> list[RoleConfig]:
        """감지된 환경 기반으로 역할 구성을 추천."""
        roles: list[RoleConfig] = []

        if env.has_openclaw:
            roles.append(RoleConfig(
                role="PM",
                agent_id="openclaw-pm",
                display_name="PM (OpenClaw)",
                description="프로젝트 관리, 태스크 라우팅, 팀 조율",
                tool="openclaw",
                capabilities=[{
                    "name": "project_management",
                    "description": "태스크 계획, 우선순위 지정, 팀 조율",
                    "keywords": ["계획", "관리", "조율", "우선순위", "pm", "plan", "manage"],
                    "cost_level": "medium",
                }],
            ))

        if env.has_claude:
            roles.append(RoleConfig(
                role="Builder",
                agent_id="claude-builder",
                display_name="Builder (Claude Code)",
                description="코드 작성, 버그 수정, 구현",
                tool="claude",
                capabilities=[{
                    "name": "code_write",
                    "description": "코드 구현, 리팩토링, 버그 수정",
                    "keywords": ["코드", "구현", "개발", "버그", "code", "build", "fix", "implement"],
                    "cost_level": "high",
                }],
            ))

        if env.has_amp:
            roles.append(RoleConfig(
                role="Analyst",
                agent_id="amp-analyst",
                display_name="Analyst (amp)",
                description="데이터 분석, 전략 검토, 인사이트 도출",
                tool="amp",
                capabilities=[{
                    "name": "emergent_analysis",
                    "description": "데이터 분석, 전략 검토, 인사이트 도출",
                    "keywords": ["분석", "검토", "전략", "인사이트", "analyze", "review", "strategy"],
                    "cost_level": "medium",
                }],
            ))

        if not roles:
            roles.append(RoleConfig(
                role="PM",
                agent_id="local-pm",
                display_name="PM (로컬)",
                description="로컬 프로젝트 관리자 (라이트 모드)",
                tool=None,
                capabilities=[{
                    "name": "project_management",
                    "description": "태스크 계획 및 관리",
                    "keywords": ["계획", "관리", "plan"],
                    "cost_level": "low",
                }],
            ))

        return roles

    # ── DB 초기화 ──────────────────────────────────────────────

    def init_database(self) -> None:
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)
        from ..core.init_db import init_db
        conn = init_db(self.db_path)
        conn.close()

    # ── 에이전트 등록 ──────────────────────────────────────────

    def register_roles(self, roles: list[RoleConfig]) -> None:
        from ..core.registry_client import RegistryClient
        client = RegistryClient(db_path=self.db_path)
        try:
            for role in roles:
                client.register_agent(
                    agent_id=role.agent_id,
                    display_name=role.display_name,
                    description=role.description,
                )
                for cap in role.capabilities:
                    client.register_capability(
                        agent_id=role.agent_id,
                        name=cap["name"],
                        description=cap.get("description", ""),
                        keywords=cap.get("keywords", []),
                        cost_level=cap.get("cost_level", "medium"),
                    )
        finally:
            client.close()

    # ── 인터랙티브 실행 ────────────────────────────────────────

    def run(self, interactive: bool = True) -> None:
        """인터랙티브 마법사 모드. --non-interactive 시 자동 실행."""
        print()
        _print_box([
            "RoleMesh Installer Wizard v0.2",
            "로컬 AI 팀을 15분 내에 구성합니다.",
            "",
            "Ctrl+C 로 언제든 중단 가능.",
        ])
        print()

        # ── Step 1: 환경 탐지 ──
        print("▶ [1/5] 환경 탐지 중...")
        env = self.detect_environment()
        print(f"  Python       : {env.python_version}")
        print(f"  claude       : {'✓  ' + (env.claude_path or '') if env.has_claude else '✗  미감지'}")
        print(f"  openclaw     : {'✓  ' + (env.openclaw_path or '') if env.has_openclaw else '✗  미감지'}")
        print(f"  amp          : {'✓  ' + (env.amp_path or '') if env.has_amp else '✗  미감지'}")
        print(f"  OAUTH 토큰   : {'설정됨 ✓' if env.has_oauth_token else '미설정'}")
        print()

        if interactive and not _ask_confirm("환경 탐지 완료. 계속할까요?", default=True):
            print("설치를 취소했습니다.")
            return

        # ── Step 2: 역할 추천 + 확인 ──
        print()
        print("▶ [2/5] 역할 추천")
        roles = self.recommend_roles(env)
        confirmed_roles = []

        for role in roles:
            tool_info = f" ({role.tool})" if role.tool else ""
            print(f"\n  [{role.role}]{tool_info}")
            print(f"  설명: {role.description}")
            if interactive:
                include = _ask_confirm(f"  '{role.display_name}' 역할을 포함할까요?", default=True)
                if include:
                    confirmed_roles.append(role)
                else:
                    print(f"  → '{role.role}' 제외됨")
            else:
                confirmed_roles.append(role)

        if not confirmed_roles:
            print("\n⚠️  역할이 하나도 선택되지 않았습니다. 라이트 모드로 전환합니다.")
            self.run_lite()
            return

        # ── Step 3: 연결 테스트 ──
        print()
        print("▶ [3/5] 연결 테스트 중...")
        health = self.health_check(env)
        has_failure = False

        for tool, (ok, info) in health.items():
            status = "✓" if ok else "✗"
            print(f"  {status}  {tool}: {info}")
            if not ok:
                has_failure = True

        if has_failure and interactive:
            print()
            print("  ⚠️  일부 도구 연결에 실패했습니다.")
            print("  힌트: 경로 문제라면 'which claude' 로 확인하세요.")
            lite = _ask_confirm("  라이트 모드(PM만)로 계속할까요?", default=True)
            if lite:
                self.run_lite()
                return

        # ── Step 4: DB 초기화 ──
        print()
        print("▶ [4/5] DB 초기화 중...")
        self.init_database()
        print(f"  → {self.db_path} 생성 완료")

        # ── Step 5: 에이전트 등록 + 완료 ──
        print()
        print("▶ [5/5] 에이전트 등록 중...")
        self.register_roles(confirmed_roles)
        for r in confirmed_roles:
            print(f"  ✓  {r.role}: {r.display_name}")

        print()
        _print_box([
            "✅  설치 완료!",
            "",
            "구성된 역할:",
        ] + [f"  • {r.role:10s}: {r.display_name}" for r in confirmed_roles] + [
            "",
            "첫 번째 명령어:",
            "  rolemesh status",
            "  rolemesh route '코드 리뷰해줘'",
            "  rolemesh agents",
            "",
            f"DB: {self.db_path}",
            "문서: ~/rolemesh/docs/",
        ])
        print()

    # ── 라이트 모드 ───────────────────────────────────────────

    def run_lite(self) -> None:
        """라이트 모드: DB 초기화 + PM 역할만 등록."""
        print()
        _print_box([
            "RoleMesh Lite Mode",
            "최소 구성: DB 초기화 + PM 역할만 등록.",
        ])
        print()

        print("▶ [1/2] DB 초기화 중...")
        self.init_database()
        print(f"  → {self.db_path} 생성 완료")
        print()

        env = self.detect_environment()
        roles = self.recommend_roles(env)
        pm_roles = [r for r in roles if r.role == "PM"]
        if not pm_roles:
            pm_roles = [RoleConfig(
                role="PM",
                agent_id="local-pm",
                display_name="PM (로컬)",
                description="로컬 프로젝트 관리자 (라이트 모드)",
                tool=None,
                capabilities=[{
                    "name": "project_management",
                    "description": "태스크 계획 및 관리",
                    "keywords": ["계획", "관리", "plan"],
                    "cost_level": "low",
                }],
            )]

        print("▶ [2/2] PM 역할 등록 중...")
        self.register_roles(pm_roles)
        for r in pm_roles:
            print(f"  ✓  {r.role}: {r.display_name}")

        print()
        _print_box([
            "라이트 모드 완료.",
            f"DB: {self.db_path}",
            "",
            "Builder/Analyst 추가: rolemesh init",
        ])
        print()


def main():
    import argparse
    parser = argparse.ArgumentParser(prog="rolemesh init", add_help=False)
    parser.add_argument("--lite", action="store_true", help="라이트 모드: DB 초기화 + PM 역할만 등록")
    parser.add_argument("--non-interactive", action="store_true", help="자동 모드 (확인 없이 실행)")
    parser.add_argument("--db", default=None, help="DB 경로 재정의")
    parsed, _ = parser.parse_known_args()

    db_path = parsed.db or os.environ.get("ROLEMESH_DB", DEFAULT_DB_PATH)
    installer = RoleMeshInstaller(db_path=db_path)

    if parsed.lite:
        installer.run_lite()
    else:
        installer.run(interactive=not parsed.non_interactive)


if __name__ == "__main__":
    main()
