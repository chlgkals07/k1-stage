#!/usr/bin/env python3
"""model00.yml 원본에서 P1 수정본(model00_p1.yml)을 생성한다.

변경은 정확히 두 군데:
1. mixData: CH5/CH6/CH7(destCh 4/5/6)의 기존 믹스 바로 뒤에 L1 게이트 REPL 믹스 추가
   (기존 CH11 "mode" 믹스의 서식을 그대로 복제, weight만 GV6/GV4/GV5)
2. flightModeData 앞에 logicalSw 섹션(L1 = FUNC_STICKY) 신설

사용: python3 gen_model_p1.py <원본> <출력>
"""

import sys

MIX_TEMPLATE = """ -
   weight: {gv}
   destCh: {dest}
   srcRaw: MAX
   carryTrim: 1
   mixWarn: 0
   mltpx: REPL
   speedPrec: 0
   offset: 0
   swtch: "L1"
   flightModes: 000000000
   delayUp: 0
   delayDown: 0
   speedUp: 0
   speedDown: 0
   name: "{name}"
"""

PC_MIXES = {4: ("GV6", "pc5"), 5: ("GV4", "pc6"), 6: ("GV5", "pc7")}

LOGICAL_SW = """logicalSw:
   0:
      func: FUNC_STICKY
      def: "NONE,NONE"
      andsw: "NONE"
      delay: 0
      duration: 0
"""


def main():
    src, dst = sys.argv[1], sys.argv[2]
    # 원본이 CRLF(EdgeTX SD 파일)라 개행을 그대로 보존한다
    raw = open(src, newline="").read()
    lines = raw.splitlines(keepends=True)
    eol = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"

    global MIX_TEMPLATE, LOGICAL_SW
    if eol == "\r\n":
        MIX_TEMPLATE = MIX_TEMPLATE.replace("\n", "\r\n")
        LOGICAL_SW = LOGICAL_SW.replace("\n", "\r\n")

    out = []
    i = 0
    in_mixdata = False
    block = []          # 현재 믹스 블록 누적
    block_dest = None

    def flush_block():
        nonlocal block, block_dest
        out.extend(block)
        if block_dest in PC_MIXES:
            gv, name = PC_MIXES[block_dest]
            out.append(MIX_TEMPLATE.format(gv=gv, dest=block_dest, name=name))
        block, block_dest = [], None

    while i < len(lines):
        line = lines[i]
        if line.startswith("mixData:"):
            in_mixdata = True
            out.append(line)
        elif in_mixdata:
            if line.startswith(" -"):          # 새 믹스 블록 시작
                flush_block()
                block = [line]
            elif line[0] not in " \t\n":       # mixData 섹션 종료 (다음 최상위 키)
                flush_block()
                in_mixdata = False
                out.append(line)
            else:
                block.append(line)
                stripped = line.strip()
                if stripped.startswith("destCh:"):
                    block_dest = int(stripped.split(":")[1])
        elif line.startswith("flightModeData:"):
            out.append(LOGICAL_SW)
            out.append(line)
        else:
            out.append(line)
        i += 1
    flush_block()

    open(dst, "w", newline="").write("".join(out))
    print(f"written: {dst}")


if __name__ == "__main__":
    main()
