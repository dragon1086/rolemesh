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
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path

    # ── 환경 탐지 ──────────────────────────────────────────────

    def detect_environment(self) -> Environment:
        """시스템에서 사용 가능한 도구와 환경변수를 탐지."""
        env = Environment()

        # claude 바이너리
        env.claude_path = shutil.which("claude")
        env.has_claude = env.claude_path is not None

        # openclaw 바이너리
        env.openclaw_path = shutil.which("openclaw")
        env.has_openclaw = env.openclaw_path is not None

        # amp 바이너리
        env.amp_path = shutil.which("amp")
        env.has_amp = env.amp_path is not None

        # python 버전
        env.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        # 환경변수
        env.anthropic_model = os.environ.get("ANTHROPIC_MODEL")
        env.has_oauth_token = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))

        return env

    # ── 역할 추천 ──────────────────────────────────────────────

    def recommend_roles(self, env: Environment) -> list[RoleConfig]:
        """감지된 환경 기반으로 역할 구성을 추천."""
        roles: list[RoleConfig] = []

        # PM — openclaw 감지 시 자동 배정
        if env.has_openclaw:
            roles.append(RoleConfig(
                role="PM",
                agent_id="openclaw-pm",
                display_name="PM (OpenClaw)",
                description="프로젝트 관리, 태스크 라우팅, 팀 조율",
                tool="openclaw",
                capabilities=[
                    {
                        "name": "project_management",
                        "description": "태스크 계획, 우선순위 지정, 팀 조율",
                        "keywords": ["계획", "관리", "조율", "우선순위", "pm", "plan", "manage"],
                        "cost_level": "medium",
                    }
                ],
            ))

        # Builder — claude 감지 시 자동 배정
        if env.has_claude:
            roles.append(RoleConfig(
                role="Builder",
                agent_id="claude-builder",
                display_name="Builder (Claude Code)",
                description="코드 작성, 버그 수정, 구현",
                tool="claude",
                capabilities=[
                    {
                        "name": "code_write",
                        "description": "코드 구현, 리팩토링, 버그 수정",
                        "keywords": ["코드", "구현", "개발", "버그", "code", "build", "fix", "implement"],
                        "cost_level": "high",
                    }
                ],
            ))

        # Analyst — amp 감지 시 자동 배정
        if env.has_amp:
            roles.append(RoleConfig(
                role="Analyst",
                agent_id="amp-analyst",
                display_name="Analyst (amp)",
                description="데이터 분석, 전략 검토, 인사이트 도출",
                tool="amp",
                capabilities=[
                    {
                        "name": "emergent_analysis",
                        "description": "데이터 분석, 전략 검토, 인사이트 도출",
                        "keywords": ["분석", "검토", "전략", "인사이트", "analyze", "review", "strategy"],
                        "cost_level": "medium",
                    }
                ],
            ))

        # 라이트 모드: 아무것도 없으면 최소 구성 (PM + Builder 더미)
        if not roles:
            roles.append(RoleConfig(
                role="PM",
                agent_id="local-pm",
                display_name="PM (로컬)",
                description="로컬 프로젝트 관리자 (라이트 모드)",
                tool=None,
                capabilities=[
                    {
                        "name": "project_management",
                        "description": "태스크 계획 및 관리",
                        "keywords": ["계획", "관리", "plan"],
                        "cost_level": "low",
                    }
                ],
            ))

        return roles

    # ── DB 초기화 ──────────────────────────────────────────────

    def init_database(self) -> None:
        """rolemesh.db 경로에 DB 초기화."""
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)

        # init_db.py의 init_db() 호출
        from init_db import init_db
        conn = init_db(self.db_path)
        conn.close()

    # ── 에이전트 등록 ──────────────────────────────────────────

    def register_roles(self, roles: list[RoleConfig]) -> None:
        """추천된 역할들을 registry에 등록."""
        from registry_client import RegistryClient
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

    # ── 출력 헬퍼 ─────────────────────────────────────────────

    @staticmethod
    def _print_header():
        print()
        print("=" * 56)
        print("  RoleMesh Installer Wizard v0.1")
        print("  로컬 AI 팀을 15분 내에 구성합니다.")
        print("=" * 56)
        print()

    @staticmethod
    def _print_env_summary(env: Environment):
        print("[1/4] 환경 탐지 결과")
        print(f"  Python       : {env.python_version}")
        print(f"  claude       : {'✓ ' + env.claude_path if env.has_claude else '✗ 미감지'}")
        print(f"  openclaw     : {'✓ ' + env.openclaw_path if env.has_openclaw else '✗ 미감지'}")
        print(f"  amp          : {'✓ ' + env.amp_path if env.has_amp else '✗ 미감지'}")
        print(f"  ANTHROPIC_MODEL      : {env.anthropic_model or '미설정'}")
        print(f"  CLAUDE_CODE_OAUTH_TOKEN : {'설정됨' if env.has_oauth_token else '미설정'}")
        print()

    @staticmethod
    def _print_roles(roles: list[RoleConfig]):
        print("[2/4] 추천 역할 구성")
        for r in roles:
            tool_info = f" ({r.tool})" if r.tool else ""
            print(f"  [{r.role}]{tool_info} → {r.display_name}")
            print(f"         {r.description}")
        print()

    @staticmethod
    def _print_completion(roles: list[RoleConfig], db_path: str):
        print("[4/4] 설치 완료!")
        print()
        print("  구성된 역할:")
        for r in roles:
            print(f"    - {r.role:10s} : {r.display_name}")
        print()
        print(f"  DB 위치: {db_path}")
        print()
        print("  첫 사용 예시:")
        print("    python3 -m rolemesh status")
        print("    python3 -m rolemesh route '코드 리뷰해줘'")
        print("    python3 -m rolemesh agents")
        print()
        print("  문서: ~/rolemesh/docs/")
        print("=" * 56)
        print()

    # ── 라이트 모드 ───────────────────────────────────────────

    def run_lite(self) -> None:
        """라이트 모드: DB 초기화 + PM 역할만 등록. sqlite3만 필요. 워커 미실행."""
        print()
        print("=" * 56)
        print("  RoleMesh Lite Mode")
        print("  최소 구성: DB 초기화 + PM 역할 등록만 수행.")
        print("=" * 56)
        print()

        # DB 초기화
        print("[1/2] DB 초기화 중...")
        self.init_database()
        print(f"  → {self.db_path} 생성 완료")
        print()

        # PM 역할만 등록 (openclaw 또는 local-pm)
        env = self.detect_environment()
        roles = self.recommend_roles(env)
        pm_roles = [r for r in roles if r.role == "PM"]
        if not pm_roles:
            pm_roles = [
                RoleConfig(
                    role="PM",
                    agent_id="local-pm",
                    display_name="PM (로컬)",
                    description="로컬 프로젝트 관리자 (라이트 모드)",
                    tool=None,
                    capabilities=[
                        {
                            "name": "project_management",
                            "description": "태스크 계획 및 관리",
                            "keywords": ["계획", "관리", "plan"],
                            "cost_level": "low",
                        }
                    ],
                )
            ]

        print("[2/2] PM 역할 등록 중...")
        self.register_roles(pm_roles)
        for r in pm_roles:
            print(f"  → {r.role}: {r.display_name} 등록 완료")
        print()
        print(f"  DB 위치: {self.db_path}")
        print("  라이트 모드 완료. Builder/Analyst는 'python3 -m rolemesh init' 으로 추가 가능.")
        print("=" * 56)
        print()

    # ── 메인 실행 ─────────────────────────────────────────────

    def run(self) -> None:
        """인터랙티브 없이 자동으로 환경 탐지 → 역할 추천 → DB 초기화 → 등록."""
        self._print_header()

        # 1. 환경 탐지
        env = self.detect_environment()
        self._print_env_summary(env)

        # 2. 역할 추천
        roles = self.recommend_roles(env)
        self._print_roles(roles)

        # 3. DB 초기화
        print("[3/4] DB 초기화 중...")
        self.init_database()
        print(f"  → {self.db_path} 생성 완료")
        print()

        # 4. 에이전트 등록
        self.register_roles(roles)

        # 5. 완료 요약
        self._print_completion(roles, self.db_path)


def main():
    import argparse
    parser = argparse.ArgumentParser(prog="rolemesh init", add_help=False)
    parser.add_argument("--lite", action="store_true", help="라이트 모드: DB 초기화 + PM 역할만 등록 (워커 미실행)")
    parser.add_argument("--db", default=None, help="DB 경로 재정의")
    parsed, _ = parser.parse_known_args()

    db_path = parsed.db or os.environ.get("ROLEMESH_DB", DEFAULT_DB_PATH)
    installer = RoleMeshInstaller(db_path=db_path)

    if parsed.lite:
        installer.run_lite()
    else:
        installer.run()


if __name__ == "__main__":
    main()
