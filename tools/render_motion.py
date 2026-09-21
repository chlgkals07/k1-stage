#!/usr/bin/env python3
"""리타깃 모션 CSV 를 MuJoCo K1 몸으로 렌더해 mp4 로 굽는다.

`/pad` 버튼을 눌렀을 때 모니터에 "이 동작이 이렇게 생겼다"를 보여주기 위한 클립을
만드는 도구다. 물리를 굴리지 않고 자세만 먹이므로(mj_forward) 흔들리거나 넘어지지
않는다 — 정책 롤아웃이 아니라 **레퍼런스 재생**이다.

## 실행

mujoco 는 시스템 python3 에 없다. GEM-X 가상환경의 python 으로 실행해야 한다.

    cd /home/robotis-ai/Projects/shape10
    MUJOCO_GL=egl GEM-X/.venv/bin/python \
        /home/robotis-ai/Projects/shape3/tools/render_motion.py \
        outputs/0043_casual_greeting_R_001__A428/prepared/casual_greeting_R_001__A428.csv \
        /tmp/casual_greeting.mp4

한 클립(약 300프레임)에 1.5초쯤 걸린다.

## CSV 형식

헤더 없는 30열이고, 이 값이 그대로 모델의 ``nq`` 와 일치한다.

    0:3    root 위치
    3:7    쿼터니언 **(x, y, z, w)**  ← MuJoCo 는 (w, x, y, z) 라 재배열이 필요하다.
           안 하면 로봇이 누운 채로 렌더된다
    7:30   관절 23개

## 카메라

로봇의 정면은 프레임 0 몸통 yaw 기준 **``yaw + 180``** 이다 (처음에 이걸 몰라서
뒤통수를 찍었다). ``--azimuth-offset`` 이 그 각도이며 기본 145 는 3/4 뷰,
180 이면 정면이다.

카메라를 세계 좌표가 아니라 **로봇 방향 기준**으로 잡기 때문에, 동작마다 리타깃
결과의 world yaw 가 달라도 클립 12개가 같은 뷰로 통일된다. 세트로 보일 때 이게
중요하다 — 하나만 각도가 다르면 바로 티가 난다.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

import numpy as np

os.environ.setdefault("MUJOCO_GL", "egl")

SCENE = ("/home/robotis-ai/Projects/shape10/cyclo_lab/third_party/ai_sapiens"
         "/ai_sapiens_description/mujoco/k1/scene.xml")


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("csv", help="리타깃 결과 CSV (헤더 없는 30열)")
    ap.add_argument("out", help="출력 mp4")
    ap.add_argument("--scene", default=SCENE, help="MuJoCo K1 scene.xml")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--azimuth-offset", type=float, default=145.0,
                    help="로봇 정면이 yaw+180 이다. 145=3/4 뷰, 180=정면")
    ap.add_argument("--elevation", type=float, default=-8.0)
    ap.add_argument("--distance", type=float, default=2.15)
    ap.add_argument("--lookat-scale", type=float, default=0.92,
                    help="골반 높이에 곱해 카메라가 볼 지점. 1.0 이면 머리가 잘린다")
    ap.add_argument("--smooth", type=int, default=15,
                    help="추적 카메라 이동평균 프레임 수. 카메라 떨림을 막는다")
    ap.add_argument("--margin", type=float, default=0.10,
                    help="자동 프레이밍이 남기는 상하좌우 여백 비율")
    ap.add_argument("--no-autofit", dest="autofit", action="store_false",
                    help="자동 프레이밍을 끄고 --distance 를 그대로 쓴다")
    return ap.parse_args()


def to_qpos(row):
    """CSV 한 줄을 MuJoCo qpos 로. 쿼터니언 순서만 바꾸면 된다."""
    q = row.copy()
    x, y, z, w = row[3:7]
    q[3:7] = (w, x, y, z)
    return q


def body_yaw_deg(quat_wxyz):
    w, x, y, z = quat_wxyz
    return np.degrees(np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


def main():
    args = parse_args()
    try:
        import mujoco
    except ImportError:
        sys.exit("mujoco 를 못 찾았다. GEM-X 가상환경으로 실행하라:\n"
                 "  /home/robotis-ai/Projects/shape10/GEM-X/.venv/bin/python " + __file__)

    data = np.loadtxt(args.csv, delimiter=",")
    if data.ndim == 1:
        data = data[None, :]

    # scene.xml 의 오프스크린 버퍼는 640x480 이라 그대로 쓰면 HD 로 못 굽는다.
    # 남의 저장소 파일이라 건드리지 않고 MjSpec 으로 메모리에서만 키운다.
    spec = mujoco.MjSpec.from_file(args.scene)
    spec.visual.global_.offwidth = max(args.width, spec.visual.global_.offwidth)
    spec.visual.global_.offheight = max(args.height, spec.visual.global_.offheight)
    model = spec.compile()

    if data.shape[1] != model.nq:
        sys.exit(f"열 수 불일치: CSV {data.shape[1]} vs 모델 nq {model.nq}")

    mj_data = mujoco.MjData(model)
    mj_data.qpos[:] = to_qpos(data[0])
    mujoco.mj_forward(model, mj_data)
    yaw = body_yaw_deg(mj_data.qpos[3:7])

    # 카메라는 로봇을 따라간다. 궤적 평균에 고정하면 이동하는 동작(팔굽혀펴기·걷기)
    # 에서 로봇이 화면 밖으로 밀려난다. 실제로 첫 렌더에서 그렇게 잘렸다.
    # 골반 높이를 그대로 보면 서 있을 때 머리가 잘리므로 조금 낮춰 몸 중심을 본다.
    # 프레임마다 그대로 따라가면 미세 진동이 카메라 떨림으로 보이므로 이동평균을 쓴다.
    look = data[:, :3].copy()
    look[:, 2] *= args.lookat_scale
    if len(look) > 1:
        win = max(1, min(args.smooth, len(look)))
        pad = np.pad(look, ((win // 2, win - 1 - win // 2), (0, 0)), mode="edge")
        kernel = np.ones(win) / win
        look = np.stack([np.convolve(pad[:, i], kernel, mode="valid") for i in range(3)], axis=1)

    cam = mujoco.MjvCamera()
    cam.azimuth = yaw + args.azimuth_offset
    cam.elevation = args.elevation
    cam.distance = args.distance

    renderer = mujoco.Renderer(model, height=args.height, width=args.width)
    renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = True
    renderer.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = True

    def draw(frame_index, target):
        mj_data.qpos[:] = to_qpos(data[frame_index])
        mujoco.mj_forward(model, mj_data)
        cam.lookat[:] = target
        renderer.update_scene(mj_data, camera=cam)
        return renderer.render()

    def silhouette_bbox(indices):
        """표본 프레임들에서 로봇이 차지하는 픽셀 범위(합집합).

        로봇만 밝은 회색이고 하늘·바닥은 어둡다. 기하로 계산하면 메시의 두께를
        놓쳐 과소평가되므로, 실제 그려진 것을 본다.
        """
        top, bottom, left, right_edge = args.height, 0, args.width, 0
        for i in indices:
            gray = draw(i, look[i]).mean(axis=2)
            mask = gray > 190
            if not mask.any():
                continue
            rows, cols = np.where(mask)
            top, bottom = min(top, rows.min()), max(bottom, rows.max())
            left = min(left, cols.min())
            right_edge = max(right_edge, cols.max())
        if bottom <= top or right_edge <= left:
            return None
        return top, bottom, left, right_edge

    # 동작마다 몸이 차지하는 크기가 다르다. 팔굽혀펴기는 엎드려 넓게 퍼지고 손 흔들기는
    # 팔을 위로 뻗는다. 고정 거리로 굽자 전자는 아래가 잘리고 후자는 위가 닿았다.
    # 표본 프레임을 실제로 그려 보고 거리와 높이를 맞춘다. 한 번 더 돌려 잔차를 줄인다.
    if args.autofit and len(data) > 1:
        samples = sorted({int(len(data) * p) for p in
                          (0.05, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95)} & set(range(len(data))))
        fovy = np.radians(model.vis.global_.fovy)
        for _ in range(2):
            box = silhouette_bbox(samples)
            if box is None:
                break
            top, bottom, left, right_edge = box
            usable = 1.0 - 2 * args.margin
            scale = max((bottom - top) / (args.height * usable),
                        (right_edge - left) / (args.width * usable))
            world_per_px = 2 * cam.distance * np.tan(fovy / 2) / args.height
            # 세로: 화면 아래로 치우친 만큼 보는 높이를 내린다.
            look[:, 2] -= ((top + bottom) / 2 - args.height / 2) * world_per_px
            # 가로: 골반을 따라가면 엎드린 자세에서 몸이 앞으로 뻗어 치우친다.
            # 화면 오른쪽 방향을 월드 좌표로 바꿔 그만큼 밀어 준다.
            az = np.radians(cam.azimuth)
            right = np.array([-np.sin(az), np.cos(az)])
            look[:, :2] += right * (((left + right_edge) / 2 - args.width / 2) * world_per_px)
            cam.distance *= max(scale, 0.35)

    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{args.width}x{args.height}", "-r", str(args.fps), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
         "-movflags", "+faststart", args.out],
        stdin=subprocess.PIPE)

    for row, target in zip(data, look):
        mj_data.qpos[:] = to_qpos(row)
        mujoco.mj_forward(model, mj_data)
        cam.lookat[:] = target
        renderer.update_scene(mj_data, camera=cam)
        ffmpeg.stdin.write(renderer.render().tobytes())

    ffmpeg.stdin.close()
    if ffmpeg.wait() != 0:
        sys.exit("ffmpeg 실패")
    print(f"완료 {args.out}  {len(data)} 프레임 / {len(data) / args.fps:.1f}초  "
          f"카메라 az={cam.azimuth:.0f} el={cam.elevation:.0f}")


if __name__ == "__main__":
    main()
