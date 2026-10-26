"""容器人像环境自检：模型准备权限、双模型推理和异常结果。"""
import sys
import unittest
from unittest import mock

from peach import vision_runtime


class VisionRuntimeTests(unittest.TestCase):
    def test_missing_opencv_fails_before_model_or_network_access(self):
        with mock.patch.dict(sys.modules, {'cv2': None}), \
                mock.patch.object(vision_runtime.face_detect, 'FaceDetector') as detector:
            with self.assertRaises(ModuleNotFoundError):
                vision_runtime.verify()
            detector.assert_not_called()

    def test_both_models_run_and_runtime_check_disallows_download(self):
        with mock.patch.object(vision_runtime.face_detect, 'FaceDetector') as detector, \
                mock.patch.object(vision_runtime.face_match, 'FaceEmbedder') as embedder:
            embedder.return_value._feature.return_value = (1.0,) * 128
            report = vision_runtime.verify()
            detector.assert_called_once_with(allow_download=False)
            embedder.assert_called_once_with(detector=detector.return_value, allow_download=False)
            self.assertEqual(detector.return_value.detect.call_count, 1)
            self.assertEqual(embedder.return_value._feature.call_count, 1)
            self.assertEqual(report['embedding_dimensions'], 128)
            self.assertFalse(report['allow_download'])

    def test_prepare_allows_fixed_model_downloads(self):
        with mock.patch.object(vision_runtime.face_detect, 'FaceDetector') as detector, \
                mock.patch.object(vision_runtime.face_match, 'FaceEmbedder') as embedder:
            embedder.return_value._feature.return_value = (1.0,) * 128
            self.assertTrue(vision_runtime.verify(prepare=True)['allow_download'])
            detector.assert_called_once_with(allow_download=True)

    def test_invalid_embedding_fails_the_build_probe(self):
        for feature in ((0.0,) * 128, (1.0,) * 32, (float('nan'),) * 128):
            with self.subTest(length=len(feature)), \
                    mock.patch.object(vision_runtime.face_detect, 'FaceDetector'), \
                    mock.patch.object(vision_runtime.face_match, 'FaceEmbedder') as embedder:
                embedder.return_value._feature.return_value = feature
                with self.assertRaises(RuntimeError):
                    vision_runtime.verify()
