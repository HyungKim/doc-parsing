"""분류기가 '검토 필요(예)'로 본 글을 이 PC 안의 LLM(Ollama)으로 한 번 더 검증하고, 모델·프롬프트별 결과와 시간을 견준다.

    python verify.py                     고르는 화면을 브라우저에 띄운다 (이 PC 안에서만 열린다)
    python verify.py --no-ui             화면 없이 기본값으로 바로 돌린다
    python verify.py --no-ui --llm qwen3:4b-instruct,qwen3:8b --prompts A,C,F --sample 100

자료는 이 PC 밖으로 나가지 않는다: Ollama에는 127.0.0.1로만 말을 걸고, 이름에 cloud가 붙은 모델은 거부한다.
정답, 분류기, out 폴더의 문서 목록은 읽기만 한다. 결과는 out/verify 에 쌓인다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from screening import cli


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")      # Windows 콘솔 한글 깨짐 방지
        except Exception:
            pass
    from verifying import core

    ap = argparse.ArgumentParser(description="분류기가 '예'로 본 글을 이 PC 안의 LLM으로 한 번 더 검증하고 결과를 견줌")
    ap.add_argument("-o", "--out", default="out", help="추출 결과 폴더 (기본: out). 결과는 그 안의 verify 폴더에 쌓임")
    ap.add_argument("--port", type=int, default=8785, help="화면을 열 포트 (기본 8785, 쓰고 있으면 다음 번호)")
    ap.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    ap.add_argument("--no-ui", action="store_true", help="화면 없이 바로 돌린다")
    ap.add_argument("--classifier", default=core.DEFAULT_CLASSIFIER, help="분류기 모델: me5-small(기본), bge-m3, kure-v1")
    ap.add_argument("--unit", choices=["block", "agg", "line"], default=core.DEFAULT_VIEW,
                    help="넣는 크기: block(덩어리), agg(줄로 넣어 덩어리로 합침), line(줄, 기본)")
    ap.add_argument("--threshold-mode", choices=["test90", "saved", "half", "custom"], default="test90",
                    help="분류기 문턱: test90(시험 문서에서 '예'의 90%%를 찾는 문턱, 기본) | saved(지난 학습의 문턱) | half(0.5) | custom")
    ap.add_argument("--threshold", type=float, help="--threshold-mode custom 일 때의 문턱")
    ap.add_argument("--llm", default=",".join(core.DEFAULT_LLMS), help="LLM 이름(Ollama). 쉼표로 여러 개 (기본: %s)" % ",".join(core.DEFAULT_LLMS))
    ap.add_argument("--prompts", default="", help="돌릴 프롬프트 안의 기호. 쉼표로 여러 개 (기본: 모두)")
    ap.add_argument("--sample", type=int, default=core.DEFAULT_SAMPLE, help="LLM에 넣을 글 수 (기본 %d, 0이면 통과한 글 전부)" % core.DEFAULT_SAMPLE)
    ap.add_argument("--with-rejected", action="store_true", help="분류기가 떨어뜨린 글도 같은 수만큼 LLM에 넣어 본다")
    ap.add_argument("--prompts-file", help="프롬프트 파일 (기본: 프로그램 폴더의 verify_prompts.txt)")
    ap.add_argument("--sentences", help="기준 문장 파일 (기본: 프로그램 폴더의 screen_sentences.txt)")
    ap.add_argument("--labels", help="정답 파일 (기본: 프로그램 폴더의 labels/labels.json). 분류기는 그 옆 classifiers 폴더에서 읽음")
    ap.add_argument("--test-docs", help="시험용 문서 목록 파일 (기본: 프로그램 폴더의 screen_test_docs.txt)")
    ap.add_argument("--recall", type=float, default=0.9, help="놓치지 않으려는 '예'의 비율 (기본 0.9)")
    ap.add_argument("--max-len", type=int, default=512, help="분류기 모델에 넣는 글의 최대 길이(토큰). 학습 때와 같아야 함 (기본 512)")
    ap.add_argument("--models-dir", help="분류기 모델 파일을 두는 폴더 (기본: 프로그램 폴더의 models)")
    ap.add_argument("--title-weight", type=float, help="쪽 제목 점수를 섞는 비율 (기본: 설정 파일의 값)")
    ap.add_argument("--options", help="설정 파일 (기본: 프로그램 폴더의 screen_options.txt)")
    args = ap.parse_args()

    from screening.options import check_title_weight, read_options
    if not 0 < args.recall <= 1:
        raise SystemExit("--recall 은 0보다 크고 1 이하여야 합니다 (예: 0.9)")
    options_file = Path(args.options) if args.options else cli.ROOT / "screen_options.txt"
    try:
        title_weight = read_options(options_file)["title_weight"] if args.title_weight is None else check_title_weight(args.title_weight)
    except ValueError as exc:
        raise SystemExit("[오류] %s" % exc)
    cfg = cli.Config(out_dir=Path(args.out), models=None,
                     sentences=Path(args.sentences) if args.sentences else cli.ROOT / "screen_sentences.txt",
                     labels=Path(args.labels) if args.labels else cli.ROOT / "labels" / "labels.json",
                     target=args.recall, max_len=args.max_len, download=False,
                     models_dir=Path(args.models_dir) if args.models_dir else cli.ROOT / "models",
                     options=options_file, test_docs=Path(args.test_docs) if args.test_docs else cli.ROOT / "screen_test_docs.txt",
                     title_weight=title_weight)
    missing = [n for n in cli.missing_packages() if n != "sklearn"]      # 검증하기는 분류기를 새로 학습시키지 않는다
    if missing:
        raise SystemExit("[오류] 필요한 라이브러리가 없습니다: %s\n       install_screen.bat 을 먼저 실행해 주세요." % ", ".join(missing))
    cli.setup_env(cfg.models_dir)
    env = core.Env(cfg, Path(args.prompts_file) if args.prompts_file else cli.ROOT / "verify_prompts.txt")

    if args.no_ui:
        from marking import core as mcore
        from screening.models import ModelMissing
        from verifying import ollama, report
        setup = core.Setup(classifier=args.classifier, view=args.unit, thr_mode=args.threshold_mode, threshold=args.threshold,
                           llms=[n.strip() for n in args.llm.split(",") if n.strip()],
                           variants=[k.strip() for k in args.prompts.split(",") if k.strip()],
                           sample=max(0, args.sample), with_rejected=args.with_rejected)
        seen = {"n": 0}

        def log(msg: str) -> None:                 # 글마다의 진행 줄은 열 번에 한 번만 찍는다
            if "번째 글" in msg:
                seen["n"] += 1
                if seen["n"] % 10 != 1:
                    return
            print(msg, flush=True)

        try:
            res = core.run(env, setup, mcore.Scorer(cfg, "verify"), log)
        except (ValueError, ollama.OllamaError, ModelMissing) as exc:
            raise SystemExit("[오류] %s" % exc)
        page = report.write(env, res)
        for c in res["combos"]:
            m = c["metrics"]
            if not m:
                print("  %s · %s %s: %s" % (c["llm"], c["variant"], c["name"], c["error"] or "받은 답 없음"))
                continue
            print("  %s · %s %s: %d개 가운데 %d개 남김, '아니오' %d/%d 덜어냄, '예' %d/%d 잃음, 글 하나에 %.1f초" % (
                c["llm"], c["variant"], c["name"], m["n"], m["kept"], m["removed_no"], m["no"], m["lost_yes"], m["yes"], m["sec_mean"]))
        print("결과 화면: %s" % page.resolve())
        return 0

    from verifying import server
    server.serve(env, args.port, not args.no_browser)
    return 0


if __name__ == "__main__":
    sys.exit(main())
