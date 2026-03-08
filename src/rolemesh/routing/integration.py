"""
integration.py — RoleMesh Integration Manager

외부 AI 에이전트를 RoleMesh 레지스트리에 등록/조회/삭제.

사용 예:
    from rolemesh.integration import IntegrationManager
    mgr = IntegrationManager()
    mgr.add("mybot", role="builder", endpoint="http://localhost:8080",
            cmd="mybot -p", provider="openai",
            capabilities=["build", "deploy"])
    mgr.list()
    mgr.remove("mybot")
"""

import os
import stat
from typing import Optional

from ..core.registry_client import RegistryClient

DEFAULT_DB_PATH = os.environ.get(
    "ROLEMESH_DB", os.path.expanduser("~/rolemesh/rolemesh.db")
)


class DuplicateIntegrationError(ValueError):
    """동일 name의 통합이 이미 존재할 때 발생."""


class IntegrationNotFoundError(KeyError):
    """존재하지 않는 통합을 삭제/조회할 때 발생."""


class IntegrationManager:
    """
    외부 AI 에이전트를 RoleMesh 레지스트리에 등록·관리한다.

    Parameters
    ----------
    db_path : str, optional
        SQLite DB 경로. 기본값: ~/rolemesh/rolemesh.db
        (환경변수 ROLEMESH_DB로 재정의 가능)
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._client = RegistryClient(db_path=self._db_path)

    # ── public API ───────────────────────────────────────────────────────────

    def add(
        self,
        name: str,
        role: str,
        endpoint: str,
        capabilities: list[str] | None = None,
        allow_update: bool = False,
        cmd: str = "",
        provider: str = "",
        auto_script: bool = False,
    ) -> dict:
        """에이전트를 레지스트리에 등록한다.

        Parameters
        ----------
        name : str
            에이전트 고유 식별자 (agent_id로 사용)
        role : str
            역할 설명 (display_name으로 저장)
        endpoint : str
            에이전트 HTTP 엔드포인트 또는 IPC 경로
        capabilities : list[str], optional
            능력 이름 목록. 각 항목이 capability로 등록됨.
        allow_update : bool
            True면 이미 존재해도 업데이트. False(기본)면 중복 시 예외.
        cmd : str
            실행 명령 (예: "gemini -p", "amp --task"). auto_script=True 시 필수.
        provider : str
            Throttle/CB에서 사용할 provider 이름 (예: "gemini", "openai", "anthropic").
        auto_script : bool
            True면 등록 후 {name}-delegate.sh를 자동 생성. 기본 False.

        Returns
        -------
        dict
            등록된 통합 정보. script_path 키가 추가될 수 있음.

        Raises
        ------
        DuplicateIntegrationError
            allow_update=False 상태에서 동일 name이 이미 존재할 때
        ValueError
            cmd가 빈 문자열이고 auto_script=True일 때
        """
        name = name.strip()
        if not name:
            raise ValueError("name은 비어 있을 수 없습니다.")
        if not endpoint:
            raise ValueError("endpoint는 비어 있을 수 없습니다.")
        if auto_script and not cmd.strip():
            raise ValueError("auto_script=True일 때 cmd는 비어 있을 수 없습니다.")

        existing = self._find(name)
        if existing and not allow_update:
            raise DuplicateIntegrationError(
                f"'{name}' 통합이 이미 등록되어 있습니다. "
                "업데이트하려면 allow_update=True를 사용하세요."
            )

        self._client.register_agent(
            agent_id=name,
            display_name=role,
            description=f"role={role}",
            endpoint=endpoint,
        )

        caps = capabilities or []
        for cap in caps:
            cap = cap.strip()
            if cap:
                self._client.register_capability(
                    agent_id=name,
                    name=cap,
                    description=f"{role} capability: {cap}",
                    keywords=[cap],
                )

        result: dict = {
            "name": name,
            "role": role,
            "endpoint": endpoint,
            "capabilities": caps,
        }

        if auto_script:
            script_path = self.generate_delegate_script(
                name=name,
                cmd=cmd.strip(),
                provider=provider.strip() or name,
            )
            result["script_path"] = script_path

        return result

    def generate_delegate_script(
        self,
        name: str,
        cmd: str,
        provider: str,
        scripts_dir: Optional[str] = None,
        template_path: Optional[str] = None,
    ) -> str:
        """{name}-delegate.sh 스크립트를 자동 생성한다.

        Parameters
        ----------
        name : str
            에이전트 이름 (파일명: {name}-delegate.sh)
        cmd : str
            실행 명령 (예: "gemini -p")
        provider : str
            Throttle/CB provider 이름
        scripts_dir : str, optional
            출력 디렉터리. 기본: scripts/
        template_path : str, optional
            템플릿 파일 경로. 기본: scripts/templates/delegate.sh.tmpl

        Returns
        -------
        str
            생성된 스크립트 절대 경로
        """
        if not cmd.strip():
            raise ValueError("cmd는 비어 있을 수 없습니다.")

        tmpl_path = template_path or os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "templates", "delegate.sh.tmpl")
        )
        with open(tmpl_path, "r", encoding="utf-8") as f:
            content = f.read()

        content = content.replace("{{NAME}}", name).replace("{{CMD}}", cmd).replace("{{PROVIDER}}", provider)

        out_dir = scripts_dir or os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts")
        )
        os.makedirs(out_dir, exist_ok=True)
        script_path = os.path.join(out_dir, f"{name}-delegate.sh")

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(content)

        # chmod +x
        current = os.stat(script_path).st_mode
        os.chmod(script_path, current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        return os.path.abspath(script_path)

    def list(self) -> list[dict]:
        """등록된 모든 통합 목록을 반환한다.

        Returns
        -------
        list[dict]
            각 항목: {name, role, endpoint, capabilities, status}
        """
        agents = self._client.list_agents(active_only=False)
        result = []
        for agent in agents:
            caps = self._get_capabilities(agent["agent_id"])
            result.append({
                "name": agent["agent_id"],
                "role": agent["display_name"],
                "endpoint": agent.get("endpoint", ""),
                "capabilities": caps,
                "status": agent.get("status", "active"),
            })
        return result

    def remove(self, name: str) -> None:
        """등록된 통합을 삭제한다.

        Parameters
        ----------
        name : str
            삭제할 에이전트 이름 (agent_id)

        Raises
        ------
        IntegrationNotFoundError
            존재하지 않는 name일 때
        """
        if not self._find(name):
            raise IntegrationNotFoundError(
                f"'{name}' 통합을 찾을 수 없습니다."
            )
        conn = self._client._conn_ctx()
        conn.execute("DELETE FROM capabilities WHERE agent_id = ?", (name,))
        conn.execute("DELETE FROM agents WHERE agent_id = ?", (name,))
        conn.commit()

    def get(self, name: str) -> dict:
        """단일 통합 정보를 반환한다.

        Raises
        ------
        IntegrationNotFoundError
            존재하지 않을 때
        """
        info = self._find(name)
        if not info:
            raise IntegrationNotFoundError(f"'{name}' 통합을 찾을 수 없습니다.")
        caps = self._get_capabilities(name)
        return {
            "name": info["agent_id"],
            "role": info["display_name"],
            "endpoint": info.get("endpoint", ""),
            "capabilities": caps,
            "status": info.get("status", "active"),
        }

    def close(self) -> None:
        """DB 연결을 닫는다."""
        self._client.close()

    # ── internal helpers ─────────────────────────────────────────────────────

    def _find(self, name: str) -> dict | None:
        conn = self._client._conn_ctx()
        row = conn.execute(
            "SELECT * FROM agents WHERE agent_id = ?", (name,)
        ).fetchone()
        return dict(row) if row else None

    def _get_capabilities(self, agent_id: str) -> list[str]:
        conn = self._client._conn_ctx()
        rows = conn.execute(
            "SELECT name FROM capabilities WHERE agent_id = ?", (agent_id,)
        ).fetchall()
        return [r["name"] for r in rows]
