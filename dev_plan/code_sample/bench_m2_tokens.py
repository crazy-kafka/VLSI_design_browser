"""Measure the __points_only fast path over wiring tails, as shipped.

Times the full tokeniser against the shipped dispatch (guard -> point-only scan ->
full tokeniser) on the real gcd tails, synthetic via arrays, and a mix. Equivalence
is asserted per tail. Parser-accurate: the glued-star substitution happens once and
both paths share the subbed tail.

Run:  python dev_plan/code_sample/bench_m2_tokens.py
"""
import re
import time

import numpy as np

from vlsi_viewer.parsers.DEF.compiledRe import CompiledRe

DEF = "sample_data/real/nangate45/gcd_nangate45.def"

re_points = CompiledRe.re_points_tail
re_word_char = CompiledRe.re_word_char


def resolve(tok, last, axis):
    return last[axis] if tok == "*" else int(tok)


def full_tokenise(tail):
    """The re_wire_token loop, shared by both paths."""
    out, last = [], [None, None]
    for token in CompiledRe.re_wire_token.finditer(tail):
        x, y, ext, vx, vy, rx, ry, rx2, ry2 = token.group(
            'x', 'y', 'ext', 'vx', 'vy', 'rx0', 'ry0', 'rx1', 'ry1')
        if vx is not None:
            vx = resolve(vx, last, 0)
            vy = resolve(vy, last, 1)
            last[0], last[1] = vx, vy
            out.append(('vpt', vx, vy, None))
        elif x is not None:
            x = resolve(x, last, 0)
            y = resolve(y, last, 1)
            last[0], last[1] = x, y
            out.append(('pt', x, y, int(ext) if ext is not None else None))
        elif rx is None:
            name, orient = token.group('via', 'via_orient')
            if name in CompiledRe.WIRE_KEYWORDS:
                continue
            out.append(('via', name, orient))
    return out


def old_scan(tail):
    """Before M2: sub once, full tokeniser."""
    if "*" in tail:
        tail = CompiledRe.re_glued_star.sub(" ", tail)
    return full_tokenise(tail)


def new_scan(tail):
    """The shipped dispatch: sub once, guard, point-only scan, else full tokeniser."""
    if "*" in tail:
        tail = CompiledRe.re_glued_star.sub(" ", tail)
    if len(tail) >= 48 and re_word_char.search(tail) is None:
        if not re_points.sub("", tail).strip():
            local = [None, None]
            out = []
            append = out.append
            for xs, ys, exts in re_points.findall(tail):
                x = resolve(xs, local, 0)
                y = resolve(ys, local, 1)
                local[0], local[1] = x, y
                append(('pt', x, y, int(exts) if exts else None))
            return out
    return full_tokenise(tail)


def tails(path):
    """Every wiring form's tail, cut the way the parser cuts them."""
    text = open(path).read()
    out = []
    for stmt in re.finditer(r"^\s*-\s+\S[^;]*;", text, re.M | re.S):
        s = stmt.group(0)
        for pattern in (CompiledRe.re_special_wiring_form,
                        CompiledRe.re_regular_wiring_form):
            matches = list(pattern.finditer(s))
            for i, m in enumerate(matches):
                end = matches[i + 1].start() if i + 1 < len(matches) else len(s)
                if i + 1 == len(matches):
                    # The parser ends the last form's tail at the non-wiring clause.
                    clause = CompiledRe.re_non_wiring_clause.search(s, m.end())
                    if clause is not None:
                        end = min(end, clause.start())
                out.append(s[m.end():end])
    return [t for t in out if t.strip()]


def via_array_tails(n_tails, n_pts, seed=3):
    """Via-array tails at the real design's scale (hundreds of points each)."""
    rng = np.random.default_rng(seed)
    return [" ".join(f"( {int(v)} {int(w)} )" for v, w in
                     zip(rng.integers(0, 10**7, n_pts), rng.integers(0, 10**7, n_pts)))
            for _ in range(n_tails)]


def bench(ts, label, reps=5):
    n_chars = sum(len(t) for t in ts)
    for t in ts:
        assert old_scan(t) == new_scan(t), (label, t[:80])
    olds, news = [], []
    for _ in range(4):
        for fn, acc in ((old_scan, olds), (new_scan, news)):
            best = 1e9
            for _ in range(reps):
                t0 = time.perf_counter()
                for t in ts:
                    fn(t)
                best = min(best, time.perf_counter() - t0)
            acc.append(best)
    t_old, t_new = min(olds), min(news)
    print(f"{label}: old {t_old * 1e3:8.2f} ms ({t_old / n_chars * 1e9:5.1f} ns/ch)  "
          f"new {t_new * 1e3:8.2f} ms ({t_new / n_chars * 1e9:5.1f} ns/ch)  "
          f"{t_old / t_new:.2f}x")


def main():
    gcd = tails(DEF)
    arr = via_array_tails(200, 512)
    print(f"{len(gcd)} real tails from gcd_nangate45.def + {len(arr)} synthetic via arrays")
    bench(gcd, "gcd (1-2 pt tails)      ")
    bench(arr, "via arrays (512 pt)     ")
    bench(gcd + arr, "mix                   ")


if __name__ == "__main__":
    main()
