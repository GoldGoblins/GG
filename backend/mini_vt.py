from __future__ import annotations


class MiniVt:
    """Small VT cursor screen. Replaces a TUI, does not append a log."""

    def __init__(self, rows: int = 36, cols: int = 72) -> None:
        self.rows = max(8, int(rows))
        self.cols = max(16, int(cols))
        self.reset()

    def reset(self) -> None:
        self.buf = [[" " for _ in range(self.cols)] for _ in range(self.rows)]
        self.r = 0
        self.c = 0
        self.saved = (0, 0)
        self._mode = "text"
        self._csi = ""

    def display(self) -> str:
        lines = ["".join(row).rstrip() for row in self.buf]
        while len(lines) > 1 and lines[-1] == "":
            lines.pop()
        return "\n".join(lines) + "\n"

    def feed(self, data: str) -> None:
        for ch in str(data or ""):
            self._step(ch)

    def _step(self, ch: str) -> None:
        if self._mode == "osc":
            if ch == "\x07":
                self._mode = "text"
            elif ch == "\x1b":
                self._mode = "osc_st"
            return
        if self._mode == "osc_st":
            self._mode = "text" if ch == "\\" else "osc"
            return
        if self._mode == "esc":
            if ch == "[":
                self._mode = "csi"
                self._csi = ""
            elif ch == "]":
                self._mode = "osc"
            elif ch in "()":
                self._mode = "esc_one"
            else:
                self._mode = "text"
            return
        if self._mode == "esc_one":
            self._mode = "text"
            return
        if self._mode == "csi":
            if ("A" <= ch <= "Z") or ("a" <= ch <= "z") or ch in "@`~":
                self._csi_exec(self._csi, ch)
                self._mode = "text"
            else:
                self._csi += ch
            return
        if ch == "\x1b":
            self._mode = "esc"
            return
        self._put(ch)

    def _put(self, ch: str) -> None:
        if ch == "\n":
            self.r = min(self.rows - 1, self.r + 1)
            self.c = 0
            return
        if ch == "\r":
            self.c = 0
            return
        if ch == "\b":
            self.c = max(0, self.c - 1)
            return
        if ch == "\t":
            self.c = min(self.cols - 1, (self.c // 8 + 1) * 8)
            return
        if ord(ch) < 32:
            return
        if self.c >= self.cols:
            self.c = 0
            self.r = min(self.rows - 1, self.r + 1)
        self.buf[self.r][self.c] = ch
        self.c += 1

    def _nums(self, raw: str) -> list[int]:
        body = raw.lstrip("?")
        if not body:
            return []
        out: list[int] = []
        for part in body.split(";"):
            if part.isdigit():
                out.append(int(part))
            elif part == "":
                out.append(0)
        return out

    def _erase_row(self, row: int, start: int, end: int) -> None:
        for x in range(start, end):
            self.buf[row][x] = " "

    def _csi_exec(self, params: str, cmd: str) -> None:
        nums = self._nums(params)
        n = nums[0] if nums else 0
        m = nums[1] if len(nums) > 1 else 0
        if cmd in "Hf":
            self.r = min(self.rows - 1, max(0, (n or 1) - 1))
            self.c = min(self.cols - 1, max(0, (m or 1) - 1))
            return
        if cmd == "A":
            self.r = max(0, self.r - (n or 1))
            return
        if cmd == "B":
            self.r = min(self.rows - 1, self.r + (n or 1))
            return
        if cmd == "C":
            self.c = min(self.cols - 1, self.c + (n or 1))
            return
        if cmd == "D":
            self.c = max(0, self.c - (n or 1))
            return
        if cmd == "G":
            self.c = min(self.cols - 1, max(0, (n or 1) - 1))
            return
        if cmd == "d":
            self.r = min(self.rows - 1, max(0, (n or 1) - 1))
            return
        if cmd == "J":
            if n in (2, 3):
                self.reset()
                self._mode = "text"
                return
            if n == 1:
                for y in range(0, self.r):
                    self.buf[y] = [" "] * self.cols
                self._erase_row(self.r, 0, self.c + 1)
                return
            self._erase_row(self.r, self.c, self.cols)
            for y in range(self.r + 1, self.rows):
                self.buf[y] = [" "] * self.cols
            return
        if cmd == "K":
            if n == 1:
                self._erase_row(self.r, 0, self.c + 1)
            elif n == 2:
                self.buf[self.r] = [" "] * self.cols
            else:
                self._erase_row(self.r, self.c, self.cols)
            return
        if cmd == "s":
            self.saved = (self.r, self.c)
            return
        if cmd == "u":
            self.r, self.c = self.saved
