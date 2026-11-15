"""학습해 둔 모델로 PDF·PPTX에 '검토 필요(예)'로 본 글을 표시한다. 학습·시험·평가(screen.py, label.py)와는 따로 돈다.

    python mark.py                       고르는 화면을 브라우저에 띄운다 (이 PC 안에서만 열린다)
    python mark.py 보고서.pdf 발표.pptx   그 파일들을 올려 둔 채로 화면을 띄운다
    python mark.py 보고서.pdf --no-ui --model bge-m3 --unit line
                                         화면 없이 바로 만든다 (--stage, --threshold, --method 로 나머지를 정한다)

결과는 out/mark 에 쌓인다: 이름.모델.크기.marked.pdf(또는 .pptx)와 같은 이름의 .html(요약 화면).
out 폴더의 문서 목록, 정답, 분류기는 읽기만 하고 고치지 않는다.
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
    ap = argparse.ArgumentParser(description="학습해 둔 모델로 PDF·PPTX에 '검토 필요'로 본 글을 표시")
    ap.add_argument("files", nargs="*", help="표시할 PDF·PPTX 파일")
    ap.add_argument("-o", "--out", default="out", help="추출 결과 폴더 (기본: out). 결과는 그 안의 mark 폴더에 쌓임")
    ap.add_argument("--port", type=int, default=8775, help="화면을 열 포트 (기본 8775, 쓰고 있으면 다음 번호)")
    ap.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    ap.add_argument("--no-ui", action="store_true", help="화면 없이 바로 만든다 (--model 과 --unit 이 필요)")
    ap.add_argument("--model", help="모델: bge-m3, kure-v1, me5-small")
    ap.add_argument("--unit", choices=["block", "agg", "line"], help="넣는 크기: block(덩어리), agg(줄로 넣어 덩어리로 합침), line(줄)")
    ap.add_argument("--stage", choices=["after", "before"], default="after", help="after(학습한 분류기, 기본) | before(기준 문장)")
    ap.add_argument("--threshold", type=float, default=0.5, help="이 점수 이상이면 '예'로 표시 (기본 0.5)")
    ap.add_argument("--method", choices=["annot", "paint"], default="annot", help="PDF 표시 방식: annot(형광펜 주석, 기본) | paint(쪽에 직접 칠하기)")
    ap.add_argument("--sentences", help="기준 문장 파일 (기본: 프로그램 폴더의 screen_sentences.txt)")
    ap.add_argument("--labels", help="정답 파일 (기본: 프로그램 폴더의 labels/labels.json). 분류기는 그 옆 classifiers 폴더에서 읽음")
    ap.add_argument("--max-len", type=int, default=512, help="모델에 넣는 글의 최대 길이(토큰). 학습 때와 같아야 함 (기본 512)")
    ap.add_argument("--models-dir", help="모델 파일을 두는 폴더 (기본: 프로그램 폴더의 models)")
    ap.add_argument("--title-weight", type=float, help="쪽 제목 점수를 섞는 비율 (기본: 설정 파일의 값)")
    ap.add_argument("--options", help="설정 파일 (기본: 프로그램 폴더의 screen_options.txt)")
    args = ap.parse_args()

    from screening.options import check_title_weight, read_options
    options_file = Path(args.options) if args.options else cli.ROOT / "screen_options.txt"
    try:
        title_weight = read_options(options_file)["title_weight"] if args.title_weight is None else check_title_weight(args.title_weight)
    except ValueError as exc:
        raise SystemExit("[오류] %s" % exc)
    cfg = cli.Config(out_dir=Path(args.out), models=None,
                     sentences=Path(args.sentences) if args.sentences else cli.ROOT / "screen_sentences.txt",
                     labels=Path(args.labels) if args.labels else cli.ROOT / "labels" / "labels.json",
                     target=0.9, max_len=args.max_len, download=False,
                     models_dir=Path(args.models_dir) if args.models_dir else cli.ROOT / "models",
                     options=options_file, title_weight=title_weight)
    missing = [n for n in cli.missing_packages() if n != "sklearn"]      # 표시하기는 분류기를 새로 학습시키지 않는다
    if missing:
        raise SystemExit("[오류] 필요한 라이브러리가 없습니다: %s\n       install_screen.bat 을 먼저 실행해 주세요." % ", ".join(missing))
    cli.setup_env(cfg.models_dir)
    files = []
    for f in args.files:
        p = Path(f)
        if not p.is_file() or p.suffix.lower() not in (".pdf", ".pptx") or p.name.startswith("~$"):
            print("건너뜀(PDF나 PPTX 파일이 아니거나 없음): %s" % f, flush=True)
            continue
        files.append(p.resolve())

    if args.no_ui:
        if not files or not args.model or not args.unit:
            raise SystemExit("[오류] --no-ui 에는 파일과 --model, --unit 이 필요합니다. (예: python mark.py 보고서.pdf --no-ui --model bge-m3 --unit line)")
        from marking import core, make
        scorer = core.Scorer(cfg)
        log = lambda msg: print(msg, flush=True)
        bad = 0
        for p in files:
            log("표시하는 중: %s" % p.name)
            try:
                ex = core.extract(p)
                got = make.make(scorer, ex, args.model, args.unit, args.stage, args.threshold, args.method, log)
            except (ValueError, SystemExit) as exc:
                raise SystemExit("[오류] %s" % exc)
            except Exception as exc:
                bad += 1
                log("  실패: %s: %s" % (type(exc).__name__, exc))
                continue
            log("  '예'로 본 %s %d개 / 전체 %d개" % ("줄" if got["unit"] == "line" else "덩어리", got["yes"], got["total"]))
            for n in got["notes"]:
                log("  " + n)
            if got["marked"]:
                log("  표시한 파일: %s" % (make.mark_dir(cfg) / got["marked"]))
            log("  요약 화면:   %s" % (make.mark_dir(cfg) / got["page"]))
        return 1 if bad else 0

    from marking import server
    server.serve(cfg, files, args.port, not args.no_browser)
    return 0


if __name__ == "__main__":
    sys.exit(main())
