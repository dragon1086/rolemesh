"""
__main__.py — python3 -m rolemesh <command> 진입점
"""

import sys


def _usage():
    print("사용법: python3 -m rolemesh <command>")
    print()
    print("Commands:")
    print("  init      — RoleMesh Installer Wizard 실행 (환경 탐지 + 에이전트 등록)")
    print("  agents    — 등록된 에이전트 목록 출력")
    print("  status    — 태스크 큐 상태 출력")
    print("  route     — 태스크 라우팅 조회  예: python3 -m rolemesh route '코드 리뷰'")
    print()


def _cmd_init():
    from installer import main
    main()


def _cmd_agents():
    import os
    from registry_client import RegistryClient
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
    from registry_client import RegistryClient
    db_path = os.environ.get("ROLEMESH_DB", os.path.expanduser("~/rolemesh/rolemesh.db"))
    client = RegistryClient(db_path=db_path)
    counts = client.queue_counts()
    client.close()
    print("태스크 큐 상태:")
    for status, cnt in counts.items():
        print(f"  {status:<15}: {cnt}")


def _cmd_route(task_text: str):
    import os
    from registry_client import RegistryClient
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
    else:
        print(f"알 수 없는 명령: {cmd}")
        _usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
