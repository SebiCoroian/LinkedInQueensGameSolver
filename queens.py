import time
from typing import List, Tuple, Dict

import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab   # cross-platform screenshot

# ---------- 1.  take screenshot -------------------------------------------------
print('[*] Grabbing screenshot…')
ss = ImageGrab.grab()                # PIL.Image
ss.save('debug_screenshot.png')      # Save screenshot for debugging
frame = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2BGR)

# ---------- 2.  find the board --------------------------------------------------
import sys
max_attempts = 30
attempt = 0
while True:
    gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges  = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    board_rect = None
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        # heuristic: square-ish, at least 150 px, moderately dark border (less strict)
        if abs(w - h) < 20 and w > 150:
            border = gray[y:y+5, x:x+w]          # top 5-px strip
            if np.mean(border) < 80:             # allow lighter borders
                board_rect = (x, y, w, h)
                break
    if board_rect is not None:
        break
    attempt += 1
    if attempt >= max_attempts:
        raise RuntimeError('Board not found after multiple attempts – check zoom/scroll')
    print(f'[!] Board not found, retrying in 0.5s (attempt {attempt}/{max_attempts})…')
    time.sleep(0.5)
    ss = ImageGrab.grab()
    ss.save('debug_screenshot.png')
    frame = cv2.cvtColor(np.array(ss), cv2.COLOR_RGB2BGR)

bx, by, bw, bh = board_rect
print(f'[*] Board @ ({bx},{by}) {bw}×{bh}')

# ---------- 3.  split into cells & build colour grid ----------------------------
# count internal grid lines to infer N
proj = np.sum(gray[by:by+bh, bx:bx+bw] < 40, axis=0)  # vertical black pixels
grid_lines = np.where(proj > 0.5 * np.max(proj))[0]
grid_lines = np.unique(np.concatenate(([0], grid_lines, [bw-1])))

# deduce cell edges
edges_x = np.sort(grid_lines)
cell_coords = []
for i in range(len(edges_x)-1):
    if edges_x[i+1]-edges_x[i] > 5:           # ignore 1-px duplicates
        cell_coords.append((edges_x[i], edges_x[i+1]))
N = len(cell_coords)
cell_size = (cell_coords[0][1] - cell_coords[0][0])

print(f'[*] Detected {N} × {N} grid (cell {cell_size}px)')

# sample colour at cell centres
color_grid = np.zeros((N, N, 3), dtype=np.uint8)
for r in range(N):
    for c in range(N):
        cx = bx + cell_coords[c][0] + cell_size//2
        cy = by + cell_coords[r][0] + cell_size//2
        color_grid[r, c] = frame[cy, cx]

# ---------- 4.  assign contiguous regions IDs -----------------------------------
def rgb_to_key(rgb):          # coarse → robust to jpeg/compression
    return tuple((rgb//20).tolist())          # shrink colour space

region_grid = [[-1]*N for _ in range(N)]
current_id  = 0
for r in range(N):
    for c in range(N):
        if region_grid[r][c] != -1:
            continue
        key = rgb_to_key(color_grid[r, c])
        # flood-fill contiguous same-key cells
        stack = [(r, c)]
        while stack:
            y0, x0 = stack.pop()
            if (y0 < 0 or y0 >= N or x0 < 0 or x0 >= N):
                continue
            if region_grid[y0][x0] != -1:
                continue
            if rgb_to_key(color_grid[y0, x0]) != key:
                continue
            region_grid[y0][x0] = current_id
            stack.extend([(y0-1,x0),(y0+1,x0),(y0,x0-1),(y0,x0+1)])
        current_id += 1

print(f'[*] Found {current_id} colour regions')

# ---------- 5.  solve -----------------------------------------------------------
def solve_queens(region_grid: List[List[int]]) -> List[Tuple[int, int]]:
    N = len(region_grid)
    COLS = 0
    region_mask = 0
    solution = [-1]*N
    rows_left = list(range(N))

    def legal_count(r: int) -> int:
        cnt = 0
        for c in range(N):
            if (COLS>>c)&1:                         continue
            if (region_mask>>region_grid[r][c])&1: continue
            if 0<=r-1 and solution[r-1]!=-1 and abs(solution[r-1]-c)==1: continue
            if r+1<N and solution[r+1]!=-1 and abs(solution[r+1]-c)==1: continue
            cnt += 1
        return cnt

    def backtrack()->bool:
        nonlocal COLS,region_mask
        if not rows_left:
            return True
        r = min(rows_left,key=legal_count)
        rows_left.remove(r)
        for c in range(N):
            if (COLS>>c)&1 or (region_mask>>region_grid[r][c])&1: continue
            if 0<=r-1 and solution[r-1]!=-1 and abs(solution[r-1]-c)==1: continue
            if r+1<N and solution[r+1]!=-1 and abs(solution[r+1]-c)==1: continue
            solution[r]=c
            COLS       |=1<<c
            region_mask|=1<<region_grid[r][c]
            if backtrack(): return True
            COLS       ^=1<<c
            region_mask^=1<<region_grid[r][c]
            solution[r]=-1
        rows_left.append(r)
        return False

    if not backtrack():
        raise ValueError('No solution')
    return [(r, solution[r]) for r in range(N)]

coords = solve_queens(region_grid)
print('[*] Solution:', coords)

# ---------- 6.  click the squares ----------------------------------------------
print('[*] Clicking queens (double-click)…')
for r,c in coords:
    x = bx + cell_coords[c][0] + cell_size//2
    y = by + cell_coords[r][0] + cell_size//2
    pyautogui.doubleClick(x, y, duration=0.05)   # duration smooths movement a bit
    time.sleep(0.05)                             # tiny pause so the page keeps up

print('[✓] Done.')
