"""2단계: 추출한 덩어리·줄 가운데 특허출원 검토가 필요한 것을 걸러 내는 모델 네 가지를 비교한다.

    python screen.py                 out 폴더의 추출 결과를 네 모델로 점수 매기고 비교 화면을 만든다
    python screen.py --download      모델 파일만 내려받는다

1단계(compare.py)가 만든 out/이름.units.json 을 읽는다. 1단계의 결과물은 건드리지 않는다.
결과는 out/screen/ 에 따로 쌓인다: index.html(비교 화면), 이름.screen.html(문서별), scores.json(점수 자료).
"""
from __future__ import annotations

import argparse
import sys
import time

from screening import cli


def main() -> int:
    parser = argparse.ArgumentParser(description="1차 걸러내기 모델 비교 (bge-m3, KURE-v1, multilingual-e5-small, bge-m3-zeroshot-v2.0-c)")
    cli.add_common(parser)
    parser.add_argument("--download", action="store_true", help="모델 파일만 내려받고 끝냄")
    args = parser.parse_args()
    cfg = cli.config_from(args)

    def log(msg: str) -> None:
        print(msg, flush=True)

    if args.download:
        missing = [n for n in cli.missing_packages() if n == "huggingface_hub"]
        if missing:
            raise SystemExit("[오류] install_screen.bat 을 먼저 실행해 주세요.")
        cfg.download = True
        failed = cli.download_only(cfg, log)
        log("모델 폴더: %s" % cfg.models_dir)
        return 1 if failed else 0

    cli.check_ready(cfg)
    t0 = time.time()
    try:
        res, index = cli.execute(cfg, log)
    except ValueError as exc:                      # 기준 문장 파일이 잘못됐을 때 등
        raise SystemExit("[오류] %s" % exc)
    ok = [r for r in res.runs if r.ok]
    c = res.counts()
    log("")
    log("문서 %d개 · 덩어리 %d개 · 줄 %d개 · 정답: 줄 기준 예 %d개, 아니오 %d개" % (
        c["docs"], c["blocks"], c["lines"], c["line_yes"], c["line_no"]))
    log("쪽 제목 반영: %s" % ("비율 %g (설정: %s)" % (res.title_weight, cfg.options.name) if res.title_weight else "꺼짐"))
    for r in res.runs:
        if not r.ok:
            log("  실행하지 못한 모델: %s (%s)" % (r.spec["label"], r.error))
    log("걸린 시간 %.0f초 · 비교 화면: %s" % (time.time() - t0, index))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
