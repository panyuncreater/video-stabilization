"""视频读写封装（AGENTS.md §6 io_utils）：分辨率/帧率/编码器一致性检查。

退出码约定（§12）：1 = 输入视频打不开 / 帧读取失败；3 = 输出封装一致性检查失败。
视频编解码不重造轮子：仅使用 cv2.VideoCapture / VideoWriter（红线 5）。
"""

from __future__ import annotations

import cv2
import numpy as np

EXIT_OK = 0
EXIT_INPUT_ERROR = 1
EXIT_TRACKING_FAILED = 2
EXIT_OUTPUT_INCONSISTENT = 3
EXIT_INTERNAL = 4


class InputError(Exception):
    """输入视频打不开或帧读取失败（退出码 1）。"""


class OutputConsistencyError(Exception):
    """输出封装一致性检查失败（退出码 3）。"""


class VideoReader:
    """cv2.VideoCapture 封装：属性预取 + 读帧失败显式报错。"""

    def __init__(self, path: str):
        self.path = path
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise InputError(f"无法打开视频: {path}")
        self.fps = float(self.cap.get(cv2.CAP_PROP_FPS))
        if not np.isfinite(self.fps) or self.fps <= 0:
            self.fps = 30.0  # 元数据缺失时兜底（warning 由调用方记录）
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if self.width <= 0 or self.height <= 0:
            self.release()
            raise InputError(f"视频分辨率非法: {path} ({self.width}x{self.height})")

    def read(self):
        """读取下一帧（BGR uint8）；结束返回 None；读帧异常抛 InputError。"""
        ok, frame = self.cap.read()
        if not ok:
            return None
        if frame is None or frame.shape[0] != self.height or frame.shape[1] != self.width:
            raise InputError(f"帧读取失败或尺寸不一致: {self.path}")
        return frame

    def release(self) -> None:
        self.cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


class VideoWriterWrap:
    """cv2.VideoWriter 封装：mp4v 编码，写入帧一致性检查。"""

    def __init__(self, path: str, fps: float, width: int, height: int):
        if fps <= 0 or width <= 0 or height <= 0:
            raise OutputConsistencyError(f"非法输出参数: fps={fps}, size={width}x{height}")
        if width % 2 or height % 2:
            raise OutputConsistencyError(f"mp4v 要求偶数尺寸: {width}x{height}")
        self.path = path
        self.fps = fps
        self.width = width
        self.height = height
        self.writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        if not self.writer.isOpened():
            raise OutputConsistencyError(f"无法创建输出视频: {path}")

    def write(self, frame: np.ndarray) -> None:
        if frame is None or frame.shape[0] != self.height or frame.shape[1] != self.width:
            raise OutputConsistencyError(
                f"写入帧尺寸与声明不一致: 期望 {self.width}x{self.height}")
        if frame.ndim == 2:  # 灰度转 BGR
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        self.writer.write(frame)

    def release(self) -> None:
        self.writer.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()
