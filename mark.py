"""최종 모델로 PDF·PPTX에 '검토 필요(예)'로 본 글을 표시한다. 학습·시험·평가(screen.py, label.py)와는 따로 돈다.

    최종 모델 (5.0)   분류기 multilingual-e5-small · 덩어리  →  LLM qwen3:8b · 프롬프트 안 C(사업 분야) · 생각 모드 끔
    5.1부터          표는 행 하나씩 판단해 '예'로 본 행에만 표시한다. 표시하지 않는 규칙(mark_rules.txt)을 적용한다.

    python mark.py                       화면을 브라우저에 띄운다 (이 PC 안에서만 열린다)
    python mark.py 보고서.pdf 발표.pptx   그 파일들을 올려 둔 채로 화면을 띄운다
    python mark.py 보고서.pdf --no-ui     화면 없이 바로 만든다
    python mark.py 보고서.pdf --no-ui --no-llm --threshold 0.4      분류기까지만, 문턱을 직접 정해서

결과는 out/mark 에 쌓인다.
    이름.분류기.marked.pdf(또는 .pptx)   분류기 출력으로 표시한 사본
    이름.LLM.marked.pdf(또는 .pptx)      LLM까지 거친 결과로 표시한 사본
    이름.pdf.html(또는 이름.pptx.html)    요약 화면 (두 결과를 나란히, 단계마다 걸린 시간)
    times.html, times.csv                실행마다 쌓이는 걸린 시간 기록
out 폴더의 문서 목록, 정답, 분류기는 읽기만 하고 고치지 않는다. 자료는 이 PC 밖으로 나가지 않는다(LLM은 이 PC의 Ollama).
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
    ap = argparse.ArgumentParser(description="최종 모델(분류기 → LLM)로 PDF·PPTX에 '검토 필요'로 본 글을 표시하고 단계마다 걸린 시간을 잰다")
    ap.add_argument("files", nargs="*", help="표시할 PDF·PPTX 파일")
    ap.add_argument("-o", "--out", default="out", help="추출 결과 폴더 (기본: out). 결과는 그 안의 mark 폴더에 쌓임")
    ap.add_argument("--port", type=int, default=8775, help="화면을 열 포트 (기본 8775, 쓰고 있으면 다음 번호)")
    ap.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    ap.add_argument("--no-ui", action="store_true", help="화면 없이 바로 만든다")
    ap.add_argument("--no-llm", action="store_true", help="--no-ui 에서: LLM 단계를 돌리지 않고 분류기 출력으로 표시한 사본만 만든다")
    ap.add_argument("--fresh", action="store_true", help="--no-ui 에서: 보관해 둔 계산을 쓰지 않고 처음부터 다시 계산한다(걸린 시간을 잴 때)")
    ap.add_argument("--threshold", type=float, help="--no-ui 에서: 분류기 점수가 이 값 이상이면 '예' (기본: 지난 학습에서 '예'의 90%%를 찾던 문턱, 없으면 0.5)")
    ap.add_argument("--method", choices=["annot", "paint"], default="annot", help="PDF 표시 방식: annot(형광펜 주석, 기본) | paint(쪽에 직접 칠하기)")
    ap.add_argument("--prompts-file", help="프롬프트 파일 (기본: 프로그램 폴더의 verify_prompts.txt)")
    ap.add_argument("--rules", help="표시하지 않는 규칙 파일 (기본: 프로그램 폴더의 mark_rules.txt. 없으면 기본값으로 만든다)")
    ap.add_argument("--sentences", help="기준 문장 파일 (기본: 프로그램 폴더의 screen_sentences.txt)")
    ap.add_argument("--labels", help="정답 파일 (기본: 프로그램 폴더의 labels/labels.json). 분류기는 그 옆 classifiers 폴더에서 읽음")
    ap.add_argument("--max-len", type=int, default=512, help="분류기 모델에 넣는 글의 최대 길이(토큰). 학습 때와 같아야 함 (기본 512)")
    ap.add_argument("--models-dir", help="분류기 모델 파일을 두는 폴더 (기본: 프로그램 폴더의 models)")
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
    prompts_file = Path(args.prompts_file) if args.prompts_file else cli.ROOT / "verify_prompts.txt"
    rules_file = Path(args.rules) if args.rules else cli.ROOT / "mark_rules.txt"
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
        if not files:
            raise SystemExit("[오류] --no-ui 에는 표시할 파일이 필요합니다. (예: python mark.py 보고서.pdf --no-ui)")
        return _no_ui(cfg, files, prompts_file, rules_file, args)

    from marking import server
    server.serve(cfg, files, prompts_file, args.port, not args.no_browser, rules_file)
    return 0


def _no_ui(cfg, files, prompts_file: Path, rules_file: Path, args) -> int:
    from marking import core, final, times
    from marking import rules as mrules
    from screening.models import ModelMissing
    from verifying import core as vcore
    from verifying import ollama

    seen = {"n": 0}

    def log(msg: str) -> None:                     # 덩어리마다의 진행 줄은 열 번에 한 번만 찍는다
        if "번째 덩어리" in msg:
            seen["n"] += 1
            if seen["n"] % 10 != 1:
                return
        print(msg, flush=True)

    scorer = core.Scorer(cfg)
    stop = vcore.Stop()
    llm, answers, bad = None, None, 0
    try:
        threshold, note = final.pick_threshold(cfg, "custom" if args.threshold is not None else "", args.threshold)
        rules = mrules.read_rules(rules_file)
        if not args.no_llm:
            llm = final.prepare_llm(cfg, prompts_file, log)
            answers = vcore.Answers(final.answers_file(cfg))
        log("최종 모델: 분류기 multilingual-e5-small · 덩어리(표는 행 하나씩) · 문턱 %.2f (%s)%s" % (threshold, note, " → LLM %s" % llm.label if llm else " (LLM 단계 없음)"))
        log("표시하지 않는 규칙(%s): 쪽 제목에 %s · 문장에 %s" % (rules_file.name, " · ".join("'%s'" % w for w in rules.title_words) or "(없음)",
                                                      " · ".join("'%s'" % w for w in rules.line_words) or "(없음)"))
        for p in files:
            log("표시하는 중: %s" % p.name)
            try:
                ex = core.extract(p)
                res = final.run_document(scorer, ex, llm, answers, threshold, note, args.method, log, stop, args.fresh, rules=rules)
            except (ValueError, ModelMissing) as exc:
                raise SystemExit("[오류] %s" % exc)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                bad += 1
                log("  실패: %s: %s" % (type(exc).__name__, exc))
                continue
            c, t, f = res["counts"], res["timing"], res["files"]
            log("  판단한 글 %d개(글 덩어리 %d + 표 %d개의 행 %d) → 분류기 문턱 이상 %d개 → 규칙으로 뺀 것 %d개(줄만 뺀 것 %d줄)" % (
                c["blocks"], c["text_blocks"], c["tables"], c["rows"], c["scored_yes"], c["ruled"], c["ruled_part"]))
            log("  → 분류기 '예' %d개%s" % (c["passed"], "" if c["kept"] is None else " → LLM까지 거쳐 남은 것 %d개 (LLM '예' %d · '아니오' %d%s)" % (
                c["kept"], c["llm_yes"], c["llm_no"], " · 읽지 못한 답 %d" % c["llm_unknown"] if c["llm_unknown"] else "")))
            if res["llm"]["why"]:
                log("  " + res["llm"]["why"])
            for _, name, did, sec, one, remark in times.detail_rows(res):
                log("  걸린 시간 · %-6s %8s   %s%s%s" % (name, times.fmt(sec), did, "" if one == "-" else " · " + one, " · " + remark if remark else ""))
            log("  걸린 시간 · 합계   %8s" % times.fmt(t["total"]))
            for n in res["notes"]:
                log("  " + n)
            if f["classifier"]:
                log("  분류기 표시 사본: %s" % (final.mark_dir(cfg) / f["classifier"]))
            if f["llm"]:
                log("  LLM 표시 사본:    %s" % (final.mark_dir(cfg) / f["llm"]))
            log("  요약 화면:        %s" % (final.mark_dir(cfg) / f["page"]))
    except (ValueError, ollama.OllamaError) as exc:
        raise SystemExit("[오류] %s" % exc)
    except KeyboardInterrupt:                      # Ctrl+C: 묻고 있던 요청을 끊고 끝낸다. 받은 답은 보관되어 있다
        stop.set()
        raise SystemExit("\n멈췄습니다. 그때까지 받은 LLM의 답은 보관되어 있어서, 다시 실행하면 이어서 받습니다.")
    finally:
        if llm is not None:
            ollama.unload(llm.model["name"])
    log("걸린 시간 기록: %s" % (final.mark_dir(cfg) / "times.html"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
