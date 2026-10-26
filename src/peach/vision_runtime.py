"""人像运行环境自检；容器构建时准备定版模型，再以运行用户离线执行推理。"""
from __future__ import annotations

import argparse
import json

from . import face_detect, face_match


def verify(*, prepare: bool = False) -> dict:
    """校验依赖、模型摘要、YuNet 与 SFace 推理；仅 prepare 允许下载模型。"""
    import cv2
    import numpy

    detector = face_detect.FaceDetector(allow_download=prepare)
    embedder = face_match.FaceEmbedder(detector=detector, allow_download=prepare)
    image = numpy.zeros((320, 320, 3), dtype=numpy.uint8)
    detector.detect(image)
    # 固定几何只用于验证特征网络，不能作为人物身份或图库命中的证据。
    face = face_detect.Face(.5, .5, .5, .5, 1.0,
                            (.35, .35, .65, .35, .5, .5, .4, .65, .6, .65))
    feature = embedder._feature(image, face)
    if len(feature) != 128 or not numpy.isfinite(feature).all() or face_match.cosine(feature, feature) < .99:
        raise RuntimeError('人脸比对运行环境自检失败')
    return {'opencv': cv2.__version__, 'detector_inference': True, 'embedding_dimensions': len(feature),
            'allow_download': prepare}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true', help='允许下载固定摘要的模型')
    args = parser.parse_args(argv)
    print(json.dumps(verify(prepare=args.prepare), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
