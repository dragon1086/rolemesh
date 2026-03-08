"""
__main__.py — python3 -m rolemesh <command> 진입점
"""

import sys


def _usage():
    print("사용법: python3 -m rolemesh <command>")
    print()
    print("Commands:")
    print("  init               — RoleMesh Installer Wizard 실행 (환경 탐지 + 에이전트 등록)")
    print("  agents             — 등록된 에이전트 목록 출력")
    print("  status             — 태스크 큐 상태 출력")
    print("  route              — 태스크 라우팅 조회  예: python3 -m rolemesh route '코드 리뷰'")
    print("  integration add    — 외부 에이전트 등록  예: python3 -m rolemesh integration add --name mybot --role builder --endpoint http://localhost:8080")
    print("  integration list   — 등록된 통합 목록 출력")
    print("  integration remove — 통합 삭제  예: python3 -m rolemesh integration remove --name mybot")
    print()


def _cmd_init():
    from .installer import main
    main()


def _cmd_agents():
    import os
    from .registry_client import RegistryClient
    db_path = os.environ.get("ROLEMESH_DB", os.path.expanduser("~/rolemesh/rolemesh.db"))
    client = RegistryClient(db_path=db_path)
    agents = client.list_agents(active_only=False)
    client.close()
    if not agents:
        print("등록된 에이전트 없음. 먼저 'python3 -m rolemesh init' 실행")
        return
    print(f"{'ID':<20} {'이름':<25} {'상태'}")
    print("-" * 55)
    for a in agents:
        print(f"{a['agent_id']:<20} {a['display_name']:<25} {a['status']}")


def _cmd_status():
    import os
    from .registry_client import RegistryClient
    db_path = os.environ.get("ROLEMESH_DB", os.path.expanduser("~/rolemesh/rolemesh.db"))
    client = RegistryClient(db_path=db_path)
    counts = client.queue_counts()
    client.close()
    print("태스크 큐 상태:")
    for status, cnt in counts.items():
        print(f"  {status:<15}: {cnt}")


def _cmd_route(task_text: str):
    import os
    from .registry_client import RegistryClient
    db_path = os.environ.get("ROLEMESH_DB", os.path.expanduser("~/rolemesh/rolemesh.db"))
    client = RegistryClient(db_path=db_path)
    matches = client.lookup(task_text, top_k=3)
    client.close()
    if not matches:
        print("적합한 에이전트를 찾지 못했습니다.")
        return
    print(f"태스크: {task_text}")
    print()
    for i, m in enumerate(matches, 1):
        print(f"  [{i}] {m.agent_id} / {m.capability}  (score={m.score})")
        print(f"      {m.routing_explanation}")


def _cmd_integration(args: list[str]) -> None:
    """integration <add|list|remove> 서브커맨드 처리."""
    import os
    from .integration import IntegrationManager, DuplicateIntegrationError, IntegrationNotFoundError

    if not args:
        print("사용법: python3 -m rolemesh integration <add|list|remove>")
        sys.exit(1)

    subcmd = args[0]
    db_path = os.environ.get("ROLEMESH_DB", os.path.expanduser("~/rolemesh/rolemesh.db"))
    mgr = IntegrationManager(db_path=db_path)

    try:
        if subcmd == "add":
            _integration_add(mgr, args[1:])
        elif subcmd == "list":
            _integration_list(mgr)
        elif subcmd == "remove":
            _integration_remove(mgr, args[1:])
        else:
            print(f"알 수 없는 서브커맨드: {subcmd}")
            print("사용법: python3 -m rolemesh integration <add|list|remove>")
            sys.exit(1)
    finally:
        mgr.close()


def _integration_add(mgr, args: list[str]) -> None:
    """integration add --name X --role Y --endpoint Z [--capabilities a,b,c]"""
    import argparse
    parser = argparse.ArgumentParser(prog="rolemesh integration add", add_help=False)
    parser.add_argument("--name", required=True, help="에이전트 이름")
    parser.add_argument("--role", required=True, help="역할 (예: builder, analyzer)")
    parser.add_argument("--endpoint", required=True, help="HTTP 엔드포인트 또는 IPC 경로")
    parser.add_argument("--capabilities", default="", help="능력 목록 (쉼표 구분, 예: build,deploy)")
    parser.add_argument("--update", action="store_true", help="이미 있으면 업데이트")
    parsed = parser.parse_args(args)

    caps = [c.strip() for c in parsed.capabilities.split(",") if c.strip()] if parsed.capabilities else []

    from .integration import DuplicateIntegrationError
    try:
        info = mgr.add(
            name=parsed.name,
            role=parsed.role,
            endpoint=parsed.endpoint,
            capabilities=caps,
            allow_update=parsed.update,
        )
        print(f"[integration] 등록 완료: {info['name']} (role={info['role']}, endpoint={info['endpoint']})")
        if info["capabilities"]:
            print(f"  capabilities: {', '.join(info['capabilities'])}")
    except DuplicateIntegrationError as e:
        print(f"오류: {e}")
        sys.exit(1)


def _integration_list(mgr) -> None:
    """integration list"""
    integrations = mgr.list()
    if not integrations:
        print("등록된 통합 없음. 먼저 'python3 -m rolemesh integration add' 실행")
        return
    print(f"{'이름':<20} {'역할':<20} {'상태':<10} {'엔드포인트'}")
    print("-" * 75)
    for i in integrations:
        caps_str = ", ".join(i["capabilities"]) if i["capabilities"] else "-"
        print(f"{i['name']:<20} {i['role']:<20} {i['status']:<10} {i['endpoint']}")
        print(f"  capabilities: {caps_str}")


def _integration_remove(mgr, args: list[str]) -> None:
    """integration remove --name X"""
    import argparse
    from .integration import IntegrationNotFoundError
    parser = argparse.ArgumentParser(prog="rolemesh integration remove", add_help=False)
    parser.add_argument("--name", required=True, help="삭제할 에이전트 이름")
    parsed = parser.parse_args(args)

    try:
        mgr.remove(parsed.name)
        print(f"[integration] 삭제 완료: {parsed.name}")
    except IntegrationNotFoundError as e:
        print(f"오류: {e}")
        sys.exit(1)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        _usage()
        return

    cmd = args[0]
    if cmd == "init":
        _cmd_init()
    elif cmd == "agents":
        _cmd_agents()
    elif cmd == "status":
        _cmd_status()
    elif cmd == "route":
        if len(args) < 2:
            print("사용법: python3 -m rolemesh route '<task>'")
            sys.exit(1)
        _cmd_route(args[1])
    elif cmd == "integration":
        if len(args) < 2:
            print("사용법: python3 -m rolemesh integration <add|list|remove> [options]")
            sys.exit(1)
        _cmd_integration(args[1:])
    else:
        print(f"알 수 없는 명령: {cmd}")
        _usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
