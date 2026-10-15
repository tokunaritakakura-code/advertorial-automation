#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""テロップ消し v2 —— ボカさずに、同じカットの別のコマから本物の絵を持ってきて埋める。

v1 の問題：cv2.inpaint(TELEA) で塗ってから、塗り跡にわざと GaussianBlur を掛けとった。
          → 帯状のモザイクになる。

v2 の考え方：
  テロップは画面に貼り付いとるが、絵はカメラと一緒に動く。
  やから同じカットの別のコマでは、テロップの下にあった絵が別の場所に写っとる。
  カメラの動きを測って重ね直せば、本物の画素を持ってこれる。
  どうしても持ってこれん所（カメラが完全に止まっとるカット）だけ TELEA で塗る。ボカシは掛けん。
"""
import cv2, numpy as np, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notelop_inpaint as N

W, H = N.W, N.H
SW, SH = 360, 640                      # カメラの動きを測る時の縮小サイズ
CRIT = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5)
RING_TOL = 6.0            # 穴のまわりの合致。この値より大きくズレとったら持ってこん（0-255）
FILL_MIN = 0.75           # 塊のこの割合まで埋まらんかったら、借りた画素は捨てて全部塗り直す（ブロック状よけ）


def fit_affine(g0, g1, m0, m1, init=None):
    """g1 を g0 に合わせるアフィン変換を返す（テロップの所は見に行かん）"""
    warp = np.eye(2, 3, dtype=np.float32) if init is None else init.copy()
    valid = ((m0 == 0) & (m1 == 0)).astype(np.uint8)
    if valid.mean() < 0.25:
        valid = (m0 == 0).astype(np.uint8)
    try:
        _, warp = cv2.findTransformECC(g0, g1, warp, cv2.MOTION_AFFINE, CRIT, valid, 5)
        return warp, True
    except cv2.error:
        try:
            w2 = np.eye(2, 3, dtype=np.float32)
            _, w2 = cv2.findTransformECC(g0, g1, w2, cv2.MOTION_TRANSLATION, CRIT, valid, 5)
            return w2, True
        except cv2.error:
            return np.eye(2, 3, dtype=np.float32), False


def to_full(warp):
    """縮小サイズで測った変換を、実寸に直す"""
    s = np.array([[W / SW, 0], [0, H / SH]], np.float32)
    si = np.array([[SW / W, 0], [0, SH / H]], np.float32)
    A = warp[:, :2]; t = warp[:, 2:]
    return np.hstack([s @ A @ si, s @ t]).astype(np.float32)


def compose(a, b):
    """a の後に b（どっちも 2x3）"""
    A = np.vstack([a, [0, 0, 1]]); B = np.vstack([b, [0, 0, 1]])
    return (A @ B)[:2].astype(np.float32)


def invert(a):
    return cv2.invertAffineTransform(a).astype(np.float32)


def clean_shot(frames, times, max_cand=24, progress=None):
    """1カットぶんのコマを受け取って、テロップを消したコマの配列を返す"""
    n = len(frames)
    masks = [N.full_mask(f, t) for f, t in zip(frames, times)]
    if all(m.max() == 0 for m in masks):
        return frames, 0.0

    grays = [cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (SW, SH)).astype(np.float32) / 255 for f in frames]
    smask = [cv2.resize(m, (SW, SH), interpolation=cv2.INTER_NEAREST) for m in masks]

    # 各コマ → 先頭コマ の変換。1コマずつ繋いだ値を初期値にして、先頭と直接合わせ直す
    to0 = [np.eye(2, 3, dtype=np.float32)]
    chain = np.eye(2, 3, dtype=np.float32)
    for i in range(1, n):
        step, _ = fit_affine(grays[i - 1], grays[i], smask[i - 1], smask[i])
        chain = compose(chain, step)
        direct, ok = fit_affine(grays[0], grays[i], smask[0], smask[i], init=chain)
        to0.append(direct if ok else chain)
        chain = to0[-1]

    out = []
    filled_ratio = []
    for i in range(n):
        m = masks[i]
        if m.max() == 0:
            out.append(frames[i]); continue
        need = m > 0
        acc = np.zeros((H, W, 3), np.float32)
        cnt = np.zeros((H, W), np.float32)
        # 🔑 穴のまわり（テロップやない所）が合うとるかで、持ってきてええか判定する
        ring = (cv2.dilate(m, np.ones((21, 21), np.uint8)) > 0) & (~need)
        order = sorted(range(n), key=lambda j: abs(j - i))[1:max_cand + 1]
        for j in order:
            if not need.any():
                break
            # j のコマを i の座標に持ってくる： i→0 の逆 ∘ j→0
            wji = to_full(compose(invert(to0[i]), to0[j]))
            src = cv2.warpAffine(frames[j], wji, (W, H), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                                 borderValue=(0, 0, 0))
            okmap = cv2.warpAffine(np.full((H, W), 255, np.uint8), wji, (W, H),
                                   flags=cv2.INTER_NEAREST + cv2.WARP_INVERSE_MAP, borderValue=0)
            mj = cv2.warpAffine(masks[j], wji, (W, H),
                                flags=cv2.INTER_NEAREST + cv2.WARP_INVERSE_MAP, borderValue=255)
            chk = ring & (okmap > 0) & (mj == 0)
            if chk.sum() < 400:
                continue
            err = float(np.abs(src[chk].astype(np.float32) - frames[i][chk].astype(np.float32)).mean())
            if err > RING_TOL:                      # ズレとる／中身が動いた → 使わん
                continue
            use = need & (okmap > 0) & (mj == 0) & (cnt < 2)
            if not use.any():
                continue
            acc[use] += src[use]; cnt[use] += 1
        got = cnt > 0
        # 🔑 継ぎはぎがブロック状に見えるのは「半分だけ埋まった」時。
        #    塊ごとに見て、ほとんど埋まらんかった塊は借りた画素を捨てて全部塗り直す。
        nlab, lab = cv2.connectedComponents(m)
        for k in range(1, nlab):
            comp = (lab == k) & need
            if comp.any() and got[comp].mean() < FILL_MIN:
                got[comp] = False
        res = frames[i].copy()
        res[got] = (acc[got] / cnt[got][:, None]).astype(np.uint8)
        rest = (need & ~got).astype(np.uint8) * 255
        if rest.max() > 0:
            # 細かい絵（毛並みなど）の上に太い帯が乗っとる所は、どう塗っても元には戻らん。
            # 角ばった色の塊（ブロック状）に見えるのが一番アカンので、
            # NS で塗ってから**塗った所の内側だけ**軽くぼかして「ピンボケ」に見せる。
            # ※ v1 は縁ごとぼかしとったので帯が目立った。ここは縁を残す。
            res = cv2.inpaint(res, rest, 15, cv2.INPAINT_NS)
            inner = cv2.erode(rest, np.ones((7, 7), np.uint8))
            a = (cv2.GaussianBlur(inner, (0, 0), 4.0).astype(np.float32) / 255)[:, :, None]
            res = (res * (1 - a) + cv2.GaussianBlur(res, (0, 0), 4.0) * a).astype(np.uint8)
        # 継ぎ目だけ 1px ぶん馴染ませる
        edge = cv2.morphologyEx(m, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
        a = (cv2.GaussianBlur(edge, (0, 0), 1.2).astype(np.float32) / 255)[:, :, None]
        res = (res * (1 - a) + cv2.GaussianBlur(res, (0, 0), 1.0) * a).astype(np.uint8)
        out.append(res)
        filled_ratio.append(float(got[need].mean()) if need.any() else 1.0)
        if progress:
            progress(i, n)
    return out, (float(np.mean(filled_ratio)) if filled_ratio else 1.0)
