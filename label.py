"""정답 붙이는 화면을 연다. 줄마다 '특허출원 검토 필요'에 예/아니오를 붙여 분류기를 학습시킬 자료를 만든다.

    python label.py            out 폴더의 추출 결과를 브라우저에 띄운다 (이 PC 안에서만 열린다)

화면에서 '학습하고 결과 보기'를 누르면 screen.py 를 돌린 것과 같은 결과가 만들어진다.
"""
from __future__ import annotations

import argparse
import sys

from screening import cli


def main() -> int:
    parser = argparse.ArgumentParser(description="정답 붙이는 화면 (1차 걸러내기 분류기 학습용)")
    cli.add_common(parser)
    parser.add_argument("--port", type=int, default=8765, help="화면을 열 포트 (기본 8765, 쓰고 있으면 다음 번호)")
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    args = parser.parse_args()
    cfg = cli.config_from(args)
    cli.check_ready(cfg)
    from screening import server
    server.serve(cfg, args.port, not args.no_browser)
    return 0


if __name__ == "__main__":
    sys.exit(main())
